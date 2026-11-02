"""A Python handler that raises with nothing yet written: the same 500, alone and through the front.

The owner's decision `opr-f2ea91ab6992`, "Python answers its own failures" (`ent-d3d2c2c99ff6`). So a
silent close means Python really went, and the front's 503 stays honest. It is no row of
`R1-acceptance.md`.

"Alone" here is THIS commit's Python, not `PY-ALONE`. `PY-ALONE` is frozen at `b8e324c`, before this
decision, and closes without a word on all of these. `R1-acceptance.md`, "A", has the revision.

An exception after a commit reaches the same answer, so its words never say that nothing was done.

An answer given with a declared body unread stays open for that body, up to `LINGER_S`, so closing
doesn't send the RST that loses the answer, and so a silent close keeps meaning what it says.
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import socket
import subprocess
import time

import pytest

from tests.front.pair import (FRONT_503, PY_PORT, SPARE_PORTS, Answer, Pair, advance,
                              conversation_named, exchange, process_tree, request, rows)
from tools.r1 import common, py_alone

WORDS = ("This server failed while handling this request, so the result is unknown. It may still "
         "have done it: check the record before repeating it.")
#: In a log, once for each request that failed. `socketserver`'s `handle_error` prints it.
ONE_FAILURE = "Exception occurred during processing of request from ('127.0.0.1', "

STAND_IN_PORT, FRONT_OF_STAND_IN_PORT = SPARE_PORTS[:2]
STAND_IN = common.REPO / "tests" / "fakes" / "python_that_raises.py"
JSON_POST = {"X-Mentis-Client": "1", "Content-Type": "application/json"}
FIVE_THOUSAND_DIGITS = "1" * 5000
#: `_Handler.LINGER_S`.
LINGER_S = 2.0


def posted(path: str, body: bytes = b"", length: int | str | None = None, *, also=None) -> bytes:
    """A request whose Content-Length is as said, whatever is sent after it."""
    length = len(body) if length is None else length
    return request("POST", path, headers={**JSON_POST, **(also or {}), "Content-Length": length}) + body


#: What each raises, or `None` where that depends on the machine or the Python: only the status,
#: the words and `alone == through` then decide it.
CASES = {
    "bad-json": (posted("/api/conversations", b"{x"), "JSONDecodeError"),
    "invalid-utf-8": (posted("/api/conversations", b'{"a": "\xc3\x28"}'), "UnicodeDecodeError"),
    "nul-in-a-target": (request("GET", "/%00"), "ValueError"),
    "2^38-declared": (posted("/api/conversations", length=1 << 38), None),
    "2^38-declared-fluid": (posted("/fluid/api/posts", length=1 << 38), None),
    "5000-digit-post": (posted("/api/conversations", length=FIVE_THOUSAND_DIGITS), "ValueError"),
    "5000-digit-get": (request("GET", "/api/server",
                               headers={"Content-Length": FIVE_THOUSAND_DIGITS}), "ValueError"),
    "unparsable-get": (request("GET", "http://[/x"), "ValueError"),
    "unparsable-post": (posted("http://[/x", b"{}"), "ValueError"),
    "unparsable-options": (request("OPTIONS", "http://[/x"), "ValueError"),
    "keeping-the-connection": (posted("/api/conversations", b"{x").replace(
        b"Connection: close\r\n", b""), "JSONDecodeError"),
}


def without_date(raw: bytes) -> bytes:
    return re.sub(rb"(?m)^Date: [^\r\n]*\r\n", b"", raw)


def failures_in(log) -> int:
    return log.read_text(encoding="utf-8", errors="replace").count(ONE_FAILURE)


def assert_is_the_500(raw: bytes, kind: str | None) -> None:
    got = Answer(raw)
    assert got.status_line == "HTTP/1.1 500 Internal Server Error", raw
    assert [name for name, _ in got.headers] == ["Server", "Date", "Connection", "Content-Type",
                                                 "Content-Length", "Cache-Control"], raw
    assert got.header("Connection") == "close"
    assert got.header("Content-Type") == "application/json"
    assert got.json["error"] == WORDS
    assert kind is None or got.json["kind"] == kind, raw
    assert set(got.json) == {"error", "kind"}
    assert raw.count(b"HTTP/1.") == 1, raw


class Both:
    """One request to Python alone and to the pair, each counted in its own log."""

    def __init__(self, alone_port: int, alone_log, pair: Pair):
        self.alone_port, self.alone_log, self.pair = alone_port, alone_log, pair

    def asked(self, data: bytes) -> tuple[bytes, bytes]:
        log = self.pair.run_dir / "python.log"
        before = failures_in(self.alone_log), failures_in(log)
        python, tree = self.pair.python_pid, process_tree(self.pair.python_pid)
        theirs = exchange(self.alone_port, data, wait=20.0)
        ours = exchange(self.pair.port, data, wait=20.0)
        assert (failures_in(self.alone_log) - before[0], failures_in(log) - before[1]) == (1, 1), (
            "each failure logged once", theirs, ours)
        # Python hasn't gone, on either side, and neither port has stopped answering.
        assert self.pair.python_pid == python and process_tree(python) == tree
        assert Answer(exchange(self.alone_port, request("GET", "/api/server"))).status == 200
        assert Answer(exchange(self.pair.private_port, request("GET", "/api/server"))).status == 200
        return theirs, ours


@pytest.fixture(scope="module")
def both(brain_seed, tmp_path_factory):
    parent = tmp_path_factory.mktemp("handler-failure")
    alone_copy, pair_copy = parent / "alone" / "brain", parent / "pair" / "brain"
    shutil.copytree(brain_seed, alone_copy)
    shutil.copytree(brain_seed, pair_copy)
    run_dir = parent / "alone" / "run"
    with py_alone.running(alone_copy, port=PY_PORT, run_dir=run_dir, code=common.REPO), \
            Pair(pair_copy) as pair:
        yield Both(PY_PORT, run_dir / "server.log", pair)


@pytest.mark.parametrize("case", CASES, ids=str)
def test_a_handler_that_raises_is_the_same_500_alone_and_through_the_front(both, case):
    data, kind = CASES[case]
    theirs, ours = both.asked(data)
    assert without_date(ours) == without_date(theirs)
    assert_is_the_500(theirs, kind)


def test_nothing_is_recorded_and_the_503_is_never_given_for_a_handler_that_raised(both):
    before = advance(both.pair.brain)
    theirs, ours = both.asked(CASES["bad-json"][0])
    assert FRONT_503["Python-reached"].encode() not in ours + theirs
    assert advance(both.pair.brain) == before


def test_http_0_9_gets_the_500_s_body_alone(both):
    """It has no heads to send. A foreign or absent Host is refused first, so this one has one."""
    theirs, ours = both.asked(b"GET http://[/x\r\nHost: localhost\r\n\r\n")
    assert ours == theirs
    assert json.loads(theirs) == {"error": WORDS, "kind": "ValueError"}


def test_a_100_continue_is_not_the_answer(both):
    theirs, ours = both.asked(posted("/api/conversations", b"{x", also={"Expect": "100-continue"}))
    assert without_date(ours) == without_date(theirs)
    interim, _, final = theirs.partition(b"\r\n\r\n")
    assert interim == b"HTTP/1.1 100 Continue"
    assert_is_the_500(final, "JSONDecodeError")


# -- what no request can reach: `tests/fakes/python_that_raises.py` --------------------------------


class Raising:
    def __init__(self, brain, log, pair: Pair):
        self.brain, self.log, self.pair = brain, log, pair

    def alone(self, data: bytes) -> bytes:
        return exchange(STAND_IN_PORT, data, wait=20.0)

    def through(self, data: bytes) -> bytes:
        return exchange(self.pair.port, data, wait=20.0)


@pytest.fixture(scope="module")
def raising(brain_seed, tmp_path_factory):
    """The real server with `python_that_raises`'s replacements, with a front of its own before it.
    That front's pair has a Python too, which nothing here reaches."""
    parent = tmp_path_factory.mktemp("raising")
    its_copy, pair_copy = parent / "raises" / "brain", parent / "pair" / "brain"
    shutil.copytree(brain_seed, its_copy)
    shutil.copytree(brain_seed, pair_copy)
    log = parent / "raises" / "server.log"
    workspace = parent / "raises" / "ws"
    workspace.mkdir()
    with open(log, "ab") as out:
        started = subprocess.Popen(
            [str(common.venv_python()), str(STAND_IN), str(its_copy), "--port", str(STAND_IN_PORT),
             "--workspace", str(workspace), "--mars", py_alone.NO_MARS],
            cwd=common.REPO, env={**py_alone.environment(), "PYTHONPATH": str(common.REPO)},
            stdout=out, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + py_alone.START_LIMIT_S
        while True:
            with contextlib.suppress(OSError):
                if py_alone.get(STAND_IN_PORT, "/api/pulse", 2.0)[0] == 200:
                    break
            assert started.poll() is None and time.monotonic() < deadline, f"see {log}"
            time.sleep(0.2)
        with Pair(pair_copy, port=FRONT_OF_STAND_IN_PORT,
                  upstream=f"http://127.0.0.1:{STAND_IN_PORT}") as pair:
            yield Raising(its_copy, log, pair)
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(started.pid)], capture_output=True,
                       check=False)
        started.wait(timeout=30)


def owner_and_agent(brain) -> tuple[str, str]:
    alias = "SELECT id FROM entry WHERE def_name='participant' AND json_extract(body,'$.alias')=?"
    return rows(brain, alias, "@r1-owner")[0][0], rows(brain, alias, "@r1-agent")[0][0]


@pytest.mark.parametrize("name", ["alone", "through"])
def test_a_raise_after_a_commit_answers_words_that_are_true_of_it(raising, name):
    """`_send`'s `json.dumps`: the Conversation is on the record, and the answer doesn't deny it."""
    conversation = f"Committed, {name}"
    raw = getattr(raising, name)(posted("/api/conversations",
                                        json.dumps({"name": conversation}).encode()))
    assert_is_the_500(raw, "TypeError")
    assert conversation_named(raising.brain, conversation)


@pytest.mark.parametrize("name", ["alone", "through"])
def test_a_raise_from_dispatch_soon_after_a_commit_too(raising, name):
    owner, agent = owner_and_agent(raising.brain)
    text = f"Committed and not started, {name}"
    raw = getattr(raising, name)(posted("/fluid/api/posts", json.dumps({
        "conversation": conversation_named(raising.brain, "R1 known conversation"),
        "author": owner, "text": text, "action": "ask-participant", "addressed_to": [agent],
        "dispatch": [{"participant": agent, "runtime": "not-started"}]}).encode()))
    assert_is_the_500(raw, "RuntimeError")
    assert rows(raising.brain, "SELECT COUNT(*) FROM entry WHERE body LIKE ?", f"%{text}%")[0][0] == 1


def test_a_head_begun_and_not_ended_goes_nowhere(raising):
    data = posted("/api/raises/half-a-head")
    theirs, ours = raising.alone(data), raising.through(data)
    assert without_date(ours) == without_date(theirs)
    assert_is_the_500(theirs, "RuntimeError")
    assert b"X-Half" not in theirs


def test_a_timeout_http_server_keeps_to_itself_gets_the_500_too(raising):
    data = posted("/api/raises/timeout")
    theirs, ours = raising.alone(data), raising.through(data)
    assert without_date(ours) == without_date(theirs)
    assert_is_the_500(theirs, "TimeoutError")


def test_once_the_head_has_gone_no_second_one_follows(raising):
    data = posted("/api/raises/a-whole-head")
    theirs, ours = raising.alone(data), raising.through(data)
    assert without_date(ours) == without_date(theirs)
    assert Answer(theirs).status == 200
    assert theirs.count(b"HTTP/1.") == 1 and Answer(theirs).body == b"", theirs


def test_an_error_saying_the_client_went_is_left_alone(raising):
    """Nobody is there to answer. It is still logged, as every failure is. A handler that said so
    with a client there is what this makes of it: 0 bytes, so the front's 503 through the pair."""
    before = failures_in(raising.log)
    data = posted("/api/raises/client-gone")
    assert raising.alone(data) == b""
    assert failures_in(raising.log) == before + 1
    assert Answer(raising.through(data)).status == 503


def test_a_failure_raised_as_the_same_object_doesn_t_log_the_ones_before_it(raising):
    """A traceback grows with each raise of one object, and each log printed all of it: the whole
    server waited on that once CPython's MemoryErrors ran out, and its port refused connections."""
    data = posted("/api/raises/the-same-object")
    frames = ", in raising"
    before = raising.log.read_text(encoding="utf-8", errors="replace").count(frames)
    for _ in range(3):
        assert_is_the_500(raising.alone(data), "MemoryError")
    # Logged after the answer, so given a moment. Each failure once: 3, where carrying over is 6.
    deadline = time.monotonic() + 5
    while True:
        count = raising.log.read_text(encoding="utf-8", errors="replace").count(frames) - before
        if count >= 3 and time.monotonic() > deadline - 4.5 or time.monotonic() > deadline:
            break
        time.sleep(0.05)
    assert count == 3


def test_it_is_answered_before_draining_lets_go_of_it_and_never_counted_twice(raising):
    assert_is_the_500(raising.alone(posted("/api/raises/half-a-head")), "RuntimeError")
    # Only the one asking, in the end: the front's polls of this server come and go beside it.
    deadline = time.monotonic() + 5
    while True:
        flight = Answer(raising.alone(posted("/api/raises/flight"))).json
        if flight["now"] == 1 or time.monotonic() > deadline:
            break
        time.sleep(0.05)
    assert flight == {"left_before_its_500": False, "now": 1}


def test_a_client_header_refusal_still_wins_over_a_body_that_is_not_json(both):
    """Not everything has become this 500: what was refused before reading JSON still is."""
    data = request("POST", "/api/conversations", headers={"Content-Type": "application/json",
                                                          "Content-Length": 2}) + b"{x"
    theirs, ours = exchange(both.alone_port, data), exchange(both.pair.port, data)
    assert without_date(ours) == without_date(theirs)
    assert Answer(theirs).status == 403


# -- a body nobody read: the answer is read whole, whatever is still being sent --------------------


#: Each is answered from the head alone, with the body it declares unread and over `DISCARD_MAX`.
UNREAD = {
    "the-500": (posted("/api/conversations", length=1 << 38), 500),
    "the-413": (request("POST", "/api/artifacts", headers={"X-Mentis-Upload": "1",
                                                           "Content-Length": 1 << 38}), 413),
}
WHERE = ["alone", "through"]


def port_of(both: Both, where: str) -> int:
    return both.alone_port if where == "alone" else both.pair.port


def to_its_end(sock: socket.socket) -> bytes:
    """Unlike `exchange`, a reset is not the end of an answer: it raises."""
    got = b""
    while more := sock.recv(1 << 16):
        got += more
    return got


@pytest.mark.parametrize("where", WHERE)
@pytest.mark.parametrize("case", UNREAD, ids=str)
def test_a_client_that_sends_first_still_reads_the_whole_answer(both, case, where):
    data, status = UNREAD[case]
    with socket.create_connection(("127.0.0.1", port_of(both, where)), timeout=20) as sock:
        sock.sendall(data + bytes(1 << 20))
        raw = to_its_end(sock)
    got = Answer(raw)
    assert got.status == status, raw
    assert len(got.body) == int(got.header("Content-Length")), raw


@pytest.mark.parametrize("where", WHERE)
@pytest.mark.parametrize("case", UNREAD, ids=str)
def test_after_the_answer_a_body_still_arriving_is_read_and_not_reset(both, case, where):
    """What no rate decides. Once a socket has closed, what arrives for it is answered by RST, so
    this has the answer and its end first, and only then sends."""
    data, status = UNREAD[case]
    with socket.create_connection(("127.0.0.1", port_of(both, where)), timeout=20) as sock:
        sock.sendall(data)
        assert Answer(to_its_end(sock)).status == status
        sock.sendall(bytes(1 << 18))
        time.sleep(0.2)
        assert sock.recv(1) == b""


@pytest.mark.parametrize("where", WHERE)
def test_the_wait_for_a_body_has_its_bound(both, where):
    """Past it the connection does close, and a client still sending is told so."""
    data, status = UNREAD["the-500"]
    with socket.create_connection(("127.0.0.1", port_of(both, where)), timeout=20) as sock:
        sock.sendall(data)
        assert Answer(to_its_end(sock)).status == status
        began = time.monotonic()
        with pytest.raises(ConnectionError):
            while time.monotonic() - began < LINGER_S + 5:
                sock.sendall(bytes(1 << 16))
                time.sleep(0.02)
    assert LINGER_S - 0.5 < time.monotonic() - began < LINGER_S + 5


def in_flight(raising: Raising) -> int:
    return Answer(raising.alone(posted("/api/raises/flight"))).json["now"]


def test_the_wait_for_a_body_counts_as_in_flight_and_no_longer_than_its_bound(raising):
    """A stop waits for it, so stopping doesn't cut an answer that is still being read."""
    with socket.create_connection(("127.0.0.1", STAND_IN_PORT), timeout=20) as sock:
        sock.sendall(UNREAD["the-500"][0])
        assert Answer(to_its_end(sock)).status == 500
        for _ in range(5):
            # The one asking, and the one waiting. The front's polls can only add to that.
            assert in_flight(raising) >= 2
            time.sleep(0.05)
        # The connection is still held by this client: the bound alone ends the wait.
        deadline = time.monotonic() + LINGER_S + 3
        while in_flight(raising) != 1:
            assert time.monotonic() < deadline, "the wait outlasted its bound"
            time.sleep(0.05)


def test_a_body_read_whole_is_not_waited_for(raising):
    with socket.create_connection(("127.0.0.1", STAND_IN_PORT), timeout=20) as sock:
        sock.sendall(CASES["bad-json"][0])
        assert Answer(to_its_end(sock)).status == 500
        deadline = time.monotonic() + LINGER_S / 2
        while in_flight(raising) != 1:
            assert time.monotonic() < deadline, "held a connection with nothing unread"
            time.sleep(0.02)
