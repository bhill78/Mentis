"""A server that is about to be restarted starts no new run (owner decision,
2026-11-19: "the smallest server-side mechanism preventing new agent runs from
starting after a deployment drain begins").

WHY IT IS IN THE SERVER. A dispatch records `execution-started` before this
process takes hold of the run, and dispatches also begin inside the server
(delegations, continuations, resumptions). So a tool that counts runs from
outside and then stops the server can always be passed by a run that began in
between, and the restart ends it. Only the process that starts runs can say
"none is starting, and none will".

WHAT IT IS. One flag and one count per server state, under ONE lock:

  draining   None, or {since, by, reason, phase, expires_at, lasts_s, extended,
             refused, refused_starts} (and, held here only, its id and its
             deadline on the monotonic clock)
  admitted   how many dispatches have passed the check (`admit`) and have not
             finished (`leave`): from before anything of the run is written
             until `dispatch` has written its end and done what follows an end

`admit` reads the flag and raises the count in one step, and `request` sets
the flag and reads the count in one step. So an answer "draining, held = N"
is one moment of this process: a dispatch either was counted in N, or met the
flag and was refused. There is no third case.

WHAT IT IS NOT. Nothing here stops, pauses, queues or retries anything. Runs
already admitted finish as they would have. A dispatch refused while draining
is recorded as every failure before a start is (`dispatch._refuse_draining`)
and its work stays open. NOTHING RESTARTS IT: continuing it is somebody's act,
exactly as after any other failure before a start. Delegation recovery at
server start is unchanged and does not read it (a child that failed is not
one that never started).

THE BOUND (AGENTS.md "Background work"). The flag ends by itself BOUND_S
after the last call that set or extended it, and with the process. There is
NO timer and no thread: expiry is evaluated when the flag is next read
(`_current`), by a dispatch's check or by a read. A deployment that died or
was cancelled therefore cannot leave a server refusing work for longer than
BOUND_S, and a restarted server is never draining.

DURATIONS ARE MEASURED ON THE MONOTONIC CLOCK (`time.monotonic`), which no
clock correction moves: a wall clock set forward cannot end a drain early, and
one set back cannot keep a server refusing work past its bound. Wall-clock
times (`since`, `at`, `expires_at`) are what is reported and logged, as
information; `lasts_s` is the duration that is enforced, and what a caller
that depends on it must read.

STOPPING. Stopping a server takes longer than BOUND_S can be relied on to
cover, and nothing can extend a drain once the stop has begun. So the one who
is about to stop it asks, once, for the `stopping` phase: granted ONLY IF
NOTHING IS HELD, decided under the same lock as the check, and then lasting as
long as that call asks, at most STOPPING_BOUND_S. With anything held it is
refused and the drain stays exactly as it was. It is still a bound: a stop
that never comes frees the server after it. An ordinary call during the phase
never shortens it and never leaves it.

EVERY DRAIN HAS AN IDENTITY, and a call about a drain names the one it means.
The id is made when the drain is set, stays through its extensions and into
its stopping phase, and is given only in the answer to the call that set it
or that named it (never in a read). A call naming another drain, or none
where one stands, changes nothing and says so. So a request that arrives
late -- a clear from a deployment that gave up, an extension from one that
timed out -- cannot touch a drain that came after it. What ends a drain:

  ordinary phase   a clear naming it; a clear with `force` (the owner ending
                   a drain that is not theirs: logged as forced); its bound;
                   the process
  stopping phase   a clear naming it; its bound; the process. NEVER a forced
                   clear: by then whoever holds the id is stopping the server

AUDIT. Every set, extension, clear (and whether forced), refused call and
expiry is one line on this process's stdout, which the launcher appends to
`python.log` in the run directory (the server's existing log, like every
other start-up and maintenance line of `web.serve`). It is deliberately not a
Brain act: that would be a new operational act kind for a fact about a
process, not about work. What the drain does to work IS in the Brain: each
refused start is a `delivery-failed` on its request saying who was draining,
since when and why.
"""

from __future__ import annotations

import json
import secrets
import threading
import time

#: THE BOUND: how long one owner-authorized call keeps the server draining,
#: at most. A later call may extend it, by at most this again.
BOUND_S = 120.0
#: THE STOPPING BOUND: the most one call may keep a server that holds nothing
#: draining while it is being stopped. The caller asks for what its stop can
#: take (`tools/env/mentis_env.py`, STOP_DRAIN_S) and is given no more than this.
STOPPING_BOUND_S = 600.0
#: The two phases of a drain.
DRAINING, STOPPING = "draining", "stopping"
#: How many refused starts one drain lists by name (it counts all of them).
REFUSED_LISTED = 50
#: The `detail.stage` of the `delivery-failed` a refused start is recorded as.
STAGE = "server-draining"

#: Guards every server state's flag and count, their creation included.
_LOCK = threading.Lock()
#: What of a drain is this process's own and is never part of an answer's flag.
_PRIVATE = ("id", "deadline")


def _slot(st) -> dict:
    """This server state's flag and count. Call with `_LOCK` held."""
    slot = getattr(st, "drain", None)
    if slot is None:
        slot = st.drain = {"draining": None, "admitted": 0}
    return slot


def _log(event: str, **said) -> None:
    try:
        print("drain: " + json.dumps({"event": event, "at": time.time(), **said},
                                     default=str), flush=True)
    except Exception:                                     # noqa: BLE001
        pass                      # a log that cannot be written changes nothing


def _clocks(now, mono) -> tuple[float, float]:
    """(wall time, to report; monotonic time, to measure with). Both can be
    given, so a test owns the clock; nothing but `mono` decides an expiry."""
    return (time.time() if now is None else now,
            time.monotonic() if mono is None else mono)


def _current(slot: dict, mono: float) -> dict | None:
    """The flag as it stands at `mono`: one past its bound is cleared here,
    which is the whole of the expiry. Call with `_LOCK` held."""
    d = slot["draining"]
    if d is not None and mono >= d["deadline"]:
        slot["draining"] = None
        _log("expired", drain=d["id"], since=d["since"], by=d["by"],
             reason=d["reason"], phase=d["phase"], expires_at=d["expires_at"],
             refused=d["refused"], held=slot["admitted"])
        return None
    return d


def _public(d: dict | None, mono: float) -> dict | None:
    """The flag as an answer or a read gives it: without its id, and with
    `lasts_s`, how much longer it lasts on the clock that decides it."""
    if d is None:
        return None
    return {**{k: v for k, v in d.items() if k not in _PRIVATE},
            "lasts_s": max(0.0, d["deadline"] - mono),
            "refused_starts": list(d["refused_starts"])}


def admit(st, *, now: float | None = None, mono: float | None = None) -> dict | None:
    """THE CHECK, for one dispatch, before it writes anything. None: admitted,
    and counted as held until `leave`. Otherwise the drain it met: it must
    start nothing."""
    now, mono = _clocks(now, mono)
    with _LOCK:
        slot = _slot(st)
        d = _current(slot, mono)
        if d is None:
            slot["admitted"] += 1
            return None
        d["refused"] += 1
        return {**_public(d, mono), "_drain": d["id"]}


def leave(st) -> None:
    """An admitted dispatch has finished, whatever it did."""
    with _LOCK:
        slot = _slot(st)
        slot["admitted"] = max(0, slot["admitted"] - 1)


def note_refused(st, met: dict, **what) -> None:
    """Name a start this drain refused (the act that records it, its request),
    so whoever is deploying can see what to address again."""
    with _LOCK:
        d = _slot(st)["draining"]
        if d is not None and d["id"] == met.get("_drain") \
                and len(d["refused_starts"]) < REFUSED_LISTED:
            d["refused_starts"].append(what)


def read(st, *, now: float | None = None, mono: float | None = None) -> dict:
    """{"draining": None or the flag, "held": admitted dispatches}, one moment."""
    now, mono = _clocks(now, mono)
    with _LOCK:
        slot = _slot(st)
        return {"draining": _public(_current(slot, mono), mono),
                "held": slot["admitted"]}


def request(st, *, on: bool, by: str, reason: str = "",
            seconds: float | None = None, stopping: bool = False,
            drain: str | None = None, force: bool = False,
            now: float | None = None, mono: float | None = None) -> dict:
    """Set, extend or clear the flag, and answer with the flag and the count
    of held dispatches as they stood in that same moment.

    WHO MAY CALL IT is the caller's to have checked: the owner route does
    (`web._routes`, behind the owner's authentication like every owner write).
    `seconds` shortens the bound for this call; it never lengthens it.

    `drain` names the drain the call means (module docstring). With `on`: no
    drain standing and none named sets one, and the answer's `drain` is its
    id; the standing drain named extends it. With `on` false: the standing
    drain named is cleared; `force` clears an ordinary one without its id.
    ANY OTHER CALL CHANGES NOTHING: the answer is `ok: False` with `refused`
    saying why, and the flag and count as they stand.

    `stopping` asks for the stopping phase: granted only if nothing is held,
    in which case the drain lasts `seconds`, at most STOPPING_BOUND_S, from
    now. With anything held it is refused like any other refused call.
    """
    now, mono = _clocks(now, mono)
    most = STOPPING_BOUND_S if stopping else BOUND_S
    bound = most if seconds is None else max(0.0, min(float(seconds), most))
    with _LOCK:
        slot = _slot(st)
        d = _current(slot, mono)
        was, refused, cleared, mine = None, None, False, None
        named = d is not None and drain is not None and drain == d["id"]
        if on and d is None and drain is not None:
            refused = "the drain this call names is not standing (cleared, or past its bound)"
        elif on and d is not None and not named:
            refused = ("another drain is standing" if drain is not None else
                       "a drain is already standing, and this call does not name it")
        elif on and stopping and slot["admitted"]:
            refused = (f"{slot['admitted']} dispatch(es) are held: a server is "
                       f"marked as stopping only when it holds nothing")
        elif on and d is None:
            d = slot["draining"] = {
                "id": secrets.token_hex(8), "since": now, "by": by, "reason": reason,
                "phase": STOPPING if stopping else DRAINING,
                "expires_at": now + bound, "deadline": mono + bound,
                "extended": 0, "refused": 0, "refused_starts": []}
            mine = d["id"]
            _log("set", drain=d["id"], by=by, reason=reason, phase=d["phase"],
                 lasts_s=bound, expires_at=d["expires_at"], held=slot["admitted"])
        elif on:
            if stopping:
                d["phase"] = STOPPING
            # an ordinary call never shortens a stopping drain
            if stopping or d["phase"] != STOPPING or mono + bound > d["deadline"]:
                d["deadline"], d["expires_at"] = mono + bound, now + bound
            d["extended"] += 1
            mine = d["id"]
            _log("extended", drain=d["id"], by=by, since=d["since"], phase=d["phase"],
                 lasts_s=d["deadline"] - mono, expires_at=d["expires_at"],
                 held=slot["admitted"])
        elif d is None:
            refused = "no drain is standing"
        elif named or (force and d["phase"] != STOPPING):
            was, cleared = _public(d, mono), True
            slot["draining"] = None
            _log("cleared", drain=d["id"], by=by, reason=reason, since=d["since"],
                 phase=d["phase"], forced=not named, refused=d["refused"],
                 held=slot["admitted"])
        elif d["phase"] == STOPPING:
            refused = ("the server is being stopped: its drain is cleared only by "
                       "whoever is stopping it, its bound, or the process ending")
        else:
            refused = ("this call does not name the drain that is standing; the "
                       "owner can end it with `force`")
        if refused:
            _log("refused", by=by, on=on, stopping=stopping, force=force,
                 why=refused, standing=d["id"] if d else None, held=slot["admitted"])
        answer = {"ok": refused is None,
                  "draining": _public(slot["draining"], mono),
                  "held": slot["admitted"], "at": now, "bound_s": BOUND_S,
                  "stopping_bound_s": STOPPING_BOUND_S}
        if mine:
            answer["drain"] = mine
        if refused:
            answer["refused"] = refused
        if not on:
            answer["cleared"] = cleared
            answer["was"] = was
        return answer
