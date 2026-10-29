"""A delegated child is given its own step of the Workflow, not the Workflow.

WHAT MUST HOLD, through the real dispatch path (only the run is scripted):
  - a child whose request records an activity ("<workflow>#<key>") is told
    the Workflow's name and that activity's `what` and `done_when`, as a
    composed component sourced from the Workflow entry, and the delivery
    record says so (`activity` on the row);
  - a resumed or continued run of the same request is told the same step,
    because dispatch reads it from the request every time;
  - a Workflow superseded since the delegation gives the step of its current
    standing version; one with no standing version gives none, and says why;
  - a run with no activity is composed exactly as before;
  - the Workflow's own text, its other activities and its `requires` do not
    reach the child.
"""

from __future__ import annotations

import time

import pytest

from mentis.bootstrap import baseline
from mentis.conversation import text
from mentis.execution import RunResult
from mentis.web import _State, fixture
from mentis.web import dispatch as D
from tests._loop import script_every_backend


@pytest.fixture()
def world(tmp_path, monkeypatch):
    """A fixture Brain served by a `_State` whose dispatches nothing else
    starts: each test dispatches what it means to, through `D.dispatch`."""
    import mentis.web as web
    root = tmp_path / "corpus"
    built = fixture.build(str(root))
    state = _State(str(root))
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: None)
    return {"state": state, "cv": state.cv, "who": built["who"]}


def a_conversation(world, name):
    cv = world["cv"]
    cid = cv.open_conversation(name, attributed_to=world["who"]["@brian"])
    cv.join(world["who"]["@brian"], cid)
    return cid


@pytest.fixture()
def flow(world):
    """The baseline's Software change Workflow, installed here, and every run
    recording the prompt it was sent and ending as done."""
    out = baseline.install(world["state"].corpus, "@brian")
    items = {k: r["entry"] for k, r in out["items"].items()}
    prompts = []

    def perform(spec):
        prompts.append(spec.prompt)
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn", text="done",
                         started_at=now, finished_at=now)

    script_every_backend(world["state"].agents, perform)
    return {"entry": items["software-change"], "items": items,
            "prompts": prompts}


def _child(world, cid, who, work, activity=None):
    """A delegated request as `delegate` records it: the label on the
    request's own detail, nothing else added."""
    cv = world["cv"]
    owner = world["who"]["@brian"]
    cv.join(who, cid)
    turn = cv.say(cid, owner, [text(work)],
                  addressed_to=[who])
    exp = cv.expect(turn, of=who, kind="result", by=owner,
                    detail={"returns_to": None,
                            **({"activity": activity} if activity else {})})
    return turn, exp


def _run(world, cid, turn, who, work, exp, **kw):
    return D.dispatch(world["state"], conversation=cid, turn=turn,
                      participant=who, work=work, expectation=exp, **kw)


def _sources(world, who):
    return [s for d in world["state"].corpus.deliveries(participant=who)
            for s in d["behavioural_sources"]]


def _row(world, flow_entry, key):
    got = world["state"].corpus.read([flow_entry])[0]
    return next(r for r in got["body"]["activities"] if r["key"] == key)


def test_a_child_with_an_activity_is_given_its_step(world, flow):
    cv = world["cv"]
    cid = a_conversation(world, "Build")
    bob = cv.create_participant("@Bob")
    label = f"{flow['entry']}#implement"
    turn, exp = _child(world, cid, bob, "implement the parser", label)
    got = _run(world, cid, turn, bob, "implement the parser", exp)
    assert got.get("ok") is not False, got
    prompt = flow["prompts"][-1]
    row = _row(world, flow["entry"], "implement")
    assert "Software change" in prompt
    assert f"Your step in this Workflow (implement): {row['what']}" in prompt
    assert f"Done when: {row['done_when']}" in prompt
    # The delivery record says where it came from, and that it is a step.
    step = [s for s in _sources(world, bob) if s.get("activity")]
    assert step == [{"source_kind": "workflow", "source_id": flow["entry"],
                     "scope": "invocation:named", "supplied_as": "governance",
                     "tier": "governing", "activity": label}]


def test_the_whole_workflow_does_not_reach_the_child(world, flow):
    cv = world["cv"]
    cid = a_conversation(world, "Build")
    bob, cy = cv.create_participant("@Bob"), cv.create_participant("@Cy")
    turn, exp = _child(world, cid, bob, "implement it",
                       f"{flow['entry']}#implement")
    _run(world, cid, turn, bob, "implement it", exp)
    prompt = flow["prompts"][-1]
    body = world["state"].corpus.read([flow["entry"]])[0]["body"]
    assert body["text"].strip() and body["text"].strip() not in prompt
    for other in body["activities"]:
        if other["key"] != "implement":
            assert other["what"] not in prompt, other["key"]
    # And it requires of the runtime exactly what a child without the
    # activity is required: the step adds nothing to selection.
    plain_turn, plain = _child(world, cid, cy, "implement it")
    _run(world, cid, plain_turn, cy, "implement it", plain)

    def started(e):
        return [a for a in cv.history(caused_by=e)
                if a["act"] == "execution-started"][-1]["detail"]

    assert (started(exp).get("requires_from")
            == started(plain).get("requires_from"))
    assert started(exp).get("requires") == started(plain).get("requires")


def test_a_resumed_run_is_given_the_same_step(world, flow):
    cv = world["cv"]
    cid = a_conversation(world, "Build")
    bob = cv.create_participant("@Bob")
    turn, exp = _child(world, cid, bob, "implement it",
                       f"{flow['entry']}#verify")
    _run(world, cid, turn, bob, "implement it", exp)
    # Run again on the same request, with only the resumed work text -- as
    # `_resume` dispatches it -- and on a fresh session.
    _run(world, cid, turn, bob, "resumed: carry on with what is open", exp,
         new_instance=True)
    row = _row(world, flow["entry"], "verify")
    assert len(flow["prompts"]) == 2
    for prompt in flow["prompts"]:
        assert f"Your step in this Workflow (verify): {row['what']}" in prompt
    assert len([s for s in _sources(world, bob) if s.get("activity")]) == 2


def test_a_picked_up_label_is_read_from_the_assignment(world, flow):
    cv = world["cv"]
    cid = a_conversation(world, "Build")
    bob = cv.create_participant("@Bob")
    turn, exp = _child(world, cid, bob, "take it")
    # A pick-up of discovered work says the activity on its assignment.
    cv.assign(exp, bob, by=world["who"]["@brian"], because="picked up",
              detail={"activity": f"{flow['entry']}#integrate"})
    assert cv.activity_named(exp) == f"{flow['entry']}#integrate"
    _run(world, cid, turn, bob, "take it", exp)
    row = _row(world, flow["entry"], "integrate")
    assert (f"Your step in this Workflow (integrate): {row['what']}"
            in flow["prompts"][-1])


def test_a_superseded_workflow_gives_its_current_step(world, flow):
    c = world["state"].corpus
    old = flow["entry"]
    body = dict(c.read([old])[0]["body"])
    body["activities"] = [dict(r, what="Build it, revised.")
                          if r["key"] == "implement" else r
                          for r in body["activities"]]
    new = c.create_and_establish(kind="workflow", body=body,
                                 attributed_to=world["who"]["@brian"])
    c.write(body={"reason": "owner revised"},
            attributed_to=world["who"]["@brian"],
            link={"from": new, "to": old,
                  "relation": c.superseding_relation()})
    cv = world["cv"]
    cid = a_conversation(world, "Build")
    bob = cv.create_participant("@Bob")
    turn, exp = _child(world, cid, bob, "implement it", f"{old}#implement")
    _run(world, cid, turn, bob, "implement it", exp)
    prompt = flow["prompts"][-1]
    assert "Your step in this Workflow (implement): Build it, revised." in prompt
    step = [s for s in _sources(world, bob) if s.get("activity")]
    assert [(s["source_id"], s["activity"]) for s in step] == [
        (new, f"{new}#implement")]
    # The composition says the named version was replaced.
    comp = cv.compose(conversation=cid, participant=bob,
                      activity=f"{old}#implement")
    assert {"source_id": old, "why": "superseded", "delivered_instead": new} \
        .items() <= next(w for w in comp.withheld
                         if w.get("source_id") == old).items()


def test_a_workflow_that_does_not_stand_gives_no_step(world, flow):
    c, cv = world["state"].corpus, world["cv"]
    body = dict(c.read([flow["entry"]])[0]["body"], name="Never adopted")
    candidate = c.write(kind="workflow", body=body,
                        attributed_to=world["who"]["@brian"])
    cid = a_conversation(world, "Build")
    bob = cv.create_participant("@Bob")
    comp = cv.compose(conversation=cid, participant=bob,
                      activity=f"{candidate}#implement")
    assert not any(c_.activity for c_ in comp.components)
    why = next(w for w in comp.withheld if w.get("source_id") == candidate)
    assert "no standing version" in why["why"]
    # And an activity its standing version does not have.
    comp = cv.compose(conversation=cid, participant=bob,
                      activity=f"{flow['entry']}#no-such-step")
    assert not any(c_.activity for c_ in comp.components)
    assert any("no activity keyed" in w["why"] for w in comp.withheld)


def test_a_run_without_an_activity_is_unchanged(world, flow):
    cv = world["cv"]
    cid = a_conversation(world, "Build")
    bob = cv.create_participant("@Bob")
    turn, exp = _child(world, cid, bob, "implement it")
    assert cv.activity_named(exp) is None
    before = cv.compose(conversation=cid, participant=bob, question="x")
    after = cv.compose(conversation=cid, participant=bob, question="x",
                       activity=None)
    assert before.payload() == after.payload()
    assert before.sources() == after.sources()
    assert before.withheld == after.withheld
    _run(world, cid, turn, bob, "implement it", exp)
    assert "Your step in this Workflow" not in flow["prompts"][-1]
    assert not any("activity" in s for s in _sources(world, bob))
