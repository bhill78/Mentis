"""The additions fixture proxy's gate, against a REAL server on its OWN fixture.

Nothing here touches the live Brain, TEST, production or MARS: the module seeds
a fresh synthetic fixture inside this checkout, serves it with `mentis.web` on a
loopback port, puts the new write-capable proxy
(`tools/quiet-magnet-additions-preview.mjs`) in front of it, and throws the
whole root away afterwards. The parent clone's own seeded fixture is never
opened or written.

What is checked here is the ACCESS PATH, not the interface: which requests are
forwarded, which are refused before anything is written, whether the two
allowed writes really land in the fixture Brain, and whether the record is
untouched by everything that was refused.
"""
from __future__ import annotations

import json
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"
sys.path.insert(0, str(TOOLS))

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="the fixture proxy is a Node program")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def ask(url, *, method="GET", body=None, headers=None, timeout=20):
    request = urllib.request.Request(url, data=body, method=method,
                                     headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            raw = answer.read()
            try:
                return answer.status, json.loads(raw)
            except ValueError:
                return answer.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            return error.code, json.loads(raw)
        except ValueError:
            return error.code, raw.decode("utf-8", "replace")


def wait_for(url, process, seconds=120, headers=None):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if process.poll() is not None:
            raise RuntimeError(f"pid {process.pid} exited {process.returncode}")
        try:
            if ask(url, headers=headers, timeout=5)[0] == 200:
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError(f"did not answer: {url}")


def stop(process):
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def clean_env() -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("MENTIS", "MARS", "Q2_"))
           and k.upper() != "PYTHONPATH"}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    return env


class Trial:
    """One seeded fixture, one server, one proxy. Disposable."""

    def __init__(self, root: Path):
        self.root = root
        self.manifest = json.loads((root / "manifest.json").read_text("utf-8"))
        self.primary = self.manifest["primary"]
        self.A = self.primary["arrangement_key"]
        self.B = self.primary["B"]
        self.C = self.primary["C"]
        self.by, self.other = self.manifest["writes_allowed"]["participants"]
        self.server = None
        self.proxy = None
        self.logs = []

    def start(self):
        env = clean_env()
        no_window = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.server_port = free_port()
        log = open(self.root / "server.log", "ab")
        self.logs.append(log)
        self.server = subprocess.Popen(
            [sys.executable, "-m", "mentis.web", str(self.root / "primary"),
             "--port", str(self.server_port), "--mars",
             "quiet-magnet-additions-fixture-no-mars"],
            cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=no_window)
        self.upstream = f"http://127.0.0.1:{self.server_port}"
        wait_for(self.upstream + "/api/brain?identity=1", self.server,
                 headers={"X-Mentis-Client": "1"})
        dist = self.root / "dist"
        dist.mkdir(exist_ok=True)
        (dist / "index.html").write_text(
            "<!doctype html><title>fixture</title>", "utf-8")
        self.port = free_port()
        log = open(self.root / "proxy.log", "ab")
        self.logs.append(log)
        self.proxy = subprocess.Popen(
            ["node", str(TOOLS / "quiet-magnet-additions-preview.mjs"),
             "--front", self.upstream, "--port", str(self.port),
             "--dist", str(dist), "--log", str(self.root / "traffic.jsonl"),
             "--manifest", str(self.root / "manifest.json")],
            cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=no_window)
        self.base = f"http://127.0.0.1:{self.port}"
        wait_for(self.base + "/__q2/brain", self.proxy)
        status, brain = self.get("/fluid/api/needs-you/brain")
        assert status == 200, brain
        self.binding = f"{brain['brain']['corpus_id']}@{brain['brain']['instance']}"

    def stop(self):
        stop(self.proxy)
        stop(self.server)
        for log in self.logs:
            log.close()

    # -- how a request is made --------------------------------------------
    def get(self, path, **kw):
        return ask(self.base + path, headers={"X-Mentis-Client": "1",
                                              "Host": f"127.0.0.1:{self.port}"}, **kw)

    def write(self, path, body, *, headers=None, raw=None, method="POST",
              declared=None):
        sent = {"X-Mentis-Client": "1", "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
                "X-Mentis-Brain": self.binding}
        sent.update(headers or {})
        sent = {k: v for k, v in sent.items() if v is not None}
        data = raw if raw is not None else json.dumps(body).encode()
        if declared is not None:
            sent["Content-Length"] = str(declared)
        return ask(self.base + path, method=method, body=data, headers=sent)


@pytest.fixture(scope="module")
def trial():
    import quiet_magnet_additions_fixture as fixture

    root = REPO / ".preview" / f"additions-boundary-{os.getpid()}"
    if root.exists():
        shutil.rmtree(root)
    fixture.seed(root)
    t = Trial(root)
    try:
        t.start()
        yield t
    finally:
        t.stop()
        time.sleep(0.5)
        shutil.rmtree(root, ignore_errors=True)
        where = root.parent / (root.name + ".owner-auth.json")
        if where.exists():
            where.unlink()


@pytest.fixture
def record(trial):
    """The fixture Brain's logical record before and after one check."""
    import quiet_magnet_additions_fixture as fixture
    return lambda: fixture.brain_state(trial.root / "primary")["record_sha256"]


# -- the fixture page and its capability -------------------------------------

def test_the_page_is_read_only(trial):
    status, body = trial.get("/__q2/brain")
    assert status == 200
    assert body["readOnly"] is True


def test_the_capability_names_only_this_fixture(trial):
    status, body = trial.get("/__q2/magnet-capabilities")
    assert status == 200, body
    assert body == {"fixture": True, "corpus_id": trial.primary["corpus_id"],
                    "conversations": [trial.C], "arrangements": [trial.A]}


def test_reads_are_forwarded_and_capacity_is_not(trial):
    first = trial.manifest["primary"]["history"]["first_post"]
    status, body = trial.get(f"/fluid/api/posts?ids={first}")
    assert status == 200, body
    assert body["posts"][0]["home"] == trial.C
    assert trial.get("/api/capacity")[0] == 403
    assert trial.get("/api/capacity?all=1")[0] == 403


def test_the_seeded_history_and_work_read_back(trial):
    history = trial.manifest["primary"]["history"]
    status, body = trial.get(
        "/fluid/api/posts?ids=" + ",".join([history["history_reply"],
                                            history["work_anchor"]]))
    assert status == 200, body
    reply, anchor = body["posts"]
    assert reply["home"] == trial.C and reply["reply_to"] == history["first_post"]
    assert anchor["home"] == trial.C
    assert history["work_fixture"]["recorded"] is True
    assert history["work_fixture"]["started"] is False


# -- the one allowed post ----------------------------------------------------

def test_a_record_only_post_into_c_is_written(trial):
    status, body = trial.write("/fluid/api/posts", {
        "conversation": trial.C, "author": trial.by,
        "text": "FIXTURE SEND: written through the gated fixture proxy.",
        "op": "boundary-post-1"})
    assert status == 200, body
    assert body["home"] == trial.C
    assert body["action"] == "record-only"
    assert body["dispatched"] == 0
    trial.written_post = body["post"]
    found = trial.get(f"/fluid/api/posts?ids={body['post']}")[1]["posts"][0]
    assert found["home"] == trial.C


def test_the_same_operation_key_writes_once(trial, record):
    before = record()
    status, body = trial.write("/fluid/api/posts", {
        "conversation": trial.C, "author": trial.by,
        "text": "FIXTURE SEND: written through the gated fixture proxy.",
        "op": "boundary-post-1"})
    assert status == 200, body
    assert body["post"] == trial.written_post
    assert record() == before


def test_a_reply_inside_c_is_written(trial):
    status, body = trial.write("/fluid/api/posts", {
        "conversation": trial.C, "author": trial.other,
        "text": "FIXTURE REPLY: an answer inside the Magnet's Conversation.",
        "replies_to": trial.written_post, "op": "boundary-reply-1"})
    assert status == 200, body
    found = trial.get(f"/fluid/api/posts?ids={body['post']}")[1]["posts"][0]
    assert found["reply_to"] == trial.written_post
    assert found["home"] == trial.C


def test_a_reply_to_a_post_outside_c_is_refused(trial, record):
    before = record()
    outside = trial.manifest["primary"]["origin_post"]
    status, body = trial.write("/fluid/api/posts", {
        "conversation": trial.C, "author": trial.by,
        "text": "FIXTURE: this reply leaves the Magnet's Conversation.",
        "replies_to": outside, "op": "boundary-reply-outside"})
    assert status == 422, body
    assert "Magnet's own Conversation" in body["error"]
    assert record() == before


def test_a_reply_to_nothing_is_refused(trial, record):
    before = record()
    status, body = trial.write("/fluid/api/posts", {
        "conversation": trial.C, "author": trial.by, "text": "FIXTURE",
        "replies_to": "ent-000000000000", "op": "boundary-reply-missing"})
    assert status == 422, body
    assert record() == before


@pytest.mark.parametrize("body,why", [
    ({"conversation": None, "author": None, "text": "x", "op": "o"}, "another conversation"),
    ({"author": None, "text": "x", "op": "o", "action": "ask-mentis"}, "an ask"),
    ({"author": None, "text": "x", "op": "o", "action": "ask-participant"}, "an ask"),
    ({"author": None, "text": "x", "op": "o",
      "dispatch": [{"participant": "ent-1"}]}, "a dispatch"),
    ({"author": None, "text": "x", "op": "o", "addressed_to": ["ent-1"]}, "addressing"),
    ({"author": None, "op": "o",
      "parts": [{"type": "text", "text": "x"}]}, "parts and attachments"),
    ({"author": "human:brian", "text": "x", "op": "o"}, "a foreign author"),
    ({"author": None, "text": "x"}, "no operation key"),
    ({"author": None, "text": ""}, "no words"),
])
def test_everything_else_in_a_post_is_refused(trial, record, body, why):
    before = record()
    sent = dict(body)
    sent.setdefault("conversation", trial.C)
    if sent.get("conversation") is None:
        sent["conversation"] = trial.B
    if sent.get("author") is None:
        sent["author"] = trial.by
    status, answer = trial.write("/fluid/api/posts", sent)
    assert status == 422, (why, status, answer)
    assert record() == before, why


# -- the one allowed Magnet creation -----------------------------------------

def seed_body(conversation, **change):
    seed = {"sources": [{"kind": "conversation", "conversation": conversation}],
            "selection": {"informationTypes": ["post"]},
            "collection": {"mode": "one-time"},
            "synthesis": {"mode": "manual"},
            "notifications": {"newItems": False, "changes": False, "failures": False},
            "presentation": {"renderer": "disc"}}
    seed.update(change)
    return {"seed": seed,
            "attach": {"zone": {"type": "zone", "show": "magnet",
                                "name": "Fixture creation"}},
            "op": "boundary-magnet-1"}


def test_a_magnet_is_created_in_the_one_arrangement(trial):
    status, body = trial.write(f"/fluid/api/arrangements/{trial.A}/magnets",
                               seed_body(trial.B))
    assert status == 200, body
    trial.created = body["magnet"]["id"]
    read = trial.get(f"/fluid/api/arrangements/{trial.A}")
    assert read[0] == 200
    assert trial.created in json.dumps(read[1])


def test_the_same_magnet_key_creates_once(trial):
    status, body = trial.write(f"/fluid/api/arrangements/{trial.A}/magnets",
                               seed_body(trial.B))
    assert status == 200, body
    assert body["magnet"]["id"] == trial.created


@pytest.mark.parametrize("change,why", [
    ({"collection": {"mode": "continuous"}}, "continuous collection"),
    ({"collection": {"mode": "scheduled"}}, "scheduled collection"),
    ({"synthesis": {"mode": "on-new-information"}}, "automatic synthesis"),
    ({"notifications": {"newItems": True, "changes": False, "failures": False}},
     "notifications"),
    ({"selection": {"informationTypes": ["link"]}}, "an unsupported type"),
    ({"sources": [{"kind": "web", "url": "https://example.com"}]}, "a web source"),
    ({"sources": [{"kind": "conversation", "conversation": "ent-000000000000"}]},
     "a source outside this fixture"),
    ({"sources": [{"kind": "conversation", "conversation": "ent-000000000001"},
                  {"kind": "conversation", "conversation": "ent-000000000002"}]},
     "more than one source"),
])
def test_an_unsupported_configuration_is_refused(trial, record, change, why):
    before = record()
    status, body = trial.write(f"/fluid/api/arrangements/{trial.A}/magnets",
                               seed_body(trial.B, **change))
    assert status == 422, (why, status, body)
    assert record() == before, why


def test_another_arrangement_is_refused(trial, record):
    before = record()
    status, body = trial.write(f"/fluid/api/arrangements/{trial.B}/magnets",
                               seed_body(trial.B))
    assert status == 403, body
    assert record() == before


# -- the gate itself ---------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/fluid/api/po%73ts", "/fluid/api//posts", "/fluid/api/x/../posts",
    "/fluid/api/posts/", "/fluid/api/%70osts",
])
def test_an_encoded_or_aliased_path_is_refused(trial, record, path):
    before = record()
    status, body = trial.write(path, {"conversation": trial.C,
                                      "author": trial.by, "text": "x", "op": "o"})
    assert status in (400, 403), (path, status, body)
    assert record() == before


@pytest.mark.parametrize("method,path", [
    ("POST", "/fluid/api/requests"),
    ("POST", "/fluid/api/conversations"),
    ("POST", "/api/worker"),
    ("POST", "/api/owner/login"),
    ("PUT", "/fluid/api/posts"),
    ("DELETE", "/fluid/api/posts"),
])
def test_every_other_write_is_refused(trial, record, method, path):
    before = record()
    status, body = trial.write(path, {"any": "thing"}, method=method)
    assert status == 403, (method, path, status, body)
    assert record() == before


def test_a_post_edit_or_delete_is_refused(trial, record):
    before = record()
    for verb in ("edit", "delete", "comments", "reactions", "address"):
        status, body = trial.write(
            f"/fluid/api/posts/{trial.written_post}/{verb}", {"any": "thing"})
        assert status == 403, (verb, status, body)
    assert record() == before


@pytest.mark.parametrize("headers,expected", [
    ({"X-Mentis-Client": None}, 403),
    ({"Origin": None}, 403),
    ({"Origin": "https://evil.example"}, 403),
    ({"Origin": "http://127.0.0.1:1"}, 403),
    ({"X-Mentis-Brain": None}, 409),
    ({"X-Mentis-Brain": "another-corpus@abc"}, 409),
    ({"X-Mentis-Worker": "a-grant"}, 403),
    ({"Content-Type": "text/plain"}, 415),
    ({"Content-Type": None}, 415),
])
def test_a_request_without_this_fixtures_own_framing_is_refused(
        trial, record, headers, expected):
    before = record()
    status, body = trial.write("/fluid/api/posts", {
        "conversation": trial.C, "author": trial.by, "text": "x",
        "op": "boundary-header"}, headers=headers)
    assert status == expected, (headers, status, body)
    assert record() == before


def test_a_foreign_host_is_refused(trial, record):
    before = record()
    status, body = ask(trial.base + "/fluid/api/posts", method="POST",
                       body=b"{}", headers={"Host": "mentis.example.com",
                                            "X-Mentis-Client": "1"})
    assert status == 421, body
    assert record() == before


def test_a_body_that_is_not_json_or_is_oversize_is_refused(trial, record):
    before = record()
    assert trial.write("/fluid/api/posts", None, raw=b"{not json")[0] == 400
    assert trial.write("/fluid/api/posts", None, raw=b"[]")[0] == 422
    assert trial.write("/fluid/api/posts", None, raw=b"")[0] == 413
    big = json.dumps({"conversation": trial.C, "author": trial.by,
                      "text": "x" * 40000, "op": "big"}).encode()
    assert trial.write("/fluid/api/posts", None, raw=big)[0] == 413
    assert record() == before


def test_a_body_shorter_than_it_declared_is_refused(trial, record):
    """Sent on a raw socket: urllib cannot frame a request this way."""
    before = record()
    request = (
        f"POST /fluid/api/posts HTTP/1.1\r\nHost: 127.0.0.1:{trial.port}\r\n"
        f"X-Mentis-Client: 1\r\nContent-Type: application/json\r\n"
        f"Origin: http://127.0.0.1:{trial.port}\r\n"
        f"X-Mentis-Brain: {trial.binding}\r\nContent-Length: 99\r\n"
        f"Connection: close\r\n\r\n").encode() + b"{}"
    with socket.create_connection(("127.0.0.1", trial.port), timeout=20) as sock:
        sock.sendall(request)
        sock.shutdown(socket.SHUT_WR)
        answer = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            answer += chunk
    assert answer.startswith(b"HTTP/1.1 400"), answer[:200]
    assert record() == before


def test_the_proxy_refuses_to_start_against_another_brain(trial):
    """The gate is the server's identity, never the port it answers on."""
    env = clean_env()
    no_window = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    port = free_port()
    log = open(trial.root / "other-server.log", "ab")
    other = subprocess.Popen(
        [sys.executable, "-m", "mentis.web", str(trial.root / "secondary"),
         "--port", str(port), "--mars", "no-mars"],
        cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=no_window)
    try:
        wait_for(f"http://127.0.0.1:{port}/api/brain?identity=1", other,
                 headers={"X-Mentis-Client": "1"})
        done = subprocess.run(
            ["node", str(TOOLS / "quiet-magnet-additions-preview.mjs"),
             "--front", f"http://127.0.0.1:{port}", "--port", str(free_port()),
             "--dist", str(trial.root / "dist"),
             "--log", str(trial.root / "other-traffic.jsonl"),
             "--manifest", str(trial.root / "manifest.json")],
            cwd=REPO, env=env, capture_output=True, text=True, timeout=120,
            creationflags=no_window)
        assert done.returncode != 0, done.stdout
        assert "another Brain" in done.stderr or "another corpus" in done.stderr, done.stderr
    finally:
        stop(other)
        log.close()


def test_the_proxy_refuses_a_fixture_it_cannot_read(trial):
    env = clean_env()
    no_window = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    half = trial.root / "half"
    half.mkdir(exist_ok=True)
    (half / "manifest.json").write_text(json.dumps(
        {**trial.manifest, "setup_closed": False}), "utf-8")
    done = subprocess.run(
        ["node", str(TOOLS / "quiet-magnet-additions-preview.mjs"),
         "--front", trial.upstream, "--port", str(free_port()),
         "--dist", str(trial.root / "dist"),
         "--log", str(trial.root / "half-traffic.jsonl"),
         "--manifest", str(half / "manifest.json")],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=120,
        creationflags=no_window)
    assert done.returncode != 0
    assert "setup has not completed" in done.stderr, done.stderr


# -- B1: the verified INSTANCE, including a benign same-corpus copy ------------

@pytest.fixture(scope="module")
def copied_gate(trial):
    """Honest fixture responses, then route the next request to its SQLite copy.

    The manifest's locally pinned binding prevents mixing path reads from the
    intended Brain with an instance read from the copy. If replacement occurs
    AFTER all reads, the backend must still refuse the preserved binding.
    """
    import quiet_magnet_additions_fixture as fixture

    source, copy = trial.root / "primary", trial.root / "copy"
    shutil.copytree(source, copy, ignore=shutil.ignore_patterns("corpus.db*"))
    with sqlite3.connect(source.joinpath("corpus.db").as_uri() + "?mode=ro",
                         uri=True) as src:
        with sqlite3.connect(copy / "corpus.db") as dst:
            src.backup(dst)
    fixture._trust_local(copy)
    processes, logs = [], []
    relay = thread = None
    state = {"mode": "primary", "switch_after": None, "omit": None, "trace": []}

    def launch(command, name):
        log = open(trial.root / name, "ab")
        logs.append(log)
        child = subprocess.Popen(command, cwd=REPO, env=clean_env(), stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        processes.append(child)
        return child

    try:
        copy_port = free_port()
        child = launch([sys.executable, "-m", "mentis.web", str(copy),
                        "--port", str(copy_port), "--mars", "no-mars"], "copy-server.log")
        copy_base = f"http://127.0.0.1:{copy_port}"
        wait_for(copy_base + "/api/brain?identity=1", child,
                 headers={"X-Mentis-Client": "1"})
        brain = ask(copy_base + "/fluid/api/needs-you/brain",
                    headers={"X-Mentis-Client": "1"})[1]["brain"]
        assert brain["corpus_id"] == trial.primary["corpus_id"]
        copy_binding = f"{brain['corpus_id']}@{brain['instance']}"
        assert copy_binding != trial.binding
        assert trial.binding == f"{trial.primary['corpus_id']}@{trial.primary['instance']}"

        class Relay(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.forward()

            def do_POST(self):
                self.forward()

            def forward(self):
                port = copy_port if state["mode"] == "copy" else trial.server_port
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
                try:
                    data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                    headers = dict(self.headers)
                    headers["Host"] = f"127.0.0.1:{port}"
                    conn.request(self.command, self.path, body=data or None, headers=headers)
                    answer = conn.getresponse()
                    raw = answer.read()
                    # Uncertainty controls remove one field of a real response.
                    # Replacement cases below never alter any identity response.
                    if state["omit"] == self.path:
                        payload = json.loads(raw)
                        if self.path == "/api/brain?identity=1":
                            payload.pop("corpus_path", None)
                        elif self.path == "/api/server":
                            payload.pop("corpus", None)
                        else:
                            payload["brain"].pop("instance", None)
                        raw = json.dumps(payload).encode()
                    state["trace"].append({"method": self.command, "path": self.path,
                        "recipient": "copy" if port == copy_port else "primary",
                        "binding": self.headers.get("X-Mentis-Brain"), "status": answer.status})
                    if state["switch_after"] == self.path:
                        state["mode"] = "copy"
                    self.send_response(answer.status)
                    for name, value in answer.getheaders():
                        if name.lower() not in ("connection", "content-length", "transfer-encoding"):
                            self.send_header(name, value)
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                finally:
                    conn.close()

        relay = ThreadingHTTPServer(("127.0.0.1", free_port()), Relay)
        thread = threading.Thread(target=relay.serve_forever, daemon=True)
        thread.start()
        front = f"http://127.0.0.1:{relay.server_port}"
        port = free_port()
        command = ["node", str(TOOLS / "quiet-magnet-additions-preview.mjs"),
                   "--front", front, "--port", str(port),
                   "--dist", str(trial.root / "dist"),
                   "--log", str(trial.root / "copy-traffic.jsonl"),
                   "--manifest", str(trial.root / "manifest.json")]
        proxy = launch(command, "copy-proxy.log")
        base = f"http://127.0.0.1:{port}"
        wait_for(base + "/__q2/brain", proxy)

        def send(kind, binding):
            if kind == "post":
                path = "/fluid/api/posts"
                body = {"conversation": trial.C, "author": trial.by,
                        "text": "SYNTHETIC B1 COPY CONTROL", "op": "b1-copy-post"}
            else:
                path = f"/fluid/api/arrangements/{trial.A}/magnets"
                body = seed_body(trial.B)
                body["op"] = "b1-copy-magnet"
            return ask(base + path, method="POST", body=json.dumps(body).encode(),
                headers={"X-Mentis-Client": "1", "X-Mentis-Brain": binding,
                         "Origin": base, "Content-Type": "application/json"})

        yield {"state": state, "send": send, "base": base, "command": command,
               "copy_binding": copy_binding, "trial": trial,
               "records": lambda: {name: fixture.brain_state(trial.root / name)["record_sha256"]
                                   for name in ("primary", "copy")}}
    finally:
        for process in reversed(processes):
            stop(process)
        if relay:
            relay.shutdown()
            relay.server_close()
        if thread:
            thread.join(timeout=10)
            assert not thread.is_alive()
        for log in logs:
            log.close()
        (trial.root / "b1-replacement.json").write_text(json.dumps({
            "trace": state["trace"],
            "owned": [{"pid": p.pid, "returncode": p.poll()} for p in processes],
            "relay_stopped": thread is None or not thread.is_alive()}, indent=2), "utf-8")
        assert all(p.poll() is not None for p in processes)


@pytest.fixture
def gate(copied_gate):
    copied_gate["state"].update(mode="primary", switch_after=None, omit=None)
    copied_gate["state"]["trace"].clear()
    return copied_gate


@pytest.mark.parametrize("kind", ["post", "magnet"])
def test_b1_valid_instance_is_preserved_and_written(gate, kind):
    status, body = gate["send"](kind, gate["trial"].binding)
    assert status == 200, body
    sent = [row for row in gate["state"]["trace"] if row["method"] == "POST"]
    assert len(sent) == 1
    assert sent[0]["binding"] == gate["trial"].binding
    assert sent[0]["recipient"] == "primary"


@pytest.mark.parametrize("kind", ["post", "magnet"])
@pytest.mark.parametrize("who", ["copy", "stale"])
def test_b1_unverified_instance_is_refused_before_post(gate, kind, who):
    binding = (gate["copy_binding"] if who == "copy" else
               gate["trial"].primary["corpus_id"] + "@stale-instance")
    before = gate["records"]()
    status, body = gate["send"](kind, binding)
    assert status == 409, body
    assert gate["records"]() == before
    assert not any(row["method"] == "POST" for row in gate["state"]["trace"])


@pytest.mark.parametrize("kind", ["post", "magnet"])
@pytest.mark.parametrize("who", ["primary", "copy"])
@pytest.mark.parametrize("after", ["/api/brain?identity=1", "/api/server",
                                  "/fluid/api/needs-you/brain"])
def test_b1_copied_recipient_between_verification_and_write_is_refused(gate, kind, who, after):
    state = gate["state"]
    state["switch_after"] = after
    binding = gate["trial"].binding if who == "primary" else gate["copy_binding"]
    before = gate["records"]()
    status, body = gate["send"](kind, binding)
    assert status == (409 if after == "/fluid/api/needs-you/brain" else 503), body
    assert gate["records"]() == before
    sent = [row for row in state["trace"] if row["method"] == "POST"]
    if after == "/fluid/api/needs-you/brain" and who == "primary":
        # All verification completed honestly, then the backend rejected the
        # intended instance. The proxy never rewrote it to the copy's binding.
        assert len(sent) == 1
        expected_path = ("/fluid/api/posts" if kind == "post" else
                         f"/fluid/api/arrangements/{gate['trial'].A}/magnets")
        assert sent[0] == {"method": "POST", "path": expected_path,
            "recipient": "copy", "binding": binding, "status": 409}
        assert body["kind"] == "BrainChanged"
    else:
        assert sent == []


@pytest.mark.parametrize("kind", ["post", "magnet"])
def test_b1_stable_copy_is_refused(gate, kind):
    gate["state"]["mode"] = "copy"
    before = gate["records"]()
    assert gate["send"](kind, gate["copy_binding"])[0] == 503
    assert gate["records"]() == before


@pytest.mark.parametrize("omit", ["/api/brain?identity=1", "/api/server",
                                 "/fluid/api/needs-you/brain"])
def test_b1_uncertain_identity_refuses_capabilities_writes_and_startup(gate, omit):
    gate["state"]["omit"] = omit
    before = gate["records"]()
    assert ask(gate["base"] + "/__q2/magnet-capabilities")[0] == 503
    for kind in ("post", "magnet"):
        assert gate["send"](kind, gate["trial"].binding)[0] == 503
    done = subprocess.run(gate["command"], cwd=REPO, env=clean_env(),
        capture_output=True, text=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert done.returncode != 0
    assert "EADDRINUSE" not in done.stderr  # verification must fail BEFORE listening
    assert gate["records"]() == before
    assert not any(row["method"] == "POST" for row in gate["state"]["trace"])


@pytest.mark.parametrize("after", ["/api/brain?identity=1", "/api/server"])
def test_b1_split_identity_reads_refuse_capabilities_and_startup(gate, after):
    state = gate["state"]
    state["switch_after"] = after
    before = gate["records"]()
    assert ask(gate["base"] + "/__q2/magnet-capabilities")[0] == 503
    state["mode"] = "primary"
    done = subprocess.run(gate["command"], cwd=REPO, env=clean_env(),
        capture_output=True, text=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert done.returncode != 0
    assert "EADDRINUSE" not in done.stderr
    assert gate["records"]() == before
    assert not any(row["method"] == "POST" for row in state["trace"])
