"""What THIS process observes of one run, while it runs. Never durable.

A RUN IS NOT AN INSTANCE. An instance is a reusable session handle and carries
many runs; what it says about liveness, exit code and finish time is true of
whichever run last touched it, and nothing on it says which one that was. So
what this process knows about the run it is performing is kept HERE, keyed by
the run -- the `execution-started` act that began it -- and not on the handle.

It is ephemeral on purpose. A restart forgets it, and that is the honest
answer: a durable run with no observation here is "open, and no process here
holds it", which is exactly what a reader is then told. Nothing in this module
is written to the record, and nothing in it is a second status store: the
record decides whether a run is open; this only says what a process holding
one has seen.

WHAT THE STREAM FILLS IN, AND ONLY THAT. Each runtime adapter reads its own
structured output line by line as it arrives (`RuntimeAdapter.observe_event`)
and reports here only what that line establishes: a session named, a tool
started or finished, a helper started or finished, control handed back to the
model, the runtime's own terminal event. Silence is recorded as nothing --
there is deliberately no method for "thinking", only for a runtime that
explicitly reported thinking tokens. `observes` says which of these a
runtime's stream can establish at all, so a runtime that cannot report helpers
is not read as having none.
"""

from __future__ import annotations

import threading
import time

#: How much of a tool's arguments is kept to show what it is doing.
WHAT_CHARS = 120

#: How long a run may stay quiet after its runtime ENDED ITS TURN successfully
#: before the run is taken as finished and its process tree is stopped
#: (`RunObservation.settle_due`). Measured 2026-10-27: a Caretaker run wrote
#: its whole answer, ended its turn, and its process never exited because a
#: background shell loop it had started (`until [ -s file ]; do sleep 5;
#: done`) was waiting on a file nothing would write. The reply exists only
#: once the process exits, so the answer was held back indefinitely.
SETTLE_S = 120

#: The same, while a helper the runtime reported starting has not reported
#: finishing: the helper may still wake the model with something to add, so
#: it is given longer -- counted from the last thing the stream said.
HELPER_SETTLE_S = 20 * 60


def _brief(text) -> str | None:
    if text is None:
        return None
    text = " ".join(str(text).split())
    return text if len(text) <= WHAT_CHARS else text[:WHAT_CHARS - 1] + "…"


class RunObservation:
    """One run, as the process performing it has seen it.

    Every mutation is made under one lock and every reader gets a copy
    (`snapshot`), so a status request never sees half an update and a runtime
    stream never waits on a reader.
    """

    def __init__(self, run: str | None, instance: str, runtime: str | None,
                 *, opened_at: float | None = None):
        self._lock = threading.Lock()
        self.run = run
        self.instance = instance
        self.runtime = runtime
        #: when this process took the run on -- the handle is held from here
        self.opened_at = opened_at or time.time()
        #: when the runtime was asked to perform it
        self.performing_since: float | None = None
        #: when the call that performed it returned, and with what
        self.ended_at: float | None = None
        self.exit_code: int | None = None
        # -- from the process -------------------------------------------------
        self.pid: int | None = None
        self.launched_at: float | None = None
        self.exited_at: float | None = None
        self.process_exit: int | None = None
        # -- from the runtime's own stream ------------------------------------
        #: what this runtime's stream can establish at all (see module doc)
        self.observes: tuple[str, ...] = ()
        self.session_ref: str | None = None
        self.model: str | None = None
        self.events = 0
        self.unparsed = 0
        self.last_event: dict | None = None
        #: open tool calls, by the runtime's own key for each call, until the
        #: runtime reports that call's completion -- nothing else closes one
        self.tools: dict[str, dict] = {}
        #: runtime-internal helpers the stream reported starting and has not
        #: reported finishing (Claude Code's background tasks, for instance)
        self.helpers: dict[str, dict] = {}
        #: when the runtime handed control back to the model with nothing
        #: since to say the model has finished answering
        self.awaiting_model_since: float | None = None
        #: the last time the runtime EXPLICITLY reported thinking; never set
        #: from silence
        self.thinking_at: float | None = None
        #: the runtime's own terminal event, if it has emitted one
        self.terminal: dict | None = None
        #: the last turn-ending terminal event, kept until the MODEL speaks
        #: again (`turn_resumed`). `terminal` is cleared by any later event,
        #: helper progress included; this is cleared only by a new turn.
        self.turn_end: dict | None = None
        #: why this process stopped the run's process tree, when it did:
        #: {"by": "settled"|"watchdog", "why": ..., "at": ...}
        self.stopped_by: dict | None = None
        #: a stop somebody asked for (`halt`), honoured by the run's waiter
        self.halt_requested: dict | None = None

    # -- lifecycle ----------------------------------------------------------

    def performing(self, at: float | None = None) -> None:
        with self._lock:
            self.performing_since = at or time.time()

    def ended(self, exit_code: int | None, at: float | None = None) -> None:
        with self._lock:
            if self.ended_at is None:
                self.ended_at = at or time.time()
                self.exit_code = exit_code

    @property
    def is_ended(self) -> bool:
        return self.ended_at is not None

    # -- the process --------------------------------------------------------

    def launched(self, pid: int | None) -> None:
        with self._lock:
            self.pid, self.launched_at = pid, time.time()

    def exited(self, code: int | None) -> None:
        with self._lock:
            self.exited_at, self.process_exit = time.time(), code

    # -- the runtime's stream -----------------------------------------------
    #
    # Called from the stream reader, one event at a time. `saw` is called for
    # every event the adapter understood; the rest say what it established.

    def declare(self, observes) -> None:
        with self._lock:
            self.observes = tuple(observes)

    def saw(self, what: str, at: float | None = None) -> None:
        with self._lock:
            now = at or time.time()
            self.events += 1
            self.last_event = {"at": now, "what": _brief(what)}
            # A runtime that keeps talking after its terminal event had not
            # finished: measured, Claude Code emits a `result` for a turn and
            # then carries on when a background helper reports back.
            self.terminal = None

    def not_understood(self) -> None:
        with self._lock:
            self.unparsed += 1

    def session(self, ref: str | None) -> None:
        if ref:
            with self._lock:
                self.session_ref = str(ref)

    def model_reported(self, model: str | None) -> None:
        if model:
            with self._lock:
                self.model = str(model)

    def tool_started(self, key, name: str | None, what=None, *,
                     within: str | None = None) -> None:
        with self._lock:
            self.tools[str(key)] = {"name": name, "what": _brief(what),
                                    "since": time.time(),
                                    "within": within}
            if within is None:
                # the model asked for a tool: its response has arrived
                self.awaiting_model_since = None

    def tool_ended(self, key) -> dict | None:
        with self._lock:
            return self.tools.pop(str(key), None)

    def helper_started(self, key, kind: str | None, what=None, *,
                       via: str | None = None) -> None:
        with self._lock:
            self.helpers[str(key)] = {"kind": kind, "what": _brief(what),
                                      "since": time.time(), "via": via,
                                      "latest": None}

    def helper_event(self, key, what) -> None:
        with self._lock:
            h = self.helpers.get(str(key))
            if h is not None:
                h["latest"] = {"at": time.time(), "what": _brief(what)}

    def helper_ended(self, key) -> None:
        with self._lock:
            self.helpers.pop(str(key), None)

    def awaiting_model(self) -> None:
        with self._lock:
            if self.awaiting_model_since is None:
                self.awaiting_model_since = time.time()

    def model_answered(self) -> None:
        with self._lock:
            self.awaiting_model_since = None
            self.thinking_at = None

    def thinking_reported(self) -> None:
        with self._lock:
            self.thinking_at = time.time()

    def runtime_terminal(self, ok: bool, what=None) -> None:
        with self._lock:
            self.terminal = {"at": time.time(), "ok": bool(ok),
                             "what": _brief(what)}
            self.turn_end = dict(self.terminal)
            self.awaiting_model_since = None

    def turn_resumed(self) -> None:
        """The model is speaking again after a turn ended: that turn's end
        was not the run's."""
        with self._lock:
            self.turn_end = None

    # -- when the run is over although its process is not ------------------

    def settle_due(self, now: float | None = None, *, quiet_s=None,
                   helper_quiet_s=None) -> str | None:
        """Why this run counts as FINISHED now, or None.

        Its runtime ended a turn successfully, the model has not spoken since,
        no tool call of the main turn is open, and the stream has been quiet
        for `SETTLE_S` -- or `HELPER_SETTLE_S` while a helper is still open.
        A turn's end alone is not enough (a background helper finishing can
        wake the model, measured on Claude Code); a turn's end that nothing
        has followed for this long is.
        """
        now = now if now is not None else time.time()
        quiet_s = SETTLE_S if quiet_s is None else quiet_s
        helper_quiet_s = (HELPER_SETTLE_S if helper_quiet_s is None
                          else helper_quiet_s)
        with self._lock:
            end = self.turn_end
            if not end or not end.get("ok"):
                return None
            if any(t.get("within") is None for t in self.tools.values()):
                return None
            last = max(end["at"], (self.last_event or {}).get("at") or 0)
            for h in self.helpers.values():
                last = max(last, (h.get("latest") or {}).get("at")
                           or h.get("since") or 0)
            bound = helper_quiet_s if self.helpers else quiet_s
            quiet = now - last
            if quiet < bound:
                return None
            return (f"the runtime ended its turn ({end.get('what')}) and "
                    f"nothing followed for {int(quiet)}s"
                    + (f" while {len(self.helpers)} helper(s) it started "
                       "stayed open" if self.helpers else "")
                    + "; its process had not exited, so Mentis stopped it")

    def halt(self, by: str, why: str) -> None:
        """Ask the run's waiter to stop its process tree (the watchdog)."""
        with self._lock:
            if self.halt_requested is None:
                self.halt_requested = {"by": by, "why": why,
                                       "at": time.time()}

    def halt_due(self) -> dict | None:
        with self._lock:
            return dict(self.halt_requested) if self.halt_requested else None

    def stopped(self, by: str, why: str) -> None:
        with self._lock:
            self.stopped_by = {"by": by, "why": why, "at": time.time()}

    # -- reading ------------------------------------------------------------

    def mark(self) -> tuple:
        """Changes whenever anything observed here does. For comparison only."""
        with self._lock:
            return (self.performing_since, self.ended_at, self.exited_at,
                    self.events, len(self.tools), len(self.helpers))

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "run": self.run,
                "instance": self.instance,
                "runtime": self.runtime,
                "opened_at": self.opened_at,
                "performing_since": self.performing_since,
                "ended_at": self.ended_at,
                "exit_code": self.exit_code,
                "pid": self.pid,
                "launched_at": self.launched_at,
                "exited_at": self.exited_at,
                "process_exit": self.process_exit,
                "observes": list(self.observes),
                "session_ref": self.session_ref,
                "model": self.model,
                "events": self.events,
                "unparsed": self.unparsed,
                "last_event": dict(self.last_event) if self.last_event else None,
                "tools": {k: dict(v) for k, v in self.tools.items()},
                "helpers": {k: {**v, "latest": dict(v["latest"])
                                if v["latest"] else None}
                            for k, v in self.helpers.items()},
                "awaiting_model_since": self.awaiting_model_since,
                "thinking_at": self.thinking_at,
                "terminal": dict(self.terminal) if self.terminal else None,
                "turn_end": dict(self.turn_end) if self.turn_end else None,
                "stopped_by": (dict(self.stopped_by) if self.stopped_by
                               else None),
                "halt_requested": (dict(self.halt_requested)
                                   if self.halt_requested else None),
            }
