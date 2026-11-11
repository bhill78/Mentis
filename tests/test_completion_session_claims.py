"""WS-C review item 11: a session claims only its OWN work.

Since WS-I every hand-started session has a participant of its own. Another
session may still post the outcome of work a session recorded (that
continuity is WS-I's), but the CLAIM is made only by the participant that
recorded the request or carries it -- for another, after `take_up`.
"""

from __future__ import annotations

from tests.test_manual_session import world  # noqa: F401
from tests.test_session_contribution import _start


def test_only_the_recording_participant_claims(world):
    cv = world["st"].cv
    g1, first = _start(world, runtime="codex")
    g2, second = _start(world, runtime="claude")
    assert g1["participant"] != g2["participant"]
    _, opened = first("open_conversation", name="Session claims")
    _, request = first("record_request", conversation=opened["conversation"],
                       text="Try this")
    exp = request["expectation"]
    status, other = second("record_outcome", expectation=exp,
                           outcome="Done by somebody else", result="done")
    assert status == 200, other
    assert other["claim"] is None and other["fulfilled_by"] is None
    assert "take_up" in other["claim_why_not"]
    assert not cv.expectation_state(exp)["satisfied_by"]
    status, own = first("record_outcome", expectation=exp,
                        outcome="Done by its recorder", result="done")
    assert status == 200 and own["claim"] and own["fulfilled_by"], own
    assert cv._act(own["claim"])["actor"] == g1["participant"]
