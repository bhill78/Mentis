"""Workflow changes: final corrections (owner, 2026-10-29).

  2-3. A Workflow change never widens execution authority, enforced at
       dispatch: the change records what the work could do, and a later run
       allowed more without an owner act since is refused before it starts.
  4.   `take_up`: a session taking up work, and any session briefed on it,
       receives the request's current Workflow.
  5.   Children delegated under a Workflow stay in the progress view after it
       is changed.
  6.   The owner's control is offered only where the server permits it.
  And the change carried through continuation and delegation.

Through the real posting route, dispatch, `/api/worker` and Fluid command
doors; only the run is scripted.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_workflow_change import (NEW_TEXT, OLD_TEXT, _ask, _again,
                                        _finding, _fluid, _get, _run_sent,
                                        _workflow, door)  # noqa: F401


def _change_as_carrier(world, door, cid, exp, new, marker="[[switch]]"):
    """The carrier's own run changes the Workflow, citing a finding."""
    found = _finding(world, cid)
    door["calls"][marker] = [("change_workflow", {
        "workflow": new, "because": "it turned out to be a defect",
        "evidence": [found]})]
    _run_sent(world, exp)
    status, said = door["answers"][-1]
    assert status == 200 and said.get("ok"), said
    return said


# -- 2-3: authority is not the Workflow's -------------------------------------

def test_a_change_records_what_the_work_could_do_and_the_run_is_told(world, door):
    from mentis.conversation import workflow_change as wc
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Software change", NEW_TEXT)
    cid = a_conversation(world)
    exp = _ask(world, cid, "look into it", work="[[switch]]", governed=[old],
               coordinate=True)["expectations"][0]
    before = wc.authority_snapshot(cv, exp)
    said = _change_as_carrier(world, door, cid, exp, new)
    act = cv._act(said["act"])["detail"]["workflow_change"]
    assert act["authority"] == before
    assert act["authority"]["consent"]["mode"] == "ask"
    first_grant = door["ran"][-1]["grant"]
    _again(world, cid, exp)
    _run_sent(world, exp)
    prompt, grant = door["ran"][-1]["prompt"], door["ran"][-1]["grant"]
    assert NEW_TEXT in prompt
    assert "The change authorises nothing" in prompt
    assert "Research to Software change" in prompt
    # what the run may do is exactly what it could before
    assert grant.get("operations") == first_grant.get("operations")
    assert grant.get("scope") == first_grant.get("scope")
    assert wc.authority_snapshot(cv, exp) == before
    assert wc.authority_widened(cv, exp) is None


def test_dispatch_refuses_a_run_wider_than_the_work_was_when_it_changed(
        world, door, monkeypatch):
    """Nothing today lets a Workflow widen authority; this proves the guard
    holds if anything ever did: a widening with no owner act since the change
    stops the run before it starts, and an owner act makes it theirs."""
    from mentis.conversation import workflow_change as wc
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Software change", NEW_TEXT)
    cid = a_conversation(world)
    exp = _ask(world, cid, "look into it", work="[[switch]]", governed=[old],
               coordinate=True)["expectations"][0]
    _change_as_carrier(world, door, cid, exp, new)
    real = wc.authority_snapshot

    def wider(cv_, e):
        got = real(cv_, e)
        return {**got, "consent": {**got["consent"], "mode": "all"},
                "follow_up": "unrestricted"}
    monkeypatch.setattr(wc, "authority_snapshot", wider)
    runs = len(door["ran"])
    _again(world, cid, exp)
    _, out = _run_sent(world, exp)
    assert out["ok"] is False and out["before_execution_started"] is True
    assert "consent ask -> all" in out["why"] and "follow-up" in out["why"]
    assert len(door["ran"]) == runs                  # nothing started
    failed = cv._act(out["failed_act"])
    assert failed["detail"]["stage"] == "workflow-authority"
    # the owner widening it is the owner's to do
    cv.record_act(actor=world["who"]["@brian"], act="consent-set",
                  conversation=cid, caused_by=exp, because="approve all",
                  detail={"scope": "task", "consent": {"mode": "all"}})
    _again(world, cid, exp)
    _, out = _run_sent(world, exp)
    assert out.get("ok") is not False, out
    assert len(door["ran"]) == runs + 1


def test_a_carriers_own_consent_act_does_not_count_as_the_owners(world, door,
                                                                  monkeypatch):
    from mentis.conversation import workflow_change as wc
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Software change", NEW_TEXT)
    cid = a_conversation(world)
    exp = _ask(world, cid, "look into it", work="[[switch]]", governed=[old],
               coordinate=True)["expectations"][0]
    _change_as_carrier(world, door, cid, exp, new)
    cv.record_act(actor=world["steward"], act="consent-set", conversation=cid,
                  caused_by=exp, because="I allow myself",
                  detail={"scope": "task", "consent": {"mode": "all"}})
    real = wc.authority_snapshot
    monkeypatch.setattr(wc, "authority_snapshot", lambda c, e: {
        **real(c, e), "consent": {**real(c, e)["consent"], "mode": "all"}})
    _again(world, cid, exp)
    _, out = _run_sent(world, exp)
    assert out["ok"] is False and "consent ask -> all" in out["why"]


# -- continuation and delegation after a change --------------------------------

def test_a_continuation_after_a_change_carries_the_new_workflow(world, door):
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Software change", NEW_TEXT)
    cid = a_conversation(world)
    exp = _ask(world, cid, "look into it", work="[[switch]]", governed=[old],
               coordinate=True)["expectations"][0]
    _change_as_carrier(world, door, cid, exp, new)
    result = [a for a in cv.history() if a["act"] == "result-returned"
              and a.get("caused_by") and a["actor"] == world["steward"]][-1]
    out = say(world, cid, "now carry on", replies_to=result["turn"],
              action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "go on"}])
    assert "error" not in out, out
    again = out["expectations"][0]
    assert cv.governed_named(again) == [new]
    assert cv._act(again)["detail"]["governed_from"] == "continued"
    _run_sent(world, again)
    assert NEW_TEXT in door["ran"][-1]["prompt"]
    assert OLD_TEXT not in door["ran"][-1]["prompt"]


def test_delegation_follows_the_new_workflow_and_earlier_children_stay(world,
                                                                       door):
    from mentis.operational.work import trunk_status
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Software change", NEW_TEXT)
    bob = cv.create_participant("@Bob")
    cid = a_conversation(world)
    exp = _ask(world, cid, "look into it", work="[[first]]", governed=[old],
               coordinate=True)["expectations"][0]
    found = _finding(world, cid)
    door["calls"]["[[first]]"] = [
        ("delegate", {"participant": bob, "work": "investigate a part",
                      "activity": f"{old}#do"}),
        ("change_workflow", {"workflow": new, "because": "a defect",
                             "evidence": [found]})]
    _run_sent(world, exp)
    assert all(s == 200 for s, _ in door["answers"][-2:]), door["answers"][-2:]
    # the next run carries the new Workflow: its steps may be delegated, the
    # old one's may not (it was not delivered)
    _again(world, cid, exp)
    world["sent"][-1]["work"] = "carry on [[second]]"
    door["calls"]["[[second]]"] = [
        ("delegate", {"participant": bob, "work": "fix a part",
                      "activity": f"{new}#do"}),
        ("delegate", {"participant": bob, "work": "more research",
                      "activity": f"{old}#do"})]
    _run_sent(world, exp)
    (s1, ok), (s2, refused) = door["answers"][-2:]
    assert s1 == 200 and ok.get("ok"), ok
    assert s2 == 403 and "not governing material this run was delivered" \
        in json.dumps(refused)
    ts = trunk_status(cv, exp, viewer=None, runtime=None)
    progress = {w["entry"]: w for w in ts["workflow"]["value"]}
    assert progress[new].get("former") is None
    assert progress[old]["former"] is True
    assert len(progress[old]["activities"][0]["children"]) == 1
    assert len(progress[new]["activities"][0]["children"]) == 1
    # and Fluid reads it the same way
    view = _get(world, f"/api/work/{exp}")["workflow"]
    assert {w["entry"]: w.get("former") for w in view["progress"]} == \
        {new: None, old: True}


def test_an_earlier_workflow_with_nothing_under_it_is_not_shown(world, door):
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Software change", NEW_TEXT)
    cid = a_conversation(world)
    exp = _ask(world, cid, "look", work="x", governed=[old])["expectations"][0]
    status, _ = _fluid(world, f"/fluid/api/work/{exp}/workflow", {
        "workflow": new, "because": "a defect", "evidence": [
            cv._act(exp)["turn"]]})
    assert status == 200
    view = _get(world, f"/api/work/{exp}")["workflow"]
    assert [w["entry"] for w in view["progress"]] == [new]


# -- 4: take_up --------------------------------------------------------------

def _session(world):
    from mentis.worker import CAPABILITY_HEADER, SESSION_ROUTE

    def post(path, body, headers):
        req = urllib.request.Request(
            world["base"] + path, method="POST",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
    status, grant = post(SESSION_ROUTE, {"corpus": world["state"].path,
                                         "runtime": "claude"},
                         {"X-Mentis-Client": "1"})
    assert status == 200, grant

    def op(name, **args):
        return post("/api/worker", {"op": name, "args": args},
                    {CAPABILITY_HEADER: grant["grant"]})
    return op


def test_take_up_receives_the_current_workflow_and_a_new_session_is_briefed(
        world):
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Software change", NEW_TEXT)
    cid = a_conversation(world)
    first = _session(world)
    _, trunk = first("record_request", conversation=cid, text="trunk",
                     workflow=old, follow_up={"depth": 1})
    status, side = first("record_discovered_work", under=trunk["expectation"],
                         work="the page re-reads every conversation")
    assert status == 200, side
    d = side["expectation"]
    # the owner names the side work's Workflow before anybody takes it up
    status, said = _fluid(world, f"/fluid/api/work/{d}/workflow", {
        "workflow": new, "because": "it is a defect",
        "evidence": [cv._act(d)["turn"]]})
    assert status == 200, said
    assert cv.assigned_carrier(d)["carrier"] is None   # still unassigned
    status, took = first("take_up", expectation=d, under=trunk["expectation"])
    assert status == 200, took
    assert took["workflow"] == [{"entry": new, "name": "Software change"}]
    # a newly started session, briefed on the work it took up
    second = _session(world)
    status, briefed = second("brief", conversation=cid, expectation=d)
    assert status == 200, briefed
    assert NEW_TEXT in json.dumps(briefed)
    # and after a further change, by the session that carries it
    status, again = first("change_workflow", expectation=d, workflow=old,
                          because="reproduction failed",
                          evidence=[_finding(world, cid)])
    assert status == 200, again
    status, briefed = second("brief", conversation=cid, expectation=d)
    assert OLD_TEXT in json.dumps(briefed) and NEW_TEXT not in json.dumps(briefed)


# -- 6: the control only where the server permits it ---------------------------

def test_can_change_says_where_the_owners_change_can_succeed(world):
    from mentis.conversation import workflow_change as wc
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    cid = a_conversation(world)
    exp = _ask(world, cid, "look", work="x", governed=[old])["expectations"][0]
    # only one standing Workflow, and it is the current one
    got = _get(world, f"/api/work/{exp}")["workflow"]["can_change"]
    assert got == {"owner": False,
                   "why": "no other standing Workflow to change to"}
    _workflow(world, "Software change", NEW_TEXT)
    assert _get(world, f"/api/work/{exp}")["workflow"]["can_change"] == \
        {"owner": True, "why": None}
    cv.record_act(actor=world["who"]["@brian"], act="expectation-met",
                  conversation=cid, caused_by=exp, about=[exp], because="done")
    assert wc.changeable(cv, exp) == {"owner": False, "why": "the work is met"}
