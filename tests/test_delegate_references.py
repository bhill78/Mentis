"""Delegation by reference, and stated requirements over inferred ones.

THE FAILURES THIS EXISTS FOR (owner, 2026-10-30, from opr-49e8e40d7fa2).
Three planning-only Surface Tension briefs were refused before their runs
started, because `delegate` read "(npm run build)", "browser-test list" and
"no UI build" in them as needing a UI build and a browser. And every brief
copied or paraphrased the owner's request and amendments into itself, because
a delegated run was given nothing but the brief.

What holds now, through the real delegate and dispatch paths:

  * `requires` stated -- `[]` included -- is the answer; the brief's wording is
    read only when it is absent, and the carrier is told when it was;
  * a stated requirement is still enforced: a runtime known to lack it is not
    given the work;
  * a delegated run is told the original request and the posts its
    delegations referenced, by reference -- never a copy -- and a child of a
    child is told its ancestors' references without them being restated;
  * work a person asked for directly is told no such posts.
"""

from __future__ import annotations

import time

import pytest

from mentis.execution import RunResult
from tests._loop import (a_conversation, grant_of_run, say,  # noqa: F401
                         script_every_backend, world)

PLANNING = "PLANNING ONLY: read code, write the plan; no UI build, no browser."


@pytest.fixture()
def told(world, monkeypatch):
    """Dispatch for real; each run records its grant and prompt and stops."""
    import mentis.web as web
    from mentis.web import dispatch as D
    svc = world["state"].agents
    seen: list[dict] = []

    def stop(spec):
        seen.append({"grant": grant_of_run(svc, spec, world["state"].path),
                     "prompt": spec.prompt, "backend": spec.backend})
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=False, error_kind="test_stop",
                         error="stopped once the grant was minted",
                         started_at=now, finished_at=now)

    script_every_backend(svc, stop)
    monkeypatch.setattr(web, "dispatch_soon",
                        lambda st, **kw: D.dispatch(world["state"], **kw))
    return seen


def _owner_asks(world, told, work="@Ada plan this"):
    cid = a_conversation(world)
    ada = world["who"]["@Ada"]
    asked = say(world, cid, work, action="ask-participant",
                dispatch=[{"participant": ada, "work": "plan"}])
    return cid, asked["turn"], asked["expectations"][0], told[-1]["grant"]


def _delegate(world, grant, to, work, **more):
    """`delegate` as the run holding `grant`, then dispatched as the worker
    door dispatches it (`web._Handler`, the `spec = out.pop("dispatch")`
    path)."""
    import mentis.web as web
    from mentis.web import _surface
    from mentis.worker import _operate
    out = _operate(_surface(world["state"]), "delegate",
                   {"participant": to, "work": work, **more}, grant)
    spec = out["dispatch"]
    web.dispatch_soon(world["state"], conversation=out["conversation"],
                      turn=spec.get("turn") or out["turn"],
                      participant=spec["participant"], work=spec["work"],
                      persona=spec.get("persona"), runtime=spec.get("runtime"),
                      model=spec.get("model"), effort=spec.get("effort"),
                      requires=spec.get("requires") or (),
                      expectation=out["expectation"])
    return out


def _delegated(cv, child):
    return next(a for a in cv.history(turn=cv._act(child)["turn"])
                if a["act"] == "work-delegated" and child in (a["about"] or ()))


def _everyone_lacks_a_browser(world):
    """Every runtime known to lack `drive_browser`, as MARS reports codex's."""
    for b in world["state"].agents.execution._backends:
        b["lacks"] = {"drive_browser": "measured: cannot launch a browser"}


def _failed_before_start(cv, child):
    return [a for a in cv.history(caused_by=child)
            if a["act"] == "delivery-failed"]


# -- 1. stated requirements win over the brief's wording ---------------------

def test_an_empty_requires_is_an_answer_and_the_wording_is_not_read(world, told):
    cv = world["cv"]
    _everyone_lacks_a_browser(world)
    _, _, _, grant = _owner_asks(world, told)
    bob = cv.create_participant("@Bob")

    out = _delegate(world, grant, bob, PLANNING, requires=[])
    child = out["expectation"]
    assert cv._act(child)["detail"].get("requires") in (None, [], ())
    assert "requires_inferred" not in _delegated(cv, child)["detail"]
    assert not out.get("warnings")
    assert not _failed_before_start(cv, child), "a planning brief was refused"
    assert told[-1]["grant"]["expectation"] == child, "the child did not run"


def test_said_nothing_the_wording_is_read_and_the_carrier_is_told(world, told):
    """Unchanged where the delegation is silent, and now said at once."""
    cv = world["cv"]
    _everyone_lacks_a_browser(world)
    _, _, _, grant = _owner_asks(world, told)
    bob = cv.create_participant("@Bob")

    out = _delegate(world, grant, bob, PLANNING)
    child = out["expectation"]
    assert _delegated(cv, child)["detail"]["requires_inferred"] == [
        "build_ui", "drive_browser"]
    assert any("inferred from the brief" in w and "[] for none" in w
               for w in out.get("warnings") or ()), out.get("warnings")
    assert _failed_before_start(cv, child), (
        "the inferred requirement was not enforced")


def test_a_stated_requirement_is_kept_and_nothing_added_to_it(world, told):
    cv = world["cv"]
    _, _, _, grant = _owner_asks(world, told)
    bob = cv.create_participant("@Bob")
    out = _delegate(world, grant, bob, "run the Playwright browser tests",
                    requires=["call_mentis_tools"])
    child = out["expectation"]
    assert list(cv._act(child)["detail"]["requires"]) == ["call_mentis_tools"]
    assert "requires_inferred" not in _delegated(cv, child)["detail"]


def test_a_stated_requirement_is_still_enforced(world, told):
    """Stating replaces inference; it does not switch enforcement off."""
    cv = world["cv"]
    _everyone_lacks_a_browser(world)
    _, _, _, grant = _owner_asks(world, told)
    bob = cv.create_participant("@Bob")
    out = _delegate(world, grant, bob, "check it", requires=["drive_browser"])
    failed = _failed_before_start(cv, out["expectation"])
    assert failed and "drive_browser" in failed[-1]["because"]


def test_a_retried_run_is_held_to_what_was_stated(world, told):
    """`recorded_requires` reads the request, so every later run of it is
    held to the stated answer, never re-inferred."""
    from mentis.web.dispatch import recorded_requires
    cv = world["cv"]
    _, _, _, grant = _owner_asks(world, told)
    bob = cv.create_participant("@Bob")
    out = _delegate(world, grant, bob, PLANNING, requires=[])
    assert recorded_requires(cv, out["expectation"]) == []


# -- 2. posts by reference ----------------------------------------------------

def test_a_delegated_run_is_told_the_request_and_the_referenced_posts(world, told):
    cv = world["cv"]
    cid, request_turn, _, grant = _owner_asks(
        world, told, "@Ada plan the surface with these ten sections")
    owner = world["who"]["@brian"]
    amend = cv.say(cid, owner, [{"type": "text",
                                 "text": "Amendment: one universal magnet."}])
    bob = cv.create_participant("@Bob")

    out = _delegate(world, grant, bob, "write the plan", requires=[],
                    references=[amend])
    child = out["expectation"]
    assert cv._act(child)["detail"]["references"] == [amend]
    assert _delegated(cv, child)["detail"]["references"] == [amend]

    prompt = told[-1]["prompt"]
    assert "POSTS YOUR WORK ANSWERS TO" in prompt
    block = prompt.split("POSTS YOUR WORK ANSWERS TO", 1)[1]
    assert block.index(request_turn) < block.index(amend), "request first"
    assert "the original request" in block
    assert "referenced for this work" in block
    assert "@brian" in block and "grant nothing" in block
    # a reference, not the post: an opening to recognise it by, and resolve
    assert "Amendment: one universal magnet." in block
    assert "resolve" in block


def test_a_long_post_is_referenced_not_copied(world, told):
    cv = world["cv"]
    long = "Section one. " + "word " * 2000 + "THE TAIL NOBODY COPIED"
    cid, _, _, grant = _owner_asks(world, told, "@Ada plan this")
    spec = cv.say(cid, world["who"]["@brian"], [{"type": "text", "text": long}])
    bob = cv.create_participant("@Bob")
    _delegate(world, grant, bob, "write the plan", requires=[],
              references=[spec])
    prompt = told[-1]["prompt"]
    assert "THE TAIL NOBODY COPIED" not in prompt
    block = prompt.split("POSTS YOUR WORK ANSWERS TO", 1)[1]
    assert spec in block and "…" in block, "referenced by an opening"


def test_a_child_of_a_child_is_told_its_ancestors_references(world, told):
    cv = world["cv"]
    cid, request_turn, _, grant = _owner_asks(world, told)
    amend = cv.say(cid, world["who"]["@brian"],
                   [{"type": "text", "text": "and mobile too"}])
    later = cv.say(cid, world["who"]["@brian"],
                   [{"type": "text", "text": "and dark mode"}])
    bob, cy = cv.create_participant("@Bob"), cv.create_participant("@Cy")

    first = _delegate(world, grant, bob, "plan", requires=[],
                      references=[amend])
    bob_grant = told[-1]["grant"]
    assert bob_grant["expectation"] == first["expectation"]
    _delegate(world, bob_grant, cy, "review the plan", requires=[],
              references=[later, amend])
    block = told[-1]["prompt"].split("POSTS YOUR WORK ANSWERS TO", 1)[1]
    # the original request, then the furthest ancestor's, each once
    order = [block.index(request_turn), block.index(amend), block.index(later)]
    assert order == sorted(order)
    assert block.count(amend) == 1


def test_work_asked_for_directly_is_told_no_posts(world, told):
    _owner_asks(world, told)
    assert "POSTS YOUR WORK ANSWERS TO" not in told[-1]["prompt"]


def test_a_reference_that_is_not_a_turn_or_is_deleted_is_refused(world, told):
    from mentis.web import _surface
    from mentis.worker import NotPermitted, _operate
    cv = world["cv"]
    cid, _, _, grant = _owner_asks(world, told)
    bob = cv.create_participant("@Bob")
    surface = _surface(world["state"])
    with pytest.raises(NotPermitted, match="not a Turn"):
        _operate(surface, "delegate", {"participant": bob, "work": "x",
                                       "references": [bob]}, grant)
    with pytest.raises(NotPermitted, match="not a Turn"):
        _operate(surface, "delegate", {"participant": bob, "work": "x",
                                       "references": ["ent-nothing"]}, grant)
    from mentis.conversation.versions import delete
    gone = cv.say(cid, world["who"]["@brian"], [{"type": "text", "text": "x"}])
    deletion = delete(cv, gone, by=world["who"]["@brian"])
    for ref in (gone, deletion["deletion"]):
        with pytest.raises(NotPermitted):
            _operate(surface, "delegate", {"participant": bob, "work": "x",
                                           "references": [ref]}, grant)
    with pytest.raises(NotPermitted, match="more than 20"):
        _operate(surface, "delegate", {
            "participant": bob, "work": "x",
            "references": [cv.say(cid, world["who"]["@brian"],
                                  [{"type": "text", "text": str(i)}])
                           for i in range(21)]}, grant)


def test_a_post_deleted_after_it_was_referenced_is_said_to_be(world, told):
    from mentis.web.dispatch import posts_lines, referenced_posts
    cv = world["cv"]
    cid, _, _, grant = _owner_asks(world, told)
    amend = cv.say(cid, world["who"]["@brian"],
                   [{"type": "text", "text": "do this too"}])
    bob = cv.create_participant("@Bob")
    out = _delegate(world, grant, bob, "plan", requires=[], references=[amend])
    from mentis.conversation.versions import delete
    delete(cv, amend, by=world["who"]["@brian"])
    lines = posts_lines(referenced_posts(cv, out["expectation"]))
    assert "DELETED since it was referenced" in lines
    assert "do this too" not in lines


# -- from independent review --------------------------------------------------

def test_an_empty_requires_does_not_clear_what_governing_material_requires(
        world, told):
    """`[]` answers what the BRIEF needs; a Discipline the child is governed
    by still requires what it requires, and selection still enforces it."""
    cv = world["cv"]
    _everyone_lacks_a_browser(world)
    _, _, _, grant = _owner_asks(world, told)
    browse = world["state"].corpus.create_and_establish(
        kind="discipline", body={"name": "Look at it", "about": "always",
                                 "text": "check the page in a browser",
                                 "requires": ["drive_browser"]},
        attributed_to=world["who"]["@brian"])
    bob = cv.create_participant("@Bob")
    out = _delegate(world, grant, bob, "plan it", requires=[],
                    governed=[browse])
    failed = _failed_before_start(cv, out["expectation"])
    assert failed and "drive_browser" in failed[-1]["because"]


def test_a_picked_up_finding_is_not_told_another_parts_references(world, told):
    cv = world["cv"]
    from mentis.web import _surface
    from mentis.worker import _operate
    cid = a_conversation(world)
    ada, bob, cy = (world["who"]["@Ada"], cv.create_participant("@Bob"),
                    cv.create_participant("@Cy"))
    asked = say(world, cid, "@Ada plan this", action="ask-participant",
                dispatch=[{"participant": ada, "work": "plan",
                           "follow_up": "unrestricted"}])
    request_turn, grant = asked["turn"], told[-1]["grant"]
    bobs = cv.say(cid, world["who"]["@brian"],
                  [{"type": "text", "text": "for Bob's part only"}])
    mine = cv.say(cid, world["who"]["@brian"],
                  [{"type": "text", "text": "for the finding"}])
    _delegate(world, grant, bob, "plan", requires=[], references=[bobs])
    bob_grant = told[-1]["grant"]
    found = _operate(_surface(world["state"]), "record_discovered_work",
                     {"work": "side work", "because": "found it"}, bob_grant)
    out = _delegate(world, bob_grant, cy, "side work", requires=[],
                    expectation=found["expectation"], references=[mine])
    assert out.get("picked_up") is True
    block = told[-1]["prompt"].split("POSTS YOUR WORK ANSWERS TO", 1)[1]
    assert request_turn in block and mine in block
    assert bobs not in block, "a finding was told another part's amendment"
    picked = [a for a in cv.history(caused_by=found["expectation"])
              if a["act"] == "expectation-assigned"][-1]
    assert picked["detail"]["references"] == [mine]


def test_another_conversations_post_is_named_and_an_edit_is_said(world, told):
    from mentis.conversation.versions import edit
    from mentis.web.dispatch import posts_lines, referenced_posts
    cv = world["cv"]
    cid, _, _, grant = _owner_asks(world, told)
    there = a_conversation(world, "Elsewhere")
    far = cv.say(there, world["who"]["@brian"],
                 [{"type": "text", "text": "from elsewhere"}])
    near = cv.say(cid, world["who"]["@brian"],
                  [{"type": "text", "text": "first wording"}])
    bob = cv.create_participant("@Bob")
    out = _delegate(world, grant, bob, "plan", requires=[],
                    references=[far, near])
    edit(cv, near, by=world["who"]["@brian"], text="second wording")
    lines = posts_lines(referenced_posts(cv, out["expectation"]))
    far_line = next(ln for ln in lines.splitlines() if far in ln)
    assert '"Elsewhere"' in far_line and there in far_line
    near_line = next(ln for ln in lines.splitlines() if near in ln)
    assert "Elsewhere" not in near_line and "edited since" in near_line
    assert "second wording" in lines and "first wording" not in lines


def test_references_change_nothing_a_run_may_do_or_read(world, told):
    cv = world["cv"]
    cid, _, _, grant = _owner_asks(world, told)
    amend = cv.say(cid, world["who"]["@brian"],
                   [{"type": "text", "text": "deploy it too"}])
    bob, cy = cv.create_participant("@Bob"), cv.create_participant("@Cy")
    _delegate(world, grant, bob, "plan", requires=[])
    plain = told[-1]["grant"]
    _delegate(world, grant, cy, "plan", requires=[], references=[amend])
    referenced = told[-1]["grant"]
    for key in ("scope", "permitted", "operations", "delivered", "reach"):
        assert plain.get(key) == referenced.get(key), key
    assert "grant nothing" in told[-1]["prompt"]


def test_references_are_bounded_before_they_are_read(world, told, monkeypatch):
    from mentis.web import _surface
    from mentis.worker import NotPermitted, _operate
    cv = world["cv"]
    _, _, _, grant = _owner_asks(world, told)
    bob = cv.create_participant("@Bob")
    surface = _surface(world["state"])
    reads, real = [], type(surface.cv)._is_kind

    def counted(self, ref, *a):
        if str(ref).startswith("ent-0000"):
            reads.append(ref)
        return real(self, ref, *a)
    monkeypatch.setattr(type(surface.cv), "_is_kind", counted)
    with pytest.raises(NotPermitted, match="more than 20"):
        _operate(surface, "delegate", {
            "participant": bob, "work": "x",
            "references": [f"ent-{i:012d}" for i in range(10_000)]}, grant)
    assert not reads, "references were read before the bound"
    with pytest.raises(NotPermitted, match="a list"):
        monkeypatch.undo()
        _operate(surface, "delegate", {"participant": bob, "work": "x",
                                       "references": "ent-1"}, grant)
