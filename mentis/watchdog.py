"""The watchdog: a periodic look at work that is supposed to be happening.

NOT AN AGENT AND NOT A LOOP OF AGENTS. A thread of the server that wakes every
`EVERY_S` (25 minutes), reads what it already holds, and acts only through
mechanisms that already exist. It dispatches nothing itself and asks no model
anything.

WHY IT EXISTS (measured 2026-10-27). A dispatched run had no deadline, and the
server recorded its reply only when its process exited. A Caretaker run wrote
its whole answer and ended its turn at 09:19, and its process never exited --
a background shell loop it left behind was waiting on a file nothing would
write -- so the answer was held back indefinitely and the request read as in
progress. The run's own waiter now ends a run that has settled
(`RunObservation.settle_due`); this is the backstop for runs that never get
that far, and for runs the record holds open that no process here holds.

WHAT EACH LOOK DOES
  progressing   a run this process holds that has shown activity within
                `STALL_S` -- a stream event, a helper's progress, anything
                written under its scratch or (Claude) its transcript folder --
                or whose main turn has a tool call open for less than
                `TOOL_STALL_S` (a long test suite is progress). Left alone.
  stalled       held here, none of that. Its waiter is asked to stop its
                process tree (`Foundation.halt_run`); the run then ends with
                terminal `stalled`, and recovery is the existing one
                (`dispatch.recovery_of`): moved to another runtime once, then
                put to the owner to retry or park.
  stuck         a stall it already asked to stop, still running a look
                later: the process could not be stopped from here (an
                elevated process, say). Said once in the record as
                `problem-noticed` -- the one thing a person has to do.
  not held      runs the record holds open that no process here holds are
                the wake check's (`wakecheck.reconcile` and `review`), run
                here as it runs at start: confirmed interruptions are
                recorded, and stopped work old enough is put to the owner.

A look never restarts work by itself beyond that, never deletes anything, and
never decides for the owner. Everything it did is returned and printed.
"""

from __future__ import annotations

import threading
import time
import traceback

from mentis import recovery

#: How often the watchdog looks. The owner's figure: every 20-30 minutes.
EVERY_S = 25 * 60

#: How long a held run may show no activity at all before it is stalled.
#: The same thirty minutes the wake check takes as "stopped" (`recovery`).
STALL_S = recovery.QUIET_S

#: How long a tool call of the main turn may run with nothing else happening
#: before it, too, counts as stalled: long test suites run silently.
TOOL_STALL_S = 2 * 3600

PROGRESSING, STALLED, STUCK = "progressing", "stalled", "stuck"


def _newest(snap: dict) -> float:
    seen = [snap.get("performing_since") or 0, snap.get("launched_at") or 0,
            snap.get("opened_at") or 0,
            (snap.get("last_event") or {}).get("at") or 0]
    for h in (snap.get("helpers") or {}).values():
        seen.append((h.get("latest") or {}).get("at") or h.get("since") or 0)
    return max(seen)


def assess(snap: dict, *, written_at: float | None = None,
           now: float | None = None) -> dict:
    """What one held run is doing, from its observation (`RunObservation.
    snapshot`) and the newest write found for it (`written_at`). Pure."""
    now = now if now is not None else time.time()
    last = max(_newest(snap), written_at or 0)
    quiet = now - last
    halt = snap.get("halt_requested")
    if halt:
        return {"state": STUCK if now - halt["at"] >= EVERY_S / 2 else
                STALLED, "quiet_s": int(quiet), "why": halt["why"]}
    main_tools = [t for t in (snap.get("tools") or {}).values()
                  if t.get("within") is None]
    if main_tools:
        oldest = min(t.get("since") or now for t in main_tools)
        running = now - oldest
        if running < TOOL_STALL_S:
            return {"state": PROGRESSING, "quiet_s": int(quiet),
                    "why": f"a tool call has been running for "
                           f"{int(running // 60)} min "
                           f"({main_tools[0].get('name')})"}
        return {"state": STALLED, "quiet_s": int(quiet),
                "why": f"a tool call ({main_tools[0].get('name')}) has been "
                       f"open for {int(running // 60)} min, beyond "
                       f"{TOOL_STALL_S // 60} min"}
    if quiet < STALL_S:
        return {"state": PROGRESSING, "quiet_s": int(quiet),
                "why": f"active {int(quiet // 60)} min ago"}
    return {"state": STALLED, "quiet_s": int(quiet),
            "why": f"no activity for {int(quiet // 60)} min: nothing from its "
                   f"runtime's stream and nothing written under its scratch"}


def look(st, *, now: float | None = None) -> dict:
    """One look at all work in progress. Returns what was found and done."""
    from mentis import wakecheck
    now = now if now is not None else time.time()
    cv, agents = st.cv, st.agents
    out = {"at": now, "held": [], "halted": [], "stuck": [],
           "reconciled": None, "asked": []}
    try:
        held = agents.agents_runs()
    except Exception as exc:                              # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
        held = {}
    executions = set()
    for run, snap in held.items():
        if snap.get("ended_at"):
            continue
        if snap.get("instance"):
            executions.add(snap["instance"])
        start = cv._act(run) if run else None
        written = None
        if start is not None:
            try:
                written, _ = wakecheck._last_activity(st.path, start)
            except Exception:                             # noqa: BLE001
                written = None
        found = {"run": run, **assess(snap, written_at=written, now=now)}
        out["held"].append(found)
        if found["state"] == STALLED and not snap.get("halt_requested"):
            if agents.agents_halt_run(run, by="watchdog", why=found["why"]):
                out["halted"].append(found)
        elif found["state"] == STUCK and start is not None:
            if not any(a["act"] == "problem-noticed"
                       and (a.get("detail") or {}).get("watchdog") == run
                       for a in cv.history(caused_by=run)):
                cv.record_act(
                    actor="mentis", act="problem-noticed",
                    conversation=start.get("conversation"),
                    turn=start.get("turn"), caused_by=run,
                    execution=start.get("execution"),
                    runtime=start.get("runtime"),
                    because=("the watchdog asked this run to stop because it "
                             f"had stalled ({found['why']}) and its process "
                             "is still running: it could not be stopped from "
                             "here, so a person has to stop it (pid "
                             f"{snap.get('pid')})"),
                    detail={"watchdog": run, "pid": snap.get("pid"),
                            "quiet_s": found["quiet_s"]})
                out["stuck"].append(found)
    # NOT HELD HERE: the wake check, as a server starting runs it.
    try:
        woke = wakecheck.reconcile(cv, st.path, held=executions, now=now)
        out["reconciled"] = woke["counts"]
        out["asked"] = wakecheck.review(cv, found=woke["runs"], now=now)
    except Exception as exc:                              # noqa: BLE001
        out["wake_error"] = f"{type(exc).__name__}: {exc}"
    return out


def report(found: dict) -> list[str]:
    lines = []
    for f in found["halted"]:
        lines.append(f"watchdog: stopped stalled run {f['run']}: {f['why']}")
    for f in found["stuck"]:
        lines.append(f"watchdog: run {f['run']} could not be stopped; "
                     "noted for a person")
    if found.get("reconciled") and (found["reconciled"].get("interrupted")
                                    or found["asked"]):
        lines.append(f"watchdog: wake check {found['reconciled']}, "
                     f"{len(found['asked'])} put to the owner")
    for k in ("error", "wake_error"):
        if found.get(k):
            lines.append(f"watchdog: {k}: {found[k]}")
    return lines


def start(st, *, every_s: float = EVERY_S) -> threading.Event:
    """Look every `every_s` until the returned event is set."""
    stop = threading.Event()

    def run():
        while not stop.wait(every_s):
            try:
                for line in report(look(st)):
                    print(line, flush=True)
            except Exception:                             # noqa: BLE001
                traceback.print_exc()

    threading.Thread(target=run, daemon=True, name="mentis-watchdog").start()
    return stop
