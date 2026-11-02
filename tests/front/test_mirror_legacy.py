"""A Python from before this build, against a real front. `docs/rust/R3-mirror.md`, section 8.

`L` is a real `python -m mentis.web` exported with `git archive` from the rollback tag `r1`: exactly
the commit the deployed rollback runs, `89d8f94`. It imports nothing of this build, and it runs on a
copy of BRAIN-SEED.
"""

from __future__ import annotations

import pathlib
import json
import shutil
import subprocess
import sys
import tarfile
import time

import pytest

from tests.front.mirror_harness import (REPO, SECRET, Front, ServerPython, environment, free_port,
                                        http, in_background, kill_tree, read_as, wait_until, world)

#: The rollback tag, and the commit it has to be. A moved tag fails here, not silently elsewhere.
ROLLBACK_TAG = "r1"
ROLLBACK_COMMIT = "89d8f94519fe6e847ad0b4ade2a90bd9cfe2bea1"
REFUSAL = "another Mentis server already serves"


@pytest.fixture(scope="module")
def rollback_code(tmp_path_factory) -> pathlib.Path:
    resolved = subprocess.run(["git", "rev-parse", f"{ROLLBACK_TAG}^{{commit}}"], cwd=REPO,
                              capture_output=True, text=True, check=True).stdout.strip()
    assert resolved == ROLLBACK_COMMIT, f"{ROLLBACK_TAG} is at {resolved}"
    archive = tmp_path_factory.mktemp("rollback") / "code.tar"
    subprocess.run(["git", "archive", "--format=tar", "-o", str(archive), ROLLBACK_TAG,
                    "mentis", "pyproject.toml"], cwd=REPO, check=True)
    code = archive.parent / "code"
    code.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(code, filter="data")
    assert b"SOLE_LOCK" not in (code / "mentis/spine/brainlock.py").read_bytes()
    return code


class Legacy:
    """`L`, started as a launcher's `--only python --code` would: no harness, no fault point."""

    def __init__(self, code: pathlib.Path, brain: pathlib.Path, port: int, public: int,
                 log: pathlib.Path):
        self.port = port
        self.log = log
        with open(log, "ab") as out:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "mentis.web", str(brain), "--host", "127.0.0.1",
                 "--port", str(port), "--workspace", str(log.parent),
                 "--mars", "workload-no-mars-here",
                 "--answers-at", f"http://127.0.0.1:{public}"],
                cwd=str(code), env=environment(SECRET), stdout=out, stderr=subprocess.STDOUT)

    def wait_answering(self) -> None:
        def up():
            assert self.process.poll() is None, self.log.read_text(errors="replace")
            try:
                return http(self.port, "GET", "/api/server", timeout=2.0)[0] == 200
            except OSError:
                return False
        wait_until(up, message="L never answered")

    def refused(self, within: float = 120.0) -> str:
        self.process.wait(timeout=within)
        assert self.process.returncode == 3, self.log.read_text(errors="replace")
        return self.log.read_text(errors="replace")

    def end(self) -> None:
        if self.process.poll() is None:
            kill_tree(self.process.pid)
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass


def _gave_up_serve_and_sole(w) -> None:
    """The teardown order @Quill named: `.mentis.serve.lock` gone, the owner lock still held, and the
    process not signalled, so the stale claim, the owner lock and the watch all still say `B`."""
    w.b.tell("give-up")
    wait_until(lambda: w.b.has("gave-up"), limit=10)


def test_i17a_an_older_python_past_the_serve_lock_stops_the_mirror(brain_seed, rollback_code, tmp_path):
    with world(brain_seed, tmp_path) as w:
        _gave_up_serve_and_sole(w)
        legacy = Legacy(rollback_code, w.brain, free_port(), w.public, tmp_path / "L.log")
        try:
            legacy.wait_answering()
            status, _ = read_as(w.public, w.token)
            assert status != 200, "answered from the mirror beside an older Python"
            assert w.front.forwards()[-1] == "serve lock held exclusive", w.front.forwards()
            assert b"owner lock" not in (w.brain / ".mentis.claim").read_bytes()
        finally:
            legacy.end()


def test_i17b_a_tail_stopped_in_its_send_makes_an_older_python_refuse(brain_seed, rollback_code, tmp_path):
    with world(brain_seed, tmp_path) as w:
        w.front.arm("checked")
        reading = in_background(lambda: read_as(w.public, w.token))
        w.front.wait_stopped("checked")
        w.front.suspend()
        w.b.kill()
        port = free_port()
        legacy = Legacy(rollback_code, w.brain, port, w.public, tmp_path / "L.log")
        try:
            said = legacy.refused()
            assert REFUSAL in said, said
            w.front.go_on("checked")
            w.front.resume()
            assert reading.result()[0] == 200, "the answer completes"
            again = Legacy(rollback_code, w.brain, port, w.public, tmp_path / "L2.log")
            try:
                again.wait_answering()
            finally:
                again.end()
        finally:
            legacy.end()


def test_i17c_a_read_queued_on_a_suspended_front_with_the_old_owner_lock_still_held(
        brain_seed, rollback_code, tmp_path):
    """The form the serve lock alone decides: `B` still holds its owner lock, so the kill's own form,
    below, can't tell whether the tail looked at the serve lock at all."""
    with world(brain_seed, tmp_path) as w:
        w.front.suspend()
        queued = in_background(lambda: read_as(w.public, w.token))
        _gave_up_serve_and_sole(w)
        legacy = Legacy(rollback_code, w.brain, free_port(), w.public, tmp_path / "L.log")
        try:
            legacy.wait_answering()
            w.front.resume()
            status, _ = queued.result()
            assert status != 200
            assert "serve lock held exclusive" in w.front.forwards()
        finally:
            legacy.end()


def test_i17c_killed_a_read_queued_on_a_suspended_front_is_never_a_200(
        brain_seed, rollback_code, tmp_path):
    with world(brain_seed, tmp_path) as w:
        w.front.suspend()
        queued = in_background(lambda: read_as(w.public, w.token))
        w.b.kill()
        legacy = Legacy(rollback_code, w.brain, free_port(), w.public, tmp_path / "L.log")
        try:
            legacy.wait_answering()
            w.front.resume()
            assert queued.result()[0] != 200
        finally:
            legacy.end()


def test_i17d_with_the_older_python_gone_the_read_is_answered_and_holds_the_next_off(
        brain_seed, rollback_code, tmp_path):
    with world(brain_seed, tmp_path) as w:
        _gave_up_serve_and_sole(w)
        legacy = Legacy(rollback_code, w.brain, free_port(), w.public, tmp_path / "L.log")
        legacy.wait_answering()
        legacy.end()
        wait_until(lambda: _free(w.brain), limit=30)
        # Nothing holds the serve lock exclusive now, and `B` still holds its owner lock. That can only
        # be answered by a mirror still Held, and a tail's discard has dropped it if L was seen.
        w.b.tell("late-position", f"{w.b.boot()} 1")
        w.front.arm("checked")
        reading = in_background(lambda: read_as(w.public, w.token))
        try:
            w.front.wait_stopped("checked", limit=5.0)
        except AssertionError:
            # The discard happened: a read while L ran saw it, and nothing is Held again. Safe.
            reading.result()
            return
        further = Legacy(rollback_code, w.brain, free_port(), w.public, tmp_path / "L3.log")
        try:
            assert REFUSAL in further.refused()
        finally:
            further.end()
            w.front.go_on("checked")
        assert reading.result()[0] == 200


def _free(brain: pathlib.Path) -> bool:
    from mentis.spine import brainlock
    got = brainlock._take(str(brain), brainlock.SERVE_LOCK, False)
    if got is None:
        return False
    got.release()
    return True


def test_i17e_this_build_refuses_beside_an_older_python_and_claims_after_it(
        brain_seed, rollback_code, tmp_path):
    brain = tmp_path / "brain"
    shutil.copytree(brain_seed, brain)
    public, private = free_port(), free_port()
    legacy = Legacy(rollback_code, brain, private, public, tmp_path / "L.log")
    try:
        legacy.wait_answering()
        mine = ServerPython(brain, free_port(), control=tmp_path / "mine",
                            answers_at=f"http://127.0.0.1:{public}")
        wait_until(lambda: mine.process.poll() is not None, limit=120)
        assert mine.process.returncode == 3
        assert REFUSAL in mine.read("refused")
        assert not (brain / ".mentis.claim").exists(), "it changed nothing"
        front = Front(brain, public, private, directory=tmp_path / "front")
        try:
            front.wait_answering()
            status, body = http(private, "GET", "/private/grants",
                                headers={"X-Mentis-Boot-Secret": SECRET})
            assert status == 404, body
            token = http(private, "POST", "/api/worker/session", {"runtime": "claude"},
                         {"X-Mentis-Client": "1"})
            assert token[0] == 200
            status, _ = read_as(public, json.loads(token[1])["grant"])
            assert status == 200, "Python answers it"
            assert not front.events("last-byte"), "never Held on an older Python"
        finally:
            front.end()
    finally:
        legacy.end()
    wait_until(lambda: _free(brain), limit=30)
    after = ServerPython(brain, free_port(), control=tmp_path / "after",
                         answers_at=f"http://127.0.0.1:{public}")
    try:
        after.wait_answering()
        assert len((brain / ".mentis.claim").read_bytes()) == 32
    finally:
        after.end()


@pytest.mark.parametrize("front_first", [True, False])
def test_rolling_back_both_ways_round(brain_seed, rollback_code, tmp_path, front_first):
    with world(brain_seed, tmp_path) as w:
        if front_first:
            w.front.end()
        w.b.kill()
        time.sleep(0.2)
        legacy = Legacy(rollback_code, w.brain, w.private, w.public, tmp_path / "L.log")
        try:
            legacy.wait_answering()
            if not front_first:
                assert read_as(w.public, w.token)[0] != 200, "the old token is never answered"
        finally:
            legacy.end()
