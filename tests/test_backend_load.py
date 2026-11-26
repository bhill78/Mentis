"""The serving path's measured load corrections (2026-11-25).

On the live Brain the current-work maintainer rebuilt the whole model every
15 minutes (~60 s of CPU; beside the owner's reads ~12 of every 15 minutes,
holding the interpreter lock), and `is_finding` decoded every act of a
request's Turn -- megabytes for a run's Turn -- at every step `discovery`
walked. These pin the corrections: no rebuild on a timer, reconciling only
when asked, and `is_finding` answered from the Turn's `work-discovered` acts.
"""
from __future__ import annotations

import time

import pytest

from mentis.conversation import text
from mentis.operational import current_work as cw
from mentis.operational import discovery
from tests._loop import _coordinator, a_conversation, world  # noqa: F401


@pytest.fixture(autouse=True)
def _fresh_models():
    cw.forget()
    yield
    cw.forget()


def _found(world):
    from mentis.web import _surface
    from mentis.worker import _operate
    cid = a_conversation(world)
    _coach, parent, grant = _coordinator(world, cid)
    got = _operate(_surface(world["state"]), "record_discovered_work",
                   {"work": "a side task", "because": "seen on the way"}, grant)
    return cid, parent, got["expectation"]


def test_the_maintainer_never_rebuilds_on_a_timer(world):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    cv.expect(cv.say(cid, owner, [text("w")]), of=None, kind="result",
              by=owner, conversation=cid)
    kept = cw.current_work(cv)
    kept.current(wait=True)
    builds = kept.stats["builds"]
    # as if the model were a day old: before, anything past 15 minutes was
    # rebuilt and compared on the next pass
    kept._model = kept._model.replace(built_at=time.time() - 86_400)
    kept.refresh(wait=True)
    cv.expect(cv.say(cid, owner, [text("more")]), of=None, kind="result",
              by=owner, conversation=cid)
    kept.refresh(wait=True)
    assert kept.stats["builds"] == builds, kept.stats["rebuilt_because"]
    assert kept.stats["reconciled"] == 0
    assert not hasattr(cw, "RECONCILE_S")


def test_reconcile_is_still_there_when_asked(world):
    cv = world["cv"]
    cid, _parent, _found_exp = _found(world)
    kept = cw.current_work(cv)
    kept.current(wait=True)
    assert kept.reconcile() == []
    assert kept.stats["rebuilt_because"].get("reconcile") == 1


def test_is_finding_reads_only_the_turns_discovered_work_acts(world, monkeypatch):
    cv = world["cv"]
    _cid, parent, found = _found(world)
    asked = []
    real = cv._c.operational

    def spy(**kw):
        asked.append(kw)
        return real(**kw)

    monkeypatch.setattr(cv._c, "operational", spy)
    assert cv.is_finding(found) is True
    assert cv.is_finding(parent) is False
    turn_reads = [kw for kw in asked if "turn" in kw]
    # never the whole Turn: each read names the act and the request
    assert turn_reads and all(kw.get("act") == "work-discovered"
                              and kw.get("about") for kw in turn_reads)
    assert discovery(cv, found)["generation"] == 1


def test_is_finding_is_asked_once_per_reading(world, monkeypatch):
    cv = world["cv"]
    _cid, _parent, found = _found(world)
    calls = []
    real = cv._c.operational

    def spy(**kw):
        calls.append(kw)
        return real(**kw)

    monkeypatch.setattr(cv._c, "operational", spy)
    with cv.reading():
        for _ in range(5):
            assert cv.is_finding(found)
    assert len([kw for kw in calls if kw.get("act") == "work-discovered"]) == 1


def test_a_finding_on_a_turn_with_other_acts_is_still_found(world):
    """The SQL narrowing is exact: other acts on the same Turn, including one
    whose detail names the request, never make or unmake a finding."""
    cv = world["cv"]
    cid, parent, found = _found(world)
    turn = cv._act(found)["turn"]
    owner = world["who"]["@brian"]
    # a request on the same Turn that was not kept as discovered work
    plain = cv.expect(turn, of=None, kind="result", by=owner, conversation=cid)
    assert cv.is_finding(found) is True
    assert cv.is_finding(plain) is False
