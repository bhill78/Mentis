"""What the mirror's tests share: real Pythons and a real front on a copy of BRAIN-SEED, and the raw
tools to look at them with. `docs/rust/R3-mirror.md`, section 8.

`MENTIS_R3_FRONT` names the front under test, a build with the `tail-probe` feature, or for a
negative control a build that gets the barrier wrong. Not being told one is a failure, never a skip.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import threading
import time

from tests.front import pair

REPO = pathlib.Path(__file__).resolve().parents[2]
SECRET = "a secret for this test alone"
#: `ROUNDS_FAST`: long enough for a start on a seed Brain, on a loaded machine.
START_LIMIT_S = 120


def front_exe() -> str:
    named = os.environ.get("MENTIS_R3_FRONT")
    assert named, "MENTIS_R3_FRONT isn't set, so there is no front under test and this fails"
    return named


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


def qpc() -> int:
    now = ctypes.c_longlong()
    ctypes.windll.kernel32.QueryPerformanceCounter(ctypes.byref(now))
    return now.value


def environment(secret: str | None = SECRET) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("MENTIS")}
    env.pop("PYTHONPATH", None)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    if secret:
        env["MENTIS_BOOT_SECRET"] = secret
    return env


def wait_until(what, *, limit: float = START_LIMIT_S, message: str = "") -> None:
    deadline = time.monotonic() + limit
    while not what():
        assert time.monotonic() < deadline, message or f"not within {limit} s"
        time.sleep(0.005)


def http(port: int, method: str, path: str, body: dict | None = None,
         headers: dict | None = None, timeout: float = 60.0) -> tuple[int, bytes]:
    """One request on a new connection, read to the end of its `Content-Length`."""
    data = json.dumps(body).encode() if body is not None else b""
    lines = [f"{method} {path} HTTP/1.1", f"Host: 127.0.0.1:{port}", "Connection: close",
             f"Content-Length: {len(data)}"]
    if body is not None:
        lines.append("Content-Type: application/json")
    lines += [f"{name}: {value}" for name, value in (headers or {}).items()]
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
        sock.sendall("\r\n".join(lines).encode("latin-1") + b"\r\n\r\n" + data)
        return read_answer(sock)


def read_answer(sock: socket.socket) -> tuple[int, bytes]:
    """`(status, body)`. A body short of `Content-Length` raises `Short`, saying how far it got."""
    got = b""
    while b"\r\n\r\n" not in got:
        try:
            more = sock.recv(1 << 20)
        except OSError as error:
            raise Short(got, None) from error
        if not more:
            raise Short(got, None)
        got += more
    head, _, body = got.partition(b"\r\n\r\n")
    status = int(head.split(b" ")[1])
    length = None
    for line in head.split(b"\r\n")[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            length = int(value)
    while length is not None and len(body) < length:
        try:
            more = sock.recv(1 << 20)
        except OSError as error:
            raise Short(body, length) from error
        if not more:
            raise Short(body, length)
        body += more
    return status, body


class Short(Exception):
    def __init__(self, got: bytes, length: int | None):
        super().__init__(f"{len(got)} bytes of {length}")
        self.got, self.length = got, length


def worker_request(port: int, token: str, op: str = "capabilities",
                   args: dict | None = None) -> bytes:
    body = json.dumps({"op": op, "args": args or {}}).encode()
    return (f"POST /api/worker HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
            f"X-Mentis-Client: 1\r\nX-Mentis-Worker: {token}\r\nConnection: close\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n"
            ).encode("latin-1") + body


def read_as(port: int, token: str, op: str = "capabilities", args: dict | None = None,
            timeout: float = 60.0) -> tuple[int, bytes]:
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
        sock.sendall(worker_request(port, token, op, args))
        return read_answer(sock)


class ServerPython:
    """`mirror_python.py`, a real server. A venv's `python.exe` is a stub, so the pid here is the one
    the interpreter says, and that is what a kill or a watch has to be on."""

    def __init__(self, brain, port, *, control, answers_at=None, secret=SECRET, code=REPO,
                 claim_wait=None, die_at=None, pause_at=None, wait_for_go=False):
        self.brain, self.port, self.control = pathlib.Path(brain), port, pathlib.Path(control)
        self.control.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, str(REPO / "tests" / "front" / "mirror_python.py"), str(brain),
                   "--port", str(port), "--control", str(control), "--code", str(code),
                   "--workspace", str(self.control)]
        if answers_at:
            command += ["--answers-at", answers_at]
        if claim_wait is not None:
            command += ["--claim-wait", str(claim_wait)]
        if die_at:
            command += ["--die-at", die_at]
        if pause_at:
            command += ["--pause-at", pause_at]
        if wait_for_go:
            command += ["--wait-for-go"]
        self.log = self.control / "server.log"
        with open(self.log, "ab") as log:
            self.process = subprocess.Popen(command, cwd=str(code), env=environment(secret),
                                            stdout=log, stderr=subprocess.STDOUT)

    def has(self, name: str) -> bool:
        return (self.control / name).exists()

    def read(self, name: str) -> str:
        return (self.control / name).read_text(encoding="utf-8")

    def tell(self, name: str, text: str = "") -> None:
        temporary = self.control / f"{name}.tmp"
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(self.control / name)

    @property
    def pid(self) -> int:
        wait_until(lambda: self.has("pid"), message="it never said its pid")
        return int(self.read("pid"))

    def steps(self) -> dict[str, int]:
        if not self.has("steps.jsonl"):
            return {}
        out = {}
        for line in self.read("steps.jsonl").splitlines():
            if line.endswith("}"):
                seen = json.loads(line)
                out[seen["step"]] = seen["at"]
        return out

    def wait_imported(self) -> None:
        wait_until(lambda: self.has("imported"), message="it never finished importing")

    def go(self) -> None:
        self.tell("go")

    def answering(self) -> bool:
        try:
            return http(self.port, "GET", "/api/server", timeout=2.0)[0] == 200
        except OSError:
            return False

    def wait_answering(self) -> None:
        def up():
            assert self.process.poll() is None, self.log.read_text(errors="replace")
            return self.answering()
        wait_until(up, message="it never answered")

    def stop_alive(self) -> None:
        """Its port and locks free, and its process object not signalled."""
        self.tell("stop")
        wait_until(lambda: self.has("stopped"), message="it never stopped")

    def kill(self) -> None:
        """`TerminateProcess`, and waited on until signalled."""
        pair.terminate(self.pid)
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.process.wait(timeout=30)

    def session(self) -> str:
        status, body = http(self.port, "POST", "/api/worker/session", {"runtime": "claude"},
                            {"X-Mentis-Client": "1"})
        assert status == 200, body
        return json.loads(body)["grant"]

    def end_session(self, token: str) -> None:
        status, body = http(self.port, "POST", "/api/worker/session/end", {"grant": token},
                            {"X-Mentis-Client": "1"})
        assert status == 200, body

    def boot(self) -> str:
        return self.brain.joinpath(".mentis.claim").read_text(encoding="ascii")

    def end(self) -> None:
        with contextlib.suppress(OSError, AssertionError):
            if self.process.poll() is None:
                if self.has("pid"):
                    pair.terminate(self.pid)
                kill_tree(self.process.pid)
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.process.wait(timeout=30)


class Front:
    """The front under test, and its tail's stops and trace."""

    def __init__(self, brain, port, upstream, *, directory, secret=SECRET, send_bound_ms=None):
        self.port = port
        self.dir = pathlib.Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        dist = self.dir / "dist"
        dist.mkdir(exist_ok=True)
        env = environment(secret)
        env["MENTIS_TAIL_DIR"] = str(self.dir)
        if send_bound_ms is not None:
            env["MENTIS_TAIL_SEND_BOUND_MS"] = str(send_bound_ms)
        with open(self.dir / "front.log", "ab") as log:
            self.process = subprocess.Popen(
                [front_exe(), str(brain), "--host", "127.0.0.1", "--port", str(port),
                 "--upstream", f"http://127.0.0.1:{upstream}", "--dist", str(dist)],
                cwd=str(self.dir), env=env, stdout=log, stderr=subprocess.STDOUT)
        self.suspended = False

    @property
    def pid(self) -> int:
        return self.process.pid

    def wait_answering(self) -> None:
        def up():
            assert self.process.poll() is None, (self.dir / "front.log").read_text(errors="replace")
            try:
                return http(self.port, "GET", "/api/pulse", headers={"X-Mentis-Client": "1"},
                            timeout=2.0)[0] == 200
            except OSError:
                return False
        wait_until(up, message="the front never answered")

    def arm(self, line: str) -> None:
        (self.dir / f"stop-{line}").write_bytes(b"")

    def wait_stopped(self, line: str, limit: float = 30.0) -> None:
        wait_until(lambda: (self.dir / f"stopped-{line}").exists(), limit=limit,
                   message=f"no tail reached {line}")

    def go_on(self, line: str) -> None:
        (self.dir / f"go-{line}").write_bytes(b"")

    def limit_next_write(self, most: int) -> None:
        temporary = self.dir / "limit.tmp"
        temporary.write_text(str(most), encoding="ascii")
        temporary.replace(self.dir / "limit")

    def suspend(self) -> None:
        pair.suspend(self.pid)
        self.suspended = True

    def resume(self) -> None:
        pair.resume(self.pid)
        self.suspended = False

    def trace(self) -> list[dict]:
        file = self.dir / "trace.jsonl"
        if not file.exists():
            return []
        return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()
                if line.endswith("}")]

    def events(self, event: str) -> list[dict]:
        return [seen for seen in self.trace() if seen["event"] == event]

    def forwards(self) -> list[str]:
        """Why each read went on to Python: the door's reasons, the tail's among them."""
        return [seen["event"].removeprefix("door-forward:") for seen in self.trace()
                if seen["event"].startswith("door-forward:")]

    def answer_trace(self, event_id: int) -> dict[str, int]:
        return {seen["event"]: seen["at"] for seen in self.trace() if seen["id"] == event_id}

    def end(self) -> None:
        if self.suspended:
            with contextlib.suppress(OSError):
                self.resume()
        for line in ("checked", "mid-send"):
            with contextlib.suppress(OSError):
                self.go_on(line)
        kill_tree(self.process.pid)
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.process.wait(timeout=30)


class World:
    """`B` behind a front on one Brain, with a session grant the front has answered for."""

    def __init__(self, brain: pathlib.Path, work: pathlib.Path, *, send_bound_ms=None):
        self.brain, self.work = brain, work
        self.public, self.private = free_port(), free_port()
        self.pythons: list[ServerPython] = []
        self.counter = 0
        self.b = self.python()
        self.b.wait_answering()
        self.front = Front(brain, self.public, self.private, directory=work / "front",
                           send_bound_ms=send_bound_ms)
        self.front.wait_answering()
        self.token = self.b.session()
        self.wait_held(self.token)

    def python(self, **options) -> ServerPython:
        self.counter += 1
        options.setdefault("answers_at", f"http://127.0.0.1:{self.public}")
        python = ServerPython(self.brain, options.pop("port", self.private),
                              control=self.work / f"python-{self.counter}", **options)
        self.pythons.append(python)
        return python

    def wait_held(self, token: str, limit: float = 20.0) -> None:
        """Until a read has been answered by the front itself: the trace says so."""
        def answered():
            before = len(self.front.events("last-byte"))
            status, _ = read_as(self.public, token)
            return status == 200 and len(self.front.events("last-byte")) > before
        wait_until(answered, limit=limit, message="the front never answered from the mirror")

    def end(self) -> None:
        self.front.end()
        for python in self.pythons:
            python.end()


@contextlib.contextmanager
def world(brain_seed, tmp_path, **options):
    brain = tmp_path / "brain"
    shutil.copytree(brain_seed, brain)
    made = World(brain, tmp_path, **options)
    try:
        yield made
    finally:
        made.end()


def in_background(what):
    """Run `what` on a thread. `.result()` gives what it returned, or raises what it raised."""
    box: dict = {}

    def run():
        try:
            box["value"] = what()
        except BaseException as error:  # noqa: BLE001
            box["error"] = error

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    class Running:
        @staticmethod
        def result(timeout: float = 120.0):
            thread.join(timeout)
            assert not thread.is_alive(), "still running"
            if "error" in box:
                raise box["error"]
            return box["value"]

        @staticmethod
        def done() -> bool:
            return not thread.is_alive()

    return Running


def big_turn(brain: pathlib.Path, size: int) -> str:
    """A Turn several times what two socket buffers hold, on a Brain nothing is serving. Its id."""
    script = (
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / 'crates/mentis-rules/tests/support'))\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import python_side\n"
        "corpus, cv = python_side._open(sys.argv[2])\n"
        "owner = cv.resolve_participant('@r1-owner')\n"
        "known = python_side._named(corpus, 'conversation', 'R1 known conversation')\n"
        "turn = cv.say(known, owner, [{'type': 'text', 'text': 'x' * int(sys.argv[3])}])\n"
        "corpus.close()\n"
        "print(turn)\n")
    done = subprocess.run([sys.executable, "-c", script, str(REPO), str(brain), str(size)],
                          capture_output=True, text=True, encoding="utf-8", cwd=str(REPO),
                          env=environment(None))
    assert done.returncode == 0, done.stderr
    return done.stdout.strip().splitlines()[-1]


def slow_client(port: int, request: bytes) -> socket.socket:
    """A client with a small receive buffer that sends its request and doesn't read."""
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    sock.settimeout(60.0)
    sock.connect(("127.0.0.1", port))
    sock.sendall(request)
    return sock
