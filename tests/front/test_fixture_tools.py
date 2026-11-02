"""R1's fixture tools, with nothing built: the ledger, the per-test comparison, the messages."""

from __future__ import annotations

import contextlib
import http.client
import http.server
import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
import urllib.error
import urllib.request

import pytest

from tests.front import restart_messages
from tools.r1 import compare_outcomes, door_recorder, ledger


def test_ledger_format_and_version(tmp_path):
    path = tmp_path / "run.ledger"
    book = ledger.Ledger(path)
    book.acknowledged("ent-1", "entry", 7, "abc")
    book.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"format": "r1-ledger", "version": 1}
    assert json.loads(lines[1]) == {"id": "ent-1", "table": "entry", "seq": 7, "hash": "abc"}
    assert ledger.read(path) == [{"id": "ent-1", "table": "entry", "seq": 7, "hash": "abc"}]


def test_ledger_belongs_to_one_run(tmp_path):
    ledger.Ledger(tmp_path / "run.ledger").close()
    with pytest.raises(FileExistsError):
        ledger.Ledger(tmp_path / "run.ledger")


def test_ledger_refuses_another_version(tmp_path):
    path = tmp_path / "old.ledger"
    path.write_text('{"format": "r1-ledger", "version": 2}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        ledger.read(path)


def test_writer_fsyncs_each_acknowledgement_before_the_next_write_begins(tmp_path, monkeypatch):
    events = []
    real = os.fsync
    monkeypatch.setattr(ledger.os, "fsync", lambda fd: (events.append("fsync"), real(fd))[1])
    book = ledger.Ledger(tmp_path / "run.ledger")
    events.clear()  # the header's own

    def send(n):
        def go():
            events.append(f"send {n}")
            return (f"ent-{n}", "entry", n, f"h{n}")
        return go

    writer = ledger.Writer(book)
    writer.write(send(1))
    writer.write(send(2))
    book.close()
    assert events == ["send 1", "fsync", "send 2", "fsync"]


def test_a_write_not_acknowledged_records_nothing(tmp_path):
    book = ledger.Ledger(tmp_path / "run.ledger")

    def fails():
        raise ConnectionResetError("no answer")

    with pytest.raises(ConnectionResetError):
        ledger.Writer(book).write(fails)
    book.close()
    assert ledger.read(tmp_path / "run.ledger") == []


def test_acknowledged_rows_outlive_a_hard_kill_of_the_writer(tmp_path):
    path = tmp_path / "run.ledger"
    code = textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {os.getcwd()!r})
        from tools.r1 import ledger
        book = ledger.Ledger({str(path)!r})
        for n in range(5):
            book.acknowledged(f"ent-{{n}}", "entry", n, "h")
        os._exit(9)
    """)
    done = subprocess.run([sys.executable, "-c", code], check=False)
    assert done.returncode == 9
    assert [r["seq"] for r in ledger.read(path)] == [0, 1, 2, 3, 4]


def test_verify_names_a_missing_row_and_a_changed_hash(tmp_path):
    conn = sqlite3.connect(tmp_path / "r.db")
    conn.execute("CREATE TABLE entry (seq INTEGER, id TEXT, hash TEXT)")
    conn.execute("INSERT INTO entry VALUES (1, 'ent-a', 'ha'), (2, 'ent-b', 'hb')")
    book = ledger.Ledger(tmp_path / "run.ledger")
    book.acknowledged("ent-a", "entry", 1, "ha")
    book.close()
    assert ledger.verify(tmp_path / "run.ledger", conn) == []

    book = ledger.Ledger(tmp_path / "bad.ledger")
    book.acknowledged("ent-a", "entry", 1, "changed")
    book.acknowledged("ent-gone", "entry", 3, "hg")
    book.close()
    wrong = ledger.verify(tmp_path / "bad.ledger", conn)
    assert len(wrong) == 2
    assert wrong[0].startswith("different: entry ent-a")
    assert wrong[1] == "missing: entry ent-gone"


JUNIT = """<testsuites><testsuite>
<testcase classname="tests.test_a" name="test_good"/>
<testcase classname="tests.test_a" name="test_known_bad"><failure message="x"/></testcase>
<testcase classname="tests.test_a.TestK" name="test_m[1]"/>
<testcase classname="tests.test_b" name="test_skip"><skipped/></testcase>
<testcase classname="tests.test_b" name="test_broke"><error message="x"/></testcase>
</testsuite></testsuites>"""


def test_junit_gives_node_ids_and_outcomes(tmp_path):
    path = tmp_path / "j.xml"
    path.write_text(JUNIT, encoding="utf-8")
    assert compare_outcomes.pytest_outcomes(path) == {
        "tests/test_a.py::test_good": "passed",
        "tests/test_a.py::test_known_bad": "failed",
        "tests/test_a.py::TestK::test_m[1]": "passed",
        "tests/test_b.py::test_skip": "skipped",
        "tests/test_b.py::test_broke": "error",
    }


def test_equal_totals_cannot_hide_a_repair_and_a_new_regression():
    baseline = {"outcomes": {"t::good": "passed", "t::allowed": "failed"}}
    swapped = {"t::good": "failed", "t::allowed": "passed"}
    assert compare_outcomes.differences(baseline["outcomes"], baseline["outcomes"]) == []
    assert len(compare_outcomes.differences(baseline["outcomes"], swapped)) == 2


@pytest.mark.parametrize("junit, code", [
    ('<testcase classname="tests.t" name="a"/><testcase classname="tests.t" name="b">'
     '<failure/></testcase>', 0),
    ('<testcase classname="tests.t" name="a"/>', 1),  # one missing
    ('<testcase classname="tests.t" name="a"/><testcase classname="tests.t" name="b"/>', 1),
    ('<testcase classname="tests.t" name="a"/><testcase classname="tests.t" name="b">'
     '<failure/></testcase><testcase classname="tests.t" name="c"/>', 1),  # one added
    ('', 1),
])
def test_compare_exits_nonzero_on_any_difference(tmp_path, junit, code):
    baseline = {"outcomes": {"tests/t.py::a": "passed", "tests/t.py::b": "failed"}}
    (tmp_path / "base.json").write_text(json.dumps(baseline), encoding="utf-8")
    (tmp_path / "j.xml").write_text(f"<testsuite>{junit}</testsuite>", encoding="utf-8")
    got = compare_outcomes.main(["pytest", str(tmp_path / "base.json"), str(tmp_path / "j.xml")])
    assert got == code


def test_npm_lines_are_read_per_file():
    text = "> node tests/run.mjs\n\nok   a_unit.mjs\nFAIL b_unit.mjs\nboom\nskip c_unit.mjs (why)\n"
    assert compare_outcomes.npm_outcomes(text) == {
        "a_unit.mjs": "passed", "b_unit.mjs": "failed", "c_unit.mjs": "skipped"}


REFUSED = ("<urlopen error [WinError 10061] No connection could be made because the target "
           "machine actively refused it>")
VIA = "http://127.0.0.1:8852"


@pytest.mark.parametrize("message, cases", [
    (f"NoOwner: no Mentis is answering at {VIA} for corpus 'C:\\\\b\\\\brain': {REFUSED}. The "
     "record can only be read by the process that owns it, so there is no answer to give and "
     "nothing else to try.", ["A", "B-sending"]),
    (f"OwnerError: Mentis at {VIA} stopped before answering 'record_outcome': the request was "
     "sent, so the result is unknown. It may still have done it: do not report it as not done. "
     "Check the record, or call it again if it is safe to repeat.", ["B-sent", "B-reply"]),
    (f"OwnerError: Mentis at {VIA} did not answer 'answer' within 30 s. It may still have done "
     "it: do not report it as not done. Check the record, or call it again if it is safe to "
     "repeat.", ["E-timeout"]),
    (f"OwnerError: Mentis at {VIA} could not answer this: Python stopped with this request in "
     "hand, so the result is unknown. It may still have done it: check the record before "
     "repeating it.", ["Python-reached"]),
    (f"OwnerError: Mentis at {VIA} could not answer this: Python is not answering behind this "
     "front, so this request did not reach it and nothing was done.", ["Python-unreached"]),
])
def test_each_allowed_message_is_decided(message, cases):
    assert restart_messages.decide(message) == cases


@pytest.mark.parametrize("message", [
    "IncompleteRead: IncompleteRead(10 bytes read, 5 more expected)",
    "RemoteDisconnected: Remote end closed connection without response",
    f"NoOwner: no Mentis is answering at {VIA} for corpus 'x': timed out. The record can only "
    "be read by the process that owns it, so there is no answer to give and nothing else to try.",
    f"OwnerError: Mentis at {VIA} stopped before answering 'answer': the result is unknown.",
    f"OwnerError: Mentis at {VIA} could not answer this: something else went wrong",
    "NotPermitted: Mentis did the write but falsely says it did not",
    "",
])
def test_any_other_message_fails(message):
    assert restart_messages.decide(message) == []


REFUSAL = {"error": "'answer' is not admissible for this execution", "kind": "PermissionError"}


def _told_by_the_worker(status_body: str) -> str:
    """What the real `_over` and `serve`'s catch-all tell an agent of a 403 with this body."""
    from mentis.worker import _over

    class Door(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            data = status_body.encode("utf-8")
            self.send_response(403)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Door)
    threading.Thread(target=server.handle_request, daemon=True).start()
    try:
        _over(f"http://127.0.0.1:{server.server_port}", "x", "answer", {}, "a-grant")
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"
    finally:
        server.server_close()
    raise AssertionError("a 403 raised nothing")


class _StandIn(http.server.ThreadingHTTPServer):
    """One side of the wire in these tests, as `answer(handler, body)` says. Counts what it got."""
    daemon_threads = True

    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

        class Side(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                self.server.calls += 1
                length = int(self.headers.get("Content-Length") or 0)
                self.server.answer(self, self.rfile.read(length))

            do_GET = do_POST

            def log_message(self, *a):
                pass

        super().__init__(("127.0.0.1", 0), Side)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_port}"

    def stop(self):
        self.shutdown()
        self.server_close()


def _reply(handler, status, body: str, *headers):
    data = body.encode("utf-8")
    handler.send_response_only(status)
    for name, value in headers:
        handler.send_header(name, value)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


@pytest.fixture
def corpus(tmp_path):
    db = tmp_path / "corpus.db"
    conn = sqlite3.connect(db)
    for table, at in restart_messages.STAMPED.items():
        conn.execute(f"CREATE TABLE {table} (seq INTEGER PRIMARY KEY, {at} REAL)")
    conn.commit()
    conn.close()
    return db


def _write_row(db, table, stamp):
    conn = sqlite3.connect(db)
    conn.execute(f"INSERT INTO {table} VALUES (NULL, ?)", (stamp,))
    conn.commit()
    conn.close()


@contextlib.contextmanager
def _python_behind_a_recorder(answer):
    """A stand-in for Python's door, and the harness's recorder in front of it."""
    python = _StandIn(answer)
    try:
        with door_recorder.DoorRecorder(python.server_port) as recorder:
            yield python, recorder
    finally:
        python.stop()


def _refuses(handler, _body):
    _reply(handler, 403, json.dumps(REFUSAL))


def _told_through(via: str) -> str:
    from mentis.worker import _over

    try:
        _over(via, "x", "answer", {}, "a-grant")
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"
    raise AssertionError("the call raised nothing")


def test_a_genuine_refusal_passes(corpus):
    with _python_behind_a_recorder(_refuses) as (python, recorder):
        # A row of another moment isn't this call's.
        _write_row(corpus, "entry", time.time() - 60)
        _write_row(corpus, "operational", time.time() + 60)
        told = _told_through(recorder.url)
        assert told == f"NotPermitted: {REFUSAL['error']}"
        assert python.calls == 1
        refusals = restart_messages.Refusals(recorder, corpus)
        assert restart_messages.decide(told, refusals=refusals) == ["Refused"]
        assert refusals.failed == []


def test_a_false_refusal_fails_with_a_real_one_beside_it(corpus):
    with _python_behind_a_recorder(_refuses) as (_, recorder):
        _told_through(recorder.url)
        refusals = restart_messages.Refusals(recorder, corpus)
        told = "NotPermitted: Mentis did the write but falsely says it did not"
        assert restart_messages.decide(told, refusals=refusals) == []
        assert refusals.failed == [f"Python answered no such refusal: {told}"]


@pytest.mark.parametrize("table", list(restart_messages.STAMPED))
def test_a_refusal_whose_call_wrote_fails(corpus, table):
    def writes_then_refuses(handler, _body):
        _write_row(corpus, table, time.time())
        _refuses(handler, _body)

    with _python_behind_a_recorder(writes_then_refuses) as (_, recorder):
        told = _told_through(recorder.url)
        refusals = restart_messages.Refusals(recorder, corpus)
        assert restart_messages.decide(told, refusals=refusals) == []
        assert refusals.failed[0].startswith("1 rows written while refusing")


def test_one_refusal_vouches_for_one_message(corpus):
    with _python_behind_a_recorder(_refuses) as (_, recorder):
        told = _told_through(recorder.url)
        refusals = restart_messages.Refusals(recorder, corpus)
        assert restart_messages.decide(told, refusals=refusals) == ["Refused"]
        assert restart_messages.decide(told, refusals=refusals) == []


def test_no_call_vouches_for_nothing(corpus):
    with _python_behind_a_recorder(_refuses) as (_, recorder):
        refusals = restart_messages.Refusals(recorder, corpus)
        assert restart_messages.decide(f"NotPermitted: {REFUSAL['error']}",
                                       refusals=refusals) == []


def _wrote_its_own_line(tmp_path, body: str) -> None:
    """What a defective front could leave: a perfect line, in the file P1.2 once owed."""
    (tmp_path / "worker-refusals.jsonl").write_text(
        json.dumps({"received_at": 1000.0, "answered_at": 1000.2, "body": body}) + "\n",
        encoding="utf-8")


def test_a_front_that_fabricates_a_refusal_and_its_own_line_fails(tmp_path, corpus):
    def fabricates(handler, _body):
        _wrote_its_own_line(tmp_path, json.dumps(REFUSAL))
        _reply(handler, 403, json.dumps(REFUSAL))

    with _python_behind_a_recorder(_refuses) as (python, recorder):
        front = _StandIn(fabricates)
        try:
            told = _told_through(front.url)
        finally:
            front.stop()
        assert told == f"NotPermitted: {REFUSAL['error']}"
        assert (tmp_path / "worker-refusals.jsonl").exists()
        assert python.calls == 0  # no such call reached Python
        refusals = restart_messages.Refusals(recorder, corpus)
        assert restart_messages.decide(told, refusals=refusals) == []
        assert refusals.failed == [f"Python answered no such refusal: {told}"]


def _forwards(recorder_of, says):
    """A stand-in front that really forwards the call, then tells the caller `says`'s 403."""
    def go(handler, body):
        request = urllib.request.Request(
            f"{recorder_of()}/api/worker", method="POST", data=body,
            headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(request, timeout=10).read()
        except urllib.error.HTTPError as exc:
            exc.read()
        _reply(handler, 403, says)
    return go


def test_a_front_that_turns_a_write_into_a_refusal_fails(tmp_path, corpus):
    def writes(handler, _body):
        _write_row(corpus, "entry", time.time())
        _reply(handler, 200, "{}")

    with _python_behind_a_recorder(writes) as (python, recorder):
        front = _StandIn(_forwards(lambda: recorder.url, json.dumps(REFUSAL)))
        try:
            told = _told_through(front.url)
        finally:
            front.stop()
        assert python.calls == 1
        assert recorder.refusals == []  # Python answered 200, and that isn't a refusal
        refusals = restart_messages.Refusals(recorder, corpus)
        assert restart_messages.decide(told, refusals=refusals) == []


def test_a_front_that_changes_pythons_words_fails(corpus):
    with _python_behind_a_recorder(_refuses) as (_, recorder):
        changed = json.dumps({**REFUSAL, "error": "you may not, says the front"})
        front = _StandIn(_forwards(lambda: recorder.url, changed))
        try:
            told = _told_through(front.url)
        finally:
            front.stop()
        assert len(recorder.refusals) == 1
        refusals = restart_messages.Refusals(recorder, corpus)
        assert restart_messages.decide(told, refusals=refusals) == []


def test_the_recorder_carries_a_call_unchanged_and_keeps_only_the_doors_403s():
    seen = []

    def answer(handler, body):
        seen.append((handler.command, handler.path, list(handler.headers.items()), body))
        status = 403 if handler.path.startswith("/fluid/") else 200
        _reply(handler, status, "the body", ("Set-Cookie", "a=1"), ("X-Two", "x"),
               ("Set-Cookie", "b=2"))

    with _python_behind_a_recorder(answer) as (_, recorder):
        sent = [("Host", "front.example:8852"), ("X-Mentis-Peer", "10.0.0.7"),
                ("X-Mentis-Boot-Secret", "s"), ("Content-Length", "4")]
        conn = http.client.HTTPConnection("127.0.0.1", int(recorder.url.rsplit(":", 1)[1]))
        conn.putrequest("POST", "/api/worker?a=%2Fb", skip_host=True, skip_accept_encoding=True)
        for name, value in sent:
            conn.putheader(name, value)
        conn.endheaders(b"ping")
        answered = conn.getresponse()
        assert answered.status == 200
        assert answered.read() == b"the body"
        assert [h for h in answered.getheaders() if h[0] != "Content-Length"] == [
            ("Set-Cookie", "a=1"), ("X-Two", "x"), ("Set-Cookie", "b=2")]
        conn.request("POST", "/fluid/api/posts", body=b"", headers={"Host": "h"})
        assert conn.getresponse().read() == b"the body"  # the same connection, kept alive
        conn.close()
        assert seen[0] == ("POST", "/api/worker?a=%2Fb", sent, b"ping")
        assert recorder.refusals == []


def test_the_recorder_outlives_a_front_killed_with_a_call_in_hand(corpus):
    release = threading.Event()

    def slow(handler, body):
        if json.loads(body)["op"] == "slow":
            release.wait(30)
        _refuses(handler, body)

    with _python_behind_a_recorder(slow) as (python, recorder):
        host, port = recorder.url.removeprefix("http://").split(":")
        body = json.dumps({"op": "slow"})
        code = textwrap.dedent(f"""
            import socket, sys, time
            s = socket.create_connection(({host!r}, {port}))
            s.sendall(b"POST /api/worker HTTP/1.1\\r\\nHost: h\\r\\nContent-Length: {len(body)}"
                      b"\\r\\n\\r\\n" + {body!r}.encode())
            print("sent", flush=True)
            time.sleep(60)
        """)
        front = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE)
        try:
            assert front.stdout.readline().strip() == b"sent"
            deadline = time.monotonic() + 10
            while python.calls < 1:
                assert time.monotonic() < deadline
                time.sleep(0.01)
        finally:
            front.kill()
            front.wait()
            front.stdout.close()
        release.set()
        deadline = time.monotonic() + 10
        while not recorder.refusals:  # Python answered, whoever was left to hear it
            assert time.monotonic() < deadline
            time.sleep(0.01)
        told = _told_through(recorder.url)  # the next front gets through the same recorder
        assert python.calls == 2
        assert len(recorder.refusals) == 2
        refusals = restart_messages.Refusals(recorder, corpus)
        assert restart_messages.decide(told, refusals=refusals) == ["Refused"]


@pytest.mark.parametrize("body", [
    json.dumps({**REFUSAL, "error": "x" * 1300}),  # cut short by `_over`, so not JSON to it
    json.dumps({"kind": "PermissionError"}),       # no `error` to say
    "[1]",                                         # JSON, and not an object
    "not json",
])
def test_the_message_is_made_from_a_body_as_the_worker_makes_it(body):
    assert restart_messages.told_for(body) == _told_by_the_worker(body)


def test_a_sent_call_may_not_read_as_nothing_done():
    # Case B after sending: the message allowed for case A says nothing was done, which is false.
    told = (f"NoOwner: no Mentis is answering at {VIA} for corpus 'x': {REFUSED}. The record can "
            "only be read by the process that owns it, so there is no answer to give and nothing "
            "else to try.")
    assert restart_messages.decide(told, ["B-sent", "B-reply"]) == []


def test_the_bridge_exit_is_decided():
    good = (f"mentis mcp bridge: Mentis is not answering at {VIA} ({REFUSED}); start it, then "
            "reconnect\n")
    assert restart_messages.is_bridge_exit(good)
    assert not restart_messages.is_bridge_exit("mentis mcp bridge: something else")
    assert restart_messages.LIST["bridge_exit"]["C"]["exit_code"] == 1


def test_the_503_reasons_are_the_ones_the_agent_is_told():
    for case, reason in restart_messages.LIST["front_503_error"].items():
        told = f"OwnerError: Mentis at {VIA} could not answer this: {reason}"
        assert restart_messages.decide(told) == [case]
