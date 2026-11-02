"""Row A: the front against PY-ALONE, on one BRAIN-SEED each. `R1-acceptance.md`, "A".

Each case compares status, the headers named and the body with Python's own answer, except where
it is about the front alone. A difference fails: the listed behaviour differences are the only
ones there may be.

58 once P1.3's Pulse, Topics and Names are appended here. Host 10, Client header 4, Grant 2,
Framing 8, Streaming 4, Forwarded answers 3, Peer 4, Static 5.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time

import pytest

from tests.front import request_forms
from tests.front.pair import (CLIENT, PORT, PY_PORT, SPARE_PORTS, Answer, Pair, advance, ask,
                              conversation_named, exchange, memory, non_loopback_address, post_json,
                              request, rows)
from tools.r1 import common, py_alone

ALLOWED_ENTRY = "listed.example"
#: A second PY-ALONE, for the one case its environment has to differ in.
PY_ALLOWED_PORT = SPARE_PORTS[0]
#: The pair of servers of the one case with no build, and the second front of the Peer cases.
PY_UNBUILT_PORT, PAIR_UNBUILT_PORT, SECOND_FRONT_PORT = SPARE_PORTS[1:4]
PY_NOW_PORT = SPARE_PORTS[4]

MB = 1024 * 1024
UPLOAD = {"X-Mentis-Upload": "1"}


def seed_copy(brain_seed, parent, name: str):
    copy = parent / name / "brain"
    copy.parent.mkdir()
    shutil.copytree(brain_seed, copy)
    return copy


@pytest.fixture(scope="module")
def py(brain_seed, tmp_path_factory):
    """PY-ALONE, the other side. Its copy is at `py.brain`."""
    copy = seed_copy(brain_seed, tmp_path_factory.mktemp("py"), "alone")
    with py_alone.running(copy, port=PY_PORT):
        yield _Side(PY_PORT, copy)


@pytest.fixture(scope="module")
def pair(brain_seed, tmp_path_factory):
    copy = seed_copy(brain_seed, tmp_path_factory.mktemp("pair"), "under-test")
    with Pair(copy, env={"MENTIS_ALLOWED_HOSTS": ALLOWED_ENTRY}) as running:
        yield running


class _Side:
    def __init__(self, port, brain):
        self.port, self.brain = port, brain


@pytest.fixture(scope="module")
def python_now(brain_seed, tmp_path_factory):
    """THIS COMMIT'S Python alone, and not PY-ALONE, for the only cases where the two differ by the
    owner's decision (`opr-f2ea91ab6992`): `R1-acceptance.md`, "A", says which and why."""
    copy = seed_copy(brain_seed, tmp_path_factory.mktemp("python-now"), "alone")
    with py_alone.running(copy, port=PY_NOW_PORT, code=common.REPO):
        yield _Side(PY_NOW_PORT, copy)


def both(py, pair, data: bytes, *, wait: float = 3.0) -> tuple[Answer, Answer]:
    """The same bytes to each side, raw. Python's answer, then the front's."""
    return (Answer(exchange(py.port, data, wait=wait)),
            Answer(exchange(pair.port, data, wait=wait)))


def assert_same(py, pair, data: bytes, *, wait: float = 3.0) -> Answer:
    """Byte for byte, but for `Date`: every header in its order, repeats included."""
    theirs, ours = both(py, pair, data, wait=wait)
    assert ours.comparable == theirs.comparable
    return ours


# -- Host, 10: on `/`, which the front owns --------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1:8852", "localhost", "x.localhost", "x.ts.net",
                                  "[::1]:8852"])
def test_host_allowed(py, pair, host):
    assert assert_same(py, pair, request("GET", "/", host=host)).status == 200


def test_host_allowed_by_mentis_allowed_hosts(pair, tmp_path, brain_seed):
    copy = seed_copy(brain_seed, tmp_path, "listed")
    env = {**py_alone.environment(), "MENTIS_ALLOWED_HOSTS": ALLOWED_ENTRY}
    run_dir = copy.parent / "run"
    (run_dir / "ws").mkdir(parents=True)
    with open(run_dir / "server.log", "ab") as log:
        proc = subprocess.Popen(py_alone.command(copy, PY_ALLOWED_PORT, run_dir / "ws"),
                                cwd=common.code_dir(), env=env, stdout=log,
                                stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + py_alone.START_LIMIT_S
        while True:
            try:
                if py_alone.get(PY_ALLOWED_PORT, "/api/server", 2.0)[0] == 200:
                    break
            except OSError:
                pass
            assert proc.poll() is None and time.monotonic() < deadline, "that PY-ALONE didn't start"
            time.sleep(0.1)
        data = request("GET", "/", host=ALLOWED_ENTRY)
        theirs = Answer(exchange(PY_ALLOWED_PORT, data))
        ours = Answer(exchange(pair.port, data))
        assert theirs.status == 200
        assert ours.comparable == theirs.comparable
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       check=False)
        proc.wait(timeout=30)


@pytest.mark.parametrize("host", ["evil.example", "a.ts.net.evil.example", "localhost:1:2", None])
def test_host_refused(py, pair, host):
    ours = assert_same(py, pair, request("GET", "/", host=host, close=False))
    assert ours.status == 421
    assert ours.header("Connection") == "close"
    assert ours.json["kind"] == "PermissionError"


# -- Client header, 4 ------------------------------------------------------------------------------


def test_client_header_missing_on_get(py, pair):
    ours = assert_same(py, pair, request("GET", "/api/pulse", close=False))
    assert ours.status == 403
    assert ours.json == {"error": "missing X-Mentis-Client", "kind": "PermissionError"}


def test_client_header_missing_on_post(py, pair):
    doc = json.dumps({}).encode()
    ours = assert_same(py, pair, request("POST", "/api/conversations", body=doc, close=False,
                                         headers={"Content-Type": "application/json"}))
    assert ours.status == 403
    assert ours.json == {"error": "missing X-Mentis-Client", "kind": "PermissionError"}


def test_api_server_is_exempt_from_the_client_header(py, pair):
    theirs, ours = both(py, pair, request("GET", "/api/server"))
    assert ours.status == theirs.status == 200
    assert [h[0] for h in ours.headers] == [h[0] for h in theirs.headers]
    # It says where it is and which process it is, so those are the two sides' own.
    assert set(ours.json) == set(theirs.json)
    assert ours.json["process"]["port"] == PORT, "it reports the public address"


def test_a_preflight_grants_nothing(py, pair):
    ours = assert_same(py, pair, request("OPTIONS", "/api/pulse", close=False,
                                         headers={"Origin": "https://evil.example",
                                                  "Access-Control-Request-Method": "GET",
                                                  "Access-Control-Request-Headers":
                                                      "X-Mentis-Client"}))
    assert ours.status == 204
    assert ours.header("Access-Control-Allow-Origin") is None
    assert ours.header("Access-Control-Allow-Headers") is None


# -- Grant, 2 --------------------------------------------------------------------------------------


def test_a_grant_on_another_route_gets_that_door_s_own_words(py, pair):
    for path, words in [
            ("/api/pulse", "a worker grant authorises the four reads at /api/worker and nothing else"),
            ("/api/conversations", "a worker grant authorises the four reads at /api/worker and nothing else"),
            ("/fluid/api/topics", "a worker grant authorises /api/worker and nothing else"),
            ("/fluid/api/names", "a worker grant authorises /api/worker and nothing else")]:
        ours = assert_same(py, pair, request("GET", path, headers={"X-Mentis-Worker": "any"},
                                             close=False))
        assert ours.status == 403, path
        assert ours.json == {"error": words, "kind": "PermissionError", "asked_for": path}, path


def test_a_grant_on_the_worker_door_is_forwarded_and_its_403_relayed_as_sent(pair):
    doc = {"corpus": str(pair.brain), "op": "orient", "args": {}}
    data = request("POST", "/api/worker", body=json.dumps(doc).encode(), close=False,
                   headers={"Content-Type": "application/json", "X-Mentis-Worker": "no-such-grant"})
    ours = Answer(exchange(pair.port, data))
    # As this pair's Python answers it itself, the paths in its words being this copy's.
    assert ours.comparable == Answer(exchange(pair.private_port, data)).comparable
    assert ours.status == 403
    assert ours.json["kind"] == "PermissionError"


# -- Framing, 8 ------------------------------------------------------------------------------------


GOOD_BODY = b"{}"
POST_HEAD = "POST /api/conversations HTTP/1.1\r\nHost: localhost\r\nX-Mentis-Client: 1\r\nContent-Type: application/json\r\n"


def test_transfer_encoding_chunked_is_refused(py, pair):
    ours = assert_same(py, pair, (POST_HEAD + "Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n").encode())
    assert ours.status == 501


def test_transfer_encoding_with_a_space_before_the_colon_is_python_s_400(py, pair):
    ours = assert_same(py, pair, (POST_HEAD + "Transfer-Encoding : chunked\r\n\r\n0\r\n\r\n").encode())
    assert ours.status_line == "HTTP/1.1 400 a header line is not `Name: value`"
    assert [h for h in ours.headers if h[0] == "Connection"] == [("Connection", "close")] * 2


def test_a_duplicate_content_length_is_refused(py, pair):
    ours = assert_same(py, pair, (POST_HEAD + "Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}").encode())
    assert ours.status_line == "HTTP/1.1 400 more than one Content-Length"


def test_a_conflicting_content_length_is_refused(py, pair):
    ours = assert_same(py, pair, (POST_HEAD + "Content-Length: 2\r\nContent-Length: 3\r\n\r\n{}").encode())
    assert ours.status_line == "HTTP/1.1 400 more than one Content-Length"


def test_a_non_digit_content_length_is_refused(py, pair):
    ours = assert_same(py, pair, (POST_HEAD + "Content-Length: +2\r\n\r\n{}").encode())
    assert ours.status_line == "HTTP/1.1 400 Content-Length must be digits only"


def test_a_get_with_a_body_closes_as_python_does(py, pair):
    # `/api/pulse`'s token isn't what is being compared here, so a route with a settled answer.
    ours = assert_same(py, pair, b"GET /api/no-such-route HTTP/1.1\r\nHost: localhost\r\n"
                                 b"X-Mentis-Client: 1\r\nContent-Length: 2\r\n\r\n{}")
    assert ours.status == 404
    assert ours.header("Connection") == "close"


def test_a_request_pipelined_after_a_refused_one_never_reaches_python(py, pair):
    second = json.dumps({"name": "smuggled"}).encode()
    pipelined = (
        (POST_HEAD + "Content-Length: +2\r\n\r\n{}").encode()
        + (POST_HEAD + f"Content-Length: {len(second)}\r\n\r\n").encode() + second)
    before = advance(pair.brain)
    ours = assert_same(py, pair, pipelined)
    assert ours.status == 400
    assert ours.body.count(b"HTTP/1.1") == 0, "one answer only"
    time.sleep(0.5)
    assert advance(pair.brain) == before
    assert not pair_holds(pair, "smuggled")


def pair_holds(pair, name: str) -> bool:
    return bool(rows(pair.brain, "SELECT 1 FROM entry WHERE def_name='conversation' "
                                 "AND json_extract(body,'$.name')=?", name))


def test_head_is_python_s_501_with_a_length_and_no_body(py, pair):
    ours = assert_same(py, pair, b"HEAD /api/server HTTP/1.1\r\nHost: localhost\r\n\r\n")
    assert ours.status_line == "HTTP/1.1 501 Unsupported method ('HEAD')"
    assert ours.header("Content-Length") == "357"
    assert ours.body == b""


# -- Parser, 62: where the front and Python could read one request two ways. R1-acceptance.md, A ----
#
# `tests/front/request_forms.py` says what each is, by Python's own parse. A private form must get
# the front's words: this pair's Python holds the secret and would answer `/private/live` with a
# snapshot, so a front that forwarded the proof shows up here as `boot_id`.


def assert_the_front_s_own_404(raw: bytes, data: bytes) -> None:
    assert b"boot_id" not in raw, f"Python was reached with the proof: {data!r}"
    got = Answer(raw)
    assert got.status_line == "HTTP/1.1 404 Not Found", got
    assert got.json == {"error": "no such semantic surface"}, got


@pytest.mark.parametrize("target", request_forms.PRIVATE_TARGETS, ids=ascii)
def test_a_target_python_reads_as_private_is_the_front_s(pair, target):
    data = request("GET", target)
    assert_the_front_s_own_404(exchange(pair.port, data), data)


@pytest.mark.parametrize("target", request_forms.ELSEWHERE_TARGETS, ids=ascii)
def test_a_target_python_reads_elsewhere_is_python_s(py, pair, target):
    assert_same(py, pair, request("GET", target))


@pytest.mark.parametrize("target", request_forms.RAISING_TARGETS, ids=ascii)
def test_a_target_python_cannot_parse_is_python_s_500(python_now, pair, target):
    assert assert_same(python_now, pair, request("GET", target)).status == 500


@pytest.mark.parametrize("target", request_forms.BARE_PRIVATE_TARGETS)
def test_http_0_9_under_private_is_the_front_s_body_alone(pair, target):
    got = exchange(pair.port, f"GET {target}\r\nHost: localhost\r\n\r\n".encode())
    assert got == b'{"error": "no such semantic surface"}'


@pytest.mark.parametrize("target", request_forms.BARE_ELSEWHERE_TARGETS)
def test_http_0_9_elsewhere_is_python_s(py, pair, target):
    assert_same(py, pair, f"GET {target}\r\nHost: localhost\r\n\r\n".encode())


def test_http_0_9_under_private_with_a_bad_header_is_python_s_refusal(py, pair):
    assert_same(py, pair, b"GET /private/live\r\nno colon here\r\n\r\n")


@pytest.mark.parametrize("line", request_forms.ODD_LINES)
def test_an_odd_line_with_private_in_it_is_python_s_refusal(py, pair, line):
    # A bad version leaves Python on HTTP/0.9 for its answer, so some of these are a page alone.
    assert b"Error response" in assert_same(py, pair, f"{line}\r\nHost: localhost\r\n\r\n".encode()).raw


@pytest.mark.parametrize("length", request_forms.ENORMOUS_LENGTHS)
def test_an_enormous_content_length_is_python_s_500(python_now, pair, length):
    data = (POST_HEAD + f"Content-Length: {length}\r\n\r\n").encode()
    assert assert_same(python_now, pair, data).status == 500


# -- Streaming, 4 ----------------------------------------------------------------------------------


def stage(port: int, data: bytes) -> dict:
    got = ask(port, "POST", "/api/artifacts", body=data,
              headers={**UPLOAD, "Content-Type": "application/octet-stream"})
    assert got.status == 200, got
    return got.json


def post_with_files(side, conversation: str, author: str, *files: bytes) -> str:
    """A post naming files staged first, as the composer does. Its id."""
    parts = [{"type": "text", "text": "with files"}]
    for number, data in enumerate(files):
        parts.append({"type": "file", "ref": stage(side.port, data)["staged"],
                      "alt": f"file-{number}.bin", "media_type": "application/octet-stream"})
    made = post_json(side.port, "/fluid/api/posts",
                     {"conversation": conversation, "author": author, "parts": parts}, CLIENT)
    assert made.status == 200, made
    return made.json["post"]


def admissions_of(side, post: str) -> list[str]:
    """The files of a post, by the id they were admitted under."""
    body = rows(side.brain, "SELECT body FROM entry WHERE id = ?", post)[0][0]
    return re.findall(r"adm-[0-9a-f]{12}", str(body))


def test_an_export_streams_and_its_body_is_whole(py, pair):
    conversation = conversation_named(pair.brain, "R1 known conversation")
    export = f"/api/conversations/{conversation}/export"

    # On the seed as it stands, the whole body, against Python's own for the same record. An
    # archive's bytes are its files': both sides were built byte for byte the same.
    theirs, ours = both(py, pair, request("GET", export), wait=30.0)
    assert ours.status == theirs.status == 200
    assert ours.header("Content-Type") == "application/zip"
    assert ours.header("Content-Disposition") == theirs.header("Content-Disposition")
    assert (hashlib.sha256(ours.body).hexdigest()
            == hashlib.sha256(direct_export(pair, export)).hexdigest())

    # Made big enough to outrun the sockets, and with Python held mid-write: the first bytes are
    # already here though the rest can't have been written. A front that held the body would have
    # sent nothing.
    post_with_files(pair, conversation, first_participant(pair),
                    *(os.urandom(20 * MB) for _ in range(3)))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # As little as the system allows, so the bytes wait in Python rather than in this socket.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        sock.settimeout(60)
        sock.connect(("127.0.0.1", pair.port))
        sock.sendall(request("GET", export))
        got = sock.recv(1 << 16)
        while b"\r\n\r\n" not in got:
            got += sock.recv(1 << 16)
        head, _, first = got.partition(b"\r\n\r\n")
        total = Answer(head + b"\r\n\r\n").header("Content-Length")
        assert total is not None and int(total) > 40 * MB
        pair.suspend_python()
        try:
            # Whatever was on its way arrives, and then nothing: the rest isn't written.
            sock.settimeout(1.0)
            received = len(first)
            try:
                while True:
                    more = sock.recv(1 << 20)
                    assert more, "it ended while Python was suspended"
                    received += len(more)
            except TimeoutError:
                pass
            assert 0 < received < int(total), "the body was held, not streamed"
        finally:
            pair.resume_python()
        sock.settimeout(60)
        while received < int(total):
            more = sock.recv(1 << 20)
            assert more
            received += len(more)
        assert received == int(total)


def direct_export(pair, path: str) -> bytes:
    """The same request straight to the pair's Python, on the same record."""
    return Answer(exchange(pair.private_port, request("GET", path), wait=30.0)).body


def first_participant(pair) -> str:
    return rows(pair.brain, "SELECT id FROM entry WHERE def_name='participant' "
                            "AND json_extract(body,'$.alias')='@r1-owner'")[0][0]


def test_a_client_disconnecting_mid_body_leaves_no_error_row_and_no_stuck_worker(pair):
    before = advance(pair.brain)
    with socket.create_connection(("127.0.0.1", pair.port)) as sock:
        sock.sendall(request("POST", "/api/artifacts", close=False,
                             headers={**UPLOAD, "Content-Type": "application/octet-stream",
                                      "Content-Length": str(4 * MB)}) + b"x" * 65536)
        time.sleep(0.2)
    time.sleep(0.5)
    assert advance(pair.brain) == before, "a dropped upload wrote nothing"
    started = time.monotonic()
    assert ask(pair.port, "GET", "/api/server", wait=10.0).status == 200
    assert time.monotonic() - started < 5, "the server is still free"


def test_an_artifact_s_bytes_come_with_their_security_headers(py, pair):
    data = b"\x89PNG\r\n\x1a\n not really a picture"
    conversation = conversation_named(pair.brain, "R1 known conversation")
    author = first_participant(pair)
    admission = {side.port: admissions_of(side, post_with_files(side, conversation, author, data))[0]
                 for side in (py, pair)}

    theirs = ask(py.port, "GET", f"/api/artifacts/{admission[py.port]}")
    ours = ask(pair.port, "GET", f"/api/artifacts/{admission[pair.port]}")
    assert ours.status == theirs.status == 200
    assert ours.body == theirs.body == data
    for name in ("Content-Type", "Content-Length", "X-Content-Type-Options",
                 "Content-Security-Policy", "Cross-Origin-Resource-Policy", "Referrer-Policy",
                 "Cache-Control"):
        assert ours.header(name) == theirs.header(name), name
        assert ours.header(name) is not None, name


def test_a_200_mb_body_is_not_held_in_memory(pair):
    """Correctness, not a mark: within 32 MB of idle, while all of it passes through to Python."""
    idle = memory(pair.front_pid)[0]
    size = 200 * MB
    answer: list[Answer] = []
    done = threading.Event()

    def send():
        chunk = b"z" * MB
        with socket.create_connection(("127.0.0.1", pair.port)) as sock:
            sock.settimeout(120)
            sock.sendall(request("POST", "/api/exchange/import/no-such-path", close=False,
                                 headers={**UPLOAD, "Content-Length": str(size)}))
            for _ in range(200):
                sock.sendall(chunk)
            got = b""
            while True:
                more = sock.recv(1 << 16)
                if not more or b"\r\n\r\n" in got:
                    got += more
                    break
                got += more
            answer.append(Answer(got))
        done.set()

    sender = threading.Thread(target=send, daemon=True)
    sender.start()
    highest = idle
    while not done.wait(0.02):
        highest = max(highest, memory(pair.front_pid)[0])
        assert sender.is_alive() or done.is_set(), "the sender died"
    sender.join(timeout=5)
    assert answer and answer[0].status == 404, f"Python read it all and answered: {answer}"
    assert answer[0].json == {"error": "unknown import path: /api/exchange/import/no-such-path"}
    assert highest - idle <= 32 * MB, f"{(highest - idle) / MB:.1f} MB over idle"
    # The system's own count catches a peak between samples.
    assert memory(pair.front_pid)[1] - idle <= 32 * MB


# -- Forwarded answers, 3 --------------------------------------------------------------------------


def test_a_json_404_from_python_is_passed_on_whole(py, pair):
    ours = assert_same(py, pair, request("GET", "/api/no-such-route", headers=CLIENT, close=False))
    assert ours.status == 404
    assert ours.json == {"error": "no such semantic surface"}


def test_a_500_from_python_is_passed_through_as_python_sent_it(py, pair):
    """R1 changes no Python for this row's sake, so this is a real 500 of Python's rather than a
    hook's: the one route whose failing code is a test's to arrange is an artifact whose bytes
    have gone (`_artifact`, "held-but-missing"). The bytes are taken from each side's copy."""
    conversation = conversation_named(pair.brain, "R1 known conversation")
    data = os.urandom(64)
    answers = {}
    for side in (py, pair):
        admission = admissions_of(side, post_with_files(
            side, conversation, first_participant(pair), data))[0]
        digest = hashlib.sha256(data).hexdigest()
        blob = side.brain / "artifacts" / "sha256" / digest[:2] / digest
        assert blob.is_file(), "the artifact's bytes weren't where its digest says"
        blob.unlink()
        answers[side.port] = ask(side.port, "GET", f"/api/artifacts/{admission}")
    theirs, ours = answers[py.port], answers[pair.port]
    assert theirs.status == 500, theirs
    # The two Admissions were made separately, so each has its own id, of the same length.
    same = re.compile(rb"adm-[0-9a-f]{12}")
    assert same.sub(b"adm", ours.body) == same.sub(b"adm", theirs.body)
    assert ours.status_line == theirs.status_line
    assert [h for h in ours.headers if h[0] != "Date"] == [h for h in theirs.headers if h[0] != "Date"]


def test_response_headers_repeats_included_come_in_python_s_order(py, pair):
    # `send_error` sends `Connection` twice, and the artifact door's headers are its own order.
    twice = assert_same(py, pair, b"PUT /x HTTP/1.1\r\nHost: localhost\r\n\r\n")
    assert [h[0] for h in twice.headers if h[0] != "Date"] == [
        "Server", "Connection", "Connection", "Content-Type", "Content-Length"]
    ordered = assert_same(py, pair, request("GET", "/api/artifacts/adm-000000000000", close=False))
    assert {h[0] for h in ordered.headers} >= {
        "X-Content-Type-Options", "Content-Security-Policy", "Cross-Origin-Resource-Policy",
        "Referrer-Policy"}


# -- Peer, 4 ---------------------------------------------------------------------------------------

PICKER_PEER_WORDS = "The Windows picker is available only to a loopback peer."


def picker(port: int, *, host: str = "127.0.0.1", headers: dict | None = None) -> dict:
    data = request("GET", "/api/sources", headers={**CLIENT, **(headers or {})})
    got = Answer(exchange(port, data, wait=30.0, host=host))
    assert got.status == 200, got
    return got.json["picker"]


def test_a_non_loopback_peer_is_refused_the_picker_in_python_s_words(pair):
    """PY-ALONE on loopback can't be reached from anywhere but loopback, and off loopback its first
    refusal is a different one, so Python's words are read from PY-ALONE's own source."""
    source = (common.code_dir() / "mentis" / "sources" / "picker.py").read_text(encoding="utf-8")
    assert PICKER_PEER_WORDS in source
    remote = non_loopback_address()
    with pair.second_front(remote, SECOND_FRONT_PORT):
        ours = picker(SECOND_FRONT_PORT, host=remote)
    assert ours == {"available": False, "why_not": PICKER_PEER_WORDS}


def test_a_loopback_peer_is_not_refused_as_a_peer(py, pair):
    theirs = picker(py.port)
    ours = picker(pair.port)
    assert ours == theirs
    assert ours["why_not"] != PICKER_PEER_WORDS


def test_an_inbound_peer_header_is_stripped_whichever_way_it_lies(py, pair):
    # Claiming to be remote from loopback doesn't lose the picker...
    theirs = picker(py.port)
    ours = picker(pair.port, headers={"X-Mentis-Peer": "100.64.0.1",
                                      "X-Mentis-Boot-Secret": "guess"})
    assert ours == theirs
    assert ours["why_not"] != PICKER_PEER_WORDS
    # ...and claiming to be loopback from elsewhere doesn't gain it, even with the real secret.
    remote = non_loopback_address()
    with pair.second_front(remote, SECOND_FRONT_PORT):
        ours = picker(SECOND_FRONT_PORT, host=remote,
                      headers={"X-Mentis-Peer": "127.0.0.1", "X-Mentis-Boot-Secret": pair.secret})
    assert ours == {"available": False, "why_not": PICKER_PEER_WORDS}


def test_the_peer_header_without_the_secret_is_ignored_on_the_private_port(pair):
    forged = picker(pair.private_port, headers={"X-Mentis-Peer": "100.64.0.1"})
    assert forged["why_not"] != PICKER_PEER_WORDS, "the socket's peer was used"
    wrong = picker(pair.private_port, headers={"X-Mentis-Peer": "100.64.0.1",
                                               "X-Mentis-Boot-Secret": "wrong"})
    assert wrong["why_not"] != PICKER_PEER_WORDS
    # And the secret is what makes it believed, so that wasn't for lack of a working header.
    true = picker(pair.private_port, headers={"X-Mentis-Peer": "100.64.0.1",
                                              "X-Mentis-Boot-Secret": pair.secret})
    assert true == {"available": False, "why_not": PICKER_PEER_WORDS}


# -- Static, 5 -------------------------------------------------------------------------------------


def test_the_index_is_served(py, pair):
    ours = assert_same(py, pair, request("GET", "/", close=False))
    assert ours.status == 200
    assert ours.header("Content-Type") == "text/html"


def test_a_hashed_asset_is_served_with_python_s_type(py, pair):
    assets = sorted((common.dist_dir() / "assets").iterdir())
    for name in {path.suffix: path for path in assets}.values():
        ours = assert_same(py, pair, request("GET", f"/assets/{name.name}", close=False), wait=5.0)
        assert ours.status == 200, name
        assert ours.body == name.read_bytes()


def test_a_missing_file_is_the_page(py, pair):
    ours = assert_same(py, pair, request("GET", "/assets/no-such-file.js", close=False))
    assert ours.status == 200
    assert ours.header("Content-Type") == "text/html"


def test_dot_dot_traversal_goes_nowhere(py, pair):
    for path in ["/../pyproject.toml", "/../../pyproject.toml", "/assets/../../pyproject.toml",
                 "/%2e%2e/pyproject.toml", "/..%2fpyproject.toml", "/..\\pyproject.toml"]:
        ours = assert_same(py, pair, request("GET", path, close=False))
        assert ours.status == 200, path
        assert b"[project]" not in ours.body, path


def test_with_no_build_present_both_say_so(tmp_path, brain_seed):
    missing = tmp_path / "no-fluid-build"
    theirs_copy = seed_copy(brain_seed, tmp_path, "py-no-build")
    ours_copy = seed_copy(brain_seed, tmp_path, "pair-no-build")
    with py_alone.running(theirs_copy, port=PY_UNBUILT_PORT, dist=missing), \
            Pair(ours_copy, port=PAIR_UNBUILT_PORT, dist=missing) as running:
        for path in ["/", "/assets/anything.js"]:
            data = request("GET", path, close=False)
            theirs = Answer(exchange(PY_UNBUILT_PORT, data))
            ours = Answer(exchange(running.port, data))
            assert ours.comparable == theirs.comparable, path
            assert ours.status == 404
            assert ours.json["kind"] == "NotFound"
