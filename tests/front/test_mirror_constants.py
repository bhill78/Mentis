"""Measures `CLAIM_WAIT`, `CLAIM_POLL` and `SEND_BOUND` on a real front and real Pythons, and reports
what it finds to `docs/rust/evidence/r3-constants.json` (`R3-mirror.md`, Timings, and section 8's
"reported, never a gate"). The one thing it holds to is the design's relation: `CLAIM_WAIT` is longer
than `SEND_BOUND`.

- **`CLAIM_POLL`:** what a try costs, and what a claim behind a short tail waits at each value.
- **`CLAIM_WAIT`:** how long a killed owner's locks take to go, and how long tails hold under load.
- **`SEND_BOUND`:** how long a client that keeps reading holds a tail, at sizes up to a large answer.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import statistics
import threading
import time

import pytest

from mentis.spine import brainlock
from tests.front.mirror_harness import (REPO, World, big_turn, read_as, slow_client,
                                        worker_request, world)

EVIDENCE = REPO / "docs" / "rust" / "evidence" / "r3-constants.json"
#: From the Rust constant, which is what a release has: read, not repeated.
SEND_BOUND_RS = (REPO / "crates/mentis-server/src/front/tail.rs").read_text(encoding="utf-8")


def _send_bound_s() -> float:
    marker = "pub const SEND_BOUND: Duration = Duration::from_secs("
    at = SEND_BOUND_RS.index(marker) + len(marker)
    return float(SEND_BOUND_RS[at:SEND_BOUND_RS.index(")", at)])


found: dict = {}


def _frequency() -> float:
    frequency = ctypes.c_longlong()
    ctypes.windll.kernel32.QueryPerformanceFrequency(ctypes.byref(frequency))
    return float(frequency.value)


def _summary(values: list[float]) -> dict:
    ordered = sorted(values)
    return {"n": len(ordered), "median": round(statistics.median(ordered), 6),
            "p95": round(ordered[int(len(ordered) * 0.95) - 1], 6), "max": round(ordered[-1], 6)}


def test_claim_poll_what_a_try_costs_and_what_a_claim_waits(tmp_path):
    brainlock.serve(str(tmp_path), boot_id="0" * 32).release()
    fh = brainlock._open_claim(str(tmp_path))
    held = brainlock._open_claim(str(tmp_path))
    assert brainlock._lock(held, True)
    tries = 20000
    began = time.perf_counter()
    for _ in range(tries):
        assert not brainlock._lock(fh, False)
    per_try = (time.perf_counter() - began) / tries
    brainlock._unlock(held)
    held.close()
    fh.close()
    found["claim_try_seconds"] = round(per_try, 9)
    by_poll = {}
    original = brainlock.CLAIM_POLL
    try:
        for poll in (0.001, 0.005, 0.01, 0.05):
            brainlock.CLAIM_POLL = poll
            overruns = []
            for _ in range(30):
                tail = brainlock._open_claim(str(tmp_path))
                assert brainlock._lock(tail, True)
                released = []

                def release(tail=tail, released=released):
                    time.sleep(0.02)
                    released.append(time.perf_counter())
                    brainlock._unlock(tail)
                    tail.close()
                thread = threading.Thread(target=release)
                thread.start()
                serving = brainlock.serve(str(tmp_path), boot_id="1" * 32)
                got = time.perf_counter()
                serving.release()
                thread.join()
                overruns.append(got - released[0])
            by_poll[str(poll)] = _summary(overruns)
    finally:
        brainlock.CLAIM_POLL = original
    found["claim_behind_a_20ms_tail_seconds_past_its_release_by_poll"] = by_poll


def test_claim_wait_how_long_a_killed_owner_s_locks_take_to_go(brain_seed, tmp_path):
    waits = []
    frequency = _frequency()
    for number in range(10):
        made = tmp_path / str(number)
        made.mkdir()
        with world(brain_seed, made) as w:
            b2 = w.python(wait_for_go=True)
            b2.wait_imported()
            b2.go()
            w.b.kill()
            b2.wait_answering()
            steps = b2.steps()
            waits.append((steps["owner"] - steps["sole"]) / frequency)
    found["claim_after_a_kill_waited_seconds"] = _summary(waits)


@pytest.fixture(scope="module")
def big_brain(brain_seed, tmp_path_factory):
    sizes = {}
    made = tmp_path_factory.mktemp("big") / "brain"
    shutil.copytree(brain_seed, made)
    for size in (1 << 16, 1 << 20, 8 << 20, 32 << 20):
        sizes[size] = big_turn(made, size)
    return made, sizes


def test_send_bound_how_long_a_client_that_keeps_reading_holds_a_tail(big_brain, tmp_path):
    made, sizes = big_brain
    brain = tmp_path / "brain"
    shutil.copytree(made, brain)
    w = World(brain, tmp_path)
    frequency = _frequency()
    try:
        by_size = {}
        for size, turn in sizes.items():
            holds = []
            for _ in range(5):
                known = {seen["id"] for seen in w.front.events("first-byte")}
                status, body = read_as(w.public, w.token, "resolve", {"ref": turn})
                assert status == 200 and len(body) > size
                new = [seen for seen in w.front.events("first-byte") if seen["id"] not in known]
                assert new, "the front didn't answer this"
                trace = w.front.answer_trace(new[-1]["id"])
                holds.append((trace["released"] - trace["checked"]) / frequency)
            by_size[str(size)] = _summary(holds)
        found["tail_hold_seconds_reading_client_by_answer_bytes"] = by_size
        # A reader that takes its time, as a stalled agent's transport might.
        turn = sizes[8 << 20]
        client = slow_client(w.public, worker_request(w.public, w.token, "resolve", {"ref": turn}))
        began = time.monotonic()
        got = 0
        try:
            while True:
                chunk = client.recv(64 * 1024)
                if not chunk:
                    break
                got += len(chunk)
                time.sleep(0.001)
        except OSError:
            pass
        client.close()
        found["slow_reader_64k_per_ms_seconds_for_8MiB"] = round(time.monotonic() - began, 3)
        found["slow_reader_got_bytes"] = got
    finally:
        w.end()


def test_the_design_s_relation_holds_and_this_is_recorded():
    assert brainlock.CLAIM_WAIT > _send_bound_s()
    found.update(CLAIM_WAIT=brainlock.CLAIM_WAIT, CLAIM_POLL=brainlock.CLAIM_POLL,
                 SEND_BOUND=_send_bound_s())
    if os.environ.get("MENTIS_R3_RECORD_CONSTANTS"):
        EVIDENCE.write_text(json.dumps(found, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("\n" + json.dumps(found, indent=1, sort_keys=True))
