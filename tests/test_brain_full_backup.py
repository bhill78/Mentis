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


def _restored(capsys, full, new) -> dict:
    code, plan = _ask(capsys, "restore-plan", str(new), str(full))
    assert code == 0 and plan["restorable"], plan["refusals"]
    code, done = _ask(capsys, "restore", str(new), str(full), "--confirm", plan["digest"])
    assert code == 0, done
    return done


def _manifest(full) -> dict:
    return json.loads((pathlib.Path(full) / "BACKUP.json").read_text("utf-8"))


def _rewrite_manifest(full, change) -> None:
    doc = _manifest(full)
    change(doc)
    (pathlib.Path(full) / "BACKUP.json").write_text(json.dumps(doc), "utf-8")


def _damage(path) -> None:
    path.chmod(0o644)
    path.write_bytes(b"not what it was")


def test_what_it_leaves_out_is_what_is_not_the_record(brain, capsys, tmp_path):
    """The complete durable Brain: a stored file nothing in the record names (an attachment
    on a draft never sent) goes and comes back like the rest. Only `derived/`, made again
    from the record, stays behind."""
    root, made = brain
    unnamed, _ = held.put(str(root), b"attached to a draft and never sent")
    (root / "derived" / "extractions").mkdir(parents=True)
    (root / "derived" / "extractions" / "x").write_text("made again", "utf-8")
    new = tmp_path / "restored"
    full = _full(capsys, root)
    assert _manifest(full)["unnamed_stored_files"] == [{"digest": unnamed, "size": 34}]
    assert [f["digest"] for f in _manifest(full)["stored_files"]] == [made["digest"]]
    done = _restored(capsys, full, new)
    assert done["unnamed_stored_files"] == 1
    assert held.path(new, unnamed).read_bytes() == b"attached to a draft and never sent"
    assert _ask(capsys, "verify", str(new))[0] == 0
    assert not (new / "derived").exists()
    left = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} \
        - {p.relative_to(new).as_posix() for p in new.rglob("*") if p.is_file()}
    assert left - {".mentis.lock"} == {"derived/extractions/x"}


def _purge_leaving_the_bytes(root, made) -> bytes:
    """A purge that died before it removed them: `purge` says the record decides first."""
    data = held.path(root, made["digest"]).read_bytes()
    c, cv = open_brain(root)
    try:
        artifacts.purge(c, cv, made["adm"], by=made["owner"], because="the owner decided")
    finally:
        c.close()
    assert not held.path(root, made["digest"]).exists()
    held.put(str(root), data)
    return data


def test_purged_bytes_do_not_come_back(brain, capsys, tmp_path):
    root, made = brain
    _purge_leaving_the_bytes(root, made)
    keep, _ = held.put(str(root), b"nothing names this and it is kept")
    full = pathlib.Path(_full(capsys, root))
    assert not held.path(full, made["digest"]).exists()
    assert held.path(full, keep).exists()
    doc = _manifest(full)
    assert doc["purged_stored_files_left_out"] == [made["digest"]]
    assert _ask(capsys, "verify-backup", str(full))[0] == 0
    new = tmp_path / "restored"
    _restored(capsys, full, new)
    assert not held.path(new, made["digest"]).exists()
    assert held.path(new, keep).exists()


def test_a_backup_that_holds_purged_bytes_is_not_usable(brain, capsys):
    """However they got there: it would undo the purge."""
    root, made = brain
    data = _purge_leaving_the_bytes(root, made)
    full = pathlib.Path(_full(capsys, root))
    held.put(str(full), data)
    _rewrite_manifest(full, lambda d: d["unnamed_stored_files"].append({"digest": made["digest"], "size": len(data)}))
    code, said = _ask(capsys, "verify-backup", str(full))
    assert code == 1 and "purged" in " ".join(said["problems"])


def test_what_the_backup_held_unnamed_and_was_purged_since_stays_out_of_the_restore(brain, capsys):
    """Attached to a draft, backed up, then sent and purged: the owner's decision stands."""
    root, made = brain
    data = b"a draft's, then sent, then purged"
    late, _ = held.put(str(root), data)
    other, _ = held.put(str(root), b"a draft's, never sent")
    full = pathlib.Path(_full(capsys, root))
    assert held.path(full, late).exists()
    c, cv = open_brain(root)
    try:
        got = artifacts.hold(c, cv, data, act="artifact-submitted", actor=made["owner"],
                             source=f"submission:{made['owner']}", door="human-ingress")
        artifacts.purge(c, cv, got["admission"], by=made["owner"], because="the owner decided")
    finally:
        c.close()
    held.remove(str(root), other)
    assert not held.path(root, late).exists()
    code, plan = _ask(capsys, "restore-plan", str(root), str(full))
    assert code == 0 and plan["restorable"], plan["refusals"]
    assert plan["unnamed_purged_since_backup"] == [late] and plan["unnamed_stored_files"] == 2
    code, done = _ask(capsys, "restore", str(root), str(full), "--confirm", plan["digest"])
    assert code == 0 and done["unnamed_withheld"] == [late]
    assert not held.path(root, late).exists()
    assert held.path(root, other).exists()


def test_one_already_corrupt_in_the_brain_is_said_and_stays_there(brain, capsys, tmp_path):
    """Nothing names it, and what it should hold is gone: the rest of the Brain is backed up,
    and the words and the manifest name it. It stays where it is, as evidence."""
    root, made = brain
    bad, _ = held.put(str(root), b"nothing names this, and it rots")
    good, _ = held.put(str(root), b"nothing names this either")
    _damage(held.path(root, bad))
    code, got = _ask(capsys, "backup", str(root), "--portable")
    assert code == 0 and got["usable"] is True and got["unnamed_stored_files"] == 1
    rel = held.path(".", bad).as_posix()
    assert got["stored_files_not_carried"] == [
        {"file": rel, "size": 15, "why": "it does not hash to its name"}]
    full = pathlib.Path(got["backup"])
    assert not held.path(full, bad).exists() and held.path(full, good).exists()
    assert held.path(root, bad).read_bytes() == b"not what it was"
    code, said = _ask(capsys, "verify-backup", str(full))
    assert code == 0 and said["stored_files_not_carried"] == got["stored_files_not_carried"]
    new = tmp_path / "restored"
    code, plan = _ask(capsys, "restore-plan", str(new), str(full))
    assert plan["stored_files_not_carried"] == got["stored_files_not_carried"]
    _restored(capsys, full, new)
    assert not held.path(new, bad).exists() and held.path(new, good).exists()


def test_what_is_in_the_store_and_cannot_be_a_copy_of_anything_is_said(brain, capsys):
    root, _ = brain
    good, _ = held.put(str(root), b"a real one")
    store = root / "artifacts" / "sha256"
    (store / "ab").mkdir(exist_ok=True)
    (store / "ab" / ".incoming-xyz").write_bytes(b"half a write")
    (store / "ab" / "readme.txt").write_bytes(b"somebody left this")
    misfiled = "cd" * 32
    (store / "ab" / misfiled).write_bytes(b"not at its own name")
    code, got = _ask(capsys, "backup", str(root), "--portable")
    assert code == 0 and got["unnamed_stored_files"] == 1
    why = {f["file"].rsplit("/", 1)[1]: f["why"] for f in got["stored_files_not_carried"]}
    assert why == {".incoming-xyz": "a write that never finished",
                   "readme.txt": "it is not at the name of its content",
                   misfiled: "it is not at the name of its content"}
    assert _ask(capsys, "verify-backup", got["backup"])[0] == 0


@pytest.mark.parametrize("how", ["changed", "gone", "wrong size listed"])
def test_an_unnamed_one_that_is_not_right_in_the_backup_is_found(brain, capsys, tmp_path, how):
    root, _ = brain
    unnamed, _ = held.put(str(root), b"nothing names this")
    full = pathlib.Path(_full(capsys, root))
    target = held.path(full, unnamed)
    if how == "changed":
        _damage(target)
    elif how == "gone":
        target.chmod(0o644)
        target.unlink()
    else:
        _rewrite_manifest(full, lambda d: d["unnamed_stored_files"][0].update(size=1))
    code, said = _ask(capsys, "verify-backup", str(full))
    assert code == 1 and said["usable"] is False and said["intact"] is False
    assert unnamed in " ".join(said["problems"])
    code, plan = _ask(capsys, "restore-plan", str(tmp_path / "restored"), str(full))
    assert plan["restorable"] is False and unnamed in " ".join(plan["refusals"])


@pytest.mark.parametrize("name", ["cd" * 32, "stray.txt"], ids=["a digest", "anything else"])
def test_a_file_in_the_backups_store_it_does_not_list_is_found(brain, capsys, name):
    root, _ = brain
    full = pathlib.Path(_full(capsys, root))
    where = full / "artifacts" / "sha256" / name[:2]
    where.mkdir(parents=True, exist_ok=True)
    (where / name).write_bytes(b"how did this get here")
    code, said = _ask(capsys, "verify-backup", str(full))
    assert code == 1 and name in " ".join(said["problems"])


def test_one_made_before_unnamed_files_were_carried_verifies_and_restores_as_it_did(brain, capsys, tmp_path):
    """BACKUP.json as it was: `stored_files` is the store, and nothing else is asked of it."""
    root, made = brain
    full = pathlib.Path(_full(capsys, root))

    def as_it_was(doc):
        for key in ("unnamed_stored_files", "purged_stored_files_left_out", "stored_files_not_carried"):
            del doc[key]
    _rewrite_manifest(full, as_it_was)
    code, said = _ask(capsys, "verify-backup", str(full))
    assert code == 0 and said["usable"] is True and "unnamed_stored_files" not in said
    new = tmp_path / "restored"
    done = _restored(capsys, full, new)
    assert done["unnamed_stored_files"] == 0
    assert held.path(new, made["digest"]).exists() and _ask(capsys, "verify", str(new))[0] == 0


def test_the_quick_one_stays_a_manifest_of_what_the_record_names(brain, capsys):
    root, made = brain
    unnamed, _ = held.put(str(root), b"nothing names this")
    code, quick = _ask(capsys, "backup", str(root))
    assert code == 0 and "unnamed_stored_files" not in quick
    doc = _manifest(quick["backup"])
    assert not {"unnamed_stored_files", "purged_stored_files_left_out", "stored_files_not_carried"} & set(doc)
    assert [f["digest"] for f in doc["stored_files"]] == [made["digest"]]
    assert not held.path(quick["backup"], unnamed).exists()
    # what the record does not name is no part of whether it can be used
    held.remove(str(root), unnamed)
    code, said = _ask(capsys, "verify-backup", quick["backup"], "--brain", str(root))
    assert code == 0 and said["usable"] is True
    held.remove(str(root), made["digest"])
    code, said = _ask(capsys, "verify-backup", quick["backup"], "--brain", str(root))
    assert code == 1 and said["intact"] is True and made["digest"] in " ".join(said["live_store_problems"])


class _Killed(Exception):
    pass


def _killed_at(label):
    def hook(at):
        if at == label:
            raise _Killed(label)
    return hook


def test_a_restore_killed_part_way_resumes_with_them(brain, capsys):
    root, _ = brain
    unnamed, _ = held.put(str(root), b"nothing names this")
    full = _full(capsys, root)
    held.remove(str(root), unnamed)
    plan = backup.restore_plan(str(root), full)
    with pytest.raises(_Killed):
        backup.restore(str(root), full, plan["digest"], _hook=_killed_at("after-rename"))
    qid = backup._unfinished(str(root))[0]["id"]
    done = backup.resume_restore(str(root), qid)
    assert done["restored"] and held.path(root, unnamed).read_bytes() == b"nothing names this"


def test_a_restore_reversed_takes_back_the_ones_it_added(brain, capsys):
    root, _ = brain
    added, _ = held.put(str(root), b"the backup has this and the Brain will not")
    own, _ = held.put(str(root), b"the Brain has its own copy of this")
    full = _full(capsys, root)
    held.remove(str(root), added)
    plan = backup.restore_plan(str(root), full)
    with pytest.raises(_Killed):
        backup.restore(str(root), full, plan["digest"], _hook=_killed_at("after-copy-in"))
    assert held.path(root, added).exists()
    qid = backup._unfinished(str(root))[0]["id"]
    assert backup.resume_restore(str(root), qid, reverse=True)["reversed"]
    assert not held.path(root, added).exists() and held.path(root, own).exists()


def test_a_restored_brain_missing_one_does_not_verify(brain, capsys, tmp_path):
    root, _ = brain
    unnamed, _ = held.put(str(root), b"nothing names this")
    full = _full(capsys, root)
    new = tmp_path / "restored"
    _restored(capsys, full, new)
    meta = _manifest(full)
    assert backup._verify_restored(str(new), meta) == []
    held.remove(str(new), unnamed)
    assert unnamed in " ".join(backup._verify_restored(str(new), meta))
    assert backup._verify_restored(str(new), meta, [unnamed]) == []


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


def test_an_unfinished_one_goes_by_prune_once_it_is_30_days_old(brain, tmp_path, monkeypatch):
    """What a kill during the backup leaves, as the guide says."""
    root, _ = brain
    with monkeypatch.context() as m:
        m.setattr(backup.held, "copy", lambda *a, **k: (_ for _ in ()).throw(OSError(errno.ENOSPC, "full")))
        with pytest.raises(OSError):
            brain_main(["backup", str(root), "--portable"])
    part = next((tmp_path / "backups").glob("*/*.partial"))
    assert backup.prune(str(root), confirm=True)["removed"] == [] and part.is_dir()
    later = part.stat().st_mtime + (backup.KEEP_DAYS + 1) * 86400
    assert backup.prune(str(root), confirm=True, now=later)["removed"] == [str(part)]
    assert not part.exists()


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
