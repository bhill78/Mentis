"""Row K: what the front knows of run state. 20. `R1-acceptance.md`, "K", governed by
`docs/rust/contracts/live-snapshot.md`. The exact boundaries are `live.rs`'s tests; these show the
system keeps them.

"Suspended" is the whole process tree, by `NtSuspendProcess`. "Stalled" is `/private/live` alone, so
Python can still write. R1 changes nothing in Python for this, so the hook is on the harness's side:
`Gate` stands where `door_recorder` does, as the front's `--upstream`, and holds that one route while
everything else goes on to Python. For K13 and K14, `Stub` is the whole of what the front is talking
to, because no real Python answers an unknown schema or a lower generation.

Times here allow for the sampling, never for the state: a boundary's exact value is `live.rs`'s.
"""

from __future__ import annotations

import contextlib
import http.server
import json
import pathlib
import shutil
import subprocess
import threading
import time

import pytest

from tests.front.pair import (CLIENT, PORT, REAL_MARS, SPARE_PORTS, Pair, _template, advance, ask,
                              conversation_named, post_json, rows, terminate, wait_gone)
from tools.r1 import common, door_recorder

SECRET_HEADER = "X-Mentis-Boot-Secret"
PRIVATE_PORT = PORT + 10000
#: `POLL_WHILE_ASKED_WITHIN` and `POLL_EVERY`, and a little.
POLLING_STOPS_S = 6.5
ONE_POLL_S = 1.0
#: What a refused connection takes to say so on Windows, on top of the poll that finds it.
REFUSED_S = 4.0
#: Long enough after the last pulse that polling has stopped and what it last got is past fresh.
IDLE_S = POLLING_STOPS_S + 2.5
STUB_PORT, STUB_FRONT_PORT = SPARE_PORTS[0:2]


@pytest.fixture
def copy(brain_seed, tmp_path) -> pathlib.Path:
    brain = tmp_path / "brain"
    shutil.copytree(brain_seed, brain)
    return brain


@pytest.fixture
def pair(copy):
    with Pair(copy) as running:
        yield running


class _Held(door_recorder._Carry):
    """`door_recorder`'s carrying, with one route that can be held. A held poll is left unanswered,
    so the front gives up on it, and is then answered to nobody."""

    def _carry(self) -> None:
        gate = self.server.gate
        if self.path == "/private/live":
            gate.polled(through=gate.open.is_set())
            gate.open.wait()
        super()._carry()

    do_GET = do_POST = do_OPTIONS = do_HEAD = do_PUT = do_DELETE = _carry


class Gate:
    """Stands between the front and Python. `hold()` stalls `/private/live` alone."""

    def __init__(self, python_port: int = PRIVATE_PORT):
        self.open = threading.Event()
        self.open.set()
        self._lock = threading.Lock()
        self.polls: list[float] = []
        #: When each poll that was let straight through arrived. No earlier than the front sent it,
        #: so an age counted from here is never more than the front's own.
        self.through: list[float] = []
        self._server = door_recorder._Server(("127.0.0.1", 0), _Held)
        self._server.python_port = python_port
        self._server.gate = self
        self._server.recorder = self
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def answered(self, *_) -> None:
        pass

    def polled(self, through: bool) -> None:
        now = time.monotonic()
        with self._lock:
            self.polls.append(now)
            if through:
                self.through.append(now)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self.polls)

    @property
    def last_through(self) -> float:
        with self._lock:
            return self.through[-1]

    def hold(self) -> None:
        self.open.clear()

    def release(self) -> None:
        self.open.set()

    def __enter__(self) -> Gate:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.open.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=10)


@contextlib.contextmanager
def gated(copy):
    """A pair whose front reaches Python through a `Gate`."""
    with Gate() as gate, Pair(copy, upstream=gate.url) as running:
        yield running, gate


# -- a stand-in for all of Python ---------------------------------------------------------------


class _Answers(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        body = json.dumps(self.server.envelope()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def log_message(self, *args) -> None:
        pass


def envelope(schema=1, boot="boot-a", generation=5, live_hash="aaaaaaaaaaaa") -> dict:
    return {"schema": schema, "boot_id": boot, "generation": generation, "live_hash": live_hash,
            "taken_at": time.time(), "fields": {"live_now": [], "run_marks": []}}


@contextlib.contextmanager
def stubbed(copy):
    """A front alone, by the launcher's step 4, with `Stub` where Python goes. `set(...)` says what it
    answers next. The front takes it for Python: it can't tell, and that is the point."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", STUB_PORT), _Answers)
    server.daemon_threads = True
    current = {"answer": envelope()}
    server.envelope = lambda: current["answer"]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    words = _template()
    front = _front_binary(words)
    dist = words[words.index("--dist") + 1]
    log = open(copy.parent / "stub-front.log", "ab")  # noqa: SIM115  held for the process's life
    process = subprocess.Popen([front, str(copy), "--host", "127.0.0.1", "--port",
                                str(STUB_FRONT_PORT), "--upstream",
                                f"http://127.0.0.1:{STUB_PORT}", "--dist", dist],
                               env={**_clean_env(), "MENTIS_BOOT_SECRET": "stub-secret"},
                               stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 30
        while True:
            with contextlib.suppress(OSError):
                if ask(STUB_FRONT_PORT, "GET", "/", wait=5.0).status in (200, 404):
                    break
            assert process.poll() is None and time.monotonic() < deadline, "the front didn't start"
            time.sleep(0.05)
        yield STUB_FRONT_PORT, current
    finally:
        process.kill()
        process.wait(timeout=30)
        log.close()
        server.shutdown()
        server.server_close()


def _front_binary(words: list[str]) -> str:
    if "--front" in words:
        return words[words.index("--front") + 1]
    return str(pathlib.Path(words[0]).with_name("mentis-server.exe"))


def _clean_env() -> dict:
    import os
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("MENTIS")}


# -- looking at pulses --------------------------------------------------------------------------


class Pulse:
    def __init__(self, answer):
        assert answer.status == 200, answer
        self.doc = answer.json
        self.token = self.doc["token"]
        self.durable, self.hash = self.token.split("/")
        self.live = self.doc.get("live")
        self.state = self.live["state"] if self.live else "fresh"
        self.at = time.monotonic()


def pulse(port: int) -> Pulse:
    return Pulse(ask(port, "GET", "/api/pulse", headers=CLIENT, wait=10.0))


def until(port: int, wanted, limit: float, every: float = 0.05) -> Pulse:
    """Pulses until one is wanted. A failure names what was seen."""
    deadline = time.monotonic() + limit
    seen = None
    while time.monotonic() < deadline:
        seen = pulse(port)
        if wanted(seen):
            return seen
        time.sleep(every)
    raise AssertionError(f"not within {limit} s; last was {seen and seen.doc}")


def is_fresh(seen: Pulse) -> bool:
    return seen.live is None


def is_stale(seen: Pulse) -> bool:
    return seen.state == "stale"


def is_unavailable(seen: Pulse) -> bool:
    return seen.state == "unavailable"


def fresh_pulse(port: int) -> Pulse:
    return until(port, is_fresh, 15)


def durable_position(brain) -> str:
    return ".".join(str(n) for n in advance(brain))


def owner_of(brain) -> str:
    return rows(brain, "SELECT id FROM entry WHERE def_name='participant' "
                       "AND json_extract(body,'$.alias')='@r1-owner'")[0][0]


def post(pair, words: str, port: int | None = None) -> None:
    conversation = conversation_named(pair.brain, "R1 known conversation")
    got = post_json(port or pair.port, "/fluid/api/posts",
                    {"conversation": conversation, "author": owner_of(pair.brain), "text": words},
                    CLIENT)
    assert got.status == 200, got


def live_envelope(pair, secret: str | None = None):
    return ask(pair.private_port, "GET", "/private/live",
               headers={SECRET_HEADER: secret if secret is not None else pair.secret})


def kill_python(pair) -> None:
    """The real server first, as `Pair.kill_python`. A venv's stub then ends on its own, and
    Windows refuses to terminate a process that is already ending, so that isn't a failure."""
    tree = _tree_of(pair)
    for pid in reversed(tree):
        try:
            terminate(pid)
        except OSError:
            assert wait_gone(pid), f"{pid} couldn't be killed and is still there"
    assert all(wait_gone(pid) for pid in tree)


def _tree_of(pair) -> list[int]:
    from tests.front.pair import process_tree
    return process_tree(pair.python_pid)


#: The Python that can run the repository's scripted backend, and the backend's name to MARS.
MARS_PYTHON = r"C:\Work\MARS-venv\Scripts\python.exe"
SCRIPTED_RUNTIME = "k1-scripted"


def scripted_mars(where: pathlib.Path) -> dict:
    """What it takes for a real run on this server with no logged-in runtime: real MARS, with the
    scripted ACP backend the repository's own tests use, `tests/fakes/mars_acp_agent.py`.

    Nothing else moves Python's live state from outside it. On `workload-no-mars-here` a dispatch
    ends in `RuntimeNotPresent` before a run opens, and R1 adds no hook to Python."""
    (where / "mars-data").mkdir()
    backends = where / "backends.json"
    agent = common.REPO / "tests" / "fakes" / "mars_acp_agent.py"
    backends.write_text(json.dumps({"backends": [
        {"id": SCRIPTED_RUNTIME, "command": [MARS_PYTHON, str(agent)],
         "permissions": "forwarded"}]}), encoding="utf-8")
    return {"MARS_BACKENDS_FILE": str(backends), "MARS_DATA_DIR": str(where / "mars-data")}


def dispatch_something(pair) -> None:
    """Something that moves a run this Python holds: a turn asked of an agent."""
    conversation = conversation_named(pair.brain, "R1 known conversation")
    agent = rows(pair.brain, "SELECT id FROM entry WHERE def_name='participant' "
                             "AND json_extract(body,'$.alias')='@r1-agent'")[0][0]
    got = post_json(pair.port, "/fluid/api/posts", {
        "conversation": conversation, "author": owner_of(pair.brain),
        "text": "row K: a live change", "action": "ask-participant", "addressed_to": [agent],
        "dispatch": [{"participant": agent, "runtime": SCRIPTED_RUNTIME}]}, CLIENT)
    assert got.status == 200, got
    assert got.json["dispatched"] == 1, got


# -- K1 to K20 ----------------------------------------------------------------------------------


def test_k1_the_envelope_and_what_moves_its_generation(copy):
    with Pair(copy, mars=f"{REAL_MARS}", env=scripted_mars(copy.parent)) as pair:
        got = live_envelope(pair)
        assert got.status == 200, got
        first = got.json
        assert first["schema"] == 1
        assert isinstance(first["generation"], int) and not isinstance(first["generation"], bool)
        assert isinstance(first["boot_id"], str) and first["boot_id"] != str(first["generation"])
        assert isinstance(first["live_hash"], str) and len(first["live_hash"]) == 12
        assert isinstance(first["taken_at"], float)
        assert set(first["fields"]) >= {"live_now", "run_marks"}

        # Nothing moves it but a live change: not asking again, not a pulse, not a durable write.
        pulse(pair.port)
        post(pair, "row K: a durable write is not a live change")
        again = live_envelope(pair).json
        assert again["generation"] == first["generation"]
        assert again["live_hash"] == first["live_hash"]
        assert again["boot_id"] == first["boot_id"]

        dispatch_something(pair)
        deadline = time.monotonic() + 60
        moved = again
        while moved["generation"] == first["generation"]:
            assert time.monotonic() < deadline, "a live change didn't move the generation"
            time.sleep(0.02)
            moved = live_envelope(pair).json
        assert moved["generation"] > first["generation"]
        assert moved["live_hash"] != first["live_hash"]
        assert moved["boot_id"] == first["boot_id"]

        for wrong in ["", "not-the-secret"]:
            refused = live_envelope(pair, wrong)
            assert refused.status == 403, refused
            assert refused.json["kind"] == "PermissionError"
            assert set(refused.json) == {"error", "kind"}


def test_k2_stalled_the_durable_half_still_moves_and_the_hash_is_kept(copy):
    with gated(copy) as (pair, gate):
        before = fresh_pulse(pair.port)
        gate.hold()
        took = []
        for n in range(8):
            post(pair, f"row K2 post {n}")
            started = time.monotonic()
            seen = pulse(pair.port)
            took.append(time.monotonic() - started)
            assert seen.durable == durable_position(pair.brain), "waited on Python"
            assert seen.hash == before.hash
            time.sleep(0.25)
        print(f"K2: pulse while stalled, slowest {max(took) * 1000:.1f} ms, of {len(took)}")
        # Answered, not held until a poll gave up: well inside one poll timeout's worth of waiting.
        assert seen.durable != before.durable


def test_k3_stalled_then_released_the_live_half_catches_up_within_one_poll(copy):
    with gated(copy) as (pair, gate):
        fresh_pulse(pair.port)
        gate.hold()
        until(pair.port, is_stale, 5)
        gate.release()
        released = time.monotonic()
        until(pair.port, is_fresh, ONE_POLL_S)
        print(f"K3: fresh again {(time.monotonic() - released) * 1000:.0f} ms after the release")


def test_k4_suspended_the_durable_half_answers_throughout(pair):
    fresh_pulse(pair.port)
    position = durable_position(pair.brain)
    pair.suspend_python()
    try:
        deadline = time.monotonic() + 5
        count = 0
        while time.monotonic() < deadline:
            seen = pulse(pair.port)
            assert seen.durable == position
            assert seen.durable == durable_position(pair.brain)
            count += 1
            time.sleep(0.1)
        assert count >= 20, count
    finally:
        pair.resume_python()


def test_k5_suspended_fresh_to_stale_at_two_seconds(pair):
    before = fresh_pulse(pair.port)
    time.sleep(0.6)
    fresh_pulse(pair.port)
    pair.suspend_python()
    suspended = time.monotonic()
    try:
        seen = before
        while is_fresh(seen):
            assert time.monotonic() - suspended < 4, "still fresh"
            seen = pulse(pair.port)
            time.sleep(0.02)
        assert is_stale(seen), seen.doc
        assert seen.hash == before.hash
        assert seen.live["age_ms"] > 2000
        # No longer than the limit, and no shorter than the limit less the poll it answered last.
        assert 1.0 <= time.monotonic() - suspended <= 3.0
    finally:
        pair.resume_python()


def test_k6_suspended_stale_to_unavailable_at_ten_seconds(pair):
    before = fresh_pulse(pair.port)
    pair.suspend_python()
    suspended = time.monotonic()
    try:
        until(pair.port, is_stale, 4)
        seen = until(pair.port, lambda p: not is_stale(p), 11)
        assert is_unavailable(seen), seen.doc
        assert seen.hash == "unavailable"
        assert seen.hash != before.hash
        assert seen.live["age_ms"] > 10000
        assert 9.0 <= time.monotonic() - suspended <= 11.5
    finally:
        pair.resume_python()


def test_k7_resumed_before_ten_seconds_no_hash_change(pair):
    before = fresh_pulse(pair.port)
    pair.suspend_python()
    resumed = False
    try:
        until(pair.port, is_stale, 4)
        pair.resume_python()
        resumed = True
        seen = until(pair.port, is_fresh, 3)
        assert seen.hash == before.hash
    finally:
        if not resumed:
            pair.resume_python()


def test_k8_resumed_after_ten_seconds_the_hash_changes_once(pair):
    before = fresh_pulse(pair.port)
    pair.suspend_python()
    resumed = False
    try:
        until(pair.port, is_unavailable, 12)
        pair.resume_python()
        resumed = True
        hashes = [pulse(pair.port).hash]
        deadline = time.monotonic() + 3
        while hashes[-1] == "unavailable":
            assert time.monotonic() < deadline, "never came back"
            hashes.append(pulse(pair.port).hash)
            time.sleep(0.02)
        assert hashes[-1] == before.hash
        assert set(hashes[:-1]) <= {"unavailable"}
        time.sleep(1)
        assert pulse(pair.port).hash == before.hash
    finally:
        if not resumed:
            pair.resume_python()


def test_k9_killed_while_fresh_unavailable_from_the_refused_poll(pair):
    fresh_pulse(pair.port)
    kill_python(pair)
    killed = time.monotonic()
    seen = until(pair.port, is_unavailable, REFUSED_S)
    print(f"K9: unavailable {(time.monotonic() - killed) * 1000:.0f} ms after the kill")
    assert seen.hash == "unavailable"
    assert time.monotonic() - killed < 9


def test_k10_killed_while_stale_the_same(pair):
    fresh_pulse(pair.port)
    pair.suspend_python()
    until(pair.port, is_stale, 4)
    # A suspended process is killed as it stands, and the kill is what the poll then meets.
    kill_python(pair)
    killed = time.monotonic()
    seen = until(pair.port, is_unavailable, REFUSED_S)
    print(f"K10: unavailable {(time.monotonic() - killed) * 1000:.0f} ms after the kill")
    assert seen.hash == "unavailable"
    assert seen.live["age_ms"] < 10000, "by the refused poll, not by the ten seconds"


def test_k11_restarted_between_polls_two_transitions_nothing_older_served(copy):
    with gated(copy) as (pair, gate):
        before = fresh_pulse(pair.port)
        old_boot = live_envelope(pair).json["boot_id"]
        # No poll reaches Python through the restart, so to the front it is between two polls.
        gate.hold()
        time.sleep(0.1)
        kill_python(pair)
        pair.restart_python()
        new_boot = live_envelope(pair).json["boot_id"]
        assert new_boot != old_boot
        # A restart can take less than the 2 s a snapshot stays fresh. Held until it isn't, so that
        # "fresh" below can only be the new boot's.
        seen = until(pair.port, is_stale, 5)
        assert seen.hash == before.hash, "the front has heard nothing yet"
        gate.release()
        hashes = [seen.hash]
        deadline = time.monotonic() + 5
        while True:
            seen = pulse(pair.port)
            if seen.hash != hashes[-1]:
                hashes.append(seen.hash)
            if is_fresh(seen):
                break
            assert time.monotonic() < deadline, hashes
            time.sleep(0.02)
        # Into `unavailable`, then to the new boot's hash. Both boots hold no runs, so the hash reads
        # the same; what shows the discard is the state it passed through.
        assert hashes == [before.hash, "unavailable", live_envelope(pair).json["live_hash"]]


def test_k12_restarted_while_unavailable_one_hash_change_only(pair):
    fresh_pulse(pair.port)
    kill_python(pair)
    until(pair.port, is_unavailable, REFUSED_S)
    pair.restart_python()
    hashes = ["unavailable"]
    deadline = time.monotonic() + 10
    while True:
        seen = pulse(pair.port)
        if seen.hash != hashes[-1]:
            hashes.append(seen.hash)
        if is_fresh(seen):
            break
        assert time.monotonic() < deadline, hashes
        time.sleep(0.02)
    assert hashes == ["unavailable", live_envelope(pair).json["live_hash"]]


def test_k13_an_unknown_schema_discards_until_a_known_one_answers(copy):
    with stubbed(copy) as (port, stub):
        fresh = fresh_pulse(port)
        assert fresh.hash == "aaaaaaaaaaaa"
        stub["answer"] = {"schema": 2, "elsewhere": True}
        seen = until(port, is_unavailable, 2)
        assert seen.hash == "unavailable"
        assert seen.live["age_ms"] is None, "what was held is gone"
        # It stays so while the schema stays unknown.
        time.sleep(1.2)
        assert is_unavailable(pulse(port))
        stub["answer"] = envelope(live_hash="bbbbbbbbbbbb")
        seen = until(port, is_fresh, 2)
        assert seen.hash == "bbbbbbbbbbbb"


def test_k14_a_lower_generation_is_discarded(copy):
    with stubbed(copy) as (port, stub):
        assert fresh_pulse(port).hash == "aaaaaaaaaaaa"
        stub["answer"] = envelope(generation=4, live_hash="cccccccccccc")
        seen = until(port, is_unavailable, 2)
        assert seen.hash == "unavailable"
        seen = until(port, is_fresh, 2)
        assert seen.hash == "cccccccccccc"


class Reader:
    """A reader as `apps/fluid-web/src/fluid/identity/activity.ts` is: it keeps the last token and
    rereads when `moved(prev, next)` says the live half changed. Its first token isn't a reread."""

    def __init__(self):
        self.token: str | None = None
        self.rereads = 0

    def hears(self, seen: Pulse) -> None:
        if self.token is not None and self.token != seen.token:
            before, after = self.token.split("/"), seen.token.split("/")
            if before[0] == after[0] and before[1] != after[1]:
                self.rereads += 1
        self.token = seen.token


def test_k15_one_reread_per_transition(pair):
    fresh_pulse(pair.port)

    # Fresh, stale, fresh: nothing to reread.
    reader = Reader()
    reader.hears(pulse(pair.port))
    pair.suspend_python()
    try:
        seen = until(pair.port, is_stale, 4)
        reader.hears(seen)
        for _ in range(10):
            reader.hears(pulse(pair.port))
            time.sleep(0.05)
    finally:
        pair.resume_python()
    while not is_fresh(seen):
        seen = pulse(pair.port)
        reader.hears(seen)
        time.sleep(0.02)
    assert reader.rereads == 0

    # Fresh, stale, unavailable, fresh: one going in, one coming out.
    reader = Reader()
    reader.hears(pulse(pair.port))
    pair.suspend_python()
    resumed = False
    try:
        states = []
        while "unavailable" not in states:
            seen = pulse(pair.port)
            reader.hears(seen)
            states.append(seen.state)
            time.sleep(0.05)
        assert "stale" in states
        pair.resume_python()
        resumed = True
    finally:
        if not resumed:
            pair.resume_python()
    while not is_fresh(seen):
        seen = pulse(pair.port)
        reader.hears(seen)
        time.sleep(0.02)
    assert reader.rereads == 2


def test_k16_stale_is_never_served_as_fresh(copy):
    with gated(copy) as (pair, gate):
        fresh_pulse(pair.port)
        time.sleep(0.6)
        fresh_pulse(pair.port)

        def sample(for_seconds: float) -> int:
            """At 20 Hz. No answer without `live` may be older, by the last poll this test saw go
            through, than the 2 s it may be."""
            served = 0
            deadline = time.monotonic() + for_seconds
            while time.monotonic() < deadline:
                asked = time.monotonic()
                seen = pulse(pair.port)
                if is_fresh(seen):
                    age = asked - gate.last_through
                    assert age <= 2.0, f"served as fresh at {age:.3f} s: {seen.doc}"
                    served += 1
                time.sleep(max(0.0, 0.05 - (time.monotonic() - asked)))
            return served

        assert sample(1.5) > 5, "the front was never fresh while answering"
        gate.hold()
        sample(11.5)
        assert is_unavailable(pulse(pair.port))
        gate.release()
        until(pair.port, is_fresh, 3)
        assert sample(1.5) > 5


def test_k17_no_pulse_over_five_seconds_no_polls(copy):
    with gated(copy) as (pair, gate):
        # Nothing has asked since it started, so nothing has been polled.
        time.sleep(1.0)
        assert gate.count == 0, "polled with no pulse asked"
        fresh_pulse(pair.port)
        assert gate.count > 0
        time.sleep(POLLING_STOPS_S)
        stopped = gate.count
        time.sleep(3.0)
        assert gate.count == stopped, "still polling"


def test_k18_resumed_after_idle_is_not_unavailable(pair):
    before = fresh_pulse(pair.port)
    # The polls go on for 5 s after that pulse, and the idle counted is from when they stop.
    time.sleep(POLLING_STOPS_S + 15.5)
    first = pulse(pair.port)
    assert is_stale(first), first.doc
    assert first.hash == before.hash, "the hash doesn't change, so no reader rereads"
    assert first.live["age_ms"] > 15000
    states = [first.state]
    deadline = time.monotonic() + 3
    while states[-1] != "fresh":
        assert time.monotonic() < deadline, states
        states.append(pulse(pair.port).state)
        time.sleep(0.02)
    assert "unavailable" not in states


def test_k19_suspended_during_idle_stale_for_ten_seconds_from_the_resume(pair):
    before = fresh_pulse(pair.port)
    time.sleep(POLLING_STOPS_S)
    pair.suspend_python()
    try:
        time.sleep(1.0)
        first = pulse(pair.port)
        resumed = time.monotonic()
        assert is_stale(first), first.doc
        assert first.hash == before.hash
        seen = first
        while is_stale(seen):
            assert time.monotonic() - resumed < 11.5, "still stale"
            seen = pulse(pair.port)
            time.sleep(0.1)
        assert is_unavailable(seen), seen.doc
        assert time.monotonic() - resumed >= 9.5, "unavailable before its ten seconds"
    finally:
        pair.resume_python()


def test_k20_killed_or_restarted_during_idle_the_first_poll_decides(pair):
    # Killed: the first pulse is stale, and the refused poll makes it unavailable.
    before = fresh_pulse(pair.port)
    time.sleep(IDLE_S)
    kill_python(pair)
    first = pulse(pair.port)
    assert is_stale(first), first.doc
    assert first.hash == before.hash
    until(pair.port, is_unavailable, REFUSED_S)

    # Restarted: stale again, and the new boot discards rather than being adopted.
    pair.restart_python()
    fresh_pulse(pair.port)
    time.sleep(IDLE_S)
    old_boot = live_envelope(pair).json["boot_id"]
    kill_python(pair)
    pair.restart_python()
    assert live_envelope(pair).json["boot_id"] != old_boot
    first = pulse(pair.port)
    assert is_stale(first), first.doc
    states = [first.state]
    deadline = time.monotonic() + 5
    while states[-1] != "fresh":
        assert time.monotonic() < deadline, states
        states.append(pulse(pair.port).state)
        time.sleep(0.02)
    assert "unavailable" in states, states
