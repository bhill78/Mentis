"""The full backup an update takes (`mentis.brain backup --portable`), on a real Brain.

Every Brain is disposable, under tmp_path. What is pinned is what the installer relies on:
it holds the durable Brain by itself, it is checked, what it leaves out is named here, and
a disk that fills leaves nothing that can be taken for a backup. The last also runs on a
really full disk where one is given (MENTIS_TEST_SMALL_DISK, a small tmpfs in Linux).
"""

from __future__ import annotations

import errno
import json
import os
import pathlib
import shutil
import subprocess
import sys
import uuid

import pytest

from mentis import artifacts
from mentis.brain.__main__ import main as brain_main
from mentis.spine import backup, held
from tests.test_exchange_export import build, open_brain


@pytest.fixture
def brain(tmp_path):
    root = tmp_path / "brain"
    made = build(root)
    made["corpus"].close()
    (root / "presentation").mkdir(exist_ok=True)
    (root / "presentation" / "look.json").write_text("{}", "utf-8")
    if not (root / "mentis-corpus.json").exists():
        (root / "mentis-corpus.json").write_text(json.dumps({"corpus_version": 1, "corpus_id": "fixture"}), "utf-8")
    (root / "instances").mkdir(exist_ok=True)
    (root / "instances" / "kept.json").write_text("{}", "utf-8")
    return root, made


def _ask(capsys, *args) -> tuple:
    capsys.readouterr()
    code = brain_main(list(args))
    return code, json.loads(capsys.readouterr().out)


def _full(capsys, root) -> str:
    code, got = _ask(capsys, "backup", str(root), "--portable")
    assert code == 0 and got["kind"] == "portable"
    return got["backup"]


def test_it_goes_beside_the_brain_and_says_its_kind(brain, capsys, tmp_path):
    root, _ = brain
    made = pathlib.Path(_full(capsys, root))
    assert made.parent.parent == tmp_path / "backups"
    assert made.name.endswith("-portable") and not made.name.endswith(".partial")
    assert json.loads((made / "BACKUP.json").read_text("utf-8"))["kind"] == "portable"


def test_it_holds_the_stored_files_and_the_quick_one_does_not(brain, capsys):
    root, made = brain
    full = pathlib.Path(_full(capsys, root))
    assert held.path(full, made["digest"]).read_bytes() == held.path(root, made["digest"]).read_bytes()
    code, quick = _ask(capsys, "backup", str(root))
    assert code == 0 and quick["kind"] == "local-recovery"
    assert not held.path(quick["backup"], made["digest"]).exists()


def test_it_stands_without_the_brain_and_the_quick_one_does_not(brain, capsys, tmp_path):
    """What makes it the complete durable Brain: the Brain can be gone."""
    root, _ = brain
    full = _full(capsys, root)
    _, quick = _ask(capsys, "backup", str(root))
    aside = tmp_path / "gone"
    os.rename(root, aside)
    assert _ask(capsys, "verify-backup", full)[0] == 0
    code, said = _ask(capsys, "verify-backup", quick["backup"])
    assert code == 1 and said["usable"] is False


def test_it_restores_elsewhere_whole(brain, capsys, tmp_path):
    root, made = brain
    full = _full(capsys, root)
    new = tmp_path / "restored"
    _, plan = _ask(capsys, "restore-plan", str(new), full)
    assert plan["restorable"], plan["refusals"]
    assert _ask(capsys, "restore", str(new), full, "--confirm", plan["digest"])[0] == 0
    assert _ask(capsys, "verify", str(new))[0] == 0
    assert held.path(new, made["digest"]).read_bytes() == held.path(root, made["digest"]).read_bytes()
    for rel in ("mentis-corpus.json", "presentation/look.json", "instances/kept.json"):
        assert (new / rel).read_bytes() == (root / rel).read_bytes()


def test_a_changed_stored_file_is_found_by_the_check(brain, capsys):
    root, made = brain
    full = pathlib.Path(_full(capsys, root))
    target = held.path(full, made["digest"])
    target.chmod(0o644)
    target.write_bytes(b"not what it was")
    code, said = _ask(capsys, "verify-backup", str(full))
    assert code == 1 and made["digest"] in " ".join(said["problems"])


def test_a_damaged_stored_file_stops_it_and_leaves_nothing(brain, capsys, tmp_path):
    root, made = brain
    target = held.path(root, made["digest"])
    target.chmod(0o644)
    target.write_bytes(b"not what it was")
    capsys.readouterr()
    assert brain_main(["backup", str(root), "--portable"]) == 2
    assert "did not verify" in capsys.readouterr().err
    assert not [p for p in (tmp_path / "backups").glob("*/*")]


def test_what_it_leaves_out_is_what_is_not_the_record(brain, capsys, tmp_path):
    """The completeness finding, pinned: bytes nothing in the record names (an attachment
    on a draft never sent) and `derived/`, which is made again from the record. Purged
    bytes too, as a purge means. Everything else in a Brain goes with it."""
    root, _ = brain
    unnamed, _ = held.put(str(root), b"attached to a draft and never sent")
    (root / "derived" / "extractions").mkdir(parents=True)
    (root / "derived" / "extractions" / "x").write_text("made again", "utf-8")
    new = tmp_path / "restored"
    full = _full(capsys, root)
    _, plan = _ask(capsys, "restore-plan", str(new), full)
    assert _ask(capsys, "restore", str(new), full, "--confirm", plan["digest"])[0] == 0
    assert not held.path(new, unnamed).exists()
    assert not (new / "derived").exists()
    left = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} \
        - {p.relative_to(new).as_posix() for p in new.rglob("*") if p.is_file()}
    assert left - {".mentis.lock"} <= {held.path(".", unnamed).as_posix(), "derived/extractions/x"}


def test_a_disk_that_fills_leaves_only_what_says_it_is_not_a_backup(brain, capsys, tmp_path, monkeypatch):
    root, _ = brain

    def full_up(*a, **k):
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(backup.held, "copy", full_up)
    with pytest.raises(OSError):
        brain_main(["backup", str(root), "--portable"])
    left = list((tmp_path / "backups").glob("*/*"))
    assert [p.name.endswith(".partial") for p in left] == [True]
    # never finished, so never usable, and retention does not count it
    code, said = _ask(capsys, "verify-backup", str(left[0]))
    assert code == 1 and said["usable"] is False


@pytest.mark.skipif(not os.environ.get("MENTIS_TEST_SMALL_DISK"), reason="no small disk given")
def test_a_really_full_disk_fails_it_in_another_process(brain):
    """The command `_step_backed_up` runs, with its stored files bigger than the disk."""
    root, made = brain
    disk = pathlib.Path(os.environ["MENTIS_TEST_SMALL_DISK"])
    dest = disk / f"full-{uuid.uuid4().hex[:8]}"
    size = min(shutil.disk_usage(disk).free, held.MAX_BYTES)
    c, cv = open_brain(root)
    try:
        for _ in range(3):
            artifacts.hold(c, cv, os.urandom(size), act="artifact-submitted", actor=made["owner"],
                           source=f"submission:{made['owner']}", door="human-ingress")
    finally:
        c.close()
    r = subprocess.run([sys.executable, "-m", "mentis.brain", "backup", str(root), "--dest", str(dest), "--portable"],
                       capture_output=True, text=True)
    assert r.returncode != 0 and ("No space left" in r.stderr or "disk is full" in r.stderr), r.stderr[-800:]
    assert not dest.exists()
    assert pathlib.Path(str(dest) + ".partial").is_dir()    # what `_step_backed_up` then removes
    assert backup.verify_backup(str(dest) + ".partial")["usable"] is False
    shutil.rmtree(str(dest) + ".partial")
