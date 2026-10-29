"""The hand-started path uses the same gravity policy as dispatched work."""

from mentis.operational import pursuit_permitted
from tests.test_manual_session import _session, world


def test_session_request_carries_discovery_and_keeps_the_policy_reply(world):
    _, op = _session(world)
    status, opened = op("open_conversation", name="Carried gravity")
    assert status == 200
    status, request = op("record_request",
                         conversation=opened["conversation"], text="root",
                         follow_up={"depth": 1})
    assert status == 200
    status, found = op("record_discovered_work",
                       under=request["expectation"], work="side work")
    assert status == 200
    assert found["may_pursue"] is True
    assert "permission covers it" in found["note"]
    assert pursuit_permitted(world["st"].cv, found["expectation"])


def test_session_cannot_carry_an_unrelated_request(world):
    _, op = _session(world)
    status, found = op("record_discovered_work", under="opr-000000000000",
                       work="not mine")
    assert status == 403
    assert "recorded by this session participant" in found["error"]


def test_session_picks_up_covered_finding_under_its_request(world, monkeypatch):
    import mentis.web as web
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: None)
    _, op = _session(world)
    _, opened = op("open_conversation", name="Pickup")
    _, helper = op("summon_participant", alias="GravityHelper",
                   conversation=opened["conversation"])
    _, request = op("record_request", conversation=opened["conversation"],
                    text="root", follow_up="unrestricted")
    _, found = op("record_discovered_work", under=request["expectation"],
                  work="side work")
    status, picked = op("delegate", under=request["expectation"],
                        expectation=found["expectation"],
                        participant=helper["participant"], work="side work")
    assert status == 200 and picked["picked_up"] is True


def test_gravity_never_grants_an_unknown_runtime_capability(world):
    _, op = _session(world)
    _, opened = op("open_conversation", name="No authority widening")
    _, helper = op("summon_participant", alias="BoundedHelper",
                   conversation=opened["conversation"])
    _, request = op("record_request", conversation=opened["conversation"],
                    text="root", follow_up="unrestricted")
    _, found = op("record_discovered_work", under=request["expectation"],
                  work="side work")
    status, refused = op("delegate", under=request["expectation"],
                         expectation=found["expectation"],
                         participant=helper["participant"], work="side work",
                         requires=["imaginary_power"])
    assert status == 403
    assert "no capability any runtime can declare" in refused["error"]
