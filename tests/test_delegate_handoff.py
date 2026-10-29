"""Every dispatched run can hand work on; nothing else about authority moves.

THE FAILURE THIS EXISTS FOR, repeated in real use. A run addressed by name, or
delegated to, was dispatched as ordinary work. When its work needed another
role it could not involve one -- `delegate` was organising -- and was told to
"return that need", which nothing ever picked up. Caretaker could not hand
implementation to Builder; a delegated specialist could not hand review on.

What holds now, checked through the real dispatch path:

  * every dispatched scope holds `delegate`, and a Scratch answer still does not;
  * no other organising operation reaches an ordinary run;
  * a delegated run can delegate again, as deep as the work goes, each child
    caused by the request it came from and recorded as permitted;
  * the existing checks still bound it: this Conversation only, and picking up
    discovered work stays organising.

Whether a role SHOULD hand something on is its Persona's to say. Nothing here
encodes which role hands what to whom.
"""

from __future__ import annotations

import pytest

from tests._loop import a_conversation, say, world  # noqa: F401
from tests._loop import runs  # noqa: F401


def test_every_dispatched_scope_may_hand_work_on_and_nothing_more():
    from mentis.worker import (HANDS_OFF, ORGANISES, TRANSIENT_SCOPE,
                               permitted)
    organising = set(ORGANISES) - set(HANDS_OFF)
    for scope in ("worker", None, "", "unrecognised"):
        got = set(permitted(scope))
        assert "delegate" in got, f"scope {scope!r} cannot hand work on"
        assert not (organising & got), (
            f"scope {scope!r} gained organising operations: {organising & got}")
    # A grant narrowed to other organising operations still hands work on.
    assert "delegate" in permitted("organising", ["respond"])
    assert "open_conversation" not in permitted("organising", ["respond"])
    # A Scratch answer has no tools of its own and leaves no mark.
    assert "delegate" not in permitted(TRANSIENT_SCOPE)


def _hand_on(world, grant, to, work, **more):
    """Delegate as the run holding `grant`, then dispatch as the door does."""
    import mentis.web as web
    from mentis.web import _surface
    from mentis.worker import _operate
    out = _operate(_surface(world["state"]), "delegate",
                   {"participant": to, "work": work, **more}, grant)
    web.dispatch_soon(world["state"], conversation=out["conversation"],
                      turn=out["turn"], participant=to, work=work,
                      expectation=out["expectation"])
    return out


def test_a_delegated_run_can_delegate_again_with_lineage_kept(world, runs):
    cv = world["cv"]
    ada = world["who"]["@Ada"]
    bob, cy = cv.create_participant("@Bob"), cv.create_participant("@Cy")
    cid = a_conversation(world)

    # The owner addresses Ada by name: ordinary work, no organising grant.
    asked = say(world, cid, "@Ada plan this", action="ask-participant",
                dispatch=[{"participant": ada, "work": "plan"}])
    top = asked["expectations"][0]
    grant = runs[-1]
    assert grant["scope"] == "worker"
    assert cv.authority_of(top)["act"] is None

    # Ada -> Bob -> Cy -> Ada: three hand-offs, every one an ordinary run.
    parent = top
    for to in (bob, cy, ada):
        out = _hand_on(world, grant, to, "the part that is theirs",
                       return_to_me=True)
        child = out["expectation"]
        assert cv._act(child)["caused_by"] == parent, "lineage was lost"
        assert cv.expectation_state(child)["expected_of"] == to
        assert cv.expectation_state(parent)["satisfied_by"] in (None, [], ()), (
            "handing work on answered the request it came from")
        # The child's own run. Others follow it here: the stopped run ends, and
        # `return_to_me` resumes whatever was waiting on it.
        grant = next(r for r in runs if r["expectation"] == child)
        assert grant["scope"] == "worker", "a hand-off conferred organising"
        started = [a for a in cv.history(caused_by=child)
                   if a["act"] == "execution-started"]
        assert started and "delegate" in (
            started[-1]["detail"]["authority"]["permitted"]), (
            "the start record does not say the run could hand work on")
        parent = child
    # Resumed or handed-to, no run in the chain was dispatched to organise.
    assert {r["scope"] for r in runs} == {"worker"}


def test_handing_on_is_still_bounded_by_the_existing_checks(world, runs):
    from mentis.web import _surface
    from mentis.worker import NotPermitted, _operate
    cv = world["cv"]
    ada, bob = world["who"]["@Ada"], cv.create_participant("@Bob")
    cid, elsewhere = a_conversation(world), a_conversation(world, "Elsewhere")

    say(world, cid, "@Ada look", action="ask-participant",
        dispatch=[{"participant": ada, "work": "look"}])
    grant = runs[-1]
    surface = _surface(world["state"])

    # Only in the Conversation it was dispatched into.
    with pytest.raises(NotPermitted, match="dispatched into"):
        _operate(surface, "delegate",
                 {"participant": bob, "work": "x", "conversation": elsewhere},
                 grant)
    # Never back to the person who asked.
    with pytest.raises(NotPermitted, match="requested by"):
        _operate(surface, "delegate",
                 {"participant": world["who"]["@brian"], "work": "x"}, grant)
    # Discovered work is not this run's to pick up.
    found = _operate(surface, "record_discovered_work",
                     {"work": "unrelated", "because": "not this work"}, grant)
    with pytest.raises(NotPermitted, match="widens"):
        _operate(surface, "delegate",
                 {"participant": bob, "work": "x",
                  "expectation": found["expectation"]}, grant)
    assert cv.expectation_state(found["expectation"])["unassigned"] is True


# -- the acceptance case: Caretaker's three mockups ---------------------------
#
# THE FAILURE, AS IT HAPPENED (Mentis UI/UX #380-#383). The owner asked
# @Caretaker, by name, to have Claude, Codex and Antigravity each make a
# mockup. Caretaker was ordinary work, made the Claude one, and recorded the
# other two as unassigned work for the owner to route. This replays it with
# only the runtimes replaced: Caretaker hands the two portions on through the
# real `/api/worker` door, under the grant its run was actually minted, and
# the owner does nothing more until Caretaker has been resumed.

@pytest.fixture()
def three_runtimes(world, monkeypatch):
    """Every runtime available (the service's FakeExecution lists claude,
    codex, antigravity and local), and every run ending as reported done. A
    run whose work says `[[hand-on]]` first makes the next queued set of
    delegations through the door with its own grant, as its MCP surface
    would."""
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
        ran.append({"grant": grant, "runtime": spec.backend,
                    "work": spec.prompt})
        if "[[hand-on]]" in spec.prompt and calls:
            for args in calls.pop(0):
                door(token, "delegate", args)
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn",
                         text="done: mockup", started_at=now, finished_at=now)

    script_every_backend(svc, perform)
    return {"ran": ran, "calls": calls}


def _dispatch_sent(world, expectation):
    """Run, through the real path, what was sent to be dispatched for this
    request -- by the owner's Turn, the door, or a resumption."""
    from mentis.web import dispatch as D
    spec = next(s for s in world["sent"] if s.get("expectation") == expectation)
    world["sent"].remove(spec)
    return D.dispatch(world["state"], **spec)


def _children(cv, parent):
    return [a for a in cv.history(caused_by=parent)
            if a["act"] == "expectation-recorded"]


def _started(cv, expectation):
    return [a for a in cv.history(caused_by=expectation)
            if a["act"] == "execution-started"][-1]


def test_caretaker_hands_two_mockups_to_codex_and_antigravity_unaided(
        world, three_runtimes):
    cv = world["cv"]
    owner = world["who"]["@brian"]
    caretaker = cv.create_participant("@Caretaker")
    codex = cv.create_participant("@Quill")
    antigravity = cv.create_participant("@Orbit")
    cid = a_conversation(world, "Mentis UI/UX")

    # The owner asks Caretaker BY NAME: ordinary work, no organising grant.
    asked = say(world, cid, "@Caretaker have Claude, Antigravity and Codex "
                            "each mock up the header",
                action="ask-participant",
                dispatch=[{"participant": caretaker,
                           "work": "three mockups [[hand-on]]"}])
    parent, request_turn = asked["expectations"][0], asked["turn"]
    assert cv.authority_of(parent)["act"] is None
    owners_acts = len(cv.history(actor=owner))

    # What Caretaker's run does with the tools it is shown.
    three_runtimes["calls"].append([
        {"participant": who, "work": f"the {rt} mockup", "runtime": rt,
         "constraint_basis": request_turn, "return_to_me": True}
        for who, rt in ((codex, "codex"), (antigravity, "antigravity"))])
    _dispatch_sent(world, parent)
    assert three_runtimes["ran"][0]["grant"]["scope"] == "worker"
    assert not three_runtimes["calls"], "Caretaker's hand-offs were not made"

    # Two children, each caused by Caretaker's request and carrying the
    # runtime the owner's Turn decided -- and the parent still owed.
    by_who = {cv.expectation_state(c["id"])["expected_of"]: c
              for c in _children(cv, parent)}
    assert set(by_who) == {codex, antigravity}
    for who, rt in ((codex, "codex"), (antigravity, "antigravity")):
        detail = by_who[who]["detail"]
        assert detail["constraints"]["runtime"] == rt
        assert detail["constraints"]["basis"] == request_turn
        assert detail["constraints"]["supplied_by"] == caretaker
        assert detail["returns_to"] == caretaker
    assert not cv.expectation_state(parent)["satisfied_by"]

    # The door sent both to run on the runtime named, and each ran as itself.
    for who, rt in ((codex, "codex"), (antigravity, "antigravity")):
        _dispatch_sent(world, by_who[who]["id"])
        assert three_runtimes["ran"][-1]["runtime"] == rt
        assert three_runtimes["ran"][-1]["grant"]["scope"] == "worker"
        started = _started(cv, by_who[who]["id"])
        assert started["actor"] == who
        assert started["runtime"] == rt
        assert started["detail"]["requested_runtime"] == rt
        assert started["detail"]["runtime_chosen_by_caller"] is True
        # And it could hand work on in turn: no depth at which this stops.
        assert "delegate" in started["detail"]["authority"]["permitted"]

    # Both returned, so Caretaker resumes on the SAME request, once.
    resumed = [a for a in cv.history(caused_by=parent)
               if a["act"] == "work-resumed"]
    assert len(resumed) == 1
    back = [s for s in world["sent"] if s.get("expectation") == parent]
    assert len(back) == 1 and back[0]["participant"] == caretaker
    _dispatch_sent(world, parent)
    assert three_runtimes["ran"][-1]["grant"]["expectation"] == parent

    # And none of it was the owner's act.
    assert len(cv.history(actor=owner)) == owners_acts, (
        "the owner had to act for the hand-off to happen")


def test_a_participant_named_like_a_runtime_does_not_choose_it(
        world, three_runtimes):
    """THE NAME IS NOT A RUNTIME SELECTOR. Handing work to `@Codex` without
    `runtime` leaves the runtime open, and selection makes its ordinary choice
    -- nothing is inferred from the alias. Meaning Codex is said with
    `runtime="codex"`."""
    from tests._loop import named_before_the_rule
    cv = world["cv"]
    caretaker = cv.create_participant("@Caretaker")
    # Named before such names were refused, as the live Brain's was.
    codex = named_before_the_rule(cv, "@Codex")
    cid = a_conversation(world)
    asked = say(world, cid, "@Caretaker get Codex on it",
                action="ask-participant",
                dispatch=[{"participant": caretaker,
                           "work": "hand it on [[hand-on]]"}])
    parent = asked["expectations"][0]
    three_runtimes["calls"].append([
        {"participant": codex, "work": "the mockup", "return_to_me": True}])
    _dispatch_sent(world, parent)

    child = _children(cv, parent)[0]
    assert not child["detail"].get("constraints")
    # Codex has just been used, so the ordinary rule (least recently
    # selected) cannot land on it -- only the name could.
    svc = world["state"].agents
    svc._last_selected["codex"] = max(svc._last_selected.values(),
                                      default=0) + 1
    _dispatch_sent(world, child["id"])
    started = _started(cv, child["id"])
    assert started["detail"]["requested_runtime"] is None
    assert started["detail"]["runtime_chosen_by_caller"] is False
    assert started["runtime"] != "codex", "the name chose the runtime"
    because = started["detail"]["selection_because"]
    assert "capacity ranking" in because and "least recently selected" in because, (
        "with no runtime named, selection's ordinary rule decides: capacity, "
        "then the least recently selected")
    assert "capacity is not an input" not in because
