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


# -- 2-3 in substance: the permission policy, where each operation is decided --

OPTS = [{"option_id": "once", "kind": "allow_once", "name": "Yes"},
        {"option_id": "no", "kind": "reject_once", "name": "No"}]


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("x = 1\n")
    return str(root)


def _edit(path):
    return {"tool_call": {"kind": "edit", "title": f"Edit {path}",
                          "locations": [{"path": path}]}, "options": OPTS}


def _read(path):
    return {"tool_call": {"kind": "read", "title": f"Read {path}",
                          "locations": [{"path": path}]}, "options": OPTS}


def _policy_on(world, repo, monkeypatch, consent=None):
    """A request governed by Research, a run of it in `repo`, and the real
    permission policy; asking the owner is recorded instead of waited on."""
    from mentis.operational import consent as C
    from mentis.web import permissions as P
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Software change", NEW_TEXT)
    cid = a_conversation(world, "Policy")
    turn = say(world, cid, "investigate it; build nothing")["turn"]
    exp = cv.expect(turn, of=world["steward"], kind="result",
                    by=world["who"]["@brian"],
                    detail={"governed": [old],
                            **({"consent": C.consent_value(consent)}
                               if consent else {})})
    run = cv.record_act(actor=world["steward"], act="execution-started",
                        conversation=cid, turn=turn, execution="inst-p",
                        runtime="claude", caused_by=exp, because="test",
                        detail={"workspace": repo})
    asked = []
    monkeypatch.setattr(P, "_ask_owner", lambda st, cv_, run_, request, obs,
                        op, consent, start: asked.append(op) or "asked")
    return {"cv": cv, "cid": cid, "exp": exp, "run": run, "old": old,
            "new": new, "asked": asked, "policy": P.make_policy(world["state"])}


def _carrier_changes(world, w):
    from mentis.conversation import workflow_change as wc
    change = wc.check(w["cv"], w["exp"], w["new"], because="a defect",
                      evidence=[_finding(world, w["cid"])], role=wc.CARRIER)
    return wc.record(w["cv"], change, by=world["steward"])


def test_a_carriers_change_withdraws_the_implicit_edit_allowance(world, repo,
                                                                 monkeypatch):
    w = _policy_on(world, repo, monkeypatch)              # consent: ask
    edit = f"{repo}\\src\\app.py"
    # before: an edit in the run's own workspace proceeds on its own grant
    assert w["policy"](w["run"], "inst-p", _edit(edit), {}) == "once"
    _carrier_changes(world, w)
    # after: the same edit is the owner's to answer; reading is untouched
    assert w["policy"](w["run"], "inst-p", _edit(edit), {}) == "asked"
    assert "Workflow was changed by its carrier" in w["asked"][-1].why
    assert w["policy"](w["run"], "inst-p", _read(edit), {}) == "once"


def test_edits_after_a_change_follow_only_the_owners_consent(world, repo,
                                                            monkeypatch):
    edit = f"{repo}\\src\\app.py"
    # the owner consented to routine work, edits included, in this workspace:
    # that implementation was already authorised, and proceeds
    w = _policy_on(world, repo, monkeypatch,
                   consent={"mode": "deny", "workspaces": [repo]})
    _carrier_changes(world, w)
    assert w["policy"](w["run"], "inst-p", _edit(edit), {}) == "once"
    # the owner's consent did not include edits: refused, never waiting
    w2 = _policy_on(world, repo, monkeypatch,
                    consent={"mode": "deny", "workspaces": [repo],
                             "categories": ["read", "test"]})
    assert w2["policy"](w2["run"], "inst-p", _edit(edit), {}) == "once"
    _carrier_changes(world, w2)
    assert w2["policy"](w2["run"], "inst-p", _edit(edit), {}) is None
    assert w2["asked"] == []


def test_the_owner_authorising_ends_the_restriction_and_a_post_does_not(
        world, repo, monkeypatch):
    from mentis.conversation import workflow_change as wc
    w = _policy_on(world, repo, monkeypatch)
    edit = f"{repo}\\src\\app.py"
    _carrier_changes(world, w)
    # the owner posting, or answering something, says nothing about edits
    say(world, w["cid"], "interesting, keep going")
    w["cv"].record_act(actor=world["who"]["@brian"], act="expectation-met",
                       conversation=w["cid"], caused_by=w["exp"],
                       about=[w["exp"]], because="answered a question",
                       detail={"decision": True})
    assert wc.pending_carrier_change(w["cv"], w["exp"]) is not None
    # the owner setting the task's consent is them saying what it may do
    w["cv"].record_act(actor=world["who"]["@brian"], act="consent-set",
                       conversation=w["cid"], caused_by=w["exp"],
                       because="go ahead", detail={"scope": "task",
                                                   "consent": {"mode": "ask"}})
    assert wc.pending_carrier_change(w["cv"], w["exp"]) is None
    assert w["policy"](w["run"], "inst-p", _edit(edit), {}) == "once"


def test_the_owners_own_change_restricts_nothing(world, repo, monkeypatch):
    from mentis.conversation import workflow_change as wc
    w = _policy_on(world, repo, monkeypatch)
    change = wc.check(w["cv"], w["exp"], w["new"], because="approved: build it",
                      evidence=[w["cv"]._act(w["exp"])["turn"]], role=wc.OWNER)
    wc.record(w["cv"], change, by=world["who"]["@brian"])
    assert wc.pending_carrier_change(w["cv"], w["exp"]) is None
    assert w["policy"](w["run"], "inst-p",
                       _edit(f"{repo}\\src\\app.py"), {}) == "once"


def test_a_delegated_child_of_a_changed_request_is_held_too(world, repo,
                                                            monkeypatch):
    from mentis.conversation import workflow_change as wc
    w = _policy_on(world, repo, monkeypatch)
    _carrier_changes(world, w)
    cv = w["cv"]
    turn = say(world, w["cid"], "a part of it")["turn"]
    child = cv.expect(turn, of=world["steward"], kind="result",
                      by=world["steward"], caused_by=w["exp"])
    held = wc.pending_carrier_change(cv, child)
    assert held is not None and held["detail"]["workflow_change"]["role"] == \
        "carrier"


def test_a_second_change_cannot_carry_a_widening_forward(world, door,
                                                         monkeypatch):
    from mentis.conversation import workflow_change as wc
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Software change", NEW_TEXT)
    cid = a_conversation(world)
    exp = _ask(world, cid, "look into it", work="[[switch]]", governed=[old],
               coordinate=True)["expectations"][0]
    _change_as_carrier(world, door, cid, exp, new)
    real = wc.authority_snapshot
    monkeypatch.setattr(wc, "authority_snapshot", lambda c, e: {
        **real(c, e), "consent": {**real(c, e)["consent"], "mode": "all"}})
    # a second carrier change, made while the work could (somehow) do more
    change = wc.check(cv, exp, old, because="back again",
                      evidence=[_finding(world, cid)], role=wc.CARRIER)
    wc.record(cv, change, by=world["steward"])
    assert "consent ask -> all" in (wc.authority_widened(cv, exp) or "")


def test_can_change_agrees_with_check_for_several_workflows(world):
    from mentis.conversation import workflow_change as wc
    cv = world["cv"]
    a = _workflow(world, "Research", OLD_TEXT)
    b = _workflow(world, "Software change", NEW_TEXT)
    cid = a_conversation(world)
    exp = _ask(world, cid, "look", work="x", governed=[a, b])["expectations"][0]
    assert wc.changeable(cv, exp) == {"owner": True, "why": None}
    assert wc.check(cv, exp, a, because="x", evidence=[cv._act(exp)["turn"]],
                    role=wc.OWNER)["to"] == [a]
