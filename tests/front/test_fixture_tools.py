"""R1's fixture tools, with nothing built: the ledger, the per-test comparison, the messages."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import textwrap

import pytest

from tests.front import restart_messages
from tools.r1 import compare_outcomes, ledger


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
    ("NotPermitted: 'ent-1' is already carried", ["Refused"]),
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
    "",
])
def test_any_other_message_fails(message):
    assert restart_messages.decide(message) == []


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
