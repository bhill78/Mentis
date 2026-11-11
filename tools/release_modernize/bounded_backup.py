"""Bounded Brain backup for the modernize release helper (O1). No full copies.

    python -I bounded_backup.py backup  SRC DEST [--label TEXT]
    python -I bounded_backup.py verify-restore BACKUP TEMP      # restore into TEMP, check, delete TEMP
    python -I bounded_backup.py restore BACKUP DEST             # an owner's restore: a Brain at DEST (new folder)
    python -I bounded_backup.py retain  ROOT PREFIX KEEP        # delete this helper's older backups
    python -I bounded_backup.py report  ROOT                    # pre-* backups by earlier helpers

What a backup is, and what it costs:
  corpus.db      a consistent copy through SQLite's online backup API from a read-only
                 connection (WAL content included; never a file copy of a live WAL db).
                 This is the only large thing written: ~the size of the db.
  artifacts/     every blob is HARDLINKED, not copied. Blobs are named by the sha256 of
                 their bytes and written once, never edited in place (mentis/spine/held.py),
                 so one physical file can back the Brain and every backup. Each blob is
                 hashed and must match its name before it is linked; one that does not is
                 COPIED and reported. No attribute is ever changed on a linked blob (a
                 read-only flag would land on the live Brain's file too).
  small dirs     presentation/, derived/, instances/ and mentis-corpus.json are copied.
  never          worktrees/, worktrees-locked-residue/, scratch/, .pytest_cache/, lock and
                 serve files, corpus.db-wal/-shm.

Every backup this helper makes holds BACKUP.json (its manifest). `retain` only ever deletes
a directory under ROOT whose name starts with PREFIX AND holds that manifest: older pre-*
backups made by earlier helpers are never deleted, only reported.
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HEX = re.compile(r"^[0-9a-f]{64}$")
SMALL = ("presentation", "derived", "instances")
MANIFEST = "BACKUP.json"
MARK = "modernize-release bounded backup"


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def free_bytes(path):
    return shutil.disk_usage(path).free


def counts(brain):
    """The same read as counts.py, for one Brain."""
    c = sqlite3.connect(f"file:{brain}/corpus.db?mode=ro", uri=True)
    try:
        q = lambda s: c.execute(s).fetchone()[0]
        art = sum(len(f) for _, _, f in os.walk(os.path.join(brain, "artifacts")))
        meta = os.path.join(brain, "mentis-corpus.json")
        return {"entry": q("select count(*) from entry"),
                "operational": q("select count(*) from operational"),
                "delivery": q("select count(*) from delivery"),
                "max_entry_rowid": q("select max(rowid) from entry"),
                "migrations": q("select count(*) from schema_migration"),
                "user_version": q("pragma user_version"),
                "artifacts_files": art,
                "corpus_id": json.load(open(meta)).get("corpus_id") if os.path.exists(meta) else None,
                "quick_check": q("pragma quick_check")}
    finally:
        c.close()


def sqlite_copy(src_db, dst_db):
    """SQLite online backup, one step: one read transaction, so a consistent snapshot even if
    a writer is live. The destination is a plain rollback-journal db (no -wal beside it)."""
    src = sqlite3.connect(f"file:{src_db}?mode=ro", uri=True)
    dst = sqlite3.connect(dst_db)
    try:
        src.backup(dst)
        dst.execute("pragma journal_mode=delete")
        dst.commit()
    finally:
        dst.close()
        src.close()


def link_artifacts(src_root, dst_root, threads=8):
    """Hardlink each blob after checking its bytes against its name."""
    stats = {"linked": 0, "linked_bytes": 0, "copied": 0, "copied_bytes": 0,
             "mismatched": [], "errors": []}
    jobs = []
    for d, _, files in os.walk(src_root):
        rel = os.path.relpath(d, src_root)
        os.makedirs(os.path.join(dst_root, rel), exist_ok=True)
        for n in files:
            jobs.append((os.path.join(d, n), os.path.join(dst_root, rel, n), n))

    def one(job):
        src, dst, name = job
        try:
            size = os.path.getsize(src)
            if HEX.match(name) and sha(src) == name:
                os.link(src, dst)
                return ("linked", size, None)
            shutil.copy2(src, dst)  # not a verifiable blob: a real copy, reported
            return ("copied", size, src)
        except OSError as e:
            return ("error", 0, f"{src}: {e}")

    with ThreadPoolExecutor(threads) as ex:
        for kind, size, what in ex.map(one, jobs):
            if kind == "linked":
                stats["linked"] += 1; stats["linked_bytes"] += size
            elif kind == "copied":
                stats["copied"] += 1; stats["copied_bytes"] += size
                stats["mismatched"].append(what)
            else:
                stats["errors"].append(what)
    return stats


def copy_small(src, dst):
    copied = 0
    for name in SMALL:
        s = os.path.join(src, name)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(dst, name))
            copied += sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(s) for f in fs)
    meta = os.path.join(src, "mentis-corpus.json")
    if os.path.exists(meta):
        shutil.copy2(meta, os.path.join(dst, "mentis-corpus.json"))
        copied += os.path.getsize(meta)
    return copied


def build(src, dst, label, *, source_counts=None):
    """A Brain at dst from src: sqlite backup + hardlinked blobs + small copies."""
    if os.path.exists(dst):
        raise SystemExit(f"destination exists: {dst}")
    os.makedirs(dst)
    free0 = free_bytes(dst)
    t0 = time.time()
    sqlite_copy(os.path.join(src, "corpus.db"), os.path.join(dst, "corpus.db"))
    t_db = time.time() - t0
    small = copy_small(src, dst)
    art = {"linked": 0, "linked_bytes": 0, "copied": 0, "copied_bytes": 0, "mismatched": [], "errors": []}
    if os.path.isdir(os.path.join(src, "artifacts")):
        art = link_artifacts(os.path.join(src, "artifacts"), os.path.join(dst, "artifacts"))
    if art["errors"]:
        raise SystemExit(f"artifact errors: {art['errors'][:5]}")
    got = counts(dst)
    manifest = {
        "mark": MARK, "label": label, "source": src, "made_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seconds": round(time.time() - t0, 1), "sqlite_backup_seconds": round(t_db, 1),
        "corpus_db_bytes": os.path.getsize(os.path.join(dst, "corpus.db")),
        "small_copied_bytes": small,
        "artifacts": {k: (v if not isinstance(v, list) else len(v)) for k, v in art.items()},
        "artifacts_mismatched": art["mismatched"],
        "disk_cost_bytes_written": os.path.getsize(os.path.join(dst, "corpus.db")) + small + art["copied_bytes"],
        "free_space_drop_bytes": free0 - free_bytes(dst),
        "apparent_bytes_if_full_copy": os.path.getsize(os.path.join(dst, "corpus.db")) + small
                                       + art["linked_bytes"] + art["copied_bytes"],
        "counts": got,
    }
    if source_counts is not None:
        manifest["source_counts"] = source_counts
    with open(os.path.join(dst, MANIFEST), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    return manifest


def cmd_backup(src, dst, label):
    before = counts(src)
    m = build(src, dst, label, source_counts=before)
    if m["counts"]["quick_check"] != "ok":
        raise SystemExit(f"backup quick_check: {m['counts']['quick_check']}")
    # A stopped Brain must match exactly; a live one (rehearsal-brain making) may only have grown.
    for k in ("entry", "operational", "delivery", "max_entry_rowid"):
        if m["counts"][k] < before[k]:
            raise SystemExit(f"backup {k} {m['counts'][k]} < source {before[k]}")
    for k in ("migrations", "corpus_id", "artifacts_files"):
        if m["counts"][k] != before[k]:
            raise SystemExit(f"backup {k} {m['counts'][k]} != source {before[k]}")
    print(json.dumps({k: m[k] for k in ("label", "seconds", "corpus_db_bytes", "small_copied_bytes",
                                         "artifacts", "disk_cost_bytes_written", "free_space_drop_bytes",
                                         "apparent_bytes_if_full_copy", "counts", "source_counts")}))


def cmd_verify_restore(backup, temp):
    """Restore the backup the way an owner would (same build), open it, check it, delete it."""
    with open(os.path.join(backup, MANIFEST), encoding="utf-8") as f:
        m = json.load(f)
    r = build(backup, temp, "restore-check")
    try:
        ok = r["counts"]["quick_check"] == "ok"
        same = {k: (r["counts"][k], m["counts"][k]) for k in m["counts"] if r["counts"][k] != m["counts"][k]}
        # every blob in the restore is the backup's own file (hardlink), and a sample re-hashes to its name
        sample, bad = 0, []
        for d, _, files in os.walk(os.path.join(temp, "artifacts")):
            for n in files:
                p = os.path.join(d, n)
                b = os.path.join(backup, os.path.relpath(p, temp))
                if not os.path.samefile(p, b):
                    bad.append(p)
                if sample < 200 and HEX.match(n):
                    sample += 1
                    if sha(p) != n:
                        bad.append(p)
        out = {"restore": temp, "quick_check": r["counts"]["quick_check"], "differs_from_manifest": same,
               "artifacts_bad": bad[:10], "artifacts_rehashed": sample, "restore_seconds": r["seconds"],
               "restore_disk_cost_bytes": r["disk_cost_bytes_written"], "counts": r["counts"]}
    finally:
        shutil.rmtree(temp)
    out["temp_deleted"] = not os.path.exists(temp)
    print(json.dumps(out))
    if not ok or same or bad:
        raise SystemExit("restore verification FAILED")


def is_ours(path):
    try:
        with open(os.path.join(path, MANIFEST), encoding="utf-8") as f:
            return json.load(f).get("mark") == MARK
    except (OSError, ValueError):
        return False


def cmd_retain(root, prefix, keep):
    ours = sorted((d for d in os.listdir(root)
                   if d.startswith(prefix) and is_ours(os.path.join(root, d))),
                  key=lambda d: os.path.getmtime(os.path.join(root, d, MANIFEST)), reverse=True)
    deleted = []
    for d in ours[keep:]:
        p = os.path.join(root, d)
        # corpus.db may have been marked read-only; it is this backup's own file, never a link.
        db = os.path.join(p, "corpus.db")
        if os.path.exists(db):
            os.chmod(db, 0o666)
        shutil.rmtree(p)
        deleted.append(d)
    print(json.dumps({"kept": ours[:keep], "deleted": deleted}))


def cmd_report(root):
    """Earlier helpers' pre-* backups: count, apparent size, unique bytes (hardlinks counted once)."""
    seen, apparent, unique, n = set(), 0, 0, 0
    names = sorted(d for d in os.listdir(root) if d.startswith("pre-") and not is_ours(os.path.join(root, d)))
    for name in names:
        n += 1
        for d, _, files in os.walk(os.path.join(root, name)):
            for f in files:
                try:
                    st = os.stat(os.path.join(d, f))
                except OSError:
                    continue
                apparent += st.st_size
                key = (st.st_dev, st.st_ino)
                if key not in seen:
                    seen.add(key); unique += st.st_size
    print(json.dumps({"root": root, "earlier_pre_backups": n, "names": names,
                      "apparent_gb": round(apparent / 2**30, 2), "unique_gb": round(unique / 2**30, 2)}))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    if a[0] == "backup":
        label = a[a.index("--label") + 1] if "--label" in a else "backup"
        cmd_backup(a[1], a[2], label)
    elif a[0] == "verify-restore":
        cmd_verify_restore(a[1], a[2])
    elif a[0] == "restore":
        # The owner's act, with the server stopped: build a Brain at a NEW folder from the backup,
        # then move it into place by hand. Blobs are hardlinked, corpus.db copied through SQLite.
        m = build(a[1], a[2], "restored")
        print(json.dumps({"restored_to": a[2], "counts": m["counts"]}))
    elif a[0] == "retain":
        cmd_retain(a[1], a[2], int(a[3]))
    elif a[0] == "report":
        cmd_report(a[1])
    else:
        raise SystemExit(__doc__)
