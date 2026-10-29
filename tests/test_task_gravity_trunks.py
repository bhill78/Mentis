"""Completion and reconsideration on the manual-session trunk."""

from mentis.operational import owner_decided, resolve_reconsideration_decision
from tests.test_manual_session import _session, world


def test_done_trunk_offers_its_deferred_finding(world):
    _, op = _session(world)
    _, opened = op("open_conversation", name="Reconsider")
    _, request = op("record_request", conversation=opened["conversation"],
                    text="root", follow_up="ask")
    _, found = op("record_discovered_work", under=request["expectation"],
                  work="later")
    status, outcome = op("record_outcome", expectation=request["expectation"],
                         outcome="root done", result="done")
    assert status == 200
    offer = outcome["reconsideration"]
    assert offer["detail"]["findings"] == [found["expectation"]]


def test_owner_decision_overrides_unrestricted_permission(world):
    _, op = _session(world)
    _, opened = op("open_conversation", name="Owner decides")
    _, request = op("record_request", conversation=opened["conversation"],
                    text="root", follow_up="unrestricted")
    _, found = op("record_discovered_work", under=request["expectation"],
                  work="later")
    _, outcome = op("record_outcome", expectation=request["expectation"],
                    outcome="root done", result="done")
    decision = outcome["reconsideration"]["detail"]["decision_expectation"]
    decision_owner = world["st"].cv.expectation_state(decision)["expected_of"]
    resolved = resolve_reconsideration_decision(
        world["st"].cv, decision, actor=decision_owner,
        dismiss=[found["expectation"]])
    assert resolved.get("ok"), resolved
    assert owner_decided(world["st"].cv, found["expectation"]) == "dismissed"
