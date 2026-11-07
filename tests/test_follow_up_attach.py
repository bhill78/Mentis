"""The owner's follow-up about work already being carried reaches that work's one coordinator.

THE DELAY THIS EXISTS FOR (Quiet Chat round 5, 2026-11-07). The owner's wrap-up arrived as a new
request while the round's carrier had Builders out. A second carrier ran beside the first: it
waited 54 minutes for a Builder it did not need, both carriers resumed when that Builder returned,
both integrated, and the owner was told "ready" three times. The owner's later STOP reached
neither: the first carrier's run had begun before it, and handed out a full regression three
minutes after it.

What holds now, through the real Ask Mentis, attach_follow_up, delegate, dispatch and posting:

  * a new request's carrier is told what the same person already has being carried there, and
    hands a follow-up about it to that work (`attach_follow_up`) -- the new request is recorded
    as carried under it, and nobody coordinates it twice;
  * the work's carrier is resumed with the follow-up at once, while its Builders still run, and
    told what is still outstanding (scenario A, a wrap-up during parallel development);
  * a follow-up handed over while the carrier is running is shown to that run before it hands
    anything on, and nothing is delegated then (scenario B, STOP supersedes); a run that hands
    nothing on is resumed with it when it ends -- once;
  * children still return as before: each resumption is claimed once.
"""

from __future__ import annotations

import threading
import time

import pytest

from mentis.execution import RunResult
from mentis.web import dispatch as D
from tests._loop import (a_conversation, grant_of_run, say,  # noqa: F401
                         script_every_backend, world)
from tests.test_delegate_coordinate import _present

WRAP_UP = "Wrap up: give me a usable preview of what is finished. Start nothing new."
STOP = "STOP: no further development, no full regression, no deployment preparation."


@pytest.fixture()
def team(world):
    """Runs complete as the test says, by the expectation they carry: each run of an expectation
    in `on_run` first calls its next function with the run's own grant; one in `hold` waits on its
    gate. Every run returns."""
    svc = world["state"].agents
    plan = {"on_run": {}, "hold": {}, "results": []}

    def perform(spec):
        grant = grant_of_run(svc, spec, world["state"].path)
        queue = plan["on_run"].get(grant["expectation"]) or []
        if queue:
            plan["results"].append(queue.pop(0)(grant))
        gate = plan["hold"].get(grant["expectation"])
        if gate is not None:
            gate.wait(timeout=120)
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done: here is what I did",
                         started_at=now, finished_at=now)

    script_every_backend(svc, perform)
    return plan


def _op(world, grant, name, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), name, args, grant)


def _ask_mentis(world, cid, words):
    """The owner posts to nobody: Ask Mentis. Its carrier's dispatch is captured, not run."""
    out = say(world, cid, words, action="ask-mentis")
    assert "error" not in out, out
    return out["expectation"]


def _spec(world, expectation):
    """The captured dispatch of `expectation`, taken out of what was sent."""
    spec = next(k for k in reversed(world["sent"]) if k["expectation"] == expectation)
    world["sent"].remove(spec)
    return spec


def _run(world, expectation):
    D.dispatch(world["state"], **_spec(world, expectation))


def _start(world, team, part):
    """Run a delegated part on a thread, held at its gate until released."""
    expectation = part["expectation"]
    gate = threading.Event()
    team["hold"][expectation] = gate
    spec = dict(conversation=part["conversation"], turn=part["turn"],
                participant=part["participant"], work=part["dispatch"]["work"],
                expectation=expectation)
    t = threading.Thread(target=D.dispatch, args=(world["state"],), kwargs=spec)
    t.start()
    deadline = time.time() + 20
    while not world["cv"].expectation_state(expectation)["live_execution"]:
        assert time.time() < deadline, f"{expectation} never started"
        time.sleep(0.05)
    return t, gate


def _resumes(cv, expectation):
    return [a for a in cv.history(caused_by=expectation) if a["act"] == "work-resumed"]


def _builders(world, cid, n):
    return [_present(world, cid, f"@Builder-{i}") for i in range(1, n + 1)]


def _round(world, team, cid, builders):
    """The owner asks for a round; its carrier's first run hands each Builder a part, returning
    to it, and ends. Returns the round's request and the parts' expectations."""
    work = _ask_mentis(world, cid, "Build the feature in parallel parts.")
    parts = []

    def hand_out(grant):
        for i, b in enumerate(builders):
            out = _op(world, grant, "delegate", participant=b, work=f"part {i + 1}",
                      return_to_me=True)
            assert "error" not in out, out
            parts.append({**out, "participant": b})
    team["on_run"][work] = [hand_out]
    _run(world, work)
    assert len(parts) == len(builders)
    return work, parts


def _attach_by_its_carrier(world, team, request, work):
    """The new request's carrier runs and hands it to `work`."""
    team["on_run"][request] = [lambda g: _op(world, g, "attach_follow_up", work=work,
                                             because="it wraps up that work")]
    _run(world, request)
    out = team["results"][-1]
    assert out.get("ok"), out
    return out


# -- A and C: a wrap-up while three Builders run --------------------------------------------------

def test_a_wrap_up_reaches_the_one_carrier_while_its_builders_still_run(world, team):
    cv = world["cv"]
    cid = a_conversation(world)
    builders = _builders(world, cid, 3)
    work, parts = _round(world, team, cid, builders)
    held = [_start(world, team, p) for p in parts]
    try:
        follow = _ask_mentis(world, cid, WRAP_UP)
        # the new request's carrier is told what is already being carried for the owner here
        brief = next(k for k in world["sent"] if k["expectation"] == follow)["work"]
        assert f"request {work}" in brief and "attach_follow_up" in brief
        world["sent"][:] = [k for k in world["sent"] if k["expectation"] == follow]

        out = _attach_by_its_carrier(world, team, follow, work)
        # the follow-up is carried under the work: met, and carried by nobody else
        state = cv.expectation_state(follow)
        assert state["satisfied_by"] and out["met"] in state["satisfied_by"]
        assert not [a for a in cv.history(caused_by=follow) if a["act"] == "work-delegated"]
        # ...and the work's carrier is resumed AT ONCE, with all three Builders still running
        resumed = _resumes(cv, work)
        assert len(resumed) == 1 and out["resumed"] == resumed[0]["id"]
        detail = resumed[0]["detail"]
        assert detail["follow_ups"] == [out["attached"]]
        assert sorted(detail["outstanding"]) == sorted(p["expectation"] for p in parts)
        assert detail["event"]["kind"] == "follow-up"
        sent = next(k for k in out["dispatches"] if k["expectation"] == work)
        assert "The owner gave a follow-up on this work" in sent["work"]
        assert WRAP_UP in sent["work"]
        assert "still outstanding" in sent["work"]
        # its status says where it went
        from mentis.operational.work import conversation_work
        item = next(i for i in conversation_work(cv, cid)["items"]
                    if i["expectation"] == follow)
        assert item["state"]["label"].startswith("Handed to the work it follows up"), item

        # the carrier's resumed run, and no second one beside it
        D.dispatch(world["state"], **sent)
        assert len(_resumes(cv, work)) == 1
        assert cv.claim_resumption(work, event={"kind": "again"}) is None
    finally:
        for _, gate in held:
            gate.set()
        for t, _ in held:
            t.join(60)
    # the parts were not delegated to be acted on alone, so they join: one more resumption
    resumed = _resumes(cv, work)
    assert len(resumed) == 2 and "follow_ups" not in resumed[-1]["detail"]
    assert cv.claim_resumption(work, event={"kind": "again"}) is None


def test_a_follow_up_is_handed_over_once(world, team):
    cv = world["cv"]
    cid = a_conversation(world)
    work, parts = _round(world, team, cid, _builders(world, cid, 1))
    t, gate = _start(world, team, parts[0])
    try:
        follow = _ask_mentis(world, cid, WRAP_UP)
        out = _attach_by_its_carrier(world, team, follow, work)
        assert out["resumed"]
        # resumed and not yet started: nothing resumes it again in that gap
        assert cv.claim_resumption(work, event={"kind": "again"}) is None
        D.dispatch(world["state"], **out["dispatches"][0])
        # its run ended, the Builder still runs, and the follow-up was handed over
        assert cv.claim_resumption(work, event={"kind": "again"}) is None
        assert len(_resumes(cv, work)) == 1
    finally:
        gate.set()
        t.join(60)
    assert len(_resumes(cv, work)) == 2


# -- B: STOP while the carrier is running ----------------------------------------------------------

def test_stop_given_while_the_carrier_runs_is_shown_before_it_hands_anything_on(world, team):
    cv = world["cv"]
    cid = a_conversation(world)
    builders = _builders(world, cid, 2)
    work = _ask_mentis(world, cid, "Build it, review it, then run the full regression.")
    begun, go = threading.Event(), threading.Event()
    seen = {}

    def runs_on(grant):
        seen["first"] = _op(world, grant, "delegate", participant=builders[0],
                            work="build it", return_to_me=True)
        begun.set()
        go.wait(timeout=60)
        # the plan this run was given says: full regression next
        seen["regression"] = _op(world, grant, "delegate", participant=builders[1],
                                 work="run the full regression", return_to_me=True)
    team["on_run"][work] = [runs_on]
    spec = _spec(world, work)
    t = threading.Thread(target=D.dispatch, args=(world["state"],), kwargs=spec)
    t.start()
    assert begun.wait(30)
    try:
        follow = _ask_mentis(world, cid, STOP)
        out = _attach_by_its_carrier(world, team, follow, work)
        # its carrier is running: nothing resumes it beside that run
        assert out["resumed"] is None and not out["dispatches"]
        assert not _resumes(cv, work)
    finally:
        go.set()
        t.join(60)
    # the delegation the old plan asked for was not made; the STOP was shown instead
    refused = seen["regression"]
    assert refused["delegated"] is False and refused["follow_ups"][0]["words"] == STOP
    assert [a for a in cv.history(caused_by=work)
            if a["act"] == "work-delegated"] == [cv._act(seen["first"]["delegation"])]
    shown = [a for a in cv.history(caused_by=work) if a["act"] == "follow-up-shown"]
    assert len(shown) == 1 and shown[0]["detail"]["follow_ups"] == [out["attached"]]
    # the run was shown it, so its ending hands it over to nobody again
    assert not _resumes(cv, work)
    assert cv.claim_resumption(work, event={"kind": "again"}) is None


def test_a_carrier_shown_the_follow_up_may_still_hand_on_what_it_still_needs(world, team):
    cv = world["cv"]
    cid = a_conversation(world)
    builder = _builders(world, cid, 1)[0]
    work = _ask_mentis(world, cid, "Build it.")
    begun, go = threading.Event(), threading.Event()
    seen = {}

    def runs_on(grant):
        begun.set()
        go.wait(timeout=60)
        seen["first"] = _op(world, grant, "delegate", participant=builder,
                            work="build the preview", return_to_me=True)
        seen["again"] = _op(world, grant, "delegate", participant=builder,
                            work="build the preview", return_to_me=True)
    team["on_run"][work] = [runs_on]
    spec = _spec(world, work)
    t = threading.Thread(target=D.dispatch, args=(world["state"],), kwargs=spec)
    t.start()
    assert begun.wait(30)
    try:
        _attach_by_its_carrier(world, team, _ask_mentis(world, cid, WRAP_UP), work)
    finally:
        go.set()
        t.join(60)
    assert seen["first"]["delegated"] is False
    assert "error" not in seen["again"] and seen["again"]["expectation"]
    assert cv._act(seen["again"]["expectation"])["caused_by"] == work


def test_a_run_that_hands_nothing_on_is_resumed_with_the_follow_up_when_it_ends(world, team):
    cv = world["cv"]
    cid = a_conversation(world)
    builder = _builders(world, cid, 1)[0]
    work = _ask_mentis(world, cid, "Build it.")
    begun, go = threading.Event(), threading.Event()
    parts = []

    def runs_on(grant):
        parts.append(_op(world, grant, "delegate", participant=builder, work="build it",
                         return_to_me=True)["expectation"])
        begun.set()
        go.wait(timeout=60)
    team["on_run"][work] = [runs_on]
    spec = _spec(world, work)
    t = threading.Thread(target=D.dispatch, args=(world["state"],), kwargs=spec)
    t.start()
    assert begun.wait(30)
    try:
        out = _attach_by_its_carrier(world, team, _ask_mentis(world, cid, STOP), work)
        assert out["resumed"] is None
    finally:
        go.set()
        t.join(60)
    # ended with its Builder still out: resumed once, with the STOP, the Builder outstanding
    resumed = _resumes(cv, work)
    assert len(resumed) == 1
    assert resumed[0]["detail"]["follow_ups"] == [out["attached"]]
    assert resumed[0]["detail"]["outstanding"] == parts
    assert cv.claim_resumption(work, event={"kind": "again"}) is None


# -- C: what is refused, and a separate request ----------------------------------------------------

def test_a_separate_request_stays_its_own(world, team):
    cv = world["cv"]
    cid = a_conversation(world)
    work, parts = _round(world, team, cid, _builders(world, cid, 1))
    other = _ask_mentis(world, cid, "Separately: summarise yesterday's notes.")
    # nothing ties them: the new request is its own, its carrier dispatched as before
    assert not cv.follow_ups(work)
    assert not cv.expectation_state(other)["satisfied_by"]
    assert any(k["expectation"] == other for k in world["sent"])


def test_what_a_follow_up_cannot_be_handed_to(world, team):
    cv = world["cv"]
    cid = a_conversation(world)
    work, parts = _round(world, team, cid, _builders(world, cid, 1))
    follow = _ask_mentis(world, cid, WRAP_UP)
    owner = world["who"]["@brian"]
    by = world["steward"]
    # work delegated under a request, the request itself, nothing at all
    assert "error" in cv.attach_follow_up(follow, parts[0]["expectation"], by=by)
    assert "error" in cv.attach_follow_up(follow, follow, by=by)
    assert "error" in cv.attach_follow_up(follow, "opr-nothing", by=by)
    # work in another Conversation
    elsewhere = a_conversation(world, "Elsewhere")
    there = _ask_mentis(world, elsewhere, "Something else entirely.")
    assert "error" in cv.attach_follow_up(follow, there, by=by)
    # work already claimed met
    cv.record_act(actor=owner, act="expectation-met", conversation=elsewhere,
                  turn=cv._act(there)["turn"], caused_by=there)
    later = _ask_mentis(world, elsewhere, "And one more thing about it.")
    assert "error" in cv.attach_follow_up(later, there, by=by)
    # a refusal wrote nothing
    assert not cv.follow_ups(work) and not cv.follow_ups(there)


def test_only_a_run_whose_request_may_coordinate_holds_it(world):
    from mentis.worker import ATTACH_FOLLOW_UP, AUTHORITY, permitted
    assert ATTACH_FOLLOW_UP in permitted("intake", AUTHORITY)
    assert ATTACH_FOLLOW_UP not in permitted("intake", [o for o in AUTHORITY
                                                        if o != "coordinate"])
    assert ATTACH_FOLLOW_UP not in permitted("worker")


# -- found by the independent review ---------------------------------------------------------------

def _live_run(world, team, work, during):
    """Run `work`'s captured dispatch on a thread; `during(grant)` is called once the test lets it
    go on, and its result kept. Returns (thread, go, seen)."""
    begun, go, seen = threading.Event(), threading.Event(), {}

    def runs_on(grant):
        begun.set()
        go.wait(timeout=60)
        seen["out"] = during(grant)
    team["on_run"][work] = [runs_on]
    spec = _spec(world, work)
    t = threading.Thread(target=D.dispatch, args=(world["state"],), kwargs=spec)
    t.start()
    assert begun.wait(30)
    return t, go, seen


def test_a_carrier_claiming_the_work_met_is_shown_the_follow_up_first(world, team):
    cv = world["cv"]
    cid = a_conversation(world)
    work = _ask_mentis(world, cid, "Build it.")
    t, go, seen = _live_run(world, team, work, lambda g: (
        _op(world, g, "respond", text="done", fulfils=True),
        _op(world, g, "respond", text="done, and I read the STOP", fulfils=True)))
    try:
        out = _attach_by_its_carrier(world, team, _ask_mentis(world, cid, STOP), work)
        assert out["resumed"] is None
    finally:
        go.set()
        t.join(60)
    first, second = seen["out"]
    assert first["ok"] is False and first["follow_ups"][0]["words"] == STOP
    assert "error" not in second and cv.expectation_state(work)["satisfied_by"]
    assert [a for a in cv.history(caused_by=work) if a["act"] == "follow-up-shown"]


def test_a_follow_up_given_before_the_first_run_starts_is_shown_to_it(world, team):
    cv = world["cv"]
    cid = a_conversation(world)
    builder = _builders(world, cid, 1)[0]
    work = _ask_mentis(world, cid, "Build it, then run the full regression.")
    # its first dispatch is queued and has not started when the STOP is handed over
    follow = _ask_mentis(world, cid, STOP)
    out = _attach_by_its_carrier(world, team, follow, work)
    assert out["resumed"] is None
    team["on_run"][work] = [lambda g: _op(world, g, "delegate", participant=builder,
                                          work="run the full regression",
                                          return_to_me=True)]
    _run(world, work)
    refused = team["results"][-1]
    assert refused["delegated"] is False and refused["follow_ups"][0]["words"] == STOP
    assert not [a for a in cv.history(caused_by=work) if a["act"] == "work-delegated"]


def test_a_resumed_run_given_the_follow_up_is_not_shown_it_again(world, team):
    cv = world["cv"]
    cid = a_conversation(world)
    builders = _builders(world, cid, 2)
    work, parts = _round(world, team, cid, builders[:1])
    t, gate = _start(world, team, parts[0])
    try:
        out = _attach_by_its_carrier(world, team, _ask_mentis(world, cid, WRAP_UP), work)
        team["on_run"][work] = [lambda g: _op(world, g, "delegate", participant=builders[1],
                                              work="integrate what is finished",
                                              return_to_me=True)]
        D.dispatch(world["state"], **out["dispatches"][0])
        made = team["results"][-1]
        assert "error" not in made and made.get("delegated") is not False, made
        assert cv._act(made["expectation"])["caused_by"] == work
    finally:
        gate.set()
        t.join(60)


def test_a_request_with_work_of_its_own_is_not_handed_on(world, team):
    cv = world["cv"]
    cid = a_conversation(world)
    work, _ = _round(world, team, cid, _builders(world, cid, 1))
    other, parts = _round(world, team, cid, _builders(world, cid, 1))
    # `other` has handed work out: attached and met, its Builder's return would go nowhere
    got = cv.attach_follow_up(other, work, by=world["steward"])
    assert "error" in got and not cv.follow_ups(work)
    assert not cv.expectation_state(other)["satisfied_by"]
