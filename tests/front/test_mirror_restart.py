"""A restart under a held mirror: `docs/rust/R3-mirror.md`, section 8. Grants have no clock, so what
"expired" means here is the previous boot. 20 rounds of each.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import threading

import pytest

from tests.front import mirror_harness, pair
from tests.front.mirror_harness import (Front, World, free_port, in_background, read_as, world)

ROUNDS = 20


def test_a_front_restart_during_a_run_rebuilds_the_mirror(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        token = w.token
        w.front.end()
        w.front = Front(w.brain, w.public, w.private, directory=tmp_path / "front2")
        w.front.wait_answering()
        # Forwarded or not, the agent's next read works.
        assert read_as(w.public, token)[0] == 200
        w.wait_held(token)


def test_a_front_that_could_not_take_the_port_is_not_taken_for_the_one_on_it(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        second = Front(w.brain, w.public, w.private, directory=tmp_path / "second")
        with pytest.raises(AssertionError, match="cannot listen"):
            second.wait_answering()


def test_ending_a_process_tree_does_not_rest_on_taskkill(monkeypatch):
    """Where `taskkill` is refused, as under a restricted token, nothing has to change here."""
    def no_taskkill(*_args, **_kwargs):
        raise AssertionError("taskkill was asked")

    monkeypatch.setattr(mirror_harness.subprocess, "run", no_taskkill)
    # In a virtual environment this is a stub with the real interpreter under it: two processes.
    started = subprocess.Popen(
        [sys.executable, "-c", "import time; print('up', flush=True); time.sleep(120)"],
        stdout=subprocess.PIPE)
    try:
        assert started.stdout.readline().strip() == b"up"
        tree = pair.process_tree(started.pid)
        mirror_harness.kill_tree(started.pid)
        started.wait(timeout=30)
        assert not [one for one in tree if pair.alive(one)]
    finally:
        started.kill()
        started.stdout.close()


@pytest.mark.parametrize("round_number", range(ROUNDS))
def test_a_read_queued_on_a_suspended_front_is_never_a_200_after_a_kill(
        brain_seed, tmp_path, round_number):
    with world(brain_seed, tmp_path) as w:
        w.front.suspend()
        queued = in_background(lambda: read_as(w.public, w.token))
        w.b.kill()
        replacement = w.python()
        replacement.wait_answering()
        w.front.resume()
        status, body = queued.result()
        assert status in (403, 503), (status, body[:200])
        new_token = replacement.session()
        w.wait_held(new_token)


class HeldOpenProxy:
    """On `--upstream`: passes everything through, and when Python dies keeps the client's connection
    open, so the front's poll connection never sees its end."""

    def __init__(self, target: int):
        self.target = target
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
        try:
            onward = socket.create_connection(("127.0.0.1", self.target), timeout=5)
        except OSError:
            conn.close()    # Nothing there, and this never had a request to keep open.
            return
        threading.Thread(target=self._pass, args=(onward, conn, True), daemon=True).start()
        self._pass(conn, onward, False)

    @staticmethod
    def _pass(source, sink, hold_open):
        try:
            while True:
                got = source.recv(65536)
                if not got:
                    break
                sink.sendall(got)
        except OSError:
            pass
        if hold_open:
            return      # The client's connection stays open, saying nothing.
        for sock in (source, sink):
            try:
                sock.close()
            except OSError:
                pass

    def close(self):
        self.listener.close()


@pytest.mark.parametrize("round_number", range(ROUNDS))
def test_with_the_poll_connection_held_open_a_read_after_a_kill_is_never_a_200(
        brain_seed, tmp_path, round_number):
    brain = tmp_path / "brain"
    shutil.copytree(brain_seed, brain)
    w = World.__new__(World)
    w.brain, w.work = brain, tmp_path
    w.public, w.private = free_port(), free_port()
    w.pythons, w.counter = [], 0
    proxy = HeldOpenProxy(w.private)
    w.b = w.python()
    w.b.wait_answering()
    w.front = Front(brain, w.public, proxy.port, directory=tmp_path / "front")
    w.front.wait_answering()
    try:
        w.token = w.b.session()
        w.wait_held(w.token)
        w.b.kill()
        status, body = read_as(w.public, w.token)
        assert status != 200, body[:200]
        assert "lease" not in w.front.forwards()
    finally:
        w.end()
        proxy.close()
