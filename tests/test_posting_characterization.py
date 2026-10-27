"""Characterization of the turns route's branches no other test reached.

Fluid F2 moved the body of `POST /api/conversations/<id>/turns` (and of
`/api/turns/<id>/address`) into `mentis/conversation/posting.py`. Measured over
the 123 test files that exercise posting, these branches of the moved code ran
in none of them, so their behaviour is pinned here, through the production
route, as it was before the move: what each answers, and that it writes and
dispatches nothing.
"""
from __future__ import annotations

from mentis.conversation import posting
from tests._loop import OPTIONS, REASON, _ask, _withdraw, _written
from tests._loop import a_conversation, post, say, world  # noqa: F401
from tests._loop import _coordinator, rt  # noqa: F401


def test_a_choice_that_is_not_an_object_is_refused(world):
    cid = a_conversation(world)
    before = _written(world)
    out = say(world, cid, "pick", chose="the first one")
    assert out == {"error": "a choice names the expectation and the option"}
    assert _written(world) == before and world["sent"] == []


def test_a_choice_naming_no_decision_is_refused(world):
    cid = a_conversation(world)
    before = _written(world)
    out = say(world, cid, "pick", chose={"expectation": "ent-000000000000",
                                         "option": 0})
    assert out == {"error": "there is no such decision to choose an answer to",
                   "expectation": "ent-000000000000"}
    assert _written(world) == before


def test_findings_chosen_on_a_decision_that_offered_none_is_refused(world, rt):
    cid = a_conversation(world)
    _coach, _parent, g = _coordinator(world, cid)
    asked = _ask(world, g, options=OPTIONS)
    before = _written(world)
    out = say(world, cid, OPTIONS[0]["label"], replies_to=asked["turn"],
              action="record-only",
              chose={"expectation": asked["expectation"], "option": 0,
                     "selections": {}})
    assert out == {"error": "that decision offered no findings to choose for",
                   "expectation": asked["expectation"]}
    assert _written(world) == before


def test_authority_that_is_not_a_list_is_refused(world):
    cid = a_conversation(world)
    before = _written(world)
    out = say(world, cid, "work", action="ask-participant", dispatch=[
        {"participant": world["who"]["@Ada"], "authority": "everything"}])
    assert out["error"] == "authority is a list of what this work may organise"
    assert "organising" in out
    assert _written(world) == before and world["sent"] == []


def test_continuing_work_this_reply_does_not_continue_is_refused(world):
    cid = a_conversation(world)
    first = say(world, cid, "the start", action="record-only")["turn"]
    before = _written(world)
    out = say(world, cid, "go on", action="ask-participant", replies_to=first,
              dispatch=[{"participant": world["who"]["@Ada"],
                         "continues": "ent-000000000000"}])
    assert out == {"error": "that is not open, authorised work this reply "
                            "continues"}
    assert _written(world) == before and world["sent"] == []


def test_addressing_what_is_not_a_turn_is_refused(world):
    cid = a_conversation(world)
    before = _written(world)
    out = post(world, f"/api/turns/{cid}/address",
               {"participant": world["who"]["@Ada"],
                "by": world["who"]["@brian"]})
    assert out == {"error": "that is not a turn in a conversation"}
    assert _written(world) == before


def test_a_key_written_between_the_two_checks_replays_under_the_lock(
        world, monkeypatch):
    """THE RACE: the first look (outside the write lock) misses, another
    request writes the key, and the look under the lock finds it -- so the
    second request writes and dispatches nothing and answers the first's."""
    cid = a_conversation(world)
    first = say(world, cid, "once", action="ask-mentis", op="raced")
    assert len(world["sent"]) == 1
    from mentis.conversation import anchors
    real, looks = anchors.prior_outcome, []

    def miss_first(*a, **kw):
        looks.append(1)
        return None if len(looks) == 1 else real(*a, **kw)

    monkeypatch.setattr(anchors, "prior_outcome", miss_first)
    before = _written(world)
    again = say(world, cid, "once", action="ask-mentis", op="raced")
    assert len(looks) == 2
    assert again == {**first, "replayed": True}
    assert _written(world) == before and len(world["sent"]) == 1


def test_a_withdrawal_closed_meanwhile_is_refused_under_the_lock(
        world, rt, monkeypatch):
    """THE RACE: the decision is open when first asked, and closed by the
    time the write lock is held -- the second answer writes nothing."""
    cid = a_conversation(world)
    _coach, _parent, g = _coordinator(world, cid)
    asked = _ask(world, g, options=OPTIONS)
    real, looks = posting.withdrawal_refusal, []

    def closed_meanwhile(*a, **kw):
        looks.append(1)
        return (real(*a, **kw) if len(looks) == 1 else
                {"error": "this decision is already closed, so there is "
                          "nothing to withdraw",
                 "expectation": asked["expectation"]})

    monkeypatch.setattr(posting, "withdrawal_refusal", closed_meanwhile)
    before = _written(world)
    out = _withdraw(world, cid, asked, REASON)
    assert len(looks) == 2
    assert out["error"].startswith("this decision is already closed")
    assert _written(world) == before and world["sent"] == []
