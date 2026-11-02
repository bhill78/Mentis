"""Row H: the read scope and SQLite, beside a real Python writing. `R1-acceptance.md`, "H: SQLite".

PAIR is `$env:MENTIS_UNDER_TEST`, on a fresh BRAIN-COPY. The front names no way to hold a read
scope stuck or to run a statement of a test's choosing, so H2 to H4 start PAIR with `--front` naming
a test build of the same source with `mentis-record`'s `row-h-probe` feature (`src/probe.rs`): the
front's own reader, in the front's process. H1 runs on PAIR's binary as it stands, and H4 checks
that binary doesn't hold the probe. What row H asks to be recorded goes to `<fixtures>/row-H.json`,
for the release report.

This module holds what the row files share, D's and I's included.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request

from tools.r1 import common

PORT = 8852
NO_MARS = "workload-no-mars-here"
START_LIMIT_S = 240
EXIT_REFUSED = 3
#: A read past the 2 s scope is ended within this of its snapshot (`READ_SCOPE_ENDED_WITHIN`).
ENDED_WITHIN_S = 2.5
#: In a build with `row-h-probe` and in no other: its thread's name.
PROBE_MARKER = b"row-h-probe"


def environment() -> dict:
    """As the harness starts anything under test (`contracts/bench.md`)."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("MENTIS")}
    env.pop("PYTHONPATH", None)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    return env


def template() -> list[str]:
    """The command PAIR starts by. Not being told one is a failure, never a skip."""
    return json.loads(os.environ["MENTIS_UNDER_TEST"])


def front_exe() -> pathlib.Path:
    """`mentis-server.exe` beside the launcher, which is `--front`'s default."""
    return pathlib.Path(template()[0]).with_name("mentis-server.exe")


def dist() -> str:
    words = template()
    return words[words.index("--dist") + 1]


def code() -> str:
    words = template()
    return words[words.index("--code") + 1]


def venv_python() -> str:
    words = template()
    return words[words.index("--python") + 1]


def run_dir(brain: pathlib.Path) -> pathlib.Path:
    run = brain.parent / f"{brain.name}.run"
    (run / "ws").mkdir(parents=True, exist_ok=True)
    return run


def get(path: str, port: int = PORT, timeout: float = 10.0) -> tuple[int, bytes]:
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                     headers={"X-Mentis-Client": "1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return answer.status, answer.read()
    except urllib.error.HTTPError as refused:
        return refused.code, refused.read()


def post(path: str, body: dict, port: int = PORT, timeout: float = 30.0) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"X-Mentis-Client": "1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return answer.status, json.loads(answer.read())
    except urllib.error.HTTPError as refused:
        return refused.code, json.loads(refused.read())


def wait_for_server(port: int, alive=lambda: True) -> None:
    deadline = time.monotonic() + START_LIMIT_S
    while True:
        assert alive(), "what was started exited before it answered"
        try:
            if get("/api/server", port, 2.0)[0] == 200:
                return
        except OSError:
            pass
        assert time.monotonic() < deadline, f"nothing answered on {port}"
        time.sleep(0.2)


def kill(pid: int) -> None:
    """`TerminateProcess`, by way of `taskkill`, with whatever it started."""
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


class Pair:
    def __init__(self, process: subprocess.Popen, run: pathlib.Path):
        self.process, self.run = process, run

    @property
    def state(self) -> dict:
        return json.loads((self.run / "launch.json").read_text(encoding="utf-8"))

    def kill_python(self) -> None:
        kill(self.state["python"]["pid"])

    def kill_front(self) -> None:
        kill(self.state["front"]["pid"])


@contextlib.contextmanager
def running_pair(brain: pathlib.Path, *, port: int = PORT, probed: bool = False):
    """PAIR on `brain`, both answering, until the block ends, with no process left after. `probed`
    puts the test build of the front in it: see the top of this file."""
    run = run_dir(brain)
    filled = {"{brain}": str(brain), "{port}": str(port), "{ws}": str(run / "ws"),
              "{mars}": NO_MARS, "{run}": str(run)}
    command = [filled.get(word, word) for word in template()]
    env = environment()
    if probed:
        command += ["--front", str(probed_front())]
        env["ROW_H_PROBE_DIR"] = str(probe_dir(run))
    with open(run / "server.log", "ab") as log:
        process = subprocess.Popen(command, cwd=run, env=env, stdout=log,
                                   stderr=subprocess.STDOUT)
    pair = Pair(process, run)
    try:
        wait_for_server(port, lambda: process.poll() is None)
        while not (run / "launch.json").exists():
            assert process.poll() is None, "the launcher exited without saying so"
            time.sleep(0.1)
        yield pair
    finally:
        with contextlib.suppress(OSError, ValueError, KeyError):
            pair.kill_python()
        with contextlib.suppress(OSError, ValueError, KeyError):
            pair.kill_front()
        kill(process.pid)
        process.wait(timeout=30)


@contextlib.contextmanager
def running_front(brain: pathlib.Path, *, port: int = PORT, upstream_port: int = PORT + 10000):
    """The front alone, as `contracts/launcher.md`'s step 4 starts it, with nothing behind it."""
    process = start_front(brain, port=port, upstream_port=upstream_port)
    try:
        wait_for_server_or_owned(port, process)
        yield process
    finally:
        kill(process.pid)
        process.wait(timeout=30)


def start_front(brain: pathlib.Path, *, port: int = PORT,
                upstream_port: int = PORT + 10000) -> subprocess.Popen:
    run = run_dir(brain)
    env = {**environment(), "MENTIS_BOOT_SECRET": "a secret for this test alone"}
    log = open(run / "front.log", "ab")
    try:
        return subprocess.Popen(
            [str(front_exe()), str(brain), "--host", "127.0.0.1", "--port", str(port),
             "--upstream", f"http://127.0.0.1:{upstream_port}", "--dist", dist()],
            cwd=run, env=env, stdout=log, stderr=subprocess.STDOUT)
    finally:
        log.close()


def wait_for_server_or_owned(port: int, process: subprocess.Popen) -> None:
    """A front with no Python behind it answers `/api/pulse` itself, and 503 for the rest."""
    deadline = time.monotonic() + START_LIMIT_S
    while True:
        assert process.poll() is None, "the front exited before it answered"
        with contextlib.suppress(OSError):
            if get("/api/pulse", port, 2.0)[0] == 200:
                return
        assert time.monotonic() < deadline, f"the front did not answer on {port}"
        time.sleep(0.1)


def front_refusal(brain: pathlib.Path) -> tuple[int, str]:
    """The front refusing to start: its exit and its words."""
    process = start_front(brain)
    try:
        process.wait(timeout=60)
    finally:
        kill(process.pid)
    log = run_dir(brain) / "front.log"
    return process.returncode, log.read_text(encoding="utf-8", errors="replace")


def position_of(token: str) -> tuple[int, int, int]:
    entry, operational, delivery = token.split("/", 1)[0].split(".")
    return int(entry), int(operational), int(delivery)


def pulse_position(port: int = PORT) -> tuple[int, int, int]:
    status, body = get("/api/pulse", port)
    assert status == 200, body
    return position_of(json.loads(body)["token"])


def where_to_write(brain: pathlib.Path) -> dict:
    """The Conversation last posted in, which is no rename's version, and who started it. Read
    before anything has this copy open."""
    conn = sqlite3.connect(f"file:{(brain / 'corpus.db').as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        conversation, author = conn.execute(
            "SELECT e.id, e.attributed_to FROM operational o JOIN entry e ON e.id = o.conversation "
            "WHERE o.act = 'turn-said' ORDER BY o.seq DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    return {"conversation": conversation, "author": author}


class Writing:
    """Posts through the front, one after another, until told to stop. Python does the writing."""

    def __init__(self, target: dict, port: int = PORT):
        self.target, self.port = target, port
        self.acknowledged: list[str] = []
        self.refused: list = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        n = 0
        while not self.stop.is_set():
            n += 1
            status, answer = post("/fluid/api/posts", {
                **self.target, "text": f"row H write {n}", "op": f"row-h-{n}"}, self.port)
            if status == 200:
                self.acknowledged.append(answer["post"])
            else:
                self.refused.append((status, answer))

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(timeout=60)
        assert not self.thread.is_alive(), "a write never came back"


_built: list[pathlib.Path] = []


def probed_front() -> pathlib.Path:
    """The test build of the front, once per run, from this clone. Its own target directory, so the
    binary under test is never overwritten."""
    if not _built:
        target = common.REPO / "target" / "row-h-probe"
        subprocess.run(["cargo", "build", "--release", "--locked", "-p", "mentis-server",
                        "--bin", "mentis-server", "--features", "mentis-record/row-h-probe",
                        "--target-dir", str(target)], cwd=common.REPO, check=True,
                       capture_output=True)
        _built.append(target / "release" / "mentis-server.exe")
    return _built[0]


def probe_dir(run: pathlib.Path) -> pathlib.Path:
    probe = run / "probe"
    probe.mkdir(exist_ok=True)
    return probe


def ask_the_front(pair: Pair, mode: str) -> float:
    """A scope from the front's own reader, doing `mode`. Answers once its snapshot exists, with
    when it was asked for, which is no later than the snapshot, so a limit measured from there
    can't flatter it."""
    probe = probe_dir(pair.run)
    since = time.monotonic()
    (probe / f"ask-{mode}").write_text("", encoding="utf-8")
    while not (probe / f"{mode}.snapshot").exists():
        assert not (probe / f"{mode}.answer").exists(), (probe / f"{mode}.answer").read_text(
            encoding="utf-8")
        assert time.monotonic() - since < 10, f"{mode}: the front's probe never answered"
        time.sleep(0.005)
    return since


def fronts_answer(pair: Pair, mode: str) -> str:
    probe = probe_dir(pair.run)
    deadline = time.monotonic() + 15
    while not (probe / f"{mode}.answer").exists():
        assert time.monotonic() < deadline, f"{mode}: the front's probe never finished"
        time.sleep(0.01)
    return (probe / f"{mode}.answer").read_text(encoding="utf-8")


def checkpoint(db: pathlib.Path) -> tuple[int, int, int]:
    """A Python checkpoint on the database: busy, log frames, checkpointed frames."""
    conn = sqlite3.connect(db, timeout=0)
    try:
        return conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    finally:
        conn.close()


def wal_size(db: pathlib.Path) -> int:
    wal = db.with_name(db.name + "-wal")
    return wal.stat().st_size if wal.exists() else 0


def record(key: str, value) -> None:
    """What the row asks to be reported, kept with the fixtures for the release report."""
    path = common.fixtures_root() / "row-H.json"
    held = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    held[key] = value
    path.write_text(json.dumps(held, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def test_the_front_reads_committed_rows_during_sustained_python_writes(brain_copy):
    target = where_to_write(brain_copy)
    with running_pair(brain_copy):
        before = pulse_position()
        seen = before
        with Writing(target) as writing:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                at = pulse_position()
                assert at >= seen, f"the position went back: {seen} then {at}"
                seen = at
                time.sleep(0.05)
        assert not writing.refused, writing.refused[:3]
        assert len(writing.acknowledged) >= 10, "that was not sustained writing"
        assert seen[0] > before[0], "the durable half never moved under Python's writes"
        settled = pulse_position()
        # Every acknowledged write is a committed row the front's next read holds.
        conn = sqlite3.connect(f"file:{(brain_copy / 'corpus.db').as_posix()}?mode=ro", uri=True)
        try:
            want = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM entry").fetchone()[0]
        finally:
            conn.close()
        assert settled[0] == want
        record("h1", {"writes_acknowledged": len(writing.acknowledged),
                      "position_before": before, "position_after": settled})


def test_a_stuck_reader_is_ended_within_2500_ms_of_its_snapshot(brain_copy):
    db = brain_copy / "corpus.db"
    target = where_to_write(brain_copy)
    seen = {}
    with running_pair(brain_copy, probed=True) as running:
        for mode in ("running", "idle", "callback"):
            since = ask_the_front(running, mode)
            status, answer = post("/fluid/api/posts", {
                **target, "text": f"row H2 {mode}", "op": f"row-h2-{mode}"})
            assert status == 200, answer
            # While the snapshot stands, what was written after it can't be checkpointed.
            assert checkpoint(db)[0] == 1, f"{mode}: nothing is pinning the WAL"
            # And the front goes on answering, from another of its connections.
            assert get("/api/pulse")[0] == 200, f"{mode}: the stuck read stopped the front"
            while checkpoint(db)[0] != 0:
                assert time.monotonic() - since < 10, f"{mode}: it never let go"
                time.sleep(0.01)
            released = time.monotonic() - since
            said = fronts_answer(running, mode)
            seen[mode] = {"released_s": round(released, 3), "answer": said}
            assert released < ENDED_WITHIN_S, seen[mode]
            assert "ran past its limit" in said, seen[mode]
    record("h2", seen)


def test_the_wal_recovers_after_that_reader_ends(brain_copy):
    db = brain_copy / "corpus.db"
    target = where_to_write(brain_copy)
    largest = 0
    with running_pair(brain_copy, probed=True) as running:
        since = ask_the_front(running, "idle")
        with Writing(target):
            while time.monotonic() - since < ENDED_WITHIN_S + 1:
                largest = max(largest, wal_size(db))
                time.sleep(0.05)
        largest = max(largest, wal_size(db))
        assert "ran past its limit" in fronts_answer(running, "idle")
        deadline = time.monotonic() + 30
        while (done := checkpoint(db))[0] != 0:
            assert time.monotonic() < deadline, f"the checkpoint never completed: {done}"
            time.sleep(0.05)
        after = wal_size(db)
        assert after < largest or after == 0, f"-wal did not shrink: {largest} then {after}"
    record("h3", {"largest_wal_bytes": largest, "wal_bytes_after_checkpoint": after})


def test_a_write_through_the_fronts_connection_is_refused(brain_copy):
    db = brain_copy / "corpus.db"
    rows = "SELECT COUNT(*) FROM corpus"
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        before = conn.execute(rows).fetchone()[0]
    finally:
        conn.close()
    assert PROBE_MARKER not in front_exe().read_bytes(), "PAIR's own front holds row H's probe"
    assert PROBE_MARKER in probed_front().read_bytes(), "this check can't see the probe"
    with running_pair(brain_copy, probed=True) as running:
        ask_the_front(running, "write")
        said = fronts_answer(running, "write")
        assert said.startswith("SQLite:"), said
        assert "readonly" in said, said
        assert get("/api/pulse")[0] == 200, "the front was left unable to read"
        ask_the_front(running, "report")
        bundled = fronts_answer(running, "report").splitlines()
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            assert conn.execute(rows).fetchone()[0] == before
            python = {"sqlite_version": sqlite3.sqlite_version,
                      "compile_options": [r[0] for r in conn.execute("PRAGMA compile_options")]}
        finally:
            conn.close()
    record("sqlite", {"bundled": bundled, "python": python})
