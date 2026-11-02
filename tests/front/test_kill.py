"""Row E: hard kills under the writing load, with the acknowledgement ledger. `R1-acceptance.md`, "E".

60: K1 to K6, 10 runs each, parametrised so pytest counts every one. Each run is on its own fresh,
checked BRAIN-COPY, about 95 s, so about 95 minutes. It is a correctness row with no time limit.

Each kill is placed by the test, not by timing:

    A held write   This process holds SQLite's write lock on the run's copy. Python's write waits
                   inside its transaction, before commit, for as long as the test likes.
    A held send    The call's body is sent half at a time, by the real `_over`.
    A held reply   The front is suspended, the write released, the commit seen in the record, and
                   only then is the suspended front killed, with the reply on its way to it.
    A held read    Python is suspended, so a read sent through the front can't be answered, and the
                   front is killed with the caller still waiting on it.
"""

from __future__ import annotations

import contextlib
import http.client
import sqlite3
import threading
import time

import pytest

from tests.front import restart_messages
from tests.front.pair import (Pair, alive, process_tree, rows, session_grant, suspend, terminate,
                              told, wait_gone)
from tests.front.verifiers import assert_both_verify
from tools.r1 import ledger as ledger_tool

RUNS = range(10)
#: Long enough for a forwarded call to be in Python's hands. Only the "in hand" of a held write
#: rests on this, and a call that wasn't yet would give `Python-unreached`, which fails.
IN_HAND_S = 1.0
LOAD_S = 2.0


@contextlib.contextmanager
def write_lock(brain):
    """SQLite's write lock on the run's copy, held by this process."""
    conn = sqlite3.connect(brain / "corpus.db", isolation_level=None, timeout=30)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield
    finally:
        conn.execute("ROLLBACK")
        conn.close()


class Run:
    """A pair on a fresh BRAIN-COPY, a session on it, and the ledger of what it was told."""

    def __init__(self, pair, ledger_path):
        self.pair = pair
        self.grant = session_grant(pair.port)["grant"]
        self.ledger_path = ledger_path
        self.ledger = ledger_tool.Ledger(ledger_path)
        self.writer = ledger_tool.Writer(self.ledger)
        self.stopping = threading.Event()
        self.number = 0
        self.thread = threading.Thread(target=self._load, daemon=True)
        self.told_to_writer: list[str] = []

    def call(self, name: str, args: dict):
        return told(self.pair.url, self.pair.brain, name, args, self.grant)

    def row_of(self, name: str):
        found = rows(self.pair.brain, "SELECT id, seq, hash FROM entry WHERE "
                                      "def_name='conversation' AND json_extract(body,'$.name')=?",
                     name)
        return found

    def _write_one(self):
        self.number += 1
        name = f"E load {self.number}"

        def send():
            answer, message = self.call("open_conversation", {"name": name})
            if message:
                raise ConnectionError(message)
            found = rows(self.pair.brain, "SELECT id, seq, hash FROM entry WHERE id = ?",
                         answer["conversation"])
            return (found[0][0], "entry", found[0][1], found[0][2])

        return self.writer.write(send)

    def _load(self):
        while not self.stopping.is_set():
            try:
                self._write_one()
            except ConnectionError as refused:
                self.told_to_writer.append(str(refused))
                time.sleep(0.05)

    def load(self):
        """The writing load, running, with rows already acknowledged."""
        self.thread.start()
        deadline = time.monotonic() + 60
        time.sleep(LOAD_S)
        while not ledger_tool.read(self.ledger_path):
            assert time.monotonic() < deadline, f"nothing was acknowledged: {self.told_to_writer}"
            time.sleep(0.05)

    def stop_load(self):
        self.stopping.set()
        self.thread.join(timeout=60)
        assert not self.thread.is_alive()
        self.ledger.close()

    def in_thread(self, name: str, args: dict):
        """Make a call on its own thread. Returns what to wait on, and where the result lands."""
        result: dict = {}

        def run():
            result["answer"], result["message"] = self.call(name, args)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread, result


def judge(message, cases, *, answered_is_allowed=False):
    if message is None:
        assert answered_is_allowed, f"the write was answered: it should have been cut off ({cases})"
        return
    assert restart_messages.decide(message, cases), f"not allowed for {cases}: {message}"


def everything_after(run: Run, killed_tree: list[int], write_name: str | None) -> None:
    """After each run, and after Python restarts. `R1-acceptance.md`, "E"'s five points."""
    pair = run.pair
    run.stop_load()
    assert not any(alive(pid) for pid in killed_tree), "an orphan process"

    if not alive(pair.python_pid):
        pair.restart_python()
    if not alive(pair.front_pid):
        pair.restart_front()
    assert pair.answers(), "it doesn't come back, so a lock or the WAL has been left behind"

    conn = sqlite3.connect(f"file:{(pair.brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    try:
        wrong = ledger_tool.verify(run.ledger_path, conn)
    finally:
        conn.close()
    assert not wrong, wrong
    assert ledger_tool.read(run.ledger_path), "the run acknowledged nothing, so it showed nothing"

    # The write answered during the kill: all of it or none of it, by its one Conversation and
    # the act that opened it, which share a transaction.
    if write_name:
        found = run.row_of(write_name)
        assert len(found) <= 1, f"{write_name} is there {len(found)} times"
        if found:
            acts = rows(pair.brain, "SELECT COUNT(*) FROM operational WHERE conversation = ?",
                        found[0][0])[0][0]
            assert acts >= 1, f"{write_name} is there without the act that goes with it"

    assert_both_verify(pair)


def _k1(run: Run):
    """Front, during a forwarded write's request body."""
    pair = run.pair
    name = "E K1"
    halfway, killed = threading.Event(), threading.Event()
    original = http.client.HTTPConnection.send
    target: list[threading.Thread] = []

    def send(self, data):
        body = isinstance(data, (bytes, bytearray)) and data.startswith(b'{"corpus"')
        if target and threading.current_thread() is target[0] and body:
            half = len(data) // 2
            original(self, data[:half])
            halfway.set()
            assert killed.wait(60)
            return original(self, data[half:])
        return original(self, data)

    http.client.HTTPConnection.send = send
    try:
        thread, result = run.in_thread("open_conversation", {"name": name})
        target.append(thread)
        # The thread may have got to `send` before `target` was set: it can't have, because it
        # opens its connection first, but if so the wait below fails rather than passing.
        assert halfway.wait(60), "the body was never sent half at a time"
        time.sleep(0.5)  # the front has had the half that was sent
        tree = process_tree(pair.front_pid)
        pair.kill_front()
        killed.set()
        thread.join(60)
    finally:
        http.client.HTTPConnection.send = original
    judge(result["message"], ["B-sending", "B-sent"])
    assert not run.row_of(name), "Python never had the whole request"
    return tree, name


def _k2(run: Run):
    """Front, with Python committed and the response on its way back."""
    pair = run.pair
    name = "E K2"
    with write_lock(pair.brain):
        thread, result = run.in_thread("open_conversation", {"name": name})
        time.sleep(IN_HAND_S)
        front = pair.front_pid
        suspend(front)
    try:
        deadline = time.monotonic() + 60
        while not run.row_of(name):
            assert time.monotonic() < deadline, "Python never committed it"
            time.sleep(0.02)
    finally:
        terminate(front)
    thread.join(60)
    judge(result["message"], ["B-sent", "B-reply"])
    assert len(run.row_of(name)) == 1
    return [front], name


def _k3(run: Run):
    """Python, inside a write, before commit."""
    pair = run.pair
    name = "E K3"
    tree = process_tree(pair.python_pid)
    with write_lock(pair.brain):
        thread, result = run.in_thread("open_conversation", {"name": name})
        time.sleep(IN_HAND_S)
        pair.kill_python()
    thread.join(60)
    judge(result["message"], ["Python-reached"])
    assert not run.row_of(name), "it was killed before commit"
    return tree, name


def _k4(run: Run):
    """Python, straight after acknowledging a write. The next write is in its hands by then."""
    pair = run.pair
    name = "E K4"
    tree = process_tree(pair.python_pid)
    acknowledged = run._write_one()
    with write_lock(pair.brain):
        thread, result = run.in_thread("open_conversation", {"name": name})
        time.sleep(IN_HAND_S)
        pair.kill_python()
    thread.join(60)
    judge(result["message"], ["Python-reached"])
    assert rows(pair.brain, "SELECT COUNT(*) FROM entry WHERE id = ?", acknowledged[0])[0][0] == 1
    return tree, name


def _k5(run: Run):
    """Both, during writes."""
    pair = run.pair
    name = "E K5"
    tree = process_tree(pair.python_pid) + [pair.front_pid]
    with write_lock(pair.brain):
        thread, result = run.in_thread("open_conversation", {"name": name})
        time.sleep(IN_HAND_S)
        pair.kill_python()
        pair.kill_front()
    thread.join(60)
    judge(result["message"], ["A", "B-sending", "B-sent", "B-reply", "Python-reached"])
    return tree, name


def _k6(run: Run):
    """Front, with a forwarded read in hand, under the writes.

    This is what `R1-acceptance.md` says K6 places, and all it places. The read is the worker's, so
    Python is the one reading: a scope of the front's own can't be held open without a hook, and row
    H2 is where one is tested on purpose. Python is suspended before the read is sent and resumed
    only after the kill, so the read can't have been answered, and the caller still waiting at the
    kill is what shows it. `A` is not allowed here, because that would be a read that never got in."""
    pair = run.pair
    tree = process_tree(pair.front_pid)
    pair.suspend_python()
    try:
        thread, result = run.in_thread("kinds", {})
        time.sleep(IN_HAND_S)
        assert thread.is_alive(), "the read was answered with Python suspended"
        pair.kill_front()
        thread.join(60)
        assert not thread.is_alive(), "the read kept waiting through the kill"
    finally:
        pair.resume_python()
    judge(result["message"], ["B-sent", "B-reply"])
    return tree, None


POINTS = {"K1": _k1, "K2": _k2, "K3": _k3, "K4": _k4, "K5": _k5, "K6": _k6}


@pytest.mark.parametrize("run_number", RUNS)
@pytest.mark.parametrize("point", POINTS)
def test_kill(point, run_number, brain_copy, tmp_path):
    with Pair(brain_copy) as pair:
        run = Run(pair, tmp_path / "ledger.jsonl")
        try:
            run.load()
            tree, name = POINTS[point](run)
            # What the load was told as it went must be on the list as well.
            for message in run.told_to_writer:
                assert restart_messages.decide(
                    message, ["A", "B-sending", "B-sent", "B-reply", "Python-reached",
                              "Python-unreached"]), message
            everything_after(run, tree, name)
        finally:
            run.stopping.set()
    for pid in tree:
        assert wait_gone(pid), f"{pid} is still running"

