"""Needs You under agents' writes (2026-11-26).

On DAY-TO-DAY, with seven agent runs writing, Needs You's list and details
took 3-9 s per read: its rule asked the state of every expectation the owner
had ever carried, under `Corpus.settled`, whose counted tries rarely held
while writes landed, so the whole Brain's expectations answered instead.
These pin the corrections:

  * `Store.one_moment` -- one read transaction, one moment of the record;
  * `Corpus.settled` computes once in it, writes landing or not;
  * Needs You's rule from the kept model, exact as the record stands now
    (`CurrentWork.owed_now`), whatever the model last caught up to;
  * a Turn's number by rank, never by reading every Turn's body.
"""
from __future__ import annotations

import threading

import pytest

from mentis.conversation import text
from mentis.operational import current_work as cw
from mentis.spine.store import WriteWhileReadingBeside
from tests._loop import a_conversation, say, world  # noqa: F401


@pytest.fixture(autouse=True)
def _fresh_models():
    cw.forget()
    yield
    cw.forget()


def _owner_asks(cv):
    from mentis.operational import work_overview as wo
    owner = wo.owner_of(cv)
    return owner, sorted(s["expectation"] for s in cv.expectations(of=owner)
                         if not s["response_present"])


# -- one moment ----------------------------------------------------------------

def test_a_moment_does_not_see_what_another_thread_commits_meanwhile(world):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    store = cv._c._store
    count = "SELECT COUNT(*) FROM entry"
    before = store._rows(count)[0][0]
    with store.one_moment():
        first = store._rows(count)[0][0]
        t = threading.Thread(target=lambda: cv.say(cid, owner, [text("x")]))
        t.start()
        t.join(10)
        assert not t.is_alive()
        again = store._rows(count)[0][0]
    after = store._rows(count)[0][0]
    assert first == again == before
    assert after > before                      # and it was committed


def test_a_write_in_a_moment_is_refused_and_nesting_keeps_the_outer_one(world):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    store = cv._c._store
    with store.one_moment():
        with store.one_moment():
            assert store._rows("SELECT 1")[0][0] == 1
        with pytest.raises(WriteWhileReadingBeside):
            cv.say(cid, owner, [text("not here")])
    cv.say(cid, owner, [text("here")])           # and outside it, as ever


def test_settled_computes_once_while_writes_land(world):
    """Before: a write during the computation discarded it, three times,
    and the whole-record `otherwise` answered."""
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    computed, fell_back = [], []

    def compute():
        computed.append(1)
        n = cv._c._store._rows("SELECT COUNT(*) FROM entry")[0][0]
        t = threading.Thread(target=lambda: cv.say(cid, owner, [text("w")]))
        t.start()
        t.join(10)
        return (n, cv._c._store._rows("SELECT COUNT(*) FROM entry")[0][0])

    got = cv._c.settled(compute, lambda: fell_back.append(1))
    assert computed == [1] and not fell_back
    assert got[0] == got[1]                    # one moment throughout


def test_settled_inside_a_write_transaction_still_sees_its_own_appends(world):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    with cv._c.atomic():
        t = cv.say(cid, owner, [text("mine")])
        seen = cv._c.settled(lambda: bool(cv._c.read([t])),
                             lambda: bool(cv._c.read([t])))
    assert seen


# -- Needs You from the kept model, exact now ------------------------------------

def _decision(world, cid, asker):
    cv = world["cv"]
    owner = world["who"]["@brian"]
    q = cv.say(cid, asker, [text("left or right?")], addressed_to=[owner])
    return q, cv.expect(q, of=owner, kind="decision", by=asker)


def test_needs_you_is_what_the_record_says_while_the_model_lags(world):
    from mentis.fluid.home import asking_owner
    cv = world["cv"]
    cid = a_conversation(world)
    asker = cv.create_participant("@Asker", about="an agent")
    _q1, d1 = _decision(world, cid, asker)
    kept = cw.current_work(cv)
    kept.current(wait=True)                    # the model, caught up
    owner, record = _owner_asks(cv)
    assert record and d1 in record
    assert sorted(i for _, i in asking_owner(cv, owner)) == record
    # the record moves; the model is NOT refreshed (no maintainer here)
    q2, d2 = _decision(world, cid, asker)
    say(world, cid, "left", replies_to=_q1, action="record-only")
    _owner, record = _owner_asks(cv)
    assert d2 in record and d1 not in record
    assert kept.owed_now(owner) is not None    # answered from the model
    assert sorted(i for _, i in asking_owner(cv, owner)) == record


def test_owed_now_steps_aside_for_what_the_model_would_rebuild_for(world):
    cv = world["cv"]
    kept = cw.current_work(cv)
    kept.current(wait=True)
    owner, _ = _owner_asks(cv)
    assert kept.owed_now(owner) is not None
    cv.define_persona("Tester", "Check what you are given.")
    assert kept.owed_now(owner) is None        # the record is asked instead


def test_owed_now_without_a_model_says_so():
    class _Nothing:
        _model = None
        _broken = False
    assert cw.CurrentWork.owed_now(_Nothing(), "anyone") is None


# -- a Turn's number ---------------------------------------------------------------

def test_a_turns_number_is_its_rank_and_reads_no_body(world, monkeypatch):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    turns = [cv.say(cid, owner, [text(f"t{i}")]) for i in range(5)]
    expected = {r["turn"]: r["number"] for r in cv.turns(cid)}
    bodies = []
    real = type(cv._c).read
    monkeypatch.setattr(type(cv._c), "read",
                        lambda self, ids, *a, **kw: bodies.extend(
                            i for i in ids if i in turns)
                        or real(self, ids, *a, **kw))
    with cv.reading():
        got = {t: cv.turn_number(t) for t in turns}
    assert got == {t: expected[t] for t in turns}
    assert not bodies                          # no Turn was read in full
