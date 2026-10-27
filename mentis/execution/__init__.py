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
    text: str = ""  # everything the agent said (agent_message_chunk), in order
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # {id, title, kind, status, locations}
    usage: dict[str, Any] | None = None
    session_id: str | None = None  # MARS's session id
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
                 script: dict[str, Callable[[RunSpec], RunResult]] | None = None) -> None:
        self._backends = backends if backends is not None else [
            {"id": b, "kind": "acp", "installed": True, "available": True, "reason": None,
             "version": "test", "models": [], "efforts": [],
             "supports": {"cancel": "cooperative", "permissions": "forwarded", "mcp": ["stdio"]}}
            for b in ("claude", "codex", "antigravity", "local")]
        self.script = script or {}
        self.performed: list[RunSpec] = []
        self._running: set[str] = set()
        self._lock = threading.Lock()

    def backends(self) -> list[dict[str, Any]]:
        return list(self._backends)

    def perform(self, spec: RunSpec, on_event=None, on_permission=None) -> RunResult:
        with self._lock:
            self.performed.append(spec)
            self._running.add(spec.run_id)
        try:
            fn = self.script.get(spec.backend)
            if fn is not None:
                return fn(spec)
            now = time.time()
            if on_event is not None:
                on_event(RunEvent("agent_message_chunk", {"text": "done"}, now))
            return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                             stop_reason="end_turn", text="done", started_at=now,
                             finished_at=time.time())
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
