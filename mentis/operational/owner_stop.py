"""THE OWNER'S STOP IS AUTHORITATIVE (owner instruction 2026-11-22).

"Once the owner stops a Work, no existing agent, pending return, retry, or
automatic continuation can restart it without fresh owner authorization."

WHAT WENT WRONG. The owner told a carrier to stop a piece of work and stopped
its running run. Stopping a run ends that execution only, and nothing in the
record said the WORK was stopped: the stopped child counted as returned, the
carrier was resumed because "nothing it waited on is outstanding", and it
delegated a recovery of the very run the owner had stopped.

THE STATE IS AN EXISTING ACT. `work-parked` (`operational.stage.WORK_PARKED`)
already means "the owner chose to leave a request where it stopped, until they
say to continue", and Work views already read it. It was only never enforced.
The owner's stop door (`POST /api/work/<request>/stop`) writes it; this module
is the one question every path that could continue work asks of it:

    parked_over(cv, request) -> the park that holds this request, or None

A PARK HOLDS THE REQUEST IT IS ON AND EVERYTHING UNDER IT: every request whose
`caused_by` chain passes through it -- delegated children, continuations
recorded under it, retries of them. A run of any of them is not started
(`dispatch`), the work is not resumed (`claim_resumption`), and its carrier
cannot hand on more of it (`delegate`). Stopping one execution stays what it
was; parking is the Work-level stop.

ONLY THE OWNER LIFTS IT, AND ONLY BY A NEWER ACT OF THEIR OWN in the same line:
a request the owner records after the park, at or below the parked request
(their reply asking for the work to continue), or their retry of it
(`work-retried`). Nothing an agent records, no return, resumption, retry or
recovery, and no time passing lifts it. A later park holds again.

WHAT IT IS NOT. Not a lock on the filesystem or on a process that is already
running: stopping those is the run stop's (`agents_halt_run`), which the stop
door also asks of every live run in the line. Nothing here deletes, closes or
marks anything met: a parked request is still open, unfinished, and resumable
by the owner.
"""
from __future__ import annotations

from mentis.operational.stage import WORK_PARKED

#: The owner's retry of a request (`dispatch.retry_if_chosen`): fresh authority.
WORK_RETRIED = "work-retried"


def _owner(cv):
    from mentis.conversation.owner import _owner as owner_of
    return owner_of(cv)


def line(cv, expectation) -> list[dict]:
    """The request and every request above it, nearest first."""
    out, cur, seen = [], expectation, set()
    while cur and cur not in seen:
        act = cv._act(cur)
        if act is None or act.get("act") != "expectation-recorded":
            break
        seen.add(cur)
        out.append(act)
        cur = act.get("caused_by")
    return out


def parked_over(cv, expectation) -> dict | None:
    """The `work-parked` act holding `expectation`, or None.

    Walks from the request up. At each level the owner's own authority there
    -- the owner recorded that request, or retried it -- is noted first, then
    the newest park on that level is compared with the newest owner authority
    seen at or below it: a park newer than all of it holds.
    """
    if not expectation:
        return None
    owner = _owner(cv)
    fresh = 0.0
    for level in line(cv, expectation):
        if owner and level.get("actor") == owner:
            fresh = max(fresh, level["at"])
        acts = cv.history(caused_by=level["id"])
        for a in acts:
            if a["act"] == WORK_RETRIED and owner and a.get("actor") == owner:
                fresh = max(fresh, a["at"])
        parks = [a for a in acts if a["act"] == WORK_PARKED]
        if parks:
            newest = max(parks, key=lambda a: a["at"])
            if newest["at"] > fresh:
                return {**newest, "parked_request": level["id"],
                        "held_request": expectation}
    return None


def why(cv, park) -> str:
    """The refusal's words: who stopped which work, and how it continues."""
    who = cv.alias(park.get("actor")) or "the owner"
    said = (park.get("because") or "").strip()
    return (f"{who} stopped this work (request {park['parked_request']})"
            + (f": {said}" if said else "")
            + ". Nothing restarts it by itself: only a new request of the "
              "owner's, continuing it, does")


def descendants(cv, expectation) -> list[str]:
    """The request and every request recorded under it (by `caused_by`)."""
    out, frontier = [expectation], [expectation]
    seen = {expectation}
    while frontier:
        kids = [a["id"] for a in cv._c.operational(act="expectation-recorded",
                                                   caused_by=frontier)
                if a["id"] not in seen]
        seen.update(kids)
        out += kids
        frontier = kids
    return out
