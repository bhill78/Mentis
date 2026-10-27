"""File-based SQLite Sources. Identity is a key slot, never a lifetime claim.

The backup API captures a consistent private database. Before column consent, Mentis reads from the live file only: its first 16 bytes (the SQLite header); the catalog (`sqlite_schema` and the table, column, index, foreign-key and page PRAGMAs); one `count(*)` per table; and, to size tables, the file's b-tree pages as raw bytes. The size walk decodes only page headers, cell pointers, payload-length and rowid varints and overflow page numbers. It decodes no column value, and returns only page counts. Nothing but those counts and sizes leaves `inspect`. Every value, including keys, samples and acquired rows, is read later from the private snapshot, never the live file. No SQL supplied by the caller is executed; per-table rules are a closed structure compiled to parameterised SQL.

This module is the SQLite dialect of `relational`, which holds what every relational Source shares and states these guarantees for every dialect. What is SQLite's own stays here: the header check, the backup-API snapshot, b-tree and dbstat sizing, `find`, WAL handling and staging.
"""
from __future__ import annotations

import contextlib
import hashlib
import pathlib
import os
import re
import shutil
import sqlite3
import sys
import time
import uuid

from mentis.sources import (DECLARED, PlanChanged, Refused, apply, bindings,
                            canonical, declaration as any_declaration, diff,
                            effective_scope, latest, prepare, record_revision,
                            source_id, OVER_HELD_LIMIT)
from mentis.spine import held
from mentis.sources import relational, sqlite_rules

CONNECTOR = "sqlite"
LABEL = "SQLite"
NOUN = "database file"
PLAN_CHANGE_REASON = "binding, scope, consent or record changed since preview"
CAPTURE = "atomic snapshot (SQLite backup API)"
PAYLOAD_TYPE = "application/vnd.mentis.sqlite+json"
FK_SYNTAX = "sqlite-foreign-key"
VIRTUAL_REASON = "virtual or shadow table: external module reader not executed"
BIND_KIND = "file"
STAGE_DIR = "sqlite-stages"
STAGE_TTL = 3600
STAGE_CAP = 16
STAGE_DISK_HEADROOM = 1024 * 1024 * 1024
STAGE_TOTAL_BYTES = None
STAGE_MEMORY_BYTES = 64 * 1024 * 1024
_STAGES = {}
_SECRET = relational.SECRET

DB_ERROR = sqlite3.Error
QUERY_ERROR = sqlite3.OperationalError
NOT_EQUAL = "IS NOT"
LIKE_ESCAPE = " ESCAPE '\\'"


def _life():
    # Item 2 supplies this module. Do not copy its lifecycle into this adapter.
    from mentis.sources import lifecycle
    return lifecycle


def _me():
    return sys.modules[__name__]


_UNDECODABLE = re.compile(r"^Could not decode to UTF-8 column '(.*?)' with text ", re.S)


def _reason(exc):
    """Why a table was not examined, without quoting the source's data.

    A reason is shown in the preview, hashed into the plan and recorded on the
    sweep act, so it must never carry a value (D4). Only SQLite's own errors
    (those carrying `sqlite_errorname`) are kept as said: they name schema,
    syntax or state, never rows. Python-side errors can quote what was read --
    CPython's undecodable-text error quotes the value ("Could not decode to
    UTF-8 column 'c' with text '<value>'") -- so only their kind is said, and
    for a decode failure the column, which the schema already names.
    """
    found = _UNDECODABLE.match(str(exc))
    if found:
        return f"text that is not valid UTF-8 in column {found.group(1)!r}"
    if getattr(exc, "sqlite_errorname", None):
        # Raised by SQLite itself: its messages name schema, syntax or state.
        return str(exc)
    # Raised on the Python side (decoding, conversion), whose messages can
    # quote what was read: only the kind of failure is said.
    return relational.value_free(exc)


def _interrupted(exc):
    return 'interrupt' in str(exc)


def _on_progress(db, check, every):
    db.set_progress_handler(check, every)


def _patterns(ps, default):
    return _life()._patterns(ps, default)


def _Quiet():
    return _life()._Quiet()


def _custody(corpus, s):
    return _life()._custody(corpus, s)


def _stage_cache(corpus):
    return _life()._stage_cache(_me(), corpus)


def _stage_budget(corpus, base, used):
    return _life()._stage_budget(_me(), corpus, base, used)


def _abandon_stage(corpus, key):
    return _life()._abandon_stage(_me(), corpus, key)


def _cleanup_stage_blobs(corpus, stage):
    return _life()._cleanup_stage_blobs(corpus, stage)


def _serial(fn):
    def call(*args, **kwargs):
        return _life()._serialized(_me(), fn)(*args, **kwargs)
    return call


def source_of(collection):
    return source_id(CONNECTOR, collection)


def declaration(corpus, collection):
    d = any_declaration(corpus, collection)
    if not d or d["connector"] != CONNECTOR:
        raise Refused("not a SQLite collection")
    return d


def checked_options(options, *, base=None):
    return sqlite_rules.checked_options(options, base=base)


selected = relational.selected
table_key = relational.table_key
typed = relational.typed


def row_key(table, values):
    return relational.row_key(table, values, typed)


def _q(name):
    return '"' + name.replace('"', '""') + '"'


def _param(n):
    return f"?{n}"


def _limit(sql, n):
    return f"{sql} LIMIT {n}"


def _subquery(sql):
    return "(" + sql + ")"


def _fold(value):
    # SQLite folds ASCII identifiers only. Unicode casefold would merge
    # distinct tables such as Ä and ä, even though their keys are exact.
    return value.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))


def _open(path):
    db = sqlite3.connect(pathlib.Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
    except BaseException:
        db.close()
        raise
    return db


def _digest_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _disk(db, root, budget):
    needed = db.execute("PRAGMA page_count").fetchone()[0] * db.execute("PRAGMA page_size").fetchone()[0]
    wal = pathlib.Path(str(root) + "-wal")
    try:
        needed += wal.stat().st_size
    except FileNotFoundError:
        pass
    ok = needed <= budget["room"]
    return {"needed_for_snapshot": needed, "room": budget["room"], "ok": ok,
            "message": (f"Room for the whole-file snapshot ({needed} bytes; {budget['room']} bytes available)." if ok else
                        _life()._over_budget(_me(), budget, needed))}


INSPECT_SECONDS = 10


def _clean_path(root):
    if not isinstance(root, str):
        raise Refused("a path must be text")
    root = root.strip()
    if len(root) >= 2 and root[0] == root[-1] == '"':
        root = root[1:-1]
    if not os.path.isabs(root):
        raise Refused("choose an absolute path on this machine")
    return root


def _database_path(root):
    root = _clean_path(root)
    path = pathlib.Path(root)
    if not path.exists():
        raise Refused("There is nothing at this path. Check the spelling, or use Choose a database file.")
    if path.is_dir():
        raise Refused("This is a folder. Use Look in a folder to find the databases inside it.")
    for suffix in ('-wal', '-shm', '-journal'):
        if root.endswith(suffix) and pathlib.Path(root[:-len(suffix)]).is_file():
            kind = "SQLite's write-ahead log" if suffix == '-wal' else "one of SQLite's side files"
            raise Refused(f"This is {kind}, not the database. Pick {path.name[:-len(suffix)]} next to it.")
    real = bindings._checked_root_for_file(root)
    with open(real, 'rb') as stream:
        header = stream.read(16)
    if header != b'SQLite format 3\x00':
        detail = ('It is a ZIP file.' if header.startswith(b'PK\x03\x04') else
                  'It is a Windows shortcut (.lnk); choose the file it points to.' if header.startswith(b'L\x00\x00\x00') else
                  'It is empty.' if not header else 'It may be encrypted.')
        raise Refused('This file is not a SQLite database: its first bytes do not match the SQLite header. Choose another file. ' + detail)
    return real


def _sizes(db, root, wal):
    from mentis.sources.sqlite_pages import btree_pages
    trees = list(db.execute("SELECT name,tbl_name,rootpage FROM sqlite_schema WHERE rootpage>0"))
    try:
        sizes = {name: amount for name, amount in db.execute('SELECT name,sum(pgsize) FROM dbstat GROUP BY name')}
        return {table: (sum(sizes.get(name, 0) for name, owner, _ in trees if owner == table), 'dbstat') for table in {t[1] for t in trees}}
    except sqlite3.OperationalError:
        pass
    page_size = db.execute('PRAGMA page_size').fetchone()[0]
    result = {}
    for table in {t[1] for t in trees}:
        try:
            pages = btree_pages(root, [r for _, owner, r in trees if owner == table])
            result[table] = (sum(pages.values()) * page_size, 'pages, approximate (in use)' if wal else 'pages')
        except (ValueError, OSError, IndexError):
            result[table] = (None, 'unavailable')
    return result


def inspect(corpus, root, *, progress=None):
    progress = progress or _Quiet()
    real = _database_path(root)
    # Apply the same corpus/reparse boundary as acquisition.
    real = bindings._checked_root(corpus, real, kind='file')
    info = pathlib.Path(real).stat()
    wal_path = pathlib.Path(real + '-wal')
    wal_size = wal_path.stat().st_size if wal_path.exists() else 0
    with contextlib.closing(_open(real)) as db:
        catalog = _catalog(db, metadata_only=True)
        sizes = _sizes(db, real, wal_size > 0)
        tables = relational.overview(_me(), db, catalog, sizes, progress)
        base = _stage_cache(corpus)
        used = sum(sum(f.stat().st_size for f in pathlib.Path(st['survey']['stage_dir']).iterdir() if f.is_file()) for k, st in _STAGES.items() if k[0] == corpus.corpus_id)
        disk = _disk(db, real, _stage_budget(corpus, base, used))
        return {'path': real, 'name_suggestion': pathlib.Path(real).stem.lstrip('.'), 'size': info.st_size,
                'modified': info.st_mtime, 'page_size': db.execute('PRAGMA page_size').fetchone()[0],
                'page_count': db.execute('PRAGMA page_count').fetchone()[0], 'tables': tables,
                'totals': {'tables': len(tables), 'rows': sum(t['rows'] or 0 for t in tables)},
                'wal': {'present': wal_path.exists(), 'size': wal_size}, 'shm': pathlib.Path(real+'-shm').exists(), 'disk': disk}


SAMPLE_SECONDS = 2


@_serial
def sample(corpus, plan, table, rules=None):
    return relational.sample(_me(), corpus, plan, table, rules)


def find(corpus, folder):
    folder = bindings._checked_root(corpus, _clean_path(folder))
    matches, scanned, invalid, capped = [], 0, 0, False
    pending = [(folder, 0)]
    while pending and not capped:
        parent, depth = pending.pop(0)
        with os.scandir(parent) as entries:
            for entry in entries:
                scanned += 1
                if scanned > 2000:
                    capped = True
                    break
                try:
                    info = entry.stat(follow_symlinks=False)
                    if bindings.is_reparse(info):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if depth == 0:
                            pending.append((entry.path, 1))
                        continue
                    if not entry.is_file(follow_symlinks=False) or entry.name.endswith(('-wal', '-shm', '-journal')):
                        continue
                    with open(entry.path, 'rb') as stream:
                        valid = stream.read(16) == b'SQLite format 3\x00'
                    if not valid:
                        if pathlib.Path(entry.name).suffix.lower() not in ('.db', '.sqlite', '.sqlite3', '.db3') or invalid >= 20:
                            continue
                        invalid += 1
                    matches.append({'path': entry.path, 'name': entry.name, 'size': info.st_size, 'modified': info.st_mtime,
                                    'sqlite': valid, 'wal': pathlib.Path(entry.path+'-wal').is_file()})
                    if sum(m['sqlite'] for m in matches) >= 100:
                        capped = True
                        break
                except OSError:
                    continue
    return {'folder': folder, 'matches': sorted(matches, key=lambda m: -m['size']), 'capped': capped, 'scanned': min(scanned, 2000)}


def _capture(root, directory, budget, progress, snapshot=None):
    target = directory / "capture"
    if snapshot:
        source, expected = snapshot
        if not pathlib.Path(source).is_file() or _digest_file(source) != expected:
            raise PlanChanged("captured snapshot lost or corrupt; preview again")
        if pathlib.Path(source).stat().st_size > budget["room"]:
            raise Refused("snapshot exceeds private staging budget")
        shutil.copyfile(source, target)
    else:
        bindings._checked_root_for_file(root)
        start = time.monotonic()
        def tick(status, remaining, total):
            progress.check()
            if time.monotonic() - start > 60:
                raise Refused("snapshot capture timed out; preview again")
            if target.stat().st_size > budget["room"]:
                raise Refused("snapshot exceeds private staging budget")
        try:
            with contextlib.closing(_open(root)) as src:
                disk = _disk(src, root, budget)
                if not disk["ok"]:
                    raise Refused(disk["message"])
                with contextlib.closing(sqlite3.connect(target)) as dst:
                    src.backup(dst, pages=128, progress=tick, sleep=0.01)
        except sqlite3.Error as exc:
            raise Refused(f"cannot capture SQLite database: {exc}") from None
    if target.stat().st_size > budget["room"]:
        raise Refused("snapshot exceeds private staging budget")
    digest = _digest_file(target)
    if snapshot and digest != snapshot[1]:
        raise PlanChanged("captured snapshot changed while copied; preview again")
    final = directory / digest
    target.rename(final)
    return final, digest


def _catalog(db, *, metadata_only=False):
    out = {}
    for name, sql in db.execute("SELECT name, sql FROM sqlite_schema WHERE type='table' AND name NOT GLOB 'sqlite_*' ORDER BY name"):
        # Virtual modules are not ordinary file-backed tables and may reach
        # external resources. Never execute their reader or shadow tables.
        out[name] = {"name": name, "virtual": bool(re.match(r"\s*CREATE\s+VIRTUAL", sql or "", re.I))}
    # table_list connects virtual modules (FTS reads its config rows). Inspect
    # must stay in metadata, so recognise their standard shadow names instead.
    shadows = ({name + suffix for name, t in out.items() if t["virtual"]
                for suffix in ('_data', '_idx', '_content', '_docsize', '_config', '_segments', '_segdir', '_stat', '_node', '_rowid', '_parent')}
               if metadata_only else {r[1] for r in db.execute("PRAGMA table_list") if r[2] == "shadow"})
    for name, t in out.items():
        t["virtual"] |= name in shadows
        if t["virtual"]:
            continue
        try:
            t["columns"] = list(db.execute("PRAGMA table_xinfo(" + _q(name) + ")"))
            t["foreign_keys"] = list(db.execute("PRAGMA foreign_key_list(" + _q(name) + ")"))
            t["indexes"] = []
            for idx in db.execute("PRAGMA index_list(" + _q(name) + ")"):
                parts = list(db.execute("PRAGMA index_xinfo(" + _q(idx[1]) + ")"))
                t["indexes"].append({"name": idx[1], "unique": bool(idx[2]),
                                     "partial": bool(idx[4]), "parts": parts})
        except sqlite3.Error as exc:
            t["error"] = _reason(exc)
    return out


def _identity(db, table, allowed):
    return relational.identity(_me(), db, table, allowed)


def _survey(corpus, scope, root, *, stage_dir, budget, progress=None,
            decisions=None, partial=False, snapshot=None, **unused):
    return relational.survey(_me(), corpus, scope, root, stage_dir=stage_dir, budget=budget,
                             progress=progress, decisions=decisions, partial=partial,
                             snapshot=snapshot)


_key_hash = relational.key_hash
_field_digests = relational.field_digests
_compare_for = relational.compare_for
_compare = relational.compare


def _foreign_links(db, table, row, catalog, identities, allowed):
    return relational.foreign_links(_me(), db, table, row, catalog, identities, allowed)


_scope_view = relational.scope_view


def _proposed(eff, scope):
    return relational.proposed(_me(), eff, scope)


def _revision_options(under):
    return {"options": under["options"]}


def _basis(collection, decl, bnd, s, scope):
    return relational.basis(_me(), collection, decl, bnd, s, scope)


def _plan_id(basis, scope, s, d, prior):
    return _life()._plan_id(basis, scope, s, d, prior)


def _preview_result(corpus, s, d, pid, changed, bnd):
    return relational.preview_result(_me(), corpus, s, d, pid, changed)


def _confirm_scope(scope, under, s=None):
    return {"scope": _scope_view(under)} if scope is not None else {}


def _consent(corpus, decisions, categories, pid=None):
    return relational.consent(_me(), corpus, decisions, categories, pid)


def _ready(corpus, collection):
    return relational.ready(_me(), corpus, collection)


def _plan_snapshot(corpus, cv, collection, **kwargs):
    return relational.plan_snapshot(_me(), corpus, cv, collection, **kwargs)


def _sweep_snapshot(corpus, cv, collection, plan_id, **kwargs):
    return relational.sweep_snapshot(_me(), corpus, cv, collection, plan_id, **kwargs)


def _sweep_detail(s, pid, bnd, changed, last, decl):
    return relational.sweep_detail(_me(), s, pid, bnd, changed, last)


def _sweep_done(corpus, pid):
    _abandon_stage(corpus, (corpus.corpus_id, pid))


def _forget_superseded(corpus, keep, *, collection=None, root=None):
    return relational.forget_superseded(_me(), corpus, keep, collection=collection, root=root)


def _forget_expired(corpus):
    return relational.forget_expired(_me(), corpus)


@_serial
def plan(corpus, cv, collection, **kwargs):
    _forget_expired(corpus)
    return _life().plan(_me(), corpus, cv, collection, **kwargs)


@_serial
def sweep(corpus, cv, collection, plan_id, *, actor="human", written_by=None, **kwargs):
    return _life().sweep(_me(), corpus, cv, collection, plan_id, actor=actor, written_by=written_by, **kwargs)


def _draft_basis(stage):
    return relational.draft_basis(_me(), stage)


@_serial
def preview_new(corpus, *, name, root, include=None, exclude=None, options=None,
                sensitive_decisions=None, category_decisions=None, decision_plan=None, progress=None):
    """Draft snapshot policy; acquisition runs the existing shared sweep."""
    return relational.preview_new(_me(), corpus, name=name, root=root, include=include,
                                  exclude=exclude, options=options,
                                  sensitive_decisions=sensitive_decisions,
                                  category_decisions=category_decisions,
                                  decision_plan=decision_plan, progress=progress)


@_serial
def acquire_new(corpus, cv, draft, plan_id, *, actor="human", written_by=None, progress=None):
    """Convert a verified draft to a collection and use the shared sweep.

    No third apply/transaction/Admission lifecycle: shared declare and sweep
    own those operations. The outer transaction also rolls back declaration.
    """
    return relational.acquire_new(_me(), corpus, cv, draft, plan_id, actor=actor,
                                  written_by=written_by, progress=progress)


class Connector:
    def __init__(self, corpus, cv):
        self.corpus, self.cv = corpus, cv

    def declare(self, name, **kwargs):
        kwargs.setdefault("declarer", "human")
        return _life().declare(_me(), self.corpus, self.cv, name=name, **kwargs)

    def bind(self, collection, root, written_by=None):
        declaration(self.corpus, collection)
        return bindings.bind(self.corpus, collection, root, written_by=written_by, kind="file")

    def unbind(self, collection, written_by=None):
        _life()._forget_stages(_me(), self.corpus, collection=collection)
        return bindings.unbind(self.corpus, collection, written_by=written_by)

    def binding_state(self, collection):
        return _life().binding_state(_me(), self.corpus, collection)

    def plan(self, collection, **kwargs):
        return plan(self.corpus, self.cv, collection, **kwargs)

    def sweep(self, collection, plan_id, **kwargs):
        return sweep(self.corpus, self.cv, collection, plan_id, **kwargs)

    def preview_new(self, **kwargs):
        return preview_new(self.corpus, **kwargs)

    def acquire_new(self, draft, plan_id, **kwargs):
        return acquire_new(self.corpus, self.cv, draft, plan_id, **kwargs)
