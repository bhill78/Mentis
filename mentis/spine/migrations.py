"""How a Brain's schema evolves: one ledger, one ordered list, one transaction.

Approved by the owner in "Mentis Setup Installation / Updates" (D1-D3, D4;
brief adm-8ac4ef2f4866). Deliverable 1, step 1.

ONE AUTHORITY. The schema version of a Brain is the `to_version` of the last
row of an unbroken chain in its `schema_migration` table -- the LEDGER. Nothing
else decides it:

  schema_migration   THE AUTHORITY. One row per applied migration: which,
                     from and to which version, what kind, the oldest reader
                     that may still open the result, the checksum of the
                     migration's canonical definition, which code applied it,
                     in which upgrade, and the operational record that is its
                     evidence. Append-only by trigger, like the record tables.
  PRAGMA user_version  A TRIPWIRE, never a source. The runner sets it, in the
                     same transaction, to `mirror(version)`. Releases up to
                     a24c2f0 write `1` on every open, so `1` on a Brain that
                     has a ledger proves an unguarded release opened it.
  operational        EVIDENCE. One `schema-migrated` act per ledger row,
                     written in the same transaction through the chained
                     append path. Only ever cross-checked, never read for a
                     decision.

WHY THE MIRROR IS NOT THE BARE VERSION. Deliverable 1 ships exactly one
migration, to version 1, and a legacy open writes 1: a mirror of `1` would be
indistinguishable from the legacy reset, and the tripwire could never fire on
the only ledger that exists. So the mirror is `MIRROR_BASE + version` -- still
derived from the ledger alone, still set in the same transaction, still never
read to decide a version -- and any value of `1` beside a ledger is a legacy
open, whatever the version.

OPENING NEVER WRITES SCHEMA (D2). `inspect` only reads. A Brain is created by
`create_brain`, which runs the same migrations through the same runner as an
adoption, so a new Brain and an adopted one have the same shape. Anything
whose state the ledger cannot explain is NEEDS_ATTENTION and is opened
read-only; nothing here repairs anything it was not explicitly asked to.

ONE TRANSACTION PER UPGRADE. Every pending migration, every ledger row, every
`schema-migrated` act and the mirror are written in ONE `BEGIN IMMEDIATE`
transaction at `synchronous=FULL`, and every check runs inside it before
COMMIT. A process that dies at any point before COMMIT leaves the Brain
exactly at S; after COMMIT it is exactly at T. The runner never commits an
intermediate version.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import time
import uuid
from typing import Callable

DB = "corpus.db"

#: The oldest reader version every release up to a24c2f0 counts as. They
#: have no gate of their own, so a Brain they may not open must never be
#: given to them (Deliverable 2's upgrade process enforces that).
LEGACY_READER = 1

#: What every release up to a24c2f0 writes into `user_version` on every open.
LEGACY_USER_VERSION = 1

#: `user_version` = MIRROR_BASE + ledger version. See the module docstring.
MIRROR_BASE = 1_000_000

KINDS = ("additive", "appended-data", "breaking")

#: The tables whose rows are history. Never UPDATEd or DELETEd, by anything.
CHAINED_TABLES = ("entry", "operational", "delivery")
PROTECTED_TABLES = CHAINED_TABLES + ("corpus", "schema_migration")

#: The act each ledger row's evidence carries, and the one `reconcile` writes.
MIGRATED_ACT = "schema-migrated"
LEGACY_OPEN_ACT = "legacy-open-detected"
#: the act `rebuild_derived` writes: which derived indexes it re-created
DERIVED_REBUILT_ACT = "derived-rebuilt"
ACTOR = "mentis"


def mirror(version: int) -> int:
    """What `user_version` holds on a Brain whose ledger is at `version`."""
    return MIRROR_BASE + int(version)


# -- refusals -----------------------------------------------------------------

class BrainMissing(LookupError):
    """No Brain at this path. Opening never creates one (D2)."""


class BrainExists(RuntimeError):
    """`create_brain` was pointed at a Brain that already exists."""


class BrainNotWritable(RuntimeError):
    """A caller that needs a writable Brain was given one it may not write."""

    def __init__(self, status: "Status", root: str = ""):
        self.status = status
        self.root = root
        super().__init__(status.explain(root))


class BrainReadOnly(RuntimeError):
    """A write was attempted on a Brain opened read-only."""


class MigrationRefused(RuntimeError):
    """The runner declined to start, said in words. Nothing was written."""


class MigrationFailed(RuntimeError):
    """A migration or a pre-COMMIT check failed. The transaction was rolled
    back and the Brain is exactly where it was."""


class ForbiddenStatement(MigrationFailed):
    """A migration tried something no migration may do."""


# -- the migrations -------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Migration:
    """One declared step. `statements` is the canonical definition the
    checksum is taken from: every statement `apply` may run, verbatim, and
    `procedure` says in words what it decides between them. `apply` gets a
    `MigrationContext`, never a raw connection."""

    id: str
    from_version: int
    to_version: int
    kind: str
    min_reader: int
    statements: tuple[str, ...]
    procedure: str
    apply: Callable[["MigrationContext"], None]
    #: a breaking migration names the additive migration(s) that shipped its
    #: expand half; they must already be in the ledger BEFORE this upgrade
    requires_applied: tuple[str, ...] = ()

    def canonical(self) -> str:
        return json.dumps({
            "id": self.id, "from_version": self.from_version,
            "to_version": self.to_version, "kind": self.kind,
            "min_reader": self.min_reader,
            "statements": list(self.statements),
            "procedure": self.procedure,
            "requires_applied": list(self.requires_applied),
        }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()


# 0001-adopt. FROZEN: these are the statements a24c2f0 ran on every open,
# copied verbatim (`spine/store.py` `_SCHEMA`/`_TRIGGERS`, `scratch_store.py`
# `_SCHEMA`), plus the ledger. Editing a byte changes the checksum and every
# adopted Brain would then read NEEDS_ATTENTION -- correctly, because the
# definition it was adopted under would no longer be the one declared here. A
# schema change is a NEW migration, never an edit to this one.

_A_TABLES = (
    """CREATE TABLE IF NOT EXISTS corpus (
    one         INTEGER PRIMARY KEY CHECK (one = 1),
    corpus_id   TEXT NOT NULL,
    label       TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    chained_from_first INTEGER
)""",
    """CREATE TABLE IF NOT EXISTS entry (
    seq                   INTEGER PRIMARY KEY AUTOINCREMENT,
    id                    TEXT NOT NULL UNIQUE,
    family                TEXT NOT NULL,
    def_name              TEXT,
    def_version           INTEGER,
    body                  TEXT NOT NULL,
    attributed_to         TEXT NOT NULL,
    written_by            TEXT,
    recorded_at           REAL NOT NULL,
    origin                TEXT,
    link_from             TEXT,
    link_to               TEXT,
    link_relation         TEXT,
    link_relation_version INTEGER,
    prev_hash             TEXT,
    hash                  TEXT,
    CHECK (instr(id, '/') = 0)
)""",
    """CREATE TABLE IF NOT EXISTS delivery (
    seq                 INTEGER PRIMARY KEY AUTOINCREMENT,
    id                  TEXT NOT NULL UNIQUE,
    execution           TEXT NOT NULL,
    conversation        TEXT,
    participant         TEXT,
    runtime             TEXT,
    mechanism           TEXT NOT NULL,
    at                  REAL NOT NULL,
    material            TEXT NOT NULL,
    behavioural_sources TEXT NOT NULL,
    operation_ok        INTEGER NOT NULL,
    prev_hash           TEXT,
    hash                TEXT
)""",
    """CREATE TABLE IF NOT EXISTS operational (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    id           TEXT NOT NULL UNIQUE,
    at           REAL NOT NULL,
    actor        TEXT NOT NULL,
    act          TEXT NOT NULL,
    conversation TEXT,
    turn         TEXT,
    execution    TEXT,
    runtime      TEXT,
    because      TEXT,
    caused_by    TEXT,
    about        TEXT NOT NULL,
    detail       TEXT NOT NULL,
    prev_hash    TEXT,
    hash         TEXT,
    CHECK (instr(id, '/') = 0)
)""",
)

#: the chain columns, added to a Brain older than the chain. History is not
#: backfilled: rows written before the chain existed carry no hash, and
#: `verify_chain` says how many predate it.
_A_CHAIN_COLUMNS = (
    ("entry", "prev_hash", "ALTER TABLE entry ADD COLUMN prev_hash TEXT"),
    ("entry", "hash", "ALTER TABLE entry ADD COLUMN hash TEXT"),
    ("operational", "prev_hash",
     "ALTER TABLE operational ADD COLUMN prev_hash TEXT"),
    ("operational", "hash", "ALTER TABLE operational ADD COLUMN hash TEXT"),
    ("delivery", "prev_hash", "ALTER TABLE delivery ADD COLUMN prev_hash TEXT"),
    ("delivery", "hash", "ALTER TABLE delivery ADD COLUMN hash TEXT"),
    ("corpus", "chained_from_first",
     "ALTER TABLE corpus ADD COLUMN chained_from_first INTEGER"),
)

_A_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_entry_family      ON entry(family)",
    "CREATE INDEX IF NOT EXISTS idx_entry_definition  ON entry(def_name, def_version)",
    "CREATE INDEX IF NOT EXISTS idx_entry_link_to     ON entry(link_to, link_relation)",
    "CREATE INDEX IF NOT EXISTS idx_entry_link_from   ON entry(link_from, link_relation)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_execution   ON delivery(execution)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_participant ON delivery(participant)",
    "CREATE INDEX IF NOT EXISTS idx_operational_turn         ON operational(turn)",
    "CREATE INDEX IF NOT EXISTS idx_operational_actor        ON operational(actor, seq)",
    "CREATE INDEX IF NOT EXISTS idx_operational_conversation ON operational(conversation, seq)",
    "CREATE INDEX IF NOT EXISTS idx_operational_execution    ON operational(execution)",
    "CREATE INDEX IF NOT EXISTS idx_operational_caused_by    ON operational(caused_by)",
    """CREATE INDEX IF NOT EXISTS idx_entry_admission_source
    ON entry(json_extract(body, '$.source'))
    WHERE family = 'admission' AND def_name = 'admission'""",
)

_A_TRIGGERS = (
    """CREATE TRIGGER IF NOT EXISTS entry_no_replace BEFORE INSERT ON entry
WHEN EXISTS (SELECT 1 FROM entry WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'entry is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS delivery_no_replace BEFORE INSERT ON delivery
WHEN EXISTS (SELECT 1 FROM delivery WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'delivery is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS entry_no_update BEFORE UPDATE ON entry
BEGIN SELECT RAISE(ABORT, 'entry is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS entry_no_delete BEFORE DELETE ON entry
BEGIN SELECT RAISE(ABORT, 'entry is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS delivery_no_update BEFORE UPDATE ON delivery
BEGIN SELECT RAISE(ABORT, 'delivery is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS delivery_no_delete BEFORE DELETE ON delivery
BEGIN SELECT RAISE(ABORT, 'delivery is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS operational_no_replace BEFORE INSERT ON operational
WHEN EXISTS (SELECT 1 FROM operational WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'operational history is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS operational_no_update BEFORE UPDATE ON operational
BEGIN SELECT RAISE(ABORT, 'operational history is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS operational_no_delete BEFORE DELETE ON operational
BEGIN SELECT RAISE(ABORT, 'operational history is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS corpus_no_update BEFORE UPDATE ON corpus
BEGIN SELECT RAISE(ABORT, 'corpus identity is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS corpus_no_delete BEFORE DELETE ON corpus
BEGIN SELECT RAISE(ABORT, 'corpus identity is immutable'); END""",
)

_A_SCRATCH = (
    """CREATE TABLE IF NOT EXISTS scratch (
        id          TEXT PRIMARY KEY,
        owner       TEXT NOT NULL,
        context     TEXT NOT NULL,
        created_at  REAL NOT NULL,
        touched_at  REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS scratch_message (
        scratch     TEXT NOT NULL REFERENCES scratch(id) ON DELETE CASCADE,
        n           INTEGER NOT NULL,
        role        TEXT NOT NULL CHECK (role IN ('owner','mentis')),
        parts       TEXT NOT NULL,
        at          REAL NOT NULL,
        status      TEXT NOT NULL DEFAULT 'done'
                    CHECK (status IN ('pending','done','failed','interrupted')),
        provenance  TEXT,
        PRIMARY KEY (scratch, n)
    )""",
    """CREATE TABLE IF NOT EXISTS scratch_setting (
        one          INTEGER PRIMARY KEY CHECK (one = 1),
        retain_days  INTEGER
    )""",
    # DEFAULT_RETAIN_DAYS in `mentis.scratch_store`, frozen here at 7
    "INSERT OR IGNORE INTO scratch_setting (one, retain_days) VALUES (1, 7)",
)

_A_LEDGER = (
    """CREATE TABLE IF NOT EXISTS schema_migration (
    seq             INTEGER PRIMARY KEY,
    id              TEXT NOT NULL UNIQUE,
    from_version    INTEGER NOT NULL,
    to_version      INTEGER NOT NULL,
    kind            TEXT NOT NULL
                    CHECK (kind IN ('additive','appended-data','breaking')),
    min_reader      INTEGER NOT NULL,
    checksum        TEXT NOT NULL,
    applied_by      TEXT NOT NULL,
    applied_at      REAL NOT NULL,
    upgrade_id      TEXT NOT NULL,
    operational_ref TEXT NOT NULL
)""",
    """CREATE TRIGGER IF NOT EXISTS schema_migration_no_replace
BEFORE INSERT ON schema_migration
WHEN EXISTS (SELECT 1 FROM schema_migration
             WHERE id = NEW.id OR seq = NEW.seq)
BEGIN SELECT RAISE(ABORT, 'schema_migration is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS schema_migration_no_update
BEFORE UPDATE ON schema_migration
BEGIN SELECT RAISE(ABORT, 'schema_migration is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS schema_migration_no_delete
BEFORE DELETE ON schema_migration
BEGIN SELECT RAISE(ABORT, 'schema_migration is append-only'); END""",
)

#: corpus identity for a Brain that has none. `chained_from_first` is 1 only
#: when there is no history the chain could fail to cover.
_A_IDENTITY_NEW = ("INSERT OR IGNORE INTO corpus (one, corpus_id, label, "
                   "created_at, chained_from_first) VALUES (1, ?, '', ?, 1)")
_A_IDENTITY_OLD = ("INSERT OR IGNORE INTO corpus (one, corpus_id, label, "
                   "created_at, chained_from_first) VALUES (1, ?, '', ?, NULL)")

#: each table's columns, as a24c2f0 made them. A Brain made earlier may lack
#: the chain columns, never anything else.
_A_SHAPE = {
    "corpus": ("one", "corpus_id", "label", "created_at", "chained_from_first"),
    "entry": ("seq", "id", "family", "def_name", "def_version", "body",
              "attributed_to", "written_by", "recorded_at", "origin",
              "link_from", "link_to", "link_relation",
              "link_relation_version", "prev_hash", "hash"),
    "delivery": ("seq", "id", "execution", "conversation", "participant",
                 "runtime", "mechanism", "at", "material",
                 "behavioural_sources", "operation_ok", "prev_hash", "hash"),
    "operational": ("seq", "id", "at", "actor", "act", "conversation", "turn",
                    "execution", "runtime", "because", "caused_by", "about",
                    "detail", "prev_hash", "hash"),
    "scratch": ("id", "owner", "context", "created_at", "touched_at"),
    "scratch_message": ("scratch", "n", "role", "parts", "at", "status",
                        "provenance"),
    "scratch_setting": ("one", "retain_days"),
}
_A_ADDABLE = {(t, c) for t, c, _ in _A_CHAIN_COLUMNS}


def _adopt(ctx: "MigrationContext") -> None:
    """Verify the legacy shape, then create whatever is missing."""
    have_tables = {r[0] for r in ctx.query(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    for table, want in _A_SHAPE.items():
        if table not in have_tables:
            continue
        cols = tuple(r[1] for r in ctx.query(f"PRAGMA table_info({table})"))
        missing = [c for c in want if c not in cols
                   and (table, c) not in _A_ADDABLE]
        extra = [c for c in cols if c not in want]
        if missing or extra:
            raise MigrationFailed(
                f"0001-adopt: table {table!r} is not a shape any release made "
                f"(missing {missing or 'nothing'}, unexpected "
                f"{extra or 'nothing'}); nothing was changed")
    history = any(
        t in have_tables and ctx.query(f"SELECT 1 FROM {t} LIMIT 1")
        for t in CHAINED_TABLES)
    for stmt in _A_TABLES:
        ctx.execute(stmt)
    for table, column, stmt in _A_CHAIN_COLUMNS:
        cols = {r[1] for r in ctx.query(f"PRAGMA table_info({table})")}
        if column not in cols:
            ctx.execute(stmt)
    for stmt in _A_INDEXES + _A_TRIGGERS + _A_SCRATCH + _A_LEDGER:
        ctx.execute(stmt)
    # A corpus row exists on every Brain any release made. Only a Brain with
    # none is given one, and it can claim to be chained from its first row
    # only if it has no history the chain might not cover.
    ctx.execute(_A_IDENTITY_OLD if history else _A_IDENTITY_NEW,
                (str(uuid.uuid4()), time.time()))


ADOPT = Migration(
    id="0001-adopt", from_version=0, to_version=1, kind="additive",
    min_reader=1,
    statements=(_A_TABLES + tuple(s for _, _, s in _A_CHAIN_COLUMNS)
                + _A_INDEXES + _A_TRIGGERS + _A_SCRATCH + _A_LEDGER
                + (_A_IDENTITY_NEW, _A_IDENTITY_OLD)),
    procedure=("refuse unless every existing table among corpus, entry, "
               "delivery, operational, scratch, scratch_message and "
               "scratch_setting has exactly a24c2f0's columns, less at most "
               "the chain columns; create every table, index and trigger "
               "IF NOT EXISTS; add only the chain columns that are missing; "
               "insert the retention default if absent; insert a corpus "
               "identity only if none exists, chained_from_first 1 only when "
               "no record table has a row"),
    apply=_adopt)

#: THE ordered list. One per version, contiguous from 0. There is no other.
MIGRATIONS: tuple[Migration, ...] = (ADOPT,)


def migrations() -> tuple[Migration, ...]:
    """The list in force, read at call time (a test may install its own)."""
    return MIGRATIONS


def target(ms=None) -> int:
    ms = migrations() if ms is None else ms
    return ms[-1].to_version if ms else 0


#: the triggers every adopted Brain must have, by name
PROTECTED_TRIGGERS = tuple(sorted(
    re.search(r"TRIGGER IF NOT EXISTS (\w+)", s).group(1)
    for s in _A_TRIGGERS + _A_LEDGER if "TRIGGER" in s))


# -- derived indexes ------------------------------------------------------------
#
# An index holds nothing the tables do not: it can be dropped and made again
# from the record without losing anything. A Brain whose ledger records a
# migration should have every index that migration declares; one it lacks is
# found by `verify` and re-created only by `rebuild_derived`, explicitly.
# Opening never re-creates it (D2).

_INDEX_CREATE = re.compile(
    r"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"[\"`\[]?(\w+)", re.I)
_INDEX_DROP = re.compile(
    r"^\s*DROP\s+INDEX\s+(?:IF\s+EXISTS\s+)?[\"`\[]?(\w+)", re.I)


def declared_indexes(ledger: list, ms=None) -> dict:
    """{index name: its CREATE statement} for every index declared by a
    migration this ledger records under this Mentis's own definition (same
    id, same checksum), in ledger order; a later recorded migration that
    declares `DROP INDEX` takes it out again. A row this Mentis does not
    declare -- a newer Brain's -- contributes nothing: what it declared is
    not known here."""
    ms = migrations() if ms is None else ms
    known = {m.id: m for m in ms}
    out: dict = {}
    for r in ledger:
        m = known.get(r["id"])
        if m is None or m.checksum != r["checksum"]:
            continue
        for stmt in m.statements:
            made = _INDEX_CREATE.match(stmt)
            if made:
                out[made.group(1)] = stmt
                continue
            gone = _INDEX_DROP.match(stmt)
            if gone:
                out.pop(gone.group(1), None)
    return out


def _indexes(conn) -> set:
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index'")}


def missing_indexes(conn, st: "Status", ms=None) -> list:
    """The declared indexes (see `declared_indexes`) this Brain lacks, by
    name. Reads only."""
    have = _indexes(conn)
    return sorted(n for n in declared_indexes(st.ledger, ms) if n not in have)


# -- what a migration may do ----------------------------------------------------

_P = "|".join(PROTECTED_TABLES)
_FORBIDDEN = (
    (re.compile(r"^\s*VACUUM\b", re.I), "VACUUM"),
    (re.compile(r"\b(ATTACH|DETACH)\b", re.I), "ATTACH/DETACH"),
    (re.compile(r"^\s*PRAGMA\b", re.I), "a PRAGMA (journal mode, writable "
                                        "schema and the rest belong to the "
                                        "runner)"),
    (re.compile(r"^\s*(BEGIN|COMMIT|END|ROLLBACK|SAVEPOINT|RELEASE)\b", re.I),
     "transaction control (the runner owns the one transaction)"),
    (re.compile(r"\bDROP\s+TRIGGER\s+(IF\s+EXISTS\s+)?("
                + "|".join(PROTECTED_TRIGGERS) + r")\b", re.I),
     "dropping an append-only trigger"),
    (re.compile(rf"\bUPDATE\s+(OR\s+\w+\s+)?({_P})\b", re.I),
     "UPDATE of a protected table"),
    (re.compile(rf"\bDELETE\s+FROM\s+({_P})\b", re.I),
     "DELETE from a protected table"),
    (re.compile(rf"\b(REPLACE|INSERT\s+OR\s+REPLACE)\s+INTO\s+({_P})\b", re.I),
     "REPLACE into a protected table"),
    (re.compile(r"\bINSERT\s+(OR\s+\w+\s+)?INTO\s+(entry|operational|delivery"
                r"|schema_migration)\b", re.I),
     "a raw INSERT into a chained table or the ledger (use the context's "
     "chained append)"),
    (re.compile(rf"\bDROP\s+TABLE\s+(IF\s+EXISTS\s+)?({_P})\b", re.I),
     "dropping a protected table"),
    (re.compile(rf"\bALTER\s+TABLE\s+({_P})\s+(DROP|RENAME)\b", re.I),
     "dropping or renaming a protected table's column"),
)


def forbidden(sql: str) -> str | None:
    """Why a migration may not run `sql`, or None. Comments are ignored."""
    text = re.sub(r"--[^\n]*", " ", sql)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    # a quoted or schema-qualified name is the same table: `"entry"`,
    # `[entry]`, `main.entry` and `temp.entry` must not slip past the patterns
    text = re.sub(r'["`\[\]]', "", text)
    text = re.sub(r"\b(main|temp)\s*\.\s*", "", text, flags=re.I)
    for pattern, why in _FORBIDDEN:
        if pattern.search(text):
            return why
    return None


#: what `MigrationContext.query` lets a statement do (SQLite authorizer codes)
_READ_ACTIONS = frozenset((sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT,
                           sqlite3.SQLITE_FUNCTION,
                           getattr(sqlite3, "SQLITE_RECURSIVE", 33)))
#: pragmas whose argument names what to read rather than a value to set
_READ_PRAGMAS = frozenset(("table_info", "table_xinfo", "index_list",
                           "index_info", "index_xinfo", "foreign_key_list",
                           "foreign_key_check", "integrity_check",
                           "quick_check"))


class MigrationContext:
    """What a migration's `apply` gets: statement-by-statement execution
    through the runner's checks, reads, and the chained append paths. No
    `executescript`, no raw connection."""

    def __init__(self, store, migration: Migration):
        self._store = store
        self._conn = store._conn
        self.migration = migration
        self.appended: dict[str, list[str]] = {t: [] for t in CHAINED_TABLES}

    def execute(self, sql: str, args=()):
        why = forbidden(sql)
        if why:
            raise ForbiddenStatement(
                f"{self.migration.id}: {why} is not allowed in a migration")
        if sql not in self.migration.statements:
            raise ForbiddenStatement(
                f"{self.migration.id}: ran a statement its canonical "
                f"definition does not declare: {sql[:80]!r}")
        return self._conn.execute(sql, args)

    def query(self, sql: str, args=()) -> list:
        head = sql.lstrip().split(None, 1)[0].upper()
        if head not in ("SELECT", "PRAGMA", "WITH"):
            raise ForbiddenStatement(f"{self.migration.id}: query() reads only")
        if head == "PRAGMA" and "=" in sql:
            raise ForbiddenStatement(f"{self.migration.id}: query() reads only")
        # THE HEAD IS NOT ENOUGH: `WITH ... DELETE`, `PRAGMA x(1)` read as a
        # read by the words above and write. SQLite's authorizer says what a
        # statement actually does, so anything but a read is denied there.
        denied = []

        def _only_reads(action, arg1, arg2, _db, _trigger):
            if action in _READ_ACTIONS:
                return sqlite3.SQLITE_OK
            if (action == sqlite3.SQLITE_PRAGMA
                    and (arg2 is None or arg1.lower() in _READ_PRAGMAS)):
                return sqlite3.SQLITE_OK
            denied.append(action)
            return sqlite3.SQLITE_DENY
        self._conn.set_authorizer(_only_reads)
        try:
            return self._conn.execute(sql, args).fetchall()
        except sqlite3.DatabaseError:
            if denied:
                raise ForbiddenStatement(
                    f"{self.migration.id}: query() reads only") from None
            raise
        finally:
            self._conn.set_authorizer(None)

    def append_operational(self, record: dict) -> dict:
        """appended-data migrations only: a new chained act."""
        self._appending()
        out = self._store.append_operational(record)
        self.appended["operational"].append(record["id"])
        return out

    def append_entry(self, record: dict) -> dict:
        self._appending()
        out = self._store.append_entry(record)
        self.appended["entry"].append(record["id"])
        return out

    def _appending(self):
        if self.migration.kind != "appended-data":
            raise ForbiddenStatement(
                f"{self.migration.id}: only an appended-data migration "
                f"appends records")


# -- reading a Brain's schema state (never writes) ------------------------------

OPEN = "open"
OPEN_WARNING = "open-with-warning"
UNADOPTED = "unadopted"
NEEDS_MIGRATE = "needs-migrate"
NEEDS_ATTENTION = "needs-attention"
NEEDS_NEWER = "needs-newer-mentis"
WRITABLE = (OPEN, OPEN_WARNING)


@dataclasses.dataclass
class Status:
    state: str
    target: int
    version: int | None = None            # the ledger's, None without one
    min_reader: int | None = None
    user_version: int | None = None
    ledger: list = dataclasses.field(default_factory=list)
    problems: list = dataclasses.field(default_factory=list)
    warnings: list = dataclasses.field(default_factory=list)
    legacy_open: bool = False

    @property
    def writable(self) -> bool:
        return self.state in WRITABLE

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["writable"] = self.writable
        d["expected_user_version"] = (None if self.version is None
                                      else mirror(self.version))
        return d

    def explain(self, root: str = "") -> str:
        where = f" at {root}" if root else ""
        if self.state == OPEN:
            return f"Brain{where} is at schema version {self.version}"
        if self.state == OPEN_WARNING:
            return (f"Brain{where} is at schema version {self.version}, with "
                    f"a warning: " + "; ".join(self.warnings))
        if self.state == UNADOPTED:
            return (f"Brain{where} predates the schema ledger and is opened "
                    f"read-only. Run `python -m mentis.migrate \"{root or '<brain>'}\""
                    f" --plan`, then `--apply`, to adopt it")
        if self.state == NEEDS_MIGRATE:
            return (f"Brain{where} is at schema version {self.version}; this "
                    f"Mentis needs {self.target}. It is opened read-only. Run "
                    f"`python -m mentis.migrate \"{root or '<brain>'}\" --plan`")
        if self.state == NEEDS_NEWER:
            return (f"Brain{where} is at schema version {self.version} and "
                    f"needs a reader of at least {self.min_reader}; this "
                    f"Mentis is {self.target}. It needs a newer Mentis")
        return (f"Brain{where} NEEDS ATTENTION and is opened read-only; "
                f"nothing has been repaired: " + "; ".join(self.problems))


def _tables(conn) -> set:
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}


def _triggers(conn) -> set:
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger'")}


def inspect(conn: sqlite3.Connection, ms=None) -> Status:
    """Read what this Brain's schema state is. Writes nothing.

    The ledger decides; `user_version` and the operational evidence are only
    compared with it. Every row of the open-check table in the brief is a
    branch here, and the compatibility gate is applied last."""
    ms = migrations() if ms is None else ms
    t = target(ms)
    uv = conn.execute("PRAGMA user_version").fetchone()[0]
    tables = _tables(conn)
    st = Status(state=OPEN, target=t, user_version=uv)

    if "schema_migration" not in tables:
        if uv in (0, LEGACY_USER_VERSION):
            st.state = UNADOPTED
        else:
            st.state = NEEDS_ATTENTION
            st.problems.append(
                f"no schema ledger, yet user_version is {uv}: no release "
                f"writes that without a ledger")
        return st

    rows = [dict(zip(("seq", "id", "from_version", "to_version", "kind",
                      "min_reader", "checksum", "applied_by", "applied_at",
                      "upgrade_id", "operational_ref"), r))
            for r in conn.execute(
                "SELECT seq, id, from_version, to_version, kind, min_reader, "
                "checksum, applied_by, applied_at, upgrade_id, operational_ref "
                "FROM schema_migration ORDER BY seq")]
    st.ledger = rows
    if not rows:
        st.state = NEEDS_ATTENTION
        st.problems.append("the schema ledger exists but is empty: no "
                           "runner commits a ledger without its first row")
        return st

    known = {m.to_version: m for m in ms}
    version = 0
    for i, r in enumerate(rows, start=1):
        if r["seq"] != i:
            st.problems.append(f"ledger gap: row {i} has seq {r['seq']}")
            break
        if r["from_version"] != version or r["to_version"] != version + 1:
            st.problems.append(
                f"ledger gap at {r['id']}: {r['from_version']} -> "
                f"{r['to_version']} does not follow version {version}")
            break
        if r["kind"] not in KINDS:
            st.problems.append(f"{r['id']}: unknown kind {r['kind']!r}")
        m = known.get(r["to_version"])
        if m is not None:
            if m.id != r["id"]:
                st.problems.append(
                    f"version {r['to_version']} was reached by {r['id']!r}, "
                    f"but this Mentis declares {m.id!r} for it")
            elif m.checksum != r["checksum"]:
                st.problems.append(
                    f"{r['id']}: ledger checksum {r['checksum'][:12]} does "
                    f"not match the declared definition {m.checksum[:12]}")
        version = r["to_version"]
    st.version = version
    st.min_reader = max(r["min_reader"] for r in rows)

    # EVIDENCE: one schema-migrated act per ledger row, and no other
    if "operational" in tables:
        acts = {}
        for oid, detail in conn.execute(
                "SELECT id, detail FROM operational WHERE act = ?",
                (MIGRATED_ACT,)):
            try:
                acts[oid] = json.loads(detail)
            except (TypeError, ValueError):
                acts[oid] = {}
        refs = set()
        for r in rows:
            refs.add(r["operational_ref"])
            d = acts.get(r["operational_ref"])
            if d is None:
                st.problems.append(
                    f"ledger row {r['id']} names operational record "
                    f"{r['operational_ref']} as its evidence and there is "
                    f"no such schema-migrated act")
            elif (d.get("migration") != r["id"] or d.get("ledger_seq") != r["seq"]
                  or d.get("checksum") != r["checksum"]):
                st.problems.append(
                    f"the schema-migrated act {r['operational_ref']} does not "
                    f"describe ledger row {r['id']}")
        for oid in sorted(set(acts) - refs):
            st.problems.append(
                f"schema-migrated act {oid} has no ledger row")
    else:
        st.problems.append("no operational table to hold the ledger's evidence")

    missing = [n for n in PROTECTED_TRIGGERS if n not in _triggers(conn)]
    if missing:
        st.problems.append("append-only triggers missing: " + ", ".join(missing))

    if uv != mirror(version):
        if uv == LEGACY_USER_VERSION:
            st.legacy_open = True
            if st.min_reader > LEGACY_READER:
                st.problems.append(
                    f"a release older than the schema ledger opened this "
                    f"Brain (user_version reset to 1), and the Brain needs a "
                    f"reader of at least {st.min_reader}: that release could "
                    f"not use it safely and may have written to it")
            else:
                st.warnings.append(
                    "a release older than the schema ledger opened this Brain "
                    "since its last migration (user_version reset to 1). Every "
                    "change so far is additive, so it did no harm. Run "
                    "`python -m mentis.brain reconcile <brain>` to record it")
        else:
            st.problems.append(
                f"user_version is {uv}; the ledger at version {version} "
                f"implies {mirror(version)}")

    if st.problems:
        st.state = NEEDS_ATTENTION
        return st
    # the compatibility gate
    if version == t or (version > t and st.min_reader <= t):
        st.state = OPEN_WARNING if st.warnings else OPEN
    elif version < t:
        st.state = NEEDS_MIGRATE
    else:
        st.state = NEEDS_NEWER
    return st


def require_brain(root: str) -> None:
    """BrainMissing unless a Brain exists at `root`. Never creates one."""
    if not os.path.isfile(os.path.join(root, DB)):
        raise BrainMissing(
            f"no Brain at {root}; opening or serving never creates one. "
            f"Create it with `python -m mentis.bootstrap`")


def status_of(root: str, ms=None) -> Status:
    """Inspect a Brain by path on a read-only connection of its own."""
    path = os.path.join(root, DB)
    from mentis.spine import brainlock
    brainlock.refuse_if_restoring(root)
    if not os.path.isfile(path):
        raise BrainMissing(f"no Brain at {root}")
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA query_only=ON")
        return inspect(conn, ms)
    finally:
        conn.close()


# -- who applied it ---------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def code_identity() -> dict:
    """The code doing the applying: commit and dirtiness, observed once per
    process. A published release has no git: its folder name is its commit."""
    here = pathlib.Path(__file__).resolve().parents[2]
    try:
        out = subprocess.run(["git", "-C", str(here), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            st = subprocess.run(
                ["git", "-C", str(here), "status", "--porcelain", "--",
                 "mentis"], capture_output=True, text=True, timeout=20)
            return {"commit": out.stdout.strip(),
                    "dirty": (bool(st.stdout.strip())
                              if st.returncode == 0 else None)}
    except Exception:                                       # noqa: BLE001
        pass
    name = here.name
    if re.fullmatch(r"[0-9a-f]{12}", name):
        return {"commit": None, "release": name, "dirty": None}
    return {"commit": None, "dirty": None, "path": str(here)}


# -- the runner -------------------------------------------------------------------

def _heads(conn) -> dict:
    out = {}
    tables = _tables(conn)
    for t in CHAINED_TABLES:
        if t not in tables:
            out[t] = {"count": 0, "max_seq": 0, "head": None}
            continue
        n, top = conn.execute(f"SELECT COUNT(*), COALESCE(MAX(seq), 0) "
                              f"FROM {t}").fetchone()
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
        head = None
        if top and "hash" in cols:
            head = conn.execute(f"SELECT hash FROM {t} WHERE seq = ?",
                                (top,)).fetchone()[0]
        out[t] = {"count": n, "max_seq": top, "head": head}
    return out


def free_space_needed(root: str) -> int:
    size = 0
    for name in (DB, DB + "-wal"):
        p = os.path.join(root, name)
        if os.path.exists(p):
            size += os.path.getsize(p)
    return 2 * size


def plan(root: str, *, ms=None) -> dict:
    """What `apply` would do. Writes nothing."""
    ms = migrations() if ms is None else ms
    st = status_of(root, ms)
    start = st.version or 0
    pending = [m for m in ms if m.to_version > start] \
        if st.state in (UNADOPTED, NEEDS_MIGRATE) else []
    resulting = max([r["min_reader"] for r in st.ledger]
                    + [m.min_reader for m in pending] or [0]) or None
    need = free_space_needed(root)
    free = shutil.disk_usage(root).free
    return {
        "brain": root, "status": st.state, "explain": st.explain(root),
        "from_version": st.version, "to_version": target(ms),
        "migrations": [{"id": m.id, "from": m.from_version,
                        "to": m.to_version, "kind": m.kind,
                        "min_reader": m.min_reader, "checksum": m.checksum}
                       for m in pending],
        "breaking": [m.id for m in pending if m.kind == "breaking"],
        "resulting_min_reader": resulting,
        "pre_ledger_releases_can_open_result": (
            None if resulting is None else resulting <= LEGACY_READER),
        "free_space_needed": need, "free_space": free,
        "problems": st.problems, "warnings": st.warnings,
    }


def _check_inside(store, before: dict, ctxs: list, ms, written_ops: list,
                  stop) -> None:
    """Every pre-COMMIT check, on the transaction's own connection."""
    conn = store._conn
    ic = [r[0] for r in conn.execute("PRAGMA integrity_check")]
    if ic != ["ok"]:
        raise MigrationFailed(f"integrity_check: {ic[:5]}")
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk:
        raise MigrationFailed(f"foreign_key_check: {len(fk)} violation(s)")
    chain = store.verify_chain()
    if not chain["intact"]:
        broken = {t: s["broken_at"] for t, s in chain["streams"].items()
                  if s["broken_at"]}
        raise MigrationFailed(f"verify_chain broke: {broken}")
    after = _heads(conn)
    expected = {t: sum(len(c.appended[t]) for c in ctxs) for t in CHAINED_TABLES}
    expected["operational"] += len(written_ops)
    for t in CHAINED_TABLES:
        b, a = before[t], after[t]
        kept = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE seq <= ?",
                            (b["max_seq"],)).fetchone()[0]
        if kept != b["count"]:
            raise MigrationFailed(f"{t}: {b['count']} rows before, {kept} "
                                  f"of them after")
        if b["max_seq"]:
            h = conn.execute(f"SELECT hash FROM {t} WHERE seq = ?",
                             (b["max_seq"],)).fetchone()
            if (h[0] if h else None) != b["head"]:
                raise MigrationFailed(f"{t}: the chain head before the "
                                      f"upgrade is no longer where it was")
        if a["count"] - b["count"] != expected[t]:
            raise MigrationFailed(
                f"{t}: {a['count'] - b['count']} rows appended, "
                f"{expected[t]} declared")
    missing = [n for n in PROTECTED_TRIGGERS if n not in _triggers(conn)]
    if missing:
        raise MigrationFailed("triggers missing after migration: "
                              + ", ".join(missing))
    st = inspect(conn, ms)
    if st.state != OPEN or st.version != target(ms):
        raise MigrationFailed(
            f"after migration the Brain would read {st.state} at version "
            f"{st.version}: " + "; ".join(st.problems + st.warnings))
    stop("checked")


def _run(store, st: Status, *, ms, upgrade_id: str, allow_breaking: bool,
         hook) -> dict:
    stop = hook or (lambda label: None)
    start = st.version or 0
    pending = [m for m in ms if m.to_version > start]
    applied = {r["id"] for r in st.ledger}
    for m in pending:
        if m.kind == "breaking":
            if not allow_breaking:
                raise MigrationRefused(
                    f"{m.id} is a breaking migration (raises min_reader to "
                    f"{m.min_reader}); it needs --allow-breaking")
            missing = [r for r in m.requires_applied if r not in applied]
            if not m.requires_applied or missing:
                raise MigrationRefused(
                    f"{m.id} is breaking and its additive half "
                    f"({', '.join(missing or ['undeclared'])}) has not "
                    f"shipped in an earlier upgrade")
    if not pending:
        return {"applied": [], "from_version": start, "to_version": start,
                "upgrade_id": upgrade_id}
    conn = store._conn
    before = _heads(conn)
    identity = json.dumps(code_identity(), sort_keys=True)
    ctxs, ops = [], []
    stop("before-begin")
    with store.write():
        stop("began")
        seq = len(st.ledger)
        for m in pending:
            ctx = MigrationContext(store, m)
            try:
                m.apply(ctx)
            except MigrationFailed:
                raise
            except Exception as exc:
                # whatever a migration raised, the transaction rolls back and
                # the caller is told so in the runner's own terms
                raise MigrationFailed(
                    f"{m.id} failed: {type(exc).__name__}: {exc}") from exc
            ctxs.append(ctx)
            seq += 1
            oid = f"opr-{uuid.uuid4().hex[:12]}"
            store.append_operational({
                "id": oid, "at": time.time(), "actor": ACTOR,
                "act": MIGRATED_ACT,
                "because": f"schema migration {m.id}",
                "about": [],
                "detail": {"migration": m.id, "ledger_seq": seq,
                           "from_version": m.from_version,
                           "to_version": m.to_version, "kind": m.kind,
                           "min_reader": m.min_reader,
                           "checksum": m.checksum,
                           "upgrade_id": upgrade_id,
                           "applied_by": json.loads(identity)}})
            ops.append(oid)
            conn.execute(
                "INSERT INTO schema_migration (seq, id, from_version, "
                "to_version, kind, min_reader, checksum, applied_by, "
                "applied_at, upgrade_id, operational_ref) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (seq, m.id, m.from_version, m.to_version, m.kind,
                 m.min_reader, m.checksum, identity, time.time(), upgrade_id,
                 oid))
            stop(f"after:{m.id}")
        conn.execute(f"PRAGMA user_version={mirror(pending[-1].to_version)}")
        _check_inside(store, before, ctxs, ms, ops, stop)
        stop("before-commit")
    stop("after-commit")
    return {"applied": [m.id for m in pending], "from_version": start,
            "to_version": pending[-1].to_version, "upgrade_id": upgrade_id,
            "operational": ops}


def _maintenance(root: str, *, purpose: str):
    """The exclusive lock, then a writable store that skips the open gate."""
    from mentis.spine import brainlock, store as _store
    lock = brainlock.exclusive(root, purpose)
    try:
        s = _store.Store(root, _maintenance=True)
    except BaseException:
        lock.release()
        raise
    return lock, s


def apply(root: str, *, allow_breaking: bool = False, ms=None,
          upgrade_id: str | None = None, hook=None) -> dict:
    """Run every pending migration in ONE transaction. Exclusive lock; refuses
    while anything guarded has the Brain open."""
    ms = migrations() if ms is None else ms
    if not os.path.isfile(os.path.join(root, DB)):
        raise BrainMissing(f"no Brain at {root}; migrate never creates one")
    need = free_space_needed(root)
    free = shutil.disk_usage(root).free
    if free < need:
        raise MigrationRefused(f"{free} bytes free; the upgrade needs {need}")
    lock, s = _maintenance(root, purpose="migrate")
    try:
        st = inspect(s._conn, ms)
        if st.state == NEEDS_ATTENTION:
            raise MigrationRefused(st.explain(root))
        if st.state == NEEDS_NEWER:
            raise MigrationRefused(st.explain(root))
        if st.legacy_open:
            raise MigrationRefused(
                "a pre-ledger release opened this Brain since its last "
                "migration; run `python -m mentis.brain reconcile` first so "
                "that is recorded before anything else changes")
        return _run(s, st, ms=ms, upgrade_id=upgrade_id or
                    f"upg-{uuid.uuid4().hex[:12]}",
                    allow_breaking=allow_breaking, hook=hook)
    finally:
        s.close()
        lock.release()


def create_brain(root: str, *, ms=None) -> dict:
    """Make a new Brain: the explicit act D2 requires. Every migration runs
    through the same runner as an adoption, so the two have one shape.

    Refused where a Brain exists and where an interrupted restore is
    unresolved. If it fails, the empty file it made is removed again, so a
    failed creation leaves nothing that reads as a Brain."""
    from mentis.spine import brainlock
    ms = migrations() if ms is None else ms
    path = os.path.join(root, DB)
    brainlock.refuse_if_restoring(root)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        raise BrainExists(f"a Brain already exists at {root}")
    made = not os.path.exists(path)
    os.makedirs(root, exist_ok=True)
    lock, s = _maintenance(root, purpose="create")
    ok = False
    try:
        if _tables(s._conn):
            raise BrainExists(f"a Brain already exists at {root}")
        s._conn.execute("PRAGMA journal_mode=WAL")
        st = inspect(s._conn, ms)
        out = _run(s, st, ms=ms, upgrade_id=f"new-{uuid.uuid4().hex[:12]}",
                   allow_breaking=True, hook=None)
        ok = True
        return out
    finally:
        empty = not ok and made and not _tables(s._conn)
        s.close()
        if empty:
            for name in (DB, DB + "-wal", DB + "-shm"):
                try:
                    os.remove(os.path.join(root, name))
                except OSError:
                    pass
        lock.release()


def verify(root: str, *, ms=None) -> dict:
    """`mentis brain verify`: the open check in full, plus integrity, foreign
    keys, the hash chain, the trigger set and both stores' markers. Read-only;
    takes the OPEN lock shared, so it waits for nothing and changes nothing."""
    from mentis.spine import store as _store
    ms = migrations() if ms is None else ms
    s = _store.Store(root, access="read")
    try:
        conn = s._conn
        st = inspect(conn, ms)
        ic = [r[0] for r in conn.execute("PRAGMA integrity_check")]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        # a Brain older than the chain (unadopted) has no hash columns yet
        chained = all(
            {"prev_hash", "hash"} <= {r[1] for r in conn.execute(
                f"PRAGMA table_info({t})")}
            for t in CHAINED_TABLES if t in _tables(conn))
        chain = (s.verify_chain() if "entry" in _tables(conn) and chained
                 else None)
        triggers = sorted(_triggers(conn))
        lacking = missing_indexes(conn, st, ms)
    finally:
        s.close()
    markers = {}
    for name, where in (("brain", root),
                        ("instances", os.path.join(root, "instances"))):
        p = os.path.join(where, "mentis-corpus.json")
        try:
            with open(p, encoding="utf-8") as fh:
                v = json.load(fh).get("corpus_version")
            from mentis.corpus.store import CORPUS_VERSION
            markers[name] = {"corpus_version": v,
                             "known": isinstance(v, int)
                             and v <= CORPUS_VERSION}
        except FileNotFoundError:
            markers[name] = None
        except (OSError, ValueError) as exc:
            markers[name] = {"error": f"{type(exc).__name__}: {exc}"}
    problems = list(st.problems)
    if ic != ["ok"]:
        problems.append(f"integrity_check: {ic[:5]}")
    if fk:
        problems.append(f"foreign_key_check: {len(fk)} violation(s)")
    if chain is not None and not chain["intact"]:
        problems.append("hash chain broken: " + json.dumps(
            {t: v["broken_at"] for t, v in chain["streams"].items()
             if v["broken_at"]}))
    for name, m in markers.items():
        if m and not m.get("known", True):
            problems.append(f"{name} marker corpus_version "
                            f"{m.get('corpus_version')} is newer than this "
                            f"Mentis knows")
    if lacking:
        problems.append(
            "derived indexes the ledger's migrations declare are missing: "
            + ", ".join(lacking) + ". They hold nothing the record does not; "
            "re-create them with `python -m mentis.brain rebuild-derived "
            f"\"{root}\"`")
    return {"brain": root, "status": st.as_dict(), "explain": st.explain(root),
            "integrity_check": ic, "foreign_key_violations": len(fk),
            "chain": chain, "triggers": triggers, "markers": markers,
            "missing_indexes": lacking,
            "ok": not problems and st.state in WRITABLE,
            "problems": problems}


def reconcile(root: str, *, ms=None) -> dict:
    """Record a detected legacy open and restore the mirror. Explicit only;
    refuses unless the tripwire is the ONLY thing wrong and it was harmless."""
    ms = migrations() if ms is None else ms
    if not os.path.isfile(os.path.join(root, DB)):
        raise BrainMissing(f"no Brain at {root}")
    lock, s = _maintenance(root, purpose="reconcile")
    try:
        st = inspect(s._conn, ms)
        if not st.legacy_open:
            raise MigrationRefused(
                f"nothing to reconcile: {st.explain(root)}")
        if st.state != OPEN_WARNING and not (
                st.state == NEEDS_MIGRATE and not st.problems):
            raise MigrationRefused(
                "reconcile only records a harmless legacy open; this Brain "
                + st.explain(root))
        oid = f"opr-{uuid.uuid4().hex[:12]}"
        with s.write():
            s.append_operational({
                "id": oid, "at": time.time(), "actor": ACTOR,
                "act": LEGACY_OPEN_ACT,
                "because": ("user_version was reset to 1 by a release older "
                            "than the schema ledger"),
                "about": [],
                "detail": {"observed_user_version": st.user_version,
                           "restored_user_version": mirror(st.version),
                           "ledger_version": st.version,
                           "min_reader": st.min_reader,
                           "reconciled_by": code_identity()}})
            s._conn.execute(f"PRAGMA user_version={mirror(st.version)}")
            after = inspect(s._conn, ms)
            if after.legacy_open or after.problems:
                raise MigrationFailed("reconcile did not clear the tripwire: "
                                      + after.explain(root))
        return {"reconciled": True, "operational": oid,
                "user_version": mirror(st.version), "version": st.version}
    finally:
        s.close()
        lock.release()


def _read_only(root: str) -> str:
    return (f"rebuild-derived needs to write the Brain at {root}, but its "
            f"{DB} is read-only; nothing was changed. Make it writable and "
            f"run rebuild-derived again")


def rebuild_derived(root: str, *, ms=None, hook=None) -> dict:
    """Re-create every derived index the ledger's migrations declare and the
    Brain lacks. Explicit only; exclusive lock; ONE transaction holding every
    index and the `derived-rebuilt` act that says which. Changes no ledger
    row, no version and no mirror, and refuses on any Brain this Mentis does
    not open writable -- an index is never the thing that settles that."""
    ms = migrations() if ms is None else ms
    stop = hook or (lambda label: None)
    if not os.path.isfile(os.path.join(root, DB)):
        raise BrainMissing(f"no Brain at {root}")
    if not os.access(os.path.join(root, DB), os.W_OK):
        raise MigrationRefused(_read_only(root))
    lock, s = _maintenance(root, purpose="rebuild-derived")
    try:
        conn = s._conn
        st = inspect(conn, ms)
        if st.state not in WRITABLE:
            raise MigrationRefused(
                "rebuild-derived re-creates indexes only on a Brain this "
                "Mentis opens writable; " + st.explain(root))
        missing = missing_indexes(conn, st, ms)
        if not missing:
            return {"brain": root, "rebuilt": [], "operational": None,
                    "version": st.version}
        declared = declared_indexes(st.ledger, ms)
        oid = f"opr-{uuid.uuid4().hex[:12]}"
        try:
            with s.write():
                for name in missing:
                    conn.execute(declared[name])
                    stop(f"after:{name}")
                s.append_operational({
                    "id": oid, "at": time.time(), "actor": ACTOR,
                    "act": DERIVED_REBUILT_ACT,
                    "because": ("derived indexes the ledger's migrations "
                                "declare were missing from the Brain"),
                    "about": [],
                    "detail": {"indexes": missing,
                               "ledger_version": st.version,
                               "user_version": st.user_version,
                               "rebuilt_by": code_identity()}})
                after = inspect(conn, ms)
                still = missing_indexes(conn, after, ms)
                ic = [r[0] for r in conn.execute("PRAGMA integrity_check")]
                if (still or ic != ["ok"] or after.ledger != st.ledger
                        or after.user_version != st.user_version
                        or after.state != st.state):
                    raise MigrationFailed(
                        f"rebuild-derived would leave the Brain changed "
                        f"beyond its indexes or still lacking some (missing "
                        f"{still}, integrity {ic[:3]}, state {after.state}); "
                        f"rolled back")
                stop("before-commit")
        except sqlite3.OperationalError as exc:
            # the file's permissions, not its state: a refusal, not a crash
            if "readonly" not in str(exc).replace(" ", "").lower():
                raise
            raise MigrationRefused(_read_only(root)) from exc
        return {"brain": root, "rebuilt": missing, "operational": oid,
                "version": st.version}
    finally:
        s.close()
        lock.release()
