"""WHAT THE COMPOSER'S SUBMISSION ACTUALLY AUTHORISES, on a fixture Brain.

WHY THIS IS HERE. The browser remembers one permission configuration and fills
a fresh draft in with it (`apps/fluid-web/src/fluid/composer/permissionDefault.ts`).
A focused independent re-review (adm-871e7b570a26) reproduced the one way that
can escalate authority: the Brain a page is bound to is answered after the
composer mounts, so a submission built before the answer carried the values
chosen on ANOTHER Brain, and the server -- correctly -- treats the concrete
values in an owner's submission as the authority for that work.

The correction is in the client: a submission is placed against the scope it
resolves to before its body is built, so the values of another Brain's
configuration are not in it (tests/permission_send_unit.mjs captures the
requests). THIS says what each of those two bodies comes to HERE, so that what
the client stopped sending is known to be exactly what it stopped authorising:

  * the body a stale submission sent -- Allow All, "may coordinate", side work
    to depth 1 -- records all three on the request, as the owner's submission;
  * the body the corrected composer sends for the same draft on another Brain
    records none of them: permission is asked for, nothing is organised, side
    work is asked about first.

Nothing about the server changed for this. It is the boundary the escalation
crossed, checked from the record rather than from the client's own assertions.
"""

from __future__ import annotations

from mentis.operational import consent as C
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_delegate_coordinate import _present
from tests.test_run_consent import ws  # noqa: F401

#: WHAT A DRAFT FILLED IN FROM "ALLOW ALL" CARRIES, exactly as the composer
#: serialises it (`bodyOf`, `savedOf`): the three concrete fields and nothing
#: else. The stale submission the re-review captured was this.
FILLED_IN = {"consent": {"mode": "all", "workspaces": []},
             "coordinate": True,
             "follow_up": {"depth": 1}}


def _asked(world, cid, who, **over):  # noqa: F811
    """The owner asks `who` to work, with what the submission carried."""
    out = say(world, cid, "look at the overnight run", addressed_to=[who],
              dispatch=[{"participant": who, "work": "look at it", **over}])
    assert "error" not in out, out
    return out


def _recorded(world, out):  # noqa: F811
    """The request this submission recorded: its detail, and its authority."""
    exp = out["expectations"][0]
    act = next(a for a in world["cv"]._c.operational(turn=out["turn"])
               if a["act"] == "expectation-recorded" and a["id"] == exp)
    return exp, act["detail"], out["authority"][exp]


def test_the_values_a_stale_submission_carried_are_the_authority(world, ws):  # noqa: F811
    """The escalation, as the record saw it: nothing refuses an owner's own
    concrete values, which is why they must not be another Brain's."""
    cid = a_conversation(world, "Stale submission")
    who = _present(world, cid, "@Worker")
    filled = {**FILLED_IN, "consent": {"mode": "all", "workspaces": [ws["repo"]]}}
    exp, detail, authority = _recorded(world, _asked(world, cid, who, **filled))
    assert detail["consent"]["mode"] == C.ALL
    assert C.of_request(world["cv"], exp)["mode"] == C.ALL
    assert detail["follow_up"] == {"depth": 1}
    assert authority["operations"], "coordination was granted to this work"
    assert authority["because"] == "the author granted this work coordination"


def test_the_corrected_submission_authorises_none_of_it(world, ws):  # noqa: F811
    """The same draft, sent after the page could say it was on another Brain:
    the three fields are not in the body, so none of them is on the request."""
    cid = a_conversation(world, "Placed submission")
    who = _present(world, cid, "@Worker")
    exp, detail, authority = _recorded(world, _asked(world, cid, who))
    assert "consent" not in detail
    assert C.of_request(world["cv"], exp)["mode"] == C.ASK
    assert "follow_up" not in detail
    assert not authority["operations"], "nothing was granted to organise"
    assert authority["source"] is None


def test_what_the_owner_chose_by_hand_still_reaches_the_record(world, ws):  # noqa: F811
    """The correction takes out what was FILLED IN, never what the owner
    decided: an explicit narrowing is still theirs and still arrives."""
    cid = a_conversation(world, "Chosen by hand")
    who = _present(world, cid, "@Worker")
    exp, detail, authority = _recorded(world, _asked(
        world, cid, who, consent={"mode": "task", "workspaces": [ws["repo"]]},
        follow_up="unrestricted"))
    assert detail["consent"]["mode"] == C.TASK
    assert C.of_request(world["cv"], exp)["mode"] == C.TASK
    assert detail["follow_up"] == "unrestricted"
    assert not authority["operations"], "and narrowing permission organises nothing"
