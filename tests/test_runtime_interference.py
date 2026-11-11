"""A run whose runtime was terminated by a command that kills processes BY NAME is recorded
as such: the command, who ran it, and what that means for a retry
(`mentis.execution.interference`; DAY-TO-DAY incident 2026-11-11, ent-e05dcf622c97).
MARS's exit code and stderr tail reach the record."""

from __future__ import annotations

import json
import time

import pytest

from mentis.execution import RunResult, RunSpec
from mentis.execution import interference as I
from mentis.execution.mars import MarsExecution
from tests._loop import a_conversation, say, world  # noqa: F401


# -- which commands kill by name --------------------------------------------------------


@pytest.mark.parametrize("command, names", [
    ("taskkill //F //IM node.exe //T 2>&1 | tail -5", ["node"]),            # the 15:57 command
    ("powershell -NoProfile -Command \"Get-Process node -ErrorAction SilentlyContinue"
     " | Stop-Process -Force\" 2>&1", ["node"]),                             # the 16:11 command
    ("taskkill /F /IM node.exe /IM python.exe", ["node", "python"]),
    ("Stop-Process -Name node,python -Force", ["node", "python"]),
    ("Get-Process -Name python | % { $_.Kill() }", ["python"]),
    ("pkill node", ["node"]),
    ("killall -9 node", ["node"]),
    ("wmic process where name='node.exe' delete", ["node"]),
    ("Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | Invoke-CimMethod -MethodName Terminate",
     ["node"]),
    ("taskkill /IM node*", ["node*"]),
])
def test_commands_that_kill_by_name_are_read(command, names):
    assert I.killed_names(command) == names


@pytest.mark.parametrize("command", [
    "taskkill /F /T /PID 4242",                # owned: by pid
    "Stop-Process -Id 4242 -Force",
    "kill $(cat /c/tmp/vite.pid)",
    "npm run dev -- --port 5183",
    "Get-Process node | Select-Object Id,Path",  # a read, not a kill
    "",
])
def test_stopping_by_pid_or_reading_is_not_a_kill_by_name(command):
    assert I.killed_names(command) == []


def test_a_name_matches_only_the_runtimes_that_have_it():
    assert I.hits_runtime(["node"], "claude") == ["node"]
    assert I.hits_runtime(["node"], "local") == []
    assert I.hits_runtime(["python"], "local") == ["python"]
    assert I.hits_runtime(["node*"], "codex") == ["node*"]
    assert I.hits_runtime(["node"], "a-runtime-nobody-listed") == []


# -- finding the command in the record (shaped as DAY-TO-DAY recorded it) ----------------


class _Reader:
    def __init__(self, rows):
        self.rows = rows

    def acts(self, where, args=()):
        lo = args[0]
        return [r for r in self.rows if r["act"] in ("operations-observed", "operation-answered")
                and r["at"] >= lo]


T = 1_794_430_650.0
KILLER, VICTIM = "ecda92c2-killer", "e4e1bf6d-victim"
OBSERVED = {"id": "opr-obs", "act": "operations-observed", "at": T + 0.01, "execution": KILLER,
            "runtime": "claude", "actor": "ent-builder",
            "detail": json.dumps({"batch": 84, "calls": [
                {"first_at": T - 1.5, "id": "toolu_1", "kind": "execute", "status": "pending",
                 "title": "taskkill //F //IM node.exe //T 2>&1 | tail -5"}]})}


def test_another_runs_kill_by_name_is_found_for_the_victim():
    got = I.find(_Reader([OBSERVED]), execution=VICTIM, runtime="claude", ended_at=T)
    assert got["execution"] == KILLER and got["self"] is False and got["names"] == ["node"]
    assert got["seconds_before_exit"] == 1.5 and got["actor"] == "ent-builder"
    said = I.words(got, alias="@Builder")
    assert "possibly ended by another run's command: @Builder ran" in said
    assert "not its effect" in said and "Nothing recorded says this work failed on its own" in said


def test_a_run_that_killed_its_own_runtime_is_told_so():
    got = I.find(_Reader([OBSERVED]), execution=KILLER, runtime="claude", ended_at=T)
    assert got["self"] is True
    said = I.words(got)
    assert said.startswith("likely ended by its own command") and "not its effect" in said and "by pid" in said


def test_its_own_last_call_counts_before_anything_is_recorded():
    calls = [{"id": "t", "title": "Get-Process node | Stop-Process -Force", "status": "pending"}]
    got = I.find(_Reader([]), execution=KILLER, runtime="claude", ended_at=T, own_calls=calls)
    assert got["self"] is True and got["names"] == ["node"]


@pytest.mark.parametrize("why, kwargs", [
    ("too long before the exit", {"ended_at": T + 120}),
    ("a runtime without that process name", {"runtime": "local"}),
])
def test_nothing_is_inferred_without_a_matching_recent_command(why, kwargs):
    args = {"execution": VICTIM, "runtime": "claude", "ended_at": T, **kwargs}
    assert I.find(_Reader([OBSERVED]), **args) is None, why


def test_an_exit_alone_is_never_attributed():
    assert I.find(_Reader([]), execution=VICTIM, runtime="claude", ended_at=T) is None


# -- what MARS reports reaches the run ---------------------------------------------------


def test_the_runtimes_exit_code_and_stderr_are_kept():
    from acp import RequestError
    spec = RunSpec(run_id="r1", backend="claude", prompt="x", workspace=".")
    exc = RequestError(-32603, "backend 'claude' exited with code 1", {"mars": {
        "kind": "backend_exited", "exitCode": 1,
        "stderrTail": "fatal: something broke\napi_key=sk-ant-SECRETSECRETSECRET"}})
    res = MarsExecution._failed_result(spec, 0.0, exc)
    assert res.error_kind == "backend_exited" and res.backend_exit_code == 1
    assert "something broke" in res.stderr_tail
    assert "SECRETSECRETSECRET" not in res.stderr_tail, "stderr is redacted before it is kept"
    assert MarsExecution._death({}) == (None, None)
    assert MarsExecution._death({"exitCode": True, "stderrTail": "  "}) == (None, None)


# -- through dispatch: the failure record ------------------------------------------------


def test_a_failed_run_records_the_exit_code_stderr_and_who_ended_it(world, monkeypatch):
    import mentis.web as web
    from mentis.web import dispatch as D
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: D.dispatch(st, **kw))
    st, cv = world["state"], world["cv"]

    def killed(spec):
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         error_kind="backend_exited",
                         error="backend 'claude' exited with code 1",
                         backend_exit_code=1, stderr_tail="the last line it wrote",
                         tool_calls=[{"id": "t", "title": "taskkill /F /IM node.exe /T",
                                      "kind": "execute", "status": "pending"}],
                         started_at=now, finished_at=now)

    st.agents.execution.script = {"claude": killed}
    ada = cv.create_participant("@Ada", about="an agent")
    cid = a_conversation(world)
    say(world, cid, "start vite, then stop it", action="ask-participant",
        dispatch=[{"participant": ada, "work": "start vite, then stop it", "runtime": "claude"}])
    spec = st.agents.execution.performed[-1]
    started = [a for a in cv.history(execution=spec.run_id) if a["act"] == "execution-started"]
    end = cv.run_end(started[-1]["id"])
    assert end["act"] == "delivery-failed"
    assert end["detail"]["exit_code"] == 1
    assert end["detail"]["runtime_evidence"]["stderr_tail"] == "the last line it wrote"
    by = end["detail"]["terminated_by"]
    assert by["self"] is True and by["names"] == ["node"]
    assert "likely ended by its own command: it was running `taskkill /F /IM node.exe /T`" in end["because"]


def test_every_run_is_told_to_stop_only_its_own_processes_by_pid():
    from mentis.execution import tooling
    for backend in ("claude", "codex", "antigravity"):
        said = tooling.render({"backend": backend, "workspace": "C:/w"})
        assert tooling.PROCESS_OWNERSHIP in said
    assert "by their pid" in tooling.PROCESS_OWNERSHIP and "`taskkill /IM`" in tooling.PROCESS_OWNERSHIP


# -- review findings (2026-11-11): redaction, and nothing claimed on timing alone ---------


def test_a_command_written_to_the_record_is_redacted():
    calls = [{"id": "t", "status": "pending",
              "title": 'taskkill /F /IM node.exe & curl -H "Authorization: Bearer sk-ant-SECRETSECRETSECRET" x'}]
    got = I.find(_Reader([]), execution=KILLER, runtime="claude", ended_at=T, own_calls=calls)
    assert got and "SECRETSECRETSECRET" not in got["command"]


def test_a_filtered_pipeline_stops_what_it_chose_and_is_not_a_kill_by_name():
    assert I.killed_names("Get-Process node | Where-Object Id -eq 1234 | Stop-Process") == []
    assert I.killed_names("Get-Process node | ? { $_.Path -like '*vite*' } | Stop-Process") == []


def test_only_a_call_still_running_at_the_end_is_its_own_last_act():
    done = [{"id": "a", "title": "Get-Process node | Stop-Process -Force", "status": "completed"},
            {"id": "b", "title": "npm test", "status": "completed"}]
    assert I.find(_Reader([]), execution=KILLER, runtime="claude", ended_at=T, own_calls=done) is None
    old = [{"id": "a", "title": "taskkill /F /IM node.exe", "status": "pending"}] + [
        {"id": str(i), "title": "ls", "status": "completed"} for i in range(5)]
    assert I.find(_Reader([]), execution=KILLER, runtime="claude", ended_at=T, own_calls=old) is None


def test_a_failed_or_refused_command_ended_nothing():
    failed = dict(OBSERVED, detail=json.dumps({"calls": [
        {"first_at": T - 1, "status": "failed", "title": "taskkill /F /IM node.exe"}]}))
    assert I.find(_Reader([failed]), execution=VICTIM, runtime="claude", ended_at=T) is None
    refused = {"id": "opr-ans", "act": "operation-answered", "at": T - 1, "execution": KILLER,
               "runtime": "claude", "actor": "ent-builder",
               "detail": json.dumps({"answer": "refused", "operation": {"command": "taskkill /F /IM node.exe"}})}
    assert I.find(_Reader([refused]), execution=VICTIM, runtime="claude", ended_at=T) is None
    allowed = dict(refused, detail=json.dumps({"answer": "allowed", "operation": {"command": "taskkill /F /IM node.exe"}}))
    assert I.find(_Reader([allowed]), execution=VICTIM, runtime="claude", ended_at=T)["act"] == "opr-ans"
