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
        kept = json.dumps(list(cv._shared["memo"].values()), default=str)
    finally:
        read_done.set()
        t.join(30)
    assert seen["turn"] in seen["writer_sees"]
    assert seen["turn"] not in seen["reader_sees"]
    assert seen["turn"] not in kept
    with reading_beside_writer(), cv.reading():
        after = [e["id"] for e in cv.contributions(conv)]
    assert seen["turn"] not in after
    assert cv._shared["memo"], "nothing was kept after the rollback"
    assert seen["turn"] not in json.dumps(list(cv._shared["memo"].values()), default=str)
    assert seen["turn"] not in json.dumps(over(owner, "find", q="sharedmemo", limit=50))


def test_a_scope_older_than_what_is_kept_reads_for_itself(owner):
    """A long read opened before another handle's commit meets answers kept by
    a newer read. It must answer -- from its own reading, never blocking on
    the shared answers -- and must not throw the newer ones away."""
    w = owner["world"]
    cv = owner["state"].cv
    conv = w["design"]
    got, newer = {}, {}

    def older_read():
        with reading_beside_writer(), cv.reading():
            first = [e["id"] for e in cv.contributions(conv)]
            wrote = {}

            def write():                     # another handle, another thread
                wrote["id"] = w["cv"].say(conv, w["who"]["@brian"],
                                          [text("sharedmemo older-scope")])
            t = threading.Thread(target=write)
            t.start()
            t.join(30)
            said = wrote["id"]

            def newer_read():
                with reading_beside_writer(), cv.reading():
                    newer["ids"] = [e["id"] for e in cv.contributions(conv)]
                    newer["epoch"] = cv._shared["writes"]
            t = threading.Thread(target=newer_read)
            t.start()
            t.join(30)
            # older now: `turn_number` asks the memo inside the memo
            got["number"] = cv.turn_number(first[0])
            got["ids"] = [e["id"] for e in cv.contributions(conv)]
            got["first"], got["said"] = first, said

    reader = threading.Thread(target=older_read)
    reader.start()
    reader.join(30)
    assert not reader.is_alive(), "an older scope blocked on the shared answers"
    assert got["number"] == 1
    assert got["said"] in newer["ids"]
    assert got["said"] not in got["first"]
    assert cv._shared["writes"] == newer["epoch"], "the newer answers were thrown away"


def test_a_rollback_ends_what_its_own_thread_read(owner):
    """The writer's thread reads its own appended rows inside one reading;
    the transaction rolls back; the same reading, asked again, must not show
    them -- the rollback moves the count every answer is kept on."""
    w = owner["world"]
    cv = owner["state"].cv
    conv = w["tavern"]

    class RolledBack(Exception):
        pass

    with cv.reading():
        try:
            with owner["state"].corpus.atomic():
                said = cv.say(conv, w["who"]["@brian"], [text("sharedmemo rolled back")])
                assert said in [e["id"] for e in cv.contributions(conv)]
                raise RolledBack()
        except RolledBack:
            pass
        assert said not in [e["id"] for e in cv.contributions(conv)]


def test_an_answer_too_large_to_share_is_still_asked_once_per_reading(owner, monkeypatch):
    """Over a tenth of the bound, an answer is kept for its own reading only:
    asked again there it is not recomputed, it is not shared, and the shared
    memo is not emptied for it."""
    w = owner["world"]
    cv = owner["state"].cv
    monkeypatch.setattr(type(cv), "SHARED_UNITS", 20)
    calls = _count_contributions(monkeypatch, cv)
    big = w["design"]
    with reading_beside_writer(), cv.reading():
        first = cv.contributions(big)
        assert len(first) + 1 > 20 // 10, "the answer must be over a tenth of the bound"
        cv.contributions(big)
        assert calls.count(big) == 1, "recomputed within one reading"
        assert ("contributions", big) not in cv._shared["memo"]


def test_a_full_shared_memo_stops_growing_rather_than_starting_again(owner, monkeypatch):
    w = owner["world"]
    cv = owner["state"].cv
    monkeypatch.setattr(type(cv), "SHARED_UNITS", 10**6)
    with reading_beside_writer(), cv.reading():
        for c in (w["design"], w["research"], w["tavern"]):
            cv.contributions(c)
        held = dict(cv._shared["memo"])
        assert held
        monkeypatch.setattr(type(cv), "SHARED_UNITS", cv._shared["units"])  # now full
        cv.turn_number(cv.contributions(w["design"])[0]["id"])
        assert all(k in cv._shared["memo"] for k in held), "kept answers were thrown away"
