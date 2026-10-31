"""Current work is kept and updated from a cursor, and is exactly the projection.

WHAT MUST HOLD (`operational.current_work`):
  * after every kind of write work goes through -- a request, a delegation
    (which makes the child no trunk), a run's result, a wait on other work and
    that work moving, a decision, a reply, governed material -- the kept
    model is item for item what a full projection computes then;
  * an update projects only the items the writes reached;
  * `since` gives only what changed after a cursor, an item no longer current
    as removed, and the next cursor; a cursor not given here is refused;
  * a reader never waits for an update under way;
  * reconcile finds nothing to repair after a run of writes;
  * `orient` lists outstanding work from the same model.

The real record's own writes, replayed in order, are checked the same way by
`C:\\Work\\Mentis-reviews\\timeouts-2026-10-31\\bench\\replay.py`.
"""
from __future__ import annotations

import threading

import pytest

from mentis.conversation import text
from mentis.operational import current_work as cw
from tests._loop import a_conversation, say, world  # noqa: F401
from tests._loop import runs  # noqa: F401
from tests.test_delegate_coordinate import _delegate, _present, _run_of


@pytest.fixture(autouse=True)
def _fresh_models():
    cw.forget()
    yield
    cw.forget()


def _same_as_full(cv, cid):
    """The kept model brought up to now, against a model built from scratch."""
    kept = cw.current_work(cv, cid)
    model = kept.current(wait=True)
    full = cw.CurrentWork(cv, cid)
    fresh = full.current(wait=True)
    assert set(model.items) == set(fresh.items)
    for tid in fresh.items:
        assert cw._canon(model.items[tid]) == cw._canon(fresh.items[tid]), tid
    return kept, model


def test_every_kind_of_write_leaves_the_model_equal_to_a_full_projection(
        world, runs):
    import mentis.web as web
    cv = world["cv"]
    run = _run_of(world, runs, "gesture")
    cid = run["cid"]
    kept, model = _same_as_full(cv, cid)
    assert kept.stats["builds"] == 1
    # a request
    turn = cv.say(cid, world["who"]["@brian"], [text("please also do this")])
    second = cv.expect(turn, of=None, kind="result", by=world["who"]["@brian"],
                       conversation=cid)
    _same_as_full(cv, cid)
    # a delegation: the child is under the run's request, not a trunk
    bob = _present(world, cid, "@Bob")
    out = _delegate(world, run["grant"], participant=bob, work="a part")
    web.dispatch_soon(world["state"], conversation=out["conversation"],
                      turn=out["turn"], participant=bob, work="a part",
                      expectation=out["expectation"])
    _, model = _same_as_full(cv, cid)
    assert out["expectation"] not in model.items
    # waiting on other work, and that work moving
    cv.await_work(run["grant"]["expectation"], second,
                  by=run["grant"]["participant"], because="needs it first")
    _same_as_full(cv, cid)
    cv.record_act(actor=world["who"]["@brian"], act="expectation-met",
                  conversation=cid, caused_by=second, about=[second],
                  detail={"met_by": "owner"})
    _same_as_full(cv, cid)
    # a reply in the Conversation
    cv.say(cid, world["who"]["@brian"], [text("a reply")], replies_to=turn)
    _same_as_full(cv, cid)
    # and the Brain-wide model, kept the same way
    _same_as_full(cv, None)
    # updated, not rebuilt -- except for creating @Bob: a participant written
    # rebuilds; bringing them into the Conversation does not
    assert set(kept.stats["rebuilt_because"]) == {"first", "entry participant"}, kept.stats


def test_an_update_projects_only_what_the_writes_reached(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    asks = []
    for i in range(5):
        t = cv.say(cid, owner, [text(f"request {i}")])
        asks.append(cv.expect(t, of=None, kind="result", by=owner,
                              conversation=cid))
    kept = cw.current_work(cv, cid)
    kept.current(wait=True)
    before = kept.stats["projected"]
    cv.record_act(actor=owner, act="expectation-met", conversation=cid,
                  caused_by=asks[2], about=[asks[2]], detail={})
    kept.current(wait=True)
    assert kept.stats["projected"] - before <= 1 + len(kept._time_dependent(kept._model))
    _same_as_full(cv, cid)


def test_since_gives_only_what_changed_after_a_cursor(world, runs):
    from mentis.web import _surface
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    s = _surface(world["state"])
    t = cv.say(cid, owner, [text("first")])
    first = cv.expect(t, of=None, kind="result", by=owner, conversation=cid)
    whole = s.work_overview(cid)
    assert first in [i["expectation"] for i in whole["items"]]
    cursor = whole["cursor"]
    nothing = s.work_overview(cid, since=cursor)
    assert nothing["items"] == [] and nothing["changed_since"] == cursor
    assert nothing["counts"] == whole["counts"]       # counts are always whole
    t2 = cv.say(cid, owner, [text("second")])
    second = cv.expect(t2, of=None, kind="result", by=owner, conversation=cid)
    moved = s.work_overview(cid, since=cursor)
    assert [i["expectation"] for i in moved["items"]] == [second]
    assert moved["cursor"] != cursor
    assert s.work_overview(cid, since=moved["cursor"])["items"] == []
    refused = s.work_overview(cid, since="yesterday")
    assert refused["refused"] is True and "cursor" in refused["why_not"]


def test_a_reader_does_not_wait_for_an_update_under_way(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    t = cv.say(cid, owner, [text("work")])
    cv.expect(t, of=None, kind="result", by=owner, conversation=cid)
    kept = cw.current_work(cv, cid)
    first = kept.current(wait=True)
    t2 = cv.say(cid, owner, [text("more")])
    cv.expect(t2, of=None, kind="result", by=owner, conversation=cid)
    assert kept._updating.acquire(timeout=5)        # an update is under way
    try:
        got = []
        reader = threading.Thread(target=lambda: got.append(kept.current()))
        reader.start()
        reader.join(5)
        assert not reader.is_alive(), "a reader waited for the update"
        assert got[0].cursor == first.cursor        # as it stood, said so
    finally:
        kept._updating.release()
    assert kept.current().cursor != first.cursor


def test_governed_material_rebuilds_and_reconcile_finds_nothing(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    t = cv.say(cid, owner, [text("work")])
    cv.expect(t, of=None, kind="result", by=owner, conversation=cid)
    kept = cw.current_work(cv, cid)
    kept.current(wait=True)
    cv.corpus.write(kind="lesson", attributed_to=owner,
                    body={"text": "a lesson"})
    kept.current(wait=True)
    assert any(k.startswith("entry") for k in kept.stats["rebuilt_because"])
    t2 = cv.say(cid, owner, [text("more")])
    cv.expect(t2, of=None, kind="result", by=owner, conversation=cid)
    kept.current(wait=True)
    assert kept.reconcile() == []
    assert kept.stats["reconcile_differences"] == 0


def test_orient_lists_outstanding_work_from_the_kept_model(world, runs):
    from mentis.web import _surface
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    t = cv.say(cid, owner, [text("orient on this")])
    exp = cv.expect(t, of=None, kind="result", by=owner, conversation=cid)
    got = _surface(world["state"]).orient(cid)
    assert exp in [w["id"] for w in got["outstanding_work"]]
    assert cw.current_work(cv, cid).stats["builds"] == 1


# -- review findings ------------------------------------------------------------

@pytest.fixture()
def no_time_window(monkeypatch):
    """Nothing re-projected for being recent: what an update reaches must be
    reached by what was written, or the miss shows."""
    monkeypatch.setattr(cw, "_window", lambda item, at: None)


def test_two_items_awaiting_the_same_work_both_hear_it_move(world, runs,
                                                            no_time_window):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    ask = lambda words: cv.expect(cv.say(cid, owner, [text(words)]), of=None,
                                  kind="result", by=owner, conversation=cid)
    a, b, x = ask("a"), ask("b"), ask("x")
    cv.await_work(a, x, by=owner, because="needs x")
    cv.await_work(b, x, by=owner, because="needs x")
    kept = cw.current_work(cv, cid)
    model = kept.current(wait=True)
    assert x in model.deps[a] and x in model.deps[b]
    cv.record_act(actor=owner, act="expectation-met", conversation=cid,
                  caused_by=x, about=[x], detail={})
    _same_as_full(cv, cid)


def test_an_item_read_inside_its_time_window_is_projected_again_after_it(
        world, runs, monkeypatch):
    import time
    from mentis.operational import stage
    monkeypatch.setattr(stage, "RESUME_GRACE_S", 0.5)
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    exp = cv.expect(cv.say(cid, owner, [text("w")]), of=None, kind="result",
                    by=owner, conversation=cid)
    kept = cw.current_work(cv, cid)
    assert kept.current(wait=True).due[exp] is not None
    time.sleep(1.7)
    before = kept.stats["projected"]
    model = kept.current(wait=True)                # no write since
    assert kept.stats["projected"] > before
    assert model.due[exp] is None                  # projected after its window


def test_a_removal_is_still_said_after_a_rebuild(world, runs, no_time_window):
    from mentis.web import _surface
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    s = _surface(world["state"])
    parent = cv.expect(cv.say(cid, owner, [text("parent")]), of=None,
                       kind="result", by=owner, conversation=cid)
    child = cv.expect(cv.say(cid, owner, [text("child")]), of=None,
                      kind="result", by=owner, conversation=cid,
                      caused_by=parent)
    cursor = s.work_overview(cid)["cursor"]
    assert child in cw.current_work(cv, cid).current().items
    # handed on under the parent: no longer a trunk of its own
    cv.record_act(actor=owner, act="work-delegated", conversation=cid,
                  caused_by=parent, about=[child], detail={})
    s.work_overview(cid)
    cv.create_participant("@Someone")                # a rebuild
    got = s.work_overview(cid, since=cursor)
    assert {"expectation": child, "removed": True} in got["items"]
    assert "resync" not in got
    _same_as_full(cv, cid)


def test_cursors_from_before_the_model_or_ahead_of_the_record(world, runs):
    from mentis.web import _surface
    cv = world["cv"]
    cid = a_conversation(world)
    s = _surface(world["state"])
    born = s.work_overview(cid)["cursor"]
    old = s.work_overview(cid, since="0.0.0")
    assert old["resync"] and old["changed_since"] is None
    ahead = ".".join(str(int(x) + 10) for x in born.split("."))
    assert s.work_overview(cid, since=ahead)["refused"] is True
