"""Current work is kept and updated from a cursor, and is exactly the projection.

WHAT MUST HOLD (`operational.current_work`):
  * after every kind of write work goes through -- a request, a delegation
    (which makes the child no trunk), a run's result, a wait on other work and
    that work moving, a decision, a reply, governed material -- the kept
    model is item for item what a full projection computes then;
  * an update projects only the items the writes reached;
  * a reader never waits for an update under way;
  * reconcile finds nothing to repair after a run of writes;
  * `brief` lists outstanding work from the same model; `orient` does not;
  * `work_overview` answers as it did: the same keys, no cursor protocol.

The real record's own writes, replayed in order, are checked the same way by
`C:\\Work\\Mentis-reviews\\timeouts-2026-10-31\\bench\\replay.py`.
"""
from __future__ import annotations

import json
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
    """The kept model brought up to now, filtered to `cid`, against that
    Conversation's current work built from scratch on its own."""
    kept = cw.current_work(cv)
    model = kept.current(wait=True)
    fresh = cw.CurrentWork(cv, cid).current(wait=True).items
    mine = model.of(cid)
    assert set(mine) == set(fresh)
    for tid in fresh:
        assert cw._canon(mine[tid]) == cw._canon(fresh[tid]), tid
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
    assert out["expectation"] not in model.of(cid)
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
    kept = cw.current_work(cv)
    kept.current(wait=True)
    before = kept.stats["projected"]
    cv.record_act(actor=owner, act="expectation-met", conversation=cid,
                  caused_by=asks[2], about=[asks[2]], detail={})
    kept.current(wait=True)
    assert kept.stats["projected"] - before <= 1 + len(kept._time_dependent(kept._model))
    _same_as_full(cv, cid)


def test_a_reader_does_not_wait_for_an_update_under_way(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    t = cv.say(cid, owner, [text("work")])
    cv.expect(t, of=None, kind="result", by=owner, conversation=cid)
    kept = cw.current_work(cv)
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
    kept = cw.current_work(cv)
    kept.current(wait=True)
    # who people are is read by every item: a participant written rebuilds
    # (knowledge does not: `test_ordinary_writes_do_not_rebuild`)
    cv.create_participant("@Newcomer")
    kept.current(wait=True)
    assert "entry participant" in kept.stats["rebuilt_because"]
    t2 = cv.say(cid, owner, [text("more")])
    cv.expect(t2, of=None, kind="result", by=owner, conversation=cid)
    kept.current(wait=True)
    assert kept.reconcile() == []
    assert kept.stats["reconcile_differences"] == 0


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
    kept = cw.current_work(cv)
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
    kept = cw.current_work(cv)
    assert kept.current(wait=True).due[exp] is not None
    time.sleep(1.7)
    before = kept.stats["projected"]
    model = kept.current(wait=True)                # no write since
    assert kept.stats["projected"] > before
    assert model.due[exp] is None                  # projected after its window


def test_a_maintained_model_is_brought_up_by_its_own_thread(world, runs):
    """As the server runs it: built and updated on its thread, never in a
    reader. A reader waits for it to catch up with the record as it stood when
    asked -- briefly -- and is answered from it."""
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    kept = cw.current_work(cv)
    kept.start()
    first = kept.current(wait=True)
    exp = cv.expect(cv.say(cid, owner, [text("after start")]), of=None,
                    kind="result", by=owner, conversation=cid)
    readers = []
    real = kept.refresh

    def counted(**kw):
        readers.append(threading.current_thread().name)
        return real(**kw)
    kept.refresh = counted
    got = kept.current(wait_s=10)
    assert exp in got.of(cid) and got.cursor != first.cursor
    assert readers and set(readers) == {"current-work"}, readers
    _same_as_full(cv, cid)


def test_before_the_first_build_a_reader_is_told_at_once(world, runs):
    from mentis.web import _surface
    cv = world["cv"]
    kept = cw.current_work(cv)
    started = threading.Event()
    real = kept._build

    def slow(why):
        started.set()
        release.wait(10)
        return real(why)
    release = threading.Event()
    kept._build = slow
    kept.start()
    assert started.wait(5)
    try:
        got = _surface(world["state"]).work_overview(a_conversation(world))
        assert got["refused"] and got["not_ready"]
    finally:
        release.set()
    kept.current(wait=True)


def test_a_stopped_maintainer_is_not_waited_on(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    kept = cw.current_work(cv)
    kept.current(wait=True)
    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()
    kept._thread = dead                       # it was started, and has ended
    exp = cv.expect(cv.say(cid, owner, [text("after it stopped")]), of=None,
                    kind="result", by=owner, conversation=cid)
    import time
    t0 = time.monotonic()
    got = kept.current()
    assert time.monotonic() - t0 < 1.5
    assert exp in got.of(cid)


def test_a_brief_says_outstanding_work_is_unknown_not_none(world, runs):
    from mentis.core.orientation import blocks
    text_of = lambda shared: "\n".join(b["text"] for b in blocks(shared, {}))
    shared = {"conversation": "c", "name": "n", "participants": [],
              "outstanding_work": [],
              "outstanding_work_why_not": "being prepared"}
    assert "Outstanding work" in text_of(shared)
    assert "not available yet: being prepared" in text_of(shared)


def test_brief_lists_outstanding_work_from_the_kept_model_and_orient_does_not(
        world, runs):
    from mentis.web import _surface
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    exp = cv.expect(cv.say(cid, owner, [text("brief on this")]), of=None,
                    kind="result", by=owner, conversation=cid)
    s = _surface(world["state"])
    briefed = s.brief(cid, participant=owner, detail=True)
    assert exp in json.dumps(briefed)
    assert "outstanding_work" not in s.orient(cid)


def test_work_overview_answers_as_it_did(world, runs):
    from mentis.web import _surface
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    exp = cv.expect(cv.say(cid, owner, [text("w")]), of=None, kind="result",
                    by=owner, conversation=cid)
    got = _surface(world["state"]).work_overview(cid, limit=5)
    assert set(got) == {"conversation", "counts", "stage_counts",
                        "outstanding_count", "items", "omitted", "limit",
                        "needs_owner_unknown", "needs_owner_why"}
    assert [i["expectation"] for i in got["items"]] == [exp]


# -- second review: the corrections ---------------------------------------------

def test_a_wait_that_ended_and_opens_again_is_heard(world, runs,
                                                    no_time_window):
    """THE BLOCKER (reproduced by the reviewer). T waits on X, a delegated
    child that returns to its asker; X's delivery fails, so T's wait ends; X
    is sent again, so T waits again. The kept item must say so, not keep
    'not started' until reconcile."""
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    ask = lambda w, **kw: cv.expect(cv.say(cid, owner, [text(w)]), of=None,
                                    kind="result", by=owner, conversation=cid,
                                    **kw)
    y = ask("parent y")
    bob = cv.create_participant("@Bob")
    cv.join(bob, cid, attributed_to=owner)
    x = cv.expect(cv.say(cid, owner, [text("child x")], addressed_to=[bob]),
                  of=bob, kind="result", by=owner, caused_by=y,
                  conversation=cid, detail={"returns_to": owner})
    cv.record_act(actor=owner, act="work-delegated", conversation=cid,
                  caused_by=y, about=[x], detail={})
    t = ask("waiting t")
    cv.await_work(t, x, by=owner, because="needs x")
    _same_as_full(cv, cid)
    cv.record_act(actor=bob, act="delivery-failed", conversation=cid,
                  caused_by=x, about=[x], because="no runtime",
                  detail={"before_execution_started": True})
    _same_as_full(cv, cid)
    assert x in cw.current_work(cv).current(wait=True).deps[t]
    cv.record_act(actor=owner, act="work-reassigned", conversation=cid,
                  caused_by=x, about=[x], detail={})
    _same_as_full(cv, cid)


def test_the_model_reads_beside_the_writer(world, runs):
    """A rebuild does not queue behind a write transaction (review)."""
    cv = world["cv"]
    store = cv._c._store
    kept = cw.current_work(cv)
    held, done = threading.Event(), threading.Event()

    def writer():
        with store._lock:                 # another thread's write under way
            held.set()
            done.wait(10)
    w = threading.Thread(target=writer)
    w.start()
    try:
        assert held.wait(5)
        built = threading.Thread(target=lambda: kept.current(wait=True))
        built.start()
        built.join(8)
        assert not built.is_alive(), "the build waited for the writer's lock"
    finally:
        done.set()
        w.join()


def test_work_just_recorded_is_in_a_brief_even_when_the_model_is_behind(
        world, runs):
    from mentis.core.orientation import outstanding
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    kept = cw.current_work(cv)
    kept.current(wait=True)
    assert kept._updating.acquire(timeout=5)       # the maintainer is busy
    try:
        exp = cv.expect(cv.say(cid, owner, [text("just recorded")]), of=None,
                        kind="result", by=owner, conversation=cid)
        got = outstanding(cv, cid)
    finally:
        kept._updating.release()
    first = got["outstanding_work"][0]
    assert first["id"] == exp and first["recorded_since"] is True
    assert first["title"] == "just recorded"
    assert got["outstanding_work_standing"]["behind"] is True


def test_a_failed_update_is_said_and_the_next_refresh_rebuilds(world, runs):
    from mentis.web import _surface
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    kept = cw.current_work(cv)
    kept.current(wait=True)
    real = kept._update

    def broken():
        raise RuntimeError("the record could not be read")
    kept._update = broken
    exp = cv.expect(cv.say(cid, owner, [text("w")]), of=None, kind="result",
                    by=owner, conversation=cid)
    with pytest.raises(RuntimeError):
        kept.refresh(wait=True)
    assert kept.failed and "could not be read" in kept.failed
    said = kept.standing(kept._model, cid)
    assert said["failed"] and said["behind"]
    assert [r["expectation"] for r in said["recorded_since"]] == [exp]
    kept._update = real
    kept.refresh(wait=True)                         # recovers by rebuilding
    assert kept.failed is None
    assert kept.stats["rebuilt_because"].get("after a failure") == 1
    assert exp in kept._model.of(cid)
    assert "standing" not in _surface(world["state"]).work_overview(cid)


def test_ordinary_writes_do_not_rebuild(world, runs, no_time_window):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    cv.expect(cv.say(cid, owner, [text("w")]), of=None, kind="result",
              by=owner, conversation=cid)
    kept = cw.current_work(cv)
    kept.current(wait=True)
    builds = kept.stats["builds"]
    for kind, body in (("note", {"text": "n"}), ("finding", {"text": "f"}),
                       ("lesson", {"text": "l"}),
                       ("outcome", {"text": "o", "result": "done"})):
        cv.corpus.write(kind=kind, attributed_to=owner, body=body)
        kept.current(wait=True)
    assert kept.stats["builds"] == builds, kept.stats["rebuilt_because"]
    _same_as_full(cv, cid)


def test_items_that_asked_git_are_projected_again(world, runs, monkeypatch,
                                                  no_time_window):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    exp = cv.expect(cv.say(cid, owner, [text("w")]), of=None, kind="result",
                    by=owner, conversation=cid)
    kept = cw.current_work(cv)
    model = kept.current(wait=True)
    # as if its stage had asked git (a merge or deploy writes no record)
    kept._model = model.replace(git={exp}, git_at=model.git_at - cw.GIT_S - 1)
    before = kept.stats["projected"]
    kept.current(wait=True)                         # nothing written since
    assert kept.stats["projected"] == before + 1


# -- focused re-review: the three that leave state wrong -------------------------

def test_a_chain_of_waits_is_heard_at_its_end(world, runs, no_time_window):
    """A awaits B awaits C: when C's wait ends and C moves again, A hears it."""
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    ask = lambda w, **kw: cv.expect(cv.say(cid, owner, [text(w)]), of=None,
                                    kind="result", by=owner, conversation=cid,
                                    **kw)
    p = ask("parent p")
    bob = cv.create_participant("@Bob")
    cv.join(bob, cid, attributed_to=owner)
    c = cv.expect(cv.say(cid, owner, [text("child c")], addressed_to=[bob]),
                  of=bob, kind="result", by=owner, caused_by=p,
                  conversation=cid, detail={"returns_to": owner})
    cv.record_act(actor=owner, act="work-delegated", conversation=cid,
                  caused_by=p, about=[c], detail={})
    a, b = ask("a"), ask("b")
    cv.await_work(b, c, by=owner, because="b needs c")
    cv.await_work(a, b, by=owner, because="a needs b")
    _, model = _same_as_full(cv, cid)
    assert c in model.deps[a]
    cv.record_act(actor=bob, act="delivery-failed", conversation=cid,
                  caused_by=c, about=[c], because="no runtime",
                  detail={"before_execution_started": True})
    _, model = _same_as_full(cv, cid)
    # B's wait on C has ended, so B's motion no longer reads C -- but A must
    # still depend on C, or C moving again would not reach A
    assert c in model.deps[a]
    cv.record_act(actor=owner, act="work-reassigned", conversation=cid,
                  caused_by=c, about=[c], detail={})
    _same_as_full(cv, cid)


def test_a_form_answer_rebuilds_so_input_readiness_is_current():
    """Whether an input is given is read from its response set's entries;
    nothing an item read names them, so they rebuild (as before this
    model), never sit placed and unreached."""
    for kind in ("marked-ready", "withdraws", "in-response-set", "answer",
                 "response-set", "responds-to"):
        assert kind in cw.REBUILDS and kind not in cw.PLACED, kind


def test_only_work_of_its_own_is_listed_as_just_recorded(world, runs):
    from mentis.core.orientation import outstanding
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    kept = cw.current_work(cv)
    kept.current(wait=True)
    assert kept._updating.acquire(timeout=5)       # the maintainer is busy
    try:
        parent = cv.expect(cv.say(cid, owner, [text("parent")]), of=None,
                           kind="result", by=owner, conversation=cid)
        child = cv.expect(cv.say(cid, owner, [text("child")]), of=None,
                          kind="result", by=owner, conversation=cid,
                          caused_by=parent)
        cv.record_act(actor=owner, act="work-delegated", conversation=cid,
                      caused_by=parent, about=[child], detail={})
        asked = cv.expect(cv.say(cid, owner, [text("a decision?")]), of=owner,
                          kind="decision", by=owner, conversation=cid,
                          caused_by=parent)
        got = [w["id"] for w in outstanding(cv, cid)["outstanding_work"]
               if w.get("recorded_since")]
    finally:
        kept._updating.release()
    assert parent in got
    assert child not in got and asked not in got
