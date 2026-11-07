"""A deferral the owner decided stands: the finding is not offered to them again.

Owner, 2026-11-07: "Do not ask me to reconsider a deferral I have already explicitly decided."
Before this, a finding kept deferred was offered again whenever its trunk finished again.
"""

from mentis.operational import (offer_reconsideration, owner_decided,
                                resolve_reconsideration_decision, trunk_of)
from tests.test_manual_session import _session, world  # noqa: F401


def _finish_again(cv, request, by):
    """The trunk is finished again: another claim that its request is met."""
    exp = cv._act(request)
    return cv.record_act(actor=by, act="expectation-met",
                         conversation=exp["conversation"], turn=exp["turn"],
                         caused_by=request, because="finished again")


def test_a_finding_kept_deferred_is_not_offered_again(world):
    cv = world["st"].cv
    _, op = _session(world)
    _, opened = op("open_conversation", name="Deferred stays deferred")
    _, request = op("record_request", conversation=opened["conversation"],
                    text="root", follow_up="ask")
    root = request["expectation"]
    _, kept = op("record_discovered_work", under=root, work="a minor visual issue")
    _, dropped = op("record_discovered_work", under=root, work="an idea nobody wants")
    _, outcome = op("record_outcome", expectation=root, outcome="root done", result="done")
    offer = outcome["reconsideration"]
    assert offer["detail"]["findings"] == [kept["expectation"], dropped["expectation"]]
    decision = offer["detail"]["decision_expectation"]
    resolved = resolve_reconsideration_decision(
        cv, decision, actor=cv.expectation_state(decision)["expected_of"],
        defer=[kept["expectation"]], dismiss=[dropped["expectation"]])
    assert resolved.get("ok"), resolved
    assert owner_decided(cv, kept["expectation"]) == "kept deferred"

    # the trunk finishes again: nothing it found is put to the owner a second time
    _finish_again(cv, root, cv.expectation_state(decision)["expected_of"])
    turn = trunk_of(world["st"].brain, root)["originating_turn"]
    assert offer_reconsideration(world["st"].brain, turn) is None
    offers = [a for a in cv.history(act="reconsideration-offered")
              if kept["expectation"] in (a["detail"] or {}).get("findings", ())]
    assert len(offers) == 1
