"""BRAIN-COPY: one read-only master, and a checked fresh copy of it for each test.

    <venv python> tools/r1/copy_brain.py build <source Brain> --manifest <file> [--master <dir>]
    <venv python> tools/r1/copy_brain.py fresh <new directory> --manifest <file> [--master <dir>]
    <venv python> tools/r1/copy_brain.py check <directory> --manifest <file> [--verify-chain]

`build` makes the master. `corpus.db` comes through SQLite's backup API from a `mode=ro`
connection, and that is the only way this opens the source. The Brain's sibling files are then
copied by name, and only those named in `SIBLINGS`. So what they hold is at least as new as the
database, and a file the database names is present. The master's row counts, position and chain
are read before it is sealed: every file read-only, and SQLite never opens it again.

A Brain keeps moving, so a build is a new snapshot with a new identity, and it never compares
with an earlier manifest. It refuses to write over one: a new manifest goes to a new file, and
replacing the committed one is a person's visible revision (R1-acceptance.md, `BRAIN-COPY`).

`fresh` copies the master and checks the copy against the manifest before anyone uses it. A
mismatch raises `Mismatch` and exits nonzero: it fails, it never skips. `check` is that check.
Standard library, and PY_COMMIT's `mentis.spine.backup` for the chain.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sqlite3
import stat
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402

FORMAT = 1
SIBLING_DIRS = ("artifacts", "instances", "presentation", "derived")
SIBLING_FILES = ("mentis-corpus.json",)
CHAINED = ("entry", "operational", "delivery")


class Mismatch(Exception):
    """A copy that isn't what its manifest says."""


def _read_only(db: pathlib.Path) -> sqlite3.Connection:
    """A Brain nothing has open. `immutable` makes no -wal or -shm beside a copy, and is
    used only on the fixtures' own copies: never on a source, and never on a live Brain."""
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro&immutable=1", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _chain(db: pathlib.Path) -> dict:
    """Python's own walk (`Store.verify_chain`, over a bare connection), at PY_COMMIT."""
    sys.path.insert(0, str(common.code_dir()))
    from mentis.spine import backup

    conn = _read_only(db)
    conn.row_factory = sqlite3.Row
    try:
        return backup._chain(conn)
    finally:
        conn.close()


def _positions(db: pathlib.Path) -> dict:
    conn = _read_only(db)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name")]
        return {
            "advance": [conn.execute(f"SELECT COALESCE(MAX(seq),0) FROM {t}").fetchone()[0]
                        for t in CHAINED],
            "rows": {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                     for t in tables},
            "heads": {t: (conn.execute(f"SELECT hash FROM {t} ORDER BY seq DESC LIMIT 1")
                          .fetchone() or [None])[0] for t in CHAINED},
        }
    finally:
        conn.close()


def digests(brain: pathlib.Path) -> dict:
    return {
        "corpus_db": common.sha256_file(brain / "corpus.db"),
        "files": {n: common.sha256_file(brain / n) if (brain / n).is_file() else None
                  for n in SIBLING_FILES},
        "trees": {d: common.tree_digest(brain / d) for d in SIBLING_DIRS},
    }


def build(source: pathlib.Path, master: pathlib.Path, manifest: pathlib.Path) -> dict:
    if master.exists():
        raise SystemExit(f"{master} already exists: a master is built new, never over")
    if manifest.exists():
        raise SystemExit(f"{manifest} already exists: a new master's manifest goes to a new "
                         "file, and replacing a committed one is a visible revision")
    started = time.time()
    master.mkdir(parents=True)
    src = sqlite3.connect(f"file:{(source / 'corpus.db').as_posix()}?mode=ro", uri=True)
    try:
        src.execute("PRAGMA query_only=ON")
        dst = sqlite3.connect(master / "corpus.db")
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    for name in SIBLING_FILES:
        shutil.copy2(source / name, master / name)
    for name in SIBLING_DIRS:
        if (source / name).is_dir():
            shutil.copytree(source / name, master / name)
        else:
            (master / name).mkdir()
    db = master / "corpus.db"
    for leftover in ("corpus.db-wal", "corpus.db-shm"):
        (master / leftover).unlink(missing_ok=True)
    chain = _chain(db)
    doc = {
        "format": FORMAT,
        "source": str(source),
        "built_at": started,
        "built_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "built_seconds": round(time.time() - started, 1),
        "code_commit": common.head_of(common.code_dir()),
        "tool_blob": common.git_blob(__file__),
        "sqlite_version": sqlite3.sqlite_version,
        **_positions(db),
        "verify_chain": chain,
        "digests": digests(master),
    }
    for path in master.rglob("*"):
        if path.is_file():
            path.chmod(stat.S_IREAD)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def check(brain: pathlib.Path, manifest: pathlib.Path, *, verify_chain: bool = False) -> None:
    """Raises `Mismatch`, naming every difference found."""
    want = json.loads(manifest.read_text(encoding="utf-8"))
    if want.get("format") != FORMAT:
        raise Mismatch(f"manifest format {want.get('format')!r}, this tool reads {FORMAT}")
    if not (brain / "corpus.db").is_file():
        raise Mismatch(f"no corpus.db in {brain}")
    wrong = []
    got = digests(brain)
    if got["corpus_db"] != want["digests"]["corpus_db"]:
        wrong.append("corpus.db's digest")
    for name, digest in want["digests"]["files"].items():
        if got["files"].get(name) != digest:
            wrong.append(f"{name}'s digest")
    for name, digest in want["digests"]["trees"].items():
        if got["trees"].get(name) != digest:
            wrong.append(f"{name}/, {got['trees'].get(name)} against {digest}")
    try:
        have = _positions(brain / "corpus.db")
    except sqlite3.DatabaseError as exc:
        wrong.append(f"corpus.db doesn't read: {exc}")
    else:
        for key in ("advance", "rows", "heads"):
            if have[key] != want[key]:
                wrong.append(f"{key}: {have[key]} against {want[key]}")
    if verify_chain and not wrong and _chain(brain / "corpus.db") != want["verify_chain"]:
        wrong.append("verify_chain")
    if wrong:
        raise Mismatch(f"{brain} isn't what {manifest} says: " + "; ".join(wrong))


def fresh(dest: pathlib.Path, master: pathlib.Path, manifest: pathlib.Path) -> pathlib.Path:
    """A copy of the master, writable, checked. The master's bytes are only ever read."""
    if dest.exists():
        raise SystemExit(f"{dest} already exists: a fresh copy is made new, never over")
    if not (master / "corpus.db").is_file():
        raise Mismatch(f"no master at {master}. Build it: R1-acceptance.md, Fixtures")
    shutil.copytree(master, dest, copy_function=shutil.copyfile)
    for root, _dirs, files in os.walk(dest):
        for name in files:
            os.chmod(os.path.join(root, name), stat.S_IREAD | stat.S_IWRITE)
    check(dest, manifest)
    return dest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="build and copy BRAIN-COPY")
    ap.add_argument("action", choices=("build", "fresh", "check"))
    ap.add_argument("path", type=pathlib.Path)
    ap.add_argument("--manifest", type=pathlib.Path, required=True)
    ap.add_argument("--master", type=pathlib.Path, default=None)
    ap.add_argument("--verify-chain", action="store_true")
    a = ap.parse_args(argv)
    master = a.master or common.master_dir()
    try:
        if a.action == "build":
            doc = build(a.path, master, a.manifest)
            print(json.dumps({k: doc[k] for k in ("advance", "rows", "built_seconds")}))
        elif a.action == "fresh":
            started = time.monotonic()
            fresh(a.path, master, a.manifest)
            print(f"fresh copy, checked, in {time.monotonic() - started:.1f} s")
        else:
            started = time.monotonic()
            check(a.path, a.manifest, verify_chain=a.verify_chain)
            print(f"matches, in {time.monotonic() - started:.1f} s")
    except Mismatch as exc:
        print(f"MISMATCH: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
