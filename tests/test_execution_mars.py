from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import threading
import time

import pytest

from mentis.execution import RunEvent, RunSpec
from mentis.execution.mars import MarsExecution


def _command_from_environment() -> list[str]:
    value = os.environ.get("MENTIS_TEST_MARS")
    if not value:
        pytest.skip("MENTIS_TEST_MARS is not set", allow_module_level=True)
    command = shlex.split(value, posix=os.name != "nt")
    command = [part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part
               for part in command]
    if not command:
        pytest.skip("MENTIS_TEST_MARS is empty", allow_module_level=True)
    executable = command[0]
    if not Path(executable).is_file() and shutil.which(executable) is None:
        pytest.skip(f"MENTIS_TEST_MARS executable is missing: {executable}", allow_module_level=True)
    return command


MARS_COMMAND = _command_from_environment()
FAKE_AGENT = Path(__file__).with_name("fakes") / "mars_acp_agent.py"


@pytest.fixture(scope="module")
def mars_execution(tmp_path_factory):
    root = tmp_path_factory.mktemp("mentis-mars")
    data_dir = root / "data"
    data_dir.mkdir()
    backends_file = root / "backends.json"
    backends_file.write_text(
        json.dumps({
            "backends": [
                {
                    "id": "mentis-test",
                    "command": [sys.executable, str(FAKE_AGENT)],
                    "permissions": "forwarded",
                },
                {
                    "id": "mentis-test-auth",
                    "command": [sys.executable, str(FAKE_AGENT), "--auth"],
                    "permissions": "forwarded",
                },
            ]
        }),
        encoding="utf-8",
    )

    old_data = os.environ.get("MARS_DATA_DIR")
    old_backends = os.environ.get("MARS_BACKENDS_FILE")
    os.environ["MARS_DATA_DIR"] = str(data_dir)
    os.environ["MARS_BACKENDS_FILE"] = str(backends_file)
    execution = MarsExecution(MARS_COMMAND)
    try:
        yield execution
    finally:
        execution.close()
        if old_data is None:
            os.environ.pop("MARS_DATA_DIR", None)
        else:
            os.environ["MARS_DATA_DIR"] = old_data
        if old_backends is None:
            os.environ.pop("MARS_BACKENDS_FILE", None)
        else:
            os.environ["MARS_BACKENDS_FILE"] = old_backends


def _spec(tmp_path: Path, run_id: str, prompt: str, *, backend: str = "mentis-test",
          mcp_servers=()) -> RunSpec:
    return RunSpec(
        run_id=run_id,
        backend=backend,
        workspace=str(tmp_path.resolve()),
        prompt=prompt,
        mcp_servers=tuple(mcp_servers),
    )


def test_catalog_lists_configured_backend(mars_execution):
    catalog = {item["id"]: item for item in mars_execution.backends()}

    assert catalog["mentis-test"]["installed"] is True
    assert catalog["mentis-test"]["available"] is True
    assert catalog["mentis-test"]["supports"]["permissions"] == "forwarded"


def test_capacity_report_names_every_backend(mars_execution):
    """`_mars/capacity` answers for every backend; one that reports nothing has no
    windows and says why (never a zero)."""
    report = mars_execution.capacity()
    entry = report["mentis-test"]
    assert entry["windows"] == [] and entry["notes"]


def test_run_collects_text_tools_usage_and_stop_reason(mars_execution, tmp_path):
    events: list[RunEvent] = []

    result = mars_execution.perform(_spec(tmp_path, "complete", "run"), events.append)

    assert result.started is True
    assert result.stop_reason == "end_turn"
    assert result.error_kind is None
    assert result.text == "hello from fake"
    assert result.usage == {"used": 7, "size": 100}
    assert result.tool_calls == [{
        "id": "tool-1",
        "title": "write result",
        "kind": "edit",
        "status": "completed",
        "locations": [{"path": str(tmp_path / "result.txt"), "line": 3}],
    }]
    assert [event.kind for event in events] == [
        "agent_message_chunk", "tool_call", "tool_call_update", "usage_update"
    ]
    assert events[0].data["text"] == "hello from fake"


def test_permission_is_allowed_once_and_recorded(mars_execution, tmp_path):
    events: list[RunEvent] = []

    result = mars_execution.perform(_spec(tmp_path, "permission", "permission"), events.append)

    assert result.text == "permission:selected:once"
    permissions = [event for event in events if event.kind == "permission"]
    assert len(permissions) == 1
    assert permissions[0].data["selected_option_id"] == "once"
    assert permissions[0].data["outcome"] == "selected"


def test_callback_exception_does_not_break_run(mars_execution, tmp_path):
    def broken_callback(event: RunEvent) -> None:
        raise RuntimeError(f"cannot record {event.kind}")

    result = mars_execution.perform(
        _spec(tmp_path, "broken-callback", "echo still-finished"), broken_callback
    )

    assert result.stop_reason == "end_turn"
    assert result.text == "still-finished"


def test_cancel_running_turn(mars_execution, tmp_path):
    waiting = threading.Event()

    def observe(event: RunEvent) -> None:
        if event.kind == "agent_message_chunk" and event.data.get("text") == "waiting":
            waiting.set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            mars_execution.perform, _spec(tmp_path, "cancel-me", "slow"), observe
        )
        assert waiting.wait(20)
        assert "cancel-me" in mars_execution.running()
        assert mars_execution.cancel("cancel-me") is True
        result = future.result(timeout=20)

    assert result.started is True
    assert result.stop_reason == "cancelled"
    assert mars_execution.cancel("cancel-me") is False


def test_auth_required_is_a_not_started_result(mars_execution, tmp_path):
    result = mars_execution.perform(
        _spec(tmp_path, "auth", "run", backend="mentis-test-auth")
    )

    assert result.started is False
    assert result.session_id is None
    assert result.error_kind == "auth_required"
    assert result.stop_reason is None


def test_mcp_stdio_servers_reach_backend(mars_execution, tmp_path):
    servers = (
        {
            "name": "bridge-one",
            "command": sys.executable,
            "args": ["-c", "pass"],
            "env": [{"name": "ONE", "value": "1"}],
        },
        {
            "name": "bridge-two",
            "command": sys.executable,
            "args": ["-c", "pass"],
            "env": [],
        },
    )

    result = mars_execution.perform(
        _spec(tmp_path, "mcp", "mcp", mcp_servers=servers)
    )

    assert result.stop_reason == "end_turn"
    assert result.text == "bridge-one,bridge-two"


def test_two_runs_share_connection_concurrently(mars_execution, tmp_path):
    first = _spec(tmp_path, "parallel-a", "echo first")
    second = _spec(tmp_path, "parallel-b", "echo second")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(mars_execution.perform, spec) for spec in (first, second)]
        deadline = time.monotonic() + 20
        while len(mars_execution.running()) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert mars_execution.running() == {"parallel-a", "parallel-b"}
        results = [future.result(timeout=20) for future in futures]

    assert [result.text for result in results] == ["first", "second"]
    assert all(result.stop_reason == "end_turn" for result in results)


def test_permission_answered_by_mentis_policy(mars_execution, tmp_path):
    """`on_permission` answers: an option id selects it, None refuses with the
    request's own reject option, `...` leaves the old default."""
    asked: list[dict] = []

    def choose(answer):
        def policy(request):
            asked.append(request)
            return answer
        return policy

    got = mars_execution.perform(_spec(tmp_path, "p-always", "permission"),
                                 on_permission=choose("always"))
    assert got.text == "permission:selected:always"
    assert asked[-1]["tool_call"]["title"] == "run test command"
    assert {o["option_id"] for o in asked[-1]["options"]} == {"once", "always", "no"}
    events: list[RunEvent] = []
    got = mars_execution.perform(_spec(tmp_path, "p-refused", "permission"),
                                 events.append, on_permission=choose(None))
    assert got.text == "permission:selected:no"
    perm = [e for e in events if e.kind == "permission"]
    assert perm[-1].data["answered_by"] == "mentis"
    got = mars_execution.perform(_spec(tmp_path, "p-default", "permission"),
                                 on_permission=choose(...))
    assert got.text == "permission:selected:once"


def test_tooling_is_told_after_the_session_opens(mars_execution, tmp_path):
    """`RunSpec.tooling` is called with what MARS reported for the session
    and its text reaches the agent after the prompt; the result records it."""
    seen = []

    def tooling(meta):
        seen.append(meta)
        return "TOOLING-BLOCK", {"backend": "mentis-test", "reported_by_mars": meta is not None}

    spec = RunSpec(run_id="tooling-1", backend="mentis-test", workspace=str(tmp_path.resolve()),
                   prompt="echo hello", tooling=tooling)
    got = mars_execution.perform(spec)
    assert got.text.startswith("hello") and got.text.endswith("TOOLING-BLOCK")
    assert got.tooling == {"backend": "mentis-test", "reported_by_mars": seen[0] is not None}
    assert len(seen) == 1


def test_a_permission_request_carries_only_verified_shell_facts(mars_execution, tmp_path):
    """Before any shell command ran in the session, its declared cwd; the
    shell only when MARS declared it for the session."""
    asked: list[dict] = []
    mars_execution.perform(_spec(tmp_path, "p-facts", "permission"),
                           on_permission=lambda r: asked.append(r) or ...)
    assert asked[-1]["shell_cwd"] == str(tmp_path.resolve())
    assert asked[-1]["shell"] is None
