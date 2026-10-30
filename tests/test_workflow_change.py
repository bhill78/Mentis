"""Changing the Workflow on an active request (owner's assignment, 2026-10-29).

Through the real posting route, the real dispatch path, the real `/api/worker`
door and the real Fluid command door; only the run is scripted.

  1-2. the owner (Fluid) or an authorised carrier (`change_workflow`) changes
       the Workflow by an append-only assignment naming no carrier, with the
       new Workflow, a reason and evidence; the original and every change stay
       readable in order.
  3.   a carrier needs the request it carries and organising authority, stays
       inside the request's scope, and nothing it may do changes.
  4.   the next run of the request is composed with the new Workflow.
  5.   the delivery record says, per component, full / conditional /
       reference and why.
  6.   the work detail Fluid reads carries the current Workflow, its origin,
       the server-computed activity progress and the change history.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import pytest

from tests._loop import a_conversation, say, world  # noqa: F401

OLD_TEXT = "Investigate and report findings; build nothing."
NEW_TEXT = "Reproduce the defect, fix it with a regression test, then integrate."


def _workflow(world, name, text, *, about=None, projects=()):
    return world["cv"].corpus.create_and_establish(
        kind="workflow",
        body={"name": name, "about": about or name, "text": text,
              "projects": list(projects),
              "activities": [{"key": "do", "what": "do the work",
                              "who": {"role": "the carrier"},
                              "done_when": "done"}],
              "decisions": [], "done_when": "done", "requires": []},
        attributed_to=world["who"]["@brian"])


def _discipline(world, name="Targeted tests"):
    return world["cv"].corpus.create_and_establish(
        kind="discipline", body={"name": name, "about": name,
                                 "text": "run what you touched"},
        attributed_to=world["who"]["@brian"])


@pytest.fixture()
def door(world):
    """Every run ends reported done. A run whose prompt carries a marker
    queued in `calls` first makes those calls through `/api/worker` with its
    own grant, and the answers are kept (status, body)."""
    from mentis.execution import RunResult
    from mentis.worker import CAPABILITY_HEADER
    from tests._loop import script_every_backend

    svc = world["state"].agents
    ran, calls, answers = [], {}, []

    def call(token, op, args):
        req = urllib.request.Request(
            world["base"] + "/api/worker", method="POST",
            data=json.dumps({"op": op, "args": args}).encode(),
            headers={"Content-Type": "application/json",
                     CAPABILITY_HEADER: token})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def perform(spec):
        token = svc.authority.grant_of(spec.run_id)
        grant = svc.authority.grant_for(token, world["state"].path)
        ran.append({"grant": grant, "prompt": spec.prompt,
                    "execution": spec.run_id})
        for marker, todo in list(calls.items()):
            if marker in spec.prompt:
                del calls[marker]
                for op, args in todo:
                    answers.append(call(token, op, args(grant) if callable(args)
                                        else args))
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn",
                         text="done", started_at=now, finished_at=now)

    script_every_backend(svc, perform)
    return {"ran": ran, "calls": calls, "answers": answers}


def _run_sent(world, expectation):
    from mentis.web import dispatch as D
    spec = next(s for s in world["sent"] if s.get("expectation") == expectation)
    world["sent"].remove(spec)
    return spec, D.dispatch(world["state"], **spec)


def _finding(world, cid, text="finding: it is a defect against the spec"):
    """A post somebody made with something learned -- evidence a carrier may
    cite (a carrier may not cite only the request it carries)."""
    out = say(world, cid, text, action="record-only")
    assert "error" not in out, out
    return out["turn"]


def _ask(world, cid, text, **spec):
    out = say(world, cid, text, action="ask-participant",
              dispatch=[{"participant": world["steward"], **spec}])
    assert "error" not in out, out
    return out


def _again(world, cid, exp):
    """Send the same request to its carrier again, as a resume does."""
    world["sent"].append({"conversation": cid,
                          "turn": world["cv"]._act(exp)["turn"],
                          "participant": world["steward"],
                          "work": "carry on", "expectation": exp})


def _fluid(world, path, body, client=True):
    req = urllib.request.Request(
        world["base"] + path, method="POST", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 **({"X-Mentis-Client": "1"} if client else {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _get(world, path):
    req = urllib.request.Request(world["base"] + path,
                                 headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


# -- 1-4: the carrier changes it, and the next run is given the new one --------

def test_a_carrier_changes_the_workflow_and_the_next_run_gets_it(world, door):
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Bug repair", NEW_TEXT)
    disc = _discipline(world)
    cid = a_conversation(world)
    asked = _ask(world, cid, "look into the slow page", work="[[switch]]",
                 governed=[old, disc], coordinate=True)
    exp = asked["expectations"][0]
    turn = cv._act(exp)["turn"]
    carrier_before = cv.assigned_carrier(exp)
    authority_before = cv.authority_of(exp)
    found = _finding(world, cid)
    door["calls"]["[[switch]]"] = [
        # the request alone is not evidence for a carrier
        ("change_workflow", {"workflow": new, "because": "a defect",
                             "evidence": [turn]}),
        ("change_workflow", {
            "workflow": new, "because": "it is a defect against the spec",
            "evidence": [found, turn]})]
    _run_sent(world, exp)
    assert OLD_TEXT in door["ran"][-1]["prompt"]
    status, said = door["answers"][-2]
    assert status == 403 and "beyond the request" in json.dumps(said)
    status, said = door["answers"][-1]
    assert status == 200 and said.get("ok"), said
    assert said["from"] == [old] and said["to"] == [new]

    # resolved newest-first; the Discipline named for the request stays
    assert cv.governed_named(exp) == [disc, new]
    # the act names no carrier: who carries it, and as whom, is unchanged
    change = cv._act(said["act"])
    assert change["act"] == "expectation-assigned" and change["about"] == []
    assert cv.assigned_carrier(exp)["carrier"] == carrier_before["carrier"]
    assert cv.authority_of(exp) == authority_before
    from mentis.operational import work
    assert work._persona(cv, exp, work._order(cv)) == \
        work._persona(cv, exp, work._order(cv))  # stable read
    detail = change["detail"]["workflow_change"]
    assert detail["evidence"] == [found, turn] and detail["role"] == "carrier"
    assert "nothing" in detail["grants"]

    # the next run of the same request is composed with the new Workflow
    _again(world, cid, exp)
    _run_sent(world, exp)
    prompt = door["ran"][-1]["prompt"]
    assert NEW_TEXT in prompt and OLD_TEXT not in prompt
    assert new in door["ran"][-1]["grant"]["delivered"]
    assert old not in door["ran"][-1]["grant"]["delivered"]
    # and with exactly the authority the request had
    assert door["ran"][-1]["grant"].get("operations") == \
        door["ran"][0]["grant"].get("operations")

    # the history keeps the original and the change, in order
    from mentis.conversation import workflow_change as wc
    h = wc.history(cv, exp)
    assert [e["kind"] for e in h["history"]] == ["asked", "changed"]
    assert h["history"][0]["workflows"][0]["entry"] == old
    assert h["history"][1]["because"] == "it is a defect against the spec"
    assert h["current"] == [{"entry": new, "name": "Bug repair"}]
    assert h["origin"] == "changed"


def test_the_persona_of_the_work_survives_a_change(world, door):
    """`work._persona` reads the latest act that PUT A CARRIER on the work; a
    change names nobody and must not read as "no Persona"."""
    from mentis.operational import work
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Bug repair", NEW_TEXT)
    cid = a_conversation(world)
    # unaddressed: intake assigns it to the designated carrier with a Persona
    out = say(world, cid, "look into the slow page", action="ask-mentis",
              governed=[old])
    assert "error" not in out, out
    exp = out["expectations"][0]
    before = work._persona(cv, exp, work._order(cv))
    assert before == world["persona"]
    status, said = _fluid(world, f"/fluid/api/work/{exp}/workflow", {
        "workflow": new, "because": "a defect", "evidence": [
            cv._act(exp)["turn"]]})
    assert status == 200, said
    assert work._persona(cv, exp, work._order(cv)) == before


def test_without_organising_authority_a_carrier_is_refused(world, door):
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Bug repair", NEW_TEXT)
    cid = a_conversation(world)
    asked = _ask(world, cid, "look", work="[[switch]]", governed=[old])
    exp = asked["expectations"][0]
    door["calls"]["[[switch]]"] = [("change_workflow", {
        "workflow": new, "because": "x", "evidence": [cv._act(exp)["turn"]]})]
    _run_sent(world, exp)
    status, said = door["answers"][-1]
    assert status == 403 and "coordinate" in json.dumps(said)
    assert cv.governed_named(exp) == [old]


def test_a_run_cannot_change_a_request_it_does_not_carry(world, door):
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Bug repair", NEW_TEXT)
    cid = a_conversation(world)
    other = _ask(world, cid, "other work", work="x",
                 governed=[old])["expectations"][0]
    asked = _ask(world, cid, "look", work="[[switch]]", governed=[old],
                 coordinate=True)
    exp = asked["expectations"][0]
    door["calls"]["[[switch]]"] = [("change_workflow", {
        "expectation": other, "workflow": new, "because": "x",
        "evidence": [cv._act(exp)["turn"]]})]
    _run_sent(world, exp)
    status, said = door["answers"][-1]
    assert status == 403 and "dispatched to carry" in json.dumps(said)
    assert cv.governed_named(other) == [old]


def test_a_delegated_step_cannot_change_a_workflow(world, door):
    """A child's Workflow is its parent's; `check` refuses a non-trunk."""
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Bug repair", NEW_TEXT)
    bob = cv.create_participant("@Bob")
    cid = a_conversation(world)
    asked = _ask(world, cid, "look", work="[[hand]]", governed=[old],
                 coordinate=True)
    exp = asked["expectations"][0]
    door["calls"]["[[hand]]"] = [("delegate", {
        "participant": bob, "work": "a part [[child]]", "return_to_me": True})]
    _run_sent(world, exp)
    child = next(a["id"] for a in cv.history(caused_by=exp)
                 if a["act"] == "expectation-recorded")
    from mentis.conversation import workflow_change as wc
    with pytest.raises(wc.Refused, match="its own right"):
        wc.check(cv, child, new, because="x", evidence=[cv._act(exp)["turn"]],
                 role=wc.CARRIER)


@pytest.mark.parametrize("args,match", [
    ({"because": "", "evidence": ["TURN"]}, "say why"),
    ({"because": "x", "evidence": []}, "needs evidence"),
    ({"because": "x", "evidence": ["ent-000000000000"]}, "not something"),
    ({"because": "x", "evidence": ["somewhere"]}, "not something"),
])
def test_a_change_needs_a_reason_and_held_evidence(world, args, match):
    from mentis.conversation import workflow_change as wc
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Bug repair", NEW_TEXT)
    cid = a_conversation(world)
    exp = _ask(world, cid, "look", work="x", governed=[old])["expectations"][0]
    ev = [cv._act(exp)["turn"] if e == "TURN" else e for e in args["evidence"]]
    with pytest.raises(wc.Refused, match=match):
        wc.check(cv, exp, new, because=args["because"], evidence=ev,
                 role=wc.OWNER)


def test_only_a_standing_workflow_and_only_a_change(world):
    from mentis.conversation import workflow_change as wc
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    disc = _discipline(world)
    cid = a_conversation(world)
    exp = _ask(world, cid, "look", work="x", governed=[old])["expectations"][0]
    ev = [cv._act(exp)["turn"]]
    with pytest.raises(wc.Refused, match="not a Workflow"):
        wc.check(cv, exp, disc, because="x", evidence=ev, role=wc.OWNER)
    with pytest.raises(wc.Refused, match="already governed"):
        wc.check(cv, exp, old, because="x", evidence=ev, role=wc.OWNER)
    with pytest.raises(wc.Refused, match="Workflows are named"):
        wc.check(cv, exp, "No such workflow", because="x", evidence=ev,
                 role=wc.OWNER)
    # by exact name is fine
    new = _workflow(world, "Bug repair", NEW_TEXT)
    assert wc.check(cv, exp, "Bug repair", because="x", evidence=ev,
                    role=wc.OWNER)["to"] == [new]


def test_met_work_is_not_changed(world):
    from mentis.conversation import workflow_change as wc
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Bug repair", NEW_TEXT)
    cid = a_conversation(world)
    exp = _ask(world, cid, "look", work="x", governed=[old])["expectations"][0]
    cv.record_act(actor=world["who"]["@brian"], act="expectation-met",
                  conversation=cid, caused_by=exp, about=[exp],
                  because="done")
    with pytest.raises(wc.Refused, match="already met"):
        wc.check(cv, exp, new, because="x", evidence=[cv._act(exp)["turn"]],
                 role=wc.OWNER)


def test_a_carrier_stays_inside_the_requests_scope_the_owner_need_not(world):
    from mentis.conversation import workflow_change as wc
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    mars_only = _workflow(world, "MARS change", NEW_TEXT, projects=["MARS"])
    cid = a_conversation(world)
    out = say(world, cid, "look", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "x",
                         "governed": [old],
                         "repository": {"path": "C:\\Work\\Mentis"}}])
    assert "error" not in out, out
    exp = out["expectations"][0]
    ev = [_finding(world, cid)]
    with pytest.raises(wc.Refused, match="outside the scope"):
        wc.check(cv, exp, mars_only, because="x", evidence=ev,
                 role=wc.CARRIER)
    # a Workflow written for this repository, or for any, is in scope
    mentis_wf = _workflow(world, "Mentis change", NEW_TEXT,
                          projects=["Mentis"])
    assert wc.check(cv, exp, mentis_wf, because="x", evidence=ev,
                    role=wc.CARRIER)["to"] == [mentis_wf]
    # the owner decides the scope
    assert wc.check(cv, exp, mars_only, because="x", evidence=ev,
                    role=wc.OWNER)["to"] == [mars_only]


# -- 1: the owner, through Fluid ------------------------------------------------

def test_the_owner_changes_it_from_fluid_once_per_operation_key(world):
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Bug repair", NEW_TEXT)
    cid = a_conversation(world)
    exp = _ask(world, cid, "look", work="x", governed=[old])["expectations"][0]
    body = {"workflow": new, "because": "approved: build it",
            "evidence": [cv._act(exp)["turn"]], "op": "k-1",
            "author": world["steward"]}          # an `author` is ignored
    status, said = _fluid(world, f"/fluid/api/work/{exp}/workflow", body)
    assert status == 200 and said["to"] == [new], said
    act = cv._act(said["act"])
    assert act["actor"] == world["who"]["@brian"]
    assert act["detail"]["workflow_change"]["role"] == "owner"
    again, said2 = _fluid(world, f"/fluid/api/work/{exp}/workflow", body)
    assert again == 200 and said2.get("replayed")
    assert len([a for a in cv.history(caused_by=exp)
                if "workflow_change" in (a.get("detail") or {})]) == 1
    # a refusal is 422 with the reason, and writes nothing
    status, said = _fluid(world, f"/fluid/api/work/{exp}/workflow",
                          {"workflow": old, "because": "", "evidence": []})
    assert status == 422 and said.get("refused")
    # the client header is required, as on every Fluid POST
    status, _ = _fluid(world, f"/fluid/api/work/{exp}/workflow", body,
                       client=False)
    assert status in (400, 403)


def test_a_hand_started_session_changes_a_request_it_recorded(world):
    from mentis.worker import CAPABILITY_HEADER, SESSION_ROUTE
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Bug repair", NEW_TEXT)
    cid = a_conversation(world)

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
    h = {CAPABILITY_HEADER: grant["grant"]}
    status, rec = post("/api/worker", {"op": "record_request", "args": {
        "conversation": cid, "text": "look into it", "workflow": old}}, h)
    assert status == 200, rec
    status, briefed = post("/api/worker", {"op": "brief", "args": {
        "conversation": cid, "expectation": rec["expectation"]}}, h)
    assert status == 200 and OLD_TEXT in json.dumps(briefed), briefed
    status, said = post("/api/worker", {"op": "change_workflow", "args": {
        "expectation": rec["expectation"], "workflow": new,
        "because": "it is a bug", "evidence": [_finding(world, cid)]}}, h)
    assert status == 200 and said["to"] == [new], said
    assert cv.governed_named(rec["expectation"])[-1] == new
    # the session is briefed with the Workflow it is governed by now
    status, briefed = post("/api/worker", {"op": "brief", "args": {
        "conversation": cid, "expectation": rec["expectation"]}}, h)
    assert status == 200, briefed
    assert NEW_TEXT in json.dumps(briefed) and OLD_TEXT not in json.dumps(briefed)
    # and not a request somebody else recorded
    other = _ask(world, cid, "theirs", work="x",
                 governed=[old])["expectations"][0]
    status, said = post("/api/worker", {"op": "change_workflow", "args": {
        "expectation": other, "workflow": new, "because": "x",
        "evidence": [rec["turn"]]}}, h)
    assert status == 403


# -- 5: the delivery record says how much of each crossed -----------------------

def test_the_delivery_record_says_full_or_pointer_and_why(world, door):
    cv = world["cv"]
    named = _workflow(world, "Research", OLD_TEXT)
    placed = _workflow(world, "Release", "Cut the release.",
                       about="cutting a release of the parser")
    cv.place(placed, whole_brain=True, by=world["who"]["@brian"],
             because="placed on a condition", delivery="conditional",
             when="cutting a release of the parser")
    cid = a_conversation(world)
    exp = _ask(world, cid, "look into the slow page", work="look into it",
               governed=[named])["expectations"][0]
    _run_sent(world, exp)
    row = max(world["state"].corpus.deliveries(), key=lambda d: d["at"])
    by_id = {s["source_id"]: s for s in row["behavioural_sources"]}
    assert by_id[named]["level"] == "full"
    assert "named for this work" in by_id[named]["level_why"]
    assert by_id[placed]["level"] == "conditional"
    assert by_id[placed]["condition"] == "cutting a release of the parser"
    assert "met_by" not in by_id[placed]
    # the same placement, met by the request's words, is full -- and says by which
    exp2 = _ask(world, cid, "cutting the parser release",
                work="cutting the parser release")[
        "expectations"][0]
    _run_sent(world, exp2)
    row = max(world["state"].corpus.deliveries(), key=lambda d: d["at"])
    src = next(s for s in row["behavioural_sources"] if s["source_id"] == placed)
    assert src["level"] == "full" and set(src["met_by"]) >= {"parser"}


# -- 6: what Fluid reads --------------------------------------------------------

def test_the_work_detail_carries_the_workflow_view(world, door):
    cv = world["cv"]
    old = _workflow(world, "Research", OLD_TEXT)
    new = _workflow(world, "Bug repair", NEW_TEXT)
    cid = a_conversation(world)
    exp = _ask(world, cid, "look", work="x", governed=[old],
               coordinate=True)["expectations"][0]
    got = _get(world, f"/api/work/{exp}")["workflow"]
    assert got["current"] == [{"entry": old, "name": "Research"}]
    assert got["origin"] == "named"
    assert [w["entry"] for w in got["progress"]] == [old]
    assert got["progress"][0]["activities"][0]["key"] == "do"
    status, said = _fluid(world, f"/fluid/api/work/{exp}/workflow", {
        "workflow": new, "because": "it is a defect",
        "evidence": [cv._act(exp)["turn"]]})
    assert status == 200, said
    got = _get(world, f"/api/work/{exp}")["workflow"]
    assert got["current"] == [{"entry": new, "name": "Bug repair"}]
    assert got["origin"] == "changed"
    assert [w["entry"] for w in got["progress"]] == [new]
    changed = got["history"][-1]
    assert changed["kind"] == "changed" and changed["role"] == "owner"
    assert changed["because"] == "it is a defect"
    assert changed["from"][0]["entry"] == old
    assert changed["evidence"][0]["ref"] == cv._act(exp)["turn"]
