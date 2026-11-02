"""The claim: `docs/rust/R3-mirror.md`, section 4, "A Python's start".

**The real cross-process read:** a real Python, through the real claim code, writes a boot and
releases, and at that moment a real Rust process, through the tail's own read, must see all 32 bytes,
over 1,000 rounds with no sleep, no flush of its own and the writer still alive. `MENTIS_R3_CLAIM_READER`
names `claim_reader.exe`. Without it those tests fail: nothing here skips.
"""

from __future__ import annotations

import os
import pathlib
import secrets
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from mentis.spine import brainlock

ROUNDS = 1000


def reader() -> str:
    named = os.environ.get("MENTIS_R3_CLAIM_READER")
    assert named, "MENTIS_R3_CLAIM_READER isn't set"
    return named


def boot() -> str:
    return secrets.token_hex(16)


def test_a_claim_is_32_bytes_at_offset_0_through_the_locked_handle(tmp_path):
    (tmp_path / brainlock.CLAIM).write_bytes(b"z" * 40)
    who = boot()
    held = brainlock.serve(str(tmp_path), boot_id=who)
    try:
        assert (tmp_path / brainlock.CLAIM).read_bytes() == who.encode()
    finally:
        held.release()


def test_a_second_handle_cannot_read_what_the_lock_holds(tmp_path):
    """Why the write has to go through the handle holding the lock: on Windows a second handle in the
    same process can't touch an exclusively locked range. Design says so from memory; this runs it."""
    (tmp_path / brainlock.CLAIM).write_bytes(b"a" * 32)
    fh = brainlock._open_claim(str(tmp_path))
    assert brainlock._lock(fh, False)
    try:
        if sys.platform == "win32":
            with pytest.raises(OSError):
                with open(tmp_path / brainlock.CLAIM, "rb") as other:
                    other.read(1)
    finally:
        brainlock._unlock(fh)
        fh.close()


def test_a_short_write_refuses_the_start_and_lets_everything_go(tmp_path, monkeypatch):
    real_write = os.write
    monkeypatch.setattr(brainlock.os, "write", lambda fd, data: 0 if len(data) == 32 else real_write(fd, data))
    with pytest.raises(brainlock.BrainBusy, match="could not claim"):
        brainlock.serve(str(tmp_path), boot_id=boot())
    monkeypatch.undo()
    held = brainlock.serve(str(tmp_path), boot_id=boot())
    held.release()


def test_a_python_alone_on_a_brain_never_mirrored_is_as_it_was(tmp_path):
    held = brainlock.serve(str(tmp_path), port=1)
    try:
        assert isinstance(held, brainlock.Lock) and not held.shared
        for name in (brainlock.SOLE_LOCK, brainlock.OWNER_LOCK, brainlock.CLAIM):
            assert not (tmp_path / name).exists(), name
    finally:
        held.release()


def test_any_python_claims_once_the_claim_exists(tmp_path):
    brainlock.serve(str(tmp_path), boot_id=boot()).release()
    before = (tmp_path / brainlock.CLAIM).read_bytes()
    held = brainlock.serve(str(tmp_path))
    try:
        assert isinstance(held, brainlock.Serving)
        assert (tmp_path / brainlock.CLAIM).read_bytes() != before
    finally:
        held.release()


def test_every_pair_that_refused_still_refuses(tmp_path):
    held = brainlock.serve(str(tmp_path), boot_id=boot())
    try:
        with pytest.raises(brainlock.BrainBusy, match="another Mentis server already serves"):
            brainlock.serve(str(tmp_path), boot_id=boot())
        assert brainlock._take(str(tmp_path), brainlock.SERVE_LOCK, False) is None, \
            "what `exchange/apply.py` asks for, and a Python from before this build"
    finally:
        held.release()
    old = brainlock._take(str(tmp_path), brainlock.SERVE_LOCK, False)
    try:
        with pytest.raises(brainlock.BrainBusy, match="another Mentis server already serves"):
            brainlock.serve(str(tmp_path), boot_id=boot())
    finally:
        old.release()


def test_past_the_wait_the_start_refuses_in_words_and_changes_nothing(tmp_path, monkeypatch):
    who = boot()
    brainlock.serve(str(tmp_path), boot_id=who).release()
    monkeypatch.setattr(brainlock, "CLAIM_WAIT", 0.05)
    fh = brainlock._open_claim(str(tmp_path))
    assert brainlock._lock(fh, True), "a tail's shared hold"
    try:
        with pytest.raises(brainlock.BrainBusy, match="stopped in the middle of an answer"):
            brainlock.serve(str(tmp_path), boot_id=boot())
    finally:
        brainlock._unlock(fh)
        fh.close()
    assert (tmp_path / brainlock.CLAIM).read_bytes() == who.encode()
    brainlock.serve(str(tmp_path), boot_id=boot()).release()


def test_a_claim_waits_for_a_tail_then_goes(tmp_path):
    brainlock.serve(str(tmp_path), boot_id=boot()).release()
    fh = brainlock._open_claim(str(tmp_path))
    assert brainlock._lock(fh, True)
    got = []
    thread = threading.Thread(target=lambda: got.append(brainlock.serve(str(tmp_path), boot_id=boot())))
    thread.start()
    time.sleep(0.2)
    assert not got
    brainlock._unlock(fh)
    fh.close()
    thread.join(timeout=10)
    assert got
    got[0].release()


def test_lock_files_hold_all_three_so_a_backup_carries_none():
    for name in (brainlock.SOLE_LOCK, brainlock.OWNER_LOCK, brainlock.CLAIM):
        assert name in brainlock.LOCK_FILES


WRITER = textwrap.dedent("""
    import sys
    from mentis.spine import brainlock
    brainlock._buffered_claim_for_test = sys.argv[2] == "buffered"
    root = sys.argv[1]
    held = None
    for line in sys.stdin:
        # The lock the last round left holds nothing that matters, so take it again.
        if held is not None:
            held.release()
        held = brainlock.serve(root, boot_id=line.strip())
        print("written", flush=True)
""")


def _rounds(tmp_path, mode: str, rounds: int) -> list[str]:
    root = tmp_path / mode
    root.mkdir()
    brainlock.serve(str(root), boot_id=boot()).release()
    writer = subprocess.Popen([sys.executable, "-c", WRITER, str(root), mode],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                              cwd=str(pathlib.Path(__file__).resolve().parents[1]), env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    rust = subprocess.Popen([reader(), str(root)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True)
    said = []
    try:
        for _ in range(rounds):
            who = boot()
            writer.stdin.write(who + "\n")
            writer.stdin.flush()
            assert writer.stdout.readline().strip() == "written"
            # At that moment, with the writer alive and nothing flushed by anybody else.
            rust.stdin.write(who + "\n")
            rust.stdin.flush()
            said.append(rust.stdout.readline().strip())
    finally:
        writer.kill()
        rust.kill()
    return said


def test_a_real_rust_process_sees_all_32_bytes_the_moment_the_lock_goes(tmp_path):
    said = _rounds(tmp_path, "unbuffered", ROUNDS)
    assert said == ["same"] * ROUNDS


def test_the_buffered_control_fails_that_read(tmp_path):
    """A negative control: a claim made with a buffered write and no flush has to be caught."""
    said = _rounds(tmp_path, "buffered", 20)
    assert "different" in said


def test_a_backup_carries_none_of_them():
    from mentis.spine import backup
    for name in (brainlock.SOLE_LOCK, brainlock.OWNER_LOCK, brainlock.CLAIM):
        assert name in backup._SKIP
