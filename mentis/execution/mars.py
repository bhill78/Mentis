"""The real execution boundary: one long-lived ACP connection to ``mars stdio``.

The public interface is deliberately synchronous because Mentis's coordination code is
synchronous.  ACP remains asynchronous on a single private event loop, which also lets
several caller threads use independent MARS sessions over the same connection.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import logging
import os
import shutil
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from acp import PROTOCOL_VERSION, RequestError, connect_to_agent, text_block
from acp.schema import (
    AllowedOutcome,
    DeniedOutcome,
    Implementation,
    McpServerStdio,
    RequestPermissionResponse,
)

from . import RunEvent, RunResult, RunSpec, send
from .send import SendBoundary

log = logging.getLogger(__name__)

_STREAM_LIMIT = 16 * 1024 * 1024
_CATALOG_TIMEOUT_S = 30.0
#: agy's /usage alone may take up to a minute inside MARS.
_CAPACITY_TIMEOUT_S = 75.0
_PROCESS_EXIT_TIMEOUT_S = 15.0


@dataclass
class _RunState:
    spec: RunSpec
    result: RunResult
    on_event: Callable[[RunEvent], None] | None
    on_permission: Callable[[dict[str, Any]], Any] | None = None
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    tool_order: list[str] = field(default_factory=list)
    event_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    #: the session's declared shell ("powershell", "bash") or None, from
    #: _meta["mars/tooling"] (docs/tooling-context.md)
    shell: str | None = None
    #: where each shell command starts, as MARS declared it ("session": every
    #: command starts in the session's cwd; "per-call"; or None)
    command_cwd: str | None = None
    #: THIS RUN'S SEND, once its prompt has been handed over: what the first
    #: session update acknowledges (`execution.send`). None until then.
    boundary: SendBoundary | None = None
    #: WHICH MESSAGE THE LAST TEXT CAME FROM (ACP `messageId`), and whether a
    #: tool call has been seen since. Together they say where one block of the
    #: agent's prose ends and the next begins (`block_break`). `said_text` is
    #: False until the run's first text chunk, so the first block never breaks.
    said_text: bool = False
    said_message: str | None = None
    tool_since_text: bool = False


def shell_cwd(state: "_RunState", call_id: str | None) -> str | None:
    """Where the shell command of a permission request starts, as a verified
    fact, or None: the session's cwd when MARS declared that every command
    starts there (`command_cwd: "session"`), or while no other shell command
    has run in the session yet; otherwise not known."""
    if state.command_cwd == "session":
        return state.spec.workspace
    if any(t.get("kind") == "execute" and i != call_id for i, t in state.tools.items()):
        return None
    return state.spec.workspace


def block_break(state: "_RunState", update: Any, text: str) -> bool:
    """Whether a new BLOCK of the agent's prose starts at `text`, so that it
    needs a separator from what the run has said so far.

    `agent_message_chunk` is sent both for the token deltas of one block being
    streamed ("Hel", "lo") and for the start of a genuinely separate block --
    the agent stops to call a tool and resumes writing afterwards. Joining the
    deltas is right and joining the blocks is not: a block's text begins at a
    sentence rather than at a space, so without a separator the last sentence
    of one block and the first of the next meet with no character between them.

    ACP names the boundary itself: every chunk of one message carries the same
    `messageId`, and a change means a new message began. Where an agent sends
    one, that is the whole answer and nothing is guessed. Where it sends none,
    a tool call since the last text says the same thing less exactly, and is
    used only then.

    Either way a break is added ONLY where the two would meet with no space at
    all. An agent that ended its block with a newline, or begins the next with
    one, spaced its own prose and it is left exactly as written.
    """
    if not state.said_text or not text or not state.result.text:
        return False                      # the run's first text breaks nothing
    message = getattr(update, "message_id", None)
    if message is not None or state.said_message is not None:
        if message == state.said_message:
            return False
    elif not state.tool_since_text:
        return False
    return not state.result.text[-1].isspace() and not text[0].isspace()


#: The heading of the block every dispatched prompt closes with
#: (`mentis.web.dispatch._closing_block`); it stays last.
CLOSING_HEADING = "# Before you return"


#: The facts of a native worker (`mars/tool.worker`) Mentis keeps, as MARS names them.
WORKER_FACTS = ("description", "requested_model", "agent_type", "agent_id", "model",
                "elapsed_s", "duration_ms", "tool_calls", "context_tokens",
                # A RUNTIME THAT REPORTS ONLY EVENTS OF A WORKER, not a call that
                # spans its work, says which report this is: Codex "started" then
                # "completed"; Antigravity "launched" alone -- the launch is all
                # that is ever known, so it is never read as running. `count` is
                # how many workers one report started, where more than one.
                "event", "count")


def native_facts(meta: Any) -> dict[str, Any]:
    """WHAT MARS SAID OF A TOOL CALL'S PLACE IN ITS RUN (`_meta["mars/tool"]`):

    - `parent`: the call that started the runtime-native worker (a Claude
      sub-agent) this call belongs to;
    - `worker`: this call IS such a worker's start, with what the runtime
      reported of it on this update (possibly nothing yet: an empty dict).

    Only what MARS reported. A runtime that exposes no workers yields `{}`, and
    nothing here makes a worker a participant, an execution or an authority:
    it stays a tool call of the run that made it."""
    tool = meta.get("mars/tool") if isinstance(meta, dict) else None
    if not isinstance(tool, dict):
        return {}
    out: dict[str, Any] = {}
    parent = tool.get("parent")
    if isinstance(parent, str) and parent:
        out["parent"] = parent
    worker = tool.get("worker")
    if isinstance(worker, dict):
        out["worker"] = {k: worker[k] for k in WORKER_FACTS
                         if isinstance(worker.get(k), (str, int, float))
                         and not isinstance(worker.get(k), bool)}
    return out


def turn_usage(meta: Any) -> dict[str, Any] | None:
    """session/prompt result `_meta["mars/usage"]`, as MARS passed on what the
    runtime reported the turn used: `tokens` (with `tokens_cover` where MARS
    knows what they count), `by_model`, `cost`, and `context` -- how full the
    context window is, which is not consumption. None when MARS reported none."""
    usage = meta.get("mars/usage") if isinstance(meta, dict) else None
    if not isinstance(usage, dict):
        return None
    kept = {k: usage[k] for k in ("tokens", "tokens_cover", "by_model", "cost", "context", "how")
            if usage.get(k) is not None}
    return kept or None


def with_tooling(prompt: str, told: str) -> str:
    """The prompt with the run's tooling context in it: before the closing
    "# Before you return" block when the prompt has one, so that block stays
    the last thing the run reads; otherwise after the prompt."""
    at = prompt.rfind("\n" + CLOSING_HEADING)
    if at < 0:
        return f"{prompt}\n\n---\n{told}"
    return f"{prompt[:at + 1]}{told}\n\n---\n\n{prompt[at + 1:]}"


class _MarsClient:
    """The client callbacks MARS invokes over ACP."""

    def __init__(self, owner: MarsExecution) -> None:
        self.owner = owner

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        await self.owner._session_update(session_id, update)

    async def request_permission(
        self, session_id: str, tool_call: Any, options: list[Any], **kwargs: Any
    ) -> RequestPermissionResponse:
        return await self.owner._request_permission(session_id, tool_call, options)


#: How long a cancel asked before a run's `perform` stays good.
PRECANCEL_S = 300.0


class MarsExecution:
    """Run Mentis work through a lazily started ``mars stdio`` process."""

    def __init__(self, command: list[str], *, startup_s: float = 60) -> None:
        if not command:
            raise ValueError("MARS command must not be empty")
        if startup_s <= 0:
            raise ValueError("startup_s must be positive")

        self.command = list(command)
        self.startup_s = float(startup_s)

        # State read by caller threads.
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_ready = threading.Event()
        self._closed = False
        self._running: set[str] = set()
        self._sessions: dict[str, str] = {}
        self._cancel_requested: set[str] = set()
        #: A cancel asked before the run's `perform` began: run id -> when.
        #: `perform` takes it up, and the session is cancelled before its
        #: prompt is sent (`precancel`). Older than PRECANCEL_S, it is stale.
        self._precancelled: dict[str, float] = {}
        #: Runs the caller said it is about to perform (`expect`).
        self._pending: set[str] = set()

        # The fields below belong to the private event-loop thread.
        self._connect_lock: asyncio.Lock | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._conn: Any = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self._states: dict[str, _RunState] = {}
        self._perform_tasks: set[asyncio.Task[Any]] = set()
        self._client = _MarsClient(self)
        #: WHICH `mars stdio` PROCESS answers now: incremented each time one is
        #: started, so a caller holding something MARS said (its backend
        #: catalogue) can tell that MARS restarted since (`MentisService`).
        self.generation = 0

    # ---- synchronous interface -------------------------------------------------

    def backends(self) -> list[dict[str, Any]]:
        """Return MARS's backend catalog, or an empty list when MARS is unreachable."""
        try:
            return self._submit(self._backends(), timeout=_CATALOG_TIMEOUT_S)
        except Exception as exc:
            log.warning("could not get MARS backend catalog: %s", exc)
            return []

    def capacity(self) -> dict[str, dict[str, Any]]:
        """MARS's capacity report (`_mars/capacity`), or {} when MARS cannot give it."""
        try:
            return self._submit(self._capacity(), timeout=_CAPACITY_TIMEOUT_S)
        except Exception as exc:
            log.warning("could not get MARS capacity: %s", exc)
            return {}

    def perform(
        self, spec: RunSpec, on_event: Callable[[RunEvent], None] | None = None,
        on_permission: Callable[[dict[str, Any]], Any] | None = None,
    ) -> RunResult:
        started_at = time.time()
        with self._lock:
            if self._closed:
                return self._failed_result(spec, started_at, RuntimeError("MARS execution is closed"))
            self._running.add(spec.run_id)
            self._pending.discard(spec.run_id)
            self._cancel_requested.discard(spec.run_id)
            asked_before = self._precancelled.pop(spec.run_id, None)
            if asked_before is not None and time.time() - asked_before < PRECANCEL_S:
                self._cancel_requested.add(spec.run_id)

        try:
            try:
                return self._submit(self._perform(spec, on_event, started_at, on_permission))
            except Exception as exc:
                # Event-loop/process failures are observations too.  They must not tear
                # through the coordination code as an exception from an agent run.
                return self._failed_result(spec, started_at, exc)
        finally:
            with self._lock:
                self._running.discard(spec.run_id)
                self._sessions.pop(spec.run_id, None)
                self._cancel_requested.discard(spec.run_id)

    def expect(self, run_id: str) -> None:
        """The caller is about to `perform` this run: until it does, a cancel
        is held for it (`precancel`)."""
        with self._lock:
            self._pending.add(run_id)
            self._precancelled.pop(run_id, None)

    def unexpect(self, run_id: str) -> None:
        """The caller armed this run (`expect`) and then did not perform it: let
        go of what was armed, so nothing is held for the handle's next run."""
        with self._lock:
            self._pending.discard(run_id)
            self._precancelled.pop(run_id, None)

    def precancel(self, run_id: str) -> bool:
        """Cancel a run that is performing, or about to (`expect`): about to,
        it is cancelled before its prompt is sent (or no session opens).
        False for anything else -- a run whose perform has already returned
        is not cancelled, and nothing is held for its handle's next run."""
        with self._lock:
            if run_id in self._pending and run_id not in self._running:
                self._precancelled[run_id] = time.time()
                return True
        return self.cancel(run_id)

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            if run_id not in self._running:
                return False
            self._cancel_requested.add(run_id)
            session_id = self._sessions.get(run_id)

        if session_id is not None:
            try:
                with self._lock:
                    loop_thread = self._thread
                if threading.current_thread() is loop_thread:
                    # Event callbacks run on the ACP loop.  A callback may cancel its
                    # own run, but must not synchronously wait on that same loop.
                    asyncio.create_task(self._cancel_session(session_id))
                else:
                    self._submit(self._cancel_session(session_id))
            except Exception:
                # The perform call will report a dead connection/process.  The run was
                # nevertheless running when cancellation was requested.
                log.debug("could not send cancellation for run %s", run_id, exc_info=True)
        return True

    def running(self) -> set[str]:
        with self._lock:
            return set(self._running)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            thread = self._thread
            loop = self._loop
            pool, self._perm_pool = getattr(self, "_perm_pool", None), None
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)

        if thread is None:
            return
        # close() can race the few instructions between starting the thread and
        # publishing its loop.  Wait for that publication so the new daemon is not
        # accidentally left running forever.
        if loop is None:
            self._loop_ready.wait(timeout=self.startup_s)
            with self._lock:
                loop = self._loop
        if loop is None:
            return
        if threading.current_thread() is thread:
            # This is not the usual path (callbacks are deliberately off-loop), but
            # avoid blocking the loop on its own future if called from internal code.
            async def finish_on_loop() -> None:
                await self._shutdown()
                loop.stop()

            asyncio.create_task(finish_on_loop())
            return

        future = asyncio.run_coroutine_threadsafe(self._shutdown(), loop)
        try:
            future.result(timeout=self.startup_s + _PROCESS_EXIT_TIMEOUT_S + 5)
        except Exception:
            log.warning("error while closing MARS", exc_info=True)
        finally:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=10)

    # ---- private loop and process lifecycle ------------------------------------

    def _ensure_thread(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._closed:
                raise RuntimeError("MARS execution is closed")
            if self._thread is None:
                self._loop_ready.clear()
                self._thread = threading.Thread(
                    target=self._thread_main, name="mentis-mars", daemon=True
                )
                self._thread.start()
            thread = self._thread

        if not self._loop_ready.wait(timeout=self.startup_s):
            raise TimeoutError("MARS event loop did not start")
        with self._lock:
            loop = self._loop
        if loop is None or not thread.is_alive():
            raise RuntimeError("MARS event loop is not running")
        return loop

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._connect_lock = asyncio.Lock()
        with self._lock:
            self._loop = loop
        self._loop_ready.set()
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            with self._lock:
                self._loop = None

    def _submit(self, coroutine: Any, timeout: float | None = None) -> Any:
        try:
            loop = self._ensure_thread()
        except Exception:
            coroutine.close()
            raise
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise TimeoutError("MARS operation timed out") from None

    def _resolved_command(self) -> list[str]:
        command = list(self.command)
        if os.name == "nt":
            executable = shutil.which(command[0])
            if executable is None:
                raise FileNotFoundError(f"MARS executable {command[0]!r} is not on PATH")
            command[0] = executable
        return command

    async def _ensure_connection(self) -> Any:
        assert self._connect_lock is not None
        async with self._connect_lock:
            if self._conn is not None and self._proc is not None and self._proc.returncode is None:
                return self._conn

            # A process that died since the previous call is discarded here.  This call
            # makes exactly one fresh start attempt; a failed start is not recursively
            # retried until another public call arrives.
            await self._drop_connection()
            command = self._resolved_command()
            self._stderr_tail.clear()
            try:
                proc = await asyncio.create_subprocess_exec(
                    *command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=_STREAM_LIMIT,
                )
            except OSError as exc:
                raise RuntimeError(f"could not start MARS: {exc}") from exc

            assert proc.stdin is not None and proc.stdout is not None
            self._proc = proc
            self.generation += 1
            self._stderr_task = asyncio.create_task(self._drain_stderr(proc))
            conn = connect_to_agent(
                self._client, proc.stdin, proc.stdout, use_unstable_protocol=True
            )
            self._conn = conn
            try:
                await asyncio.wait_for(
                    conn.initialize(
                        protocol_version=PROTOCOL_VERSION,
                        client_info=Implementation(name="mentis", title="Mentis", version="0.1.0"),
                    ),
                    self.startup_s,
                )
            except BaseException as exc:
                await self._drop_connection()
                detail = self._stderr_detail()
                if isinstance(exc, asyncio.TimeoutError):
                    raise TimeoutError(f"MARS did not initialize within {self.startup_s:g}s{detail}") from None
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise RuntimeError(f"MARS initialization failed: {exc}{detail}") from exc
            return conn

    async def _drain_stderr(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            text = line.decode(errors="replace").rstrip()
            self._stderr_tail.append(text)
            log.debug("MARS stderr: %s", text)

    def _stderr_detail(self) -> str:
        if not self._stderr_tail:
            return ""
        return "; stderr: " + " | ".join(self._stderr_tail)[-2000:]

    async def _drop_connection(self) -> None:
        conn, proc, stderr_task = self._conn, self._proc, self._stderr_task
        self._conn = None
        self._proc = None
        self._stderr_task = None

        if conn is not None:
            with contextlib.suppress(Exception):
                await conn.close()
        if proc is not None:
            if proc.stdin is not None:
                proc.stdin.close()
            if proc.returncode is None:
                try:
                    await asyncio.wait_for(proc.wait(), _PROCESS_EXIT_TIMEOUT_S)
                except TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        proc.kill()
                    with contextlib.suppress(Exception):
                        await proc.wait()
            else:
                with contextlib.suppress(Exception):
                    await proc.wait()
        if stderr_task is not None:
            if not stderr_task.done():
                stderr_task.cancel()
            with contextlib.suppress(BaseException):
                await stderr_task

    async def _mark_connection_failed(self, conn: Any) -> None:
        assert self._connect_lock is not None
        async with self._connect_lock:
            # Do not let a stale request tear down a newer, successfully restarted link.
            if conn is self._conn:
                await self._drop_connection()

    async def _shutdown(self) -> None:
        assert self._connect_lock is not None
        # Serialize with startup.  Without this lock, close() could observe no process
        # just before _ensure_connection publishes one, then stop the loop and orphan
        # the newly spawned child.
        async with self._connect_lock:
            conn = self._conn
            if conn is not None:
                for session_id in list(self._states):
                    with contextlib.suppress(Exception):
                        await conn.cancel(session_id=session_id)
            await self._drop_connection()

        current = asyncio.current_task()
        active = [task for task in self._perform_tasks if task is not current and not task.done()]
        if active:
            done, pending = await asyncio.wait(active, timeout=5)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    # ---- ACP operations ---------------------------------------------------------

    async def _backends(self) -> list[dict[str, Any]]:
        try:
            conn = await self._ensure_connection()
            response = await asyncio.wait_for(
                conn.ext_method("mars/backends", {}), _CATALOG_TIMEOUT_S
            )
            backends = response.get("backends", []) if isinstance(response, dict) else []
            return [dict(item) for item in backends if isinstance(item, dict)]
        except Exception as exc:
            if "conn" in locals() and isinstance(
                exc, (ConnectionError, BrokenPipeError, EOFError)
            ):
                await self._mark_connection_failed(conn)
            log.warning("MARS backend discovery failed: %s", exc)
            return []

    async def _capacity(self) -> dict[str, dict[str, Any]]:
        try:
            conn = await self._ensure_connection()
            response = await asyncio.wait_for(
                conn.ext_method("mars/capacity", {}), _CAPACITY_TIMEOUT_S
            )
        except Exception as exc:
            log.warning("MARS capacity read failed: %s", exc)
            return {}
        report = response.get("capacity") if isinstance(response, dict) else None
        if not isinstance(report, dict):
            return {}
        return {str(k): dict(v) for k, v in report.items() if isinstance(v, dict)}

    async def _perform(
        self,
        spec: RunSpec,
        on_event: Callable[[RunEvent], None] | None,
        started_at: float,
        on_permission: Callable[[dict[str, Any]], Any] | None = None,
    ) -> RunResult:
        task = asyncio.current_task()
        assert task is not None
        self._perform_tasks.add(task)
        result = RunResult(
            run_id=spec.run_id,
            backend=spec.backend,
            started=False,
            started_at=started_at,
        )
        # WHERE THE TIME WENT (WS-P): `loop_entered` against the caller's
        # `started_at` says how long the run queued for this event loop.
        timing = result.timing
        timing["loop_entered"] = time.time()
        session_id: str | None = None
        conn: Any = None
        #: THIS RUN'S SEND (`execution.send`), from the moment its gate is
        #: entered: so a failure anywhere below can say what became of the
        #: bytes rather than leave a send unaccounted for.
        boundary: SendBoundary | None = None
        asked = (spec.resume or {}).get("token") if isinstance(spec.resume, dict) else None
        try:
            conn = await self._ensure_connection()
            timing["connected"] = time.time()
            # CANCELLED BEFORE IT OPENED: no session is opened at all.
            with self._lock:
                cancelled_first = spec.run_id in self._cancel_requested
            if cancelled_first:
                result.stop_reason = "cancelled"
                return result
            mcp_servers = [McpServerStdio.model_validate(server) for server in spec.mcp_servers]
            response = await conn.new_session(
                cwd=spec.workspace,
                mcp_servers=mcp_servers,
                **{
                    "mars/backend": spec.backend,
                    "mars/options": dict(spec.options),
                    "mars/limits": dict(spec.limits),
                    **({"mars/consent": dict(spec.consent)} if spec.consent else {}),
                    # THE RUN'S MCP CONFIGURATION, stated (O8): MARS
                    # assembles the session's servers from it.
                    **({"mars/mcp": dict(spec.mcp)} if spec.mcp else {}),
                    # THE RUNTIME SESSION AN EARLIER RUN OF THIS WORK LEFT, to
                    # continue if MARS can; a MARS that does not know the key
                    # ignores it and opens a fresh session.
                    **({"mars/resume": {"token": str(asked)}} if asked else {}),
                },
            )
            timing["session_opened"] = time.time()
            session_id = response.session_id
            result.session_id = session_id
            meta = getattr(response, "field_meta", None) or {}
            if isinstance(meta.get("mars/consent"), dict):
                result.consent_applied = dict(meta["mars/consent"])
            if spec.on_open is not None:
                try:
                    spec.on_open(dict(result.consent_applied)
                                 if result.consent_applied else None)
                except Exception:                          # noqa: BLE001
                    log.warning("on_open failed for run %s", spec.run_id,
                                exc_info=True)
            if isinstance(meta.get("mars/timing"), dict):
                timing["mars"] = {k: v for k, v in meta["mars/timing"].items()
                                  if isinstance(v, (int, float, str))
                                  and not isinstance(v, bool)}
            result.runtime_session = self._runtime_session(meta, spec.backend)
            if spec.mcp:
                from mentis.execution.mcp_policy import summary
                result.mcp = summary(meta.get("mars/mcp"), spec.mcp)
            resumed = self._resumed(meta, asked)
            result.resumed = resumed
            # A RESUMED SESSION IS SENT THE CONTINUATION; anything else -- no
            # token asked, a MARS that does not say, or one that could not
            # load it -- is sent the full composition, as before.
            base = (spec.continuation if resumed and resumed["resumed"]
                    and spec.continuation else spec.prompt)
            # THE RUN'S TOOLING, now that MARS has said what the session can
            # reach: told once, after the shared prompt, and recorded.
            reported = meta.get("mars/tooling")
            reported = dict(reported) if isinstance(reported, dict) else None
            if isinstance(meta.get("mars/mcp"), dict):
                # what MARS gave the session, so the run is told exactly that
                reported = {**(reported or {}), "mcp": dict(meta["mars/mcp"])}
            prompt_text = base
            if spec.tooling is not None:
                try:
                    told, result.tooling = spec.tooling(reported)
                    if told:
                        prompt_text = with_tooling(base, told)
                except Exception:                          # noqa: BLE001
                    log.warning("tooling context failed for run %s; not told",
                                spec.run_id, exc_info=True)
            result.started = True
            shell = (reported or {}).get("shell") or {}
            state = _RunState(spec=spec, result=result, on_event=on_event,
                              on_permission=on_permission,
                              shell=(shell.get("name") if shell.get("how") == "declared"
                                     else None),
                              command_cwd=((reported or {}).get("command_cwd")
                                           if (reported or {}).get("command_cwd")
                                           in ("session", "per-call") else None))
            self._states[session_id] = state
            with self._lock:
                self._sessions[spec.run_id] = session_id
                cancelled_early = spec.run_id in self._cancel_requested

            if cancelled_early:
                await conn.cancel(session_id=session_id)
                result.stop_reason = "cancelled"
            else:
                # WHETHER IT MAY STILL BE SENT, HERE AND NOWHERE EARLIER
                # (`execution.send`). Deciding a run may go and sending it are
                # not the same moment: the connection, the session and the
                # tooling happen in between, and what the caller checked can
                # have changed since. Its gate is entered now, with nothing
                # but the hand-over after it, off this loop because it may
                # take a record transaction. A refusal sends nothing: the
                # session that opened is closed in `finally`, like a cancel's.
                boundary = SendBoundary(spec)
                state.boundary = boundary
                loop = asyncio.get_running_loop()
                refused = await loop.run_in_executor(self._permission_pool(),
                                                     boundary.reserve)
                if refused:
                    await self._tell(boundary, send.REFUSED, why=refused)
                    result.stop_reason = "cancelled"
                    result.error_kind = "cancelled"
                    result.error = "not sent: " + refused
                    return result
                timing["prompt_sent"] = time.time()
                # HANDED OVER, WHICH IS NOT DELIVERED: `supplied` waits for
                # this turn's own acknowledgement, below or in `_session_update`.
                await self._tell(boundary, send.SENT, at=timing["prompt_sent"])
                prompt_response = await conn.prompt(
                    session_id=session_id, prompt=[text_block(prompt_text)]
                )
                result.stop_reason = prompt_response.stop_reason
                # THE RUNTIME ANSWERED FOR THESE BYTES: the turn ran, so they
                # arrived. Only now, and never read back onto the send itself.
                boundary.acknowledge(send.BY_RESULT)
                await self._tell(boundary, send.SUPPLIED)
                # WHAT THE RUNTIME SAID THE TURN USED (`mars/usage`): tokens,
                # per-model rows (native sub-agents included where the runtime
                # counts them), cost, and the context size apart from them.
                turn_used = turn_usage(getattr(prompt_response, "field_meta", None))
                if turn_used is not None:
                    result.turn_usage = turn_used
                    async with state.event_lock:
                        await self._emit(state, RunEvent("turn_usage", dict(turn_used), time.time()))
                # WHAT THE TURN LEFT BEHIND, as MARS read it at the turn end:
                # work sent to the background, and git work trees it edited.
                ended = getattr(prompt_response, "field_meta", None) or {}
                for key, attr in (("mars/background", "background"),
                                  ("mars/workspace", "workspace")):
                    if isinstance(ended.get(key), list) and ended[key]:
                        setattr(result, attr,
                                [dict(e) for e in ended[key] if isinstance(e, dict)])
                # A PER-TURN BACKEND (agy) knows its runtime session only
                # after a turn, so MARS gives the token on the prompt result;
                # when it does, it is the one a later run continues.
                later = self._runtime_session(ended, spec.backend)
                if later is not None:
                    result.runtime_session = later
                # WHAT THE RUNTIME REFUSED IN A TURN THAT WENT ON (`mars/denied`):
                # a pre-turn runtime handed a refusal back to the model, which
                # continued with its other tools. The same record as a refusal
                # that ended the run: the refused command stays named.
                result.denied = self._denied(
                    {"deniedActions": ended.get("mars/denied")}) or result.denied
        except asyncio.CancelledError as exc:
            result.error_kind = "backend_unavailable"
            result.error = "MARS execution closed"
            # BYTES IN FLIGHT WHEN THE LOOP WENT: not called delivered, and
            # not called failed either -- nobody knows (`execution.send`).
            if boundary is not None:
                boundary.after_failure(exc)
        except Exception as exc:
            # A SEND THE OTHER END ANSWERED AND DID NOT TAKE failed; one whose
            # connection simply went is not known either way, and is not
            # called delivered or failed (`execution.send`).
            if boundary is not None:
                boundary.after_failure(exc, refused=isinstance(exc, RequestError))
            result.error_kind, result.error, mars_data = self._error_from_exception(exc)
            result.retry_after_s = self._retry_after(mars_data)
            result.option, result.offered = self._rejected_option(mars_data)
            result.denied = self._denied(mars_data)
            result.mcp_conflict = self._mcp_conflict(result.error_kind, mars_data)
            # HOW THE RUNTIME'S PROCESS DIED, as MARS saw it (kept, not only the message).
            result.backend_exit_code, result.stderr_tail = self._death(mars_data)
            if conn is not None and isinstance(exc, (ConnectionError, BrokenPipeError, EOFError)):
                await self._mark_connection_failed(conn)
        finally:
            if session_id is not None and conn is not None:
                with contextlib.suppress(Exception):
                    await conn.close_session(session_id=session_id)
                self._states.pop(session_id, None)
            with self._lock:
                self._sessions.pop(spec.run_id, None)
            result.finished_at = time.time()
            self._perform_tasks.discard(task)

        state = locals().get("state")
        if isinstance(state, _RunState):
            # A CALL THE RUNTIME NEVER REPORTED FINISHED (a cancelled or killed
            # turn sends no terminal status for what it was running): said as
            # exactly that, never left reading as still pending.
            for record in state.tools.values():
                if record.get("status") in (None, "pending", "in_progress"):
                    record["open_at_end"] = True
            result.tool_calls = [dict(state.tools[tool_id]) for tool_id in state.tool_order]
        return result

    async def _tell(self, boundary: SendBoundary, what: str, *,
                    why: str | None = None, at: float | None = None) -> None:
        """Say what became of a send, off this loop: the caller's audit may
        write to the record, and no other session's events wait for it.

        Each report is awaited in turn, so `sent` is told before the
        acknowledgement that follows it and never the other way round. The
        reports are one-shot, so one made in a thread that outlived a
        cancellation is not made twice.
        """
        def report() -> None:
            if what == send.SENT:
                boundary.handed_over(at)
            else:
                boundary.say(what, why=why)
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(self._permission_pool(), report)
        except asyncio.CancelledError:
            report()
            raise
        except RuntimeError:                  # the pool is shutting down
            report()

    @staticmethod
    def _runtime_session(meta: dict[str, Any], backend: str) -> dict[str, Any] | None:
        """session/new _meta["mars/resume"] as `{token, backend, supported}`,
        or None when MARS gave no token."""
        given = meta.get("mars/resume")
        if not isinstance(given, dict):
            return None
        token = given.get("token")
        if not isinstance(token, str) or not token:
            return None
        return {"token": token, "backend": backend,
                "supported": given.get("supported") is not False}

    @staticmethod
    def _resumed(meta: dict[str, Any], asked: str | None) -> dict[str, Any] | None:
        """Whether MARS continued the session asked for: `{asked, resumed,
        why}`. Only an explicit `resumed: true` counts; a MARS that says
        nothing resumed nothing."""
        if not asked:
            return None
        said = meta.get("mars/resumed")
        if not isinstance(said, dict):
            return {"asked": True, "resumed": False,
                    "why": "MARS did not say it resumed the session"}
        return {"asked": True, "resumed": said.get("resumed") is True,
                "why": str(said.get("why") or "")}

    async def _cancel_session(self, session_id: str) -> None:
        conn = self._conn
        if conn is not None:
            await conn.cancel(session_id=session_id)

    async def _session_update(self, session_id: str, update: Any) -> None:
        state = self._states.get(session_id)
        if state is None:
            return
        now = time.time()
        timing = state.result.timing
        timing.setdefault("first_event", now)
        timing["last_event"] = now
        # THE RUNTIME ACTING ON WHAT IT WAS SENT is an acknowledgement of
        # those bytes (`execution.send`), and the earliest there is. Only
        # recorded here; the report is made where the send is.
        if state.boundary is not None:
            state.boundary.acknowledge(send.BY_UPDATE, now)
        async with state.event_lock:
            kind = getattr(update, "session_update", type(update).__name__)
            data = self._model_dict(update)
            data.pop("session_update", None)
            data.pop("field_meta", None)

            if kind == "agent_message_chunk":
                content = getattr(update, "content", None)
                if getattr(content, "type", None) == "text":
                    text = getattr(content, "text", "")
                    if block_break(state, update, text):
                        state.result.text += "\n\n"
                    state.result.text += text
                    state.said_text = True
                    state.said_message = getattr(update, "message_id", None)
                    state.tool_since_text = False
                    data["text"] = text
            elif kind in ("tool_call", "tool_call_update"):
                # A NEW CALL ENDS THE BLOCK OF PROSE BEFORE IT (`block_break`);
                # an update to a call already made says nothing about the text,
                # because one can arrive while the agent is still writing.
                if kind == "tool_call":
                    state.tool_since_text = True
                # ITS PLACE IN THE RUN, read before `_meta` is dropped: the
                # native worker it belongs to, or that it starts one.
                data.update(self._record_tool(state, update))
            elif kind == "usage_update":
                state.result.usage = dict(data)

            await self._emit(state, RunEvent(kind=kind, data=data, at=time.time()))

    async def _request_permission(
        self, session_id: str, tool_call: Any, options: list[Any]
    ) -> RequestPermissionResponse:
        selected = next((option for option in options if option.kind == "allow_once"), None)
        if selected is None:
            selected = next((option for option in options if option.kind.startswith("allow_")), None)
        answered_by = "default"

        state = self._states.get(session_id)
        # WHO ANSWERS is Mentis's to decide (`on_permission`): the run's
        # authority or the owner. It may wait for a person, so it runs off the
        # event loop, and nothing is held while it waits.
        if state is not None and state.on_permission is not None:
            call_id = getattr(tool_call, "tool_call_id", None)
            request = {"tool_call": self._model_dict(tool_call),
                       # A NATIVE WORKER ASKED (a Claude sub-agent): the same
                       # run, the same authority and consent; only said.
                       **self._asked_by_worker(state, tool_call),
                       "options": [self._model_dict(option) for option in options],
                       "asked_at": time.time(),
                       # VERIFIED FACTS ONLY (docs/tooling-context.md): the
                       # session's declared shell, and its declared cwd while
                       # no shell command has run in it yet -- after that,
                       # where the shell is is not reported (None) -- unless
                       # MARS declared that every command starts there
                       # (`command_cwd: "session"`, round 2).
                       "shell": state.shell,
                       "shell_cwd": shell_cwd(state, call_id)}
            loop = asyncio.get_running_loop()
            try:
                chosen = await loop.run_in_executor(self._permission_pool(),
                                                    state.on_permission, request)
            except Exception:
                log.warning("permission policy failed for run %s; refused",
                            state.spec.run_id, exc_info=True)
                chosen = None
            if chosen is not ...:
                answered_by = "mentis"
                selected = next((option for option in options
                                 if chosen is not None and option.option_id == chosen), None)
                if selected is None:
                    # A STOPPED RUN'S REQUEST is answered as ACP answers a
                    # cancelled turn's: `cancelled`.
                    with self._lock:
                        stopping = state.spec.run_id in self._cancel_requested
                    if stopping:
                        await self._permission_event(state, tool_call, options, None,
                                                     answered_by)
                        return RequestPermissionResponse(
                            outcome=DeniedOutcome(outcome="cancelled"))
                    # REFUSED, OR NOT ANSWERED: fail closed with the request's
                    # own reject option, else as cancelled.
                    reject = next((option for option in options
                                   if option.kind == "reject_once"), None)
                    if reject is not None:
                        await self._permission_event(state, tool_call, options, reject,
                                                     answered_by)
                        return RequestPermissionResponse(
                            outcome=AllowedOutcome(outcome="selected",
                                                   option_id=reject.option_id))

        if state is not None:
            async with state.event_lock:
                data = {
                    "tool_call": self._model_dict(tool_call),
                    **self._asked_by_worker(state, tool_call),
                    "options": [self._model_dict(option) for option in options],
                    "selected_option_id": getattr(selected, "option_id", None),
                    "outcome": "selected" if selected is not None else "cancelled",
                    "answered_by": answered_by,
                }
                await self._emit(state, RunEvent("permission", data, time.time()))

        if selected is None:
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))
        return RequestPermissionResponse(
            outcome=AllowedOutcome(outcome="selected", option_id=selected.option_id)
        )

    def _permission_pool(self) -> concurrent.futures.ThreadPoolExecutor:
        """Threads that wait for a permission answer: their own, so owners
        being slow never queue a request behind the loop's default executor."""
        with self._lock:
            if getattr(self, "_perm_pool", None) is None:
                self._perm_pool = concurrent.futures.ThreadPoolExecutor(
                    max_workers=64, thread_name_prefix="mars-permission")
            return self._perm_pool

    async def _permission_event(self, state: _RunState, tool_call: Any, options: list[Any],
                                selected: Any, answered_by: str) -> None:
        async with state.event_lock:
            await self._emit(state, RunEvent("permission", {
                "tool_call": self._model_dict(tool_call),
                **self._asked_by_worker(state, tool_call),
                "options": [self._model_dict(option) for option in options],
                "selected_option_id": getattr(selected, "option_id", None),
                "outcome": "selected" if selected is not None else "cancelled",
                "answered_by": answered_by}, time.time()))

    async def _emit(self, state: _RunState, event: RunEvent) -> None:
        if state.on_event is None:
            return
        try:
            state.on_event(event)
        except Exception:
            log.warning("MARS event callback failed for run %s", state.spec.run_id, exc_info=True)

    @staticmethod
    def _model_dict(value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json", by_alias=False, exclude_none=True)
        if isinstance(value, dict):
            return dict(value)
        return {"value": str(value)}

    @staticmethod
    def _asked_by_worker(state: _RunState, tool_call: Any) -> dict[str, Any]:
        """`{parent, parent_title}` when the call a permission is asked for
        belongs to a native worker, as MARS said (`mars/tool.parent`) or as
        this run's own record of that call says; else nothing."""
        parent = native_facts(getattr(tool_call, "field_meta", None)).get("parent")
        if not parent:
            known = state.tools.get(getattr(tool_call, "tool_call_id", None)) or {}
            parent = known.get("parent")
        if not parent:
            return {}
        title = (state.tools.get(parent) or {}).get("title")
        return {"parent": parent, **({"parent_title": title} if title else {})}

    def _record_tool(self, state: _RunState, update: Any) -> dict[str, Any]:
        """Keeps the call in the run's record; returns what MARS said of its
        place in the run (`native_facts`), for the event."""
        tool_id = update.tool_call_id
        if tool_id not in state.tools:
            state.tool_order.append(tool_id)
            state.tools[tool_id] = {
                "id": tool_id,
                "title": "",
                "kind": None,
                "status": None,
                "locations": [],
            }
        record = state.tools[tool_id]
        for name in ("title", "kind", "status"):
            value = getattr(update, name, None)
            if value is not None:
                record[name] = value
        # THE RUNTIME'S OWN NAME FOR THE TOOL, observed on this call: MARS's
        # `mars/tool`, else Claude's `claudeCode.toolName`.
        meta = getattr(update, "field_meta", None) or {}
        named = ((meta.get("mars/tool") or {}).get("name")
                 or (meta.get("claudeCode") or {}).get("toolName")) if isinstance(meta, dict) else None
        if isinstance(named, str) and named:
            record["name"] = named
        locations = getattr(update, "locations", None)
        if locations is not None:
            record["locations"] = [self._model_dict(location) for location in locations]
        facts = native_facts(meta)
        if "parent" in facts:
            record["parent"] = facts["parent"]
        if "worker" in facts:
            # one worker, reported over several updates: later facts add to earlier
            record["worker"] = {**(record.get("worker") or {}), **facts["worker"]}
        worker = record.get("worker") or {}
        if worker.get("event") == "completed":
            # THE REPORT THAT A WORKER COMPLETED (Codex), for a worker whose start
            # this run holds: that worker is completed, and this call is the
            # report of it, under it -- not a second worker.
            start = next((r for r in state.tools.values() if r is not record
                          and (r.get("worker") or {}).get("event") == "started"
                          and r["worker"].get("agent_id")
                          and r["worker"].get("agent_id") == worker.get("agent_id")), None)
            if start is not None:
                start["status"] = "completed"
                start["worker_done"] = True
                record.pop("worker", None)
                record["parent"] = start["id"]
                return {"parent": start["id"], "worker_ended": start["id"]}
        elif worker.get("event") in ("started", "launched") and record.get("status") != "failed":
            # THE CALL'S OWN STATUS IS THE LAUNCH'S (it "completes" in a fraction
            # of a second); the worker is at work until its end is reported, and
            # a runtime that never reports one leaves it open (`open_at_end`).
            if not record.get("worker_done"):
                record["status"] = "in_progress"
            return {**facts, "worker": dict(worker), "status": record["status"]}
        return facts

    @staticmethod
    def _error_from_exception(exc: BaseException) -> tuple[str, str, dict[str, Any]]:
        """(kind, message, MARS's error data `error.data["mars"]` or {})."""
        if isinstance(exc, RequestError):
            data = exc.data if isinstance(exc.data, dict) else {}
            mars = data.get("mars") if isinstance(data.get("mars"), dict) else {}
            if exc.code == -32000:
                return "auth_required", str(exc), mars
            kind = mars.get("kind")
            message = str(exc)
            # WHAT WAS REFUSED, or the record says only that something was
            # (`deniedActions`, MARS docs/API.md).
            actions = mars.get("deniedActions")
            denied = (dict.fromkeys(_refused_words(d) for d in actions
                                    if isinstance(d, dict) and d.get("action"))
                      if isinstance(actions, list) else ())
            if denied:
                message += f" (refused: {', '.join(denied)})"
            return (str(kind) if kind else "backend_error"), message, mars
        if isinstance(exc, (ConnectionError, BrokenPipeError, EOFError)):
            return "backend_unavailable", str(exc) or type(exc).__name__, {}
        return "backend_unavailable", str(exc) or repr(exc), {}

    @staticmethod
    def _mcp_conflict(kind: str | None, mars: dict[str, Any]) -> dict[str, Any] | None:
        """MARS's structured `mcp_conflict` refusal (`reason`, `backend`, `server`,
        `file`, `field`), string values only; None for any other failure."""
        if kind != "mcp_conflict":
            return None
        kept = {k: mars[k][:500] for k in ("reason", "backend", "server", "file", "field")
                if isinstance(mars.get(k), str) and mars[k]}
        return kept or {"reason": "not reported"}

    @staticmethod
    def _denied(mars: dict[str, Any]) -> list[dict[str, Any]] | None:
        """MARS's `deniedActions`, as reported: each entry's string fields
        (bounded), or None when there are none."""
        actions = mars.get("deniedActions")
        if not isinstance(actions, list):
            return None
        out = []
        for d in actions[:20]:
            if isinstance(d, dict):
                kept = {str(k)[:40]: v[:500] for k, v in d.items()
                        if isinstance(v, str) and v}
                if kept:
                    out.append(kept)
        return out or None

    @staticmethod
    def _retry_after(mars: dict[str, Any]) -> float | None:
        """MARS's reported `retryAfterSeconds` (seconds until the quota resets), or None."""
        value = mars.get("retryAfterSeconds")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            return None
        return float(value)

    @staticmethod
    def _rejected_option(mars: dict[str, Any]) -> tuple[str | None, list[str] | None]:
        """MARS's structured `option` and `offered`, when a requested model or effort
        was rejected as not offered. Only the two exact values count; no message is
        ever read for this, so anything else is an ordinary failure."""
        option = mars.get("option")
        if option not in ("model", "effort"):
            return None, None
        offered = mars.get("offered")
        return option, ([str(o) for o in offered] if isinstance(offered, list) else None)

    @classmethod
    def _failed_result(cls, spec: RunSpec, started_at: float, exc: BaseException) -> RunResult:
        kind, message, mars = cls._error_from_exception(exc)
        option, offered = cls._rejected_option(mars)
        return RunResult(
            run_id=spec.run_id,
            backend=spec.backend,
            started=False,
            error_kind=kind,
            error=message,
            retry_after_s=cls._retry_after(mars),
            option=option,
            offered=offered,
            denied=cls._denied(mars),
            mcp_conflict=cls._mcp_conflict(kind, mars),
            backend_exit_code=cls._death(mars)[0],
            stderr_tail=cls._death(mars)[1],
            started_at=started_at,
            finished_at=time.time(),
        )

    @staticmethod
    def _death(mars: dict[str, Any]) -> tuple[int | None, str | None]:
        """MARS's error data `exitCode` and `stderrTail` (backend_exited, protocol_error):
        the runtime process's exit code and the end of its stderr, redacted and bounded.
        (None, None) when MARS reported neither."""
        code = mars.get("exitCode")
        code = code if isinstance(code, int) and not isinstance(code, bool) else None
        tail = mars.get("stderrTail")
        if isinstance(tail, str) and tail.strip():
            from mentis.redaction import redact
            tail = redact(tail[-2000:])
        else:
            tail = None
        return code, tail


def _refused_words(d: dict[str, Any]) -> str:
    """One refused action as the failure says it: its action, and the command
    line MARS named when it did (command `dir`)."""
    words = str(d.get("action"))
    command = d.get("command")
    if isinstance(command, str) and command.strip():
        line = " ".join(command.split())
        words += f" `{line[:120]}{'...' if len(line) > 120 else ''}`"
    return words


__all__ = ["MarsExecution"]
