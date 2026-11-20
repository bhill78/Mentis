"""`GET /api/brain/overview`: what this Brain holds and what it takes to move.

READ ONLY. Nothing here writes to the Brain, its folder or anything beside
it; the only thing kept is in this process's memory (two caches, below).

TWO SORTS OF NUMBER, NEVER MIXED.

  counts    LOGICAL: how many things the record holds -- conversations,
            posts, records by Kind and by the Ladder's status, files and the
            references that name them, connected sources.
  storage   PHYSICAL: bytes on this machine's disk -- the database's files,
            the stored files, whatever else is in the Brain's folder.

EVERY NUMBER IS READ, NOT ESTIMATED FROM ANOTHER, and where one could not be
read it is None with the reason beside it -- never 0 standing in for unknown.

WHERE EACH COMES FROM, and what it costs:

  conversations, posts   `conversation_summaries`, the conversation list's own
                         read model (kept until an entry is written).
  records                `mentis.web.ladder.tally`: the rule the Brain
                         browser lists by. The costly part (one status per
                         record), so it is kept here until the record moves
                         (`advance`, and the erasure mark).
  files                  ONE GROUPED SQL STATEMENT over the Admissions
                         (`Corpus.held_file_tally`), with the sizes written
                         when the bytes crossed. A file named by two
                         references is one file: its bytes are counted once.
  database               the sizes of `corpus.db`, `-wal` and `-shm`, and the
                         page count a backup of it would write.
  the store on disk      one directory walk of `artifacts/`, sizes from the
                         directory entries; no file is opened or hashed. Kept
                         for `STORE_KEPT_S` and said with the time it was
                         measured; `?measure=1` measures again.

THE PORTABLE FOOTPRINT is what `python -m mentis.brain backup --portable`
would write (`mentis.spine.backup`, read for this and not re-implemented): the
database as one file, `instances/`, `mentis-corpus.json`, `presentation/`,
and every stored file at its own name except those only purged references
name. It is an estimate because nothing is hashed here (a file that no longer
hashes to its name is left behind by a real backup) and the backup's own
manifest is not counted. What it leaves out is listed with it.
"""

from __future__ import annotations

import os
import threading
import time

from mentis.spine import backup as _backup
from mentis.spine import held as _held

#: how long a measurement of the store on disk is answered again without
#: walking it (`?measure=1` walks at once)
STORE_KEPT_S = 600.0

#: the Ladder's statuses of a record that is current, in the order said
CURRENT = ("adopted", "adoption_requested", "recorded", "declined")
PAST = ("superseded", "deleted")

_lock = threading.Lock()
#: Brain folder -> (measured at, the measurement)
_store_kept: dict = {}
#: Brain folder -> (what the record had got to, the tally)
_tally_kept: dict = {}


def _size(path: str) -> int | None:
    try:
        return os.stat(path).st_size
    except OSError:
        return None


def _tree(path: str) -> tuple[int, int]:
    """(files, bytes) under a file or folder, by what a backup would copy:
    lock files, `-wal`/`-shm` and caches are skipped, as `backup._skip`."""
    if os.path.isfile(path):
        return 1, _size(path) or 0
    files = size = 0
    stack = [path]
    while stack:
        try:
            entries = list(os.scandir(stack.pop()))
        except OSError:
            continue
        for e in entries:
            if _backup._skip(e.name):
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
                elif e.is_file(follow_symlinks=False):
                    files += 1
                    size += e.stat(follow_symlinks=False).st_size
            except OSError:
                continue
    return files, size


def _walk_store(root: str) -> dict:
    """Every file under `artifacts/`: `{digest: bytes}` for those at their
    own name, and (count, bytes) of whatever else is there (a write that
    never finished, a file not at the name of its content)."""
    top = os.path.join(root, str(_held.STORE.parent))
    at_name: dict = {}
    other = other_bytes = 0
    stack = [top] if os.path.isdir(top) else []
    while stack:
        here = stack.pop()
        try:
            entries = list(os.scandir(here))
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
                    continue
                if not e.is_file(follow_symlinks=False):
                    continue
                size = e.stat(follow_symlinks=False).st_size
            except OSError:
                continue
            if _held.is_digest(e.name) and os.path.normcase(e.path) == \
                    os.path.normcase(str(_held.path(root, e.name))):
                at_name[e.name] = size
            else:
                other += 1
                other_bytes += size
    return {"at_name": at_name, "other": other, "other_bytes": other_bytes}


def _store(root: str, *, measure: bool) -> tuple[float, dict]:
    now = time.time()
    with _lock:
        kept = _store_kept.get(root)
    if kept is not None and not measure and now - kept[0] < STORE_KEPT_S:
        return kept
    got = (now, _walk_store(root))
    with _lock:
        _store_kept[root] = got
    return got


def _tally(st) -> dict:
    """`ladder.tally`, kept until the record moves."""
    from mentis.web import ladder
    corpus = st.corpus
    entries, acts, _ = corpus.advance()
    key = (entries, acts, corpus._store.erased_mark())
    with _lock:
        kept = _tally_kept.get(corpus.root)
    if kept is not None and kept[0] == key:
        return kept[1]
    got = ladder.tally(corpus)
    if not corpus.uncommitted and corpus.advance()[:2] == key[:2]:
        with _lock:
            _tally_kept[corpus.root] = (key, got)
    return got


def _records(tally: dict, governs: bool) -> dict:
    kinds, standing, past = [], dict.fromkeys(CURRENT, 0), 0
    for kind in sorted(tally):
        row = tally[kind]
        if row["governs"] is not governs:
            continue
        now = sum(n for s, n in row["statuses"].items() if s not in PAST)
        past += sum(n for s, n in row["statuses"].items() if s in PAST)
        for s, n in row["statuses"].items():
            if s not in PAST:
                standing[s] = standing.get(s, 0) + n
        if now:
            kinds.append({"kind": kind, "count": now})
    return {"total": sum(k["count"] for k in kinds), "kinds": kinds,
            "standing": [{"status": s, "count": n}
                         for s, n in standing.items()],
            "past": past}


def _conversations(cv) -> dict:
    rows = cv.conversation_summaries(cv.active_executions())
    states = cv.conversation_states()
    gone = {c for c, v in states.items() if v["state"] == "deleted"}
    rows = [r for r in rows if r.get("id") not in gone]
    by_state = {}
    for r in rows:
        s = (states.get(r["id"]) or {}).get("state")
        if s:
            by_state[s] = by_state.get(s, 0) + 1
    return {"total": len(rows),
            "archived": by_state.get("archived", 0),
            "trash": by_state.get("trashed", 0),
            "posts": sum(int(r.get("turns") or 0) for r in rows)}


def _sources(corpus) -> dict:
    """The connected sources: declared collections, each living outside the
    Brain. Whether one is bound on this machine is this machine's fact (the
    path is never said, here or anywhere)."""
    from mentis import api
    from mentis.sources import declarations
    try:
        src = api.sources(corpus)
        labels = {d["id"]: d["label"] for d in src.descriptors()}
    except Exception:                                       # noqa: BLE001
        src, labels = None, {}
    out = []
    for d in declarations(corpus):
        bound = None
        if src is not None:
            try:
                bound = bool(src.binding_state(d["collection"]).get("bound"))
            except Exception:                               # noqa: BLE001
                bound = None
        out.append({"collection": d["collection"],
                    "name": d.get("name") or None,
                    "connector": d["connector"],
                    "connector_label": labels.get(d["connector"])
                    or d["connector"],
                    "bound": bound})
    return {"total": len(out),
            "bound": sum(1 for c in out if c["bound"]),
            "collections": out, "connectors": sorted(labels)}


#: how a stored file came to be held, by its Admission's source
_GROUPS = {"submission": "attached", "execution": "returned"}


def _files(corpus, connectors) -> tuple[dict, dict]:
    """(what the record names, {digest: recorded size} of what is not
    purged) from one grouped read."""
    rows = corpus.held_file_tally()
    live: dict = {}          # digest -> recorded size (None: none recorded)
    purged_only: set = set()
    seen: dict = {}          # digest -> any reference that is not purged
    references = purged_refs = 0
    origins: dict = {}
    for origin, locator, size, refs, purged in rows:
        digest = _held.digest_of(locator)
        if digest is None:
            continue
        refs, purged = int(refs or 0), int(purged or 0)
        references += refs
        purged_refs += purged
        alive = refs > purged
        seen[digest] = seen.get(digest, False) or alive
        if alive:
            if isinstance(size, (int, float)):
                live[digest] = max(int(size), live.get(digest) or 0)
            else:
                live.setdefault(digest, None)
            group = _GROUPS.get(origin) or (
                "source" if origin in connectors else "other")
            o = origins.setdefault((group, origin), {
                "group": group, "origin": origin, "references": 0,
                "files": {}})
            o["references"] += refs - purged
            o["files"][digest] = int(size) if isinstance(
                size, (int, float)) else None
    purged_only = {d for d, alive in seen.items() if not alive}
    sized = [v for v in live.values() if v is not None]
    return ({"unique": len(live), "references": references - purged_refs,
             "purged_references": purged_refs,
             "purged_files": len(purged_only),
             "recorded_bytes": sum(sized),
             "unsized": len(live) - len(sized),
             "origins": sorted(
                 ({"group": o["group"], "origin": o["origin"],
                   "references": o["references"], "unique": len(o["files"]),
                   "bytes": sum(v for v in o["files"].values()
                                if v is not None)}
                  for o in origins.values()),
                 key=lambda o: (-o["bytes"], o["origin"]))},
            {"live": live, "purged_only": purged_only})


def overview(st, *, measure: bool = False) -> dict:
    """The whole answer. See the module's own words for what each part is."""
    from mentis.web import _named
    corpus, cv = st.corpus, st.cv
    root = corpus.root
    now = time.time()

    sources = _sources(corpus)
    files, named = _files(corpus, set(sources.pop("connectors")))
    tally = _tally(st)
    conversations = _conversations(cv)
    posts = conversations.pop("posts")

    # -- PHYSICAL: the database -------------------------------------------
    db_files = []
    for name in (_backup.DB,) + tuple(
            s for s in _backup.SIDECARS if not s.endswith("-journal")):
        size = _size(os.path.join(root, name))
        if size is not None:
            db_files.append({"name": name, "bytes": size})
    try:
        pages, page_size = corpus.database_pages()
        copy_bytes = pages * page_size
    except Exception:                                       # noqa: BLE001
        copy_bytes = None

    # -- PHYSICAL: the stored files, as the disk has them ------------------
    measured_at, walk = _store(root, measure=measure)
    on_disk = walk["at_name"]
    live, purged_only = named["live"], named["purged_only"]
    # NAMED SINCE THE STORE WAS MEASURED: a file that arrived after a kept
    # measurement is looked for by its own name (one stat each), so it is
    # never said to be missing because the measurement is older than it is
    for d in live:
        if d not in on_disk:
            size = _size(str(_held.path(root, d)))
            if size is not None:
                on_disk[d] = size
    missing = [d for d in live if d not in on_disk]
    unnamed = [d for d in on_disk if d not in live and d not in purged_only]
    purged_here = [d for d in on_disk if d in purged_only]
    carried = [d for d in on_disk if d not in purged_only]
    carried_bytes = sum(on_disk[d] for d in carried)

    # -- PHYSICAL: whatever else is in the Brain's folder ------------------
    kept, kept_bytes, other = [], 0, []
    try:
        top = sorted(os.listdir(root))
    except OSError:
        top = []
    skip = {_backup.DB, str(_held.STORE.parent)} | set(_backup.SIDECARS)
    for name in top:
        if name in skip or _backup._skip(name):
            continue
        n, size = _tree(os.path.join(root, name))
        row = {"name": name, "files": n, "bytes": size,
               "portable": name in _backup.AUX}
        if row["portable"]:
            kept.append(row)
            kept_bytes += size
        else:
            other.append(row)

    portable = None if copy_bytes is None else \
        copy_bytes + carried_bytes + kept_bytes
    return {
        "brain": {"id": corpus.corpus_id, **_named(root)},
        "read_at": now,
        # LOGICAL: how many things
        "counts": {
            "conversations": conversations,
            "posts": posts,
            "knowledge": _records(tally, False),
            "governing": _records(tally, True),
            "files": files,
            "sources": sources,
        },
        # PHYSICAL: bytes on this machine's disk
        "storage": {
            "database": {
                "bytes": sum(f["bytes"] for f in db_files),
                "files": db_files,
                # what a backup of it writes: one file, no -wal beside it
                "copy_bytes": copy_bytes},
            "files": {
                "measured_at": measured_at,
                "kept_for_s": STORE_KEPT_S,
                "on_disk": len(on_disk),
                "bytes": sum(on_disk.values()),
                # named by the record and not there: a copy made without
                # the stored files reads every one of them as missing
                "missing": len(missing),
                "missing_bytes": sum(live[d] or 0 for d in missing),
                # there, and named by nothing in the record
                "unnamed": len(unnamed),
                "unnamed_bytes": sum(on_disk[d] for d in unnamed),
                # there, though every reference to them was purged
                "purged_present": len(purged_here),
                "purged_present_bytes": sum(on_disk[d] for d in purged_here),
                # not at the name of their content, or a write never finished
                "stray": walk["other"],
                "stray_bytes": walk["other_bytes"]},
            "kept": kept,
            "other": other,
        },
        "portable": {
            "bytes": portable,
            "why_not": None if portable is not None
            else "the database's size could not be read",
            "as": "python -m mentis.brain backup --portable",
            "parts": [
                {"part": "database", "bytes": copy_bytes},
                {"part": "files", "bytes": carried_bytes,
                 "count": len(carried)},
                {"part": "kept", "bytes": kept_bytes,
                 "names": [k["name"] for k in kept]}],
            "left_out": {
                "sources": sources["total"],
                "purged_files": len(purged_here),
                "purged_bytes": sum(on_disk[d] for d in purged_here),
                "missing_files": len(missing),
                "stray_files": walk["other"],
                "stray_bytes": walk["other_bytes"],
                "other": other,
                "other_bytes": sum(o["bytes"] for o in other),
                "sidecar_bytes": sum(f["bytes"] for f in db_files
                                     if f["name"] != _backup.DB)},
        },
    }


def routes(st, path, query, method):
    """None when the path is not this module's."""
    if path != "/api/brain/overview":
        return None
    if method != "GET":
        return {"error": "the Brain overview is read with GET; it writes "
                         "nothing"}
    return overview(st, measure=(query.get("measure") or [""])[0] == "1")
