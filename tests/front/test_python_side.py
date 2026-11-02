"""R1's Python changes, on real Python and BRAIN-SEED, with no front: `--answers-at`, the trusted
peer, `/private/live`, and the worker's transport wording.

P1.5's own tests, and not a frozen row. `docs/rust/contracts/launcher.md`, "R1's Python changes".
What matters as much is that each leaves Python alone as it was, so rows L and M stand beside these.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from mentis import worker
from tests.front import restart_messages
from tests.front.pair_harness import SPARE_PORTS

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
#: Beside the launcher's own, and moved with everything else by `MENTIS_R1_PORTS`.
PRIVATE, PUBLIC = SPARE_PORTS[3:5] if os.environ.get("MENTIS_R1_PORTS") else (8874, 8875)
SECRET = "the-secret-of-this-boot"
PEER = "X-Mentis-Peer"
BOOT_SECRET = "X-Mentis-Boot-Secret"


@contextlib.contextmanager
def python(brain: pathlib.Path, *extra: str, secret: str | None = None):
    run = brain.parent / f"{brain.name}.run"
    (run / "ws").mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("MENTIS")}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
               MENTIS_FLUID_DIST=str(REPO / "no-fluid-build-here"))
    if secret:
        env["MENTIS_BOOT_SECRET"] = secret
    with open(run / "server.log", "ab") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "mentis.web", str(brain), "--port", str(PRIVATE),
             "--workspace", str(run / "ws"), "--mars", "workload-no-mars-here", *extra],
            cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 120
        while True:
            assert proc.poll() is None, (run / "server.log").read_text(encoding="utf-8")
            try:
                if ask("/api/server")[0] == 200:
                    break
            except OSError:
                pass
            assert time.monotonic() < deadline
            time.sleep(0.1)
        yield proc
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.wait(timeout=30)


def ask(path: str, headers: dict | None = None, method: str = "GET",
        data: bytes | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(f"http://127.0.0.1:{PRIVATE}{path}", method=method,
                                 headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as fh:
            return fh.status, fh.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


CLIENT = {"X-Mentis-Client": "1"}


@pytest.fixture
def brain(brain_seed, tmp_path) -> pathlib.Path:
    copy = tmp_path / "brain"
    shutil.copytree(brain_seed, copy)
    return copy


def test_answers_at_is_told_and_python_alone_keeps_its_own_address(brain):
    with python(brain):
        server = json.loads(ask("/api/server")[1])
        assert server["process"]["port"] == PRIVATE
    with python(brain, "--answers-at", f"http://127.0.0.1:{PUBLIC}"):
        server = json.loads(ask("/api/server")[1])
        assert server["process"]["port"] == PUBLIC, "agents and bridges are told the public one"


def test_python_alone_answers_private_paths_as_it_always_did(brain):
    with python(brain):
        for path in ("/private/live", "/private/stop", "/private/anything"):
            status, body = ask(path)
            assert status == 404 and b"Fluid is not built" in body, "as `_static` with no build"
        assert ask("/private/live", {BOOT_SECRET: "anything"})[0] == 404
        status, body = ask("/private/live", {**CLIENT, "Content-Type": "application/json"}, "POST")
        assert status == 404, body


def test_the_snapshot_needs_the_secret_and_nothing_else_is_private(brain):
    with python(brain, secret=SECRET):
        refused, body = ask("/private/live")
        assert refused == 403
        assert json.loads(body)["kind"] == "PermissionError"
        assert ask("/private/live", {BOOT_SECRET: "wrong"})[0] == 403
        assert ask("/private/live", {BOOT_SECRET: "é"})[0] == 403, "a non-ASCII guess is refused"
        for path in ("/private/stop", "/private/live/", "/private/x"):
            status, body = ask(path, {BOOT_SECRET: SECRET})
            assert status == 404 and json.loads(body) == {"error": "no such semantic surface"}
        assert ask("/private/live", {BOOT_SECRET: SECRET, **CLIENT}, "POST")[0] == 404


def raw_status(target: str, *headers: str) -> int:
    """`target` exactly as sent, which urllib wouldn't do."""
    with socket.create_connection(("127.0.0.1", PRIVATE), timeout=20) as conn:
        lines = [f"GET {target} HTTP/1.1", "Host: 127.0.0.1", "Connection: close", *headers]
        conn.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
        return int(conn.makefile("rb").readline().split()[1])


@pytest.mark.parametrize("target", ["//private/live", "///private/live", "http://host/private/live",
                                    "/private/live?x=1", "/private/live;x"])
def test_the_guard_reads_the_path_python_will_act_on(brain, target):
    """The front keeps these from the public port, and this holds on the private port by itself."""
    with python(brain, secret=SECRET):
        assert raw_status(target) == 403
        assert raw_status(target, f"{BOOT_SECRET}: {SECRET}") == 200


def test_the_snapshot_is_the_envelope_and_says_the_pulses_live_half(brain):
    with python(brain, secret=SECRET):
        status, body = ask("/private/live", {BOOT_SECRET: SECRET})
        assert status == 200
        one = json.loads(body)
        assert set(one) == {"schema", "boot_id", "generation", "live_hash", "taken_at", "fields"}
        assert one["schema"] == 1 and isinstance(one["generation"], int)
        assert isinstance(one["boot_id"], str) and one["boot_id"]
        assert one["fields"] == {"live_now": [], "run_marks": []}
        token = json.loads(ask("/api/pulse", CLIENT)[1])["token"]
        assert token.split("/")[1] == one["live_hash"]
        two = json.loads(ask("/private/live", {BOOT_SECRET: SECRET})[1])
        assert two["generation"] == one["generation"], "nothing live moved, so nothing moved it"
        assert two["boot_id"] == one["boot_id"]
    with python(brain, secret=SECRET):
        third = json.loads(ask("/private/live", {BOOT_SECRET: SECRET})[1])
        assert third["boot_id"] != one["boot_id"]


def test_the_generation_rises_when_live_state_moves_and_only_then():
    from mentis.web import _live_hash, _LiveSnapshots

    class Agents:
        live, marks = [], []

        def live_now(self):
            return list(self.live)

        def run_marks(self):
            return list(self.marks)

    agents, taken = Agents(), _LiveSnapshots()
    first = taken.take(agents)["generation"]
    assert taken.take(agents)["generation"] == first
    agents.live = [("inst-1", "live")]
    second = taken.take(agents)
    assert second["generation"] == first + 1
    assert second["live_hash"] == _live_hash(([("inst-1", "live")], []))
    assert taken.take(agents)["generation"] == first + 1
    agents.marks = [("opr-1", 1.5, None, None, False, 2, "Run npm test")]
    moved = taken.take(agents)
    assert moved["generation"] == first + 2
    assert json.loads(json.dumps(moved))["fields"]["run_marks"] == [
        ["opr-1", 1.5, None, None, False, 2, "Run npm test"]]


def picker_says(headers: dict) -> dict:
    return json.loads(ask("/api/sources", {**CLIENT, **headers})[1])["picker"]


def test_the_peer_is_believed_only_with_the_secret(brain):
    loopback_said = "The Windows picker is available only to a loopback peer."
    with python(brain, secret=SECRET):
        told = picker_says({PEER: "100.64.0.9", BOOT_SECRET: SECRET})
        assert told["why_not"] == loopback_said, "the front said who it was, and is believed"
        for headers in ({PEER: "100.64.0.9"}, {PEER: "100.64.0.9", BOOT_SECRET: "wrong"}):
            assert picker_says(headers)["why_not"] != loopback_said, "the socket peer is used"
        assert picker_says({PEER: "127.0.0.1", BOOT_SECRET: SECRET})["why_not"] != loopback_said


def test_holding_the_secret_gets_a_process_on_this_machine_nothing_its_socket_doesnt_have(brain):
    """Why a same-user process is outside what the secret defends (`contracts/launcher.md`, "The
    secret"): the peer reaches only the picker's loopback check, which its socket already passes,
    and the grant check doesn't look at either header."""
    with python(brain, secret=SECRET):
        forged = {PEER: "127.0.0.1", BOOT_SECRET: SECRET}
        assert picker_says(forged) == picker_says({})
        call = json.dumps({"corpus": str(brain), "op": "orient", "args": {}}).encode()
        json_call = {"Content-Type": "application/json"}
        plain = ask("/api/worker", json_call, "POST", call)
        with_secret = ask("/api/worker", {**json_call, **forged}, "POST", call)
        assert plain[0] == 403, plain
        assert with_secret == plain


def test_python_alone_ignores_the_peer_header(brain):
    with python(brain):
        for headers in ({PEER: "100.64.0.9"}, {PEER: "100.64.0.9", BOOT_SECRET: SECRET},
                        {PEER: "100.64.0.9", BOOT_SECRET: ""}):
            assert picker_says(headers)["why_not"] != (
                "The Windows picker is available only to a loopback peer.")


def test_the_secret_leaves_the_environment_so_nothing_python_starts_holds_it(monkeypatch):
    import mentis.spine.migrations as migrations
    import mentis.web as web

    class Stop(Exception):
        pass

    def refuse(path):
        raise Stop

    monkeypatch.setenv("MENTIS_BOOT_SECRET", SECRET)
    monkeypatch.setattr(migrations, "require_brain", refuse)
    monkeypatch.setattr(web._Handler, "boot_secret", None)
    with pytest.raises(Stop):
        web.serve("nowhere")
    assert "MENTIS_BOOT_SECRET" not in os.environ
    assert web._Handler.boot_secret == SECRET


# -- the worker's transport, against stand-ins --------------------------------

JSON_HEAD = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 15\r\n\r\n"
REFUSED_HEAD = (b"HTTP/1.1 403 Forbidden\r\nContent-Type: application/json\r\n"
                b"Content-Length: 15\r\n\r\n")


def read_request(conn: socket.socket) -> None:
    data = b""
    while b"\r\n\r\n" not in data:
        data += conn.recv(65536)
    head, _, body = data.partition(b"\r\n\r\n")
    length = next(int(line.split(b":")[1]) for line in head.split(b"\r\n")
                  if line.lower().startswith(b"content-length:"))
    while len(body) < length:
        body += conn.recv(65536)


def reset(conn: socket.socket) -> None:
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("hh", 1, 0))
    conn.close()


def told(stand_in, args=None) -> tuple[str, str]:
    listener = socket.create_server(("127.0.0.1", 0))
    via = f"http://127.0.0.1:{listener.getsockname()[1]}"

    def serve():
        conn, _ = listener.accept()
        try:
            stand_in(conn)
        except OSError:
            pass
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        with pytest.raises(Exception) as caught:  # noqa: PT011  which it is, is what's asserted
            worker._over(via, "C:\\b\\brain", "answer", args or {}, "grant")
        return caught.type.__name__, f"{caught.type.__name__}: {caught.value}"
    finally:
        thread.join(timeout=10)
        listener.close()


def answering(data: bytes, end):
    def stand_in(conn):
        read_request(conn)
        conn.sendall(data)
        end(conn)
    return stand_in


def nothing_then(end):
    def stand_in(conn):
        read_request(conn)
        end(conn)
    return stand_in


@pytest.mark.parametrize("stand_in, entry", [
    (nothing_then(reset), "B-sent"),
    (nothing_then(socket.socket.close), "B-sent"),
    (answering(JSON_HEAD + b'{"a":', socket.socket.close), "B-reply"),
    (answering(JSON_HEAD + b'{"a":', reset), "B-reply"),
    (answering(REFUSED_HEAD + b'{"a":', socket.socket.close), "B-reply"),
    (answering(REFUSED_HEAD + b'{"a":', reset), "B-reply"),
], ids=["reset-after-sending", "closed-after-sending", "body-cut-by-close", "body-cut-by-reset",
        "refusal-body-cut-by-close", "refusal-body-cut-by-reset"])
def test_a_call_that_was_sent_is_told_the_result_is_unknown(stand_in, entry):
    kind, message = told(stand_in)
    assert kind == "OwnerError"
    assert entry in restart_messages.decide(message), message
    assert "nothing else to try" not in message and "IncompleteRead" not in message


def test_a_refused_connection_is_still_nobody_there():
    with socket.create_server(("127.0.0.1", 0)) as held:
        port = held.getsockname()[1]
    with pytest.raises(worker.NoOwner) as caught:
        worker._over(f"http://127.0.0.1:{port}", "C:\\b\\brain", "answer", {}, "grant")
    assert "A" in restart_messages.decide(f"NoOwner: {caught.value}")


def test_a_reset_while_sending_is_still_nobody_there():
    def while_sending(conn):
        conn.recv(1024)
        reset(conn)
    kind, message = told(while_sending, {"text": "x" * (64 << 20)})
    assert kind == "NoOwner"
    assert "B-sending" in restart_messages.decide(message), message


def test_a_whole_answer_and_a_whole_refusal_are_as_they_were():
    def replying(data):
        return answering(data, socket.socket.close)
    kind, message = told(replying(REFUSED_HEAD + b'{"error": "no"}'))
    assert (kind, message) == ("NotPermitted", "NotPermitted: no")
    listener = socket.create_server(("127.0.0.1", 0))
    thread = threading.Thread(target=lambda: replying(JSON_HEAD + b'{"answer": 42 }')(
        listener.accept()[0]), daemon=True)
    thread.start()
    via = f"http://127.0.0.1:{listener.getsockname()[1]}"
    assert worker._over(via, "x", "answer", {}, "g") == {"answer": 42}
    thread.join(timeout=10)
    listener.close()
