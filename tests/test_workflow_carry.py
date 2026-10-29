"""A selected Workflow is carried through continuations of the same work, and
a resumed run is matched against the request's own words.

OWNER'S SCOPE ITEMS 6 AND 7 (2026-10-29), checked through the real posting
route, the real dispatch path and the real `/api/worker` door (only the run is
scripted):

  6. a post that continues a request, and names no `governed`, carries the
     Workflow(s) that request was selected with -- recorded as
     `governed_from: "continued"`; an explicit `[]` is respected; material
     that is not a Workflow is not carried. A resumed run still delivers the
     named Workflow in full, and a child delegated by activity from a carrier
     whose Workflow was only NAMED (no placement) carries its step, resumed
     or not.
  7. a resume is matched against the words of the post the request was asked
     on, not the generated "Resuming the work..." text, so a Workflow that
     reaches the work only through the whole-Brain conditional placement is
     delivered in full on the resume as on the first run. A first dispatch
     is matched against its work text exactly as before.
"""

from __future__ import annotations

import json
import time
import urllib.request

import pytest

from tests._loop import a_conversation, say, world  # noqa: F401

WF_TEXT = ("Plan the change, implement it in small steps, have it reviewed "
           "independently, then integrate it.")
STEP = "Your step in this Workflow (implement)"


# -- material ------------------------------------------------------------------

def _discipline(world, name="Targeted tests"):
    return world["cv"].corpus.create_and_establish(
        kind="discipline", body={"name": name, "about": name,
                                 "text": "run what you touched"},
        attributed_to=world["who"]["@brian"])


def _workflow(world, *, persona=None, disciplines=()):
    return world["cv"].corpus.create_and_establish(
        kind="workflow",
        body={"name": "Software change", "about": "changing software",
              "text": WF_TEXT,
              "activities": [
                  {"key": "implement", "what": "make the change",
                   "who": ({"persona": persona, "role": "a worker"}
                           if persona else {"role": "a worker"}),
                   "disciplines": list(disciplines),
                   "done_when": "committed and tested"},
                  {"key": "integrate", "what": "merge it",
                   "who": {"role": "the carrier"}, "done_when": "merged"}],
              "decisions": [], "done_when": "tested", "requires": []},
        attributed_to=world["who"]["@brian"])


#: A condition the generated resume text cannot meet by accident. The
#: owner's sheet's own condition (docs/governance/workflow-2026-10-29.json) is
#: met by the canned "Resuming the work..." lines themselves -- "change", and
#: "ent" (inside "implementing") from every reply id they list -- so with it
#: a resume usually got the Workflow by luck of words; with this one it did
#: not, which is the case item 7 corrects.
WHEN = "editing the tokenizer, grammar or error messages of the query parser"
PARSER = "fix the tokenizer in the query parser so its grammar errors read well"


def _place_conditionally(world, wf):
    """Placed as the owner's sheet places a Workflow: whole Brain,
    conditional."""
    world["cv"].place(wf, whole_brain=True, by=world["who"]["@brian"],
                      because="placed on a condition",
                      delivery="conditional", when=WHEN)


# -- runs ----------------------------------------------------------------------

@pytest.fixture()
def door(world):
    """Every run ends as reported done, recording its grant and prompt. A run
    whose prompt says `[[hand-on]]` first makes the next queued delegations
    through the real `/api/worker` door with its own grant."""
    from mentis.execution import RunResult
    from mentis.worker import CAPABILITY_HEADER
    from tests._loop import script_every_backend

    svc = world["state"].agents
    ran, calls = [], []

    def call(token, op, args):
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
                got = call(token, "delegate", args)
                assert got.get("ok"), got
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn",
                         text="done", started_at=now, finished_at=now)

    script_every_backend(svc, perform)
    return {"ran": ran, "calls": calls}


def _run_sent(world, expectation):
    """Dispatch, for real, what was queued for this request."""
    from mentis.web import dispatch as D
    spec = next(s for s in world["sent"] if s.get("expectation") == expectation)
    world["sent"].remove(spec)
    return spec, D.dispatch(world["state"], **spec)


def _children(cv, parent):
    return [a["id"] for a in cv.history(caused_by=parent)
            if a["act"] == "expectation-recorded"]


def _detail(cv, exp):
    return cv._act(exp)["detail"] or {}


def _ask(world, cid, text, **spec):
    out = say(world, cid, text, action="ask-participant",
              dispatch=[{"participant": world["steward"], **spec}])
    assert "error" not in out, out
    return out


def _continue(world, cid, asked, text="carry on with that", **spec):
    out = say(world, cid, text, replies_to=asked["turn"],
              action="ask-participant",
              dispatch=[{"participant": world["steward"], **spec}])
    assert "error" not in out, out
    return out["expectations"][0]


# -- item 6: a continuation carries the selected Workflow ----------------------

def test_a_continuation_inherits_the_named_workflow(world):
    cv = world["cv"]
    wf, disc = _workflow(world), _discipline(world)
    cid = a_conversation(world)
    asked = _ask(world, cid, "change the software", work="carry it",
                 governed=[wf, disc], coordinate=True)
    parent = asked["expectations"][0]
    again = _continue(world, cid, asked, work="carry on")
    assert cv._act(again)["caused_by"] == parent
    d = _detail(cv, again)
    # the Workflow, and only the Workflow, carried -- and said so
    assert d["governed"] == [wf]
    assert d["governed_from"] == "continued" and d["governed_continues"] == parent
    assert cv.governed_named(again) == [wf]
    # and a continuation of the continuation carries it on again
    third = _continue(world, cid, {"turn": cv._act(again)["turn"]},
                      work="and on")
    assert cv.governed_named(third) == [wf]
    assert _detail(cv, third)["governed_from"] == "continued"


def test_an_explicit_empty_governed_does_not_inherit(world):
    cv = world["cv"]
    wf = _workflow(world)
    cid = a_conversation(world)
    asked = _ask(world, cid, "change the software", work="carry it",
                 governed=[wf], coordinate=True)
    again = _continue(world, cid, asked, work="carry on", governed=[])
    assert cv._act(again)["caused_by"] == asked["expectations"][0]
    d = _detail(cv, again)
    assert d["governed"] == []
    assert "governed_from" not in d
    assert cv.governed_named(again) == []


def test_a_spec_naming_governed_material_is_not_joined_by_the_inherited(world):
    cv = world["cv"]
    wf, disc = _workflow(world), _discipline(world)
    cid = a_conversation(world)
    asked = _ask(world, cid, "change the software", work="carry it",
                 governed=[wf], coordinate=True)
    again = _continue(world, cid, asked, work="carry on", governed=[disc])
    d = _detail(cv, again)
    assert d["governed"] == [disc] and "governed_from" not in d


def test_non_workflow_governed_material_is_not_inherited(world):
    cv = world["cv"]
    disc = _discipline(world)
    cid = a_conversation(world)
    asked = _ask(world, cid, "change the software", work="carry it",
                 governed=[disc], coordinate=True)
    again = _continue(world, cid, asked, work="carry on")
    assert cv._act(again)["caused_by"] == asked["expectations"][0]
    d = _detail(cv, again)
    assert "governed" not in d and "governed_from" not in d
    assert cv.governed_named(again) == []


def test_a_reply_to_the_carriers_result_inherits_too(world, door):
    """`continued_request`: a reply to the same carrier's result, when the
    request it answered is no longer open authorised work, still says what
    it continues -- and so carries its Workflow, as it carries its runtime."""
    cv = world["cv"]
    wf = _workflow(world)
    cid = a_conversation(world)
    asked = _ask(world, cid, "change the software", work="carry it",
                 governed=[wf])
    first = asked["expectations"][0]
    _run_sent(world, first)
    returned = [a for a in cv.history() if a["act"] == "result-returned"
                and a["actor"] == world["steward"]]
    assert returned, "the run returned no result"
    result = returned[-1]
    out = say(world, cid, "now the next part", replies_to=result["turn"],
              action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "next"}])
    assert "error" not in out, out
    again = out["expectations"][0]
    from mentis.conversation.posting import continued_request
    assert continued_request(cv, result["turn"], world["steward"]) == first
    assert cv.governed_named(again) == [wf]
    assert _detail(cv, again)["governed_from"] == "continued"


# -- item 6: resumed runs and delegated steps keep it --------------------------

def test_a_resumed_run_still_delivers_the_named_workflow_in_full(world, door):
    cv = world["cv"]
    wf = _workflow(world)
    bob = cv.create_participant("@Bob")
    cid = a_conversation(world)
    asked = _ask(world, cid, "change the software", work="carry it",
                 governed=[wf], coordinate=True)
    # the continuation, which only inherited the Workflow, is the carrier
    again = _continue(world, cid, asked, work="carry on [[hand-on]]")
    door["calls"].append([{"participant": bob, "work": "a part",
                           "return_to_me": True}])
    _run_sent(world, again)
    assert WF_TEXT in door["ran"][-1]["prompt"]
    assert wf in door["ran"][-1]["grant"]["delivered"]
    (child,) = _children(cv, again)
    _run_sent(world, child)
    assert [a for a in cv.history(caused_by=again) if a["act"] == "work-resumed"]
    spec, _ = _run_sent(world, again)
    assert spec["work"].startswith("Resuming the work")
    assert WF_TEXT in door["ran"][-1]["prompt"], \
        "the resumed run lost the named Workflow"
    assert wf in door["ran"][-1]["grant"]["delivered"]


def test_a_child_delegated_by_activity_from_a_named_workflow_keeps_its_step(
        world, door):
    """The Workflow reached the carrier only by being named (inherited into
    the continuation) -- nothing places it -- and delegating one of its
    activities is accepted; the child is told its step, and told it again
    when it resumes."""
    cv = world["cv"]
    builder = cv.define_persona("Builder", "Build the part you are given.")
    wf = _workflow(world, persona=builder)
    from mentis.conversation import placements_now
    assert placements_now(cv.corpus, wf) == []
    bob, cy = cv.create_participant("@Bob"), cv.create_participant("@Cy")
    cid = a_conversation(world)
    asked = _ask(world, cid, "change the software", work="carry it",
                 governed=[wf], coordinate=True)
    again = _continue(world, cid, asked, work="carry on [[hand-on]]")
    door["calls"].append([{"participant": bob,
                           "work": "build part one [[hand-on]]",
                           "activity": f"{wf}#implement"}])
    door["calls"].append([{"participant": cy, "work": "a sub-part",
                           "return_to_me": True}])
    _run_sent(world, again)
    (child,) = _children(cv, again)
    assert cv.activity_named(child) == f"{wf}#implement"
    spec, _ = _run_sent(world, child)
    assert spec["persona"] == builder
    assert STEP in door["ran"][-1]["prompt"]
    assert WF_TEXT not in door["ran"][-1]["prompt"]
    (grandchild,) = _children(cv, child)
    _run_sent(world, grandchild)
    assert [a for a in cv.history(caused_by=child) if a["act"] == "work-resumed"]
    spec, _ = _run_sent(world, child)
    assert spec["work"].startswith("Resuming the work")
    assert spec["persona"] == builder
    assert STEP in door["ran"][-1]["prompt"], "the resumed child lost its step"


# -- item 7: a resume is matched against the request's own words ---------------

def test_a_resume_of_conditionally_placed_work_gets_the_workflow_in_full(
        world, door):
    from mentis.conversation.knowledge import meets
    cv = world["cv"]
    wf = _workflow(world)
    _place_conditionally(world, wf)
    bob = cv.create_participant("@Bob")
    cid = a_conversation(world)
    asked = _ask(world, cid, f"{PARSER} [[hand-on]]")
    parent = asked["expectations"][0]
    assert "governed" not in _detail(cv, parent)
    door["calls"].append([{"participant": bob, "work": "a part",
                           "return_to_me": True}])
    _run_sent(world, parent)
    assert WF_TEXT in door["ran"][-1]["prompt"], "the first run met the condition"
    (child,) = _children(cv, parent)
    _run_sent(world, child)
    spec, _ = _run_sent(world, parent)
    # the generic resume text does not meet the condition on its own: before
    # this was matched against the request's words, this run got a pointer
    assert spec["work"].startswith("Resuming the work")
    assert not meets(spec["work"], WHEN)
    prompt = door["ran"][-1]["prompt"]
    assert WF_TEXT in prompt, "the resumed run dropped the Workflow"
    assert spec.get("question") == f"{PARSER} [[hand-on]]"
    # the run is still told the resume text, unchanged
    assert spec["work"] in prompt


def test_a_first_dispatch_is_matched_against_its_work_as_before(world, door):
    """No `question` on an ordinary first dispatch: what it is told is what
    it is matched against, whatever the post's own words say."""
    cv = world["cv"]
    wf = _workflow(world)
    _place_conditionally(world, wf)
    cid = a_conversation(world)
    # the work meets the condition; the post's words do not
    met = _ask(world, cid, "hello there", work=PARSER)["expectations"][0]
    spec, _ = _run_sent(world, met)
    assert "question" not in spec
    assert WF_TEXT in door["ran"][-1]["prompt"]
    # the post's words meet the condition; the work does not
    unmet = _ask(world, cid, PARSER, work="say hello")["expectations"][0]
    spec, _ = _run_sent(world, unmet)
    assert "question" not in spec
    assert WF_TEXT not in door["ran"][-1]["prompt"]
    assert cv.governed_named(met) == [] and cv.governed_named(unmet) == []
