"""The modernize release helper's bounded backup (review L3, M6):
tools/release_modernize/bounded_backup.py."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "tools" / "release_modernize" / "bounded_backup.py"
spec = importlib.util.spec_from_file_location("bounded_backup_under_test", HERE)
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


def _brain(root: Path) -> Path:
    root.mkdir(parents=True)
    c = sqlite3.connect(root / "corpus.db")
    for t in ("entry", "operational", "delivery", "schema_migration"):
        c.execute(f"create table {t} (x)")
        c.execute(f"insert into {t} values (1)")
    c.commit()
    c.close()
    (root / "mentis-corpus.json").write_text(json.dumps({"corpus_id": "c-1"}))
    (root / "mcp-policy.json").write_text(json.dumps({"format": "mentis.mcp-policy",
                                                       "version": 1}))
    (root / ".mentis.serve.json").write_text("{}")             # hidden: not carried
    blob = b"bytes"
    art = root / "artifacts" / "ab"
    art.mkdir(parents=True)
    (art / hashlib.sha256(blob).hexdigest()).write_bytes(blob)
    (root / "presentation").mkdir()
    (root / "presentation" / "looks.json").write_text("[]")
    return root


def test_a_backup_carries_the_owners_top_level_config_files(tmp_path, capsys):
    brain = _brain(tmp_path / "brain")
    B.cmd_backup(str(brain), str(tmp_path / "bk"), "t")
    assert (tmp_path / "bk" / "mcp-policy.json").exists()
    assert (tmp_path / "bk" / "mentis-corpus.json").exists()
    assert not (tmp_path / "bk" / ".mentis.serve.json").exists()
    m = json.loads((tmp_path / "bk" / B.MANIFEST).read_text())
    assert "mcp-policy.json" in m["top_files"]


def test_a_restore_is_a_brain_not_a_backup_and_carries_the_config(tmp_path, capsys):
    brain = _brain(tmp_path / "brain")
    B.cmd_backup(str(brain), str(tmp_path / "pre-modernize-1"), "t")
    B.build(str(tmp_path / "pre-modernize-1"), str(tmp_path / "pre-modernize-restored"),
            "restored", mark=False)
    restored = tmp_path / "pre-modernize-restored"
    assert (restored / "mcp-policy.json").exists()
    assert not (restored / B.MANIFEST).exists(), "retention must never count it as a backup"
    assert not B.is_ours(str(restored))
    # the verify-restore leaves its mark on the backup, never in a restored Brain
    B.cmd_verify_restore(str(tmp_path / "pre-modernize-1"), str(tmp_path / "check"))
    assert not (tmp_path / "check").exists()
    assert B.is_verified(str(tmp_path / "pre-modernize-1"))


def test_a_failed_restore_check_removes_its_temp_folder(tmp_path, capsys, monkeypatch):
    brain = _brain(tmp_path / "brain")
    B.cmd_backup(str(brain), str(tmp_path / "bk"), "t")
    real = B.counts

    def broken(path):
        if "check" in str(path):
            raise SystemExit("cannot open the restore")
        return real(path)
    monkeypatch.setattr(B, "counts", broken)
    with pytest.raises(SystemExit):
        B.cmd_verify_restore(str(tmp_path / "bk"), str(tmp_path / "check"))
    assert not (tmp_path / "check").exists()
    assert not B.is_verified(str(tmp_path / "bk"))
    # and a folder it did not make is never deleted
    (tmp_path / "theirs").mkdir()
    with pytest.raises(SystemExit):
        B.cmd_verify_restore(str(tmp_path / "bk"), str(tmp_path / "theirs"))
    assert (tmp_path / "theirs").exists()


def _ours(root: Path, name: str, verified: bool, when: int):
    d = root / name
    d.mkdir()
    (d / B.MANIFEST).write_text(json.dumps({"mark": B.MARK}))
    os.utime(d / B.MANIFEST, (when, when))
    if verified:
        (d / B.VERIFIED).write_text(json.dumps({"ok": True}))


def test_retention_never_leaves_fewer_than_two_verified_backups(tmp_path, capsys):
    root = tmp_path / "backups"
    root.mkdir()
    _ours(root, "pre-modernize-1", True, 1000)
    _ours(root, "pre-modernize-2", True, 2000)
    _ours(root, "pre-modernize-3", False, 3000)      # newest: its restore check failed
    B.cmd_retain(str(root), "pre-modernize-", 1)
    out = json.loads(capsys.readouterr().out)
    assert out["deleted"] == []
    assert sorted(out["held_for_verified_minimum"]) == ["pre-modernize-1", "pre-modernize-2"]
    assert len(os.listdir(root)) == 3
    _ours(root, "pre-modernize-4", True, 4000)
    B.cmd_retain(str(root), "pre-modernize-", 2)
    out = json.loads(capsys.readouterr().out)
    assert out["deleted"] == ["pre-modernize-1"]     # 2 and 4 verified remain
    assert len(out["verified"]) == 2
