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
is doing is unknown. The one case that IS known is closed in the record
rather than guessed at here: a run left open by a server that is gone is
ended `interrupted` when the next server starts (`interrupted_by_restart`),
so "unknown" is left for what really is. Every sentence carries the time of the observation that
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
            # ENDED, NOT COMPLETED (WS-C): the run returned; whether the work
            # is done is the claim's and reconciliation's to say.
            return said("ended", f"ended · {clock(end['at'], now=now)}",
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
        # A SESSION SOMEBODY STOPPED did not fail: its turn ended `cancelled`
        # (`MentisService._outcome_of`), and the work it was doing stays open.
        if "terminal 'cancelled'" in (end.get("because") or ""):
            return said("stopped",
                        "stopped: the session was cancelled; the work it was "
                        f"doing stays open · {clock(end['at'], now=now)}",
                        end["at"], RECORDED, ended_by=end["id"])
        # CUT OFF WITH ITS SERVER did not fail either (`Conversations.
        # interrupt_run`): the process that ran it is gone, the execution is
        # over, and the work it was doing stays open for somebody to continue.
        if (end.get("detail") or {}).get("terminal") == "interrupted":
            return said("interrupted",
                        "interrupted: the server it ran under stopped; the "
                        "run is over and the work it was doing stays open "
                        f"· {clock(end['at'], now=now)}",
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
    # WHAT IT IS DOING NOW, in its own tool's words (`run_feed.activity`),
    # whether it has been asked to stop, and a permission it waits on.
    perm = o.get("permission")
    permission_keys = ("form", "decision", "title", "summary", "kind",
                       "asked_at", "post", "conversation")
    permissions = [{k: p.get(k) for k in permission_keys}
                   for p in (o.get("permissions") or ())]
    out.update(last_event=last, activity=o.get("activity"),
               activity_at=o.get("activity_at"),
               stopping=bool(o.get("stop")) and not o.get("ended_at"),
               permission=({k: perm.get(k) for k in permission_keys}
                           if perm else None),
               permissions=permissions)
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


#: `delegated_from` answers, kept briefly: `/api/activity` is polled every few
#: seconds by every open page, and whose delegation a request is changes only
#: when somebody delegates or picks it up. Keyed by the record and the request;
#: a found link is kept longer than "none" (which a later delegation changes).
_DELEGATED_FROM: dict = {}
_DELEGATED_KEPT_S = (60.0, 15.0)
_DELEGATED_MAX = 512


def delegated_from(cv, expectation) -> dict | None:
    """`_delegated_from_record`, read at most once per request every few
    seconds (`_DELEGATED_KEPT_S`)."""
    if not expectation:
        return None
    key = (id(cv), expectation)
    now = time.time()
    held = _DELEGATED_FROM.get(key)
    if held is not None and now < held[0]:
        return dict(held[1]) if held[1] else None
    got = _delegated_from_record(cv, expectation)
    if len(_DELEGATED_FROM) >= _DELEGATED_MAX:
        _DELEGATED_FROM.clear()
    _DELEGATED_FROM[key] = (now + _DELEGATED_KEPT_S[0 if got else 1], got)
    return dict(got) if got else None


def _delegated_from_record(cv, expectation) -> dict | None:
    """WHOSE MENTIS DELEGATION THIS RUN'S REQUEST IS, read from the record: the
    newest `work-delegated` act that handed the request on (`work._delegation_of`,
    the reading Work itself uses), as who delegated it and under which request.

    This is the Mentis-managed relation: an independent execution with its own
    runtime, authority and consent, linked to the work it came from. It is not
    the runtime-native relation (`workers`), which lives inside one run. None
    when the request was not delegated, or the record could not be read."""
    if not expectation:
        return None
    try:
        from mentis.operational.work import _delegation_of
        exp = cv._act(expectation) or {}
        d = _delegation_of(cv, expectation, exp, cv.history(caused_by=expectation))
    except Exception:                                     # noqa: BLE001
        return None
    if d is None:
        return None
    by = d.get("actor")
    return {"by": by, "by_name": (cv.alias(by) or "").lstrip("@") if by else None,
            "expectation": d.get("caused_by"), "at": d.get("at"),
            "source": RECORDED}


def asked_with(cv, start) -> dict:
    """WHO THE RUN WORE AND HOW FAR IT MAY GO, read from the record.

    The Persona is the one the run's own grant carried (`authority.persona`
    on its start act) -- what it actually wore -- else the latest assignment
    of its request that named one, which is where dispatch itself finds it on
    a retry or a resume. Task Gravity is the permission IN FORCE: the original
    request's `detail.follow_up` (absent is "ask"), with how many generations
    of discovery this run's request is below it -- the same walk dispatch
    checks pursuit with (`discovery`, `follow_up_of`), so the run's line and
    what the run was permitted cannot disagree. A read; nothing is stored."""
    from mentis.operational import discovery, follow_up_of
    exp = start.get("caused_by")
    persona = ((start.get("detail") or {}).get("persona")
               or ((start.get("detail") or {}).get("authority") or {}).get("persona"))
    if not persona and exp:
        persona = next((a["detail"]["persona"] for a in sorted(
            cv.history(caused_by=exp), key=lambda a: a["at"], reverse=True)
            if a["act"] == "expectation-assigned"
            and (a.get("detail") or {}).get("persona")), None)
    name = None
    if persona:
        try:
            got = cv._c.read([persona])
            name = (got[0].get("body") or {}).get("name") if got else None
        except Exception:                                 # noqa: BLE001
            name = None
    where = discovery(cv, exp) if exp else {"origin": None, "generation": 0}
    # WHICH OPERATIONS PROCEED WITHOUT ASKING, separately from Task Gravity
    # (`operational.consent`): the same read the permission policy answers by.
    from mentis.operational.consent import of_run
    try:
        consent = of_run(cv, start["id"]) if start.get("id") else None
    except Exception:                                     # noqa: BLE001
        consent = None
    # WHERE THAT PERSONA CAME FROM, as the request recorded it when it was
    # addressed (`posting.addressed_persona`): only when the run wears the
    # Persona the request recorded, so a later change is not misattributed.
    req = (cv._act(exp) or {}) if exp else {}
    rd = req.get("detail") or {}
    persona_from = rd.get("persona_from") if persona and rd.get("persona") == persona else None
    return {"persona": persona, "persona_name": name, "persona_from": persona_from,
            "follow_up": follow_up_of(cv, where["origin"]),
            "generation": where["generation"],
            "consent": consent}


def _row(cv, start, end, observation, *, now) -> dict:
    s = run_state(start, end, observation, now=now)
    d = start.get("detail") or {}
    alias = cv.alias(start["actor"]) if start.get("actor") else None
    s.update(asked_with(cv, start))
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
        "runtime": start.get("runtime"),
        "delegated": _delegated(cv, start.get("caused_by"), now=now),
        # THE TWO RELATIONS, KEPT APART. `delegated_from`: this run is an
        # independent execution Mentis dispatched for somebody's delegation.
        # `workers`: the runtime-native workers INSIDE this run (a Claude
        # sub-agent), as the run's own feed holds them -- tool calls of this
        # run, under its identity and consent, and only while held here.
        "delegated_from": delegated_from(cv, start.get("caused_by")),
        "workers": list((observation or {}).get("workers") or ()),
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
    # THE OPEN RUN A DELEGATION CAME FROM, where one is open: the run whose
    # request is the one the delegation was made under. Named so a reader can
    # show the delegated run beside its origin; absent when that run has ended.
    by_request = {r.get("expectation"): r.get("run") for r in rows if r.get("expectation")}
    for row in rows:
        origin = row.get("delegated_from")
        if origin and by_request.get(origin.get("expectation")):
            origin["run"] = by_request[origin["expectation"]]

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


#: What a run's end act keeps of what it did and used (`dispatch.usage_facts`
#: and the calls beside them), as `recorded_end` hands them on.
_RECORDED = ("tool_calls", "tokens", "tokens_cover", "tokens_by_model", "cost",
             "context_used", "context_size", "native_workers")


def recorded_end(cv, run: str) -> dict | None:
    """WHAT A RUN'S END ACT RECORDED OF WHAT IT DID AND USED, for a reader of a
    run no process holds any more: its tool calls -- each with its place in the
    run where the runtime reported one (`parent`, `worker`) -- and its usage,
    each figure named for what it is. Read from the record; None when the run
    has no recorded end, or its end kept none of it."""
    try:
        end = next((a for a in sorted(cv.history(caused_by=run), key=lambda a: a["at"],
                                      reverse=True) if a["act"] in RUN_ENDS), None)
    except Exception:                                     # noqa: BLE001
        return None
    if end is None:
        return None
    d = end.get("detail") or {}
    out = {k: d[k] for k in _RECORDED if d.get(k)}
    if not out:
        return None
    # `terminal` is how the run ended in the record's own word ("cancelled"
    # for a stopped one), which is what a reader says of calls left open.
    return {**out, "ended_at": end.get("at"), "stop_reason": d.get("terminal")}


def is_live(row: dict) -> bool:
    """Whether a run row (`working`'s) is ACTIVE RIGHT NOW: open by the
    record and held by this process, which has not seen it return. An open
    run nothing here holds is listed by `working` as open with its state
    unknown; it is not counted as somebody working, any more than a
    machine-local execution of another process would be."""
    return bool(row.get("held_here")) and row.get("state") != "runtime-ended"


def live_by_conversation(cv, agents) -> dict:
    """Conversation -> the runs active in it right now, ONE ENTRY PER RUN.

    The cheap reading of `is_live` for a list of Conversations: the record's
    open runs (`Conversations.open_runs`, the one rule for when a run is
    over) and what this process holds of each (`agents_runs`), nothing worded
    or followed. Keyed by the run's own start act, so two runs of one
    Participant -- in one Conversation or two -- are two entries, and a run
    is counted where ITS start act says it runs, never wherever its
    Participant happens to be a member.

    Read from the RECORD rather than from machine-local executions because
    the start act is what moves the change cursor: a reader that rereads on
    it finds the run, where the execution handle is only begun later, once
    the material for the run is composed. Raises if `agents` cannot be asked;
    the caller says what it does then."""
    held = agents.agents_runs() or {}
    out: dict = {}
    for start in cv.open_runs():
        o = held.get(start["id"])
        if o is None or o.get("ended_at") is not None:
            continue
        actor = start.get("actor")
        out.setdefault(start.get("conversation"), []).append({
            "run": start["id"], "participant": actor,
            "alias": (cv.alias(actor) or "?").lstrip("@") if actor else None,
            "turn": start.get("turn"), "since": start.get("at")})
    return out


def interrupted_by_restart(cv, *, held=(), server=None) -> list[dict]:
    """AT A SERVER'S START: end, as interrupted, every run the record holds
    open. Returns what it ended, each as {run, act, request}.

    DEFINITE, NOT A GUESS -- the same ground `permissions.retire_unconsumable`
    stands on. A run is performed by MARS over the stdio of the server that
    dispatched it, and its end is written by a waiter thread of that server.
    This runs while this server holds the Brain's one serving lock and before
    it starts any run, so every run open in the record was started by a
    server that is gone: its MARS connection went with it, and nothing is
    left that could ever write its end. Whatever its runtime was doing, the
    execution Mentis started is over.

    THE EXECUTION IS OVER; THE WORK MAY REMAIN OPEN. Only the run is ended
    (`Conversations.interrupt_run`): no result, no claim, no change to the
    request it carried, and nothing is restarted -- continuing interrupted
    work is somebody's act (`interruption_hold`).

    `held` is the run ids this process holds, which are never touched; at a
    server's start there are none. `server` is what is known of this process
    (pid, start time), kept as the evidence.

    WHO MAY CALL IT: only the server holding that lock, once, before it
    serves a request or starts a run (`web.serve`)."""
    held = set(held or ())
    out = []
    for start in sorted(cv.open_runs(), key=lambda a: a["at"]):
        if start["id"] in held:
            continue
        act = cv.interrupt_run(
            start["id"],
            why="the server that started this run stopped while it was "
                "running, and a server starting found it still open",
            evidence={"found_by": "server-start", "server": dict(server or {}),
                      "run_started_at": start.get("at"),
                      "why": "every open run at a server's start was started "
                             "by a server that is gone; its end could never "
                             "be recorded"})
        if act:
            out.append({"run": start["id"], "act": act,
                        "request": start.get("caused_by")})
    return out
