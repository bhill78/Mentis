"""Guarantee 1, under load: `docs/rust/R3-mirror.md`, sections 1 and 8. Any read *started* after a
revoke returned must get Python's 403. Fence time is reported, never a gate.
"""

from __future__ import annotations

import socket
import statistics
import threading
import time

import pytest

from mentis.mirror import FENCE
from tests.front.mirror_harness import World, free_port, read_as
from tests.front.test_mirror_protocol import _answered_count

CYCLES = 300
#: A revoke that fences takes `FENCE`, so these rounds are few by what they cost. Each still has the
#: readers running across the revoke, which is the case.
CYCLES_THAT_FENCE = 10
READERS = 4


class Proxy:
    """On the public port as far as a push goes: it stalls, or passes it on and drops the ack."""

    def __init__(self, target: int, mode: str):
        self.target, self.mode = target, mode
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(64)
        self.port = self.listener.getsockname()[1]
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(conn,), daemon=True).start()

    def _one(self, conn):
        with conn:
            got = b""
            while b"\r\n\r\n" not in got:
                more = conn.recv(65536)
                if not more:
                    return
                got += more
            if self.mode == "stall":
                time.sleep(1.5)
                return
            head, _, body = got.partition(b"\r\n\r\n")
            length = next(int(line.split(b":")[1]) for line in head.split(b"\r\n")
                          if line.lower().startswith(b"content-length"))
            while len(body) < length:
                body += conn.recv(65536)
            with socket.create_connection(("127.0.0.1", self.target), timeout=5) as onward:
                onward.sendall(head + b"\r\n\r\n" + body)
                while onward.recv(65536):
                    pass
            # Applied, and the ack is lost: this closes without a word.

    def close(self):
        self.listener.close()


def _cycles(w, cycles: int, *, around=None) -> list[float]:
    """Mint, read, revoke, read: `readers` on the grant all through."""
    fences = []
    stop = threading.Event()
    current = {"token": w.token, "since": None}
    bad = []

    def reader():
        while not stop.is_set():
            token, gone_at = current["token"], current["since"]
            began = time.perf_counter()
            try:
                status, _ = read_as(w.public, token, timeout=30.0)
            except OSError:
                continue
            if gone_at is not None and began >= gone_at and status == 200:
                bad.append((token, began - gone_at))

    threads = [threading.Thread(target=reader, daemon=True) for _ in range(READERS)]
    for thread in threads:
        thread.start()
    try:
        for _ in range(cycles):
            token = w.b.session()
            current.update(token=token, since=None)
            time.sleep(0.01)
            if around:
                around()
            began = time.perf_counter()
            w.b.end_session(token)
            done = time.perf_counter()
            current["since"] = done
            fences.append(done - began)
            if around:
                around()
            status, body = read_as(w.public, token, timeout=30.0)
            assert status == 403 and b"live worker grant" in body, (status, body[:200])
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=60)
    assert bad == [], f"reads started after a revoke returned that were answered: {bad[:5]}"
    return fences


def _report(name: str, fences: list[float]) -> None:
    print(f"\n{name}: {len(fences)} revokes, median {statistics.median(fences) * 1000:.1f} ms, "
          f"max {max(fences) * 1000:.1f} ms")


def _world(brain_seed, tmp_path, **options):
    import shutil
    brain = tmp_path / "brain"
    shutil.copytree(brain_seed, brain)
    return World(brain, tmp_path, **options)


def test_load_every_read_started_after_a_revoke_gets_python_s_403(brain_seed, tmp_path):
    w = _world(brain_seed, tmp_path)
    try:
        _report("plain", _cycles(w, CYCLES))
        assert _answered_count(w) > CYCLES, "the mirror answered almost none of these"
    finally:
        w.end()


def test_with_the_front_suspended_a_revoke_fences_and_nothing_old_is_answered(brain_seed, tmp_path):
    w = _world(brain_seed, tmp_path)
    try:
        fences = []
        for _ in range(CYCLES_THAT_FENCE):
            token = w.b.session()
            w.wait_held(token)
            w.front.suspend()
            began = time.perf_counter()
            w.b.end_session(token)
            fences.append(time.perf_counter() - began)
            w.front.resume()
            status, body = read_as(w.public, token, timeout=30.0)
            assert status == 403 and b"live worker grant" in body, (status, body[:200])
        _report("front suspended", fences)
        assert max(fences) <= FENCE + 2.0, "reported, and only a wild miss fails it"
    finally:
        w.end()


@pytest.mark.parametrize("mode", ["stall", "drop-ack"])
def test_with_a_push_lost_a_revoke_fences_and_nothing_old_is_answered(brain_seed, tmp_path, mode):
    brain_dir = tmp_path
    import shutil
    brain = brain_dir / "brain"
    shutil.copytree(brain_seed, brain)
    public = free_port()
    # Python pushes through the proxy, so `--answers-at` names the proxy, and clients use the front.
    proxy = Proxy(public, mode)
    w = World.__new__(World)
    w.brain, w.work = brain, tmp_path
    w.public, w.private = public, free_port()
    w.pythons, w.counter = [], 0
    from tests.front.mirror_harness import Front
    w.b = w.python(answers_at=f"http://127.0.0.1:{proxy.port}")
    w.b.wait_answering()
    w.front = Front(brain, public, w.private, directory=tmp_path / "front")
    w.front.wait_answering()
    try:
        fences = []
        for _ in range(CYCLES_THAT_FENCE):
            token = w.b.session()
            w.wait_held(token)
            began = time.perf_counter()
            w.b.end_session(token)
            fences.append(time.perf_counter() - began)
            status, body = read_as(public, token, timeout=30.0)
            assert status == 403 and b"live worker grant" in body, (status, body[:200])
        _report(mode, fences)
    finally:
        w.end()
        proxy.close()
