"""A Participant's default gives way to independent review; `delegate` judges
a default by everything the child's run will require.

OWNER APPROVAL 2026-10-29 (runtime capacity audit, items 3 and 4):

  * explicitly named runtimes stay fixed; a conflict with review separation is
    disclosed -- on the run's record (`selection_inputs.disclosed`) and to the
    delegating carrier (`warnings` in `delegate`'s result);
  * a Participant's default runtime gives way when that is needed for
    independent-runtime review: unbound, so selection avoids the author's
    runtime, with the reason said and no `runtime-bound` act to the default;
  * automatic selection considers the delegated work's full requirements: a
    default lacking what the child's governed Discipline (named, or handed on
    by a Workflow activity) needs does not bind.

Checked through the real delegate operation and the real dispatch path, with
only the runs scripted (`tests/_loop.runs`).
"""

from __future__ import annotations

import pytest

from tests._loop import a_conversation, say, world  # noqa: F401
from tests._loop import runs  # noqa: F401


def _delegate(world, grant, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), "delegate", args, grant)


def _run(world, out):
    """Dispatch what `delegate` handed back, exactly as the door does."""
    from mentis.web import dispatch as D
    spec = out["dispatch"]
    return D.dispatch(world["state"], conversation=out["conversation"],
                      turn=spec.get("turn") or out["turn"],
                      participant=spec["participant"], work=spec["work"],
                      persona=spec.get("persona"), runtime=spec.get("runtime"),
                      model=spec.get("model"), effort=spec.get("effort"),
                      requires=spec.get("requires") or (),
                      expectation=out["expectation"])


def _started(cv, expectation):
    got = [a for a in cv.history(caused_by=expectation)
           if a["act"] == "execution-started"]
    assert got, "the run did not start"
    return got[-1]


def _bound(cv, expectation):
    from mentis.web.dispatch import RUNTIME_BOUND
    return [a for a in cv.history(caused_by=expectation)
            if a["act"] == RUNTIME_BOUND]


def _constraints(cv, expectation):
    return (cv._act(expectation)["detail"] or {}).get("constraints") or {}


@pytest.fixture()
def authored(world, runs):
    """Work @Ada ran on codex, a Reviewer Persona, a Builder Persona, and @Rev,
    whose review would be of Ada's work. Returns Ada's run's grant."""
    cv = world["cv"]
    ada = world["who"]["@Ada"]
    cid = a_conversation(world)
    asked = say(world, cid, "@Ada build it", action="ask-participant",
                dispatch=[{"participant": ada, "work": "build it",
                           "runtime": "codex"}])
    assert "error" not in asked, asked
    top = asked["expectations"][0]
    assert _started(cv, top)["runtime"] == "codex"
    return {"cid": cid, "top": top, "grant": runs[-1],
            "reviewer": cv.define_persona("Reviewer", "Review the work."),
            "builder": cv.define_persona("Builder", "Build the part."),
            "rev": cv.create_participant("@Rev"),
            "owner": world["who"]["@brian"]}


def test_a_reviewers_default_equal_to_the_authors_runtime_gives_way(
        world, authored):
    cv, a = world["cv"], authored
    cv.declare_runtime_default(a["rev"], "codex", by=a["owner"])
    out = _delegate(world, a["grant"], participant=a["rev"],
                    work="review the build", persona=a["reviewer"],
                    review_of=a["top"])
    # Not recorded on the child as its runtime, and nothing to warn about.
    assert not _constraints(cv, out["expectation"]).get("runtime")
    assert out["dispatch"]["runtime"] is None
    assert "warnings" not in out

    _run(world, out)
    started = _started(cv, out["expectation"])
    assert started["runtime"] != "codex", "the review ran on the author's runtime"
    because = started["detail"]["selection_because"]
    assert ("the participant's default codex yields: the reviewed work ran "
            "on codex") in because
    assert "avoided so the review runs on a different runtime" in because
    assert started["detail"]["selection_inputs"]["avoid"] == "codex"
    assert not _bound(cv, out["expectation"]), (
        "the record says the review was bound to the default it gave way to")


def test_a_default_declared_after_delegation_gives_way_at_dispatch(
        world, authored):
    """The third fixing point: `_dispatch` resolving the default itself."""
    cv, a = world["cv"], authored
    out = _delegate(world, a["grant"], participant=a["rev"],
                    work="review the build", persona=a["reviewer"],
                    review_of=a["top"])
    assert not _constraints(cv, out["expectation"])
    cv.declare_runtime_default(a["rev"], "codex", by=a["owner"])
    _run(world, out)
    started = _started(cv, out["expectation"])
    assert started["runtime"] != "codex"
    assert started["detail"]["runtime_source"] == "auto"
    assert "the participant's default codex yields" in (
        started["detail"]["selection_because"])
    assert not _bound(cv, out["expectation"])


def test_a_recorded_default_gives_way_once_the_reviewed_work_ran_there(
        world, authored):
    """A default recorded on the request (`participant-default`) before the
    reviewed work had run is still only a default: it yields at dispatch."""
    cv, a = world["cv"], authored
    bob = cv.create_participant("@Bob")
    built = _delegate(world, a["grant"], participant=bob, work="build part two",
                      runtime="codex")
    cv.declare_runtime_default(a["rev"], "codex", by=a["owner"])
    review = _delegate(world, a["grant"], participant=a["rev"],
                       work="review part two", persona=a["reviewer"],
                       review_of=built["expectation"])
    # Part two had not run, so nothing said to avoid codex: the default stood.
    got = _constraints(cv, review["expectation"])
    assert got["runtime"] == "codex" and got["source"] == "participant-default"
    _run(world, built)
    assert _started(cv, built["expectation"])["runtime"] == "codex"

    _run(world, review)
    started = _started(cv, review["expectation"])
    assert started["runtime"] != "codex"
    assert "the participant's default codex yields" in (
        started["detail"]["selection_because"])
    assert not _bound(cv, review["expectation"])


def test_a_default_that_differs_from_the_authors_runtime_is_kept(
        world, authored):
    cv, a = world["cv"], authored
    cv.declare_runtime_default(a["rev"], "claude", by=a["owner"])
    out = _delegate(world, a["grant"], participant=a["rev"],
                    work="review the build", persona=a["reviewer"],
                    review_of=a["top"])
    got = _constraints(cv, out["expectation"])
    assert got["runtime"] == "claude" and got["source"] == "participant-default"
    assert "warnings" not in out
    _run(world, out)
    started = _started(cv, out["expectation"])
    assert started["runtime"] == "claude"
    assert "yields" not in started["detail"]["selection_because"]
    assert not started["detail"]["selection_inputs"].get("disclosed")


def test_a_named_runtime_equal_to_the_authors_is_kept_and_disclosed(
        world, authored):
    cv, a = world["cv"], authored
    cv.declare_runtime_default(a["rev"], "claude", by=a["owner"])
    out = _delegate(world, a["grant"], participant=a["rev"],
                    work="review the build", persona=a["reviewer"],
                    review_of=a["top"], runtime="codex")
    got = _constraints(cv, out["expectation"])
    assert got["runtime"] == "codex" and got["source"] == "named"
    [warning] = out["warnings"]
    assert "codex" in warning and "not independent by runtime" in warning

    _run(world, out)
    started = _started(cv, out["expectation"])
    assert started["runtime"] == "codex", "a named runtime was substituted"
    [disclosed] = started["detail"]["selection_inputs"]["disclosed"]
    assert "the runtime the reviewed work ran on" in disclosed
    assert disclosed in started["detail"]["selection_because"]


def test_non_review_work_keeps_its_default(world, authored):
    cv, a = world["cv"], authored
    cv.declare_runtime_default(a["rev"], "codex", by=a["owner"])
    # The same lineage, worn as a Builder: not review, so nothing yields.
    out = _delegate(world, a["grant"], participant=a["rev"],
                    work="extend the build", persona=a["builder"],
                    review_of=a["top"])
    got = _constraints(cv, out["expectation"])
    assert got["runtime"] == "codex" and got["source"] == "participant-default"
    _run(world, out)
    started = _started(cv, out["expectation"])
    assert started["runtime"] == "codex"
    assert started["detail"]["runtime_source"] == "participant-default"
    assert "yields" not in started["detail"]["selection_because"]


# -- item 4: the full requirements --------------------------------------------

def _discipline(world, name, requires):
    return world["cv"].corpus.create_and_establish(
        kind="discipline", body={"name": name, "about": name, "text": "do it",
                                 "requires": list(requires)},
        attributed_to=world["who"]["@brian"])


@pytest.fixture()
def browser_only_on_claude(world):
    """Only claude declares `drive_browser`; codex does not."""
    for b in world["state"].agents.execution._backends:
        if b["id"] == "claude":
            b["capabilities"] = ["drive_browser"]


def test_a_default_lacking_a_governed_disciplines_requirement_does_not_bind(
        world, authored, browser_only_on_claude):
    cv, a = world["cv"], authored
    bob = cv.create_participant("@Bob")
    cv.declare_runtime_default(bob, "codex", by=a["owner"])
    needs = _discipline(world, "Check it in a browser", ["drive_browser"])
    out = _delegate(world, a["grant"], participant=bob, work="check the page",
                    governed=[needs])
    assert not _constraints(cv, out["expectation"]).get("runtime"), (
        "a default that cannot meet the Discipline's requirement was bound")
    _run(world, out)
    started = _started(cv, out["expectation"])
    assert started["runtime"] == "claude"
    assert "participant default codex not used" in (
        started["detail"]["selection_because"])


def test_a_default_lacking_a_workflow_activitys_requirement_does_not_bind(
        world, runs, browser_only_on_claude):
    cv = world["cv"]
    owner = world["who"]["@brian"]
    needs = _discipline(world, "Check it in a browser", ["drive_browser"])
    wf = cv.corpus.create_and_establish(
        kind="workflow",
        body={"name": "UI change", "about": "changing the UI",
              "text": "build, check",
              "activities": [{"key": "check", "what": "check the page",
                              "who": {"role": "a worker"},
                              "disciplines": [needs],
                              "done_when": "checked"}],
              "decisions": [], "done_when": "checked", "requires": []},
        attributed_to=owner)
    cid = a_conversation(world)
    asked = say(world, cid, "change the UI", action="ask-participant",
                dispatch=[{"participant": world["steward"], "work": "carry it",
                           "governed": [wf]}])
    assert "error" not in asked, asked
    grant = runs[-1]
    bob = cv.create_participant("@Bob")
    cv.declare_runtime_default(bob, "codex", by=owner)
    out = _delegate(world, grant, participant=bob, work="check the page",
                    activity=f"{wf}#check")
    assert cv.governed_named(out["expectation"]) == [needs]
    assert not _constraints(cv, out["expectation"]).get("runtime")
    _run(world, out)
    assert _started(cv, out["expectation"])["runtime"] == "claude"


def test_a_default_meeting_every_requirement_still_binds(
        world, authored, browser_only_on_claude):
    cv, a = world["cv"], authored
    bob = cv.create_participant("@Bob")
    cv.declare_runtime_default(bob, "claude", by=a["owner"])
    needs = _discipline(world, "Check it in a browser", ["drive_browser"])
    out = _delegate(world, a["grant"], participant=bob, work="check the page",
                    governed=[needs])
    got = _constraints(cv, out["expectation"])
    assert got["runtime"] == "claude" and got["source"] == "participant-default"
