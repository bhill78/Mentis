"""That the BRAIN-COPY recipe yields a valid BRAIN-COPY with a new identity, leaving the master alone.

    <venv python> tools/r1/prove_brain_copy_rebuild.py <source Brain> --evidence <file>

Builds a second master in a scratch directory under the fixtures, by `copy_brain.build`, checks
its chain and its own manifest, and shows the committed manifest refuses it. The retained master's
digests are taken either side, by hashing alone: SQLite doesn't open it. Then deletes the scratch
directory and writes the evidence. Refuses a scratch directory that already exists.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import stat
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402
import copy_brain  # noqa: E402

COMMITTED = common.EVIDENCE / "brain-copy-manifest.json"
SCRATCH = "brain-copy-rebuild-proof"


def _hash_at(db: pathlib.Path, table: str, seq: int) -> str | None:
    conn = copy_brain._read_only(db)
    try:
        row = conn.execute(f"SELECT hash FROM {table} WHERE seq = ?", (seq,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _writable_then_retry(func, path, _exc):
    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    func(path)


def prove(source: pathlib.Path, scratch: pathlib.Path) -> dict:
    committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
    retained = common.master_dir()
    before = copy_brain.digests(retained)
    if before != committed["digests"]:
        raise SystemExit(f"{retained} isn't what {COMMITTED} says, before anything was done")

    master, manifest = scratch / "master", scratch / "manifest.json"
    doc = copy_brain.build(source, master, manifest)
    copy_brain.check(master, manifest, verify_chain=True)
    try:
        copy_brain.check(master, COMMITTED)
    except copy_brain.Mismatch as exc:
        refused = str(exc)
    else:
        raise SystemExit("the committed manifest accepted a different snapshot")
    # The record is append-only, so the new chain holds the committed head at its own seq.
    extends = {table: _hash_at(master / "corpus.db", table, seq) == committed["heads"][table]
               for table, seq in zip(copy_brain.CHAINED, committed["advance"])}
    after = copy_brain.digests(retained)
    return {
        "what": "A second master, built by the recipe into a scratch directory and deleted after",
        "source": str(source),
        "scratch": str(scratch),
        "built_at_utc": doc["built_at_utc"],
        "built_seconds": doc["built_seconds"],
        "code_commit": doc["code_commit"],
        "tool_blob": doc["tool_blob"],
        "sqlite_version": doc["sqlite_version"],
        "committed_advance": committed["advance"],
        "rebuilt": {
            "advance": doc["advance"],
            "heads": doc["heads"],
            "digests": doc["digests"],
            "verify_chain_intact": doc["verify_chain"]["intact"],
            "checks_against_its_own_manifest_with_the_chain": True,
            "refused_by_the_committed_manifest": refused,
            "holds_the_committed_head_at_its_seq": extends,
        },
        "retained_master": {
            "digests_before": before,
            "digests_after": after,
            "unchanged": before == after,
            "equal_to_the_committed_manifest": after == committed["digests"],
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="prove BRAIN-COPY's recipe once")
    ap.add_argument("source", type=pathlib.Path)
    ap.add_argument("--evidence", type=pathlib.Path, required=True)
    a = ap.parse_args(argv)
    scratch = common.fixtures_root() / SCRATCH
    if scratch.exists():
        raise SystemExit(f"{scratch} already exists: look at it, and delete it yourself")
    scratch.mkdir()
    try:
        doc = prove(a.source, scratch)
    finally:
        shutil.rmtree(scratch, onerror=_writable_then_retry)
    doc["scratch_deleted"] = not scratch.exists()
    a.evidence.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"advance": doc["rebuilt"]["advance"],
                      "retained_unchanged": doc["retained_master"]["unchanged"],
                      "scratch_deleted": doc["scratch_deleted"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
