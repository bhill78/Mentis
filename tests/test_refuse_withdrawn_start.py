"""A run is not started on a request that has been withdrawn (owner decision 7,
ent-750df9aa168c; defects ent-730e33101b96 and ent-a175acd8dc29).

Exactly that: a START on a WITHDRAWN request. Answers, questions and resumes on
a closed request, and whether deleting a request withdraws it, are undecided
and not ruled on here.

The refusal writes what every other failure before a start writes -- one
`delivery-failed` on the request, naming the withdrawal -- so it is not silent:
the owner reads it on the request as a reader sees it.

Through the real posting route and dispatch; only the run is scripted.
"""

from __future__ import annotations

from tests._loop import _withdraw, a_conversation, say, world  # noqa: F401
from tests.test_workflow_change import (_again, _ask, _run_sent,
                                        door)  # noqa: F401


REASON = "the migration was cancelled upstream"


def _withdraw_work(world, cid, exp, reason=REASON):
    """The owner takes back work an agent carries, in the shape W0 proved
    (`tests/w0/test_w0_dispatch.py::_withdraw`): their `expectation-met` on the
    request, marked withdrawn, by somebody who is not its carrier."""
    cv = world["cv"]
    return cv.record_act(actor=world["who"]["@brian"], act="expectation-met",
                         conversation=cid, turn=cv._act(exp)["turn"],
                         caused_by=exp, because=reason,
                         detail={"withdrawn": True})


def _acts(world, exp, name):
    return [a for a in world["cv"].history(caused_by=exp) if a["act"] == name]


def test_a_withdrawn_request_is_refused_and_nothing_is_started(world, door):
    cv = world["cv"]
    cid = a_conversation(world)
    exp = _ask(world, cid, "look into it", work="look into it")["expectations"][0]
    gone = _withdraw_work(world, cid, exp)

    _, out = _run_sent(world, exp)

    assert out["ok"] is False and out["before_execution_started"] is True
    assert out["withdrawal"] == gone
    assert door["ran"] == []
    assert _acts(world, exp, "execution-started") == []
    # REFUSED BEFORE ANYTHING ELSE IS RECORDED: not bound to a runtime for a
    # run that will never exist.
    assert _acts(world, exp, "runtime-bound") == []
    assert cv.expectation_state(exp)["live_execution"] == []
    assert [r for r in cv.open_runs() if r.get("caused_by") == exp] == []


def test_what_the_refusal_writes_and_how_the_owner_sees_it(world, door):
    from mentis.operational.work import trunk_status
    from mentis.operational.work_overview import detail as work_detail
    from mentis.web import _expectation_view
    cv, st = world["cv"], world["state"]
    cid = a_conversation(world)
    exp = _ask(world, cid, "look into it", work="look into it")["expectations"][0]
    gone = _withdraw_work(world, cid, exp)

    _, out = _run_sent(world, exp)

    # ONE ACT, ON THE REQUEST, BY THE PARTICIPANT THAT WOULD HAVE RUN IT, THAT
    # SAYS WHO WITHDREW IT AND WHY, and names the withdrawal.
    failed = _acts(world, exp, "delivery-failed")
    assert [a["id"] for a in failed] == [out["failed_act"]]
    assert failed[0]["actor"] == world["steward"]
    assert failed[0]["detail"]["stage"] == "request-withdrawn"
    assert failed[0]["detail"]["before_execution_started"] is True
    assert failed[0]["detail"]["withdrawal"] == gone
    assert "@brian" in failed[0]["because"] and REASON in failed[0]["because"]
    # WHAT THE POST SHOWS IS WHAT `Addressing.tsx` READS: `failures`, whose
    # newest `because` it says, before it says anything else of a closed
    # request. So the owner reads this and not a request that looks answered.
    seen = _expectation_view(st, cv.expectation_state(exp))
    assert seen["failures"][-1]["because"] == failed[0]["because"]
    # AND IT DOES NOT MAKE THE WORK LOOK OWED OR BLOCKED: it stays closed.
    assert seen["satisfied_by"] == [gone]
    assert exp not in [e["expectation"]
                       for e in cv.expectations(open_only=True)]
    state = trunk_status(cv, exp)["state"]
    assert state["value"] == "claimed-met"
    # AND THE WORK VIEW LISTS IT AS A RUN THAT FAILED BEFORE IT STARTED.
    item = work_detail(cv, exp, viewer=world["who"]["@brian"], runtime={})
    assert item["executions"]["failed"] == 1 == item["executions"]["total"]
    row = [x for a in item["agents_detail"] for x in a["executions"]]
    assert [(r["state"], r["started_at"]) for r in row] == [("failed", None)]
    assert REASON in row[0]["summary"]


def test_a_decision_withdrawn_through_the_posting_door_is_refused(world, door):
    # THE WITHDRAWAL THE DOOR WRITES TODAY: by the person it was asked of, with
    # the reply that gave the reason. The record's own shape, not a test's.
    cv = world["cv"]
    me = world["who"]["@brian"]
    cid = a_conversation(world)
    turn = cv.say(cid, world["steward"], [{"type": "text", "text": "Which?"}],
                  addressed_to=[me])
    exp = cv.expect(turn, of=me, kind="decision", by=world["steward"],
                    because="which one", detail={"options": ["a", "b"]})
    out = _withdraw(world, cid, {"turn": turn, "expectation": exp})
    assert "error" not in out, out
    assert cv.expectation_state(exp)["withdrawn"]
    _again(world, cid, exp)

    _, out = _run_sent(world, exp)

    assert out["ok"] is False and out["before_execution_started"] is True
    assert door["ran"] == []
    assert _acts(world, exp, "execution-started") == []


def test_a_withdrawal_landing_as_the_start_is_written_is_still_refused(
        world, door, monkeypatch):
    # THE ONE THAT MATTERS: the first check has passed and a session has been
    # claimed when the withdrawal commits. The start asks again in the
    # transaction that writes it, so nothing can land between the two.
    cv, svc = world["cv"], world["state"].agents
    cid = a_conversation(world)
    exp = _ask(world, cid, "look into it", work="look into it")["expectations"][0]
    real, held = svc.agents_summon, {}

    def summon_then_withdrawn(*a, **k):
        got = real(*a, **k)
        held["instance"] = got.instance_id
        held["gone"] = _withdraw_work(world, cid, exp)
        return got
    monkeypatch.setattr(svc, "agents_summon", summon_then_withdrawn)

    _, out = _run_sent(world, exp)

    assert out["ok"] is False and out["before_execution_started"] is True
    assert out["withdrawal"] == held["gone"]
    assert door["ran"] == []
    assert _acts(world, exp, "execution-started") == []
    # THE CLAIM WENT BACK, and the grant minted for the run with it.
    assert svc.known(held["instance"]) is None
    assert svc.authority.grant_of(held["instance"]) is None
    assert [r for r in cv.open_runs() if r.get("caused_by") == exp] == []


def test_work_waiting_on_a_refused_child_hears_why(world, door):
    # A REFUSED START ENDS THE WAIT ON IT LIKE ANY FAILURE BEFORE A START: what
    # was waiting is told how it ended, in the same words. It is not left held
    # by a child that will never run.
    cv = world["cv"]
    cid = a_conversation(world)
    exp = _ask(world, cid, "look into it", work="look into it")["expectations"][0]
    _withdraw_work(world, cid, exp)
    _run_sent(world, exp)
    child = cv._child_state(exp)
    assert child["state"] == "failed-before-start"
    assert REASON in child["because"]


# -- and nothing but that ------------------------------------------------------

def test_a_request_that_is_not_withdrawn_runs_as_it_did(world, door):
    cid = a_conversation(world)
    exp = _ask(world, cid, "look into it", work="look into it")["expectations"][0]
    _, out = _run_sent(world, exp)
    assert out.get("ok") is not False, out
    assert len(door["ran"]) == 1
    assert len(_acts(world, exp, "execution-started")) == 1


def test_a_request_closed_any_other_way_is_not_ruled_on(world, door):
    # Met, not withdrawn. Whether anything should stop a run on a request
    # closed like this is undecided (ent-a175acd8dc29), so it runs as it did.
    cv = world["cv"]
    cid = a_conversation(world)
    exp = _ask(world, cid, "look into it", work="look into it")["expectations"][0]
    cv.record_act(actor=world["steward"], act="expectation-met",
                  conversation=cid, turn=cv._act(exp)["turn"], caused_by=exp,
                  because="done", detail={"result_kind": "done"})
    _, out = _run_sent(world, exp)
    assert out.get("ok") is not False, out
    assert len(door["ran"]) == 1


def test_a_dispatch_carrying_no_request_is_not_asked_about_one(world, door):
    from mentis.web import dispatch as D
    cid = a_conversation(world)
    turn = say(world, cid, "hello", action="record-only")["turn"]
    out = D.dispatch(world["state"], conversation=cid, turn=turn,
                     participant=world["steward"], work="say hello")
    assert out.get("ok") is not False, out
    assert len(door["ran"]) == 1
