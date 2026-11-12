"""The execution boundary: how Mentis has work done by an agent, through MARS.

Mentis owns the work: what is asked, by whom, under what authority, how it is
recorded, and whether anything remains afterwards. MARS (Mentis Agent Runtime
Service, a separate project) owns running an agent: the ACP/CLI session, its events,
completion, cancellation and process cleanup. Mentis reaches MARS only through MARS's
public ACP interface (`mars stdio`), never by importing it.

This module is the whole contract between the two halves of Mentis that care:
`mentis.core.service` / `mentis.web.dispatch` (coordination, kept from Mark IV) use an
`Execution`; `mentis.execution.mars.MarsExecution` is the real one; `FakeExecution`
stands in for tests.

A finished run is an OBSERVATION, never a verdict: `RunResult.stop_reason == "end_turn"`
says the agent stopped, not that the work is done. Whether work remains is decided by
Mentis from its own record (the request, its stage, what was returned).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class RunSpec:
    """One piece of work for one agent session."""

    run_id: str  # Mentis's id for this execution (the Instance id)
    backend: str  # a MARS backend id: "claude", "codex", "antigravity", "local", "kimi-k3", ...
    workspace: str  # absolute directory the agent works in (MARS never changes it)
    prompt: str  # the brief and the work, as one prompt
    #: ACP McpServerStdio dicts passed to MARS unchanged, e.g. the Mentis bridge for this
    #: run's grant: {"name": "mentis", "command": ..., "args": [...], "env": [{"name", "value"}]}
    mcp_servers: tuple[dict[str, Any], ...] = ()
    options: dict[str, Any] = field(default_factory=dict)  # MARS _meta["mars/options"]
    limits: dict[str, float] = field(default_factory=dict)  # MARS _meta["mars/limits"]
    #: the owner's run consent, MARS _meta["mars/consent"]: {"mode", "workspaces"}.
    #: MARS adds the workspaces to the session's additional directories, so each
    #: runtime's own confinement covers them; it grants nothing and answers nothing.
    consent: dict[str, Any] | None = None
    #: THE RUN'S TOOLING, told once the session is open (docs/tooling-context.md):
    #: called with session/new _meta["mars/tooling"] (None when MARS reports
    #: none), it returns the text to append to the prompt and the effective
    #: tooling to record. It permits nothing.
    tooling: Callable[[dict[str, Any] | None], tuple[str, dict[str, Any]]] | None = None
    #: SESSION CONTINUITY (docs/modernization/CONTRACT.md, WS-P): the runtime
    #: session a previous run of the same work left, `{"token": ...}` as MARS
    #: gave it (session/new _meta["mars/resume"]). Sent as session/new
    #: _meta["mars/resume"]; MARS says whether it loaded it. None: fresh.
    resume: dict[str, Any] | None = None
    #: The prompt to send INSTEAD of `prompt` when MARS says it resumed the
    #: session (_meta["mars/resumed"].resumed is true). Ignored otherwise, so a
    #: MARS that does not resume is sent the full `prompt`, as before.
    continuation: str | None = None
    #: THE RUN'S MCP CONFIGURATION, STATED (O8; `execution.mcp_policy`): sent
    #: as session/new _meta["mars/mcp"] -- the intended Brain/server/execution
    #: and the owner's policy for the runtime's user-level servers. None: not
    #: stated, and the runtime loads its own as before.
    mcp: dict[str, Any] | None = None
    #: WHAT MARS SAID IT APPLIED, AS SOON AS THE SESSION OPENS: called once
    #: with the session/new result's `_meta["mars/consent"]` (None when MARS
    #: reported none), so a run's Permission Mode can be said truthfully while
    #: it works -- not only on its end (item 5.7). It permits nothing.
    on_open: Callable[[dict[str, Any] | None], None] | None = None


@dataclass(frozen=True)
class RunEvent:
    """One MARS session/update, reduced to what Mentis records."""

    kind: str  # ACP update kind: agent_message_chunk, tool_call, tool_call_update, plan, usage_update, ...
    data: dict[str, Any]
    at: float


@dataclass
class RunResult:
    """How one run ended, as MARS reported it."""

    run_id: str
    backend: str
    started: bool  # False when no agent session ever opened (unavailable backend, auth, ...)
    stop_reason: str | None = None  # ACP stopReason when the turn ended normally
    error_kind: str | None = None  # MARS error kind (docs/API.md in MARS), or "auth_required"
    error: str | None = None
    #: MARS's error data `exitCode` and `stderrTail` when the runtime's process died
    #: (`backend_exited`): its exit code and the end of what it wrote to stderr. None when
    #: MARS reported neither. (Exit 1 is also what `taskkill /F` leaves, -1 what
    #: `Stop-Process -Force` leaves: see `execution.interference`.)
    backend_exit_code: int | None = None
    stderr_tail: str | None = None
    #: MARS's error data `retryAfterSeconds`: how long until the runtime's quota resets,
    #: when the runtime reported it (rate_limited); None when nothing was reported.
    retry_after_s: float | None = None
    #: MARS's error data `option`: which requested option the backend does not offer,
    #: exactly "model" or "effort"; None for every other failure, a misconfigured
    #: backend included. `offered` is what it does offer, as MARS listed it.
    option: str | None = None
    offered: list[str] | None = None
    text: str = ""  # everything the agent said (agent_message_chunk), in order
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # {id, title, kind, status, locations}
    usage: dict[str, Any] | None = None
    session_id: str | None = None  # MARS's session id
    #: what MARS reported it applied of `RunSpec.consent` (session/new _meta["mars/consent"])
    consent_applied: dict[str, Any] | None = None
    #: the run's effective tooling as it was told (`RunSpec.tooling`)
    tooling: dict[str, Any] | None = None
    #: session/prompt result _meta["mars/background"]: calls sent to the background
    #: during the turn, stopped when the session closed. None when MARS reported none.
    background: list[dict[str, Any]] | None = None
    #: session/prompt result _meta["mars/workspace"]: each git work tree the turn's
    #: edits fall in, {root, head, dirty, truncated} or {root, error}, as MARS read it.
    workspace: list[dict[str, Any]] | None = None
    #: session/new _meta["mars/resume"], as `{token, backend, supported}`: the
    #: runtime session a later run of the same work may ask to continue. None
    #: when MARS gave no token (a MARS without session continuity).
    runtime_session: dict[str, Any] | None = None
    #: Whether this run continued an earlier runtime session: `{asked, resumed,
    #: why}` (session/new _meta["mars/resumed"]). None when none was asked for.
    resumed: dict[str, Any] | None = None
    #: WHERE THE TIME WENT, epoch seconds: `loop_entered`, `connected`,
    #: `session_opened`, `prompt_sent`, `first_event`, `last_event`, and MARS's
    #: own `mars` spans (session/new _meta["mars/timing"]) when it gives them.
    timing: dict[str, Any] = field(default_factory=dict)
    #: WHICH MCP SERVERS THE SESSION WAS GIVEN, as MARS assembled them
    #: (session/new _meta["mars/mcp"], kept by `mcp_policy.summary`): given,
    #: excluded with reason, unavailable. None when none was stated.
    mcp: dict[str, Any] | None = None
    #: WHAT THE RUNTIME'S OWN RULES REFUSED, as MARS reported it on a
    #: `permission_denied` failure (error data `deniedActions`): each
    #: `{action, display_name?, ...}` with string values only. None when MARS
    #: reported none (N1: a refused agy command ends the run; the record says what).
    denied: list[dict[str, Any]] | None = None
    #: WHY MARS REFUSED TO ASSEMBLE THE SESSION'S MCP SERVERS (`mcp_conflict`):
    #: `{reason, backend?, server?, file?, field?}` as MARS reported them --
    #: `registrations-unreadable`, `registrations-not-known` (an unknown backend;
    #: the owner may vouch with `"mcp_assembly": "trust"`), `merged-definition`
    #: (an owner codex entry MARS cannot neutralise), `other-brain`. None otherwise.
    mcp_conflict: dict[str, Any] | None = None
    started_at: float = 0.0
    finished_at: float = 0.0


class Execution(Protocol):
    def backends(self) -> list[dict[str, Any]]:
        """MARS's catalog (`_mars/backends`): {id, kind, installed, available, reason,
        version, models, efforts, supports}. Bounded; an unreachable MARS returns []."""
        ...

    def perform(self, spec: RunSpec,
                on_event: Callable[[RunEvent], None] | None = None,
                on_permission: Callable[[dict[str, Any]], Any] | None = None) -> RunResult:
        """Run the work to the end of one turn and return how it ended. Blocks; never
        raises for an agent failure (that is a RunResult with `error_kind`).

        `on_permission({"tool_call", "options"})` answers an agent's permission
        request: an option id to select, None to refuse, or `...` to leave it to the
        execution's own default. It may block (it runs off the event loop)."""
        ...

    def capacity(self) -> dict[str, dict[str, Any]]:
        """MARS's `_mars/capacity`: {backend id: {windows, plan, observedAt,
        modelGroups, notes, source}}. Bounded; an unreachable MARS returns {}.
        Optional: an Execution without it reports no capacity."""
        ...

    def cancel(self, run_id: str) -> bool:
        """Cancel a running run; True if it was running. The run's `perform` returns
        with stop_reason "cancelled" (or MARS's error) once MARS has cleaned up."""
        ...

    def running(self) -> set[str]:
        """Run ids currently in `perform`."""
        ...

    def close(self) -> None:
        ...


class FakeExecution:
    """An `Execution` that runs nothing: for tests of the coordination code.

    `script` maps a backend id to a function (spec) -> RunResult, defaulting to an
    agent that answers "done" with stop_reason end_turn.
    """

    def __init__(self, backends: list[dict[str, Any]] | None = None,
                 script: dict[str, Callable[[RunSpec], RunResult]] | None = None,
                 capacity: dict[str, dict[str, Any]] | None = None,
                 resumes: bool | None = None) -> None:
        self._capacity = dict(capacity or {})
        #: SESSION CONTINUITY, as a MARS that supports it would answer: None
        #: (the default) is a MARS without it -- no token, nothing resumed;
        #: True gives a token per run and resumes any token it gave; False
        #: gives tokens it says are resumable but never resumes one (a load
        #: that fails).
        self.resumes = resumes
        self._tokens: set[str] = set()
        #: what each run was actually sent: the continuation when resumed
        self.sent: list[str] = []
        self._backends = backends if backends is not None else [
            {"id": b, "kind": "acp", "installed": True, "available": True, "reason": None,
             "version": "test", "models": [], "efforts": [],
             "supports": {"cancel": "cooperative", "permissions": "forwarded", "mcp": ["stdio"]},
             # As MARS declares it: agy is told its consent before the turn.
             **({"contract": {"version": 1, "capabilities": {"permission_enforcement": {
                 "state": "supported", "kind": "pre-turn"}}}} if b == "antigravity" else {})}
            for b in ("claude", "codex", "antigravity", "local")]
        self.script = script or {}
        self.performed: list[RunSpec] = []
        self._running: set[str] = set()
        self._lock = threading.Lock()

    def backends(self) -> list[dict[str, Any]]:
        return list(self._backends)

    def capacity(self) -> dict[str, dict[str, Any]]:
        return dict(self._capacity)

    def perform(self, spec: RunSpec, on_event=None, on_permission=None) -> RunResult:
        with self._lock:
            self.performed.append(spec)
            self._running.add(spec.run_id)
        try:
            session, resumed = None, None
            if self.resumes is not None:
                token = f"fake-{spec.backend}-{len(self._tokens)}"
                asked = (spec.resume or {}).get("token")
                if asked:
                    ok = bool(self.resumes) and asked in self._tokens
                    resumed = {"asked": True, "resumed": ok,
                               "why": "loaded" if ok else "not resumable here"}
                    if ok:
                        token = asked
                self._tokens.add(token)
                session = {"token": token, "backend": spec.backend,
                           "supported": True}
            self.sent.append(spec.continuation
                             if resumed and resumed["resumed"] and spec.continuation
                             else spec.prompt)
            fn = self.script.get(spec.backend)
            if fn is not None:
                got = fn(spec)
                if session is not None and got.runtime_session is None:
                    got.runtime_session, got.resumed = session, resumed
                return got
            now = time.time()
            if on_event is not None:
                on_event(RunEvent("agent_message_chunk", {"text": "done"}, now))
            return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                             stop_reason="end_turn", text="done", started_at=now,
                             finished_at=time.time(), runtime_session=session,
                             resumed=resumed)
        finally:
            with self._lock:
                self._running.discard(spec.run_id)

    def cancel(self, run_id: str) -> bool:
        return run_id in self._running

    def running(self) -> set[str]:
        with self._lock:
            return set(self._running)

    def close(self) -> None:
        pass
