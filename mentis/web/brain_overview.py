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
  database               the sizes of `corpus.db`, `-wal` and `-shm` (three
                         stats, each request), and the page count a backup
                         of it would write.
  the folder on disk     ONE MEASUREMENT of everything else in the Brain's
                         folder: `artifacts/` and every other top-level item,
                         sizes from the directory entries; no file is opened
                         or hashed. Kept for `STORE_KEPT_S` and said with the
                         time it was made; `?measure=1` measures again. A
                         kept measurement is NEVER CHANGED: a later request
                         reads it, and looks for files the record has named
                         since by their own names, for that answer only. ONE
                         MEASUREMENT RUNS AT A TIME per Brain: whoever asks
                         while one is running is given that one's result.

WHAT COULD NOT BE READ IS NOT COUNTED AS NOTHING. A folder that could not be
listed, or a file whose size could not be read, makes the part it belongs to
"not measured" with the reason (`bytes: null`, `why_not`), and so the
portable estimate too where that part is carried. No partial total is given
as a total.

NAMES. The answer names the database's three files and, for the rest of the
folder, only what Mentis itself puts there, by what it is (`what`); anything
else is one aggregate, counted and sized, never listed by name.

THE PORTABLE FOOTPRINT is what `python -m mentis.brain backup --portable`
would write (`mentis.spine.backup`, read for this and not re-implemented): the
database as one file, `instances/`, `mentis-corpus.json`, `presentation/`,
and every stored file at its own name except those only purged references
name. It is an estimate because nothing is hashed here (a file that no longer
hashes to its name is left behind by a real backup) and the backup's own
manifest (`BACKUP.json`) is not counted. What it leaves out is listed with it.
"""

from __future__ import annotations

import collections
import concurrent.futures
import errno
import os
import sqlite3
import stat as _stat
import threading
import time
import types

from mentis.spine import backup as _backup
from mentis.spine import held as _held

#: how long a measurement of the store on disk is answered again without
#: walking it (`?measure=1` walks at once)
STORE_KEPT_S = 600.0

#: the Ladder's statuses of a record that is current, in the order said
CURRENT = ("adopted", "adoption_requested", "recorded", "declined")
PAST = ("superseded", "deleted")

_lock = threading.Lock()
#: Brain folder -> the kept measurement of its folder (never changed once kept)
_measured: dict = {}
#: Brain folder -> the measurement running now (a Future of one)
_measuring: dict = {}
#: Brain folder -> (what the record had got to, the tally)
_tally_kept: dict = {}

#: what Mentis itself puts in a Brain's folder besides the database and the
#: stored files, by what it is. Anything else there is counted together.
_KNOWN = {"instances": "runtime-notes", "mentis-corpus.json": "identity",
          "presentation": "presentation", "derived": "derived",
          "mcp-policy.json": "agent-policy"}


def _stat_size(path: str) -> int:
    return os.stat(path).st_size


def _entries(path: str) -> list:
    with os.scandir(path) as it:
        return list(it)


#: THE ONLY REASONS THIS MODULE EVER GIVES for a failed read. Its own words,
#: chosen by what kind of failure it was; nothing an exception said.
DENIED = "access was denied"
NOT_FOUND = "it was not found"
IN_USE = "it is in use by another program"
IO_ERROR = "the disk reported a read error"
DATABASE = "the database could not be read"
NOT_A_FOLDER = "it is not a folder"
UNREADABLE = "it could not be read"
REASONS = (DENIED, NOT_FOUND, IN_USE, IO_ERROR, DATABASE, NOT_A_FOLDER,
           UNREADABLE)

_ERRNO = {errno.EACCES: DENIED, errno.EPERM: DENIED, errno.ENOENT: NOT_FOUND,
          errno.EBUSY: IN_USE, errno.ETXTBSY: IN_USE, errno.EIO: IO_ERROR,
          errno.ENOTDIR: NOT_A_FOLDER}
#: Windows' own codes for a file another program holds open or has locked
_WINERROR = {32: IN_USE, 33: IN_USE, 5: DENIED, 2: NOT_FOUND, 3: NOT_FOUND}


def _why(exc: BaseException) -> str:
    """WHY SOMETHING COULD NOT BE READ, AND NEVER WHERE. The one function
    every reason in the answer goes through, and it returns one of `REASONS`
    and nothing else: NO TEXT AN EXCEPTION CARRIES IS EVER PASSED ON -- not
    its message, not the system's `strerror` -- because either can hold a
    path, a file's name or something else about this machine. The kind of
    failure is read from the exception's class and its error number."""
    if isinstance(exc, sqlite3.Error):
        return DATABASE
    if isinstance(exc, PermissionError):
        return _WINERROR.get(getattr(exc, "winerror", None), DENIED) \
            if getattr(exc, "winerror", None) in (32, 33) else DENIED
    if isinstance(exc, FileNotFoundError):
        return NOT_FOUND
    if isinstance(exc, NotADirectoryError):
        return NOT_A_FOLDER
    if isinstance(exc, OSError):
        return (_WINERROR.get(getattr(exc, "winerror", None))
                or _ERRNO.get(exc.errno) or UNREADABLE)
    return UNREADABLE


def _tree(path: str) -> tuple[int, int, str | None]:
    """(files, bytes, why not) under a file or folder, by what a backup would
    copy: lock files, `-wal`/`-shm` and caches are skipped, as
    `backup._skip`. Anything that could not be read is the third answer,
    and the first two are then not a total."""
    try:
        # asked of the disk directly: `os.path.isfile` answers False for a
        # stat that FAILED, which would read as "a folder" and then "empty"
        st = os.stat(path)
    except OSError as exc:
        return 0, 0, _why(exc)
    if _stat.S_ISREG(st.st_mode):
        return 1, st.st_size, None
    files = size = 0
    why = None
    stack = [path]
    while stack:
        try:
            entries = _entries(stack.pop())
        except OSError as exc:
            why = why or _why(exc)
            continue
        for e in entries:
            if _backup._skip(e.name):
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
                elif e.is_file(follow_symlinks=False):
                    size += e.stat(follow_symlinks=False).st_size
                    files += 1
            except OSError as exc:
                why = why or _why(exc)
    return files, size, why


def _walk_store(root: str) -> dict:
    """Every file under `artifacts/`: `{digest: bytes}` for those at their
    own name, (count, bytes) of whatever else is there (a write that never
    finished, a file not at the name of its content), and why the walk is
    not complete where something could not be read."""
    top = os.path.join(root, str(_held.STORE.parent))
    at_name: dict = {}
    other = other_bytes = 0
    why = None
    # NO STORE IS NOT AN UNREADABLE STORE. A Brain that never held a file
    # has no `artifacts/` and truly holds none; one whose `artifacts/` could
    # not be looked at is not measured. `os.path.isdir` says False for both.
    stack = []
    try:
        if _stat.S_ISDIR(os.stat(top).st_mode):
            stack = [top]
        else:
            why = NOT_A_FOLDER
    except FileNotFoundError:
        pass
    except OSError as exc:
        why = _why(exc)
    while stack:
        here = stack.pop()
        try:
            entries = _entries(here)
        except OSError as exc:
            why = why or _why(exc)
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
                    continue
                if not e.is_file(follow_symlinks=False):
                    continue
                size = e.stat(follow_symlinks=False).st_size
            except OSError as exc:
                why = why or _why(exc)
                continue
            if _held.is_digest(e.name) and os.path.normcase(e.path) == \
                    os.path.normcase(str(_held.path(root, e.name))):
                at_name[e.name] = size
            else:
                other += 1
                other_bytes += size
    return {"at_name": at_name, "other": other, "other_bytes": other_bytes,
            "why_not": why}


def _walk_folder(root: str) -> dict:
    """ONE MEASUREMENT OF THE BRAIN'S FOLDER, whole: the stored files and
    every other top-level item (the database's own files apart: they are
    read with each request). What Mentis puts there is said by what it is;
    the rest is one aggregate."""
    store = _walk_store(root)
    items, rest = [], {"what": "other", "files": 0, "bytes": 0,
                       "why_not": None, "portable": False}
    listing_why = None
    try:
        top = sorted(e.name for e in _entries(root))
    except OSError as exc:
        top, listing_why = [], _why(exc)
    skip = {_backup.DB, str(_held.STORE.parent)} | set(_backup.SIDECARS)
    seen_rest = False
    for name in top:
        if name in skip or _backup._skip(name):
            continue
        n, size, why = _tree(os.path.join(root, name))
        if name in _KNOWN:
            # a count that is not of everything is not given as a count
            items.append({"what": _KNOWN[name], "files": None if why else n,
                          "bytes": None if why else size, "why_not": why,
                          "portable": name in _backup.AUX})
        else:
            seen_rest = True
            rest["files"] += n
            rest["bytes"] += size
            rest["why_not"] = rest["why_not"] or why
    if seen_rest:
        if rest["why_not"]:
            rest["files"] = rest["bytes"] = None
        items.append(rest)
    return {"at": time.time(),
            "at_name": types.MappingProxyType(store["at_name"]),
            "stray": store["other"], "stray_bytes": store["other_bytes"],
            "store_why_not": store["why_not"],
            "items": tuple(types.MappingProxyType(i) for i in items),
            "listing_why_not": listing_why}


def _folder(root: str, *, measure: bool) -> dict:
    """The kept measurement, or a new one. ONE RUNS AT A TIME per Brain:
    a caller who arrives while one is running waits for it and is given its
    result, forced or not, so no two walks overlap and a newer measurement
    is never replaced by an older one."""
    with _lock:
        kept = _measured.get(root)
        if kept is not None and not measure \
                and time.time() - kept["at"] < STORE_KEPT_S:
            return kept
        running = _measuring.get(root)
        mine = running is None
        if mine:
            running = _measuring[root] = concurrent.futures.Future()
    if not mine:
        return running.result()
    try:
        got = _walk_folder(root)
    except BaseException as exc:
        with _lock:
            _measuring.pop(root, None)
        running.set_exception(exc)
        raise
    with _lock:
        _measured[root] = got
        _measuring.pop(root, None)
    running.set_result(got)
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
    # THE CONNECTORS THERE ARE decide which files are "from a source", so a
    # failure to read them is the whole answer's failure: it is not caught
    # and turned into "no connectors", which would recount those files as
    # arriving some other way.
    src = api.sources(corpus)
    labels = {d["id"]: d["label"] for d in src.descriptors()}
    out, why = [], None
    for d in declarations(corpus):
        # whether it is bound HERE is read from this machine's own file. One
        # that could not be read is unknown (None, with the reason), and
        # then HOW MANY are bound is unknown too: never a count of the rest.
        try:
            bound = bool(src.binding_state(d["collection"]).get("bound"))
        except Exception as exc:                            # noqa: BLE001
            bound, why = None, why or _why(exc)
        out.append({"collection": d["collection"],
                    "name": d.get("name") or None,
                    "connector": d["connector"],
                    "connector_label": labels.get(d["connector"])
                    or d["connector"],
                    "bound": bound})
    return {"total": len(out),
            "bound": None if why else sum(1 for c in out if c["bound"]),
            "bound_why_not": why,
            "collections": out, "connectors": sorted(labels)}


#: how a stored file came to be held, by its Admission's source. AN ADMISSION'S
#: SOURCE IS FREE TEXT -- whatever wrote it chose it, and it can be a path --
#: so it is never returned. A file is said to have arrived in one of four
#: ways: these two, "source" with the connector's own registered id, or
#: "other", which is every remaining source counted together, unnamed.
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
            # the connector's registered id for a source; nothing otherwise
            shown = origin if group == "source" else None
            o = origins.setdefault((group, shown), {
                "group": group, "origin": shown, "references": 0,
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
                 key=lambda o: (-o["bytes"], o["group"],
                                o["origin"] or ""))},
            {"live": live, "purged_only": purged_only})


def overview(st, *, measure: bool = False) -> dict:
    """The whole answer. See the module's own words for what each part is."""
    from mentis.web import _named
    corpus, cv = st.corpus, st.cv
    root = corpus.root
    now = time.time()
    named_as = _named(root)

    sources = _sources(corpus)
    files, named = _files(corpus, set(sources.pop("connectors")))
    tally = _tally(st)
    conversations = _conversations(cv)
    posts = conversations.pop("posts")

    # -- PHYSICAL: the database (three stats; never a directory walk) -------
    db_files, db_why = [], None
    for name in (_backup.DB,) + tuple(
            x for x in _backup.SIDECARS if not x.endswith("-journal")):
        # A FILE THAT IS NOT THERE IS LEFT OUT (a `-wal` often is not). One
        # that is there and could not be sized is LISTED, with no size and
        # the reason -- as the database itself is, even when it is not found
        try:
            db_files.append({"name": name, "why_not": None,
                             "bytes": _stat_size(os.path.join(root, name))})
        except FileNotFoundError:
            if name == _backup.DB:
                db_why = db_why or NOT_FOUND
                db_files.append({"name": name, "bytes": None,
                                 "why_not": NOT_FOUND})
        except OSError as exc:
            db_why = db_why or _why(exc)
            db_files.append({"name": name, "bytes": None,
                             "why_not": _why(exc)})
    try:
        pages, page_size = corpus.database_pages()
        copy_bytes, copy_why = pages * page_size, None
    except Exception as exc:                                # noqa: BLE001
        copy_bytes, copy_why = None, _why(exc)

    # -- PHYSICAL: the folder, as it was last measured ---------------------
    m = _folder(root, measure=measure)
    live, purged_only = named["live"], named["purged_only"]
    # NAMED SINCE THE FOLDER WAS MEASURED: a file that arrived after the kept
    # measurement is looked for by its own name (one stat each) FOR THIS
    # ANSWER ONLY. The kept measurement is not changed, so a file that has
    # gone again is not carried forward under an older measuring time.
    since, store_why = {}, m["store_why_not"]
    for d in live:
        if d not in m["at_name"]:
            try:
                since[d] = _stat_size(str(_held.path(root, d)))
            except FileNotFoundError:
                pass
            except OSError as exc:
                store_why = store_why or _why(exc)
    on_disk = collections.ChainMap(since, m["at_name"])
    missing = [d for d in live if d not in on_disk]
    unnamed = [d for d in on_disk if d not in live and d not in purged_only]
    purged_here = [d for d in on_disk if d in purged_only]
    carried = [d for d in on_disk if d not in purged_only]
    carried_bytes = sum(on_disk[d] for d in carried)
    whole = store_why is None

    def known(n):
        """A figure of the stored files, or None where they were not all read."""
        return n if whole else None

    items = [dict(i) for i in m["items"]]
    kept = [i for i in items if i["portable"]]
    other = [i for i in items if not i["portable"]]
    listing_why = m["listing_why_not"]
    kept_why = listing_why or next(
        (i["why_not"] for i in kept if i["why_not"]), None)
    other_why = listing_why or next(
        (i["why_not"] for i in other if i["why_not"]), None)
    kept_bytes = None if kept_why else sum(i["bytes"] for i in kept)
    other_bytes = None if other_why else sum(i["bytes"] for i in other)

    # THE ESTIMATE IS A NUMBER ONLY WHERE EVERY PART IT ADDS UP WAS READ
    why_not = (
        f"the database's size could not be read ({copy_why})" if copy_why
        else f"the stored files could not all be read ({store_why})"
        if store_why
        else f"part of the Brain's folder could not be read ({kept_why})"
        if kept_why else None)
    portable = None if why_not else copy_bytes + carried_bytes + kept_bytes
    return {
        # its name and what it is for, and nothing else `_named` says: where
        # there is no manifest its reason names the folder
        "brain": {"id": corpus.corpus_id,
                  "corpus_name": named_as.get("corpus_name"),
                  "corpus_role": named_as.get("corpus_role")},
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
            "measured_at": m["at"],
            "kept_for_s": STORE_KEPT_S,
            "database": {
                "bytes": None if db_why else sum(f["bytes"] for f in db_files),
                "why_not": db_why,
                "files": db_files,
                # what a backup of it writes: one file, no -wal beside it
                "copy_bytes": copy_bytes},
            "files": {
                "why_not": store_why,
                "on_disk": known(len(on_disk)),
                "bytes": known(sum(on_disk.values())),
                # named by the record and not there: a copy made without
                # the stored files reads every one of them as missing
                "missing": known(len(missing)),
                "missing_bytes": known(sum(live[d] or 0 for d in missing)),
                # there, and named by nothing in the record
                "unnamed": known(len(unnamed)),
                "unnamed_bytes": known(sum(on_disk[d] for d in unnamed)),
                # there, though every reference to them was purged
                "purged_present": known(len(purged_here)),
                "purged_present_bytes": known(
                    sum(on_disk[d] for d in purged_here)),
                # not at the name of their content, or a write never finished
                "stray": known(m["stray"]),
                "stray_bytes": known(m["stray_bytes"])},
            # the rest of the folder, by what each thing is (never by name)
            "kept": kept,
            "other": other,
            "folder_why_not": listing_why,
        },
        "portable": {
            "bytes": portable,
            "why_not": why_not,
            "as": "python -m mentis.brain backup --portable",
            # said, not counted: the backup's own list of its contents
            "not_counted": ["BACKUP.json"],
            "parts": [
                {"part": "database", "bytes": copy_bytes},
                {"part": "files", "bytes": known(carried_bytes),
                 "count": known(len(carried))},
                # how many carried items there are is not known where the
                # folder could not be listed: none found is not none there
                {"part": "kept", "bytes": kept_bytes,
                 "count": None if listing_why else len(kept)}],
            "left_out": {
                "sources": sources["total"],
                "purged_files": known(len(purged_here)),
                "purged_bytes": known(sum(on_disk[d] for d in purged_here)),
                "missing_files": known(len(missing)),
                "stray_files": known(m["stray"]),
                "stray_bytes": known(m["stray_bytes"]),
                "other": other,
                "other_bytes": other_bytes,
                "sidecar_bytes": None if db_why else sum(
                    f["bytes"] for f in db_files if f["name"] != _backup.DB)},
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
