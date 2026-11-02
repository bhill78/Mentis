"""PAIR, as `docs/rust/R1-acceptance.md` defines it: `$env:MENTIS_UNDER_TEST` with its five `{}`
filled per boot, on a fresh copy. For P1.5-PAIR and rows O and P. Never the live Brain, never 8760.

Also what a test asks of a running server: reads, a new post, and a real agent run on MARS.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import pathlib
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

from tools.r1 import common, py_alone

#: `R1-acceptance.md`'s ports, in `tests/front/pair.py`'s layout on P1.2's branch, and to go with
#: this file at the integration. `MENTIS_R1_PORTS`, one number, moves all of them together for a run
#: beside another: PY-ALONE on it, PAIR on the next, and the rest are spares.
_BASE = int(os.environ.get("MENTIS_R1_PORTS") or 0)
PY_PORT = _BASE or py_alone.PORT
PORT = _BASE + 1 if _BASE else 8852
PRIVATE_PORT = PORT + 10000
SPARE_PORTS = range(_BASE + 2, _BASE + 8) if _BASE else range(8854, 8860)
NO_MARS = "workload-no-mars-here"
REAL_MARS = r"C:\Work\MARS-venv\Scripts\mars.exe stdio"
START_LIMIT_S = 240
#: Row P4's and O3's run. Named so a capable, logged-in runtime is what's asked for.
RUNTIME = os.environ.get("MENTIS_R1_RUNTIME", "claude")
RUN_LIMIT_S = 300


def under_test() -> list[str]:
    """The command the document's PAIR section sets. Without it the row can't run, and fails."""
    text = os.environ.get("MENTIS_UNDER_TEST")
    if not text:
        pytest.fail("MENTIS_UNDER_TEST isn't set: see docs/rust/R1-acceptance.md, PAIR")
    return json.loads(text)


def fill(command: list[str], *, brain, port: int, run_dir, mars: str) -> list[str]:
    if port == 8760:
        raise SystemExit("8760 is DAY-TO-DAY")
    if pathlib.Path(brain).resolve() == common.master_dir().resolve():
        raise SystemExit("PAIR runs on a fresh copy, never on the master")
    workspace = pathlib.Path(run_dir) / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    values = {"{brain}": str(brain), "{port}": str(port), "{ws}": str(workspace),
              "{mars}": mars, "{run}": str(run_dir)}
    return [values.get(word, word) for word in command]


def environment(mars: str) -> dict:
    """As PY-ALONE's, with what the real MARS needs when a row uses it."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("MENTIS")}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    env.pop("PYTHONPATH", None)
    if mars == REAL_MARS:
        env["MARS_BACKENDS_FILE"] = str(
            pathlib.Path(os.environ["LOCALAPPDATA"]) / "mars" / "backends.json")
    return env


def option(command: list[str], flag: str) -> str:
    return command[command.index(flag) + 1]


def run_dir_of(brain) -> pathlib.Path:
    brain = pathlib.Path(brain)
    return brain.parent / f"{brain.name}.run"


def provenance(command: list[str]) -> dict:
    """What's recorded with each run: the commit, and both binaries' digests."""
    launcher = pathlib.Path(command[0])
    front = launcher.with_name("mentis-server.exe")
    code = option(command, "--code")
    return {"commit": common.head_of(code), "code": code,
            "binaries": {p.name: {"path": str(p), "sha256": common.sha256_file(p)}
                         for p in (launcher, front)}}


def get(port: int, path: str, *, timeout: float = 15.0, client: bool = True) -> tuple[int, bytes]:
    headers = {"X-Mentis-Client": "1"} if client else {}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return fh.status, fh.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def get_json(port: int, path: str, **kw) -> dict:
    status, body = get(port, path, **kw)
    assert status == 200, (path, status, body[:400])
    return json.loads(body)


def post_json(port: int, path: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"X-Mentis-Client": "1",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as fh:
            return fh.status, json.loads(fh.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def wait_for_pulse(port: int, proc: subprocess.Popen | None = None) -> None:
    deadline = time.monotonic() + START_LIMIT_S
    while True:
        if proc is not None and proc.poll() is not None:
            raise AssertionError(f"the launcher exited {proc.returncode}")
        try:
            if get(port, "/api/pulse", timeout=2.0)[0] == 200:
                return
        except OSError:
            pass
        assert time.monotonic() < deadline, f"nothing answered on {port}"
        time.sleep(0.2)


def wait_for_state(run, proc: subprocess.Popen) -> None:
    """`launch.json`, which the launcher writes after both answer: a pulse can come before it."""
    state = pathlib.Path(run) / "launch.json"
    deadline = time.monotonic() + START_LIMIT_S
    while not state.exists():
        if proc.poll() is not None:
            raise AssertionError(f"the launcher exited {proc.returncode}")
        assert time.monotonic() < deadline, f"no {state} in {START_LIMIT_S} s"
        time.sleep(0.05)


def kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


def process_exists(pid: int) -> bool:
    found = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True,
                           text=True).stdout
    return str(pid) in found.split()


def descendants(pid: int) -> set[int]:
    """Every process under `pid`, by the system's own parent records."""
    said = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | ForEach-Object "
         "{ \"$($_.ProcessId) $($_.ParentProcessId)\" }"],
        capture_output=True, text=True, check=True).stdout
    children: dict[int, list[int]] = {}
    for line in said.splitlines():
        if line.strip():
            child, parent = map(int, line.split())
            children.setdefault(parent, []).append(child)
    out, queue = set(), [pid]
    while queue:
        for child in children.get(queue.pop(), ()):
            if child not in out:
                out.add(child)
                queue.append(child)
    return out


def port_free(port: int) -> bool:
    import socket
    try:
        socket.create_server(("127.0.0.1", port)).close()
        return True
    except OSError:
        return False


def wait_port_free(port: int, limit: float = 30.0) -> None:
    deadline = time.monotonic() + limit
    while not port_free(port):
        assert time.monotonic() < deadline, f"port {port} is still held"
        time.sleep(0.2)


@contextlib.contextmanager
def running(brain, *, port: int = PORT, mars: str = NO_MARS, extra=()):
    """PAIR on `brain`, `--attached`, answering, until the block ends and its tree is killed.
    Yields the launcher's process, its filled command, and `<copy>.run`."""
    run = run_dir_of(brain)
    run.mkdir(parents=True, exist_ok=True)
    command = [*fill(under_test(), brain=brain, port=port, run_dir=run, mars=mars), *extra]
    assert "--attached" in command, "the document's command runs the launcher attached"
    (run / "provenance.json").write_text(json.dumps(provenance(command), indent=1),
                                         encoding="utf-8")
    with open(run / "server.log", "ab") as log:
        proc = subprocess.Popen(command, env=environment(mars), cwd=run, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT)
    try:
        wait_for_pulse(port, proc)
        wait_for_state(run, proc)
        yield proc, command, run
    finally:
        kill_tree(proc.pid)
        proc.wait(timeout=30)


def launch_detached(brain, *, port: int = PORT, mars: str = REAL_MARS, extra=()) -> subprocess.CompletedProcess:
    """The launcher as a person runs it: it exits 0, with both processes left running."""
    run = run_dir_of(brain)
    run.mkdir(parents=True, exist_ok=True)
    command = fill(under_test(), brain=brain, port=port, run_dir=run, mars=mars)
    command = [word for word in command if word != "--attached"] + list(extra)
    return subprocess.run(command, env=environment(mars), cwd=run, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=START_LIMIT_S + 60)


def launch_state(run) -> dict:
    return json.loads((pathlib.Path(run) / "launch.json").read_text(encoding="utf-8"))


def powershell(script: pathlib.Path, *args: str, answer: str = "", env=None, timeout: float = 300):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(script), *args], capture_output=True, text=True, input=answer,
                          env=env, timeout=timeout)


# -- what a test asks of a running server --------------------------------------

def participant(port: int, alias: str) -> str:
    rows = get_json(port, "/api/participants?q=" + urllib.parse.quote(alias))["participants"]
    return next(row["participant"] for row in rows if row["alias"] == alias)


def owner_of_copy(port: int) -> str:
    """BRAIN-COPY's owner, by the alias that Brain has always had. BRAIN-SEED's is `@r1-owner`."""
    return participant(port, "@brian")


def conversation_named(port: int, name: str) -> str:
    rows = get_json(port, "/api/conversations")["conversations"]
    return next(row["id"] for row in rows if row["name"] == name)


def ask_agent(port: int, conversation: str, author: str, carrier: str, work: str) -> dict:
    """A post addressing `carrier`, which dispatches a real run. Returns the route's answer."""
    status, out = post_json(port, f"/api/conversations/{conversation}/turns", {
        "author": author, "text": work, "action": "ask-participant",
        "dispatch": [{"participant": carrier, "work": work, "runtime": RUNTIME,
                      "new_instance": True, "difficulty": "ordinary"}]})
    assert status == 200 and out.get("expectations"), (status, out)
    return out


def wait_for_run(port: int, conversation: str, turn: str, limit: float = 120.0) -> str:
    """The id of the run started for `turn`, once the server has opened it."""
    deadline = time.monotonic() + limit
    while True:
        activity = get_json(port, "/fluid/api/home/activity?limit=64")
        ids = activity["items"][:activity["open"]]
        if ids:
            for run in get_json(port, "/fluid/api/runs?ids=" + ",".join(ids))["runs"]:
                if run.get("post") == turn:
                    return run["id"]
        assert time.monotonic() < deadline, f"no run opened for {turn} in {conversation}"
        time.sleep(0.5)


def wait_for_run_end(port: int, run: str, limit: float = RUN_LIMIT_S) -> dict:
    """What the record says of the run once it has ended."""
    deadline = time.monotonic() + limit
    while True:
        said = get_json(port, f"/fluid/api/runs?ids={run}")["runs"][0]
        if said.get("ended_at"):
            return said
        assert time.monotonic() < deadline, f"run {run} hadn't ended in {limit} s: {said}"
        time.sleep(2)


def listener_pid(port: int) -> int:
    said = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Get-NetTCPConnection -LocalPort {port} -State Listen).OwningProcess"],
        capture_output=True, text=True, check=True).stdout.split()
    assert said, f"nothing listens on {port}"
    return int(said[0])


class Suspended:
    """The whole of a process, by NtSuspendProcess, so what still answers isn't that process."""

    def __init__(self, pid: int):
        self.handle = ctypes.windll.kernel32.OpenProcess(0x0800, False, pid)
        assert self.handle, f"can't suspend {pid}"
        self.ntdll = ctypes.windll.ntdll

    def __enter__(self):
        assert self.ntdll.NtSuspendProcess(self.handle) == 0
        return self

    def __exit__(self, *exc):
        assert self.ntdll.NtResumeProcess(self.handle) == 0
        ctypes.windll.kernel32.CloseHandle(self.handle)


def answers_without_python(port: int, path: str) -> bool:
    """Whether `path` answers with Python stopped, which is whether the front itself owns it."""
    with Suspended(listener_pid(port + 10000)):
        try:
            return get(port, path, timeout=3.0)[0] == 200
        except OSError:
            return False
