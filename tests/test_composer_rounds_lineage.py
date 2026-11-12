"""The Quiet Chat composer rounds (conversation ent-e05dcf622c97, 2026-11-11),
reconstructed in the record's own shape, through the real posting, delegate and
dispatch paths (round 2 of the model-selection correction, workstream S):

1. Round 1 is delegated `complex` (open/deep) on a delegation Turn; the Builder
   returns on its OWN reply post, not on the delegation Turn.
2. The owner's next post REPLIES TO THE DELEGATION TURN and becomes a fresh
   request for the carrier.
3. Round 2 is delegated `bounded` under that request -- with the owner's post
   as a reference, and, in a variant, with no references at all. Both must be
   found as continuing round 1: open/deep inherited, an opus-class model at
   high, not sonnet at medium.
4. The owner rejects round 2 (an owner verdict) and replies to the round-2
   post; round 3, delegated under that reply with nothing stated, is a
   detected revision of failed work and must restate (D4).
5. The owner approves round 3 in a post; an `implements` citing that post may
   run at specified/substantial (sonnet-class). One citing only the design
   result keeps open/deep.
"""

from __future__ import annotations

import pytest

from mentis.worker import NotPermitted
from tests._catalogue_world import (cat_real, delegate, latest_start,  # noqa: F401
                                    reply_of, routing_of, run)
from tests._loop import a_conversation, post, say, world  # noqa: F401

UI = ["build_ui", "drive_browser"]


def _carry(world, cat_real, cid, text, *, replies_to=None):
    """An owner post addressed to the carrier, dispatched for real: (the
    request, the owner's Turn, the carrier's grant)."""
    got = say(world, cid, text, action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": text}],
              **({"replies_to": replies_to} if replies_to else {}))
    assert "error" not in got, got
    return got["expectations"][0], got["turn"], cat_real["grants"][-1]


@pytest.fixture()
def rounds(world, cat_real):
    cv = world["cv"]
    cid = a_conversation(world, "Quiet Chat Mark 2")
    builder = cv.create_participant("@Builder")
    composer = cv.create_participant("@Builder-QuietComposer")
    for p in (builder, composer):
        cv.join(p, cid, attributed_to=world["who"]["@brian"])
    # 20:10 the owner's design request, carried by the Caretaker-shaped steward
    p1, o1, g1 = _carry(world, cat_real, cid,
                        "design: approved mockups before implementation")
    # round 1, delegated `complex` on its own delegation Turn
    r1 = delegate(world, g1, participant=builder, work="mockups, round 1",
                  requires=UI, difficulty="complex")
    run(world, r1)
    r1_reply = reply_of(cv, r1["expectation"])
    assert r1_reply != r1["turn"], "returned on the Builder's own reply post"
    return {"cid": cid, "builder": builder, "composer": composer, "r1": r1,
            "r1_reply": r1_reply, "p1": p1}


def _round2_request(world, cat_real, rounds):
    # 20:49 the owner's revision REPLIES TO THE DELEGATION TURN
    return _carry(world, cat_real, rounds["cid"],
                  "one composer revision; wait for my decision",
                  replies_to=rounds["r1"]["turn"])


@pytest.mark.parametrize("with_references", [True, False])
def test_round_two_continues_round_one_from_the_record(world, cat_real, rounds,
                                                       with_references):
    cv = world["cv"]
    p2, o2, g2 = _round2_request(world, cat_real, rounds)
    r2 = delegate(world, g2, participant=rounds["composer"],
                  work="revise the composer mockups", requires=UI,
                  difficulty="bounded",
                  **({"references": [o2]} if with_references else {}))
    routed = routing_of(cv, r2["expectation"])
    req = routed["requirements"]
    r1 = rounds["r1"]["expectation"]
    assert req["relation"]["value"] == "continues"
    assert req["relation"]["source"] == "inherited"
    assert req["relation"]["ref"] == [r1], "round 1, not the parent request"
    assert req["relation"]["found"] and r1 in req["relation"]["found"][0]
    assert req["solution"] == {"value": "open", "source": "inherited",
                               "from": [r1]}
    # `bounded` read as substantial is RAISED to deep, said and recorded
    assert req["reasoning"]["value"] == "deep"
    assert req["reasoning"]["raised_from"] == {"value": "substantial",
                                               "source": "compat"}
    assert req["scope"] == {"value": "narrow", "source": "compat"}
    words = " ".join(r2["warnings"])
    assert "raised to 'deep'" in words and "'bounded'" in words
    assert f"the record shows this continues {r1}" in words
    assert routed["required_tier"] == "frontier"
    run(world, r2)
    start = latest_start(cv, r2["expectation"])
    d = start["detail"]
    assert start["runtime"] == "claude"
    assert (d["selected_model"], d["selected_effort"]) == ("claude-opus-5", "high")
    assert d["requirements"]["solution"]["value"] == "open"


def test_round_three_after_the_owner_rejects_round_two_must_restate(world,
                                                                    cat_real,
                                                                    rounds):
    cv = world["cv"]
    p2, o2, g2 = _round2_request(world, cat_real, rounds)
    r2 = delegate(world, g2, participant=rounds["composer"],
                  work="revise the composer mockups", requires=UI,
                  difficulty="bounded", references=[o2])
    run(world, r2)
    r2_reply = reply_of(cv, r2["expectation"])
    # 21:27 the owner rejects round 2: a verdict through the owner route
    got = post(world, f"/api/requests/{r2['expectation']}/verdict",
               {"verdict": "rejected", "why": "an open design problem"})
    assert got.get("ok"), got
    p3, o3, g3 = _carry(world, cat_real, rounds["cid"],
                        "no -- this is not what I asked for", replies_to=r2_reply)
    # nothing stated, no references: the record finds the revision (D4)
    with pytest.raises(NotPermitted) as refused:
        delegate(world, g3, participant=rounds["composer"],
                 work="round 3 of the composer mockups", requires=UI)
    words = str(refused.value)
    assert "failed substantively (found in the record)" in words
    assert r2["expectation"] in words and "D4" in words
    assert "state `solution`" in words
    # stating `new` does not escape the reassessment
    with pytest.raises(NotPermitted, match="failed substantively"):
        delegate(world, g3, participant=rounds["composer"],
                 work="round 3", requires=UI, relation="new")
    # restated: recorded, nothing escalated beyond the record's own values
    r3 = delegate(world, g3, participant=rounds["composer"],
                  work="round 3 of the composer mockups", requires=UI,
                  solution="open", reasoning="deep")
    detail = cv._act(r3["expectation"])["detail"]
    re = detail["reassessment"]
    assert re["detected"] is True
    assert re["prior"][0]["expectation"] == r2["expectation"]
    assert re["restated"] == {"solution": "open", "reasoning": "deep"}
    run(world, r3)
    d = latest_start(cv, r3["expectation"])["detail"]
    assert (d["selected_model"], d["selected_effort"]) == ("claude-opus-5", "high")


def _approved_round(world, cat_real, rounds):
    """Round 3 done and returned; the owner's approving post replies to it."""
    cv = world["cv"]
    p3, o3, g3 = _carry(world, cat_real, rounds["cid"], "round 3, please",
                        replies_to=rounds["r1"]["turn"])
    r3 = delegate(world, g3, participant=rounds["composer"], work="round 3",
                  requires=UI, solution="open", reasoning="deep")
    run(world, r3)
    r3_reply = reply_of(cv, r3["expectation"])
    p4, o4, g4 = _carry(world, cat_real, rounds["cid"],
                        "I approve of this work; implement it",
                        replies_to=r3_reply)
    return r3, r3_reply, o4, g4


def test_implementing_the_owner_approved_design_may_run_lower(world, cat_real,
                                                              rounds):
    cv = world["cv"]
    r3, r3_reply, o4, g4 = _approved_round(world, cat_real, rounds)
    build = delegate(world, g4, participant=rounds["composer"],
                     work="implement the approved round 3", requires=UI,
                     relation="implements", relation_ref=[o4],
                     solution="specified", reasoning="substantial")
    req = routing_of(cv, build["expectation"])["requirements"]
    assert req["relation"]["approval"] == {
        "ref": o4, "by": "owner_turn",
        "why": "a Turn the owner wrote, cited as the approval"}
    assert req["solution"] == {"value": "specified", "source": "stated",
                               "from": []}
    assert req["reasoning"] == {"value": "substantial", "source": "stated",
                                "from": []}
    # what the record found is recorded as overridden by the approval
    assert req["relation"]["detected"]["overridden"] is True
    assert r3["expectation"] in req["relation"]["detected"]["ref"]
    run(world, build)
    d = latest_start(cv, build["expectation"])["detail"]
    assert (d["selected_model"], d["selected_effort"]) == ("claude-sonnet-5",
                                                           "medium")


def test_implements_citing_only_the_design_result_keeps_open_deep(world,
                                                                  cat_real,
                                                                  rounds):
    cv = world["cv"]
    r3, r3_reply, o4, g4 = _approved_round(world, cat_real, rounds)
    build = delegate(world, g4, participant=rounds["composer"],
                     work="implement round 3", requires=UI,
                     relation="implements", relation_ref=[r3_reply],
                     solution="specified", reasoning="substantial")
    req = routing_of(cv, build["expectation"])["requirements"]
    assert "approval" not in req["relation"]
    assert req["solution"]["value"] == "open"
    assert req["solution"]["raised_from"] == {"value": "specified",
                                              "source": "stated"}
    assert req["reasoning"]["value"] == "deep"
    assert r3["expectation"] in req["reasoning"]["from"]
    words = " ".join(build["warnings"])
    assert "owner approval the record holds" in words
    assert "a Turn the owner wrote" in words
    run(world, build)
    d = latest_start(cv, build["expectation"])["detail"]
    assert (d["selected_model"], d["selected_effort"]) == ("claude-opus-5", "high")


def test_implements_citing_an_owner_decision_or_verdict(world, cat_real, rounds):
    """The other owner approvals: a decision the owner answered, and the
    owner's verdict accepting the result. Another participant's post is not."""
    from mentis.conversation import DECISION_ANSWERED
    from mentis.web.dispatch import owner_approval
    cv = world["cv"]
    r3, r3_reply, o4, g4 = _approved_round(world, cat_real, rounds)
    owner = world["who"]["@brian"]
    question = cv.record_act(actor=world["steward"], act="expectation-recorded",
                             detail={"expects": "decision"})
    assert owner_approval(cv, question) is None, "asked, not answered"
    answered = cv.record_act(actor=owner, act=DECISION_ANSWERED,
                             caused_by=question, detail={"option": 0})
    assert owner_approval(cv, question)["by"] == "owner_decision"
    assert owner_approval(cv, answered)["by"] == "owner_decision"
    got = post(world, f"/api/requests/{r3['expectation']}/verdict",
               {"verdict": "accepted", "why": "approved round 3"})
    assert owner_approval(cv, got["act"])["by"] == "owner_verdict"
    assert owner_approval(cv, r3["expectation"])["by"] == "owner_verdict"
    # the design result itself, and a non-owner's post, are not approvals
    assert owner_approval(cv, r3_reply) is None
    build = delegate(world, g4, participant=rounds["composer"],
                     work="implement round 3", requires=UI,
                     relation="implements", relation_ref=[answered],
                     solution="specified", reasoning="substantial")
    req = routing_of(cv, build["expectation"])["requirements"]
    assert req["relation"]["approval"]["by"] == "owner_decision"
    assert req["reasoning"]["value"] == "substantial"
