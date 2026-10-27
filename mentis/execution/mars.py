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

        # The fields below belong to the private event-loop thread.
        self._connect_lock: asyncio.Lock | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._conn: Any = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self._states: dict[str, _RunState] = {}
        self._perform_tasks: set[asyncio.Task[Any]] = set()
        self._client = _MarsClient(self)

    # ---- synchronous interface -------------------------------------------------

    def backends(self) -> list[dict[str, Any]]:
        """Return MARS's backend catalog, or an empty list when MARS is unreachable."""
        try:
            return self._submit(self._backends(), timeout=_CATALOG_TIMEOUT_S)
        except Exception as exc:
            log.warning("could not get MARS backend catalog: %s", exc)
            return []

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
        session_id: str | None = None
        conn: Any = None
        try:
            conn = await self._ensure_connection()
            mcp_servers = [McpServerStdio.model_validate(server) for server in spec.mcp_servers]
            response = await conn.new_session(
                cwd=spec.workspace,
                mcp_servers=mcp_servers,
                **{
                    "mars/backend": spec.backend,
                    "mars/options": dict(spec.options),
                    "mars/limits": dict(spec.limits),
                },
            )
            session_id = response.session_id
            result.session_id = session_id
            result.started = True
            state = _RunState(spec=spec, result=result, on_event=on_event,
                              on_permission=on_permission)
            self._states[session_id] = state
            with self._lock:
                self._sessions[spec.run_id] = session_id
                cancelled_early = spec.run_id in self._cancel_requested

            if cancelled_early:
                await conn.cancel(session_id=session_id)
                result.stop_reason = "cancelled"
            else:
                prompt_response = await conn.prompt(
                    session_id=session_id, prompt=[text_block(spec.prompt)]
                )
                result.stop_reason = prompt_response.stop_reason
        except asyncio.CancelledError:
            result.error_kind = "backend_unavailable"
            result.error = "MARS execution closed"
        except Exception as exc:
            result.error_kind, result.error = self._error_from_exception(exc)
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

    async def _cancel_session(self, session_id: str) -> None:
        conn = self._conn
        if conn is not None:
            await conn.cancel(session_id=session_id)

    async def _session_update(self, session_id: str, update: Any) -> None:
        state = self._states.get(session_id)
        if state is None:
            return
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
            request = {"tool_call": self._model_dict(tool_call),
                       "options": [self._model_dict(option) for option in options]}
            loop = asyncio.get_running_loop()
            try:
                chosen = await loop.run_in_executor(None, state.on_permission, request)
            except Exception:
                log.warning("permission policy failed for run %s; refused",
                            state.spec.run_id, exc_info=True)
                chosen = None
            if chosen is not ...:
                answered_by = "mentis"
                selected = next((option for option in options
                                 if chosen is not None and option.option_id == chosen), None)
                if selected is None:
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

    async def _permission_event(self, state: _RunState, tool_call: Any, options: list[Any],
                                selected: Any, answered_by: str) -> None:
        async with state.event_lock:
            await self._emit(state, RunEvent("permission", {
                "tool_call": self._model_dict(tool_call),
                "options": [self._model_dict(option) for option in options],
                "selected_option_id": getattr(selected, "option_id", None),
                "outcome": "selected", "answered_by": answered_by}, time.time()))

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
        locations = getattr(update, "locations", None)
        if locations is not None:
            record["locations"] = [self._model_dict(location) for location in locations]

    @staticmethod
    def _error_from_exception(exc: BaseException) -> tuple[str, str]:
        if isinstance(exc, RequestError):
            if exc.code == -32000:
                return "auth_required", str(exc)
            data = exc.data if isinstance(exc.data, dict) else {}
            mars = data.get("mars") if isinstance(data.get("mars"), dict) else {}
            kind = mars.get("kind")
            return (str(kind) if kind else "backend_error"), str(exc)
        if isinstance(exc, (ConnectionError, BrokenPipeError, EOFError)):
            return "backend_unavailable", str(exc) or type(exc).__name__
        return "backend_unavailable", str(exc) or repr(exc)

    @classmethod
    def _failed_result(cls, spec: RunSpec, started_at: float, exc: BaseException) -> RunResult:
        kind, message = cls._error_from_exception(exc)
        return RunResult(
            run_id=spec.run_id,
            backend=spec.backend,
            started=False,
            error_kind=kind,
            error=message,
            started_at=started_at,
            finished_at=time.time(),
        )


__all__ = ["MarsExecution"]
