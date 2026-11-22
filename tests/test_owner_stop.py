"""The owner's stop is authoritative (owner instruction 2026-11-22).

"Once the owner stops a Work, no existing agent, pending return, retry, or
automatic continuation can restart it without fresh owner authorization."

What happened before this: the owner stopped a Work's running run; the stopped
child counted as returned; the carrier was resumed because nothing it waited on
was outstanding; and it delegated a recovery of the very run the owner stopped.

Checked through the owner's stop door (`POST /api/work/<request>/stop`), the real
`delegate` operation, the real dispatch path and the real resumption; only the
runs are scripted (`tests/_loop.runs`: every run ends at once).
"""

from __future__ import annotations

import pytest

from tests._loop import a_conversation, post, say, world  # noqa: F401
from tests._loop import runs  # noqa: F401


def _delegate(world, grant, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), "delegate", args, grant)


def _dispatch(world, spec, expectation, conversation, turn):
    from mentis.web import dispatch as D
    return D.dispatch(world["state"], conversation=conversation,
                      turn=spec.get("turn") or turn,
                      participant=spec["participant"], work=spec["work"],
                      expectation=expectation, **{k: spec[k] for k in
                                                  ("persona", "runtime", "model",
                                                   "effort", "requires")
                                                  if spec.get(k)})


def _acts(world, exp, name):
    return [a for a in world["cv"].history(caused_by=exp) if a["act"] == name]


def _stop(world, exp, because="stop this work"):
    return post(world, f"/api/work/{exp}/stop", {"because": because})


@pytest.fixture()
def held(world, runs, monkeypatch):
    """@Ada carries work the owner asked for; dispatches she causes are HELD,
    not run, so a test decides when a queued dispatch fires."""
    import mentis.web as web
    queued: list[dict] = []
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: queued.append(kw))
    cv = world["cv"]
    cid = a_conversation(world)
    from mentis.web import dispatch as D
    asked = say(world, cid, "@Ada do the work", action="ask-participant",
                dispatch=[{"participant": world["who"]["@Ada"], "work": "do it"}])
    top = asked["expectations"][0]
    D.dispatch(world["state"], **queued.pop())          # Ada's first run
    return {"cid": cid, "top": top, "grant": runs[-1], "queued": queued,
            "bob": cv.create_participant("@Bob"), "turn": asked["turn"]}


def test_the_stop_door_records_the_owner_stop_and_nothing_else(world, held):
    cv, h = world["cv"], held
    out = _stop(world, h["top"], "deferred; no more corrections")
    assert out["ok"] is True and out["request"] == h["top"]
    parks = _acts(world, h["top"], "work-parked")
    assert [p["id"] for p in parks] == [out["parked"]]
    assert parks[0]["actor"] == world["who"]["@brian"]
    assert parks[0]["because"] == "deferred; no more corrections"
    # NOT ACCEPTANCE: the work stays open and unfinished.
    assert not cv.expectation_state(h["top"])["satisfied_by"]


def test_a_coordinator_cannot_delegate_after_the_stop(world, held):
    from mentis.worker import NotPermitted
    h = held
    _stop(world, h["top"])
    with pytest.raises(NotPermitted, match="stopped this work"):
        _delegate(world, h["grant"], participant=h["bob"], work="recover it",
                  return_to_me=True)


def test_a_queued_child_dispatch_arriving_after_the_stop_starts_nothing(world, held):
    h = held
    out = _delegate(world, h["grant"], participant=h["bob"], work="the part",
                    return_to_me=True)
    _stop(world, h["top"])
    got = _dispatch(world, out["dispatch"], out["expectation"], h["cid"], out["turn"])
    assert got["ok"] is False and got["before_execution_started"] is True
    assert _acts(world, out["expectation"], "execution-started") == []
    failed = _acts(world, out["expectation"], "delivery-failed")
    assert failed[-1]["detail"]["stage"] == "work-stopped-by-owner"
    assert "stopped this work" in failed[-1]["because"]


def test_a_child_that_ends_after_the_stop_does_not_resume_its_carrier(
        world, held, monkeypatch):
    """The failure the owner met: a stopped, cancelled or failed child ends, and
    the carrier is resumed because nothing it waited on is outstanding."""
    from mentis.web import dispatch as D
    h = held
    out = _delegate(world, h["grant"], participant=h["bob"], work="the part",
                    return_to_me=True)
    # The child runs and ends; its end is handled only after the stop lands.
    ends = []
    monkeypatch.setattr(D, "resume_if_ready", lambda st, exp: ends.append(exp) or [])
    _dispatch(world, out["dispatch"], out["expectation"], h["cid"], out["turn"])
    assert _acts(world, out["expectation"], "execution-started")
    monkeypatch.undo()
    before = len(_acts(world, h["top"], "execution-started"))
    _stop(world, h["top"])

    made = D.resume_if_ready(world["state"], ends[0])

    assert made == []
    assert _acts(world, h["top"], "work-resumed") == []
    assert len(_acts(world, h["top"], "execution-started")) == before
    assert h["queued"] == []


def test_a_resume_already_queued_before_the_stop_is_refused_when_it_fires(
        world, held):
    from mentis.web import dispatch as D
    h = held
    out = _delegate(world, h["grant"], participant=h["bob"], work="the part",
                    return_to_me=True)
    # The child runs and ends before the stop: the carrier's resumption is
    # recorded and its dispatch queued.
    _dispatch(world, out["dispatch"], out["expectation"], h["cid"], out["turn"])
    assert _acts(world, h["top"], "work-resumed")
    resume = h["queued"].pop()
    before = len(_acts(world, h["top"], "execution-started"))
    _stop(world, h["top"])

    got = D.dispatch(world["state"], **resume)

    assert got["ok"] is False
    assert len(_acts(world, h["top"], "execution-started")) == before


def test_an_old_delegation_is_not_recovered_at_server_start(world, held):
    from mentis.web import dispatch as D
    h = held
    out = _delegate(world, h["grant"], participant=h["bob"], work="the part",
                    return_to_me=True)
    _stop(world, h["top"])
    d = next(a for a in world["cv"].history(caused_by=h["top"])
             if a["act"] == "work-delegated")
    assert D._why_not_recover(world["cv"], d, out["expectation"], 0) == \
        "owner-stopped-work"


def test_the_stop_asks_every_live_run_of_the_work_and_under_it_to_stop(
        world, held, monkeypatch):
    cv, st, h = world["cv"], world["state"], held
    child = _delegate(world, h["grant"], participant=h["bob"], work="the part",
                      return_to_me=True)["expectation"]
    other = say(world, a_conversation(world, "Elsewhere"), "@Ada other work",
                action="ask-participant",
                dispatch=[{"participant": world["who"]["@Ada"], "work": "x"}]
                )["expectations"][0]
    live = [{"id": "opr-run-top", "caused_by": h["top"]},
            {"id": "opr-run-child", "caused_by": child},
            {"id": "opr-run-other", "caused_by": other}]
    monkeypatch.setattr(type(cv), "open_runs", lambda self, **kw: live)
    halted = []
    monkeypatch.setattr(st.agents, "agents_halt_run",
                        lambda run, by, why: halted.append(run) or True)
    out = _stop(world, h["top"])
    assert sorted(halted) == ["opr-run-child", "opr-run-top"]
    assert {r["run"] for r in out["runs"]} == {"opr-run-top", "opr-run-child"}
    # the park is written BEFORE any run is asked to stop
    stops = [a for a in cv._c.operational(act="execution-stop-asked")
             if a["caused_by"] in ("opr-run-top", "opr-run-child")]
    assert len(stops) == 2
    assert all(s["at"] >= _acts(world, h["top"], "work-parked")[0]["at"] for s in stops)


def test_only_a_newer_owner_request_continues_the_work(world, held):
    from mentis.operational.owner_stop import parked_over
    from mentis.web import dispatch as D
    cv, h = world["cv"], held
    _stop(world, h["top"])
    assert parked_over(cv, h["top"])
    # The owner's newer request continuing it is fresh authority: it starts,
    # and what its carrier hands on under it may start too.
    cont = say(world, h["cid"], "@Ada continue, narrowly", action="ask-participant",
               replies_to=h["turn"],
               dispatch=[{"participant": world["who"]["@Ada"], "work": "continue"}])
    new = cont["expectations"][0]
    assert parked_over(cv, new) is None
    D.dispatch(world["state"], **h["queued"].pop())
    assert _acts(world, new, "execution-started"), "the owner's continuation did not start"
    # ...while the stopped request itself still does not resume.
    assert parked_over(cv, h["top"])


def test_other_work_is_not_affected(world, held):
    from mentis.operational.owner_stop import parked_over
    h = held
    _stop(world, h["top"])
    other = say(world, a_conversation(world, "Elsewhere"), "@Ada other work",
                action="ask-participant",
                dispatch=[{"participant": world["who"]["@Ada"], "work": "x"}])
    exp = other["expectations"][0]
    assert parked_over(world["cv"], exp) is None
    from mentis.web import dispatch as D
    D.dispatch(world["state"], **h["queued"].pop())
    assert _acts(world, exp, "execution-started")


def test_an_agent_cannot_use_the_stop_door(world, held):
    import json, urllib.request, urllib.error
    h = held
    grant = world["state"].agents.authority._grant("fixture-worker",
                                                   world["state"].path)
    req = urllib.request.Request(
        world["base"] + f"/api/work/{h['top']}/stop",
        data=json.dumps({"because": "an agent stopping work"}).encode(),
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1",
                 "X-Mentis-Worker": grant}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(req)
    assert refused.value.code == 403
    assert _acts(world, h["top"], "work-parked") == []


# -- found by independent review ------------------------------------------------

def _park(world, exp):
    from mentis.operational.stage import WORK_PARKED
    cv = world["cv"]
    a = cv._act(exp)
    return cv.record_act(actor=world["who"]["@brian"], act=WORK_PARKED,
                         conversation=a["conversation"], turn=a["turn"],
                         caused_by=exp, about=[exp], because="stopped")


def test_a_stop_landing_between_the_start_and_the_run_is_still_enforced(
        world, held, runs, monkeypatch):
    """The start is written, then the stop lands before the cancel can be armed
    (so no cancel can reach the run yet): through the REAL halt and perform,
    nothing is sent to the runtime and the run ends as cancelled."""
    st, h = world["state"], held
    out = _delegate(world, h["grant"], participant=h["bob"], work="the part",
                    return_to_me=True)
    opened = st.agents.agents_open_run

    def open_then_stop(instance, started):
        opened(instance, started)
        _park(world, h["top"])                    # the owner's stop, in the gap

    monkeypatch.setattr(st.agents, "agents_open_run", open_then_stop)
    before = len(runs)
    _dispatch(world, out["dispatch"], out["expectation"], h["cid"], out["turn"])
    assert len(runs) == before, "the runtime was sent the work after the stop"
    started = _acts(world, out["expectation"], "execution-started")
    assert len(started) == 1
    ended = [a for a in world["cv"].history(caused_by=started[0]["id"])
             if a["act"] in ("delivery-failed", "result-returned")]
    assert ended and "cancel" in (ended[-1]["because"] or "").lower(), ended
    asked = [a for a in world["cv"]._c.operational(act="execution-stop-asked")
             if a["caused_by"] == started[0]["id"]]
    assert asked and asked[0]["detail"]["work_parked"]


def test_a_held_stop_reaches_a_run_the_cancel_could_not_reach_yet(world, held, runs,
                                                                   monkeypatch):
    """The stop door's own halt, landing before the cancel is armed and after
    dispatch's last check: held on the run, and nothing is sent."""
    from mentis.web import dispatch as D
    st, h = world["state"], held
    out = _delegate(world, h["grant"], participant=h["bob"], work="the part",
                    return_to_me=True)
    opened = st.agents.agents_open_run

    def open_then_halt(instance, started):
        opened(instance, started)
        assert st.agents.agents_halt_run(started, by="owner", why="stopped") is True

    monkeypatch.setattr(st.agents, "agents_open_run", open_then_halt)
    before = len(runs)
    _dispatch(world, out["dispatch"], out["expectation"], h["cid"], out["turn"])
    assert len(runs) == before, "the runtime was sent the work after the stop"


def test_a_follow_up_is_not_handed_to_or_from_stopped_work(world, held):
    cv, h = world["cv"], held
    other = say(world, h["cid"], "@Ada another thing", action="ask-participant",
                dispatch=[{"participant": world["who"]["@Ada"], "work": "y"}]
                )["expectations"][0]
    _park(world, h["top"])
    for request, work in ((h["top"], other), (other, h["top"])):
        out = cv.attach_follow_up(request, work, by=world["who"]["@Ada"])
        assert "stopped this work" in out.get("error", ""), out
    assert not cv.expectation_state(h["top"])["satisfied_by"]


def test_a_stop_holds_even_when_the_clock_was_set_back(world, held, monkeypatch):
    """Order is the record's append order: a park written after the request
    holds although its wall-clock time is earlier."""
    import time as _time
    from mentis.operational.owner_stop import parked_over
    h = held
    then = world["cv"]._act(h["top"])["at"] - 3600
    monkeypatch.setattr(_time, "time", lambda: then)
    _park(world, h["top"])
    monkeypatch.undo()
    assert parked_over(world["cv"], h["top"])


def test_a_stop_recorded_after_the_cancel_is_armed_still_sends_nothing(
        world, held, runs, monkeypatch):
    """The re-review's interleaving: every earlier check passed and the cancel
    is armed (`expect`), then the owner's stop is recorded before the run
    begins. The begin decision reads the record under the halt's lock, so
    nothing is sent; what `expect` armed is let go."""
    st, h = world["state"], held
    out = _delegate(world, h["grant"], participant=h["bob"], work="the part",
                    return_to_me=True)
    ex = st.agents.execution
    armed, released = [], []

    def expect(run_id):
        armed.append(run_id)
        _park(world, h["top"])                  # after arming, before beginning

    monkeypatch.setattr(ex, "expect", expect, raising=False)
    monkeypatch.setattr(ex, "unexpect", released.append, raising=False)
    before = len(runs)
    _dispatch(world, out["dispatch"], out["expectation"], h["cid"], out["turn"])
    assert armed, "the run never reached the begin decision"
    assert len(runs) == before, "the runtime was sent the work after the stop"
    assert released == armed
    started = _acts(world, out["expectation"], "execution-started")
    ended = [a for a in world["cv"].history(caused_by=started[0]["id"])
             if a["act"] in ("delivery-failed", "result-returned")]
    assert ended and "cancel" in (ended[-1]["because"] or "").lower(), ended


def test_a_run_that_began_before_the_stop_is_cancelled_as_a_running_run(world, held):
    """Once `agents_perform` marked it performing, a halt is the ordinary
    cancel of a running run, not a held stop."""
    svc = world["state"].agents
    svc._runs["opr-x"] = {"instance": "i-x", "performing": True}
    asked = []
    svc.execution.cancel = lambda rid: asked.append(rid) or True
    assert svc.agents_halt_run("opr-x", by="owner", why="stop") is True
    assert asked == ["i-x"] and not svc._runs["opr-x"]["stop"].get("held")
