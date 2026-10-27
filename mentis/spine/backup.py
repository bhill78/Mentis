"""Back up a Brain, verify a backup, plan a restore, restore, keep backups.

Deliverable 1 "Safe Brain Evolution", step 2 (owner-approved brief
adm-8ac4ef2f4866, section 3). Consumes the schema authority
(`mentis.spine.migrations`), the locks (`mentis.spine.brainlock`), the store's
own snapshot (`Store.snapshot`, SQLite's backup API) and the held byte store
(`mentis.spine.held`); it duplicates none of them.

TWO KINDS OF BACKUP.

  local-recovery  (default, R2) `corpus.db` through the backup API, copies of
                  `instances/`, `mentis-corpus.json` and `presentation/`, and a
                  MANIFEST (digest + size) of the immutable stored files the
                  record refers to -- not their bytes. It is usable only while
                  every one of them is present and intact in the live Brain's
                  store, and verifying it checks exactly that.
  portable        the same, plus a copy of every referenced stored file, so it
                  restores on another machine by itself.

"Referenced" is what `Corpus.snapshot` would copy: the digests named by held
Admissions that are not purged -- read from the backup's OWN copy of the
database, so the manifest describes that copy and nothing later.

A backup is written into `<dest>.partial` and renamed to `<dest>` only after
it verifies, so a killed backup never looks complete. One that fails its
creation checks is removed at once: the only deletion anything here does
without being asked.

RESTORE is planned first and the plan WRITES NOTHING. Its `digest` covers
everything the decision depends on, so any change to the live Brain makes an
earlier digest stale, and `restore` refuses without the digest of a plan of
the CURRENT state. Restore takes the OPEN lock exclusive for its whole length
and never deletes: what the backup replaces is MOVED into a quarantine folder
beside the Brain, `<brain>.quarantine-<id>/`, with a `RESTORE.json` intent
written before anything moves. A restore that dies part-way is completed or
reversed by `resume_restore`; a quarantine folder is removed only by
`discard_quarantine`, typed by somebody. Nothing restores automatically (D4).

RETENTION (R1) never prunes on its own: `prune` is a dry run unless confirmed
and protects the newest usable backup, the backups an unfinished restore uses
(wherever it restores to: a restore pins its backup before it begins), the
last usable backup before each breaking migration (until the owner releases
it), every backup younger than 30 days and the newest 5 usable ones -- and,
by the same counts, RECOVERY POINTS: backups intact in themselves. One that
only the live store's damage makes unusable is protected while that lasts,
so a damaged store never makes recovery points prunable. Quarantine folders
are never pruned.

A PORTABLE RESTORE HASHES EVERY STORED FILE it relies on: each copy before it
is put in place, each the Brain already holds (one that fails is moved into
the quarantine, never written over), and all of them again at the final
check. A resumed restore re-verifies its backup first.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone

from mentis.spine import brainlock, held, migrations, store

FORMAT = 1
DB = migrations.DB
MANIFEST = "BACKUP.json"
INTENT = "RESTORE.json"
RELEASED = "RELEASED.json"
PARTIAL = ".partial"
LOCAL = "local-recovery"
PORTABLE = "portable"
RESTORED_ACT = "brain-restored"
ABORTED = "aborted-restore"
#: in a quarantine: the Brain's own stored files a portable restore found
#: not hashing to their names, moved aside (never written over)
REPLACED_BLOBS = "replaced-stored-files"

#: what a backup carries besides the database, those that exist
AUX = ("instances", "mentis-corpus.json", "presentation")
#: SQLite's files beside a database. Whichever are present AT MOVE TIME are
#: moved with it, and none may be beside the backup's copy when it is put in
#: place: SQLite would replay a WAL it found there into the restored file.
SIDECARS = (DB + "-wal", DB + "-shm", DB + "-journal")
#: what a restore moves aside: the sidecars, the database, then the rest
REPLACED = SIDECARS + (DB,) + AUX
#: the order copies are renamed into place: corpus.db last
PLACE_ORDER = AUX + (DB,)
#: the scratch tables, fingerprinted by the plan in a stable order. Written
#: out whole, so the scratch boundary guard (tests/test_scratch.py) sees this
#: module read them -- and only read them.
SCRATCH = (("scratch", "SELECT * FROM scratch ORDER BY id"),
           ("scratch_message", "SELECT * FROM scratch_message "
                               "ORDER BY scratch, n"),
           ("scratch_setting", "SELECT * FROM scratch_setting ORDER BY one"))

#: never copied into a backup, at any depth
_SKIP = set(brainlock.LOCK_FILES) | {".pytest_cache", "__pycache__"}

#: retention (R1)
KEEP_DAYS = 30
KEEP_NEWEST = 5
NEWEST_SHOWN = 5


class BackupRefused(RuntimeError):
    """Declined, said in words. Nothing was changed."""


class RestoreFailed(RuntimeError):
    """A restore step failed. Nothing was deleted; the quarantine folder and
    its RESTORE.json say where it stopped, and `resume_restore` completes or
    reverses it."""


# -- small helpers ---------------------------------------------------------------

def _now() -> float:
    return time.time()


def _stamp(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fsync_file(path: str) -> None:
    try:
        with open(path, "rb+") as fh:
            os.fsync(fh.fileno())
    except OSError:
        pass


def _fsync_dir(path: str) -> None:
    """A rename is durable once its directory is. POSIX only: Windows cannot
    open a directory for fsync, and NTFS journals the rename itself."""
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _write_json(path: str, doc: dict) -> None:
    """Written whole or not at all: a temp file, fsync, then rename over."""
    tmp = f"{path}.tmp-{uuid.uuid4().hex[:8]}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True, default=str)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    _fsync_dir(os.path.dirname(path))


def _read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else None
    except (OSError, ValueError):
        return None


def _skip(name: str) -> bool:
    return name in _SKIP or name.endswith("-wal") or name.endswith("-shm")


def _copy_file(src: str, dst: str) -> str:
    shutil.copy2(src, dst)
    _fsync_file(dst)
    return dst


def _copy_item(src: str, dst: str) -> None:
    if os.path.isdir(src):
        shutil.copytree(src, dst, copy_function=_copy_file,
                        ignore=lambda d, names: [n for n in names if _skip(n)])
        _fsync_dir(dst)
    else:
        _copy_file(src, dst)


def _item_manifest(base: str, name: str) -> dict:
    """{relative posix path: {size, sha256}} for one carried item."""
    out = {}
    top = os.path.join(base, name)
    if os.path.isfile(top):
        out[name] = {"size": os.path.getsize(top), "sha256": _sha256_file(top)}
        return out
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = sorted(d for d in dirnames if not _skip(d))
        for f in sorted(filenames):
            if _skip(f):
                continue
            p = os.path.join(dirpath, f)
            rel = os.path.relpath(p, base).replace(os.sep, "/")
            out[rel] = {"size": os.path.getsize(p), "sha256": _sha256_file(p)}
    return out


def _same_path(a, b) -> bool:
    if not a or not b:
        return False
    return (os.path.normcase(os.path.abspath(a))
            == os.path.normcase(os.path.abspath(b)))


def _move(src: str, dst: str) -> None:
    """A rename, never a copy and delete."""
    os.rename(src, dst)
    _fsync_dir(os.path.dirname(dst))
    if not _same_path(os.path.dirname(src), os.path.dirname(dst)):
        _fsync_dir(os.path.dirname(src))


def _free_name(path: str) -> str:
    if not os.path.exists(path):
        return path
    n = 1
    while os.path.exists(f"{path}.{n}"):
        n += 1
    return f"{path}.{n}"


# -- reading a database without a Store ------------------------------------------

def _connect(path: str) -> sqlite3.Connection:
    """A reading connection that takes no Brain lock and writes nothing."""
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # NEVER CHECKPOINT A WAL THAT WAS ALREADY THERE: the last connection to
    # close would fold it into the file and delete it, and a reader must not
    # change which files a Brain is made of. (One this reader made itself,
    # empty, it may tidy away as SQLite always does.)
    if hasattr(conn, "setconfig") and os.path.exists(path + "-wal"):
        conn.setconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, True)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA query_only=ON")
    return conn


def _chain(conn: sqlite3.Connection) -> dict | None:
    """`Store.verify_chain` over a bare connection, so a backup's copy is
    checked by the store's own walk without opening a Store on it (which
    would take a lock, and write a lock file, in the backup folder). None
    for a database older than the chain columns."""
    tables = migrations._tables(conn)
    for t in migrations.CHAINED_TABLES:
        if t not in tables:
            return None
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
        if "hash" not in cols:
            return None
    if "corpus" not in tables:
        return None
    s = store.Store.__new__(store.Store)
    s._conn, s._lock, s._writer = conn, threading.RLock(), None
    s._idle, s._idle_lock, s._closed = [], threading.Lock(), False
    return store.Store.verify_chain(s)


def _corpus_id(conn) -> str | None:
    if "corpus" not in migrations._tables(conn):
        return None
    row = conn.execute("SELECT corpus_id FROM corpus").fetchone()
    return row[0] if row else None


def _ledger(conn) -> dict:
    st = migrations.inspect(conn)
    return {"state": st.state, "version": st.version,
            "min_reader": st.min_reader, "user_version": st.user_version,
            "rows": [[r["seq"], r["id"], r["kind"], r["to_version"],
                      r["checksum"]] for r in st.ledger]}


def _referenced(conn) -> list[str]:
    """The digests `Corpus.snapshot` would copy: named by a held Admission
    that is not purged."""
    if "entry" not in migrations._tables(conn):
        return []
    named = set()
    for row in conn.execute(
            "SELECT e.body FROM entry e WHERE e.def_name = 'admission' "
            "AND NOT EXISTS (SELECT 1 FROM entry l WHERE "
            "l.link_relation = ? AND l.link_to = e.id)", (held.PURGED,)):
        try:
            body = json.loads(row[0])
        except (TypeError, ValueError):
            continue
        if isinstance(body, dict) and body.get("content") == "held":
            d = held.digest_of(body.get("locator"))
            if d:
                named.add(d)
    return sorted(named)


def _purged_digests(brain: str) -> set[str]:
    """The digests this Brain's record has PURGED: named by a purged
    Admission and by no held Admission that is not. A purge is the owner's
    decision, not damage, and nothing repairs it. Read without writing; an
    unreadable record answers nothing purged (so a lack stays the store's)."""
    db = os.path.join(brain, DB)
    if not os.path.isfile(db):
        return set()
    try:
        conn = _connect(db)
        try:
            if "entry" not in migrations._tables(conn):
                return set()
            gone = set()
            for row in conn.execute(
                    "SELECT e.body FROM entry e WHERE e.def_name = 'admission' "
                    "AND EXISTS (SELECT 1 FROM entry l WHERE "
                    "l.link_relation = ? AND l.link_to = e.id)",
                    (held.PURGED,)):
                try:
                    body = json.loads(row[0])
                except (TypeError, ValueError):
                    continue
                if isinstance(body, dict) and body.get("content") == "held":
                    d = held.digest_of(body.get("locator"))
                    if d:
                        gone.add(d)
            return gone - set(_referenced(conn))
        finally:
            conn.close()
    except sqlite3.Error:
        return set()


def _marker_id(root: str) -> str | None:
    doc = _read_json(os.path.join(root, "mentis-corpus.json"))
    return doc.get("corpus_id") if doc else None


def _default_dir(root: str, corpus_id: str) -> str:
    return os.path.join(os.path.dirname(root), "backups", corpus_id)


# -- backup ------------------------------------------------------------------------

def backup(root: str, dest: str | None = None, portable: bool = False, *,
           _hook=None) -> dict:
    """Take a backup of the Brain at `root`. Shared lock only: works beside a
    running server and on a Brain that predates the schema ledger."""
    stop = _hook or (lambda label: None)
    root = os.path.abspath(root)
    kind = PORTABLE if portable else LOCAL
    s = store.Store(root, access="read")        # the OPEN lock, shared
    try:
        corpus_id = s.corpus_id
        created = _now()
        if dest is None:
            dest = os.path.join(_default_dir(root, corpus_id),
                                f"{_stamp(created)}-{kind}")
        dest = os.path.abspath(dest)
        partial = dest + PARTIAL
        if os.path.exists(dest) or os.path.exists(partial):
            raise BackupRefused(f"{dest} already exists; a backup never "
                                f"writes over anything")
        os.makedirs(partial)
        db = os.path.join(partial, DB)
        s.snapshot(db)
        # ONE FILE, NO SIDECARS: the copy is switched out of WAL, so reading
        # it later never creates -wal/-shm beside it and its sha256 stays
        # what was recorded. A restore's first writable open switches it back.
        c = sqlite3.connect(db, isolation_level=None)
        try:
            c.execute("PRAGMA journal_mode=DELETE")
        finally:
            c.close()
        _fsync_file(db)
        stop("after-db-copy")
        for name in AUX:
            src = os.path.join(root, name)
            if os.path.exists(src):
                _copy_item(src, os.path.join(partial, name))
        stop("after-files")
    finally:
        s.close()
    try:
        conn = _connect(db)
        try:
            heads = migrations._heads(conn)
            ledger = _ledger(conn)
            referenced = _referenced(conn)
        finally:
            conn.close()
        manifest, problems = [], []
        for d in referenced:
            st, _ = held.state(root, d, verify=True)
            manifest.append({"digest": d, "size": (held.size(root, d)
                                                   if st == "present" else None)})
            if st != "present":
                problems.append(f"stored file {d} is {st} in the live Brain")
        copied = None
        if portable:
            copied = held.copy(root, partial, referenced, verify=True)
            for d in copied["source_corrupt"]:
                problems.append(f"stored file {d} did not hash to its name "
                                f"while it was copied")
        files = {}
        for name in AUX:
            if os.path.exists(os.path.join(partial, name)):
                files.update(_item_manifest(partial, name))
        doc = {
            "format": FORMAT, "id": f"bk-{uuid.uuid4().hex[:12]}",
            "kind": kind, "corpus_id": corpus_id,
            "marker_corpus_id": _marker_id(root), "brain": root,
            "created_at": created, "created_at_utc": _iso(created),
            "code": migrations.code_identity(),
            "ledger": {"state": ledger["state"], "version": ledger["version"],
                       "min_reader": ledger["min_reader"],
                       "user_version": ledger["user_version"]},
            "db_sha256": _sha256_file(db), "tables": heads,
            "stored_files": manifest, "items": sorted(
                n for n in (DB,) + AUX
                if os.path.exists(os.path.join(partial, n))),
            "files": files,
        }
        _write_json(os.path.join(partial, MANIFEST), doc)
        check = verify_backup(partial, brain=root, _creating=True)
        problems = list(dict.fromkeys(problems + check["problems"]))
        doc["creation_checks"] = {"usable": not problems, "problems": problems,
                                  "checked_at": _iso(_now()),
                                  "portable_copy": copied}
        if problems:
            raise BackupRefused(
                f"the backup did not verify and was removed: "
                + "; ".join(problems))
        _write_json(os.path.join(partial, MANIFEST), doc)
        stop("after-verify")
        os.rename(partial, dest)
        _fsync_dir(os.path.dirname(dest))
    except BackupRefused:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return {"backup": dest, "id": doc["id"], "kind": kind,
            "corpus_id": corpus_id, "ledger": doc["ledger"],
            "tables": heads, "stored_files": len(manifest),
            "db_sha256": doc["db_sha256"], "usable": True}


# -- verify ------------------------------------------------------------------------

def verify_backup(backup_dir: str, brain: str | None = None, *,
                  _creating: bool = False) -> dict:
    """Whether this backup can be restored from. Writes nothing anywhere.
    (`_creating`: the creation checks, run on the `.partial` folder before
    it is renamed to its name.)

    Two verdicts. `usable`: it can be restored from now. `intact`: the
    backup ITSELF is sound -- everything but whether the live Brain's store
    still holds the stored files a local-recovery backup refers to. A backup
    that is intact and not usable is made unusable by the live store's
    condition, not its own; retention keeps it as a recovery point
    (`live_store_problems` says what the live store lacks). A stored file
    the live record has since purged is not the store's condition: the
    owner ended possession, nothing repairs it, and the backup is unusable
    on its own account (not intact)."""
    backup_dir = os.path.abspath(backup_dir)
    problems: list[str] = []
    live_problems: list[str] = []
    out = {"backup": backup_dir, "usable": False, "intact": False,
           "problems": problems, "live_store_problems": live_problems,
           "complete": _creating or not backup_dir.endswith(PARTIAL)}
    meta = _read_json(os.path.join(backup_dir, MANIFEST))
    if meta is None:
        problems.append(f"no readable {MANIFEST}: not a finished backup")
        return out
    if meta.get("format") != FORMAT:
        problems.append(f"backup format {meta.get('format')!r} is not "
                        f"{FORMAT}")
        return out
    out.update(id=meta.get("id"), kind=meta.get("kind"),
               corpus_id=meta.get("corpus_id"),
               created_at=meta.get("created_at"),
               ledger=meta.get("ledger"))
    if not out["complete"]:
        problems.append("the backup was never completed (.partial)")
    db = os.path.join(backup_dir, DB)
    if not os.path.isfile(db):
        problems.append("corpus.db is missing")
        return out
    # the stored files the backup's OWN record refers to, never the list
    # BACKUP.json gives: that list is only checked against this
    referenced = None
    if _sha256_file(db) != meta.get("db_sha256"):
        problems.append("corpus.db does not hash to the recorded sha256")
    else:
        try:
            conn = _connect(db)
            try:
                ic = [r[0] for r in conn.execute("PRAGMA integrity_check")]
                if ic != ["ok"]:
                    problems.append(f"integrity_check: {ic[:5]}")
                chain = _chain(conn)
                if chain is not None and not chain["intact"]:
                    problems.append("hash chain broken: " + json.dumps(
                        {t: v["broken_at"] for t, v in chain["streams"].items()
                         if v["broken_at"]}))
                heads = migrations._heads(conn)
                for t in migrations.CHAINED_TABLES:
                    want = (meta.get("tables") or {}).get(t)
                    if want != heads[t]:
                        problems.append(f"{t}: the copy has {heads[t]}, the "
                                        f"backup recorded {want}")
                if chain is not None:
                    for t in migrations.CHAINED_TABLES:
                        if chain["streams"][t]["head"] != heads[t]["head"]:
                            problems.append(f"{t}: the chain head is not the "
                                            f"row at the highest seq")
                led = _ledger(conn)
                rec = meta.get("ledger") or {}
                if (led["version"], led["min_reader"]) != (
                        rec.get("version"), rec.get("min_reader")):
                    problems.append(
                        f"ledger reads version {led['version']} min_reader "
                        f"{led['min_reader']}; recorded {rec.get('version')} "
                        f"{rec.get('min_reader')}")
                out["ledger_state"] = led["state"]
                referenced = _referenced(conn)
            finally:
                conn.close()
        except sqlite3.Error as exc:
            problems.append(f"corpus.db cannot be read: {exc}")
    listed = {f.get("digest"): f.get("size")
              for f in meta.get("stored_files") or [] if isinstance(f, dict)}
    if referenced is not None and sorted(listed) != referenced:
        problems.append(
            f"{MANIFEST} lists {len(listed)} stored files; the backup's own "
            f"record refers to {len(referenced)}: "
            + ", ".join(sorted(set(listed) ^ set(referenced))[:5]))
    # the carried items, exactly
    have = {}
    for name in AUX:
        if os.path.exists(os.path.join(backup_dir, name)):
            have.update(_item_manifest(backup_dir, name))
    if have != (meta.get("files") or {}):
        diff = sorted(set(have) ^ set(meta.get("files") or {})) or sorted(
            k for k in have if have[k] != meta["files"].get(k))
        problems.append(f"carried files differ from the record: {diff[:5]}")
    # the stored files: in the backup's own copy (portable, its own
    # soundness) or in the live Brain's store (local recovery, the live
    # store's condition)
    kind = meta.get("kind")
    sink = problems
    if kind == PORTABLE:
        where, whose = backup_dir, "the backup's own copy"
    elif kind == LOCAL:
        sink = live_problems
        where = os.path.abspath(brain) if brain else meta.get("brain")
        whose = f"the live Brain's store at {where}"
        out["brain"] = where
        if not where or not os.path.isdir(where):
            live_problems.append(f"the live Brain {where} is not there; a "
                                 f"local recovery backup needs its stored "
                                 f"files")
            where = None
    else:
        problems.append(f"unknown kind {kind!r}")
        where = None
    digests = referenced if referenced is not None else sorted(listed)
    if where is not None:
        # a stored file the live record has since PURGED is gone for good:
        # that makes this backup unusable on its own account, never damage
        # the live store could repair
        purged = _purged_digests(where) if kind == LOCAL else set()
        bad, gone = [], []
        for d in digests:
            st, data = held.state(where, d, verify=True)
            if st != "present":
                (gone if d in purged else bad).append(f"{d} is {st}")
            elif listed.get(d) is not None and len(data) != listed[d]:
                bad.append(f"{d} has the wrong size")
        if gone:
            problems.append(
                "referenced stored files the live Brain has since purged "
                "(a purge is not repaired): " + "; ".join(gone[:10])
                + (f" (+{len(gone) - 10} more)" if len(gone) > 10 else ""))
        if bad:
            sink.append(f"referenced stored files not available in "
                        f"{whose}: " + "; ".join(bad[:10])
                        + (f" (+{len(bad) - 10} more)" if len(bad) > 10
                           else ""))
    out["stored_files"] = len(digests)
    out["intact"] = not problems
    problems.extend(live_problems)
    out["usable"] = not problems
    return out


# -- restore plan ---------------------------------------------------------------

_KIND_OF = {
    "entry": "family || '/' || COALESCE(def_name, '')",
    "operational": "act",
    "delivery": "mechanism",
}
_NEWEST = {
    "entry": "seq, id, family, def_name, recorded_at AS at",
    "operational": "seq, id, act, actor, at",
    "delivery": "seq, id, mechanism, execution, at",
}


def _meta(backup_dir: str) -> dict:
    meta = _read_json(os.path.join(backup_dir, MANIFEST))
    if meta is None:
        raise BackupRefused(f"{backup_dir} is not a backup (no {MANIFEST})")
    return meta


def _unfinished(root: str, *, ignore: str | None = None) -> list[dict]:
    """Restores into this Brain whose RESTORE.json is neither complete nor
    reversed -- a `.partial` quarantine included once its intent names a
    backup (killed before it got its name; `resume_restore` takes it up).
    `ignore`: a restore id to leave out (the one being resumed)."""
    parent, name = os.path.split(root)
    out = []
    try:
        names = os.listdir(parent)
    except OSError:
        return out
    for n in sorted(names):
        if not n.startswith(f"{name}.quarantine-"):
            continue
        partial = n.endswith(PARTIAL)
        qid = n[len(name) + len(".quarantine-"):
                len(n) - (len(PARTIAL) if partial else 0)]
        if qid == ignore:
            continue
        rec = _read_json(os.path.join(parent, n, INTENT))
        if partial and not (rec or {}).get("backup"):
            continue            # never started: nothing moved, no intent
        if rec is None or not (rec.get("complete") or rec.get("reversed")):
            out.append({"quarantine": os.path.join(parent, n), "id": qid,
                        "backup": (rec or {}).get("backup")})
    return out


#: in a backup, one file per restore that uses it: `RESTORES/<id>.json`
PINS = "RESTORES"


def _pin(backup_dir: str, rec: dict) -> bool:
    """Say inside the backup that a restore uses it, BEFORE that restore's
    quarantine exists, so retention protects it wherever the restore goes
    (a new location's quarantine is beside that location, not this Brain).
    A backup that cannot be written to is not pinned: nor can it be pruned."""
    try:
        os.makedirs(os.path.join(backup_dir, PINS), exist_ok=True)
        _write_json(os.path.join(backup_dir, PINS, f"{rec['id']}.json"),
                    {"restore_id": rec["id"], "brain": rec["brain"],
                     "quarantine": rec["quarantine"],
                     "started_at": rec["started_at"]})
        return True
    except OSError:
        return False


def _unpin(backup_dir: str, qid: str) -> None:
    """Once the restore is complete or reversed. Best effort: a pin left
    behind protects nothing once its restore is finished."""
    try:
        os.remove(os.path.join(backup_dir, PINS, f"{qid}.json"))
    except OSError:
        pass


def _pinned(backup_dir: str) -> list[str]:
    """The unfinished restores that use this backup, wherever they restore
    to. A pin whose quarantine never came to exist protects nothing (the
    restore died before it began); an unreadable pin or intent protects."""
    out = []
    try:
        names = sorted(os.listdir(os.path.join(backup_dir, PINS)))
    except OSError:
        return out
    for n in names:
        if not n.endswith(".json"):
            continue
        pin = _read_json(os.path.join(backup_dir, PINS, n))
        if pin is None or not pin.get("quarantine"):
            out.append(n[:-5])
            continue
        for where in (pin["quarantine"], pin["quarantine"] + PARTIAL):
            if os.path.isdir(where):
                rec = _read_json(os.path.join(where, INTENT))
                if rec is None or not (rec.get("complete")
                                       or rec.get("reversed")):
                    out.append(pin.get("restore_id") or n[:-5])
                break
    return out


def _digest(doc) -> str:
    return hashlib.sha256(json.dumps(
        doc, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")).hexdigest()


def _scratch_fingerprint(conn) -> dict:
    """Rows and a content digest of each scratch table, in key order."""
    have = migrations._tables(conn)
    out = {}
    for t, select in SCRATCH:
        if t not in have:
            out[t] = None
            continue
        rows = [list(r) for r in conn.execute(select)]
        out[t] = {"rows": len(rows), "sha256": _digest(rows)}
    return {"tables": out, "sha256": _digest(out)}


def _carried_fingerprint(root: str) -> dict:
    """Path, size and sha256 of every file of the carried items."""
    files = {}
    for name in AUX:
        if os.path.lexists(os.path.join(root, name)):
            files.update(_item_manifest(root, name))
    return {"files": len(files),
            "items": sorted(n for n in AUX
                            if os.path.lexists(os.path.join(root, n))),
            "sha256": _digest(files)}


def _compute_plan(root: str, backup_dir: str, meta: dict, *,
                  ignore: str | None = None) -> dict:
    """Everything a restore decision depends on, read without writing.
    (`ignore`: the restore being resumed, which is not "an earlier one".)"""
    check = verify_backup(backup_dir, brain=root)
    btables = meta.get("tables") or {}
    path = os.path.join(root, DB)
    tables, current, ledger_now, cid = {}, None, None, None
    scratch = None
    carried = _carried_fingerprint(root)
    purged = []
    mode = "replace" if os.path.isfile(path) else "new-location"
    if mode == "replace":
        conn = _connect(path)
        try:
            conn.execute("BEGIN")          # one moment of the record
            current = migrations._heads(conn)
            ledger_now = _ledger(conn)
            cid = _corpus_id(conn)
            scratch = _scratch_fingerprint(conn)
            have = migrations._tables(conn)
            for t in migrations.CHAINED_TABLES:
                b = btables.get(t) or {"count": 0, "max_seq": 0, "head": None}
                if t not in have:
                    tables[t] = {"backup": b, "current": current[t],
                                 "ancestor": b["count"] == 0, "discarded": 0,
                                 "discarded_by_kind": {},
                                 "newest_discarded": []}
                    continue
                kept = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE seq <= ?",
                                    (b["max_seq"],)).fetchone()[0]
                ok = kept == b["count"]
                if ok and b["max_seq"]:
                    h = conn.execute(f"SELECT hash FROM {t} WHERE seq = ?",
                                     (b["max_seq"],)).fetchone()
                    ok = (h[0] if h else None) == b["head"]
                by_kind = {k: n for k, n in conn.execute(
                    f"SELECT {_KIND_OF[t]} AS k, COUNT(*) FROM {t} "
                    f"WHERE seq > ? GROUP BY k ORDER BY k", (b["max_seq"],))}
                newest = [dict(r) for r in conn.execute(
                    f"SELECT {_NEWEST[t]} FROM {t} WHERE seq > ? "
                    f"ORDER BY seq DESC LIMIT {NEWEST_SHOWN}", (b["max_seq"],))]
                tables[t] = {"backup": b, "current": current[t], "ancestor": ok,
                             "discarded": sum(by_kind.values()),
                             "discarded_by_kind": by_kind,
                             "newest_discarded": newest}
            if "entry" in have:
                emax = (btables.get("entry") or {}).get("max_seq", 0)
                for r in conn.execute(
                        "SELECT l.seq, l.id, l.link_to, a.body FROM entry l "
                        "LEFT JOIN entry a ON a.id = l.link_to "
                        "WHERE l.link_relation = ? AND l.seq > ? ORDER BY l.seq",
                        (held.PURGED, emax)):
                    try:
                        body = json.loads(r["body"]) if r["body"] else {}
                    except ValueError:
                        body = {}
                    purged.append({"seq": r["seq"], "link": r["id"],
                                   "admission": r["link_to"],
                                   "digest": held.digest_of(
                                       (body or {}).get("locator"))})
            conn.execute("COMMIT")
        finally:
            conn.close()
    else:
        for t in migrations.CHAINED_TABLES:
            tables[t] = {"backup": btables.get(t), "current": None,
                         "ancestor": True, "discarded": 0,
                         "discarded_by_kind": {}, "newest_discarded": []}
    ancestor = all(v["ancestor"] for v in tables.values())
    bled = meta.get("ledger") or {}
    refusals = []
    if not check["usable"]:
        refusals.append("the backup is not usable: "
                        + "; ".join(check["problems"]))
    if mode == "replace" and cid != meta.get("corpus_id"):
        refusals.append(f"the backup is of corpus {meta.get('corpus_id')}; "
                        f"this Brain is corpus {cid}")
    elif not ancestor:
        refusals.append("DIVERGED: the backup is not an ancestor of this "
                        "Brain (" + ", ".join(
                            t for t, v in tables.items() if not v["ancestor"])
                        + " differ at or before the backup's last row)")
    unfinished = _unfinished(root, ignore=ignore)
    if unfinished:
        refusals.append("an earlier restore into this Brain is unfinished: "
                        + ", ".join(u["id"] for u in unfinished)
                        + "; resume or reverse it first")
    plan = {
        "brain": root, "backup": backup_dir, "backup_id": meta.get("id"),
        "backup_kind": meta.get("kind"),
        "backup_created_at": meta.get("created_at_utc"),
        "mode": mode, "corpus_id": cid,
        "backup_corpus_id": meta.get("corpus_id"),
        "ancestor": ancestor, "diverged": not ancestor,
        "tables": tables,
        "discarded": {t: v["discarded"] for t, v in tables.items()},
        "purged_since_backup": purged,
        "ledger": {"backup": {"version": bled.get("version"),
                              "min_reader": bled.get("min_reader"),
                              "state": bled.get("state")},
                   "current": (None if ledger_now is None else {
                       "version": ledger_now["version"],
                       "min_reader": ledger_now["min_reader"],
                       "state": ledger_now["state"]}),
                   "changes": (None if ledger_now is None
                               or ledger_now["version"] == bled.get("version")
                               else f"{bled.get('version')} -> "
                                    f"{ledger_now['version']}")},
        "scratch": scratch, "carried": carried,
        "usable": check["usable"], "problems": check["problems"],
        "restorable": not refusals, "refusals": refusals,
    }
    material = {
        "brain": os.path.normcase(root), "mode": mode,
        "backup_id": meta.get("id"), "db_sha256": meta.get("db_sha256"),
        "backup_tables": btables, "backup_kind": meta.get("kind"),
        "backup_files": meta.get("files"),
        "backup_items": meta.get("items"),
        "backup_stored_files": meta.get("stored_files"), "corpus_id": cid,
        "current": current, "ledger_now": ledger_now,
        "discarded": {t: [v["discarded"], v["discarded_by_kind"]]
                      for t, v in tables.items()},
        "ledger_backup": [bled.get("version"), bled.get("min_reader")],
        "purged": [p["link"] for p in purged], "usable": check["usable"],
        "unfinished": [u["id"] for u in unfinished],
        "scratch": scratch, "carried": carried,
    }
    plan["digest"] = _digest(material)
    return plan


def restore_plan(root: str, backup_dir: str) -> dict:
    """What `restore` would do, and the digest that confirms it. Writes
    nothing; holds the OPEN lock shared, so it refuses during a restore."""
    root = os.path.abspath(root)
    backup_dir = os.path.abspath(backup_dir)
    meta = _meta(backup_dir)
    if os.path.isdir(root):
        brainlock.refuse_if_restoring(root)
    lock = (brainlock.shared(root)
            if os.path.isfile(os.path.join(root, DB)) else None)
    try:
        return _compute_plan(root, backup_dir, meta)
    finally:
        if lock is not None:
            lock.release()


# -- restore ---------------------------------------------------------------------

def _qdir(root: str, qid: str) -> str:
    parent, name = os.path.split(root)
    return os.path.join(parent, f"{name}.quarantine-{qid}")


def _tmp(root: str, qid: str, name: str) -> str:
    return os.path.join(root, f".restore-{qid}-{name}")


def _confirmed(plan: dict, confirm: str | None) -> dict:
    if plan["refusals"]:
        raise BackupRefused("; ".join(plan["refusals"]))
    if not confirm:
        # NEVER THE DIGEST HERE: it is had only from restore-plan, with the
        # plan it confirms, so what is confirmed is what was seen (D4)
        raise BackupRefused(
            "restore needs --confirm with the digest that restore-plan "
            "prints: run `python -m mentis.brain restore-plan <brain> "
            "<backup>`, read what it would discard, and confirm with its "
            "digest")
    if confirm != plan["digest"]:
        raise BackupRefused(
            "the confirmed digest is not the digest of the current state: "
            "the Brain (its records, scratch, instances/, marker or "
            "presentation/) or the backup changed since the plan was made. "
            "Stop the server, then run restore-plan again and confirm with "
            "the digest it prints")
    return plan


# -- the restoring marker ---------------------------------------------------------

def _mark(root: str, rec: dict) -> None:
    """`<brain>/.mentis.restoring`: every opener and creator refuses while it
    exists. Written after the intent, before anything moves."""
    _write_json(os.path.join(root, brainlock.RESTORING),
                {"quarantine_id": rec["id"], "quarantine": rec["quarantine"],
                 "backup": rec["backup"], "started_at": rec["started_at"]})


def _unmark(root: str, qid: str) -> None:
    """Remove the marker if it is this restore's: only once the restore is
    marked complete, or once a reverse has put the originals back."""
    got = brainlock.restoring(root)
    if got is not None and got.get("quarantine_id") == qid:
        os.remove(os.path.join(root, brainlock.RESTORING))
        _fsync_dir(root)


def restore(root: str, backup_dir: str, confirm: str | None = None, *,
            _hook=None) -> dict:
    """Put the Brain back to `backup_dir`. Needs the digest of a plan of the
    current state. Exclusive lock throughout; nothing is ever deleted."""
    stop = _hook or (lambda label: None)
    root = os.path.abspath(root)
    backup_dir = os.path.abspath(backup_dir)
    meta = _meta(backup_dir)
    if not os.path.isdir(root):
        # a new location: refuse before making anything there
        if os.path.exists(root):
            raise BackupRefused(f"{root} is not a directory")
        _confirmed(_compute_plan(root, backup_dir, meta), confirm)
        os.makedirs(root)
    lock = brainlock.exclusive(root, "restore")    # refuses beside a marker
    try:
        plan = _confirmed(_compute_plan(root, backup_dir, meta), confirm)
        qid = f"{_stamp(_now())}-{uuid.uuid4().hex[:6]}"
        q = _qdir(root, qid)
        rec = {
            "format": FORMAT, "id": qid, "brain": root, "quarantine": q,
            "backup": backup_dir, "backup_id": meta["id"],
            "backup_kind": meta["kind"], "plan_digest": plan["digest"],
            "discarded": plan["discarded"],
            #: the live record the plan was made of; a resume refuses to go
            #: forward over anything written since
            "live": {t: v["current"] for t, v in plan["tables"].items()}
                    if plan["mode"] == "replace" else None,
            "originals": [n for n in REPLACED
                          if os.path.lexists(os.path.join(root, n))],
            "items": list(meta.get("items") or [DB]),
            "moved": [], "placed": [], "blobs_added": None,
            "blobs_replaced": [],
            "steps": {"intent": True, "moved": False, "copied_in": False,
                      "renamed": False, "recorded": None, "verified": False},
            "started_at": _iso(_now()), "complete": False, "reversed": False,
        }
        # the backup is protected from prune before anything depends on it
        rec["pinned"] = _pin(backup_dir, rec)
        # the quarantine never exists under its name without a readable
        # intent in it: made as `.partial`, written, then renamed -- and the
        # marker goes down BEFORE the rename, so there is no moment at which
        # an unfinished restore stands and the Brain can be opened
        os.makedirs(q + PARTIAL)
        _write_json(os.path.join(q + PARTIAL, INTENT), rec)
        stop("before-marker")
        _mark(root, rec)
        stop("after-marker")
        os.rename(q + PARTIAL, q)
        _fsync_dir(os.path.dirname(q))
        stop("after-intent")
        return _drive(root, q, rec, meta, _hook)
    finally:
        lock.release()


def _matches(path: str, base_name: str, meta: dict) -> bool:
    """Whether a temp copy is a complete copy of the backup's item."""
    if base_name == DB:
        return os.path.isfile(path) and _sha256_file(path) == meta["db_sha256"]
    want = {k: v for k, v in (meta.get("files") or {}).items()
            if k == base_name or k.startswith(base_name + "/")}
    parent, tmpname = os.path.split(path)
    got = {}
    for k, v in _item_manifest(parent, tmpname).items():
        got[base_name + k[len(tmpname):]] = v
    return got == want


def _drive(root: str, q: str, rec: dict, meta: dict, hook) -> dict:
    """Steps 2-5, each idempotent, so a restore and its resumption are one
    path. The caller holds the exclusive lock and the marker is in place."""
    stop = hook or (lambda label: None)
    qid = rec["id"]
    intent = os.path.join(q, INTENT)
    bdir = rec["backup"]

    def save():
        _write_json(intent, rec)

    def move_aside(name: str, *, stray: bool) -> None:
        """Recorded BEFORE it is moved, so a kill between the two is seen."""
        dst = _free_name(os.path.join(q, name))
        rec["moved"].append({"name": name, "to": os.path.basename(dst),
                             "stray": stray})
        save()
        _move(os.path.join(root, name), dst)
        stop(f"after-move:{name}")

    # a move recorded and not made (killed between the two) is made now
    for e in rec["moved"]:
        src, dst = os.path.join(root, e["name"]), os.path.join(q, e["to"])
        if not os.path.lexists(dst) and os.path.lexists(src):
            _move(src, dst)

    # (2) MOVE what the backup replaces, as it is NOW: the sidecars present
    # at move time (a writer that died may have left one since the intent),
    # then the database, then the carried items. A sidecar is STRAY when no
    # original database is beside it: it belongs to nothing being kept.
    if not rec["steps"]["moved"]:
        db_moved = any(e["name"] == DB for e in rec["moved"])
        for name in SIDECARS:
            if os.path.lexists(os.path.join(root, name)):
                move_aside(name, stray=db_moved or not os.path.lexists(
                    os.path.join(root, DB)))
        if os.path.lexists(os.path.join(root, DB)):
            move_aside(DB, stray=False)
        for name in AUX:
            if os.path.lexists(os.path.join(root, name)):
                move_aside(name, stray=False)
        rec["steps"]["moved"] = True
        save()

    # (3) COPY the backup in under temp names, then rename into place. After
    # step 2 nothing of these names is in the Brain but what was placed.
    pending = [n for n in PLACE_ORDER if n in rec["items"]
               and not os.path.lexists(os.path.join(root, n))]
    if pending:
        if _sha256_file(os.path.join(bdir, DB)) != meta["db_sha256"]:
            raise RestoreFailed(f"the backup's corpus.db at {bdir} no longer "
                                f"hashes to its record")
        for name in pending:
            tmp = _tmp(root, qid, name)
            if os.path.lexists(tmp):
                if _matches(tmp, name, meta):
                    continue
                os.makedirs(os.path.join(q, ABORTED), exist_ok=True)
                _move(tmp, _free_name(os.path.join(q, ABORTED,
                                                   os.path.basename(tmp))))
            _copy_item(os.path.join(bdir, name), tmp)
            if not _matches(tmp, name, meta):
                raise RestoreFailed(f"the copy of {name} does not match the "
                                    f"backup's record")
    if meta.get("kind") == PORTABLE:
        # EVERY STORED FILE HASHED: each copy before it is put in place, and
        # each the Brain already has. One of the Brain's that does not hash
        # to its name is MOVED into the quarantine (recorded first; never
        # written over, never deleted) and the backup's copied in its place.
        digests = sorted({f["digest"] for f in meta.get("stored_files") or []})
        if rec.get("blobs_added") is None:
            rec["blobs_added"] = [d for d in digests if not held.has(root, d)]
            save()
        rec.setdefault("blobs_replaced", [])
        got = held.copy(bdir, root, digests, verify=True)
        for d in got["target_corrupt"]:
            if d not in rec["blobs_replaced"]:
                rec["blobs_replaced"].append(d)
                save()
            dst = held.path(os.path.join(q, REPLACED_BLOBS), d)
            dst.parent.mkdir(parents=True, exist_ok=True)
            _move(str(held.path(root, d)), _free_name(str(dst)))
        if got["target_corrupt"]:
            got = held.copy(bdir, root, digests, verify=True)
        bad = ([f"{d} is missing from the backup" for d in got["not_present"]]
               + [f"{d} in the backup does not hash to its name"
                  for d in got["source_corrupt"]]
               + [f"{d} in the Brain does not hash to its name"
                  for d in got["target_corrupt"]])
        if bad:
            raise RestoreFailed("stored files could not be restored "
                                "(nothing was deleted): " + "; ".join(bad[:10]))
    rec["steps"]["copied_in"] = True
    save()
    if pending:
        stop("after-copy-in")
    for name in pending:
        if name == DB:
            # NO SIDECAR beside the copy: SQLite would replay a foreign WAL
            for sc in SIDECARS:
                if os.path.lexists(os.path.join(root, sc)):
                    move_aside(sc, stray=True)
            left = [sc for sc in SIDECARS
                    if os.path.lexists(os.path.join(root, sc))]
            if left:
                raise RestoreFailed(f"{left} could not be moved aside; the "
                                    f"backup's corpus.db was not put in place")
        if name not in rec["placed"]:
            rec["placed"].append(name)
            save()
        dst = os.path.join(root, name)
        if os.path.lexists(dst):
            # POSIX rename would replace it silently; Windows would refuse
            raise RestoreFailed(f"something is already at {dst}; the "
                                f"backup's {name} was not put in place")
        os.rename(_tmp(root, qid, name), dst)
    _fsync_dir(root)
    rec["steps"]["renamed"] = True
    save()
    if pending:
        stop("after-rename")

    # (4) RECORD the restore in the restored Brain, through the chained
    # path. `_maintenance` skips the shared lock, and so the marker; the
    # caller holds the exclusive lock.
    s = store.Store(root, _maintenance=True)
    try:
        had = s.operational(act=RESTORED_ACT, detail_is={"restore_id": qid})
        if had:
            oid = had[0]["id"]
        else:
            oid = f"opr-{uuid.uuid4().hex[:12]}"
            s.append_operational({
                "id": oid, "at": _now(), "actor": migrations.ACTOR,
                "act": RESTORED_ACT,
                "because": f"restored from backup {rec['backup_id']}",
                "about": [],
                "detail": {"restore_id": qid, "backup_id": rec["backup_id"],
                           "backup": bdir, "quarantine": q,
                           "discarded": rec["discarded"],
                           "plan_digest": rec["plan_digest"],
                           "stored_files_replaced":
                               rec.get("blobs_replaced") or []}})
    finally:
        s.close()
    rec["steps"]["recorded"] = oid
    save()
    if not had:
        stop("after-record")

    # (5) VERIFY, mark complete, and only then lift the marker
    problems = _verify_restored(root, meta)
    if problems:
        raise RestoreFailed("the restored Brain did not verify (nothing was "
                            "deleted; `restore --resume <id> --reverse` puts "
                            "the quarantined Brain back): "
                            + "; ".join(problems))
    rec["steps"]["verified"] = True
    save()
    stop("before-complete")
    rec["complete"] = True
    rec["completed_at"] = _iso(_now())
    save()
    stop("after-complete")
    _unmark(root, qid)
    _unpin(bdir, qid)
    return {"restored": True, "restore_id": qid, "quarantine": q,
            "backup": bdir, "backup_id": rec["backup_id"], "operational": oid,
            "discarded": rec["discarded"], "plan_digest": rec["plan_digest"],
            "stored_files_replaced": rec.get("blobs_replaced") or []}


def _verify_restored(root: str, meta: dict) -> list[str]:
    problems = []
    conn = _connect(os.path.join(root, DB))
    try:
        ic = [r[0] for r in conn.execute("PRAGMA integrity_check")]
        if ic != ["ok"]:
            problems.append(f"integrity_check: {ic[:5]}")
        chain = _chain(conn)
        if chain is not None and not chain["intact"]:
            problems.append("hash chain broken")
        led = _ledger(conn)
        want = (meta.get("ledger") or {}).get("state")
        if led["state"] != want and led["state"] not in migrations.WRITABLE:
            problems.append(f"schema state {led['state']}, the backup's was "
                            f"{want}")
        for t in migrations.CHAINED_TABLES:
            b = meta["tables"][t]
            kept = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE seq <= ?",
                                (b["max_seq"],)).fetchone()[0]
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            extra = 1 if t == "operational" else 0
            if kept != b["count"] or n != b["count"] + extra:
                problems.append(f"{t}: {n} rows, expected {b['count'] + extra}")
            if b["max_seq"]:
                h = conn.execute(f"SELECT hash FROM {t} WHERE seq = ?",
                                 (b["max_seq"],)).fetchone()
                if (h[0] if h else None) != b["head"]:
                    problems.append(f"{t}: head at seq {b['max_seq']} is not "
                                    f"the backup's")
        referenced = _referenced(conn)
    finally:
        conn.close()
    # every stored file the restored record refers to, hashed in place
    bad = []
    for d in referenced:
        st, _ = held.state(root, d, verify=True)
        if st != "present":
            bad.append(f"{d} is {st}")
    if bad:
        problems.append("stored files the restored record refers to are not "
                        "intact: " + "; ".join(bad[:10])
                        + (f" (+{len(bad) - 10} more)" if len(bad) > 10
                           else ""))
    # the carried items: the backup's, exactly, and none it did not carry
    items = set(meta.get("items") or [])
    for name in AUX:
        here = os.path.lexists(os.path.join(root, name))
        if name not in items:
            if here:
                problems.append(f"{name} is in the Brain; the backup has none")
            continue
        if not here:
            problems.append(f"{name} is missing from the restored Brain")
            continue
        want = {k: v for k, v in (meta.get("files") or {}).items()
                if k == name or k.startswith(name + "/")}
        if _item_manifest(root, name) != want:
            problems.append(f"{name} does not match the backup's content")
    return problems


def _locate(root: str, qid: str) -> tuple[str, dict, bool]:
    """(quarantine path, its intent, whether it is still `.partial`). A
    `.partial` quarantine has had nothing moved into it: moving begins only
    once it has its name."""
    q = _qdir(root, qid)
    for where, partial in ((q, False), (q + PARTIAL, True)):
        rec = _read_json(os.path.join(where, INTENT))
        # an intent is this restore's only if it says so
        if rec is not None and rec.get("id") == qid and rec.get("backup"):
            return q, rec, partial
    if os.path.isdir(q + PARTIAL):
        raise BackupRefused(
            f"restore {qid} never started: its quarantine {q}{PARTIAL} "
            f"has no intent and nothing was moved. Remove it with "
            f"discard-quarantine {qid} --confirm {qid}")
    raise BackupRefused(f"no restore {qid} for {root} (no {INTENT} in {q})")


def _quarantines(root: str) -> list[tuple[str, dict | None, bool]]:
    """Every quarantine folder of this Brain: (path, intent, partial)."""
    parent, name = os.path.split(root)
    out = []
    try:
        names = sorted(os.listdir(parent))
    except OSError:
        return out
    for n in names:
        if n.startswith(f"{name}.quarantine-"):
            p = os.path.join(parent, n)
            out.append((p, _read_json(os.path.join(p, INTENT)),
                        n.endswith(PARTIAL)))
    return out


def _clear_unreadable(root: str) -> bool:
    """An UNREADABLE marker names no restore, so `_unmark` can never match
    it. It is removed only when every quarantine of this Brain is finished
    (complete or reversed) -- then no restore can be what it was guarding."""
    got = brainlock.restoring(root)
    if got is None or got.get("quarantine_id") is not None:
        return False
    for _, rec, partial in _quarantines(root):
        if partial or rec is None or not (rec.get("complete")
                                          or rec.get("reversed")):
            return False
    os.remove(os.path.join(root, brainlock.RESTORING))
    _fsync_dir(root)
    return True


def _nonstray(rec: dict, name: str) -> dict | None:
    """The move of an ORIGINAL item of this name, if one is recorded."""
    for e in rec.get("moved") or []:
        if e["name"] == name and not e.get("stray"):
            return e
    return None


def _original_heads(root: str, q: str, rec: dict) -> dict | None:
    """The original database's record as it stands now, wherever it is --
    read from a COPY of it and its own sidecars, so nothing of the original
    is opened, checkpointed or changed. None when there is no original."""
    e = _nonstray(rec, DB)
    src = {}
    if e and os.path.lexists(os.path.join(q, e["to"])):
        src[DB] = os.path.join(q, e["to"])
        here = False
    elif (os.path.lexists(os.path.join(root, DB))
          and DB not in (rec.get("placed") or [])):
        src[DB] = os.path.join(root, DB)
        here = True
    else:
        return None
    for sc in SIDECARS:
        if sc.endswith("-shm"):
            continue                    # rebuilt from the WAL by SQLite
        se = _nonstray(rec, sc)
        if se and os.path.lexists(os.path.join(q, se["to"])):
            src[sc] = os.path.join(q, se["to"])
        elif here and os.path.lexists(os.path.join(root, sc)):
            src[sc] = os.path.join(root, sc)
    tmp = os.path.join(q, f".check-{uuid.uuid4().hex[:8]}")
    os.makedirs(tmp)
    try:
        for name, p in src.items():
            shutil.copy2(p, os.path.join(tmp, name))
        conn = _connect(os.path.join(tmp, DB))
        try:
            return migrations._heads(conn)
        finally:
            conn.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def resume_restore(root: str, quarantine_id: str, reverse: bool = False, *,
                   _hook=None) -> dict:
    """Complete an interrupted restore, or with `reverse` put the quarantined
    Brain back. Idempotent. Exclusive lock, taken BEFORE the intent is read.
    Going forward is refused if anything was written to the Brain after the
    restore was planned; reversing never is."""
    root = os.path.abspath(root)
    lock = brainlock.exclusive(root, "restore", restoring_ok=True)
    try:
        q, rec, partial = _locate(root, quarantine_id)
        if rec.get("reversed") or rec.get("complete"):
            _unmark(root, rec["id"])        # killed between record and unmark
            _unpin(rec["backup"], rec["id"])
            cleared = _clear_unreadable(root)
            if rec.get("reversed"):
                return {"restore_id": rec["id"], "reversed": True,
                        "already": True, "quarantine": q,
                        "cleared_unreadable_marker": cleared}
            if reverse:
                raise BackupRefused(
                    f"restore {rec['id']} is complete; reversing it now would "
                    f"discard whatever was written since. Back up and restore "
                    f"from {q} deliberately instead")
            return {"restore_id": rec["id"], "restored": True,
                    "already": True, "quarantine": q,
                    "operational": rec["steps"].get("recorded"),
                    "cleared_unreadable_marker": cleared}
        marker = brainlock.restoring(root)
        if marker is not None and marker.get("quarantine_id") not in (
                None, rec["id"]):
            raise BackupRefused(
                f"the Brain is marked as being restored by "
                f"{marker.get('quarantine_id')}, not {rec['id']}")
        took_over = marker is not None and marker.get("quarantine_id") is None
        if marker is None or took_over:
            _mark(root, rec)                # killed before the marker
        if partial:
            # killed before the quarantine got its name: nothing was moved
            os.rename(q + PARTIAL, q)
            _fsync_dir(os.path.dirname(q))
        rec.setdefault("moved", [])
        rec.setdefault("placed", [])
        if reverse:
            out = _reverse(root, q, rec, _hook)
        else:
            back = (f"Reverse it (`restore <brain> --resume {rec['id']} "
                    f"--reverse`) and plan again")
            if rec.get("reversal") is not None:
                # ONE DIRECTION ONCE CHOSEN: a reverse that began has swept
                # what the restore brought in and may have put originals back
                raise BackupRefused(
                    f"a reverse of restore {rec['id']} has begun; it can only "
                    f"be finished (`restore <brain> --resume {rec['id']} "
                    f"--reverse`), then planned again")
            meta = _meta(rec["backup"])
            check = verify_backup(rec["backup"], brain=root)
            if meta.get("id") != rec.get("backup_id") or not check["usable"]:
                raise RestoreFailed(
                    f"the backup {rec['backup']} no longer verifies as the "
                    f"one restore {rec['id']} was planned from: "
                    + ("; ".join(check["problems"]) or "a different backup")
                    + ". " + back)
            if not rec["moved"] and not rec["steps"].get("moved"):
                # NOTHING MOVED YET, so nothing has stood guard over the Brain
                # since the plan (killed before the marker): the WHOLE plan
                # -- scratch, instances/, marker, presentation/ included --
                # must still be the one confirmed
                plan = _compute_plan(root, rec["backup"], meta,
                                     ignore=rec["id"])
                if plan["digest"] != rec.get("plan_digest"):
                    raise RestoreFailed(
                        f"the Brain changed after restore {rec['id']} was "
                        f"planned (while it was interrupted?): going forward "
                        f"would set aside what nobody confirmed. " + back)
            elif "live" in rec:
                now = _original_heads(root, q, rec)
                if now != rec["live"]:
                    raise RestoreFailed(
                        f"the Brain's record changed after restore "
                        f"{rec['id']} was planned (written while it was "
                        f"interrupted?): going forward would set those rows "
                        f"aside uncounted. " + back)
            out = {**_drive(root, q, rec, meta, _hook), "resumed": True}
        if took_over:
            out["replaced_unreadable_marker"] = True
        return out
    finally:
        lock.release()


def _reverse(root: str, q: str, rec: dict, hook=None) -> dict:
    """Put the original Brain back. Idempotent at every step: progress is in
    RESTORE.json, the sweep of what the restore brought in runs to the end
    before anything is put back, and nothing recorded as an ORIGINAL is ever
    swept."""
    stop = hook or (lambda label: None)
    intent = os.path.join(q, INTENT)
    aborted = os.path.join(q, ABORTED)
    os.makedirs(aborted, exist_ok=True)
    rv = rec.get("reversal") or {}
    for k in ("moved_to_aborted", "put_back", "blobs_moved"):
        rv.setdefault(k, [])
    rv.setdefault("cleared", False)
    rec["reversal"] = rv

    def save():
        _write_json(intent, rec)

    def original_here(name: str) -> bool:
        """Whether `<root>/<name>` is an item of the ORIGINAL Brain."""
        if not os.path.lexists(os.path.join(root, name)):
            return False
        e = _nonstray(rec, name)
        if e is not None:
            # moved, unless the move was recorded and never made
            return not os.path.lexists(os.path.join(q, e["to"]))
        if name in SIDECARS:
            # never moved: its own only if the original database never left
            return original_here(DB)
        return name not in rec["placed"]

    def replaced(d: str) -> str:
        """Where the Brain's own copy of a replaced stored file waits."""
        return str(held.path(os.path.join(q, REPLACED_BLOBS), d))

    # (A) SWEEP what the restore brought in into aborted-restore/
    if not rv["cleared"]:
        for name in PLACE_ORDER + SIDECARS:
            if (os.path.lexists(os.path.join(root, name))
                    and not original_here(name)):
                _move(os.path.join(root, name),
                      _free_name(os.path.join(aborted, name)))
                rv["moved_to_aborted"].append(name)
                save()
                stop(f"reverse-after-out:{name}")
        for d in rec.get("blobs_added") or []:
            p = held.path(root, d)
            if p.is_file():
                dst = held.path(aborted, d)
                dst.parent.mkdir(parents=True, exist_ok=True)
                _move(str(p), _free_name(str(dst)))
                rv["blobs_moved"].append(d)
        for d in rec.get("blobs_replaced") or []:
            # the backup's copy goes, while the Brain's own is still aside
            p = held.path(root, d)
            if p.is_file() and os.path.lexists(replaced(d)):
                dst = held.path(aborted, d)
                dst.parent.mkdir(parents=True, exist_ok=True)
                _move(str(p), _free_name(str(dst)))
                rv["blobs_moved"].append(d)
        rv["cleared"] = True
        save()
        stop("reverse-cleared")
    # the restore's temp names are never originals: swept on every run
    prefix = f".restore-{rec['id']}-"
    for n in sorted(os.listdir(root)):
        if n.startswith(prefix):
            _move(os.path.join(root, n), _free_name(os.path.join(aborted, n)))
            rv["moved_to_aborted"].append(n)
            save()

    # (B) PUT BACK exactly the originals that were moved: the database
    # first, its own sidecars after it, then the carried items. A stray
    # sidecar (arrived after the original database had left) stays in the
    # quarantine: beside the database, SQLite would replay it.
    for name in (DB,) + SIDECARS + AUX:
        e = _nonstray(rec, name)
        if e is None:
            continue
        src, dst = os.path.join(q, e["to"]), os.path.join(root, name)
        if not os.path.lexists(src):
            continue                        # already back (or never left)
        if os.path.lexists(dst):
            raise RestoreFailed(f"cannot put {name} back: something is "
                                f"already at {dst}; it is in {q}")
        _move(src, dst)
        rv["put_back"].append(name)
        save()
        stop(f"reverse-after-back:{name}")
    # the Brain's own stored files a portable restore set aside, exactly as
    # they were: putting the original Brain back repairs nothing
    for d in rec.get("blobs_replaced") or []:
        src, dst = replaced(d), held.path(root, d)
        if not os.path.lexists(src):
            continue
        if dst.exists():
            raise RestoreFailed(f"cannot put stored file {d} back: one is "
                                f"already at {dst}; the Brain's own is in {q}")
        _move(src, str(dst))
        rv["put_back"].append(f"stored file {d}")
        save()
    missing = [e["name"] for e in rec["moved"] if not e.get("stray")
               and not os.path.lexists(os.path.join(root, e["name"]))]
    if missing:
        raise RestoreFailed(f"could not put back {missing}; they are in {q}")
    rv["strays_kept_in_quarantine"] = [e["to"] for e in rec["moved"]
                                       if e.get("stray")]
    rec["reversed"] = True
    rec["reversed_at"] = _iso(_now())
    save()
    stop("reverse-before-unmark")
    _unmark(root, rec["id"])
    _unpin(rec["backup"], rec["id"])
    return {"restore_id": rec["id"], "reversed": True, "quarantine": q,
            **{k: v for k, v in rv.items() if k != "cleared"}}


def discard_quarantine(root: str, quarantine_id: str,
                       confirm: str | None = None) -> dict:
    """The ONLY way a quarantine folder is removed: typed, confirmed with its
    id, and only once its restore is finished -- or, for one that never got
    its name (`.partial`, nothing moved into it), while it holds nothing but
    the intent; its marker, if it got one, goes with it."""
    root = os.path.abspath(root)
    if confirm != quarantine_id:
        raise BackupRefused(f"discarding quarantine {quarantine_id} needs "
                            f"--confirm {quarantine_id}")
    lock = brainlock.exclusive(root, "discard-quarantine", restoring_ok=True)
    try:
        cleared = _clear_unreadable(root)
        marker = brainlock.restoring(root)
        q = _qdir(root, quarantine_id)
        if not os.path.isdir(q) and os.path.isdir(q + PARTIAL):
            extra = [n for n in os.listdir(q + PARTIAL)
                     if n != INTENT and not n.startswith(INTENT + ".tmp-")]
            if extra:
                raise BackupRefused(f"{q}{PARTIAL} holds {extra}; it is not "
                                    f"an empty or intent-only quarantine")
            shutil.rmtree(q + PARTIAL)
            unmarked = (marker is not None
                        and marker.get("quarantine_id") == quarantine_id)
            if unmarked:
                _unmark(root, quarantine_id)
            return {"discarded": q + PARTIAL, "restore_id": quarantine_id,
                    "marker_removed": unmarked,
                    "cleared_unreadable_marker": cleared}
        if marker is not None and marker.get("quarantine_id") in (
                quarantine_id, None):
            raise BackupRefused(
                f"the Brain is still marked as being restored "
                f"({marker.get('quarantine_id')}); resume or reverse it first")
        q, rec, _ = _locate(root, quarantine_id)
        if not (rec.get("complete") or rec.get("reversed")):
            raise BackupRefused(f"restore {quarantine_id} is unfinished; "
                                f"resume or reverse it before discarding its "
                                f"quarantine")
        shutil.rmtree(q)
    finally:
        lock.release()
    return {"discarded": q, "restore_id": quarantine_id,
            "cleared_unreadable_marker": cleared}


# -- retention (R1) --------------------------------------------------------------

def _live_corpus_id(root: str) -> str:
    path = os.path.join(root, DB)
    if not os.path.isfile(path):
        raise migrations.BrainMissing(f"no Brain at {root}")
    conn = _connect(path)
    try:
        cid = _corpus_id(conn)
    finally:
        conn.close()
    if not cid:
        raise BackupRefused(f"the Brain at {root} has no corpus identity")
    return cid


def _breaking_versions(root: str) -> list[int]:
    """The to_version of every breaking row in the Brain's ledger."""
    conn = _connect(os.path.join(root, DB))
    try:
        if "schema_migration" not in migrations._tables(conn):
            return []
        return [r[0] for r in conn.execute(
            "SELECT to_version FROM schema_migration WHERE kind = 'breaking' "
            "ORDER BY seq")]
    finally:
        conn.close()


def _held_shared(root: str):
    """The OPEN lock, shared, for reading the live Brain beside the backups:
    refused during an interrupted restore and while migrate/reconcile/
    restore runs, so nothing is judged against a Brain in mid-change."""
    if not os.path.isfile(os.path.join(root, DB)):
        raise migrations.BrainMissing(f"no Brain at {root}")
    return brainlock.shared(root)


def list_backups(root: str) -> dict:
    """Every backup in this Brain's default backups folder, oldest first."""
    root = os.path.abspath(root)
    lock = _held_shared(root)
    try:
        return _list(root)
    finally:
        lock.release()


def _list(root: str) -> dict:
    where = _default_dir(root, _live_corpus_id(root))
    out = []
    try:
        names = sorted(os.listdir(where))
    except FileNotFoundError:
        names = []
    for n in names:
        p = os.path.join(where, n)
        if not os.path.isdir(p):
            continue
        meta = _read_json(os.path.join(p, MANIFEST)) or {}
        check = verify_backup(p, brain=root)
        try:
            created = float(meta.get("created_at"))
        except (TypeError, ValueError):
            created = os.stat(p).st_mtime
        out.append({
            "name": n, "path": p, "id": meta.get("id"),
            "kind": meta.get("kind"), "created_at": created,
            "created_at_utc": _iso(created),
            "complete": not n.endswith(PARTIAL) and bool(meta),
            "usable": check["usable"], "intact": check["intact"],
            "problems": check["problems"],
            "live_store_problems": check["live_store_problems"],
            "restores_using_it": _pinned(p),
            "ledger_version": (meta.get("ledger") or {}).get("version"),
            "released": os.path.isfile(os.path.join(p, RELEASED)),
        })
    out.sort(key=lambda b: (b["created_at"], b["name"]))
    return {"brain": root, "backups_dir": where, "backups": out}


def _retention(root: str, listing: dict, now: float) -> list[dict]:
    """Why each backup is kept. R1's rules protect USABLE backups, and the
    same counts protect RECOVERY POINTS: backups that are themselves intact,
    usable or not. A backup the live store has made unusable (a stored file
    it refers to is missing or corrupt THERE) is protected outright for as
    long as that lasts -- the damage is the live store's, and may be
    repaired -- so a damaged store never turns a recovery point into
    something prune may remove. One that refers to a stored file the live
    record has since purged is not intact, and so not a recovery point: a
    purge is never repaired."""
    backups = listing["backups"]
    newest_first = sorted(backups, key=lambda b: b["created_at"], reverse=True)
    usable = [b for b in newest_first if b["usable"]]
    points = [b for b in newest_first if b["intact"]]
    why = {b["path"]: [] for b in backups}
    for group, noun in ((usable, "usable backup"), (points, "recovery point")):
        if group:
            why[group[0]["path"]].append(f"newest {noun}")
        for b in group[:KEEP_NEWEST]:
            why[b["path"]].append(f"one of the newest {KEEP_NEWEST} {noun}s")
    named = [u["backup"] for u in _unfinished(root) if u.get("backup")]
    for b in backups:
        if any(_same_path(b["path"], n) for n in named):
            why[b["path"]].append("named by an unfinished restore")
        if b.get("restores_using_it"):
            why[b["path"]].append(
                "used by an unfinished restore: "
                + ", ".join(b["restores_using_it"]))
        if b["created_at"] > now - KEEP_DAYS * 86400:
            why[b["path"]].append(f"younger than {KEEP_DAYS} days")
        if b["intact"] and not b["usable"]:
            why[b["path"]].append(
                "a recovery point unusable only because of the live store "
                "(repair it first): "
                + "; ".join(b["live_store_problems"])[:300])
    for v in _breaking_versions(root):
        for group, noun in ((usable, "usable backup"),
                            (points, "recovery point")):
            before = [b for b in group if (b["ledger_version"] or 0) < v]
            if before and not before[0]["released"]:
                why[before[0]["path"]].append(
                    f"last {noun} before the breaking migration to "
                    f"version {v} (until the owner releases it)")
    return [{**b, "protected_by": why[b["path"]]} for b in backups]


def prune(root: str, confirm: bool = False, now: float | None = None, *,
          allow_no_backups: bool = False) -> dict:
    """Remove backups no retention rule protects. A dry run unless
    `confirm`. Never touches a quarantine folder.

    NEVER DOWN TO NONE BY ACCIDENT. After a purge every older backup may be
    unprotected (not intact, so not a recovery point), and removing them
    all leaves the Brain with no other copy of its record. The dry run warns;
    `confirm` refuses unless `allow_no_backups` is given as well."""
    root = os.path.abspath(root)
    now = _now() if now is None else now
    lock = _held_shared(root)
    warning = None
    try:
        rows = _retention(root, _list(root), now)
        remove = [b["path"] for b in rows if not b["protected_by"]]
        if (any(b["intact"] for b in rows)
                and not any(b["intact"] for b in rows
                            if b["path"] not in remove)):
            # cannot happen under the rules above; never allowed if it does
            raise BackupRefused("prune would leave this Brain with no "
                                "recovery point; nothing was removed")
        # only COMPLETE backups count: a stale `.partial` is no copy to lose
        gone = [b for b in rows if b["path"] in remove and b["complete"]]
        left = [b for b in rows if b["path"] not in remove and b["complete"]]
        if gone and not left:
            warning = (
                f"prune would remove all {len(gone)} of this Brain's "
                f"backups and leave it with none: no other copy of its "
                f"record would remain. Take a fresh backup first "
                f"(`python -m mentis.brain backup \"{root}\"`)")
            if confirm and not allow_no_backups:
                raise BackupRefused(
                    warning + ", or confirm with --allow-no-backups; nothing "
                    "was removed")
        if confirm:
            for p in remove:
                shutil.rmtree(p)
    finally:
        lock.release()
    out = {"brain": root, "dry_run": not confirm,
           ("removed" if confirm else "would_remove"): remove,
           "keep": [{"path": b["path"], "id": b["id"],
                     "protected_by": b["protected_by"]}
                    for b in rows if b["protected_by"]]}
    if warning:
        out["warning"] = warning
        out["leaves_no_backups"] = True
    return out


def release(root: str, backup_id: str, confirm: str | None = None) -> dict:
    """The owner releasing a protected pre-breaking backup: a marker in it."""
    root = os.path.abspath(root)
    if confirm != backup_id:
        raise BackupRefused(f"releasing {backup_id} needs --confirm {backup_id}")
    for b in list_backups(root)["backups"]:
        if b["id"] == backup_id:
            p = os.path.join(b["path"], RELEASED)
            _write_json(p, {"backup_id": backup_id, "released_at": _iso(_now()),
                            "by": "owner"})
            return {"released": backup_id, "path": b["path"]}
    raise BackupRefused(f"no backup {backup_id} for the Brain at {root}")
