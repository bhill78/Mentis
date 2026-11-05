"""Waiting on work somebody else carries: when the wait ends, and what the waiter can read.

THE FAILURE THIS EXISTS FOR (Unified Fluid Space, 2026-11-04, Turns #125-#133). Work waited on a run
that was delegated with no return. That run could not read the concept it waited for, because the wait
gave it nothing, said so and stopped without claiming the work met. Nothing could end a wait on it, so
two requests sat until the owner asked again, 16 hours later. No owner decision was needed for any of it.

What holds now, through the real delegate, await_work, dispatch and read_artifact:

  * work that has stopped ends a wait on it, said as stopped and never as met;
  * work paused on something, resumed but not started, or continued is not stopped;
  * a wait on work that has already stopped is refused, in words;
  * the waiter can read what the work it awaited returned, and its resume brief lists it;
  * declaring a wait reaches nothing else: not a sibling's, not restricted work, not another
    Conversation's, and a refused read changes nothing in the record.
"""

from __future__ import annotations

import base64

import pytest

from mentis import artifacts
from mentis.worker import NotPermitted
from tests._loop import a_conversation, say, world  # noqa: F401
from tests._loop import runs  # noqa: F401
from tests.test_delegate_coordinate import _delegate, _present


def _op(world, name, args, grant):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), name, args, grant)


def _top(world, runs, cid, alias):
    """Work the owner addressed to a new Participant; its run has ended, unclaimed."""
    pid = world["cv"].create_participant(alias)
    got = say(world, cid, f"{alias} carry this", action="ask-participant",
              dispatch=[{"participant": pid, "work": "carry this"}])
    return got["expectations"][0], runs[-1]


def _dispatch(world, out, who):
    import mentis.web as web
    web.dispatch_soon(world["state"], conversation=out["conversation"], turn=out["turn"],
                      participant=who, work="a part", expectation=out["expectation"])


def _grant_of(runs, expectation):
    return next(g for g in runs if g["expectation"] == expectation)


def _child(world, runs, grant, who, **more):
    out = _delegate(world, grant, participant=who, work="a part", **more)
    _dispatch(world, out, who)
    return out["expectation"], _grant_of(runs, out["expectation"])


def _returned_by(world, grant, words=b"<p>third pass</p>"):
    return _op(world, "return_artifact",
               {"bytes_b64": base64.b64encode(words).decode(), "claimed_name": "concept.html",
                "because": "built"}, grant)["ref"]


def _resumes(cv, expectation):
    return [a for a in cv.history(caused_by=expectation) if a["act"] == "work-resumed"]


def _kinds(cv, expectation):
    return [(a["detail"].get("event") or {}).get("kind") for a in _resumes(cv, expectation)]


def _waiting_and_awaited(world, runs, *, returning):
    """A waiter, and work handed out under somebody else that ends after the wait is declared."""
    cv = world["cv"]
    cid = a_conversation(world)
    waiter, gw = _top(world, runs, cid, "@Waiter")
    _, ga = _top(world, runs, cid, "@Care")
    bob = _present(world, cid, "@Bob")
    out = _delegate(world, ga, participant=bob, work="a part",
                    **({"return_to_me": True} if returning else {}))
    awaited = out["expectation"]
    cv.await_work(waiter, awaited, by=gw["participant"], because="needs it")
    assert cv.waiting_on(waiter)["outstanding"] == [awaited]
    _dispatch(world, out, bob)
    return cv, waiter, awaited


# -- when the wait ends -----------------------------------------------------------------------------


def test_stopped_work_wakes_what_waits_on_it_and_is_not_called_met(world, runs):
    cv, waiter, awaited = _waiting_and_awaited(world, runs, returning=False)
    state = cv.awaited_state(awaited)
    assert state["ended"] and state["stopped"] and not state["met"] and not state["met_by"]
    assert state["returned"] == cv._child_state(awaited)["state"]
    assert _kinds(cv, waiter) == ["awaited-run-ended"]
    assert not cv.waiting_on(waiter)["outstanding"]
    # woken is not satisfied, neither the waiter nor what it waited on
    assert not cv.expectation_state(waiter)["satisfied_by"]
    assert not cv.expectation_state(awaited)["satisfied_by"]


def test_a_delegated_child_still_ends_a_wait_as_it_did(world, runs):
    cv, waiter, awaited = _waiting_and_awaited(world, runs, returning=True)
    state = cv.awaited_state(awaited)
    assert state["ended"] and not state["stopped"]
    assert _kinds(cv, waiter) == ["awaited-run-ended"]


def test_work_claimed_met_ends_the_wait_as_met_not_as_stopped(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    waiter, gw = _top(world, runs, cid, "@Waiter")
    owner = world["who"]["@brian"]
    open_work = cv.expect(cv.say(cid, owner, [{"type": "text", "text": "x"}]), of=None,
                          kind="result", by=owner, conversation=cid)
    cv.await_work(waiter, open_work, by=gw["participant"], because="needs it")
    cv.record_act(actor=owner, act="expectation-met", conversation=cid, caused_by=open_work,
                  about=[open_work], detail={})
    state = cv.awaited_state(open_work)
    assert state["met"] and state["ended"] and not state["stopped"]


def test_work_never_started_is_not_stopped(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    waiter, gw = _top(world, runs, cid, "@Waiter")
    owner = world["who"]["@brian"]
    open_work = cv.expect(cv.say(cid, owner, [{"type": "text", "text": "x"}]), of=None,
                          kind="result", by=owner, conversation=cid)
    cv.await_work(waiter, open_work, by=gw["participant"], because="needs it")
    assert not cv.awaited_state(open_work)["ended"]
    assert cv.waiting_on(waiter)["outstanding"] == [open_work]


def test_a_coordinator_paused_on_its_child_still_holds_the_wait(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    waiter, gw = _top(world, runs, cid, "@Waiter")
    care, gc = _top(world, runs, cid, "@Care")
    bob = _present(world, cid, "@Bob")
    pending = _delegate(world, gc, participant=bob, work="still to do", return_to_me=True)
    cv.await_work(waiter, care, by=gw["participant"], because="needs it")
    assert cv._pausing_on(care) == [pending["expectation"]]
    assert not cv.awaited_state(care)["ended"]
    assert cv.waiting_on(waiter)["outstanding"] == [care]
    assert not _resumes(cv, waiter)


def test_work_resumed_but_not_yet_started_has_not_stopped(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    waiter, gw = _top(world, runs, cid, "@Waiter")
    care, gc = _top(world, runs, cid, "@Care")
    bob = _present(world, cid, "@Bob")
    _delegate(world, gc, participant=bob, work="a part", return_to_me=True)
    cv.await_work(waiter, care, by=gw["participant"], because="needs it")
    cv.record_act(actor="mentis", act="work-resumed", conversation=cid,
                  turn=cv._act(care)["turn"], caused_by=care, about=[gc["participant"]], detail={})
    assert cv.continuation_pending(care)
    assert not cv._stopped(care)
    assert not cv.awaited_state(care)["ended"]


def test_a_chain_of_waits_unwinds_from_the_work_that_stopped(world, runs):
    """#108 waited on #106, which waited on #103: the wait on the first stopping must reach the last."""
    cv = world["cv"]
    cid = a_conversation(world)
    last, gl = _top(world, runs, cid, "@Last")
    middle, gm = _top(world, runs, cid, "@Middle")
    _, ga = _top(world, runs, cid, "@Care")
    bob = _present(world, cid, "@Bob")
    out = _delegate(world, ga, participant=bob, work="a part")
    cv.await_work(middle, out["expectation"], by=gm["participant"], because="needs it")
    cv.await_work(last, middle, by=gl["participant"], because="needs it")
    assert cv.waiting_on(last)["outstanding"] == [middle]
    _dispatch(world, out, bob)
    # the first wait ended, so the middle ran again, and its run ending ends the last wait
    assert _kinds(cv, middle) == ["awaited-run-ended"]
    assert _kinds(cv, last) == ["awaited-run-ended"]
    assert not cv.waiting_on(last)["outstanding"]


def test_work_held_for_a_person_after_its_child_ended_still_releases_a_wait_on_it(
        world, runs, monkeypatch):
    """It cannot resume itself, so it has stopped; the wait on it hears when its child ends."""
    cv = world["cv"]
    cid = a_conversation(world)
    waiter, gw = _top(world, runs, cid, "@Waiter")
    care, gc = _top(world, runs, cid, "@Care")
    bob = _present(world, cid, "@Bob")
    out = _delegate(world, gc, participant=bob, work="a part", return_to_me=True)
    cv.await_work(waiter, care, by=gw["participant"], because="needs it")
    real = type(cv).recovery_hold
    monkeypatch.setattr(type(cv), "recovery_hold",
                        lambda self, parent, **kw: (["held"] if parent == care
                                                    else real(self, parent, **kw)))
    _dispatch(world, out, bob)
    assert not _resumes(cv, care)
    assert cv.awaited_state(care)["stopped"]
    assert _kinds(cv, waiter) == ["awaited-run-ended"]


def test_a_mutual_wait_from_before_they_were_refused_reads_as_waiting_and_ends(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    a, ga = _top(world, runs, cid, "@A")
    b, gb = _top(world, runs, cid, "@B")
    for waiting, on, by in ((a, b, ga), (b, a, gb)):
        cv.record_act(actor=by["participant"], act="work-awaited", conversation=cid,
                      caused_by=waiting, about=[on], detail={})
    assert not cv.awaited_state(a)["ended"]
    assert not cv.awaited_state(b)["ended"]


def _continued(world, cid, on, carrier):
    """The owner continuing a request: its request is caused by that one, with its origin."""
    cv = world["cv"]
    owner = world["who"]["@brian"]
    turn = cv.say(cid, owner, [{"type": "text", "text": "carry on"}])
    exp = cv.expect(turn, of=carrier, kind="result", by=owner, conversation=cid, caused_by=on)
    cv.record_act(actor=owner, act="authority-granted", conversation=cid, turn=turn, caused_by=exp,
                  about=[on], detail={"operations": [], "origin": on, "source": "continuation"})
    return exp


def test_a_continuation_of_a_continuation_means_the_work_has_not_stopped(world, runs, monkeypatch):
    """Found by review of the first version: only direct continuations were asked."""
    cv = world["cv"]
    cid = a_conversation(world)
    a, ga = _top(world, runs, cid, "@Care")
    carrier = ga["participant"]
    b = _continued(world, cid, a, carrier)
    c = _continued(world, cid, b, carrier)
    assert cv.authority_of(b)["origin"] == a and cv.authority_of(c)["origin"] == b
    assert cv._continuation_line(a) == [b, c]
    # a request not started and not closed is about to run; nothing else needs to say so
    assert cv.continuation_pending(c)
    assert not cv._stopped(a)
    assert not cv.awaited_state(a)["ended"]
    waiter, gw = _top(world, runs, cid, "@Waiter")
    assert cv.await_work(waiter, a, by=gw["participant"], because="needs it")
    # and a child of the work ending does not resume it beside what is continuing it
    assert cv.claim_resumption(a, event={"kind": "child-ended", "expectation": c}) is None


def test_a_held_middle_of_a_chain_still_releases_what_waits_on_it(world, runs, monkeypatch):
    """Found by review of the first version: A waits on B waits on C, and C's end cannot resume B."""
    cv = world["cv"]
    cid = a_conversation(world)
    first, gf = _top(world, runs, cid, "@First")
    middle, gm = _top(world, runs, cid, "@Middle")
    _, ga = _top(world, runs, cid, "@Care")
    bob = _present(world, cid, "@Bob")
    out = _delegate(world, ga, participant=bob, work="a part")
    cv.await_work(middle, out["expectation"], by=gm["participant"], because="needs it")
    cv.await_work(first, middle, by=gf["participant"], because="needs it")
    real = type(cv).recovery_hold
    monkeypatch.setattr(type(cv), "recovery_hold",
                        lambda self, parent, **kw: (["held"] if parent == middle
                                                    else real(self, parent, **kw)))
    _dispatch(world, out, bob)
    assert not _resumes(cv, middle)
    assert cv.awaited_state(middle)["stopped"]
    assert _kinds(cv, first) == ["awaited-run-ended"]


def test_a_very_long_chain_of_waits_reads_without_exhausting_the_stack(world, runs):
    """Found by review of the first version: one stack frame per wait."""
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    chain = [cv.expect(cv.say(cid, owner, [{"type": "text", "text": "x"}]), of=None, kind="result",
                       by=owner, conversation=cid) for _ in range(40)]
    for waiting, on in zip(chain, chain[1:]):
        cv.record_act(actor=owner, act="work-awaited", conversation=cid, caused_by=waiting, about=[on],
                      detail={})
    import sys
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(150, len(__import__("inspect").stack()) + 90))
    try:
        assert not cv.awaited_state(chain[0])["ended"]
    finally:
        sys.setrecursionlimit(limit)


def test_a_shared_dependency_is_asked_once(world, runs, monkeypatch):
    """Found by review of the first version: diamonds repeated along every path."""
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    made = [cv.expect(cv.say(cid, owner, [{"type": "text", "text": "x"}]), of=None, kind="result",
                      by=owner, conversation=cid) for _ in range(25)]
    for i in range(0, 22, 2):       # each level waits on both of the next
        for on in (made[i + 1], made[i + 2]):
            cv.record_act(actor=owner, act="work-awaited", conversation=cid, caused_by=made[i],
                          about=[on], detail={})
        cv.record_act(actor=owner, act="work-awaited", conversation=cid, caused_by=made[i + 1],
                      about=[made[i + 2]], detail={})
    calls = []
    real = type(cv)._stop_facts
    monkeypatch.setattr(type(cv), "_stop_facts",
                        lambda self, e: (calls.append(e), real(self, e))[1])
    cv._stop_walk(made[0])
    assert len(calls) == len(set(calls))


# -- a wait that could never end ---------------------------------------------------------------------


def test_a_wait_on_work_already_stopped_is_refused_in_words(world, runs):
    cv = world["cv"]
    cid = a_conversation(world)
    waiter, gw = _top(world, runs, cid, "@Waiter")
    stopped, _ = _top(world, runs, cid, "@Care")
    with pytest.raises(NotPermitted) as said:
        _op(world, "await_work", {"expectation": stopped, "because": "needs it"}, gw)
    assert "has already stopped" in str(said.value) and "nobody claimed it met" in str(said.value)
    assert not [a for a in cv.history(caused_by=waiter) if a["act"] == "work-awaited"]


# -- what the waiter can read ------------------------------------------------------------------------


def _fluid(world, runs, **returning):
    """As it happened: one run waits on another, whose artifact did not exist when either was
    delegated, so nobody could have handed it over."""
    cid = a_conversation(world)
    exp, g = _top(world, runs, cid, "@Care")
    bob, cy = _present(world, cid, "@Bob"), _present(world, cid, "@Cy")
    made = _delegate(world, g, participant=bob, work="a part", return_to_me=True, **returning)
    c, gc = _child(world, runs, g, cy)
    _op(world, "await_work", {"expectation": made["expectation"], "because": "needs it"}, gc)
    _dispatch(world, made, bob)
    gb = _grant_of(runs, made["expectation"])
    return {"cid": cid, "g": g, "b": made["expectation"], "gb": gb, "c": c, "gc": gc,
            "ref": _returned_by(world, gb)}


def test_the_waiter_reads_what_the_work_it_waited_on_returned(world, runs):
    f = _fluid(world, runs)
    got = _op(world, "read_artifact", {"ref": f["ref"]}, f["gc"])
    assert base64.b64decode(got["bytes_b64"]) == b"<p>third pass</p>"
    supplied = [a for a in world["cv"].history(conversation=f["cid"])
                if a["act"] == artifacts.SUPPLIED and f["ref"] in (a["about"] or ())]
    assert supplied[-1]["detail"]["reachable"]["because"] == "returned-by-awaited"
    assert supplied[-1]["detail"]["reachable"]["awaited"] == f["b"]


def test_the_waiter_can_hand_on_what_it_may_read(world, runs):
    f = _fluid(world, runs)
    dee = _present(world, f["cid"], "@Dee")
    out = _delegate(world, f["gc"], participant=dee, work="revise it", artifacts=[f["ref"]])
    assert out["expectation"]


def test_a_sibling_that_declared_no_wait_stays_bounded(world, runs):
    f = _fluid(world, runs)
    dee = _present(world, f["cid"], "@Dee")
    _, gd = _child(world, runs, f["g"], dee)
    with pytest.raises(NotPermitted):
        _op(world, "read_artifact", {"ref": f["ref"]}, gd)


def test_restricted_awaited_work_stays_closed(world, runs):
    f = _fluid(world, runs, restricted=True, restricted_because="private")
    with pytest.raises(NotPermitted):
        _op(world, "read_artifact", {"ref": f["ref"]}, f["gc"])
    assert f["ref"] not in {w["ref"] for w in artifacts.available(
        world["state"].corpus, world["cv"], f["gc"])}


def test_a_wait_across_conversations_reads_nothing_of_the_other_one(world, runs):
    cv = world["cv"]
    home, away = a_conversation(world), a_conversation(world, "Elsewhere")
    waiter, gw = _top(world, runs, home, "@Waiter")
    _, ga = _top(world, runs, away, "@Care")
    bob = _present(world, away, "@Bob")
    out = _delegate(world, ga, participant=bob, work="a part", return_to_me=True)
    cv.await_work(waiter, out["expectation"], by=gw["participant"], because="needs it")
    _dispatch(world, out, bob)
    ref = _returned_by(world, _grant_of(runs, out["expectation"]))
    assert artifacts.awaited_returns(world["state"].corpus, cv, waiter) == []
    with pytest.raises(NotPermitted):
        _op(world, "read_artifact", {"ref": ref}, gw)


def test_a_refused_read_writes_nothing(world, runs):
    f = _fluid(world, runs)
    dee = _present(world, f["cid"], "@Dee")
    _, gd = _child(world, runs, f["g"], dee)
    before = len(world["cv"].history(conversation=f["cid"]))
    with pytest.raises(NotPermitted):
        _op(world, "read_artifact", {"ref": f["ref"]}, gd)
    assert len(world["cv"].history(conversation=f["cid"])) == before


def test_naming_an_artifact_in_a_brief_still_reaches_nothing(world, runs):
    """The owner's limit on prose (ent-cb649f419cd5) stands."""
    f = _fluid(world, runs)
    cy = _present(world, f["cid"], "@Zed")
    out = _delegate(world, f["g"], participant=cy, work=f"revise {f['ref']}")
    _dispatch(world, out, cy)
    with pytest.raises(NotPermitted):
        _op(world, "read_artifact", {"ref": f["ref"]}, _grant_of(runs, out["expectation"]))


# -- what the resume says ----------------------------------------------------------------------------


def _resume_words(cv, waiter):
    from mentis.web.dispatch import resume_dispatch
    return resume_dispatch(cv, waiter, _resumes(cv, waiter)[-1]["id"])["work"]


def test_the_resume_says_stopped_lists_its_reply_and_never_says_met(world, runs):
    cv, waiter, awaited = _waiting_and_awaited(world, runs, returning=False)
    words = _resume_words(cv, waiter)
    assert "STOPPED without being finished" in words
    assert "claimed met by" not in words
    assert awaited in words


def test_the_resume_lists_the_artifact_the_waiter_may_read(world, runs):
    f = _fluid(world, runs)
    cv = world["cv"]
    assert _resumes(cv, f["c"])
    from mentis.web.dispatch import resume_dispatch
    # a resume after the artifact was returned: the record, as it reads at the next resume
    act = cv.record_act(actor="mentis", act="work-resumed", conversation=f["cid"],
                        turn=cv._act(f["c"])["turn"], caused_by=f["c"], about=[f["gc"]["participant"]],
                        detail={"parent": f["c"], "event": {}, "required": [], "decisions": [],
                                "awaited": cv.waiting_on(f["c"])["awaited"], "carrier": f["gc"]["participant"]})
    words = resume_dispatch(cv, f["c"], act)["work"]
    assert f["ref"] in words and "read them with read_artifact" in words


def test_the_resume_does_not_list_what_the_waiter_may_not_read(world, runs):
    f = _fluid(world, runs, restricted=True, restricted_because="private")
    cv = world["cv"]
    from mentis.web.dispatch import resume_dispatch
    act = cv.record_act(actor="mentis", act="work-resumed", conversation=f["cid"],
                        turn=cv._act(f["c"])["turn"], caused_by=f["c"], about=[f["gc"]["participant"]],
                        detail={"parent": f["c"], "event": {}, "required": [], "decisions": [],
                                "awaited": cv.waiting_on(f["c"])["awaited"], "carrier": f["gc"]["participant"]})
    words = resume_dispatch(cv, f["c"], act)["work"]
    assert f["ref"] not in words and "not available to this work" in words


# -- authority did not move ---------------------------------------------------------------------------


def test_an_ordinary_run_hands_on_its_work_without_coordinate(world, runs):
    from mentis.worker import may_coordinate
    cid = a_conversation(world)
    _, g = _top(world, runs, cid, "@Care")
    assert not may_coordinate(g)
    newcomer = world["cv"].create_participant("@NotHereYet")
    assert _delegate(world, g, participant=newcomer, work="a part", return_to_me=True)["expectation"]
