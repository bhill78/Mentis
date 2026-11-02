"""Row D: the locks. `R1-acceptance.md`, "D: locks, 7". PAIR, on a fresh BRAIN-SEED.

Python holds `.mentis.lock` shared too, so a refusal with Python up shows nothing about the front.
Where a test is about the front's hold, Python is killed first, or never started.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import time

import pytest

from mentis.spine import backup, brainlock, migrations
from tests.front import test_sqlite as pair


@pytest.fixture
def brain(brain_seed, tmp_path):
    copy = tmp_path / "brain"
    shutil.copytree(brain_seed, copy)
    return copy


def test_migrate_refuses_while_the_front_has_the_brain_open(brain):
    with pair.running_pair(brain) as running:
        running.kill_python()
        time.sleep(0.5)
        with pytest.raises(brainlock.BrainBusy, match="open in another"):
            migrations.apply(str(brain))
        assert pair.get("/api/pulse")[0] == 200, "the front that refused it is still up"


def test_restore_refuses_while_the_front_has_the_brain_open(brain, tmp_path):
    taken = backup.backup(str(brain), str(tmp_path / "taken"))
    assert taken
    with pair.running_pair(brain) as running:
        running.kill_python()
        time.sleep(0.5)
        with pytest.raises(brainlock.BrainBusy, match="open in another"):
            backup.restore(str(brain), str(tmp_path / "taken"), "not reached")
        assert pair.get("/api/pulse")[0] == 200


def test_the_front_refuses_while_restoring_exists(brain):
    (brain / brainlock.RESTORING).write_text("{}", encoding="utf-8")
    status, said = pair.front_refusal(brain)
    assert status == pair.EXIT_REFUSED, said
    assert "being restored" in said


def test_the_front_refuses_on_an_unsupported_ledger(brain):
    conn = sqlite3.connect(brain / "corpus.db")
    try:
        columns = [r[1] for r in conn.execute("PRAGMA table_info(schema_migration)")]
        row = dict(zip(columns, conn.execute(
            "SELECT * FROM schema_migration ORDER BY seq DESC LIMIT 1").fetchone()))
        row.update(seq=row["seq"] + 1, id="9999-from-a-newer-build", checksum="0" * 64,
                   from_version=row["to_version"], to_version=row["to_version"] + 1)
        conn.execute(f"INSERT INTO schema_migration ({','.join(row)}) "
                     f"VALUES ({','.join('?' * len(row))})", tuple(row.values()))
        conn.commit()
    finally:
        conn.close()
    status, said = pair.front_refusal(brain)
    assert status == pair.EXIT_REFUSED, said
    assert "does not read this Brain's schema" in said
    assert "9999-from-a-newer-build" in said


def test_a_second_python_on_the_same_brain_refuses_on_the_serve_lock(brain):
    with pair.running_pair(brain) as running:
        second = subprocess.run(
            [pair.venv_python(), "-m", "mentis.web", str(brain), "--port", "8853",
             "--workspace", str(running.run / "ws"), "--mars", pair.NO_MARS],
            cwd=pair.code(), env=pair.environment(), capture_output=True, text=True,
            encoding="utf-8", timeout=120)
    assert second.returncode == pair.EXIT_REFUSED, second.stdout + second.stderr
    assert "another Mentis server already serves" in second.stdout + second.stderr


def test_the_fronts_shared_lock_does_not_stop_python_starting(brain):
    private = pair.PORT + 10000
    with pair.running_front(brain, upstream_port=private):
        run = pair.run_dir(brain)
        with open(run / "python.log", "ab") as log:
            python = subprocess.Popen(
                [pair.venv_python(), "-m", "mentis.web", str(brain), "--host", "127.0.0.1",
                 "--port", str(private), "--workspace", str(run / "ws"), "--mars", pair.NO_MARS],
                cwd=pair.code(), env=pair.environment(), stdout=log, stderr=subprocess.STDOUT)
        try:
            pair.wait_for_server(private, lambda: python.poll() is None)
            # The front's hold is still there, beside Python's, and the front reaches it.
            assert pair.get("/api/server")[0] == 200
        finally:
            pair.kill(python.pid)
            python.wait(timeout=30)


def test_a_killed_front_leaves_no_lock_behind(brain):
    with pair.running_front(brain) as front:
        assert brainlock.is_open(str(brain)), "the front holds it, with no Python up"
        pair.kill(front.pid)
        front.wait(timeout=30)
        deadline = time.monotonic() + 5
        while brainlock.is_open(str(brain)):
            assert time.monotonic() < deadline, "the lock outlived the process"
            time.sleep(0.05)
    brainlock.exclusive(str(brain), "show nothing holds it").release()
