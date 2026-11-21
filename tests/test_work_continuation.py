"""Blocked work continuation and the review loop (opr-6cbffa5ae505, 2026-11-21).

WHAT HAPPENED. The owner asked @Caretaker for a design, without `coordinate` on the request. Its run
handed the review on (its own work: no authority needed); the review rejected the design and
resumed the carrier. The resumed run was told "no organising operations", read that as "may not
arrange the re-review", drafted the correction and stopped not met. The owner then wrote a
follow-up asking for the re-review, as its own post; it was recorded as a new request, and its
carrier -- the same @Caretaker -- was told, as every carrier is, that a follow-up about work
already being carried "is handed to it with attach_follow_up". That tool was held only with
`coordinate`, so it was not even offered; `delegate` naming the original work was refused as
coordinating. The original work sat open with nobody able to finish its review cycle.

WHAT HOLDS NOW, each tested below on a disposable Brain, with every grant minted by the real
dispatch path and every operation called through `_operate`:

  * the owner's `coordinate` is on the run's grant, and on its resumption; nobody else's is;
  * a carrier without it hands on its own work -- the review, and after a rejection, the
    re-review of the corrected result -- and is resumed by each return;
  * its claim of met waits while the re-review it waits on is out, and is recorded met after;
  * every run holds `attach_follow_up`; the owner's follow-up handed to work the same Participant
    carries resumes that work with it, with that work's own authority and nothing more;
  * handed to another carrier's work, or picking up work through `delegate`, it is still refused
    without `coordinate`, with nothing written;
  * the resumed run is told in words that delegating its own work, a re-review included, and
    handing a follow-up to its own work remain open to it.
"""

from __future__ import annotations

import time

import pytest

from mentis.execution import RunResult
from mentis.web import dispatch as D
from tests._loop import (a_conversation, grant_of_run, say,  # noqa: F401
                         script_every_backend, world)
from tests.test_delegate_coordinate import _present

MET = "Done.\n\n```outcome\nresult: met\nsummary: {0}\nevidence:\n- {0}\n```"
NOT_MET = "Not yet.\n\n```outcome\nresult: not-met\nsummary: {0}\nevidence:\n- {0}\n```"


@pytest.fixture()
def crew(world):
    """Runs as the test scripts them, by the expectation they carry: each run calls its next
    function (if any) with its own grant, keeps the grant it ACTUALLY held, and replies with its
    next scripted text."""
    svc = world["state"].agents
    plan = {"on_run": {}, "say": {}, "grants": {}, "results": []}

    def perform(spec):
        grant = grant_of_run(svc, spec, world["state"].path)
        exp = grant["expectation"]
        plan["grants"].setdefault(exp, []).append(grant)
        queue = plan["on_run"].get(exp) or []
        if queue:
            plan["results"].append(queue.pop(0)(grant))
        words = (plan["say"].get(exp) or ["done: here is what I did"])
        text = words.pop(0) if len(words) > 1 else words[0]
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text=text, started_at=now, finished_at=now)

    script_every_backend(svc, perform)
    return plan


def _op(world, grant, name, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), name, args, grant)


def _ask(world, cid, who, words, **spec):
    """The owner asks `who` directly, with `spec` on the dispatch (`coordinate`, ...)."""
    out = say(world, cid, words, action="ask-participant",
              dispatch=[{"participant": who, "work": words, **spec}])
    assert "error" not in out, out
    return out["expectations"][0]


def _pending(world, expectation):
    return [k for k in world["sent"] if k["expectation"] == expectation]


def _run(world, expectation):
    """Run the newest captured dispatch of `expectation`, synchronously."""
    spec = _pending(world, expectation)[-1]
    world["sent"].remove(spec)
    D.dispatch(world["state"], **spec)


def _run_child(world, delegated):
    """Run what a `delegate` returned, as the door would dispatch it."""
    D.dispatch(world["state"], conversation=delegated["conversation"], turn=delegated["turn"],
               participant=delegated["dispatch"]["participant"],
               work=delegated["dispatch"]["work"], expectation=delegated["expectation"])


def _met(cv, expectation):
    return bool(cv.expectation_state(expectation)["satisfied_by"])


def _refused(world, grant, name, **args):
    from mentis.worker import NotPermitted
    with pytest.raises(NotPermitted) as caught:
        _op(world, grant, name, **args)
    return str(caught.value)


# -- the owner's coordinate grant reaches the run, and its resumption --------------------------

def test_the_owners_coordinate_is_on_the_grant_and_on_the_resumed_grant(world, crew):
    from mentis.worker import ATTACH_FOLLOW_UP, RESUME_INTAKE, may_coordinate, permitted
    cv = world["cv"]
    cid = a_conversation(world)
    carer, reviewer = _present(world, cid, "@Carer"), _present(world, cid, "@Reviewer")
    work = _ask(world, cid, carer, "Design it; have it reviewed.", coordinate=True)
    crew["on_run"][work] = [lambda g: _op(world, g, "delegate", participant=reviewer,
                                          work="review the design", return_to_me=True,
                                          resume_on_return=True, review_of=work)]
    _run(world, work)
    first = crew["grants"][work][0]
    assert may_coordinate(first)
    assert RESUME_INTAKE in permitted(first["scope"], first["operations"])
    review = crew["results"][-1]["expectation"]
    _run_child(world, crew["results"][-1])
    # the review's own run is ordinary work: the parent's coordinate is not handed down
    assert not may_coordinate(crew["grants"][review][0])
    # its return resumes the carrier, under the same request's grant
    assert _pending(world, work), "the review's return did not resume the work"
    _run(world, work)
    again = crew["grants"][work][1]
    assert may_coordinate(again) and again["operations"] == first["operations"]
    assert ATTACH_FOLLOW_UP in permitted(again["scope"], again["operations"])
    assert not _met(cv, work)


# -- the incident: review, rejection, correction, re-review, completion, without coordinate ----

def test_a_rejected_review_returns_for_correction_and_re_review_without_coordinate(world, crew):
    from mentis.worker import may_coordinate
    cv = world["cv"]
    cid = a_conversation(world)
    carer, reviewer = _present(world, cid, "@Carer"), _present(world, cid, "@Reviewer")
    work = _ask(world, cid, carer, "Design it; it needs an independent review.")

    def review(label):
        return lambda g: _op(world, g, "delegate", participant=reviewer, work=label,
                             return_to_me=True, resume_on_return=True, review_of=work)
    # 1. the carrier drafts and hands the review on: its own work, no authority needed
    crew["on_run"][work] = [review("review the draft"), review("re-review the corrected draft")]
    crew["say"][work] = ["Draft written; review requested.",
                         MET.format("corrected and sent for re-review"),
                         MET.format("re-review accepted the corrected design")]
    _run(world, work)
    assert not may_coordinate(crew["grants"][work][0])
    first_review = crew["results"][0]["expectation"]
    assert "error" not in crew["results"][0]
    # 2. the review rejects; its return resumes the original carrier
    crew["say"][first_review] = [NOT_MET.format("rejected: six blocking findings")]
    _run_child(world, crew["results"][0])
    assert _pending(world, work), "the rejection did not return to the carrier"
    # 3. the resumed carrier corrects and hands on the re-review -- with the same, ordinary grant
    _run(world, work)
    resumed = crew["grants"][work][1]
    assert resumed["operations"] == crew["grants"][work][0]["operations"]
    assert not may_coordinate(resumed)
    second = crew["results"][1]
    assert "error" not in second and second["expectation"] != first_review
    # its claim of met waits on the re-review it is waiting for
    assert not _met(cv, work)
    # 4. the re-review accepts; the carrier resumes once more and the work is met
    crew["say"][second["expectation"]] = [MET.format("accepted")]
    _run_child(world, second)
    assert _pending(world, work), "the re-review's return did not resume the carrier"
    assert not _met(cv, work)
    _run(world, work)
    assert _met(cv, work)
    # one carrier, two reviews, nothing coordinated
    assert len(crew["grants"][work]) == 3
    assert all(not may_coordinate(g) for g in crew["grants"][work])


# -- the owner's follow-up reaches its own work, not unrelated new work ------------------------

def _stalled(world, crew, cid, carer, reviewer):
    """The original work after its first round: reviewed, corrected, stopped not met."""
    work = _ask(world, cid, carer, "Design it; it needs an independent review.")
    crew["on_run"][work] = [lambda g: _op(world, g, "delegate", participant=reviewer,
                                          work="review the draft", return_to_me=True,
                                          resume_on_return=True, review_of=work)]
    crew["say"][work] = ["Draft written; review requested.",
                         NOT_MET.format("corrected; the re-review is still owed")]
    _run(world, work)
    review = crew["results"][-1]["expectation"]
    crew["say"][review] = [NOT_MET.format("rejected")]
    _run_child(world, crew["results"][-1])
    _run(world, work)
    assert not _met(world["cv"], work) and not _pending(world, work)
    return work


def test_a_follow_up_to_work_the_same_carrier_carries_is_handed_to_it(world, crew):
    from mentis.worker import ATTACH_FOLLOW_UP, may_coordinate, permitted
    cv = world["cv"]
    cid = a_conversation(world)
    carer, reviewer = _present(world, cid, "@Carer"), _present(world, cid, "@Reviewer")
    work = _stalled(world, crew, cid, carer, reviewer)
    # the owner writes again, as its own post, no coordinate: a new request is recorded...
    follow = _ask(world, cid, carer, "Complete the re-review of that design. You may coordinate it.")
    assert follow != work
    # ...whose carrier holds attach_follow_up, though it may not coordinate
    crew["on_run"][follow] = [lambda g: _op(world, g, "attach_follow_up", work=work,
                                            because="it asks for that work's re-review")]
    _run(world, follow)
    grant = crew["grants"][follow][0]
    assert not may_coordinate(grant)
    assert ATTACH_FOLLOW_UP in permitted(grant["scope"], grant["operations"])
    out = crew["results"][-1]
    assert out.get("ok") and out["work"] == work and out["carrier"] == carer, out
    # the follow-up is carried under the work, and the work's carrier is resumed with it
    assert _met(cv, follow)
    assert [a["id"] for a in cv.follow_ups(work)] == [out["attached"]]
    assert out["resumed"] and out["dispatches"]
    world["sent"].extend(out["dispatches"])
    # resumed with the WORK's authority: the follow-up's request grants it nothing
    before = crew["grants"][work][-1]["operations"]
    crew["on_run"][work] = [lambda g: _op(world, g, "delegate", participant=reviewer,
                                          work="re-review the corrected draft",
                                          return_to_me=True, resume_on_return=True,
                                          review_of=work)]
    _run(world, work)
    after = crew["grants"][work][-1]
    assert after["operations"] == before and not may_coordinate(after)
    # and it can arrange the re-review the follow-up asked for
    assert "error" not in crew["results"][-1]


def test_a_follow_up_to_another_carriers_work_still_needs_coordinate(world, crew):
    cv = world["cv"]
    cid = a_conversation(world)
    carer, other = _present(world, cid, "@Carer"), _present(world, cid, "@Other")
    reviewer = _present(world, cid, "@Reviewer")
    work = _stalled(world, crew, cid, carer, reviewer)
    written = len(cv.history())
    follow = _ask(world, cid, other, "Finish that design's review.")
    crew["on_run"][follow] = [lambda g: _refused(world, g, "attach_follow_up", work=work)]
    _run(world, follow)
    words = crew["results"][-1]
    assert "coordinat" in words and "another Participant" in words, words
    assert not cv.follow_ups(work) and not _met(cv, follow)
    # with the owner's coordinate on that request, the same hand-over is allowed
    granted = _ask(world, cid, other, "Finish that design's review.", coordinate=True)
    crew["on_run"][granted] = [lambda g: _op(world, g, "attach_follow_up", work=work)]
    _run(world, granted)
    assert crew["results"][-1].get("ok") and crew["results"][-1]["carrier"] == carer
    assert len(cv.history()) > written


def test_picking_up_other_work_through_delegate_is_still_coordinating(world, crew):
    """The call the incident's follow-up run made: refused, nothing written, and the refusal now
    names the way that is open to it."""
    from mentis.worker import may_coordinate
    cv = world["cv"]
    cid = a_conversation(world)
    carer, reviewer = _present(world, cid, "@Carer"), _present(world, cid, "@Reviewer")
    work = _stalled(world, crew, cid, carer, reviewer)
    follow = _ask(world, cid, carer, "Complete the re-review of that design.")
    delegated = len([a for a in cv.history(act="work-delegated")])
    crew["on_run"][follow] = [lambda g: _refused(
        world, g, "delegate", participant=reviewer, expectation=work,
        work="re-review it", return_to_me=True)]
    _run(world, follow)
    assert not may_coordinate(crew["grants"][follow][0])
    words = crew["results"][-1]
    assert "coordinate" in words and "attach_follow_up" in words, words
    assert len([a for a in cv.history(act="work-delegated")]) == delegated


def test_a_run_without_coordinate_gains_no_organising_operation(world, crew):
    """No escalation: holding attach_follow_up adds nothing the owner did not grant."""
    from mentis.worker import AUTHORITY, ORGANISES, RESUME_INTAKE, permitted
    for scope in ("worker", "intake", "organising"):
        held = permitted(scope, [])
        assert not set(held) & (set(ORGANISES) | {RESUME_INTAKE, "coordinate"}), (scope, held)
    narrowed = permitted("intake", ["respond"])
    assert "respond" in narrowed and RESUME_INTAKE not in narrowed
    assert RESUME_INTAKE in permitted("intake", list(AUTHORITY))


# -- the resumed run is told what is still open to it --------------------------------------------

def test_the_resumed_brief_says_delegation_and_re_review_remain_open():
    from mentis.web.continuity import continuation_prompt
    text = continuation_prompt(task="Resuming.", authority={"scope": "worker", "organising": []},
                               authority_line=None, consent_text="", closing="Reply.",
                               split="\n\n---\n\n")
    assert "no organising operations" in text
    for words in ("`delegate`", "re-review", "`attach_follow_up`", "`coordinate`"):
        assert words in text, words


# -- a claim made while the review is out is not completed by that review's return alone ---------

def _claimed_while_reviewed(world, crew, verdict=None, returns=True):
    """The carrier hands the review on and claims met in the same run; the reviewer returns,
    recording `verdict` (or none). Returns (cv, work, the review's delegation)."""
    cv = world["cv"]
    cid = a_conversation(world)
    carer, reviewer = _present(world, cid, "@Carer"), _present(world, cid, "@Reviewer")
    work = _ask(world, cid, carer, "Design it; it needs an independent review.")
    crew["on_run"][work] = [lambda g: _op(world, g, "delegate", participant=reviewer,
                                          work="review it", review_of=work,
                                          **({"return_to_me": True, "resume_on_return": True}
                                             if returns else {}))]
    crew["say"][work] = [MET.format("designed; review handed on")]
    _run(world, work)
    review = crew["results"][-1]
    assert not _met(cv, work)                       # held while the review is out
    if verdict:
        crew["on_run"][review["expectation"]] = [lambda g: _op(
            world, g, "record_verdict", verdict=verdict, summary=f"review: {verdict}")]
    crew["say"][review["expectation"]] = [MET.format("reviewed")]
    _run_child(world, review)
    return cv, work, review


def test_a_review_that_records_no_pass_leaves_the_claim_for_the_carrier(world, crew):
    cv, work, _ = _claimed_while_reviewed(world, crew, verdict="block")
    assert not _met(cv, work)
    held = [a for a in cv.history(caused_by=work) if a["act"] == "outcome-pending"]
    reasons = (held[-1].get("detail") or {}).get("reasons") or [] if held else []
    assert any("ended after this claim" in r for r in reasons), reasons
    # the carrier is resumed to judge it
    assert _pending(world, work)


def test_an_independent_pass_completes_the_claim(world, crew):
    cv, work, _ = _claimed_while_reviewed(world, crew, verdict="pass")
    assert _met(cv, work)


def test_a_review_handed_on_without_a_return_never_strands_the_claim(world, crew):
    """Nothing would resume the carrier to judge a review that does not return to it, so that
    review's ending is not held against the claim (review-1): the work is not stranded."""
    cv, work, _ = _claimed_while_reviewed(world, crew, verdict="block", returns=False)
    held = [a for a in cv.history(caused_by=work) if a["act"] == "outcome-pending"]
    reasons = [r for a in held for r in (a.get("detail") or {}).get("reasons") or []]
    assert not any("ended after this claim" in r for r in reasons), reasons
    assert _met(cv, work)
