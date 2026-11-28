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
    assert follow_up_for(cv, first) == "unrestricted"


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
