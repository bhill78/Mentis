"""Permissions changed on a follow-up to existing work (owner, 2026-11-28).

Inheriting a request's permissions is a convenience, not a constraint. When the
owner says something else on a reply that continues work -- or on a follow-up of
theirs that is handed to the work it is about -- that is their newer
authorisation for that work and what it hands on. The earlier grant stays where
it was recorded, and no agent's word widens anything.
"""

from __future__ import annotations

from mentis.operational import ASK, follow_up_for, pursuit_permitted  # noqa: F401
from mentis.operational import consent as C
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_run_consent import _carried_with_a_result, _request, ws  # noqa: F401


def _continue(world, cid, ada, answered, **spec):
    return say(world, cid, "carry on", replies_to=answered, action="ask-participant",
               dispatch=[{"participant": ada, "work": "carry on", **spec}])


def test_side_work_permission_can_be_changed_on_a_reply_that_continues_work(world):
    cid = a_conversation(world)
    ada, first, answered = _carried_with_a_result(world, cid)
    got = _continue(world, cid, ada, answered, follow_up={"depth": 2})
    assert "error" not in got, got
    new = got["expectations"][0]
    cv = world["cv"]
    assert cv._act(new)["caused_by"] == first           # it still continues that work
    assert follow_up_for(cv, new) == {"depth": 2}
    assert follow_up_for(cv, first) == ASK              # the earlier grant is untouched


def test_ask_said_on_a_reply_narrows_what_the_work_carried(world):
    cid = a_conversation(world)
    ada, first, answered = _carried_with_a_result(world, cid, follow_up="unrestricted")
    got = _continue(world, cid, ada, answered, follow_up="ask")
    assert "error" not in got, got
    new = got["expectations"][0]
    cv = world["cv"]
    assert cv._act(new)["detail"]["follow_up"] == "ask"
    assert follow_up_for(cv, new) == ASK
    # a narrowing reaches the work it continues; its own record is unchanged
    assert follow_up_for(cv, first) == ASK
    assert cv._act(first)["detail"]["follow_up"] == "unrestricted"


def test_a_reply_that_says_nothing_inherits_as_before(world):
    cid = a_conversation(world)
    ada, first, answered = _carried_with_a_result(world, cid, follow_up={"depth": 1})
    got = _continue(world, cid, ada, answered)
    new = got["expectations"][0]
    assert "follow_up" not in (world["cv"]._act(new)["detail"] or {})
    assert follow_up_for(world["cv"], new) == {"depth": 1}


def test_an_agent_cannot_widen_side_work_permission(world):
    """Below the original request only the owner's word is read."""
    cv = world["cv"]
    cid = a_conversation(world)
    turn, origin = _request(world, cid)

    def under(cause, by, follow_up):
        return cv.expect(turn, of=world["steward"], kind="result", by=by, caused_by=cause,
                         detail={"follow_up": follow_up})

    cont = under(origin, world["who"]["@brian"], {"depth": 1})      # the owner's continuation
    child = under(cont, world["steward"], "unrestricted")           # an agent's, beneath it
    assert follow_up_for(cv, child) == {"depth": 1}
    beside = under(origin, world["steward"], "unrestricted")        # an agent continuing the origin
    assert follow_up_for(cv, beside) == ASK


def test_permissions_on_a_follow_up_handed_to_work_govern_that_work(world, ws):
    """An Ask Mentis follow-up the owner wrote with a Permission Mode and side-work
    permission, handed by its carrier to the work it is about: what they chose
    governs that work from then on, and the follow-up keeps its own record."""
    cv = world["cv"]
    cid = a_conversation(world)
    work = say(world, cid, "build the thing", action="ask-mentis")["expectation"]
    assert C.of_request(cv, work)["mode"] == ASK and follow_up_for(cv, work) == ASK
    follow = say(world, cid, "and you may run the tests and pursue side work", action="ask-mentis",
                 ask_mentis={"consent": {"mode": "task", "workspaces": [ws["repo"]]},
                             "follow_up": {"depth": 1}})
    assert "error" not in follow, follow
    follow = follow["expectation"]
    got = cv.attach_follow_up(follow, work, by=world["steward"])
    assert "error" not in got, got
    now = C.of_request(cv, work)
    assert now["mode"] == "task" and ws["repo"] in now["workspaces"]
    assert now["source"] == "owner-changed" and now["granted_at"] == work
    assert follow_up_for(cv, work) == {"depth": 1}
    # the follow-up's own record is unchanged
    assert cv._act(follow)["detail"]["follow_up"] == {"depth": 1}


def test_a_later_handed_follow_up_narrows_again(world, ws):
    cv = world["cv"]
    cid = a_conversation(world)
    work = say(world, cid, "build the thing", action="ask-mentis",
               ask_mentis={"consent": {"mode": "task", "workspaces": [ws["repo"]]},
                           "follow_up": "unrestricted"})["expectation"]
    assert C.of_request(cv, work)["mode"] == "task"
    follow = say(world, cid, "stop: ask me first from now on", action="ask-mentis",
                 ask_mentis={"consent": {"mode": "ask", "workspaces": []},
                             "follow_up": "ask"})["expectation"]
    assert "error" not in cv.attach_follow_up(follow, work, by=world["steward"])
    assert C.of_request(cv, work)["mode"] == ASK
    assert follow_up_for(cv, work) == ASK


def test_a_handed_follow_up_with_no_permissions_changes_nothing(world, ws):
    cv = world["cv"]
    cid = a_conversation(world)
    work = say(world, cid, "build the thing", action="ask-mentis",
               ask_mentis={"consent": {"mode": "task", "workspaces": [ws["repo"]]},
                           "follow_up": {"depth": 2}})["expectation"]
    follow = say(world, cid, "also mention the date", action="ask-mentis")["expectation"]
    assert "error" not in cv.attach_follow_up(follow, work, by=world["steward"])
    assert C.of_request(cv, work)["mode"] == "task"
    assert follow_up_for(cv, work) == {"depth": 2}


# -- a continuation's narrowing reaches the work it continues (owner, 2026-11-28) --------------


def test_narrowing_on_a_continuation_also_narrows_the_work_it_continues(world):
    """Revoking takes effect on whatever is still doing the work; widening does not reach back."""
    cid = a_conversation(world)
    ada, first, answered = _carried_with_a_result(world, cid, follow_up="unrestricted")
    got = _continue(world, cid, ada, answered, follow_up={"depth": 1})
    new = got["expectations"][0]
    cv = world["cv"]
    assert follow_up_for(cv, new) == {"depth": 1}
    assert follow_up_for(cv, first) == {"depth": 1}            # narrowed, not left wide
    assert cv._act(first)["detail"]["follow_up"] == "unrestricted"   # its record is untouched


def test_consent_narrowed_on_a_continuation_reaches_the_continued_work_and_its_children(world, ws):
    cv = world["cv"]
    cid = a_conversation(world)
    ada, first, answered = _carried_with_a_result(
        world, cid, consent={"mode": "all", "workspaces": [ws["repo"]]})
    # work the carrier delegated under the first request, still open
    child = cv.expect(cv._act(first)["turn"], of=world["steward"], kind="result",
                      by=ada, caused_by=first)
    assert C.of_request(cv, child)["mode"] == "all"
    got = _continue(world, cid, ada, answered, consent={"mode": "ask"})
    assert "error" not in got, got
    assert C.of_request(cv, first)["mode"] == "ask"
    assert C.of_request(cv, first)["source"] == "owner-narrowed"
    assert C.of_request(cv, child)["mode"] == "ask"
    assert C.of_request(cv, got["expectations"][0])["mode"] == "ask"


def test_widening_on_a_continuation_does_not_widen_the_work_it_continues(world, ws):
    cv = world["cv"]
    cid = a_conversation(world)
    ada, first, answered = _carried_with_a_result(world, cid)
    got = _continue(world, cid, ada, answered, consent={"mode": "all", "workspaces": [ws["repo"]]})
    assert C.of_request(cv, got["expectations"][0])["mode"] == "all"
    assert C.of_request(cv, first)["mode"] == ASK


def test_coordination_taken_away_on_a_continuation_holds_the_line_of_work(world):
    """`authority: []` on a reply that continues coordinating work: the new request organises
    nothing, the request it continues is held to that now, and a later plain continuation
    inherits the narrowing rather than the original grant."""
    cv = world["cv"]
    cid = a_conversation(world)
    ada, first, answered = _carried_with_a_result(world, cid)       # granted coordinate
    assert "coordinate" in cv.authority_in_force(first)["operations"]
    got = _continue(world, cid, ada, answered, authority=[])
    assert "error" not in got, got
    new = got["expectations"][0]
    assert cv.authority_in_force(new)["operations"] == []
    now = cv.authority_in_force(first)
    assert now["operations"] == [] and now["narrowed_by"] == new
    assert "coordinate" in cv.authority_of(first)["operations"]       # the grant stays recorded
    # granting it again on a later continuation reaches the new request
    again = cv.say(cid, ada, [{"type": "text", "text": "done"}], replies_to=got["turn"])
    regrant = _continue(world, cid, ada, again, coordinate=True)
    assert "error" not in regrant, regrant
    assert "coordinate" in cv.authority_in_force(regrant["expectations"][0])["operations"]


def test_a_live_runs_grant_is_narrowed_at_the_door(world):
    from mentis.web import _authority_now
    cv = world["cv"]
    cid = a_conversation(world)
    ada, first, answered = _carried_with_a_result(world, cid)
    grant = {"expectation": first, "scope": "organising",
             "operations": list(cv.authority_of(first)["operations"])}
    st = type("St", (), {"cv": cv})()
    assert _authority_now(st, grant) == grant
    _continue(world, cid, ada, answered, authority=[])
    assert _authority_now(st, grant)["operations"] == []


def test_an_agent_cannot_change_authority_by_continuing(world):
    """Only the owner's explicit grants on their own continuations count."""
    cv = world["cv"]
    cid = a_conversation(world)
    ada, first, answered = _carried_with_a_result(world, cid)
    turn = cv._act(first)["turn"]
    sneaky = cv.expect(turn, of=ada, kind="result", by=ada, caused_by=first)
    cv.grant_authority(sneaky, [], by=ada, source="explicit", origin=first, because="t")
    assert "coordinate" in cv.authority_in_force(first)["operations"]


def test_the_continuation_read_shows_what_the_work_carries(world):
    from tests.test_run_consent import get
    cid = a_conversation(world)
    ada, first, answered = _carried_with_a_result(world, cid, follow_up={"depth": 2})
    got = get(world, f"/api/continuation?replies_to={answered}&participant={ada}")
    (c,) = got["candidates"]
    assert c["expectation"] == first and c["coordinate"] is True
    assert c["follow_up"] == {"depth": 2} and c["consent"]["mode"] == ASK
