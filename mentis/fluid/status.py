"""Fluid status: what the record says NOW, kept small and indexed BESIDE it
(opr-03012a1c7a95).

    <corpus>/derived/status.db

DERIVED, AND NEVER AUTHORITATIVE. Every row here is computed from the record
by a rule stated in the spine (`Store.toward_since`), and the file can be
deleted at any time, as `derived/extractions` can: the next read rebuilds
it, and answers from the record itself until it has. Nothing in corpus.db,
its schema or its write path knows this file exists; nothing that forms
context, delivers or governs reads it.

ONE TABLE TODAY, `toward`: one row per (who, post) for each post that turns
toward somebody -- names them in `addressed_to`, was addressed to them later
(`turn-addressed`), or replies to a post of theirs -- with the post's `seq`
and `at` (when it was written) and `why`. Indexed (who, at DESC, seq DESC),
so For you's page is the first rows of one index range, whatever the record
holds. `meta` has a row per derived table, saying what it was built under
and how far into the record it has read; a later table adds its own.

    meta(name, rules, corpus_id, entry_seq, entry_id, op_seq, op_id,
         built_at)
    toward(who, post, seq, at, why)

CURRENT BY CATCH-UP ON READ. Before answering, under one lock per file in
this process, the rows written after `meta`'s positions are read
(`seq > ?`), the posts they touch named, and each touched post's rows
replaced by its set recomputed from the record -- never added to or counted
down. Unmoved, that is one statement on the record.

RECOVERY. The whole table is rebuilt from the start when the file is missing
or unreadable, when it was built under other rules or for another corpus, or
when its positions are not positions of this record any more -- past its
end, or held by another row, as after a restore. The rebuild runs in a
thread of its own; until it is done, and whenever this file cannot be used,
the answer is `Store.toward_page`'s, read from the record. A rebuild that
fails is retried no sooner than RETRY seconds later.

    python -m mentis.fluid.status verify  --corpus <brain>
    python -m mentis.fluid.status rebuild --corpus <brain>

`verify` builds the table again into a temporary file and compares it with
the live one, at the same positions; it exits nonzero on any difference.
`rebuild` rebuilds the live file now.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import threading
import time

from mentis.spine.store import reading_beside_writer

FILE = pathlib.Path("derived") / "status.db"
#: This file's tables. Another is a rebuild from nothing.
SCHEMA = 1
#: The rules `toward` is built by: bump when `Store.toward_since` changes
#: what it says, and every file built under another is rebuilt.
RULES = 1
#: The derived table For you reads, as `meta` names it.
TOWARD = "toward"
#: `toward_since`'s why, by number.
WHY = ("named", "addressed", "reply")
#: Seconds before a rebuild that failed is tried again.
RETRY = 60.0

_TABLES = """
CREATE TABLE IF NOT EXISTS meta (
    name      TEXT PRIMARY KEY,
    rules     TEXT NOT NULL,
    corpus_id TEXT NOT NULL,
    entry_seq INTEGER NOT NULL,
    entry_id  TEXT,
    op_seq    INTEGER NOT NULL,
    op_id     TEXT,
    built_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS toward (
    who  TEXT NOT NULL,
    post TEXT NOT NULL,
    seq  INTEGER NOT NULL,
    at   REAL NOT NULL,
    why  TEXT NOT NULL,
    PRIMARY KEY (post, who)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_toward_who ON toward(who, at DESC, seq DESC);
"""


class Unusable(Exception):
    """This file cannot answer, and must be built again from the start."""


class _RecordFailed(Exception):
    """The RECORD could not be read: nothing wrong with this file."""


def path_of(root) -> pathlib.Path:
    return pathlib.Path(root) / FILE


def rules_of(spec) -> str:
    """The rules a table is built under: RULES and what it is asked for."""
    return json.dumps([RULES, SCHEMA, spec["kind"], spec["home"],
                       spec["replies"], spec["field"], spec.get("addressed")])


# -- one file, in this process -------------------------------------------------

class _Place:
    def __init__(self, path):
        self.path = path
        #: held for every read or write of the file by this process
        self.lock = threading.Lock()
        self.building: threading.Thread | None = None
        self.failed_at = 0.0
        #: why the last rebuild failed, if it did
        self.error: str | None = None
        #: why the last answer was the record's rather than this file's
        self.reason: str | None = None


_places: dict[str, _Place] = {}
_places_lock = threading.Lock()


def _place(corpus) -> _Place:
    # by name alone: `resolve()` asks the file system, and the answer can
    # differ while the file is being removed and made again
    path = os.path.normcase(os.path.abspath(path_of(corpus.root)))
    with _places_lock:
        if path not in _places:
            _places[path] = _Place(path)
        return _places[path]


def _connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None, timeout=5.0,
                           check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except BaseException:
        conn.close()          # or the file stays open, and cannot be removed
        raise
    return conn


def _transient(exc) -> bool:
    """Busy or locked: try again later, never a reason to rebuild."""
    return getattr(exc, "sqlite_errorname", "") in ("SQLITE_BUSY",
                                                    "SQLITE_LOCKED") \
        or "locked" in str(exc) or "busy" in str(exc)


def _meta(conn, name) -> dict | None:
    if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA:
        return None
    row = conn.execute(
        "SELECT rules, corpus_id, entry_seq, entry_id, op_seq, op_id, "
        "built_at FROM meta WHERE name = ?", (name,)).fetchone()
    if row is None:
        return None
    return {"rules": row[0], "corpus": row[1],
            "at": (row[2], row[3], row[4], row[5]), "built_at": row[6]}


# -- building ------------------------------------------------------------------

def _write_all(path, got, rules, *, fresh):
    """The whole table, as `got` (a `toward_since(None)` answer) says, in
    one transaction. `fresh`: the file is removed first, with its WAL."""
    if fresh:
        for p in (path, path + "-wal", path + "-shm"):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = _connect(path)
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA:
            conn.executescript("DROP TABLE IF EXISTS meta;"
                               "DROP TABLE IF EXISTS toward;")
        conn.executescript(_TABLES)
        conn.execute(f"PRAGMA user_version={SCHEMA}")
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM toward")
            conn.execute("DELETE FROM meta WHERE name = ?", (TOWARD,))
            conn.executemany(
                "INSERT INTO toward (who, post, seq, at, why) "
                "VALUES (?, ?, ?, ?, ?)",
                [(r[0], r[1], r[2], r[3], WHY[r[4]]) for r in got["rows"]])
            _set_meta(conn, rules, got)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def _set_meta(conn, rules, got):
    es, eid, os_, oid = got["at"]
    conn.execute(
        "INSERT OR REPLACE INTO meta (name, rules, corpus_id, entry_seq, "
        "entry_id, op_seq, op_id, built_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (TOWARD, rules, got["corpus"], es, eid, os_, oid, time.time()))


def build(corpus, spec, path=None, *, fresh=False) -> dict:
    """Build `toward` from the start, now, into `path` (the live file by
    default). Returns the record position it was built at."""
    path = str(path or path_of(corpus.root))
    with reading_beside_writer():
        got = corpus.toward_since(None, **spec)
    _write_all(path, got, rules_of(spec), fresh=fresh)
    return got


def _start_build(corpus, place, spec, *, fresh):
    """A rebuild in a thread of its own, unless one is running or the last
    failed less than RETRY seconds ago. Called under `place.lock`."""
    if place.building is not None and place.building.is_alive():
        return
    if time.time() - place.failed_at < RETRY:
        return

    def run():
        try:
            with reading_beside_writer():
                got = corpus.toward_since(None, **spec)
            with place.lock:
                _write_all(place.path, got, rules_of(spec), fresh=fresh)
            place.error = None
        except Exception as exc:      # answered from the record meanwhile
            place.failed_at = time.time()
            place.error = f"{type(exc).__name__}: {exc}"

    place.building = threading.Thread(target=run, daemon=True,
                                      name="fluid-status-build")
    place.building.start()


def settle(corpus, timeout=30.0) -> bool:
    """Wait for a rebuild of this corpus's file to end. True if none runs."""
    t = _place(corpus).building
    if t is not None:
        t.join(timeout)
        return not t.is_alive()
    return True


# -- catching up -----------------------------------------------------------------

def _catch_up(conn, corpus, spec, rules):
    """Bring `toward` up to the record now. Raises Unusable when it must be
    rebuilt; returns False when another process moved it meanwhile."""
    meta = _meta(conn, TOWARD)
    if meta is None or meta["rules"] != rules:
        raise Unusable("built under other rules, or not built")
    try:
        got = corpus.toward_since(meta["at"], **spec)
    except sqlite3.Error as exc:
        raise _RecordFailed(exc) from exc
    if got["corpus"] != meta["corpus"]:
        raise Unusable("built for another corpus")
    if got["foreign"]:
        raise Unusable("its positions are not this record's")
    if not got["moved"]:
        return True
    conn.execute("BEGIN IMMEDIATE")
    try:
        now = _meta(conn, TOWARD)
        if now is None or now["at"] != meta["at"]:
            conn.execute("ROLLBACK")
            return False
        conn.execute("DELETE FROM toward WHERE post IN "
                     "(SELECT value FROM json_each(?))",
                     (json.dumps(got["nodes"]),))
        conn.executemany(
            "INSERT INTO toward (who, post, seq, at, why) "
            "VALUES (?, ?, ?, ?, ?)",
            [(r[0], r[1], r[2], r[3], WHY[r[4]]) for r in got["rows"]])
        _set_meta(conn, rules, got)
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return True


def _page(conn, who, before, limit) -> list[tuple]:
    args = [who]
    cursor = ""
    if before is not None:
        cursor = "AND (at, seq) < (?, ?)"
        args += [before[0], before[1]]
    args.append(max(1, int(limit)))
    return [tuple(r) for r in conn.execute(
        f"SELECT post, seq, at FROM toward WHERE who = ? {cursor} "
        f"ORDER BY at DESC, seq DESC LIMIT ?", args)]


def _from_file(corpus, place, spec, who, before, limit):
    """The page from this file, caught up first; None where it cannot, and
    why in `place.reason`."""
    def fallback(reason, build=None):
        place.reason = reason
        if build is not None:
            _start_build(corpus, place, spec, fresh=build)
        return None

    if not os.path.exists(place.path):
        return fallback("missing", build=True)
    try:
        conn = _connect(place.path)
    except sqlite3.Error as exc:
        return fallback(f"unopenable: {exc}",
                        build=None if _transient(exc) else True)
    try:
        if not _catch_up(conn, corpus, spec, rules_of(spec)):
            return fallback("moved by another process")
        return _page(conn, who, before, limit)
    except Unusable as exc:
        return fallback(str(exc), build=False)
    except _RecordFailed as exc:
        # the record's own read, made next, says what is wrong
        return fallback(f"the record: {exc}")
    except sqlite3.Error as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        return fallback(f"unreadable: {exc}",
                        build=None if _transient(exc) else True)
    finally:
        conn.close()


def toward_page(corpus, who, *, kind, home, replies, field, addressed=None,
                before=None, limit=30) -> list[tuple]:
    """`Store.toward_page`'s answer, from this file: (id, seq, recorded_at)
    of the posts of `kind` turning toward `who`, newest first, one page.
    The same rows in the same order for the same arguments; read from the
    record instead while this file is being built or cannot be used.

    COST, with the file current: two statements on this file (its `meta`
    row and the page, one index range) and one on the record; with rows
    written since, two more on the record over those rows and the posts
    they touch, and one write here. None grows with the posts recorded."""
    spec = {"kind": kind, "home": home, "replies": replies, "field": field,
            "addressed": addressed}
    place = _place(corpus)
    rows = None
    if place.building is None or not place.building.is_alive():
        with place.lock:
            rows = _from_file(corpus, place, spec, who, before, limit)
    else:
        place.reason = "being built"
    if rows is None:
        rows = corpus.toward_page(who, before=before, limit=limit, **spec)
    return rows


# -- verify and rebuild ----------------------------------------------------------

def _rows(path) -> set:
    conn = sqlite3.connect(path)
    try:
        return set(conn.execute("SELECT who, post, seq, at, why FROM toward"))
    finally:
        conn.close()


def verify(corpus, spec, *, tries=5) -> dict:
    """Build `toward` again into a temporary file and compare it with the
    live one at the same record position. {"same", "live", "at", ...}."""
    live = str(path_of(corpus.root))
    rules = rules_of(spec)
    place = _place(corpus)
    out = {"same": False, "live": live}
    if not os.path.exists(live):
        out["problem"] = "the live file is missing"
        return out
    tmp = tempfile.mkdtemp(prefix="mentis-status-verify-")
    try:
        for _ in range(tries):
            with place.lock:
                conn = _connect(live)
                try:
                    try:
                        if not _catch_up(conn, corpus, spec, rules):
                            continue
                    except Unusable as exc:
                        out["problem"] = f"the live file is unusable: {exc}"
                        return out
                    meta = _meta(conn, TOWARD)
                finally:
                    conn.close()
            fresh = os.path.join(tmp, "status.db")
            got = build(corpus, spec, fresh, fresh=True)
            if tuple(got["at"]) != tuple(meta["at"]):
                continue                  # the record moved between the two
            a, b = _rows(live), _rows(fresh)
            out.update(same=a == b, at=list(meta["at"]), rows=len(b),
                       missing=sorted(map(list, b - a))[:20],
                       extra=sorted(map(list, a - b))[:20],
                       corpus=meta["corpus"] == got["corpus"])
            out["same"] = out["same"] and out["corpus"]
            return out
        out["problem"] = f"the record kept moving, {tries} times"
        return out
    except sqlite3.Error as exc:
        out["problem"] = f"the live file is unreadable: {exc}"
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    import argparse
    from mentis.fluid.home import TOWARD_OWNER as FOR_YOU
    from mentis.spine.seam import Corpus
    p = argparse.ArgumentParser(prog="python -m mentis.fluid.status")
    p.add_argument("command", choices=("verify", "rebuild"))
    p.add_argument("--corpus", required=True, help="the brain directory")
    a = p.parse_args(argv)
    corpus = Corpus(a.corpus)
    try:
        if a.command == "rebuild":
            t = time.perf_counter()
            with _place(corpus).lock:
                got = build(corpus, FOR_YOU, fresh=True)
            print(json.dumps({"rebuilt": str(path_of(corpus.root)),
                              "at": got["at"], "rows": len(got["rows"]),
                              "ms": round((time.perf_counter() - t) * 1e3,
                                          1)}))
            return 0
        got = verify(corpus, FOR_YOU)
        print(json.dumps(got, indent=1))
        return 0 if got["same"] else 1
    finally:
        corpus.close()


if __name__ == "__main__":
    # `mentis.fluid` has imported this module already; run THAT one, so its
    # lock and file state are the ones every other reader here uses
    from mentis.fluid.status import main as _main
    sys.exit(_main())
