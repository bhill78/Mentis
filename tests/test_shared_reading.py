"""Reading answers shared between requests on one unmoved record.

WHAT MUST HOLD, against a real HTTP server and the real `/api/worker` door:
  - two reads of an unmoved record compute a Conversation's posts once;
  - a write through this handle ends what was kept: the next read sees it;
  - a write through ANOTHER handle on the same Brain (which this process's
    write count cannot see) ends it too;
  - rows a transaction has appended and not committed are never shared: a
    reader beside the writer does not see them, nothing kept includes them,
    and once the transaction is rolled back no read ever shows them.
"""

from __future__ import annotations

import json
import threading

import mentis.api as api
from mentis.conversation import text
from mentis.spine.store import reading_beside_writer
from mentis.web import _surface
from tests.test_worker_read_scope import over, owner  # noqa: F401


def _count_contributions(monkeypatch, cv):
    calls = []
    real = type(cv)._contributions

    def counted(self, conversation):
        if self is cv:
            calls.append(conversation)
        return real(self, conversation)
    monkeypatch.setattr(type(cv), "_contributions", counted)
    return calls


def test_two_reads_of_an_unmoved_record_compute_once(owner, monkeypatch):
    w = owner["world"]
    cv = _surface(owner["state"]).cv
    cv._shared.update(memo={}, snapshots={}, writes=None)
    calls = _count_contributions(monkeypatch, cv)
    first = over(owner, "find", q="a", limit=50)
    once = len(calls)
    second = over(owner, "find", q="a", limit=50)
    assert first == second
    assert once >= 1 and len(calls) == once


def test_a_write_through_this_handle_ends_what_was_kept(owner):
    w = owner["world"]
    over(owner, "find", q="sharedmemothis", limit=10)
    said = owner["state"].cv.say(w["design"], w["who"]["@brian"],
                                 [text("sharedmemothis marker")])
    assert said in json.dumps(over(owner, "find", q="sharedmemothis", limit=10))


def test_a_write_through_another_handle_ends_what_was_kept(owner):
    """The fixture's `cv` opens a Store of its own: its commits never move
    the server's `steady`, only what the database says has been written."""
    w = owner["world"]
    over(owner, "find", q="sharedmemoother", limit=10)
    said = w["cv"].say(w["research"], w["who"]["@brian"],
                       [text("sharedmemoother marker")])
    assert said in json.dumps(over(owner, "find", q="sharedmemoother", limit=10))


def test_uncommitted_rows_are_never_shared(owner):
    w = owner["world"]
    state = owner["state"]
    cv = state.cv
    conv = w["tavern"]
    seen = {}
    appended = threading.Event()
    read_done = threading.Event()

    class RolledBack(Exception):
        pass

    def writer():
        try:
            with state.corpus.atomic():
                seen["turn"] = cv.say(conv, w["who"]["@brian"],
                                      [text("sharedmemo uncommitted")])
                with cv.reading():          # the writer reads its own rows
                    seen["writer_sees"] = [e["id"] for e in cv.contributions(conv)]
                appended.set()
                read_done.wait(30)
                raise RolledBack()
        except RolledBack:
            pass

    t = threading.Thread(target=writer)
    t.start()
    assert appended.wait(30)
    try:
        with reading_beside_writer(), cv.reading():
            seen["reader_sees"] = [e["id"] for e in cv.contributions(conv)]
        kept = json.dumps(cv._shared["memo"], default=str)
    finally:
        read_done.set()
        t.join(30)
    assert seen["turn"] in seen["writer_sees"]
    assert seen["turn"] not in seen["reader_sees"]
    assert seen["turn"] not in kept
    with reading_beside_writer(), cv.reading():
        after = [e["id"] for e in cv.contributions(conv)]
    assert seen["turn"] not in after
    assert seen["turn"] not in json.dumps(over(owner, "find", q="sharedmemo", limit=50))
