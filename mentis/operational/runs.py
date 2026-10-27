"""What each run is in, said once, from the record and what this process holds.

HEADLESS: the record's execution acts decide open or closed, as before; what
this process holds of an open run is now only what it handed MARS and what
MARS reported back (`MentisService.agents_runs`, `Execution.running`).
Mark IV's per-process observation of a runtime's stream is gone with
Foundation.

WHERE A RUN'S STATE IS WORDED -- AND WHERE IT IS STILL NOT. `/api/working`,
`/api/who` and `/api/activity` read a run through `run_state`, so the working
band, a Participant card and the Presence card cannot disagree about the same
run. There is no second status store behind it and nothing here is written.

THE PER-TRUNK WORK STATUS IS NOT YET AMONG THEM, and this file used to claim
it was. That claim belonged to a version of this work written against an
older reading of run boundaries, which `main` has since superseded; the part
that changed `mentis/operational/work.py` was deliberately not carried over,
so `work.py` still words a run itself from `runtime["instances"]`. Two
readers, two wordings. Until `work.py` is re-seated on the same reading, "they
cannot disagree" is true of three surfaces, not four.

A RUN IS ITS `execution-started` ACT, and whether it is over is decided by
`Conversation.closed_starts` -- `main`'s rule, not a second copy of it. A run
is closed when an end NAMES ITS START as `caused_by`, or when a LATER run on
the same handle has ended (an instance runs one thing at a time, so an
earlier start is behind it whatever became of it). The ends are `RUN_ENDS`:
`result-returned`, `delivery-failed` and `result-recovered` -- the third added
by `main`, and a run that ends that way SUCCEEDED; it is not a failure.

The instance id on those acts names a reusable session handle, and many runs
pass through one; nothing about a run is read from the handle's last row,
which is written when a run ENDS and so, during a later run, describes the
one before.

ONE DIVERGENCE FROM `closed_starts`'S OWN CONTRACT, SAID RATHER THAN HIDDEN:
it tells callers to pass one request's own acts, and `open_runs` passes the
record's. That makes it strictly more willing to close an orphaned start, on
the same instance-runs-one-thing reasoning the rule is built on -- but it is
a wider scope than the docstring there describes, and the two readings can
differ for a start whose own request never ended.

Three sources, never mixed without saying so:

    recorded   the run's start or end act says it
    runtime    THIS process holds the run and observed this, at this time
    unknown    the run is open by the record and no process here holds it

WHAT THIS REFUSES TO SAY. A quiet run is not "thinking", a long one is not
"stuck", and a run nobody here holds is not "dead" -- it is open, and what it
is doing is unknown. Every sentence carries the time of the observation that
supports it; the age of that observation is an age, not a verdict.
"""

from __future__ import annotations

import time

from mentis.conversation import RUN_ENDS, RUN_START

RECORDED, RUNTIME, UNKNOWN = "recorded", "runtime", "unknown"

#: How many recently ended runs the working surface shows beside the open ones.
RECENT_ENDED = 6


def clock(at: float | None, *, now: float | None = None) -> str:
    """A time as the owner reads it: the clock, and the date if not today."""
    if at is None:
        return "?"
    now = now or time.time()
    t = time.localtime(at)
    if time.strftime("%Y-%m-%d", t) == time.strftime("%Y-%m-%d",
                                                     time.localtime(now)):
        return time.strftime("%H:%M:%S", t)
    return time.strftime("%Y-%m-%d %H:%M:%S", t)


def _short(text, limit=160) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def run_state(start: dict, end: dict | None = None,
              observation: dict | None = None, *,
              now: float | None = None) -> dict:
    """ONE run's state, in words, with the time and source that support it.

    `end` is the act that closed it, if the record holds one. `observation`
    is what this process holds of it (`MentisService.agents_runs`), if it
    holds it at all. The record decides open or closed; the observation only
    ever qualifies a run the record says is open.
    """
    now = now or time.time()
    out = {"run": start["id"], "instance": start.get("execution"),
           "runtime": start.get("runtime"), "started_at": start.get("at"),
           "held_here": False}

    def said(state, words, at, source, **extra):
        out.update(state=state, words=words, at=at, source=source, **extra)
        return out

    # -- closed by the record ------------------------------------------------
    if end is not None:
        if end["act"] == "result-returned":
            return said("completed", f"completed · {clock(end['at'], now=now)}",
                        end["at"], RECORDED, ended_by=end["id"])
        # RECOVERED IS NOT FAILED. This if/else was exhaustive when a run had
        # two ways to end; `main` added a third, and without this branch a run
        # that SUCCEEDED -- whose waiter died before writing the end, and whose
        # result was then read back from the runtime's own output -- was
        # reported "failed: <the recovery reason>". The `because` on a
        # `result-recovered` act says why it had to be recovered, not why
        # anything failed, and rendering it as a failure states the opposite
        # of what happened. `Conversations` already words this case as
        # "recovered"; this is the same answer on this surface.
        if end["act"] == "result-recovered":
            owner = (end.get("detail") or {}).get("response_owner")
            return said("recovered",
                        "recovered: the run ended and nothing here saw it"
                        + ("; it had already answered"
                           if owner == "respond" else
                           "; its answer was read back from the runtime")
                        + f" · {clock(end['at'], now=now)}",
                        end["at"], RECORDED, ended_by=end["id"])
        return said("failed",
                    f"failed: {_short(end.get('because') or 'no reason recorded')}"
                    f" · {clock(end['at'], now=now)}",
                    end["at"], RECORDED, ended_by=end["id"])

    # -- open by the record, and nobody here holds it --------------------------
    if observation is None:
        return said("unknown",
                    "execution open; no process here holds it — current "
                    f"state unknown · started {clock(start.get('at'), now=now)}",
                    start.get("at"), UNKNOWN)

    # -- open by the record, and held here -------------------------------------
    # What this process holds of a run is what it handed MARS and what MARS
    # told it back: when the run was opened and given to MARS, the latest
    # event MARS reported, and whether MARS says it is running now
    # (`Execution.running`). Nothing finer is claimed.
    out["held_here"] = True
    o = observation
    c = lambda at: clock(at, now=now)                     # noqa: E731
    last = o.get("last_event")
    out.update(last_event=last)
    # -- the run returned; the record has not caught up -----------------------
    if o.get("ended_at") is not None:
        return said("runtime-ended",
                    f"the run returned · {c(o['ended_at'])}; its end is not "
                    "recorded yet", o["ended_at"], RUNTIME)
    if o.get("performing_since") is None:
        return said("not-launched",
                    "execution open; this process holds it and has not "
                    f"handed it to MARS yet · since {c(o.get('opened_at'))}",
                    o.get("opened_at"), RUNTIME)
    if not o.get("running"):
        return said("not-running",
                    "execution open; handed to MARS at "
                    f"{c(o['performing_since'])}, and MARS does not report it "
                    "running", o["performing_since"], RUNTIME)
    if last:
        return said("running",
                    f"running; latest event: {last['what']} · {c(last['at'])}",
                    last["at"], RUNTIME)
    return said("no-event",
                "running; no event reported since "
                f"{c(o['performing_since'])}", o["performing_since"], RUNTIME)


def _delegated(cv, expectation, *, now=None) -> dict | None:
    """Mentis-delegated work this run's request is still waiting on.

    Read from the operational record exactly as `claim_resumption` reads it
    (`waiting_on`), so what is shown here is what resumption waits for.
    """
    if not expectation:
        return None
    try:
        w = cv.waiting_on(expectation)
    except Exception:                                     # noqa: BLE001
        return None
    out = [c for c in w["required"] if c["expectation"] in w["outstanding"]]
    decisions = [d for d in w["decisions"] if d["expectation"] in w["outstanding"]]
    inputs = [i for i in w.get("inputs") or () if i["expectation"] in w["outstanding"]]
    if not out and not decisions and not inputs:
        return None
    # THE RECORD'S WORD, NOT A LIVENESS CLAIM. `_child_state` calls a child
    # "running" whenever a run of it has no recorded end, which is also what a
    # run whose process died looks like. That child's own run is listed on its
    # own line with what is actually observed of it; here it is only "open".
    said = {"running": "run open, no end recorded",
            "not-ended": "not started"}
    names = [f"{cv.alias(c['carrier']) if c['carrier'] else 'nobody'} "
             f"({said.get(c['state'], c['state'])})" for c in out]
    names += [f"a decision owed by "
              f"{cv.alias(d['owed_by']) if d['owed_by'] else 'nobody'}"
              for d in decisions]
    names += [f"input owed by "
              f"{cv.alias(i['owed_by']) if i['owed_by'] else 'nobody'}, "
              f"not yet marked ready"
              for i in inputs]
    return {"outstanding": w["outstanding"],
            "words": "waiting on Mentis-delegated work: " + ", ".join(names),
            "source": RECORDED}


def _row(cv, start, end, observation, *, now) -> dict:
    s = run_state(start, end, observation, now=now)
    d = start.get("detail") or {}
    alias = cv.alias(start["actor"]) if start.get("actor") else None
    s.update({
        "name": (alias or "?").lstrip("@"),
        "actor": start.get("actor"),
        "conversation": start.get("conversation"),
        "turn": start.get("turn"),
        "expectation": start.get("caused_by"),
        # WHAT WAS ASKED FOR THIS RUN, from its own start act. Never the
        # handle's `actual_model`, which is whatever the previous run on it
        # observed.
        "model_requested": d.get("requested_model") or d.get("selected_model"),
        "delegated": _delegated(cv, start.get("caused_by"), now=now),
    })
    return s


def working(cv, agents, *, recent=RECENT_ENDED, now=None) -> dict:
    """Every open run, and the few most recently ended, each in one sentence.

    `agents` is the service that can say which runs THIS process holds. If it
    cannot be asked, open runs are still listed -- the record knows them --
    and each says that what is happening in it could not be asked.
    """
    now = now or time.time()
    held, why_not = {}, None
    try:
        held = agents.agents_runs()
    except Exception as exc:                              # noqa: BLE001
        held, why_not = None, f"{type(exc).__name__}: {exc}"

    opened = cv.open_runs()
    rows = []
    for start in sorted(opened, key=lambda a: a["at"], reverse=True):
        row = _row(cv, start, None,
                   (held or {}).get(start["id"]), now=now)
        if held is None:
            row.update(state="unknown", source=UNKNOWN,
                       words="execution open; what this process holds could "
                             f"not be asked ({why_not})")
        rows.append(row)

    ended = []
    for end in (cv.history(act=RUN_ENDS, newest_first=True, limit=recent * 3)
                if recent else ()):
        start = cv._act(end.get("caused_by"))
        if start is None or start["act"] != RUN_START:
            continue          # failed before any run started: not a run
        ended.append(_row(cv, start, end, None, now=now))
        if len(ended) >= recent:
            break

    return {"open": rows, "ended": ended, "why_not": why_not,
            "observed_at": now}
