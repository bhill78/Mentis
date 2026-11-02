"""What row A, E, F and J share: `PAIR` started as `R1-acceptance.md` says, and the raw tools to look
at it with.

`PAIR` is `$env:MENTIS_UNDER_TEST`, the launcher with `--attached`. With no such variable a row
fails: nothing here skips. Each `{}` is filled per boot, as that document's table says. What a
running pair is doing comes from `launch.json`, which the launcher writes once both answer.

Kills are by `TerminateProcess` and suspensions by `NtSuspendProcess`, on the pid `launch.json`
names. Nothing here reaches into either process.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import pathlib
import socket
import subprocess
import time
from ctypes import wintypes

from tests.front.restart_messages import LIST as RESTART_LIST
from tools.r1 import common, py_alone

#: `R1-acceptance.md`'s ports. `MENTIS_R1_PORTS`, one number, moves all of them together for a run
#: beside another: PY-ALONE on it, PAIR on the next, and the rest are spares for a row's own servers.
_BASE = int(os.environ.get("MENTIS_R1_PORTS") or 0)
PY_PORT = _BASE or py_alone.PORT
PORT = _BASE + 1 if _BASE else 8852
SPARE_PORTS = range(_BASE + 2, _BASE + 8) if _BASE else range(8854, 8860)
#: `contracts/bench.md`'s command that can't exist: no MARS is reachable from this server.
NO_MARS = "workload-no-mars-here"
#: For J6, J7, J16, O and P, by `R1-acceptance.md`.
REAL_MARS = r"C:\Work\MARS-venv\Scripts\mars.exe stdio"
#: Python's own limit and the front's, from `contracts/launcher.md`, plus the launcher's own time.
START_LIMIT_S = 300

CLIENT = {"X-Mentis-Client": "1"}


def _template() -> list[str]:
    text = os.environ.get("MENTIS_UNDER_TEST")
    if not text:
        raise AssertionError("MENTIS_UNDER_TEST isn't set, so there is no PAIR and this row fails")
    return json.loads(text)


# -- processes ----------------------------------------------------------------------------------

_PROCESS_TERMINATE = 0x0001
_PROCESS_SUSPEND_RESUME = 0x0800
_PROCESS_QUERY_LIMITED = 0x1000
_PROCESS_VM_READ = 0x0010
_SYNCHRONIZE = 0x00100000
_STILL_ACTIVE = 259


class _Memory(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    return kernel


@contextlib.contextmanager
def _handle(pid: int, access: int):
    kernel = _kernel()
    handle = kernel.OpenProcess(access, False, pid)
    if not handle:
        raise OSError(f"can't open process {pid}: {ctypes.get_last_error()}")
    try:
        yield kernel, handle
    finally:
        kernel.CloseHandle(handle)


def terminate(pid: int) -> None:
    """A hard kill: no drain, no handler, nothing flushed. A venv's `python.exe` stub that is ending
    because its child was just killed can't be opened, or refuses with error 5. If it then goes, it
    has gone, and that isn't a failure of the kill."""
    try:
        with _handle(pid, _PROCESS_TERMINATE | _SYNCHRONIZE) as (kernel, handle):
            if not kernel.TerminateProcess(handle, 9):
                raise OSError(f"TerminateProcess({pid}): {ctypes.get_last_error()}")
            kernel.WaitForSingleObject(handle, 10_000)
    except OSError:
        if not wait_gone(pid):
            raise


def suspend(pid: int) -> None:
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtSuspendProcess.argtypes = [wintypes.HANDLE]
    with _handle(pid, _PROCESS_SUSPEND_RESUME) as (_, handle):
        status = ntdll.NtSuspendProcess(handle)
        if status:
            raise OSError(f"NtSuspendProcess({pid}): {status:#x}")


def resume(pid: int) -> None:
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    with _handle(pid, _PROCESS_SUSPEND_RESUME) as (_, handle):
        status = ntdll.NtResumeProcess(handle)
        if status:
            raise OSError(f"NtResumeProcess({pid}): {status:#x}")


def alive(pid: int) -> bool:
    kernel = _kernel()
    handle = kernel.OpenProcess(_PROCESS_QUERY_LIMITED, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) \
            and code.value == _STILL_ACTIVE
    finally:
        kernel.CloseHandle(handle)


def memory(pid: int) -> tuple[int, int]:
    """(working set now, its peak), in bytes."""
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Memory),
                                           wintypes.DWORD]
    with _handle(pid, _PROCESS_QUERY_LIMITED | _PROCESS_VM_READ) as (_, handle):
        got = _Memory()
        got.cb = ctypes.sizeof(_Memory)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(got), got.cb):
            raise OSError(f"GetProcessMemoryInfo({pid}): {ctypes.get_last_error()}")
        return got.WorkingSetSize, got.PeakWorkingSetSize


class _Entry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]


def process_tree(pid: int) -> list[int]:
    """`pid` and everything under it, parents first, by the system's own list. A virtual
    environment's `python.exe` is a stub that starts the real one as its child, so the server the
    launcher names is this whole tree."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Entry)]
    kernel.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)
    try:
        parents = {}
        entry = _Entry()
        entry.dwSize = ctypes.sizeof(_Entry)
        more = kernel.Process32First(snapshot, ctypes.byref(entry))
        while more:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            more = kernel.Process32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    tree = [pid]
    for parent in tree:
        tree += [child for child, its in parents.items() if its == parent and child not in tree]
    return [one for one in tree if alive(one)]


def wait_gone(pid: int, limit: float = 10.0) -> bool:
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.05)
    return not alive(pid)


# -- the wire -----------------------------------------------------------------------------------


def exchange(port: int, data: bytes, *, wait: float = 3.0, host: str = "127.0.0.1") -> bytes:
    """Send bytes on a new connection and read until it ends, or until `wait` passes with nothing
    more coming, as on a connection kept open."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(wait)
        sock.connect((host, port))
        sock.sendall(data)
        got = b""
        try:
            while True:
                more = sock.recv(1 << 16)
                if not more:
                    break
                got += more
        except (TimeoutError, ConnectionError):
            pass
        return got


class Answer:
    """An HTTP answer read from raw bytes, with its headers in order, repeats and all."""

    def __init__(self, raw: bytes):
        self.raw = raw
        head, _, self.body = raw.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        self.status_line = lines[0]
        parts = lines[0].split(" ", 2)
        self.status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        self.headers = [tuple(line.split(": ", 1)) for line in lines[1:] if ": " in line]

    def header(self, name: str) -> str | None:
        for key, value in self.headers:
            if key.lower() == name.lower():
                return value
        return None

    @property
    def json(self):
        return json.loads(self.body)

    @property
    def comparable(self) -> tuple:
        """Everything but `Date`, which is a moment."""
        return (self.status_line, [h for h in self.headers if h[0] != "Date"], self.body)

    def __repr__(self) -> str:
        return f"Answer({self.status_line!r}, {self.headers!r}, {self.body[:300]!r})"


def request(method: str, path: str, *, headers: dict | None = None, body: bytes = b"",
            host: str | None = "localhost", close: bool = True) -> bytes:
    """A request's bytes, with nothing added but what is named."""
    lines = [f"{method} {path} HTTP/1.1"]
    if host is not None:
        lines.append(f"Host: {host}")
    for name, value in (headers or {}).items():
        lines.append(f"{name}: {value}")
    if body:
        lines.append(f"Content-Length: {len(body)}")
    if close:
        lines.append("Connection: close")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body


def ask(port: int, method: str, path: str, **kw) -> Answer:
    wait = kw.pop("wait", 30.0)
    return Answer(exchange(port, request(method, path, **kw), wait=wait))


def post_json(port: int, path: str, doc, headers: dict | None = None, wait: float = 30.0) -> Answer:
    return ask(port, "POST", path, body=json.dumps(doc).encode(),
               headers={"Content-Type": "application/json", **(headers or {})}, wait=wait)


def non_loopback_address() -> str:
    """An address of this machine that isn't loopback. A connection made to it from here has it as
    its peer, so a server listening on it sees a peer that isn't loopback."""
    found = [a for a in socket.gethostbyname_ex(socket.gethostname())[2]
             if not a.startswith("127.") and not a.startswith("169.254.")]
    if not found:
        raise AssertionError("this machine has no address but loopback, so the row can't run")
    return found[0]


def rows(brain, sql: str, *args) -> list:
    """Read a Brain copy's record, read only."""
    import sqlite3
    db = (pathlib.Path(brain) / "corpus.db").as_posix()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def advance(brain) -> tuple[int, int, int]:
    """`Store.advance`, the record's position."""
    return tuple(rows(brain, "SELECT (SELECT COALESCE(MAX(seq),0) FROM entry), "
                             "(SELECT COALESCE(MAX(seq),0) FROM operational), "
                             "(SELECT COALESCE(MAX(seq),0) FROM delivery)")[0])


def conversation_named(brain, name: str) -> str:
    found = rows(brain, "SELECT id FROM entry WHERE def_name='conversation' "
                        "AND json_extract(body,'$.name')=?", name)
    if not found:
        raise AssertionError(f"no Conversation named {name!r} in {brain}")
    return found[0][0]


# -- the pair -----------------------------------------------------------------------------------


class Pair:
    """`PAIR` on one Brain copy."""

    def __init__(self, brain, *, port: int = PORT, mars: str = NO_MARS,
                 route_table=None, upstream: str | None = None, dist=None,
                 env: dict | None = None):
        self.brain = pathlib.Path(brain)
        self.port = port
        self.run_dir = self.brain.parent / f"{self.brain.name}.run"
        self.workspace = self.run_dir / "ws"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.mars = mars
        self.route_table = route_table
        self.upstream = upstream
        self.dist = dist
        self.extra_env = env or {}
        self.launcher: subprocess.Popen | None = None
        self.started_pids: set[int] = set()

    def _fill(self, words: list[str]) -> list[str]:
        values = {"{brain}": str(self.brain), "{port}": str(self.port),
                  "{ws}": str(self.workspace), "{run}": str(self.run_dir), "{mars}": self.mars}
        out = []
        for word in words:
            for name, value in values.items():
                word = word.replace(name, value)
            out.append(word)
        if self.dist is not None:
            out[out.index("--dist") + 1] = str(self.dist)
        if self.route_table is not None:
            out += ["--route-table", str(self.route_table)]
        return out

    def _environment(self) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.upper().startswith("MENTIS") and k.upper() != "PYTHONPATH"}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", **self.extra_env)
        return env

    @property
    def state_file(self) -> pathlib.Path:
        return self.run_dir / "launch.json"

    @property
    def state(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    @property
    def front_pid(self) -> int:
        return self.state["front"]["pid"]

    @property
    def python_pid(self) -> int:
        return self.state["python"]["pid"]

    @property
    def private_port(self) -> int:
        return self.state["private_port"]

    @property
    def secret(self) -> str:
        return self.state["secret"]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def front_log(self) -> pathlib.Path:
        return self.run_dir / "front.log"

    def answers(self, port: int | None = None) -> bool:
        try:
            return ask(port or self.port, "GET", "/api/server", wait=5.0).status == 200
        except OSError:
            return False

    def _wait_for_state(self, before: float | None, launcher, port: int | None = None) -> None:
        deadline = time.monotonic() + START_LIMIT_S
        while True:
            fresh = self.state_file.exists() and (
                before is None or self.state_file.stat().st_mtime_ns != before)
            if fresh and self.answers(port):
                self.started_pids |= {self.front_pid, self.python_pid}
                return
            code = launcher.poll()
            if code not in (None, 0):
                raise AssertionError(f"the launcher exited {code}; see {self.run_dir}")
            if time.monotonic() > deadline:
                raise AssertionError(f"PAIR did not answer within {START_LIMIT_S} s")
            time.sleep(0.1)

    def start(self) -> Pair:
        if self.brain.resolve() == common.master_dir().resolve():
            raise SystemExit("PAIR runs on a fresh copy, never on the master")
        words = self._fill(_template())
        if self.upstream:
            words += ["--upstream", self.upstream]
        with open(self.run_dir / "launcher.log", "ab") as log:
            self.launcher = subprocess.Popen(words, cwd=self.run_dir, env=self._environment(),
                                             stdout=log, stderr=subprocess.STDOUT)
        self._wait_for_state(None, self.launcher)
        return self

    def _only(self, side: str, extra: list[str]) -> None:
        words = [w for w in self._fill(_template()) if w != "--attached"]
        before = self.state_file.stat().st_mtime_ns
        with open(self.run_dir / "launcher.log", "ab") as log:
            launcher = subprocess.Popen(words + ["--only", side] + extra, cwd=self.run_dir,
                                        env=self._environment(), stdout=log,
                                        stderr=subprocess.STDOUT)
        # A new Python may have no front before it yet, so it is asked on its own port.
        self._wait_for_state(before, launcher, self.private_port if side == "python" else None)
        launcher.wait(timeout=START_LIMIT_S)

    def restart_front(self, upstream: str | None = None) -> None:
        """A new front on the same secret and ports. Python isn't touched. `--upstream` is not
        remembered, so J6 and J7 give it again here (`contracts/launcher.md`)."""
        self._only("front", ["--upstream", upstream] if upstream else [])

    def restart_python(self) -> None:
        self._only("python", [])

    def stop_front(self) -> Answer:
        """`POST /private/stop` with the secret, as `mentis-launch stop --front` sends it."""
        return ask(self.port, "POST", "/private/stop", headers={"X-Mentis-Boot-Secret": self.secret,
                                                                "Content-Length": "0"})

    @contextlib.contextmanager
    def second_front(self, host: str, port: int):
        """Another front on this pair's Python, by the launcher's step 4 and this boot's secret.

        What a test needs a peer that isn't loopback for. `answers_at`, which the picker reads,
        must stay loopback, so the launcher's own front must be on loopback, and from loopback
        Windows only ever shows a loopback peer."""
        dist = self._fill(_template())
        command = [self.state["front"]["executable"], str(self.brain), "--host", host,
                   "--port", str(port), "--upstream", f"http://127.0.0.1:{self.private_port}",
                   "--dist", dist[dist.index("--dist") + 1]]
        with open(self.run_dir / "second-front.log", "ab") as log:
            front = subprocess.Popen(command, env={**self._environment(),
                                                   "MENTIS_BOOT_SECRET": self.secret},
                                     stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    if Answer(exchange(port, request("GET", "/api/server"), host=host,
                                       wait=5.0)).status == 200:
                        break
                except OSError:
                    pass
                assert front.poll() is None and time.monotonic() < deadline, \
                    f"that front didn't start; see {self.run_dir}"
                time.sleep(0.05)
            yield front
        finally:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(front.pid)], capture_output=True,
                           check=False)
            front.wait(timeout=30)

    def kill_front(self) -> None:
        terminate(self.front_pid)

    def kill_python(self) -> None:
        # The real server first, so it dies by the kill and not by anything its parent does.
        for pid in reversed(process_tree(self.python_pid)):
            terminate(pid)

    def suspend_python(self) -> None:
        for pid in process_tree(self.python_pid):
            suspend(pid)

    def resume_python(self) -> None:
        for pid in process_tree(self.python_pid):
            resume(pid)

    def close(self) -> None:
        """Everything this pair ever started, gone."""
        pids = set(self.started_pids)
        if self.state_file.exists():
            with contextlib.suppress(ValueError, KeyError):
                pids |= {self.front_pid, self.python_pid}
        if self.launcher is not None:
            pids.add(self.launcher.pid)
        for pid in pids:
            if alive(pid):
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True,
                               check=False)
        if self.launcher is not None:
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.launcher.wait(timeout=30)

    def __enter__(self) -> Pair:
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()


# -- an agent's call ----------------------------------------------------------------------------


def session_grant(url_port: int) -> dict:
    """A hand-started session's grant, by the route a bridge uses."""
    got = post_json(url_port, "/api/worker/session", {"runtime": "claude"}, CLIENT)
    assert got.status == 200, got
    return got.json


def told(url: str, brain, name: str, args: dict, grant: str) -> tuple[dict | None, str | None]:
    """One call by the real worker transport (`_over`), and what the agent would be told: the answer,
    or the message `serve`'s catch-all would make of what was raised. That catch-all's shape is
    `{type}: {message}`, and it's the only thing `decide` sees."""
    from mentis.worker import _over
    try:
        return _over(url, str(brain), name, args, grant), None
    except Exception as exc:  # noqa: BLE001  the catch-all this stands for
        return None, f"{type(exc).__name__}: {exc}"


FRONT_503 = RESTART_LIST["front_503_error"]
