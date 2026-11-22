"""The owner's stop holds for hand-started sessions too (found by independent
review): a session cannot record more work under a stopped request, nor take
up work found under it. No dispatch is involved on that path."""

from __future__ import annotations

from tests.test_manual_session import _session, world  # noqa: F401


def _park(cv, exp):
    from mentis.conversation.owner import _owner
    from mentis.operational.stage import WORK_PARKED
    a = cv._act(exp)
    return cv.record_act(actor=_owner(cv), act=WORK_PARKED,
                         conversation=a["conversation"], turn=a["turn"],
                         caused_by=exp, about=[exp], because="stopped")


def test_a_session_cannot_record_or_take_up_work_under_a_stopped_request(
        world, monkeypatch):
    from mentis import web
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: None)
    cv = world["st"].cv
    grant, op = _session(world)
    _, opened = op("open_conversation", name="Stopped line")
    cid = opened["conversation"]
    _, trunk = op("record_request", conversation=cid, text="trunk",
                  follow_up={"depth": 2})
    status, found = op("record_discovered_work", under=trunk["expectation"],
                       work="a side task found along the way")
    assert status == 200, found
    _park(cv, trunk["expectation"])

    status, refused = op("take_up", expectation=found["expectation"],
                         under=trunk["expectation"])
    assert status == 403 and "stopped this work" in refused["error"], refused
    assert cv.assigned_carrier(found["expectation"])["carrier"] is None

    status, refused = op("record_request", conversation=cid, text="carry on",
                         parent=trunk["expectation"])
    assert status == 403 and "stopped this work" in refused["error"], refused


def test_stopped_work_can_be_closed_but_not_given_remaining_work(world, monkeypatch):
    from mentis import web
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: None)
    cv = world["st"].cv
    grant, op = _session(world)
    _, opened = op("open_conversation", name="Stopped outcome")
    _, trunk = op("record_request", conversation=opened["conversation"], text="trunk")
    _park(cv, trunk["expectation"])
    status, refused = op("record_outcome", expectation=trunk["expectation"],
                         outcome="partly done", result="partial",
                         remaining=["carry on with the rest"])
    assert status == 403 and "stopped this work" in refused["error"], refused
    status, closed = op("record_outcome", expectation=trunk["expectation"],
                        outcome="stopped here at the owner's direction",
                        result="partial")
    assert status == 200, closed
