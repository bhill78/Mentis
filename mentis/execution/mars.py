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

from . import RunEvent, RunResult, RunSpec

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


#: The heading of the block every dispatched prompt closes with
#: (`mentis.web.dispatch._closing_block`); it stays last.
CLOSING_HEADING = "# Before you return"


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

    def precancel(self, run_id: str) -> bool:
        """Cancel a run that is about to `perform`: it is cancelled before
        its prompt is sent. True when it is running now or will be held to
        it; a cancel of a run that never performs lapses after PRECANCEL_S."""
        with self._lock:
            if run_id not in self._running:
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
            if isinstance(meta.get("mars/timing"), dict):
                timing["mars"] = {k: v for k, v in meta["mars/timing"].items()
                                  if isinstance(v, (int, float, str))
                                  and not isinstance(v, bool)}
            result.runtime_session = self._runtime_session(meta, spec.backend)
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
                                     else None))
            self._states[session_id] = state
            with self._lock:
                self._sessions[spec.run_id] = session_id
                cancelled_early = spec.run_id in self._cancel_requested

            if cancelled_early:
                await conn.cancel(session_id=session_id)
                result.stop_reason = "cancelled"
            else:
                timing["prompt_sent"] = time.time()
                prompt_response = await conn.prompt(
                    session_id=session_id, prompt=[text_block(prompt_text)]
                )
                result.stop_reason = prompt_response.stop_reason
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
        except asyncio.CancelledError:
            result.error_kind = "backend_unavailable"
            result.error = "MARS execution closed"
        except Exception as exc:
            result.error_kind, result.error, mars_data = self._error_from_exception(exc)
            result.retry_after_s = self._retry_after(mars_data)
            result.option, result.offered = self._rejected_option(mars_data)
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
            result.tool_calls = [dict(state.tools[tool_id]) for tool_id in state.tool_order]
        return result

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
        async with state.event_lock:
            kind = getattr(update, "session_update", type(update).__name__)
            data = self._model_dict(update)
            data.pop("session_update", None)
            data.pop("field_meta", None)

            if kind == "agent_message_chunk":
                content = getattr(update, "content", None)
                if getattr(content, "type", None) == "text":
                    text = getattr(content, "text", "")
                    state.result.text += text
                    data["text"] = text
            elif kind in ("tool_call", "tool_call_update"):
                self._record_tool(state, update)
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
                       "options": [self._model_dict(option) for option in options],
                       "asked_at": time.time(),
                       # VERIFIED FACTS ONLY (docs/tooling-context.md): the
                       # session's declared shell, and its declared cwd while
                       # no shell command has run in it yet -- after that,
                       # where the shell is is not reported (None).
                       "shell": state.shell,
                       "shell_cwd": (None if any(
                           t.get("kind") == "execute" and i != call_id
                           for i, t in state.tools.items())
                           else state.spec.workspace)}
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

    def _record_tool(self, state: _RunState, update: Any) -> None:
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
            denied = (dict.fromkeys(str(d.get("action")) for d in actions
                                    if isinstance(d, dict) and d.get("action"))
                      if isinstance(actions, list) else ())
            if denied:
                message += f" (refused: {', '.join(denied)})"
            return (str(kind) if kind else "backend_error"), message, mars
        if isinstance(exc, (ConnectionError, BrokenPipeError, EOFError)):
            return "backend_unavailable", str(exc) or type(exc).__name__, {}
        return "backend_unavailable", str(exc) or repr(exc), {}

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
            started_at=started_at,
            finished_at=time.time(),
        )


__all__ = ["MarsExecution"]
