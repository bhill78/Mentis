"""Workstream R, review round (review-R.md, 2026-11-12): the six critical
findings, each as the behaviour that must hold now.

  R1  an outcome is never placed against another Conversation;
  R2  a detached operation is armed only from a post within its request's
      thread, so its report never lands under other work;
  R3  a carrier resumed with an attached follow-up is told what THAT
      follow-up replies to, with its work identity;
  R4  a detached report Turn is within the work's thread, so the resumed
      carrier can rest its outcome on it;
  R5  the thread includes what the work continues by S's recorded lineage,
      so a revision may put a decision form on its predecessor's result;
  R6  the "already being carried" block is bounded in rows and characters.
"""

from __future__ import annotations

import pytest

from mentis.conversation import posting, text
from tests._loop import _coordinator, a_conversation, say, world  # noqa: F401
from tests.test_reply_context import _answer, _reply_block, told  # noqa: F401


def _op(world, name, args, grant):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), name, args, grant)


def test_r1_an_outcome_against_another_conversation_is_refused(world):
    from mentis.worker import NotPermitted
    cv = world["cv"]
    actor, parent, grant = _coordinator(world, a_conversation(world))
    other = a_conversation(world, "Unrelated work")
    alien = cv.say(other, world["who"]["@brian"], [text("Unrelated request")])
    body = {"text": "Completed", "result": "done", "attempted": True}
    for args in ({"outcome_of": alien, "in_context": alien, "basis": [alien]},
                 {"outcome_of": cv._act(parent)["turn"], "in_context": other},
                 {"outcome_of": cv._act(parent)["turn"],
                  "in_context": grant["conversation"], "basis": [alien]}):
        with pytest.raises(NotPermitted):
            _op(world, "record_material",
                {"kind": "outcome", "body": body, **args}, grant)


def test_r2_a_promise_of_other_work_cannot_arm_this_request(world):
    from mentis.worker import NotPermitted
    cv = world["cv"]
    actor, parent, grant = _coordinator(world, a_conversation(world))
    cid = grant["conversation"]
    unrelated = cv.say(cid, world["who"]["@brian"], [text("Other work")])
    other = cv.expect(unrelated, of=actor, kind="result",
                      by=world["who"]["@brian"])
    promise = _answer(cv, cid, actor, other, "Arming a separate operation",
                      replies_to=unrelated)
    with pytest.raises(NotPermitted) as refused:
        _op(world, "arm_detached", {"what": "deployment",
                                    "result_location": "REPORT.md",
                                    "arming_post": promise}, grant)
    assert "not in the thread" in str(refused.value)
    assert not [a for a in cv._own_acts(parent) if a["act"] == "detached-armed"]


def test_r4_the_report_turn_is_basis_for_the_resumed_outcome(world):
    from mentis.operational import detached
    cv = world["cv"]
    actor, parent, grant = _coordinator(world, a_conversation(world))
    promise = _op(world, "respond",
                  {"text": "Deployment armed; helper will report."}, grant)["turn"]
    armed = _op(world, "arm_detached", {"what": "deploy",
                                        "result_location": "REPORT.md",
                                        "arming_post": promise}, grant)
    report = detached.report(world["state"], armed["operation"], {
        "token": armed["report_token"], "result": "succeeded",
        "summary": "commit deployed"})
    out = _op(world, "record_material", {
        "kind": "outcome",
        "body": {"text": "Deployment verified", "result": "deployed",
                 "attempted": True},
        "outcome_of": cv._act(parent)["turn"],
        "in_context": grant["conversation"], "basis": [report["turn"]]}, grant)
    assert out["entry"]


def test_r3_a_follow_up_resume_names_what_the_follow_up_replies_to(
        world, told):
    from mentis.web import dispatch as D
    cv = world["cv"]
    cid = a_conversation(world)
    care = cv.create_participant("@Caretaker")
    root = say(world, cid, "@Caretaker design a candidate",
               action="ask-participant",
               dispatch=[{"participant": care, "work": "design a candidate",
                          "coordinate": True}])
    parent = root["expectations"][0]
    result = _answer(cv, cid, care, parent, "Round 3: unique-commit-4037e33",
                     replies_to=root["turn"],
                     claim={"result": "partly",
                            "summary": "candidate presented"})
    follow = say(world, cid, "I approve this work; merge it",
                 replies_to=result, action="ask-mentis")
    for i in range(6):
        say(world, cid, f"Unrelated newer delivery {i}", action="record-only")
    source_grant = next(t["grant"] for t in told
                        if t["grant"]["expectation"] == follow["expectation"])
    out = _op(world, "attach_follow_up", {"work": parent}, source_grant)
    assert out["resumed"]
    D.dispatch(world["state"], **out["dispatches"][0])
    prompt = told[-1]["prompt"]
    assert "I approve this work" in prompt
    assert "IN REPLY TO." in prompt
    assert result in prompt and "unique-commit-4037e33" in prompt


def test_r5_a_revision_may_put_a_form_on_its_predecessor_s_result(world):
    cv = world["cv"]
    actor, parent, grant = _coordinator(world, a_conversation(world))
    cid = grant["conversation"]
    builder = cv.create_participant("@Builder")
    cv.join(builder, cid, attributed_to=world["who"]["@brian"])
    first = _op(world, "delegate", {"participant": builder,
                                    "work": "build first candidate",
                                    "solution": "open", "reasoning": "deep"},
                grant)
    result = _answer(cv, cid, builder, first["expectation"],
                     "First candidate commit 111111", replies_to=first["turn"],
                     claim={"result": "met", "summary": "candidate built"})
    nxt = say(world, cid, "Revise this candidate", replies_to=result,
              action="ask-participant",
              dispatch=[{"participant": actor, "work": "revise"}])
    second_grant = dict(grant, expectation=nxt["expectations"][0])
    second = _op(world, "delegate", {"participant": builder,
                                     "work": "build revision"}, second_grant)
    req = cv._act(second["expectation"])["detail"]["routing"]["requirements"]
    assert first["expectation"] in req["relation"]["ref"]
    child_grant = dict(grant, participant=builder,
                       expectation=second["expectation"])
    out = _op(world, "request_decision",
              {"question": "Approve revision to this candidate?",
               "on": result}, child_grant)
    assert out["ok"]


def test_r6_the_already_carried_block_is_bounded(world, monkeypatch):
    from mentis.conversation import threads
    cv = world["cv"]
    rows = [{"expectation": f"opr-{i:012x}", "turn": f"ent-{i:012x}",
             "number": i + 1, "carrier": world["steward"], "at": i}
            for i in range(5000)]
    monkeypatch.setattr(cv, "open_requests_by", lambda *a, **kw: rows)
    monkeypatch.setattr(posting, "_first_words", lambda *a, **kw: "x" * 160)
    monkeypatch.setattr(threads, "owner_replied_later", lambda *a, **kw: None)
    block = posting.already_carried(cv, "ent-conversation",
                                    world["who"]["@brian"], besides="opr-new")
    shown = block.count("- request ")
    assert 1 <= shown <= posting.ALREADY_ROWS
    assert len(block) < posting.ALREADY_CHARS + 600
    assert f"opr-{4999:012x}" in block            # newest first
    assert f"and {5000 - shown} more not shown" in block
    assert "work_overview conversation=ent-conversation" in block
