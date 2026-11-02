"""The interval, on a real front and real Pythons. `docs/rust/R3-mirror.md`, section 8.

`B` is a real server that stops gracefully and stays alive, so its port and locks are free and its
process object isn't signalled, for as long as a test needs: to the front, the same state as a kill
between the release and the signal. `B'` is imported and waiting before `B` stops, so its claim comes
within the lease, and the reason a read forwards has to be the barrier's and not the lease's.
"""

from __future__ import annotations

import contextlib
import ctypes
import random
import shutil
import socket
import threading
import time

import pytest

from mentis.spine import brainlock
from tests.front.mirror_harness import (Short, World, big_turn, free_port, in_background, qpc,
                                        read_as, read_answer, slow_client, wait_until,
                                        worker_request, world)

#: Several times what two socket buffers hold on any machine this runs on.
BIG = 16 * 1024 * 1024
OLD_TOKEN_ANSWERS = {403, 503}


def replacement(w, **options):
    """`B'`, imported, waiting, and told nothing yet."""
    python = w.python(wait_for_go=True, **options)
    python.wait_imported()
    return python


def never_a_200(w, token) -> int:
    status, body = read_as(w.public, token)
    assert status in OLD_TOKEN_ANSWERS, (status, body[:200])
    assert "lease" not in w.front.forwards(), w.front.forwards()
    return status


def test_i1_given_up_with_no_replacement_yet_is_never_a_200(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        w.b.stop_alive()
        assert never_a_200(w, w.token) == 503
        assert w.b.process.poll() is None, "not signalled: the watch still reads as running"


def test_i2_claimed_and_not_bound_is_never_a_200(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        b2 = replacement(w, pause_at="written")
        w.b.stop_alive()
        b2.go()
        wait_until(lambda: b2.has("paused-written"), limit=30)
        assert never_a_200(w, w.token) == 503
        b2.tell("go-written")


def test_i3_a_replacement_serving_gives_its_own_403(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        b2 = replacement(w)
        w.b.stop_alive()
        b2.go()
        b2.wait_answering()
        status, body = read_as(w.public, w.token)
        assert status == 403 and b"live worker grant" in body, (status, body[:200])
        assert "lease" not in w.front.forwards()


def _queued_read_on_a_suspended_front(w):
    w.front.suspend()
    return in_background(lambda: read_as(w.public, w.token))


def test_i4_a_read_queued_on_a_suspended_front_gets_the_replacement_s_403(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        b2 = replacement(w)
        queued = _queued_read_on_a_suspended_front(w)
        w.b.stop_alive()
        b2.go()
        b2.wait_answering()
        w.front.resume()
        status, body = queued.result()
        assert status == 403 and b"live worker grant" in body, (status, body[:200])


def test_i5_a_read_queued_with_no_replacement_gets_the_503(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        queued = _queued_read_on_a_suspended_front(w)
        w.b.stop_alive()
        w.front.resume()
        status, body = queued.result()
        assert status == 503, (status, body[:200])


def _stopped_in_its_tail(w):
    """A real read with the old token, stopped between its checks and its write, then suspended."""
    w.front.arm("checked")
    reading = in_background(lambda: read_as(w.public, w.token))
    w.front.wait_stopped("checked")
    w.front.suspend()
    return reading


def test_i6_a_tail_stopped_after_its_checks_holds_a_replacement_off(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        b2 = replacement(w)
        reading = _stopped_in_its_tail(w)
        w.b.stop_alive()
        b2.go()
        wait_until(lambda: "serve" in b2.steps(), limit=30)
        time.sleep(1.0)
        assert "claim" not in b2.steps(), "it took the claim's lock past a passed tail"
        assert not b2.answering(), "it bound past a passed tail"
        w.front.go_on("checked")
        w.front.resume()
        status, _ = reading.result()
        assert status == 200, "the whole answer goes"
        b2.wait_answering()
        released = w.front.events("released")[-1]["at"]
        assert released < b2.steps()["written"], "released before the claim"


def test_i6_past_the_claim_wait_the_replacement_refuses_and_changes_nothing(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        before = (w.brain / ".mentis.claim").read_bytes()
        b2 = replacement(w, claim_wait=1.0)
        reading = _stopped_in_its_tail(w)
        w.b.stop_alive()
        b2.go()
        wait_until(lambda: b2.process.poll() is not None, limit=60)
        assert b2.process.returncode == 3
        assert "stopped in the middle of an answer" in b2.read("refused")
        assert not b2.answering(), "the port was never bound"
        assert (w.brain / ".mentis.claim").read_bytes() == before
        w.front.go_on("checked")
        w.front.resume()
        assert reading.result()[0] == 200, "the client's answer goes out when the front is resumed"
        # Its locks are free: another start needs nothing else.
        b3 = w.python()
        b3.wait_answering()


def _partly_sent(w, big):
    """A client that doesn't read, a first write stopped inside the status line, and the rest of
    the answer not accepted: several times what the two buffers hold."""
    finished = len(w.front.events("last-byte"))
    begun = len(w.front.events("first-byte"))
    # Windows takes the whole of one write if its buffer isn't already full, so writes are offered
    # piecemeal until it is: the bytes past that really are not accepted.
    w.front.limit_each_write(16 * 1024)
    w.front.limit_next_write(9)
    client = slow_client(w.public, worker_request(w.public, w.token, "resolve", {"ref": big}))
    wait_until(lambda: len(w.front.events("first-byte")) > begun, limit=30,
               message="nothing was accepted")
    time.sleep(0.3)
    assert len(w.front.events("last-byte")) == finished, "it wasn't big enough to stay part-sent"
    return client


@pytest.fixture
def big_world(brain_seed, tmp_path):
    def making(**options):
        brain = tmp_path / "prepared"
        shutil.copytree(brain_seed, brain)
        turn = big_turn(brain, BIG)
        return brain, turn, options
    return making


def _world_with_big_turn(big_world, tmp_path, **options):
    brain, turn, options = big_world(**options)

    @contextlib.contextmanager
    def made():
        w = World(brain, tmp_path, **options)
        try:
            yield w, turn
        finally:
            w.end()
    return made()


def _drain(client) -> tuple[int, bytes]:
    return read_answer(client)


def test_i18_a_complete_success_does_not_cross_ownership(big_world, tmp_path):
    with _world_with_big_turn(big_world, tmp_path, send_bound_ms=60000) as (w, big):
        client = _partly_sent(w, big)
        b2 = replacement(w)
        w.b.stop_alive()
        b2.go()
        wait_until(lambda: "serve" in b2.steps(), limit=30)
        time.sleep(0.5)
        assert "written" not in b2.steps(), "it claimed with bytes still to send"
        status, body = _drain(client)
        client.close()
        assert status == 200 and len(body) > BIG, (status, len(body))
        b2.wait_answering()
        last = w.front.events("last-byte")[-1]["at"]
        released = w.front.events("released")[-1]["at"]
        written = b2.steps()["written"]
        assert last < released < written, (last, released, written)


def test_i19_suspended_part_way_and_resumed_before_the_bound(big_world, tmp_path):
    with _world_with_big_turn(big_world, tmp_path, send_bound_ms=60000) as (w, big):
        client = _partly_sent(w, big)
        w.front.suspend()
        b2 = replacement(w)
        w.b.stop_alive()
        b2.go()
        time.sleep(1.0)
        assert "written" not in b2.steps()
        w.front.resume()
        status, body = _drain(client)
        client.close()
        assert status == 200 and len(body) > BIG
        b2.wait_answering()
        assert w.front.events("released")[-1]["at"] < b2.steps()["written"]


def test_i19_suspended_past_the_bound_it_is_aborted_and_then_released(big_world, tmp_path):
    with _world_with_big_turn(big_world, tmp_path, send_bound_ms=1000) as (w, big):
        client = _partly_sent(w, big)
        w.front.suspend()
        b2 = replacement(w)
        w.b.stop_alive()
        b2.go()
        time.sleep(1.5)
        assert "written" not in b2.steps(), "it claimed past a tail that hadn't let go"
        w.front.resume()
        b2.wait_answering()
        _is_not_whole(client)
        _aborted_before_released_before_written(w, b2)


def test_i19_suspended_past_the_claim_wait_refuses(big_world, tmp_path):
    with _world_with_big_turn(big_world, tmp_path, send_bound_ms=60000) as (w, big):
        client = _partly_sent(w, big)
        w.front.suspend()
        b2 = replacement(w, claim_wait=1.0)
        w.b.stop_alive()
        b2.go()
        wait_until(lambda: b2.process.poll() is not None, limit=60)
        assert b2.process.returncode == 3
        client.close()
        w.front.resume()


def test_i21_a_client_that_does_not_drain_is_reset_and_never_gets_a_whole_answer(big_world, tmp_path):
    with _world_with_big_turn(big_world, tmp_path, send_bound_ms=1000) as (w, big):
        client = _partly_sent(w, big)
        b2 = replacement(w)
        w.b.stop_alive()
        b2.go()
        b2.wait_answering()
        _aborted_before_released_before_written(w, b2)
        _is_not_whole(client)


def _is_not_whole(client: socket.socket) -> None:
    """Everything there is to read: a reset, or fewer bytes than `Content-Length`, never all."""
    try:
        status, body = read_answer(client)
    except Short:
        client.close()
        return
    client.close()
    raise AssertionError(f"a whole answer came after the abort: {status}, {len(body)} bytes")


def _aborted_before_released_before_written(w, b2) -> None:
    aborted = w.front.events("abort")
    assert aborted, "it was never aborted"
    # The answer's own lines: another read's release doesn't count.
    held = [seen for seen in w.front.events("released") if seen["id"] == aborted[-1]["id"]]
    assert held, "it never released"
    assert aborted[-1]["at"] < held[-1]["at"] < b2.steps()["written"]


def test_i8_a_claim_held_exclusive_forwards_and_leaves_the_mirror_held(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        fh = brainlock._open_claim(str(w.brain))
        assert brainlock._lock(fh, False)
        try:
            assert read_as(w.public, w.token)[0] == 200, "Python answers it"
            assert w.front.forwards()[-1] == "claim busy"
        finally:
            brainlock._unlock(fh)
            fh.close()
        w.wait_held(w.token, limit=2.0)


@pytest.mark.parametrize("step", ["owner", "partial"])
def test_i9_i10_a_replacement_dying_in_its_claim_leaves_reads_forwarded(brain_seed, tmp_path, step):
    with world(brain_seed, tmp_path) as w:
        before = (w.brain / ".mentis.claim").read_bytes()
        b2 = replacement(w, die_at=step)
        w.b.stop_alive()
        b2.go()
        wait_until(lambda: b2.process.poll() is not None, limit=60)
        assert read_as(w.public, w.token)[0] in OLD_TOKEN_ANSWERS
        if step == "partial":
            assert (w.brain / ".mentis.claim").read_bytes() == b"part" + before[4:]
        b3 = w.python()
        b3.wait_answering()
        assert (w.brain / ".mentis.claim").read_text() == b3.boot()
        assert len((w.brain / ".mentis.claim").read_bytes()) == 32


def test_i11_a_second_python_changes_nothing(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        before = _lock_files(w.brain)
        second = w.python(port=free_port())
        wait_until(lambda: second.process.poll() is not None, limit=120)
        assert second.process.returncode == 3
        assert "another Mentis server already serves" in second.read("refused")
        assert "sole" not in second.steps(), "it was refused at the sole lock"
        assert _lock_files(w.brain) == before
        w.wait_held(w.token, limit=2.0)


def _lock_files(brain) -> dict:
    """The claim's bytes, which nothing holds, and that the lock files stay empty."""
    return {"claim": (brain / brainlock.CLAIM).read_bytes(),
            **{name: (brain / name).stat().st_size
               for name in (brainlock.SOLE_LOCK, brainlock.OWNER_LOCK, brainlock.SERVE_LOCK)}}


def test_i12_a_late_position_from_a_boot_that_let_go_earns_nothing(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        boot = w.b.boot()
        w.b.stop_alive()
        # The grant the world was made with is the only change this boot has had.
        w.b.tell("late-position", f"{boot} 1")
        wait_until(lambda: w.b.has("late-listening"), limit=10)
        for _ in range(5):
            time.sleep(0.2)
            status, _ = read_as(w.public, w.token)
            assert status != 200, "answered on a position from a boot that had let go"
        assert "lease" not in w.front.forwards()


def test_i13_a_pull_answered_by_the_old_boot_after_the_claim_is_never_adopted(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        boot = w.b.boot()
        b2 = replacement(w, pause_at="written")
        w.b.stop_alive()
        w.b.tell("late-position", f"{boot} 1")
        wait_until(lambda: w.b.has("late-listening"), limit=10)
        b2.go()
        wait_until(lambda: b2.has("paused-written"), limit=30)
        answered = len(w.front.events("last-byte"))
        for _ in range(5):
            time.sleep(0.3)
            assert read_as(w.public, w.token)[0] != 200
        assert len(w.front.events("last-byte")) == answered, "it answered from the mirror"
        b2.tell("go-written")


def test_i16_a_python_with_no_secret_on_another_port_claims(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        before = w.b.boot()
        w.b.stop_alive()
        by_hand = w.python(secret=None, port=free_port())
        by_hand.wait_answering()
        assert (w.brain / ".mentis.claim").read_text() != before
        assert "written" in by_hand.steps()
        assert read_as(w.public, w.token)[0] in OLD_TOKEN_ANSWERS, "nothing is Held again"


ROUNDS = 20


def test_load_a_suspended_front_a_killed_python_and_a_replacement(brain_seed, tmp_path):
    """4 readers per grant, the front suspended at a random moment, `B` killed and waited on until
    signalled, `B'` started and answering, the front resumed. A complete old-token 200 finishing after
    the resume fails unless a tail caught by the suspension accounts for it. An answer's last byte
    accepted after `C` fails regardless.
    """
    waited = []
    held_up = 0
    for round_number in range(ROUNDS):
        round_dir = tmp_path / f"round-{round_number}"
        round_dir.mkdir()
        with world(brain_seed, round_dir) as w:
            stop = threading.Event()
            finished: list[tuple[int, int]] = []

            def reader():
                while not stop.is_set():
                    try:
                        status, _ = read_as(w.public, w.token, timeout=30.0)
                    except (OSError, Short):
                        continue
                    finished.append((status, qpc()))

            readers = [threading.Thread(target=reader, daemon=True) for _ in range(4)]
            for thread in readers:
                thread.start()
            time.sleep(random.uniform(0.05, 0.4))
            b2 = w.python(wait_for_go=True)
            b2.wait_imported()
            w.front.suspend()
            suspended_at = qpc()
            w.b.kill()
            b2.go()
            # Either it claims while the front is suspended and goes on to serve, or a tail was
            # caught holding and it waits.
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and "written" not in b2.steps():
                time.sleep(0.02)
            bound_while_suspended = "written" in b2.steps()
            if bound_while_suspended:
                b2.wait_answering()
            w.front.resume()
            resumed_at = qpc()
            b2.wait_answering()
            written = b2.steps()["written"]
            sent_after = qpc()
            status, _ = read_as(w.public, w.token, timeout=30.0)
            assert status != 200, "a request sent after the resume was answered on the old grant"
            stop.set()
            for thread in readers:
                thread.join(timeout=60)
            trace = w.front.trace()
            by_id: dict[int, dict[str, int]] = {}
            for seen in trace:
                if seen["id"]:
                    by_id.setdefault(seen["id"], {})[seen["event"]] = seen["at"]
            # `last-byte` is traced with the locks still held, so it comes before the release
            # however the suspension falls. `released` is traced after the unlock, and a suspension
            # between the two can put that line after `C` with nothing wrong.
            for answer in by_id.values():
                if "last-byte" in answer:
                    assert answer["last-byte"] < written, "bytes accepted after C"
            caught = [a for a in by_id.values()
                      if a.get("checked", 1 << 62) < suspended_at
                      and a.get("released", 1 << 62) > suspended_at]
            late_200s = [at for status, at in finished if status == 200 and at > resumed_at]
            assert len(late_200s) <= len(caught), (
                "a complete 200 finished after the resume that no suspended tail accounts for")
            if not bound_while_suspended:
                held_up += 1
                assert caught, "it didn't bind in the time, with no tail caught holding"
            steps = b2.steps()
            waited.append((steps["owner"] - steps["sole"]) / _qpc_per_second())
            assert sent_after > written
    print(f"\nload: claim waited {min(waited):.4f}..{max(waited):.4f} s, "
          f"{held_up} rounds of {ROUNDS} held up by a caught tail")


def _qpc_per_second() -> float:
    frequency = ctypes.c_longlong()
    ctypes.windll.kernel32.QueryPerformanceFrequency(ctypes.byref(frequency))
    return float(frequency.value)
