"""Delegating by activity gives the child its step's Persona and Disciplines.

OWNER RULING 2026-10-29: delegated Builders and Reviewers receive their step's
Persona and Disciplines. Before it, `delegate`'s `activity` was a label that
passed nothing on, and a carrier that did not name the Persona and Disciplines
by hand sent children with neither (#1026: ten delegations, Persona null) --
so `review_signal` had no Reviewer Persona to steer a review by.

What holds now, checked through the real dispatch path and the real door:

  * absent `persona` -> the activity's `who.persona`, at its current standing
    version (a superseded one resolves to its successor); none standing ->
    no Persona, and the result says why;
  * an explicit `persona` wins;
  * absent `governed` -> the activity's Disciplines; a list -> that list and
    then the activity's (order kept, nothing twice); `[]` -> none;
  * both write sites (a new child and a picked-up finding), with
    `persona_from` / `governed_from` on the delegation;
  * a resumed child keeps its Persona;
  * a delegation without `activity` is recorded exactly as before.

Who may delegate is untouched (tests/test_delegate_coordinate.py).
"""

from __future__ import annotations

import pytest

from tests._loop import a_conversation, say, world  # noqa: F401
from tests._loop import runs  # noqa: F401


# -- material ------------------------------------------------------------------

def _discipline(world, name, text="do it this way"):
    return world["cv"].corpus.create_and_establish(
        kind="discipline", body={"name": name, "about": name, "text": text},
        attributed_to=world["who"]["@brian"])


def _workflow(world, *, persona, disciplines):
    return world["cv"].corpus.create_and_establish(
        kind="workflow",
        body={"name": "Software change", "about": "changing software",
              "text": "plan, implement, review",
              "activities": [
                  {"key": "implement", "what": "make the change",
                   "who": {"persona": persona, "role": "a worker"},
                   "disciplines": list(disciplines),
                   "done_when": "committed and tested"},
                  {"key": "integrate", "what": "merge it",
                   "who": {"role": "the carrier"},
                   "done_when": "merged"}],
              "decisions": [], "done_when": "tested", "requires": []},
        attributed_to=world["who"]["@brian"])


def _supersede(world, old, new):
    corpus = world["cv"].corpus
    corpus.write(body={"reason": "revised"}, attributed_to=world["who"]["@brian"],
                 link={"from": new, "to": old,
                       "relation": corpus.superseding_relation()})
    assert corpus.stands(old)["superseded_by"]


@pytest.fixture()
def step(world, runs):
    """A Workflow whose `implement` step names a Builder and a Discipline,
    delivered to a real run of the steward: its grant, and the material."""
    cv = world["cv"]
    builder = cv.define_persona("Builder", "Build the part you are given.")
    tests_d = _discipline(world, "Targeted tests")
    wf = _workflow(world, persona=builder, disciplines=[tests_d])
    cid = a_conversation(world)
    out = say(world, cid, "change the software", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "carry it",
                         "governed": [wf], "coordinate": True}])
    assert "error" not in out, out
    grant = runs[-1]
    assert wf in grant["delivered"], "the Workflow was not delivered"
    bob = cv.create_participant("@Bob")
    cv.join(bob, cid, attributed_to=world["who"]["@brian"])
    return {"cid": cid, "grant": grant, "wf": wf, "builder": builder,
            "discipline": tests_d, "bob": bob,
            "parent": out["expectations"][0]}


def _delegate(world, grant, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), "delegate", args, grant)


def _delegated(cv, out):
    return cv._act(out["delegation"])["detail"]


def _child(cv, out):
    return cv._act(out["expectation"])["detail"]


# -- Persona -------------------------------------------------------------------

def test_absent_persona_and_governed_are_filled_from_the_activity(world, step):
    cv = world["cv"]
    out = _delegate(world, step["grant"], participant=step["bob"],
                    work="build part one", activity=f"{step['wf']}#implement")
    # set on the dispatch the door sends, which is what review_signal reads
    assert out["dispatch"]["persona"] == step["builder"]
    assert _child(cv, out)["governed"] == [step["discipline"]]
    assert cv.governed_named(out["expectation"]) == [step["discipline"]]
    d = _delegated(cv, out)
    assert d["persona"] == step["builder"]
    assert d["activity"] == f"{step['wf']}#implement"
    assert d["persona_from"] == "activity"
    assert d["governed_from"] == "activity"
    assert out["persona_from"] == "activity"
    assert "persona_unresolved" not in out


def test_an_explicit_persona_wins_over_the_activity(world, step):
    cv = world["cv"]
    reviewer = cv.define_persona("Independent Reviewer", "Review it.")
    out = _delegate(world, step["grant"], participant=step["bob"],
                    work="review part one", persona=reviewer,
                    activity=f"{step['wf']}#implement")
    assert out["dispatch"]["persona"] == reviewer
    d = _delegated(cv, out)
    assert d["persona"] == reviewer and d["persona_from"] == "caller"
    # what the caller did not say is still the activity's
    assert _child(cv, out)["governed"] == [step["discipline"]]
    assert d["governed_from"] == "activity"


def test_a_superseded_activity_persona_and_discipline_resolve_to_successors(
        world, step):
    cv = world["cv"]
    builder2 = cv.define_persona("Builder", "Build the part, and test it.")
    _supersede(world, step["builder"], builder2)
    d2 = _discipline(world, "Targeted tests", "run what you touched")
    _supersede(world, step["discipline"], d2)
    out = _delegate(world, step["grant"], participant=step["bob"],
                    work="build part one", activity=f"{step['wf']}#implement")
    assert out["dispatch"]["persona"] == builder2
    assert _child(cv, out)["governed"] == [d2]


def test_no_standing_persona_delegates_without_one_and_says_why(world, runs):
    cv = world["cv"]
    proposed = cv.propose_persona("Builder", "never established")
    disc = _discipline(world, "Targeted tests")
    wf = _workflow(world, persona=proposed, disciplines=[disc])
    cid = a_conversation(world)
    say(world, cid, "change it", action="ask-participant",
        dispatch=[{"participant": world["steward"], "work": "carry it",
                   "governed": [wf]}])
    grant = runs[-1]
    bob = cv.create_participant("@Bob")
    out = _delegate(world, grant, participant=bob, work="build",
                    activity=f"{wf}#implement")
    assert out["dispatch"]["persona"] is None
    assert "no standing version" in out["persona_unresolved"]
    assert proposed in out["persona_unresolved"]
    d = _delegated(cv, out)
    assert d["persona"] is None and d["persona_from"] is None
    assert d["persona_unresolved"] == out["persona_unresolved"]
    # the Disciplines still go with it
    assert _child(cv, out)["governed"] == [disc]


def test_an_activity_naming_no_persona_gives_none_and_no_disciplines(
        world, step):
    cv = world["cv"]
    out = _delegate(world, step["grant"], participant=step["bob"],
                    work="merge", activity=f"{step['wf']}#integrate")
    assert out["dispatch"]["persona"] is None
    assert "persona_unresolved" not in out
    # nothing to add, so nothing was said about governed material
    assert "governed" not in _child(cv, out)
    d = _delegated(cv, out)
    assert d["persona_from"] is None and d["governed_from"] is None


# -- Disciplines ---------------------------------------------------------------

def test_a_governed_list_is_joined_by_the_activitys_disciplines(world, step):
    cv = world["cv"]
    other = _discipline(world, "Small commits")
    out = _delegate(world, step["grant"], participant=step["bob"],
                    work="build", governed=[other],
                    activity=f"{step['wf']}#implement")
    assert _child(cv, out)["governed"] == [other, step["discipline"]]
    assert _delegated(cv, out)["governed_from"] == "caller and activity"
    # named already: kept where the caller put it, never twice
    out = _delegate(world, step["grant"], participant=step["bob"],
                    work="build", governed=[step["discipline"], other],
                    activity=f"{step['wf']}#implement")
    assert _child(cv, out)["governed"] == [step["discipline"], other]
    assert _delegated(cv, out)["governed_from"] == "caller"


def test_an_explicit_empty_governed_means_none(world, step):
    cv = world["cv"]
    out = _delegate(world, step["grant"], participant=step["bob"],
                    work="build", governed=[],
                    activity=f"{step['wf']}#implement")
    assert _child(cv, out)["governed"] == []
    assert cv.governed_named(out["expectation"]) == []
    d = _delegated(cv, out)
    assert d["governed_from"] == "caller"
    # the Persona is a separate answer, still the activity's
    assert d["persona"] == step["builder"]


def test_a_workflow_is_still_not_handed_on_in_governed(world, step):
    from mentis.worker import NotPermitted
    with pytest.raises(NotPermitted, match="procedure with activities"):
        _delegate(world, step["grant"], participant=step["bob"],
                  work="build", governed=[step["wf"]],
                  activity=f"{step['wf']}#implement")


# -- the pick-up write site ----------------------------------------------------

def test_picked_up_work_by_activity_gets_the_step_too(world, step):
    from mentis.web import _surface
    from mentis.worker import _operate
    from tests.gravity_choice import owner_chooses
    cv = world["cv"]
    found = _operate(_surface(world["state"]), "record_discovered_work",
                     {"work": "found on the way", "because": "not this work"},
                     step["grant"])["expectation"]
    owner_chooses(_surface(world["state"]), step["grant"], found)
    out = _delegate(world, step["grant"], participant=step["bob"],
                    work="take it", expectation=found,
                    activity=f"{step['wf']}#implement")
    assert out["picked_up"] is True
    assert out["dispatch"]["persona"] == step["builder"]
    assert cv.governed_named(found) == [step["discipline"]]
    d = _delegated(cv, out)
    assert d["persona_from"] == "activity" and d["governed_from"] == "activity"
    from mentis.web.dispatch import delegated_persona
    assert delegated_persona(cv, found) == step["builder"]


# -- the door and the resumed child --------------------------------------------

@pytest.fixture()
def door_runs(world, monkeypatch):
    """Every run ends as reported done. A run whose work says `[[hand-on]]`
    first makes the next queued delegations through the real `/api/worker`
    door with its own grant (as in test_delegate_handoff)."""
    import json
    import time
    import urllib.request

    from mentis.execution import RunResult
    from mentis.worker import CAPABILITY_HEADER
    from tests._loop import script_every_backend

    svc = world["state"].agents
    ran, calls = [], []

    def door(token, op, args):
        req = urllib.request.Request(
            world["base"] + "/api/worker", method="POST",
            data=json.dumps({"op": op, "args": args}).encode(),
            headers={"Content-Type": "application/json",
                     CAPABILITY_HEADER: token})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    def perform(spec):
        token = svc.authority.grant_of(spec.run_id)
        grant = svc.authority.grant_for(token, world["state"].path)
        ran.append({"grant": grant, "prompt": spec.prompt})
        if "[[hand-on]]" in spec.prompt and calls:
            for args in calls.pop(0):
                door(token, "delegate", args)
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn",
                         text="done", started_at=now, finished_at=now)

    script_every_backend(svc, perform)
    return {"ran": ran, "calls": calls}


def _dispatch_sent(world, expectation):
    from mentis.web import dispatch as D
    spec = next(s for s in world["sent"] if s.get("expectation") == expectation)
    world["sent"].remove(spec)
    return spec, D.dispatch(world["state"], **spec)


def test_a_resumed_child_keeps_its_activity_persona(world, door_runs):
    cv = world["cv"]
    builder = cv.define_persona("Builder", "Build the part you are given.")
    disc = _discipline(world, "Targeted tests")
    wf = _workflow(world, persona=builder, disciplines=[disc])
    bob, cy = cv.create_participant("@Bob"), cv.create_participant("@Cy")
    cid = a_conversation(world)
    asked = say(world, cid, "change the software", action="ask-participant",
                dispatch=[{"participant": world["steward"],
                           "work": "carry it [[hand-on]]", "governed": [wf]}])
    parent = asked["expectations"][0]
    door_runs["calls"].append([{"participant": bob,
                                "work": "build part one [[hand-on]]",
                                "activity": f"{wf}#implement"}])
    door_runs["calls"].append([{"participant": cy, "work": "a sub-part",
                                "return_to_me": True}])
    _dispatch_sent(world, parent)
    child = next(a["id"] for a in cv.history(caused_by=parent)
                 if a["act"] == "expectation-recorded")
    # the door sent the child wearing the activity's Persona
    spec, _ = _dispatch_sent(world, child)
    assert spec["persona"] == builder
    grandchild = next(a["id"] for a in cv.history(caused_by=child)
                      if a["act"] == "expectation-recorded")
    _dispatch_sent(world, grandchild)
    # Cy returned, so Bob's request resumes -- still as the Builder
    assert [a for a in cv.history(caused_by=child)
            if a["act"] == "work-resumed"]
    spec, _ = _dispatch_sent(world, child)
    assert spec["persona"] == builder, "the resumed child lost its Persona"
    started = [a for a in cv.history(caused_by=child)
               if a["act"] == "execution-started"]
    assert len(started) == 2


def test_a_resumed_carrier_keeps_the_persona_the_owner_chose(world, door_runs):
    """Found by dispatching for real: the owner posted to @Caretaker as the
    Caretaker Persona; when its children returned, it resumed wearing none."""
    cv = world["cv"]
    care = cv.define_persona("Caretaker", "Carry the work to completion.")
    bob = cv.create_participant("@Bob")
    cid = a_conversation(world)
    asked = say(world, cid, "change the software", action="ask-participant",
                dispatch=[{"participant": world["steward"], "persona": care,
                           "work": "carry it [[hand-on]]"}])
    parent = asked["expectations"][0]
    door_runs["calls"].append([{"participant": bob, "work": "build part one",
                                "return_to_me": True}])
    spec, _ = _dispatch_sent(world, parent)
    assert spec["persona"] == care
    child = next(a["id"] for a in cv.history(caused_by=parent)
                 if a["act"] == "expectation-recorded")
    _dispatch_sent(world, child)
    assert [a for a in cv.history(caused_by=parent) if a["act"] == "work-resumed"]
    spec, _ = _dispatch_sent(world, parent)
    assert spec["persona"] == care, "the resumed carrier lost the Persona the owner chose"


# -- without an activity, nothing changes --------------------------------------

def test_a_delegation_without_activity_is_exactly_as_it_was(world, step):
    cv = world["cv"]
    out = _delegate(world, step["grant"], participant=step["bob"],
                    work="build part one")
    assert out["dispatch"]["persona"] is None
    assert not {"persona_from", "governed_from", "persona_unresolved",
                "disciplines_withheld"} & set(out)
    assert "governed" not in _child(cv, out)
    assert "activity" not in _child(cv, out)
    assert set(_delegated(cv, out)) == {
        "participant", "persona", "artifacts", "reach", "restricted",
        "constraints", "return_expected"}
    # and naming them by hand is what it always was
    out = _delegate(world, step["grant"], participant=step["bob"],
                    work="build", persona=step["builder"], governed=[])
    assert out["dispatch"]["persona"] == step["builder"]
    assert _child(cv, out)["governed"] == []
    assert "persona_from" not in _delegated(cv, out)
