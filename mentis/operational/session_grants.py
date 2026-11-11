"""The owner's explicit grant of carrying and coordinating to a hand-started session.

Round 2, O4 (docs/modernization/CONTRACT.md "Round 2 — A"). A hand-started CLI
session holds no coordination authority merely because it exists: it
coordinates only under a request a session recorded (`under`, WS-I). The owner
may also hand it a request of the owner's own: this grant lets one CLI
Participant carry that request -- name it in `under` (and so coordinate under
it), close it with `record_outcome`, and claim its outcome -- exactly as if a
session had recorded it. Nothing else.

IT IS THE OWNER'S ACT, recorded as such (`session-coordination-granted`, actor
the owner, about the request and the Participant, with the owner's words),
and REVOCABLE (`session-coordination-revoked`, naming the grant). It confers
nothing on a dispatched run, on any other Participant or on any other request,
establishes nothing, and starts nothing. It is reached only through the
owner's HTTP route (`POST /api/session-grants`), never through `/api/worker`,
so no agent can grant it to itself.
"""

from __future__ import annotations

GRANTED = "session-coordination-granted"
REVOKED = "session-coordination-revoked"
SCOPE = "carry-and-coordinate"


def _problem(why: str) -> ValueError:
    return ValueError(why)


def grant(cv, *, actor: str, participant: str, request: str, because: str) -> str:
    """Record the owner's grant; returns its act. Refuses (ValueError) anything
    but the owner granting a CLI session Participant a recorded request."""
    from mentis.conversation.owner import _owner
    from mentis.session_identity import is_cli_participant
    owner = _owner(cv)
    if not owner or actor != owner:
        raise _problem("only the owner grants a hand-started session a request to carry")
    if not is_cli_participant(cv, participant):
        raise _problem(f"{participant!r} is not a hand-started CLI session's Participant; "
                       "a dispatched agent is given work by addressing it, not by this grant")
    exp = cv._act(request)
    if not exp or exp.get("act") != "expectation-recorded":
        raise _problem(f"{request!r} is not a recorded request")
    because = (because or "").strip()
    if not because:
        raise _problem("say why: the grant records the owner's words")
    return cv.record_act(
        actor=owner, act=GRANTED, conversation=exp.get("conversation"), turn=exp.get("turn"),
        caused_by=request, about=[request, participant], because=because[:300],
        detail={"participant": participant, "request": request, "scope": SCOPE})


def revoke(cv, *, actor: str, grant_act: str, because: str) -> str:
    """Record the owner's revocation of one grant; returns its act."""
    from mentis.conversation.owner import _owner
    owner = _owner(cv)
    if not owner or actor != owner:
        raise _problem("only the owner revokes a session grant")
    g = cv._act(grant_act)
    if not g or g.get("act") != GRANTED:
        raise _problem(f"{grant_act!r} is not a session grant")
    d = g.get("detail") or {}
    return cv.record_act(
        actor=owner, act=REVOKED, conversation=g.get("conversation"), turn=g.get("turn"),
        caused_by=d.get("request"), about=[d.get("request"), d.get("participant")],
        because=((because or "").strip() or "revoked by the owner")[:300],
        detail={"grant": grant_act, "participant": d.get("participant"),
                "request": d.get("request")})


def standing(cv, request: str) -> list[dict]:
    """The grants on this request that are in force, oldest first."""
    if not request:
        return []
    acts = [a for a in cv.history(caused_by=request) if a["act"] in (GRANTED, REVOKED)]
    revoked = {(a.get("detail") or {}).get("grant") for a in acts if a["act"] == REVOKED}
    return sorted((a for a in acts if a["act"] == GRANTED and a["id"] not in revoked),
                  key=lambda a: a["at"])


def granted(cv, request: str, participant: str) -> dict | None:
    """The owner's grant in force letting `participant` carry `request`, or None."""
    if not participant:
        return None
    return next((g for g in reversed(standing(cv, request))
                 if (g.get("detail") or {}).get("participant") == participant), None)
