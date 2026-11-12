"""Workstream R, third review round (review-R-verify2.md, 2026-11-12):
placement is decided per TARGET, not by membership of a capped thread list.

  * a sibling Conversation opened under an ancestor, and one opened under
    work the request only refers to, are refused;
  * the ninth named requirement's result, and the last of twelve children
    with three updates each, are placeable -- no cap refuses them;
  * an unrelated post in an ancestor's Conversation is refused, a causal
    ancestor's result is not;
  * a placement check reads a number of records bounded by depth, not by
    how much the work delegated; the thread LISTING reads at most
    MOST_NODES, counted through every helper.
"""

from __future__ import annotations

import pytest

from mentis.conversation import text, threads
from mentis.worker import NotPermitted
from tests._loop import world  # noqa: F401
from tests.test_reply_context import _answer
from tests.test_reply_context_review2 import BODY, _grant_for, _op, _setup


def test_the_listing_reads_at_most_its_budget_through_every_helper(
        world, monkeypatch):
    cv, actor, parent, grant, builder = _setup(world)
    for i in range(26):
        _op(world, "delegate", {"participant": builder,
                                "work": f"Independent package {i}"}, grant)
    original = cv._act
    reads = []

    def counted(ref):
        reads.append(ref)
        return original(ref)
    monkeypatch.setattr(cv, "_act", counted)
    threads.thread_of(cv, parent)
    assert len(reads) <= threads.MOST_NODES


def test_a_placement_check_reads_by_depth_not_breadth(world, monkeypatch):
    cv, actor, parent, grant, builder = _setup(world)
    last = None
    for i in range(30):
        child = _op(world, "delegate", {"participant": builder,
                                        "work": f"Package {i}"}, grant)
        last = _answer(cv, grant["conversation"], builder,
                       child["expectation"], f"Package {i} done",
                       replies_to=child["turn"])
    original = cv._act
    reads = []

    def counted(ref):
        reads.append(ref)
        return original(ref)
    monkeypatch.setattr(cv, "_act", counted)
    assert threads.within_work(cv, parent, last)
    assert len(reads) <= 4 * (threads.MOST_UP + 2)
    assert len(reads) < 30


def test_the_last_of_twelve_children_with_three_updates_is_placeable(world):
    cv, actor, parent, grant, builder = _setup(world)
    for i in range(12):
        child = _op(world, "delegate", {"participant": builder,
                                        "work": f"Build component {i}"}, grant)
        for phase in ("progress", "candidate", "final"):
            answer = _answer(cv, grant["conversation"], builder,
                             child["expectation"], f"Component {i}: {phase}",
                             replies_to=child["turn"])
    assert _op(world, "request_decision",
               {"on": answer, "question": "Accept last component?"},
               grant)["ok"]


def test_the_ninth_named_requirement_is_placeable(world):
    cv, actor, parent, grant, builder = _setup(world)
    refs = []
    for i in range(9):
        turn = cv.say(grant["conversation"], world["who"]["@brian"],
                      [text(f"Candidate requirement {i}")])
        req = cv.expect(turn, of=builder, kind="result",
                        by=world["who"]["@brian"])
        answer = _answer(cv, grant["conversation"], builder, req,
                         f"Candidate {i} result", replies_to=turn)
        refs.append(req)
    child = _op(world, "delegate", {"participant": builder,
                                    "work": "Review all nine requirements",
                                    "relation": "verifies",
                                    "relation_ref": refs}, grant)
    assert _op(world, "request_decision",
               {"on": answer, "question": "Accept ninth requirement?"},
               _grant_for(world, child["expectation"], builder))["ok"]


def test_a_sibling_conversation_opened_under_the_parent_is_refused(world):
    cv, actor, parent, grant, builder = _setup(world)
    sibling = _op(world, "open_conversation", {"name": "Sibling work only"},
                  grant)["conversation"]
    child = _op(world, "delegate", {"participant": builder,
                                    "work": "Work in original conversation"},
                grant)
    with pytest.raises(NotPermitted):
        _op(world, "record_material", {"kind": "outcome", "body": BODY,
                                       "outcome_of": child["turn"],
                                       "in_context": sibling},
            _grant_for(world, child["expectation"], builder))
    # the parent that opened it may
    assert threads.conversation_allowed(cv, sibling, parent)


def test_a_conversation_opened_under_referenced_work_is_refused(world):
    cv, actor, parent, grant, builder = _setup(world)
    unrelated = cv.say(grant["conversation"], world["who"]["@brian"],
                       [text("Other project")])
    unrelated_req = cv.expect(unrelated, of=actor, kind="result",
                              by=world["who"]["@brian"])
    elsewhere = _op(world, "open_conversation",
                    {"name": "Other project private work"},
                    _grant_for(world, unrelated_req, actor))["conversation"]
    child = _op(world, "delegate", {"participant": builder,
                                    "work": "Reference other project",
                                    "relation": "verifies",
                                    "relation_ref": [unrelated_req]}, grant)
    with pytest.raises(NotPermitted):
        _op(world, "record_material", {"kind": "outcome", "body": BODY,
                                       "outcome_of": child["turn"],
                                       "in_context": elsewhere},
            _grant_for(world, child["expectation"], builder))


def test_an_unrelated_post_in_an_ancestor_s_conversation_is_refused(world):
    cv, actor, parent, grant, builder = _setup(world)
    other = cv.say(grant["conversation"], world["who"]["@brian"],
                   [text("Unrelated work in parent conversation")])
    sub = _op(world, "open_conversation", {"name": "Own child work"},
              grant)["conversation"]
    child = _op(world, "delegate", {"participant": builder,
                                    "work": "Own child task",
                                    "conversation": sub}, grant)
    with pytest.raises(NotPermitted):
        _op(world, "request_decision",
            {"on": other, "question": "Unrelated approval"},
            _grant_for(world, child["expectation"], builder))


def test_a_causal_ancestor_s_result_is_within_the_child_s_work(world):
    """Within the work and its Conversation allowed. (Whether a decision
    form may be put in a Conversation other than the run's own is the
    separate `_where` rule, unchanged here.)"""
    cv, actor, parent, grant, builder = _setup(world)
    answer = _op(world, "respond", {"text": "Overall plan"}, grant)["turn"]
    sub = _op(world, "open_conversation", {"name": "Own child work"},
              grant)["conversation"]
    child = _op(world, "delegate", {"participant": builder,
                                    "work": "Own child task",
                                    "conversation": sub}, grant)
    assert threads.placement_refusal(cv, child["expectation"], answer,
                                     participant=builder) is None
