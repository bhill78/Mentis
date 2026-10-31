"""The read model: one kept model behind every work and obligation route.

WHAT MUST HOLD (`operational.read_model`, Stage 1b):
  * `PythonReadModel` is the frozen `ReadModel` interface;
  * Home's Work, `/api/work` for the owner (Brain-wide, today's Ledger, a
    Conversation's pills), `/api/owed` and a Conversation's `owed` answer
    exactly what the old projection answers, after every kind of write work
    goes through (`tools/work_model_diff.compare`, the check a reviewer runs
    on a Brain copy);
  * those routes project nothing per request;
  * what this process observes of runs, and the executions it holds, move the
    kept items and obligations with no write;
  * an obligation answered and then handed to somebody else is owed again;
  * `since` gives the rows after a cursor; the READ methods answer.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import time
import urllib.request

import pytest

from mentis.conversation import text
from mentis.operational import current_work as cw
from mentis.operational import read_model as rm
from mentis.operational import work_overview as wo
from tests._loop import a_conversation, world  # noqa: F401
from tests._loop import runs  # noqa: F401
from tests.test_delegate_coordinate import _delegate, _present, _run_of

_TOOL = pathlib.Path(__file__).resolve().parents[1] / "tools" / "work_model_diff.py"
_spec = importlib.util.spec_from_file_location("work_model_diff", _TOOL)
diff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diff)


@pytest.fixture(autouse=True)
def _fresh_models():
    cw.forget()
    yield
    cw.forget()


def _get(world, path):
    req = urllib.request.Request(world["base"] + path,
                                 headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def _observe(world):
    from mentis.web import _runtime_observation
    return lambda: _runtime_observation(world["state"])


def _busy(world, runs):
    """Work going through every kind of write: a run and its result, a
    delegation dispatched, a wait on other work and that work met, a reply, a
    decision asked of the owner."""
    import mentis.web as web
    cv = world["cv"]
    owner = world["who"]["@brian"]
    run = _run_of(world, runs, "gesture")
    cid = run["cid"]
    turn = cv.say(cid, owner, [text("please also do this")])
    second = cv.expect(turn, of=None, kind="result", by=owner,
                       conversation=cid)
    bob = _present(world, cid, "@Bob")
    out = _delegate(world, run["grant"], participant=bob, work="a part")
    web.dispatch_soon(world["state"], conversation=out["conversation"],
                      turn=out["turn"], participant=bob, work="a part",
                      expectation=out["expectation"])
    cv.await_work(run["grant"]["expectation"], second,
                  by=run["grant"]["participant"], because="needs it first")
    cv.record_act(actor=owner, act="expectation-met", conversation=cid,
                  caused_by=second, about=[second], detail={"met_by": "owner"})
    cv.say(cid, owner, [text("a reply")], replies_to=turn)
    asked = cv.expect(cv.say(cid, bob, [text("which way?")]), of=owner,
                      kind="decision", by=bob, conversation=cid)
    return {"cid": cid, "owner": owner, "bob": bob, "asked": asked,
            "second": second}


def test_the_python_read_model_is_the_frozen_interface(world):
    got = rm.read_model(world["state"])
    assert isinstance(got, rm.ReadModel)
    for name in ("work_items", "owed", "stands_many", "conversation_summary",
                 "topics", "find", "since"):
        assert getattr(rm.ReadModel, name).__doc__, name


def test_every_kept_read_is_the_old_projection(world, runs):
    _busy(world, runs)
    got = diff.compare(world["cv"], _observe(world), conversations=3)
    assert got["equal"], [c for c in got["checks"] if not c["equal"]]
    reads = {c["read"].split("?")[0] for c in got["checks"]}
    assert {"/api/work", "/fluid/api/home/work", "/api/owed"} <= reads
    assert any(r.endswith("owed") and "batch=0" in r for r in
               (c["read"] for c in got["checks"]))


def test_the_routes_answer_from_the_kept_model_and_project_nothing(
        world, runs, monkeypatch):
    from mentis.web import _runtime_observation
    w = _busy(world, runs)
    cv, st, cid, owner = world["cv"], world["state"], w["cid"], w["owner"]
    # nothing re-projected for being recent: what is projected now is what a
    # route asked for
    monkeypatch.setattr(cw, "_window", lambda item, at: None)
    rm.read_model(st)._kept.current(wait=True)        # built, as a server has
    projected = []
    real = wo.project
    monkeypatch.setattr(wo, "project", lambda *a, **k: (
        projected.append(1), real(*a, **k))[1])
    home = _get(world, "/fluid/api/home/work")
    work = _get(world, "/api/work")
    pills = _get(world, f"/api/work?viewer={owner}&conversation={cid}")
    owed = _get(world, f"/api/owed?participant={owner}&limit=50")
    facts = _get(world, f"/api/conversations/{cid}?batch=0")
    assert projected == [], "a route projected work again"
    monkeypatch.setattr(wo, "project", real)
    runtime = _runtime_observation(st)
    with cv.reading():
        old_work = wo.overview(cv, viewer=owner, runtime=runtime)
        old_pills = wo.overview(cv, viewer=owner, runtime=runtime,
                                conversation=cid)
        old_home = diff.OLD_HOME_WORK(cv, runtime)
        from mentis.operational.work import owed_by
        old_owed = owed_by(cv, owner, limit=50)
        old_facts = [o["expectation"] for o in
                     cv.expectations(conversation=cid, open_only=True)
                     if not o["response_present"]]
    canon = lambda x: json.loads(json.dumps(x, default=str))  # noqa: E731
    assert canon(work) == canon(old_work)
    assert canon(pills) == canon(old_pills)
    assert {k: v for k, v in home.items() if k != "cursor"} == {
        k: v for k, v in canon(old_home).items() if k != "cursor"}
    assert canon(owed) == canon(old_owed)
    assert w["asked"] in [o["expectation"] for o in owed["owed"]]
    assert [o["expectation"] for o in facts["owed"]] == old_facts
    assert w["asked"] in old_facts


def test_another_viewer_is_still_projected_for_them(world, runs):
    w = _busy(world, runs)
    got = _get(world, f"/api/work?viewer={w['bob']}&conversation={w['cid']}")
    assert got["viewer"] == w["bob"]


def test_what_this_process_observes_moves_items_with_no_write(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    exp = cv.expect(cv.say(cid, owner, [text("running?")]), of=owner,
                    kind="result", by=owner, conversation=cid)
    start = cv.record_act(actor=owner, act="execution-started",
                          conversation=cid, caused_by=exp, execution="x-1",
                          because="started by hand", detail={})
    seen = {"runtime": {"runs": {}, "instances": {}, "why_not": None}}
    kept = cw.current_work(cv, observe=lambda: seen["runtime"])
    model = kept.current(wait=True)
    assert exp in model.rt
    before = model.items[exp]
    now = time.time()
    seen["runtime"] = {"runs": {start: {"opened_at": now,
                                        "performing_since": now,
                                        "running": True,
                                        "last_event": {"what": "a tool",
                                                       "at": now}}},
                       "instances": {"x-1": "busy"}, "why_not": None}
    cursor = model.cursor
    model = kept.current(wait=True)
    assert model.cursor == cursor                     # nothing was written
    assert model.items[exp] != before
    with cv.reading():
        fresh = wo.project(wo._Ctx(cv), cv._act(exp), viewer=owner,
                           runtime=seen["runtime"])
    fresh.pop("_seen"), fresh.pop("_awaits")
    assert cw._canon(model.items[exp]) == cw._canon(fresh)
    # only what the observation can move was projected again
    unmoved = cv.expect(cv.say(cid, owner, [text("idle")]), of=None,
                        kind="result", by=owner, conversation=cid)
    model = kept.current(wait=True)
    assert unmoved not in model.rt


def test_an_execution_held_here_moves_its_obligation(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    bob = cv.create_participant("@Holder")
    cv.join(bob, cid, attributed_to=owner)
    exp = cv.expect(cv.say(cid, owner, [text("for bob")]), of=bob,
                    kind="result", by=owner, conversation=cid)
    kept = cw.current_work(cv)
    assert kept.current(wait=True).states[exp]["live_execution"] == []
    ex = cv.begin_execution(participant=bob, conversation=cid,
                            for_expectation=exp)
    model = kept.current(wait=True)
    assert model.states[exp]["live_execution"] == [ex.reference]
    assert cw._canon(model.states[exp]) == cw._canon(
        cv.expectation_state(exp))
    cv.end_execution(ex.reference)
    assert kept.current(wait=True).states[exp]["live_execution"] == []


def test_an_answered_obligation_handed_on_is_owed_again(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    bob = cv.create_participant("@Answerer")
    carol = cv.create_participant("@Next")
    for p in (bob, carol):
        cv.join(p, cid, attributed_to=owner)
    turn = cv.say(cid, owner, [text("answer me")])
    exp = cv.expect(turn, of=bob, kind="result", by=owner, conversation=cid)
    model_of = rm.read_model(world["state"])
    assert exp in [s["expectation"] for s in model_of.owed(
        rm.Scope(participant=bob)).rows]
    cv.say(cid, bob, [text("here")], replies_to=turn)
    assert exp not in [s["expectation"] for s in model_of.owed().rows]
    cv.assign(exp, carol, by=owner, because="carol takes it")
    rows = model_of.owed(rm.Scope(participant=carol)).rows
    assert [s["expectation"] for s in rows] == [exp]
    assert cw._canon(rows[0]) == cw._canon(cv.expectation_state(exp))
    assert model_of._kept.reconcile() == []


def test_since_and_the_read_methods(world):
    cv = world["cv"]
    m = rm.read_model(world["state"])
    cid = a_conversation(world)
    at = cw.cursor_text(cv._c._store.advance())
    owner = world["who"]["@brian"]
    turn = cv.say(cid, owner, [text("a findable sentence")])
    topic = cv.open_topic(cid, "Lookup target")
    got = m.since(at)
    assert any(e[0] == turn for e in got.entries)
    assert m.since(got.cursor).entries == () or all(
        e[0] not in (turn, topic) for e in m.since(got.cursor).entries)
    with pytest.raises(ValueError):
        m.since("not a cursor")
    assert m.topics("#lookup") == [{"id": topic, "name": "Lookup target",
                                    "conversation": cid}]
    assert m.topics("") == []
    assert m.stands_many([turn, "ent-000000000000"])["ent-000000000000"] is None
    assert m.conversation_summary([cid])[cid]["id"] == cid
    found = m.find("findable sentence", kinds=["turn"])
    assert [r["ref"] for r in found.found] == [turn]
    assert found.kinds == ("turn",) and isinstance(found.not_searched, tuple)


def test_an_observation_that_keeps_moving_is_not_waited_out(world, runs):
    """Maintained, as served: a reader waits for a pass that observed the
    runs after it asked, not for a signature that never holds still."""
    import itertools
    cv = world["cv"]
    n = itertools.count()
    kept = cw.current_work(cv, observe=lambda: {
        "runs": None, "instances": None, "why_not": f"flapping {next(n)}"})
    kept.start()
    kept.current(wait=True)
    t0 = time.monotonic()
    for _ in range(3):
        kept.current()
    assert time.monotonic() - t0 < cw.WAIT_S, "a reader waited out WAIT_S"
