"""Durable storage for a corpus: portable SQLite, append-only at the database.

The JSONL prototype falsified the logical model and is gone. What it established
survives: the substrate is small, and SQLite does not get to enlarge it because
relational tables are available.

PHYSICAL SCHEMA -- three durable tables, and each preserves a fact no other can.

  corpus    the corpus's own durable identity. One row, immutable. Nothing else
            can hold it, because it is about the corpus rather than about
            anything in it. This is what makes a path a LOCATION.
  entry     every durable record, of every family and every Kind. Kinds and
            Relations are data, so a new one is a row and never a migration.
  delivery  what Foundation actually put in front of an execution. Separate
            from `entry` for the reason it was always separate: no semantic
            write path reaches it, so "existence is not delivery" stays
            structural rather than advisory.
  operational  what actors DID -- started work, consulted, delegated, returned
            a result, recorded an expectation. Measured, not assumed: putting
            these in `entry` made 480 of 481 consultation candidates
            operational chatter, burying the single genuine Finding, and cost
            4.16 entry rows per act because every reference is a Link and a
            Link is an Entry. It also invites `stands()` on an act that neither
            stands nor is superseded. Different fact, different integrity
            boundary, different access pattern -- a time-ordered feed rather
            than a graph walk.

            Unlike `delivery`, this one IS writable through the semantic seam:
            recording what you did is ordinary work. Delivery keeps its
            anti-forgery boundary precisely because nothing semantic reaches it.

APPEND-ONLY is enforced by the database, not by convention: six triggers reject
UPDATE and DELETE on all three tables. `INSERT OR REPLACE` is a DELETE followed
by an INSERT, so the delete trigger catches that too.

ORDER. A JSONL file kept append order for free. Rows do not, so append order had
to become explicit: `seq`. It is the physical realisation of what the log always
had, not a new semantic fact -- but it did have to be recognised.

THREADS. One `Store` owns one connection, and `check_same_thread=False` lets
several threads reach it. That is a promise to serialise them, not a claim that
SQLite will: measured, two threads interleaving inside one connection returned
half-built rows -- `IndexError` on a column and `None` where the body should be.
So every use of the connection is taken under one reentrant lock, and a
transaction holds that lock for its whole length, because statements from
another thread inside somebody's BEGIN IMMEDIATE is exactly the corruption that
was observed. Separate PROCESSES still get real WAL concurrency; this only
serialises threads sharing one connection.

READERS DO NOT QUEUE BEHIND A WRITER (R1) -- WHERE THEY CANNOT WRITE. With
one lock for everything, a read waited for the whole of somebody else's
transaction -- measured, a 30k-object Sources confirm held it for 14.5 s and
every Conversation read, Turn read and Sources listing in the server waited
that long. WAL already gives a reader on ANOTHER connection the last committed
state, never a row of an open transaction, so a read can take a connection of
its own from a small pool (`_reading`), opened `query_only`, and not wait.

ONLY INSIDE `reading_beside_writer()`, AND NEVER WITH A WRITE IN IT. The first
version (070aa967) read beside the writer EVERYWHERE, and the independent
review (adm-a35f4cb543a4) reproduced what that does to check-then-append code:
a check made on the committed state while another thread's transaction was
still open, acted on after it committed -- an edit of a deleted item, a reused
definition version, a duplicate Participant. Which code checks before it
writes is not a list anybody can keep, so this is not fixed site by site. A
thread reads beside the writer only inside that scope, which is entered for
work that should not write (the server's GET handling), and a write attempted
inside it is REFUSED (`WriteWhileReadingBeside`) before it takes the lock --
so nothing can be appended on what was read there. The server then answers
that request again outside the scope, every read under the lock, as before.
Everywhere else -- every POST, every agent, every sweep -- reads exactly as it
always did: the writer's connection, under the lock. A thread the scope starts
does not inherit it: the scope is per thread.

A read made inside a transaction goes through the writer's connection, because
it must see that transaction's own appends. Several statements read together
(`advance`, `operational_order`) are one read transaction on a pooled
connection, so they still describe one moment of the record. Writes are
unchanged: one connection, one lock, held for the whole transaction.

PORTABILITY. `corpus.db` is the corpus. WAL puts `-wal` and `-shm` beside it
while open; both are transient, and SQLite removes them when the LAST connection
closes cleanly. So the contract is:

  closed copy    close every connection, then copy the corpus DIRECTORY:
                 `corpus.db`, and `artifacts/` if any bytes are held.
  live snapshot  call `Corpus.snapshot(path)`. SQLite's own backup, safe with
                 writers active, and the result needs no sidecar; the held
                 bytes the record names are copied beside it.
  never          copying `corpus.db` by hand while the corpus is open. The
                 committed data you want may still be in `-wal`.

HELD BYTES ARE NOT IN HERE. An Admission with `content: held` names a digest,
and the bytes are files under `artifacts/` in the same directory -- see
`mentis.spine.held`. A copy of `corpus.db` alone is a corpus in which every
held artifact reads as missing, which is why the contract above names both.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import threading

DB = "corpus.db"

#: how many idle read connections a Store keeps for reuse. More can be open at
#: once -- one per concurrent reader -- and the extra ones are closed after use.
_IDLE_READERS = 8

#: per thread: how deep inside `reading_beside_writer()` it is, and whether a
#: write was refused there since the outermost scope was entered
_beside = threading.local()


class WriteWhileReadingBeside(RuntimeError):
    """A write was attempted inside `reading_beside_writer()`.

    Refused, never deferred: what was read in the scope may describe a moment
    before another thread's commit, and a write must not be decided on it."""


@contextlib.contextmanager
def reading_beside_writer():
    """Let THIS thread's reads, for this block, not wait for another thread's
    write transaction: they see the last committed state instead.

    For work that does not write. Any write in the block raises
    `WriteWhileReadingBeside` before it takes the lock, and the refusal is
    remembered even if the caller swallows it: `beside_writer_refused()` is
    true from then until the outermost block is entered again. The caller
    must then discard the block's answer and redo it outside the scope.
    """
    depth = getattr(_beside, "depth", 0)
    if depth == 0:
        _beside.refused = False
    _beside.depth = depth + 1
    try:
        yield
    finally:
        _beside.depth = depth


def beside_writer_refused() -> bool:
    """Whether the last outermost `reading_beside_writer()` block on this
    thread had a write refused in it."""
    return bool(getattr(_beside, "refused", False))


def _reading_beside() -> bool:
    return getattr(_beside, "depth", 0) > 0

#: THE SCHEMA IS NOT DEFINED HERE. It is the ordered migration list in
#: `mentis.spine.migrations`, and a Brain is made by `migrations.create_brain`.
#: Opening one never runs DDL (D2, adm-8ac4ef2f4866).

_COLUMNS = ("id", "family", "def_name", "def_version", "body", "attributed_to",
            "written_by", "recorded_at", "origin", "link_from", "link_to",
            "link_relation", "link_relation_version")


def reference(corpus_id: str, entry_id: str) -> str:
    """A durable object reference that survives leaving its corpus.

    Local references stay bare. A reference that must cross a corpus boundary
    names the corpus, and because a local id can never contain `/` the two are
    always distinguishable -- so adding cross-corpus Links later rewrites
    nothing that exists now.
    """
    if "/" in entry_id:
        raise ValueError("entry id already qualified")
    return f"{corpus_id}/{entry_id}"


def parse_reference(ref: str) -> tuple[str | None, str]:
    """(corpus_id or None for 'this corpus', entry_id)."""
    if "/" in ref:
        corpus_id, entry_id = ref.split("/", 1)
        return corpus_id, entry_id
    return None, ref


class Store:
    """One corpus. Opened at a path, identified by what is inside it."""

    def __init__(self, root: str, *, access: str = "auto",
                 _maintenance: bool = False):
        """Open the Brain at `root`. NEVER creates one and never runs DDL.

        `access`: "auto" opens writable when the schema check allows it and
        read-only (query_only) otherwise; "write" refuses with
        `BrainNotWritable` unless it is writable; "read" is always read-only.
        `status` says what the check found. `_maintenance` is the migration
        runner's own door: no check, writable, `synchronous=FULL`, and the
        caller already holds the exclusive lock.
        """
        from mentis.spine import brainlock, migrations
        if access not in ("auto", "write", "read"):
            raise ValueError(f"access is auto, write or read, not {access!r}")
        self.root = root
        self.path = os.path.join(root, DB)
        if not _maintenance:
            # an interrupted restore is said as such, before "no Brain here"
            brainlock.refuse_if_restoring(root)
        if not _maintenance and not os.path.isfile(self.path):
            raise migrations.BrainMissing(
                f"no Brain at {root}. Opening never creates one: create it "
                f"with `mentis.api.create_corpus(path)`")
        #: the OPEN lock, shared, for as long as this store is open
        self._open_lock = None if _maintenance else brainlock.shared(root)
        try:
            self._conn = sqlite3.connect(self.path, isolation_level=None,
                                         check_same_thread=False)
        except BaseException:
            if self._open_lock is not None:
                self._open_lock.release()
            raise
        self._conn.row_factory = sqlite3.Row
        #: reentrant, because a read inside a transaction is ordinary
        self._lock = threading.RLock()
        #: HOW MANY ROWS THIS PROCESS HAS APPENDED, of any kind. Not identity,
        #: not a version, and never durable -- it exists so a caller holding a
        #: short-lived read scope can tell that the record moved underneath it
        #: without asking the database. Bumped by every append path below,
        #: INSIDE the write lock: `+= 1` is not atomic, and two appends racing
        #: here would lose a count, which is the one thing that would let a
        #: reader miss the write it exists to notice.
        self.writes = 0
        #: HOW MANY TRANSACTIONS THAT APPENDED HAVE COMMITTED. `writes` moves
        #: as each row is appended, before any other connection can see it;
        #: this moves when they can. See `Corpus.writes`, which is both.
        self.commits = 0
        #: HOW MANY OF THOSE COMMITS HAVE BEGUN: moved just BEFORE the COMMIT
        #: statement, as `commits` is just after it returns, so while the two
        #: differ a commit may be becoming visible to the pooled readers. A
        #: reader beside the writer cannot tell "visible yet" from "not yet"
        #: inside that window, and `commits` alone moves only after it; this
        #: moves before it (R1 + R2 combined; see `Corpus.steady`).
        self.committing = 0
        #: the thread whose transaction is open on `_conn`, if any. It reads
        #: through `_conn`; so does every thread outside
        #: `reading_beside_writer()`, under the lock.
        self._writer = None
        #: idle read-only connections, and the lock that guards only the list
        self._idle: list[sqlite3.Connection] = []
        self._idle_lock = threading.Lock()
        self._closed = False
        #: Context cache revisions tracker
        self.revisions = None
        try:
            self._configure()
            # THE OPEN CHECK, read-only (D2). The ledger decides; see
            # `migrations.inspect`. A Brain it does not allow writing is
            # still readable -- that is how it is inspected and repaired.
            self.status = (None if _maintenance
                           else migrations.inspect(self._conn))
            self.read_only = (not _maintenance and (
                access == "read" or not self.status.writable))
            if access == "write" and self.read_only:
                raise migrations.BrainNotWritable(self.status, root)
            if self.read_only:
                self._conn.execute("PRAGMA query_only=ON")
            else:
                # WAL: readers never block the writer, which is what a corpus
                # with several agents, humans and connectors in it needs.
                # A connection setting on a Brain that already is WAL, so not
                # a schema change; a restored or copied file may not be.
                self._conn.execute("PRAGMA journal_mode=WAL")
                # NORMAL is the WAL-safe setting: durable across process
                # crash, and can lose only the last transactions in an
                # OS/power loss. The migration runner asks for FULL, because
                # its one commit is the upgrade's commit point.
                self._conn.execute("PRAGMA synchronous="
                                   + ("FULL" if _maintenance else "NORMAL"))
        except BaseException:
            self._conn.close()
            if self._open_lock is not None:
                self._open_lock.release()
            raise

    def _configure(self):
        c = self._conn
        # Contention is expected and is not an error. Wait rather than fail.
        c.execute("PRAGMA busy_timeout=5000")
        c.execute("PRAGMA foreign_keys=ON")
        # so that REPLACE fires the delete triggers on THIS connection too
        c.execute("PRAGMA recursive_triggers=ON")

    # -- identity -----------------------------------------------------------

    @property
    def corpus_id(self) -> str:
        """Durable identity. Not the path, and it moves with the corpus."""
        with self._reading() as conn:
            return conn.execute("SELECT corpus_id FROM corpus").fetchone()[0]

    # -- reading connections ------------------------------------------------

    def _read_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, isolation_level=None,
                               check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        # a reading connection that tried to write would be a second writer
        # outside the lock; SQLite refuses it rather than trusting the caller
        conn.execute("PRAGMA query_only=ON")
        return conn

    @contextlib.contextmanager
    def _reading(self, *, together=True):
        """A connection to read committed state through, for one read.

        OUTSIDE `reading_beside_writer()`, or inside this thread's own write
        transaction: the writer's connection under the lock, exactly as every
        read was before R1 -- it waits for another thread's transaction and
        sees its own. Only inside that scope: a pooled connection held by this
        thread alone, and nothing of a transaction still open on `_conn`.
        `together`: the statements made
        through it are one read transaction, so they see the same committed
        moment. A single statement is one already, and skips the BEGIN and
        COMMIT that cost every read about 3 us (measured).
        """
        if (not _reading_beside()
                or self._writer == threading.get_ident()):
            with self._lock:
                yield self._conn
            return
        with self._idle_lock:
            if self._closed:
                # as reading through the closed writer's connection would
                raise sqlite3.ProgrammingError(
                    "Cannot operate on a closed database.")
            conn = self._idle.pop() if self._idle else None
        if conn is None:
            conn = self._read_connection()
        ok = False
        try:
            if together:
                conn.execute("BEGIN")
            yield conn
            ok = True
        finally:
            try:
                if conn.in_transaction:
                    conn.execute("COMMIT")
            except sqlite3.Error:
                ok = False
            with self._idle_lock:
                keep = ok and not self._closed and len(self._idle) < _IDLE_READERS
                if keep:
                    self._idle.append(conn)
            if not keep:
                conn.close()

    def _rows(self, sql, args=()) -> list:
        with self._reading(together=False) as conn:
            return conn.execute(sql, args).fetchall()

    # -- transactions -------------------------------------------------------

    class _Tx:
        def __init__(self, store):
            self.store, self.owned = store, False
            self.conn, self.lock = store._conn, store._lock

        def __enter__(self):
            # NOTHING IS WRITTEN ON A READ TAKEN BESIDE THE WRITER: refused
            # before the lock, so before anything can be appended (R1 repair)
            if _reading_beside():
                _beside.refused = True
                raise WriteWhileReadingBeside(
                    "a write inside reading_beside_writer(): what was read "
                    "there may predate another transaction's commit")
            if self.store.read_only:
                from mentis.spine.migrations import BrainReadOnly
                raise BrainReadOnly(
                    "this Brain is open read-only: "
                    + self.store.status.explain(self.store.root))
            # held for the WHOLE transaction: another thread slipping a
            # statement into an open BEGIN IMMEDIATE is the observed corruption
            self.lock.acquire()
            if not self.conn.in_transaction:
                # IMMEDIATE takes the write lock up front. A deferred
                # transaction that upgrades later can fail with SQLITE_BUSY
                # even with a busy timeout, because the lock cannot be granted
                # to a connection already holding a read snapshot.
                self.conn.execute("BEGIN IMMEDIATE")
                self.owned = True
                self.writes_before = self.store.writes
                self.store._writer = threading.get_ident()
            return self

        def __exit__(self, exc_type, exc, tb):
            try:
                if not self.owned:
                    return False
                try:
                    if exc_type is None:
                        # ABOUT TO BE VISIBLE, THEN VISIBLE, AND SAID BOTH
                        # TIMES. `writes` moved as each row was appended,
                        # before other connections could see it; a pooled
                        # reader that read in between took the record as it
                        # was. Counting the commit means a reader comparing
                        # `Corpus.writes` cannot mistake that older answer
                        # for this one. Counting it on BOTH sides of COMMIT
                        # means no reader can start, or finish, inside the
                        # statement without seeing a count move or the two
                        # counts differ (`Corpus.steady`). The second count
                        # is taken however COMMIT ends: a failed one is
                        # over too, and an unmatched first count would hold
                        # every reader off for good.
                        appended = self.store.writes != self.writes_before
                        if appended:
                            self.store.committing += 1
                        try:
                            self.conn.execute("COMMIT")
                        finally:
                            if appended:
                                self.store.commits += 1
                    else:
                        self.conn.execute("ROLLBACK")
                finally:
                    self.store._writer = None
                return False
            finally:
                self.lock.release()

    def write(self):
        """All-or-nothing. Nested uses join the outermost transaction."""
        return self._Tx(self)

    # -- appending ----------------------------------------------------------

    def verify_chain(self) -> dict:
        """Walk the chains and say where, if anywhere, they break.

        WHAT A MISSING HASH MEANS. An earlier version of this treated any
        row without one as predating the chain, wherever it sat -- so the
        whole mechanism was defeated by `UPDATE ... SET hash=NULL` before
        forging the row, by inserting an unhashed row mid-stream, and by
        nulling every hash and rewriting everything. All three were
        reproduced. A missing hash is now a BREAK once the chain has begun;
        only an unbroken run of them at the very start can be historical.

        AND THE CHAIN HAS TO START SOMEWHERE. The first chained row must
        carry an empty `prev_hash`, because that is what the first row of a
        chain looks like. Without that check, deleting rows from the FRONT
        left a chain whose first row pointed at a predecessor that was no
        longer there, and it verified. Also reproduced.

        WHAT IS STILL NOT DETECTED, and it is not a small thing: anything
        that rewrites the chain rather than editing under it. Recomputing
        from an edited row through to the tail produces a consistent chain.
        So does removing a tail. So does clearing every hash and appending
        afresh -- unless this corpus was chained from its first row, which
        is recorded at creation and checked here, because then a run of
        unhashed rows cannot be historical. A corpus that predates the chain
        cannot make that claim, and says so instead.

        Closing the rewrite cases needs something outside the file to
        compare against: the head hash of each stream is returned for
        exactly that purpose.
        """
        out = {"intact": True, "streams": {}}
        row = self._rows(
            "SELECT chained_from_first FROM corpus WHERE one = 1")
        row = row[0] if row else None
        from_first = bool(row[0]) if row and row[0] is not None else False
        for table in ("entry", "operational", "delivery"):
            cols = self.CHAINED[table]
            rows = self._rows(
                f"SELECT seq, {','.join(cols)}, prev_hash, hash "
                f"FROM {table} ORDER BY seq")
            prev, before, checked, broke = "", 0, 0, None
            begun = False
            for r in rows:
                d = dict(r)
                if not d.get("hash"):
                    if begun or from_first:
                        broke = broke or {
                            "seq": d["seq"], "id": d.get("id"),
                            "why": ("this row carries no hash, and the chain "
                                    "had already begun" if begun else
                                    "this corpus has been chained since its "
                                    "first row, so no row may lack one")}
                        break
                    before += 1
                    continue
                if not begun:
                    begun = True
                    if (d.get("prev_hash") or "") != "":
                        broke = {"seq": d["seq"], "id": d.get("id"),
                                 "why": ("the chain starts here but points at "
                                         "a row that is not in front of it")}
                        break
                elif (d.get("prev_hash") or "") != prev:
                    broke = {"seq": d["seq"], "id": d.get("id"),
                             "why": "this row does not follow the one before it"}
                    break
                want = hashlib.sha256(
                    ((d.get("prev_hash") or "") + chr(30)
                     + self._canonical(table, cols, d)).encode("utf-8")
                ).hexdigest()
                if want != d["hash"]:
                    broke = {"seq": d["seq"], "id": d.get("id"),
                             "why": "the row's own content does not match "
                                    "its hash"}
                    break
                prev = d["hash"]
                checked += 1
            out["streams"][table] = {
                "rows": len(rows), "chained": checked,
                "before_the_chain": before, "head": prev or None,
                "broken_at": broke}
            if broke:
                out["intact"] = False
        out["chained_from_first_row"] = from_first
        out["note"] = (
            "tamper-evident, not tamper-proof: this detects editing under "
            "the chain, not rewriting of the chain itself. Removing a tail, "
            "or recomputing from an edited row onwards, produces a "
            "consistent chain. Compare `head` with a value kept outside "
            "this file to close those.")
        return out

    #: The three durable event streams, and the fields of each that the
    #: chain covers. Everything a reader would act on is covered; `seq` is
    #: not, because it is the position rather than the content.
    CHAINED = {
        "entry": ("id", "family", "def_name", "def_version", "body",
                  "attributed_to", "written_by", "recorded_at", "origin",
                  "link_from", "link_to", "link_relation",
                  "link_relation_version"),
        "operational": ("id", "at", "actor", "act", "conversation", "turn",
                        "execution", "runtime", "because", "caused_by",
                        "about", "detail"),
        "delivery": ("id", "execution", "conversation", "participant",
                     "runtime", "mechanism", "at", "material",
                     "behavioural_sources", "operation_ok"),
    }

    @staticmethod
    def _canonical(table: str, cols, values: dict) -> str:
        """The bytes a row commits to. Unambiguous by length, not by hope.

        FOUND BEFORE IT MATTERED, AND IT WOULD HAVE MATTERED. Joining the
        fields with a separator let a value CONTAINING that separator shift
        content across a field boundary: with the same field count, an entry
        whose `attributed_to` was `owner<sep>observed:...` canonicalised to
        exactly the same bytes as one whose `attributed_to` was `owner` and
        whose `written_by` was `observed:...`. Those two fields are adjacent
        and they are the claim and the observation -- precisely the pair the
        chain exists to hold apart.

        Each field is written as its byte length, a colon, then its bytes,
        so no value can be mistaken for a boundary. NULL is written as `-`
        rather than as an empty string, because a field nobody filled in and
        a field somebody filled in with nothing are different facts.
        """
        out = [table]
        for c in cols:
            v = values.get(c)
            if v is None:
                out.append("-")
                continue
            raw = str(v).encode("utf-8")
            out.append(f"{len(raw)}:{raw.decode('utf-8')}")
        return chr(30).join(out)
    def _link_in_chain(self, table: str, values: dict) -> tuple[str, str]:
        """The previous head and this row's hash. Append-only by arithmetic.

        WHY A CHAIN AND NOT A PERMISSION. The triggers on these tables refuse
        UPDATE and DELETE, which stops this process from rewriting history
        and stops nothing else: anything that can open the file can edit it
        with the triggers dropped. A chain does not prevent that and is not
        meant to. It makes it SHOW: each row commits to the one before it, so
        a changed field, a removed row or a reordering breaks the chain at a
        knowable place, and the break survives whatever wrote it.

        The content is hashed in the column order declared above, with a
        separator that cannot occur in the encoding, so two different rows
        cannot canonicalise to the same bytes.
        """
        head = self._conn.execute(
            f"SELECT hash FROM {table} ORDER BY seq DESC LIMIT 1").fetchone()
        prev = (head[0] if head and head[0] else "")
        material = self._canonical(table, self.CHAINED[table], values)
        digest = hashlib.sha256(
            (prev + chr(30) + material).encode("utf-8")).hexdigest()
        return prev, digest

    def append_entry(self, record: dict) -> dict:
        flat = _flatten(record)
        with self.write():
            prev, digest = self._link_in_chain("entry", flat)
            cols = list(_COLUMNS) + ["prev_hash", "hash"]
            self._conn.execute(
                f"INSERT INTO entry ({','.join(cols)}) "
                f"VALUES ({','.join('?' * len(cols))})",
                tuple(flat[c] for c in _COLUMNS) + (prev, digest))
            self.writes += 1
            if self.revisions is not None:
                self.revisions.note_write(record)
        return record

    def append_entries(self, records: list[dict]) -> list[dict]:
        """Several entries, in order, in one transaction: exactly the rows and
        the chain that `append_entry` once per record would write.

        For a Sources sweep, whose 30k Admissions and 30k links were 60k
        single appends inside one write transaction -- each reading the chain
        head back from the table -- while every other writer waited (R1).
        Here the head is read once, under the lock and inside the
        transaction, so nothing can append between it and these rows, and
        each row's hash is carried to the next in order before one
        `executemany`. Same columns, same canonical bytes, same order.
        """
        flats = [_flatten(r) for r in records]
        cols = list(_COLUMNS) + ["prev_hash", "hash"]
        with self.write():
            head = self._conn.execute(
                "SELECT hash FROM entry ORDER BY seq DESC LIMIT 1").fetchone()
            prev = head[0] if head and head[0] else ""
            rows = []
            for flat in flats:
                digest = hashlib.sha256(
                    (prev + chr(30) + self._canonical(
                        "entry", self.CHAINED["entry"], flat)).encode("utf-8")
                ).hexdigest()
                rows.append(tuple(flat[c] for c in _COLUMNS) + (prev, digest))
                prev = digest
            self._conn.executemany(
                f"INSERT INTO entry ({','.join(cols)}) "
                f"VALUES ({','.join('?' * len(cols))})", rows)
            self.writes += len(rows)
            if self.revisions is not None:
                for r in records:
                    self.revisions.note_write(r)
        return records

    def append_imported(self, entries, acts) -> dict:
        """Another Brain's rows, written here with THEIR ids and times,
        chained under THIS Brain's heads, in one transaction. The import's
        only write path (design adm-6cebfabd6e9c §3).

        WHAT IT WILL WRITE IS DECIDED BY `mentis.spine.imported.check`, inside
        this transaction and before any row is appended: definitions,
        standing, placement, intake, deliveries, acts outside the allow-list,
        present ids and dangling references are refused with nothing written
        (`ImportRefused`), and a supersession that would end standing here is
        written as a proposal. There is no argument that relaxes any of it.

        Each row is chained exactly as `append_entries` / `append_operational`
        chain theirs, so `verify_chain` walks it like any other: the origin's
        own hashes cover the origin's predecessors and cannot be kept. Returns
        the ids written and the rewrites made."""
        from mentis.spine import imported
        cols = list(_COLUMNS) + ["prev_hash", "hash"]
        acols = list(self.CHAINED["operational"]) + ["prev_hash", "hash"]
        with self.write():
            allowed = imported.check(self, entries, acts)
            head = self._conn.execute(
                "SELECT hash FROM entry ORDER BY seq DESC LIMIT 1").fetchone()
            prev = head[0] if head and head[0] else ""
            rows = []
            for flat in (_flatten(r) for r in allowed["entries"]):
                digest = hashlib.sha256(
                    (prev + chr(30) + self._canonical(
                        "entry", self.CHAINED["entry"], flat)).encode("utf-8")
                ).hexdigest()
                rows.append(tuple(flat[c] for c in _COLUMNS) + (prev, digest))
                prev = digest
            head = self._conn.execute(
                "SELECT hash FROM operational ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            prev = head[0] if head and head[0] else ""
            arows = []
            for r in allowed["acts"]:
                row = {"id": r["id"], "at": r["at"], "actor": r["actor"],
                       "act": r["act"],
                       "conversation": r.get("conversation"),
                       "turn": r.get("turn"),
                       # kept as recorded only where `check` allows one
                       "execution": (r.get("execution") if r["act"] in
                                     imported.EXECUTION_INERT_ACTS else None),
                       "runtime": r.get("runtime"),
                       "because": r.get("because"),
                       "caused_by": r.get("caused_by"),
                       "about": _dump(list(r.get("about") or [])),
                       "detail": _dump(r.get("detail") or {})}
                digest = hashlib.sha256(
                    (prev + chr(30) + self._canonical(
                        "operational", self.CHAINED["operational"], row)
                     ).encode("utf-8")).hexdigest()
                arows.append(tuple(row[c] for c in self.CHAINED["operational"])
                             + (prev, digest))
                prev = digest
            if rows:
                self._conn.executemany(
                    f"INSERT INTO entry ({','.join(cols)}) "
                    f"VALUES ({','.join('?' * len(cols))})", rows)
            if arows:
                self._conn.executemany(
                    f"INSERT INTO operational ({','.join(acols)}) "
                    f"VALUES ({','.join('?' * len(acols))})", arows)
            imported.verify_work_invariants(self, allowed, entries, acts)
            self.writes += len(rows) + len(arows)
            if self.revisions is not None:
                for r in allowed["entries"]:
                    self.revisions.note_write(r)
                for r in allowed["acts"]:
                    self.revisions.note_write(r)
        return {"entries": [r["id"] for r in allowed["entries"]],
                "acts": [r["id"] for r in allowed["acts"]],
                "rewritten": allowed["rewritten"]}

    def append_delivery(self, record: dict) -> dict:
        row = {"id": record["id"], "execution": record["execution"],
               "conversation": record.get("conversation"),
               "participant": record.get("participant"),
               "runtime": record.get("runtime"),
               "mechanism": record["mechanism"], "at": record["at"],
               "material": _dump(record["material"]),
               "behavioural_sources":
                   _dump(record.get("behavioural_sources") or []),
               "operation_ok": 1 if record["operation_ok"] else 0}
        with self.write():
            prev, digest = self._link_in_chain("delivery", row)
            cols = list(self.CHAINED["delivery"]) + ["prev_hash", "hash"]
            self._conn.execute(
                f"INSERT INTO delivery ({','.join(cols)}) "
                f"VALUES ({','.join('?' * len(cols))})",
                tuple(row[c] for c in self.CHAINED["delivery"]) + (prev, digest))
            self.writes += 1
        return record

    def append_operational(self, record: dict) -> dict:
        row = {"id": record["id"], "at": record["at"],
               "actor": record["actor"], "act": record["act"],
               "conversation": record.get("conversation"),
               "turn": record.get("turn"),
               "execution": record.get("execution"),
               "runtime": record.get("runtime"),
               "because": record.get("because"),
               "caused_by": record.get("caused_by"),
               "about": _dump(record.get("about") or []),
               "detail": _dump(record.get("detail") or {})}
        cols = self.CHAINED["operational"]
        with self.write():
            prev, digest = self._link_in_chain("operational", row)
            allc = list(cols) + ["prev_hash", "hash"]
            self._conn.execute(
                f"INSERT INTO operational ({','.join(allc)}) "
                f"VALUES ({','.join('?' * len(allc))})",
                tuple(row[c] for c in cols) + (prev, digest))
            self.writes += 1
            if self.revisions is not None:
                self.revisions.note_write(record)
        return record

    # -- reading ------------------------------------------------------------

    def _entries(self, where="", args=()) -> list[dict]:
        sql = f"SELECT * FROM entry {where} ORDER BY seq"
        return [_inflate(r) for r in self._rows(sql, args)]

    def all_entries(self) -> list[dict]:
        return self._entries()

    def by_ids(self, ids) -> list[dict]:
        ids = list(ids)
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        return self._entries(f"WHERE id IN ({marks})", tuple(ids))

    def by_family(self, family) -> list[dict]:
        return self._entries("WHERE family = ?", (family,))

    def by_definition(self, name, version=None) -> list[dict]:
        if version is None:
            return self._entries("WHERE def_name = ?", (name,))
        return self._entries("WHERE def_name = ? AND def_version = ?",
                             (name, version))

    def admissions_from(self, source: str) -> list[dict]:
        """Admissions whose `source` is exactly `source`, in append order.

        Read through `idx_entry_admission_source`, so one source's history
        costs that source's rows, not every Admission in the corpus: a
        10-object collection used to pay for a 250k-object one beside it
        (E1). Without the index the same query falls back to a `json_extract`
        over every Admission row, and answers identically -- tested with it
        dropped, not assumed.

        A `prefix=` form was added with this connector and REMOVED after
        independent review: nothing in production or in a test ever called it,
        and `substr(...) = ?` would have matched any longer source sharing the
        prefix -- so `filesystem:col-ab` would have pulled in
        `filesystem:col-abcdef`. Unexercised public spine API with a latent
        boundary bug is worse than no API; exact match is what every caller
        wants and is what this now offers.
        """
        return self._entries(
            "WHERE family = 'admission' AND def_name = 'admission' "
            "AND json_extract(body, '$.source') = ?", (source,))

    def last_admission_seq(self, source: str) -> int:
        """Where `source`'s latest Admission sits in append order, or 0.

        Asked of `idx_entry_admission_source`, whose entries are ordered by
        `seq` within one source, so this is one index seek however many
        Admissions the source or the corpus holds. `entry` is append-only, so
        an unchanged answer means `admissions_from(source)` is unchanged too.
        The WHERE is `admissions_from`'s, word for word, for the same reason.
        """
        return self._rows(
            "SELECT COALESCE(MAX(seq), 0) FROM entry "
            "WHERE family = 'admission' AND def_name = 'admission' "
            "AND json_extract(body, '$.source') = ?", (source,))[0][0]

    def nodes_of_definitions(self, names) -> list[dict]:
        """Node entries (not links, not definitions) of any of these
        definitions, in append order. Read through `idx_entry_definition`; the
        names travel as one JSON parameter, as in `links`.

        `family` is checked here rather than in the WHERE, and that is the
        point: given `family = 'entry'` the planner prefers `idx_entry_family`
        and walks every link in the corpus -- one per Source Admission -- to
        find a handful of nodes (0.005 s at 10k Admissions, 0.027 s at 60k).
        The only other rows a definition name reaches are its definitions."""
        names = list(dict.fromkeys(names))
        if not names:
            return []
        return [e for e in self._entries(
            "WHERE def_name IN (SELECT value FROM json_each(?)) "
            "AND link_relation IS NULL", (json.dumps(names),))
            if e["family"] == "entry"]

    def count_of_definition(self, name) -> int:
        """How many node entries (not links, not definitions) name this
        definition. Counted in SQL, over the indexed column, never decoded."""
        return self._rows(
            "SELECT COUNT(*) FROM entry WHERE def_name = ? "
            "AND family = 'entry' AND link_relation IS NULL", (name,))[0][0]

    def count_of_links(self) -> dict[str, int]:
        """How many link entries there are of each Relation. Counted in SQL,
        over the indexed column, never decoded."""
        return dict((r[0], r[1]) for r in self._rows(
            "SELECT link_relation, COUNT(*) FROM entry "
            "WHERE family = 'entry' AND link_relation IS NOT NULL "
            "GROUP BY link_relation ORDER BY link_relation"))

    def linked_node_tally(self, relation, to, def_name) -> tuple[int, float | None]:
        """How many nodes of one Kind this relation points at `to`, and the
        latest `recorded_at` among them. Counted in SQL, never decoded.

        For a summary that wants a NUMBER. Reading the rows to call `len()` on
        them meant inflating every Turn body in a Conversation -- all of its
        prose -- to produce one integer and one timestamp, once per Conversation
        in the rail.

        DISTINCT because the question is how many THINGS, not how many links:
        `read()` over repeated ids answers once per id, so counting link rows
        would disagree with reading them where a node is linked twice. Both
        indexed columns are in `idx_entry_link_to`.
        """
        n, newest = self._rows(
            "SELECT COUNT(DISTINCT e.id), MAX(e.recorded_at) "
            "FROM entry l JOIN entry e ON e.id = l.link_from "
            "WHERE l.link_relation = ? AND l.link_to = ? "
            "AND e.def_name = ? AND e.family = 'entry' "
            "AND e.link_relation IS NULL",
            (relation, to, def_name))[0]
        return n, newest

    def definition_rows(self, name, version=None) -> list[dict]:
        if version is None:
            return self._entries("WHERE family='definition' AND def_name = ?",
                                 (name,))
        return self._entries(
            "WHERE family='definition' AND def_name = ? AND def_version = ?",
            (name, version))

    def links(self, *, relation=None, to=None, frm=None,
              to_any=None, frm_any=None) -> list[dict]:
        """Link entries, filtered, in append order.

        `to_any` / `frm_any` name a SET of endpoints: the links whose `to` (or
        `from`) is any of them. The same rows a relation-wide read filtered in
        Python would keep, in the same order -- but read through
        `idx_entry_link_to` / `idx_entry_link_from` instead of a scan of every
        entry. `link_relation = ?` alone has no index to use (it is the second
        column of both), so a relation-wide read costs every row in the corpus,
        Source Admissions included: 0.001 s with none, 0.09 s with 10k (R2).

        The set travels as ONE JSON parameter, so no number of endpoints meets
        SQLite's limit on bound variables. An empty set is an empty answer.
        """
        where, args = ["link_relation IS NOT NULL"], []
        if relation is not None:
            where.append("link_relation = ?")
            args.append(relation)
        if to is not None:
            where.append("link_to = ?")
            args.append(to)
        if frm is not None:
            where.append("link_from = ?")
            args.append(frm)
        for column, wanted in (("link_to", to_any), ("link_from", frm_any)):
            if wanted is None:
                continue
            wanted = list(dict.fromkeys(wanted))
            if not wanted:
                return []
            where.append(f"{column} IN (SELECT value FROM json_each(?))")
            args.append(json.dumps(wanted))
        return self._entries("WHERE " + " AND ".join(where), tuple(args))

    def deliveries(self) -> list[dict]:
        return self._deliveries()

    def _deliveries(self, where="", args=()) -> list[dict]:
        out = []
        rows = self._rows(f"SELECT * FROM delivery {where} ORDER BY seq", args)
        for r in rows:
            d = dict(r)
            d.pop("seq", None)
            # Integrity metadata, not content. A reader asking what happened
            # is asking about the act; the chain is how the record shows it
            # has not been edited, and `verify_chain` reads it directly.
            d.pop("prev_hash", None)
            d.pop("hash", None)
            d["material"] = json.loads(d["material"])
            d["behavioural_sources"] = json.loads(d["behavioural_sources"])
            d["operation_ok"] = bool(d["operation_ok"])
            out.append(d)
        return out

    def deliveries_for(self, execution) -> list[dict]:
        return self._deliveries("WHERE execution = ?", (execution,))

    def deliveries_by_participant(self, participant) -> list[dict]:
        return self._deliveries("WHERE participant = ?", (participant,))

    def operational(self, *, turn=None, actor=None, conversation=None,
                    execution=None, caused_by=None, since=None, limit=None,
                    newest_first=False, id=None, act=None,
                    detail_is=None) -> list[dict]:
        where, args = [], []
        # ONE FIELD OF THE DETAIL, MATCHED BY SQLITE rather than by decoding
        # every row in Python: `{"op": "k"}` keeps only acts whose detail has
        # op == "k". Narrows a read the other filters (and their indexes)
        # already bounded; it is not an index and adds none.
        for key, value in (detail_is or {}).items():
            if not isinstance(key, str) or not key.isidentifier():
                raise ValueError("a detail key is a plain identifier")
            where.append(f"json_extract(detail, '$.{key}') = ?")
            args.append(value)
        # `id` is UNIQUE, so it is indexed: one act by its id is a lookup, not
        # a decode of the whole table -- which is what finding one used to cost.
        for column, value in (("id", id), ("turn", turn), ("actor", actor),
                              ("conversation", conversation),
                              ("execution", execution),
                              ("caused_by", caused_by), ("act", act)):
            if value is None:
                continue
            # SEVERAL ACTS, OR ONE. `act` is the only filter with a natural
            # plural -- "the ways a run can end" is a tuple (`RUN_ENDS`), and
            # binding a tuple to `= ?` is not a narrower query, it is a
            # ProgrammingError at the driver. A sequence becomes an IN.
            if isinstance(value, (tuple, list, set, frozenset)):
                vals = sorted(value)
                if not vals:
                    return []          # asked for none: none, not everything
                where.append(f"{column} IN ({','.join('?' * len(vals))})")
                args.extend(vals)
            else:
                where.append(f"{column} = ?")
                args.append(value)
        if since is not None:
            where.append("at >= ?")
            args.append(since)
        sql = "SELECT * FROM operational"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY seq DESC" if newest_first else " ORDER BY seq"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self._rows(sql, tuple(args))
        return [_act_of(r)[1] for r in rows]

    def operational_under(self, parents, *, act=None) -> list[tuple]:
        """Every act whose causal parent is any of these, as (seq, act) pairs
        in write order -- one statement for any number of parents.

        WHAT `operational(caused_by=p)` GIVES FOR EACH `p`, ALL AT ONCE: the
        same rows, decoded the same way, and -- grouped by `caused_by` -- in
        the same order, because one `ORDER BY seq` over the union orders every
        parent's share of it exactly as reading that parent alone would. It is
        what lets a reader walk a causal forest one LEVEL per statement
        instead of one NODE per statement, which on the live Brain was most of
        what `/api/owed` and a Conversation's work cost (R3).

        `seq` travels beside each act, never inside it, so the act is exactly
        what `operational` returns and the write order is still had without a
        second read. The set is ONE JSON parameter, as in `links`, so no
        number of parents meets SQLite's limit on bound variables. Read-only;
        an empty set is an empty answer."""
        parents = list(dict.fromkeys(p for p in parents if p))
        if not parents:
            return []
        sql = ("SELECT * FROM operational WHERE caused_by IN "
               "(SELECT value FROM json_each(?))")
        args = [json.dumps(parents)]
        if act is not None:
            sql += " AND act = ?"
            args.append(act)
        return [_act_of(r) for r in self._rows(sql + " ORDER BY seq",
                                                 tuple(args))]

    def operational_marks(self, *, act, execution=None) -> list[dict]:
        """The acts of these kinds as MARKS ONLY -- `seq`, `id`, `act`,
        `execution`, `caused_by` -- in write order, nothing decoded.

        FOR A QUESTION THAT IS ABOUT WHICH ACTS EXIST, NOT WHAT THEY SAY.
        Which runs are open is decided by ids, instances and causal parents
        alone, and `operational()` answered it by reading and decoding every
        start act's whole `detail` -- on the live Brain 3,075 starts carrying
        71 MB of detail, 400 ms a read, on a path the UI polls every four
        seconds (`/api/working`, `/api/activity`). Leaving the two JSON
        columns out of the SELECT means SQLite never reads their overflow
        pages, so the cost follows the number of acts, not their size."""
        acts = sorted(act) if isinstance(act, (tuple, list, set, frozenset)) else [act]
        if not acts:
            return []
        sql = ("SELECT seq, id, act, execution, caused_by FROM operational "
               f"WHERE act IN ({','.join('?' * len(acts))})")
        args = list(acts)
        if execution is not None:
            sql += " AND execution = ?"
            args.append(execution)
        return [dict(r) for r in self._rows(sql + " ORDER BY seq", tuple(args))]

    def operational_order(self, ids) -> dict:
        """Each named act's position in the record's append order (`seq`).

        What `at` cannot give: two acts written in one clock tick share a
        timestamp, and a clock that steps back stamps a later act earlier.
        `seq` is assigned inside the write, so it is the order things were
        recorded. Read-only, by the UNIQUE (indexed) id, in chunks."""
        ids = [i for i in dict.fromkeys(ids) if i]
        out = {}
        with self._reading() as conn:
            for k in range(0, len(ids), 500):
                chunk = ids[k:k + 500]
                marks = ",".join("?" * len(chunk))
                for oid, seq in conn.execute(
                        f"SELECT id, seq FROM operational WHERE id IN ({marks})",
                        tuple(chunk)):
                    out[oid] = seq
        return out

    def operational_count(self) -> int:
        return self._rows("SELECT COUNT(*) FROM operational")[0][0]

    def count(self) -> int:
        return self._rows("SELECT COUNT(*) FROM entry")[0][0]

    def advance(self) -> tuple[int, int, int]:
        """HOW FAR THIS RECORD HAS GOT, as three sequence positions.

        Not a version, not a clock and not a subscription: something to
        COMPARE. A reader that has seen (a, b, c) and sees anything else
        knows the record moved and can reread what it already knows how to
        read. Each position is the greatest visible `seq`, or zero.

        Compatibility with earlier count cursors: the append-only tables
        use AUTOINCREMENT, with no deletes or skipped committed inserts.
        Rolled-back writes roll back their sequence allocation too. Thus
        counts and positions coincide for the record's append paths.

        Three indexed aggregates over three tables, which is what makes it
        cheap enough to ask for repeatedly.
        """
        with self._reading() as conn:
            top = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM entry").fetchone()[0]
            ops = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM operational").fetchone()[0]
            out = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM delivery").fetchone()[0]
        return (top, ops, out)

    def since(self, advance, cap: int, *, acts_in_full: bool = False):
        """WHAT WAS WRITTEN AFTER `advance`, as the rows that say where.

        `advance` is a tuple `advance()` returned. The rows after it: each
        entry's id, kind and link ends; each act's name, Conversation,
        execution and Turn; each delivery's Conversation and execution. Bodies are not
        read. None where more than `cap` of any of them came after it -- the
        caller then treats everything as moved -- or where the record is no
        longer at or past it.

        `acts_in_full`: each act as `operational` gives it (id, causal
        parent, actor, about, detail ...) rather than the four fields --
        what says WHICH run or request an act belongs to (Fluid F4a). The
        same rows from the same statement, so no second pass over the acts
        before them is made to find them again.

        Seek after each sequence position, without walking earlier rows.
        Read in one read transaction, so the three answer about one moment.
        """
        seq, ops, outs = advance
        with self._reading() as conn:
            now = (conn.execute("SELECT COALESCE(MAX(seq), 0) FROM entry").fetchone()[0],
                   conn.execute("SELECT COALESCE(MAX(seq), 0) FROM operational").fetchone()[0],
                   conn.execute("SELECT COALESCE(MAX(seq), 0) FROM delivery").fetchone()[0])
            if now[0] < seq or now[1] < ops or now[2] < outs:
                return None
            if now[0] - seq > cap or now[1] - ops > cap or now[2] - outs > cap:
                return None
            entries = conn.execute(
                "SELECT id, def_name, link_from, link_to, link_relation FROM entry"
                " WHERE seq > ? ORDER BY seq", (seq,)).fetchall()
            acts = conn.execute(
                ("SELECT * FROM operational" if acts_in_full else
                 "SELECT act, conversation, execution, turn FROM operational")
                + " WHERE seq > ? ORDER BY seq", (ops,)).fetchall()
            delivered = conn.execute(
                "SELECT conversation, execution FROM delivery"
                " WHERE seq > ? ORDER BY seq", (outs,)).fetchall()
        return ([tuple(r) for r in entries],
                [_act_of(r)[1] for r in acts] if acts_in_full
                else [tuple(r) for r in acts],
                [tuple(r) for r in delivered])

    # -- bounded reads for the Fluid read model (mentis/fluid) ---------------
    #
    # ADDITIVE AND READ-ONLY. Each is one statement (or one read transaction)
    # over the indexes that already exist; none decodes a body it does not
    # return, and none knows a Kind: the relation and definition names are
    # the caller's. Nothing else in the spine calls them.

    def heads(self, ids) -> dict:
        """What each of these rows IS, without its body: id -> (seq, family,
        def_name, link_from, link_to, link_relation, recorded_at,
        attributed_to). By the UNIQUE id; the set is one JSON parameter."""
        ids = list(dict.fromkeys(i for i in ids if i))
        if not ids:
            return {}
        rows = self._rows(
            "SELECT id, seq, family, def_name, link_from, link_to, "
            "link_relation, recorded_at, attributed_to FROM entry "
            "WHERE id IN (SELECT value FROM json_each(?))", (json.dumps(ids),))
        return {r[0]: tuple(r[1:]) for r in rows}

    def members_page(self, to, *, home, kind, replies, also=(), roots=True,
                     before=None, after=None, limit=50) -> dict:
        """ONE PAGE of the nodes of `kind` linked to `to` by `home`, together
        with the extra node ids `also`, in (recorded_at, seq) order.

        Each row carries its rank among the `home` nodes (`number`, None for
        an `also` node), its first `replies` parent, its position among the
        page's units and the units' total. `roots`: only nodes whose parent is
        not itself a member are units -- a reply to a member is reached
        through its thread instead. `before` / `after` are (recorded_at, seq)
        keys, exclusive; neither is the newest page.

        COST. One statement. It reads the `home` link rows of `to` and their
        nodes' (seq, recorded_at) through `idx_entry_link_to` and the primary
        key -- never a body -- and returns at most `limit` rows. Ordering by
        node time within one target has no index, so the rows of `to` are
        sorted in SQLite; that is O(members of `to`), not O(record).
        """
        limit = max(1, int(limit))
        cursor, direction = "", "DESC"
        args = {"to": to, "home": home, "kind": kind, "replies": replies,
                "also": json.dumps(list(dict.fromkeys(also))),
                "roots": 1 if roots else 0, "limit": limit}
        if before is not None:
            cursor = "WHERE (recorded_at, seq) < (:b_at, :b_seq)"
            args.update(b_at=before[0], b_seq=before[1])
        elif after is not None:
            cursor, direction = ("WHERE (recorded_at, seq) > (:a_at, :a_seq)",
                                 "ASC")
            args.update(a_at=after[0], a_seq=after[1])
        sql = f"""
            WITH home AS (
                SELECT DISTINCT e.id, e.seq, e.recorded_at
                FROM entry l JOIN entry e ON e.id = l.link_from
                WHERE l.link_to = :to AND l.link_relation = :home
                  AND e.family = 'entry' AND e.def_name = :kind
                  AND e.link_relation IS NULL),
            numbered AS (
                SELECT id, seq, recorded_at,
                       ROW_NUMBER() OVER (ORDER BY recorded_at, seq) AS number
                FROM home),
            everyone AS (
                SELECT id, seq, recorded_at, number FROM numbered
                UNION ALL
                SELECT e.id, e.seq, e.recorded_at, NULL FROM entry e
                WHERE e.id IN (SELECT value FROM json_each(:also))
                  AND e.id NOT IN (SELECT id FROM home)),
            parented AS (
                SELECT a.*, (SELECT r.link_to FROM entry r
                             WHERE r.link_from = a.id
                               AND r.link_relation = :replies
                             ORDER BY r.seq LIMIT 1) AS parent
                FROM everyone a),
            units AS (
                SELECT p.*,
                       ROW_NUMBER() OVER (ORDER BY recorded_at, seq) AS pos,
                       COUNT(*) OVER () AS total
                FROM parented p
                WHERE :roots = 0 OR parent IS NULL
                   OR parent NOT IN (SELECT id FROM everyone))
            SELECT id, seq, recorded_at, number, parent, pos, total
            FROM units {cursor}
            ORDER BY recorded_at {direction}, seq {direction}
            LIMIT :limit"""
        rows = [tuple(r) for r in self._rows(sql, args)]
        if direction == "DESC":
            rows.reverse()
        total = rows[0][6] if rows else None
        return {"rows": [r[:6] for r in rows], "total": total}

    def activity_page(self, kind, *, home, member, linked, ends,
                      limit=100, after=None) -> tuple[list[str], int]:
        """THE NODES OF `kind`, MOST RECENTLY ACTIVE FIRST, one page:
        ([id], how many there are). A node's activity is the latest of its
        newest `member` node linked to it by `home` and its newest `linked`
        link that no `ends` link points at; with neither, its own
        `recorded_at`. Ties break newest first (seq DESC).

        A NODE THAT IS A LATER VERSION OF ANOTHER -- it has an `ends` link
        from it -- is not listed: it is read as the node it supersedes (a
        renamed Conversation is the Conversation it was), never beside it.

        COST. One statement, returning at most `limit` ids, never a body. It
        aggregates the `home` and `linked` link rows of every node of `kind`
        through `idx_entry_definition` and `idx_entry_link_to`; the facts a
        caller shows are read for the returned ids only."""
        rows = self._rows("""
            WITH nodes AS (
                SELECT id, seq, recorded_at FROM entry v
                WHERE def_name = :kind AND family = 'entry'
                  AND link_relation IS NULL
                  AND NOT EXISTS (SELECT 1 FROM entry s
                                  WHERE s.link_from = v.id
                                    AND s.link_relation = :ends)),
            posted AS (
                SELECT l.link_to AS id, MAX(e.recorded_at) AS t
                FROM nodes n JOIN entry l
                  ON l.link_to = n.id AND l.link_relation = :home
                JOIN entry e ON e.id = l.link_from
                WHERE e.def_name = :member AND e.family = 'entry'
                  AND e.link_relation IS NULL
                GROUP BY l.link_to),
            included AS (
                SELECT l.link_to AS id, MAX(l.recorded_at) AS t
                FROM nodes n JOIN entry l
                  ON l.link_to = n.id AND l.link_relation = :linked
                WHERE NOT EXISTS (SELECT 1 FROM entry s
                                  WHERE s.link_to = l.id
                                    AND s.link_relation = :ends)
                GROUP BY l.link_to)
            , ranked AS (
            SELECT n.id,
                   ROW_NUMBER() OVER (ORDER BY
                     MAX(COALESCE(p.t, i.t, n.recorded_at),
                         COALESCE(i.t, p.t, n.recorded_at)) DESC, n.seq DESC) pos,
                   COUNT(*) OVER () total
            FROM nodes n
            LEFT JOIN posted p ON p.id = n.id
            LEFT JOIN included i ON i.id = n.id)
            SELECT id, total FROM ranked
            WHERE pos > COALESCE((SELECT pos FROM ranked WHERE id = :after), 0)
            ORDER BY pos
            LIMIT :limit""", {"kind": kind, "home": home, "member": member,
                              "linked": linked, "ends": ends,
                              "after": after,
                              "limit": max(1, int(limit))})
        return [r[0] for r in rows], (rows[0][1] if rows else 0)

    def member_total(self, to, *, home, kind, replies, also=(),
                     roots=True) -> int:
        """How many units `members_page` pages over: what it would say as
        `total` for any page. For an empty page, which has no row to carry it."""
        got = self.members_page(to, home=home, kind=kind, replies=replies,
                                also=also, roots=roots, limit=1)
        return got["total"] or 0

    def home_numbers(self, to, ids, *, home, kind) -> dict:
        """Each of `ids`' rank among the nodes of `kind` linked to `to` by
        `home`, in (recorded_at, seq) order: id -> number. One statement; the
        same rank `members_page` gives as `number`."""
        ids = list(dict.fromkeys(i for i in ids if i))
        if not ids:
            return {}
        rows = self._rows("""
            WITH home AS (
                SELECT DISTINCT e.id, e.seq, e.recorded_at
                FROM entry l JOIN entry e ON e.id = l.link_from
                WHERE l.link_to = ? AND l.link_relation = ?
                  AND e.family = 'entry' AND e.def_name = ?
                  AND e.link_relation IS NULL),
            numbered AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY recorded_at, seq) AS n
                FROM home)
            SELECT id, n FROM numbered
            WHERE id IN (SELECT value FROM json_each(?))""",
            (to, home, kind, json.dumps(ids)))
        return {r[0]: r[1] for r in rows}

    def reply_closure(self, root, *, replies, home, max_depth=500) -> list:
        """Every node under `root` by `replies`, at any depth and wherever it
        lives: (id, seq, recorded_at, parent, depth, home) in (recorded_at,
        seq) order. A node's FIRST `replies` link is its parent, so a node is
        in one place in the tree; `home` is the target of its first `home`
        link. Cycle-safe: a node is kept once, at its shallowest depth.

        One recursive statement down `idx_entry_link_to`, and the parent and
        home of each node read through `idx_entry_link_from`. No body."""
        rows = self._rows("""
            WITH RECURSIVE t(id, parent, depth) AS (
                SELECT ?, NULL, 0
                UNION
                SELECT l.link_from, l.link_to, t.depth + 1
                FROM t JOIN entry l ON l.link_to = t.id
                WHERE l.link_relation = ? AND t.depth < ?
                  AND l.seq = (SELECT MIN(x.seq) FROM entry x
                               WHERE x.link_from = l.link_from
                                 AND x.link_relation = ?))
            SELECT t.id, e.seq, e.recorded_at, t.parent, MIN(t.depth),
                   (SELECT h.link_to FROM entry h WHERE h.link_from = t.id
                      AND h.link_relation = ? ORDER BY h.seq LIMIT 1)
            FROM t JOIN entry e ON e.id = t.id
            WHERE t.depth > 0 AND t.id != ?
            GROUP BY t.id
            ORDER BY e.recorded_at, e.seq""",
            (root, replies, int(max_depth), replies, home, root))
        return [tuple(r) for r in rows]

    def toward_page(self, who, *, kind, home, replies, field, addressed=None,
                    before=None, limit=30) -> list[tuple]:
        """THE NODES OF `kind` THAT TURN TOWARD `who`, newest first, one page:
        (id, seq, recorded_at). A node turns toward `who` when it is not
        attributed to them and either names them in its body's list `field`,
        or an `addressed` act about them was later recorded on it (as its
        `turn`), or its `replies` link points at a node attributed to them.
        Only nodes that have a `home` link are read -- a later version of a
        node has none. `before` is a (recorded_at, seq) key, exclusive.

        COST. One statement, returning at most `limit` rows. It visits the
        nodes of `kind` through `idx_entry_definition` -- every one of them,
        since nothing indexes who a node turns toward, and sorts those that
        turn toward `who`; each visited node's `field` is read by SQLite's
        own JSON functions, its links through `idx_entry_link_from` and its
        later acts through `idx_operational_turn`. So it grows with the
        nodes of `kind` in the record, not with the page. Nothing is decoded
        in Python and no body is returned. Additive and read-only, as the
        other Fluid reads are; it knows no Kind, act or field name but the
        ones it is given."""
        if not isinstance(field, str) or not field.isidentifier():
            raise ValueError("a body field is a plain identifier")
        args = {"who": who, "kind": kind, "home": home, "replies": replies,
                "addressed": addressed, "limit": max(1, int(limit))}
        cursor = ""
        if before is not None:
            cursor = "AND (e.recorded_at, e.seq) < (:b_at, :b_seq)"
            args.update(b_at=before[0], b_seq=before[1])
        rows = self._rows(f"""
            SELECT e.id, e.seq, e.recorded_at FROM entry e
            WHERE e.def_name = :kind AND +e.family = 'entry'
              AND e.link_relation IS NULL AND e.attributed_to != :who
              {cursor}
              AND EXISTS (SELECT 1 FROM entry h WHERE h.link_from = e.id
                            AND h.link_relation = :home)
              AND (EXISTS (SELECT 1 FROM json_each(e.body, '$.{field}')
                           WHERE value = :who)
                   OR EXISTS (SELECT 1 FROM operational o
                              WHERE o.turn = e.id AND o.act = :addressed
                                AND EXISTS (SELECT 1 FROM json_each(o.about)
                                            WHERE value = :who))
                   OR EXISTS (SELECT 1 FROM entry r JOIN entry p
                                ON p.id = r.link_to
                              WHERE r.link_from = e.id
                                AND r.link_relation = :replies
                                AND p.attributed_to = :who))
            ORDER BY e.recorded_at DESC, e.seq DESC
            LIMIT :limit""", args)
        return [tuple(r) for r in rows]

    def toward_since(self, applied, *, kind, home, replies, field,
                     addressed=None) -> dict:
        """WHOM EACH NODE TURNS TOWARD, for the nodes the record touched after
        `applied`: what a derived index of `toward_page` (mentis/fluid/status)
        catches up with. One read transaction, so every answer is about one
        moment, `at`.

        `applied` is (entry seq, id of the entry at it, operational seq, id
        of the act at it) as an earlier answer's `at` gave it, or None for
        the whole record. Returned: `corpus` (the corpus id); `at`, the same
        four for the record now; `moved`, whether anything was written
        after `applied`; `foreign`, whether `applied` is not a position of
        this record any more -- past its end, or a different row stands
        there, as after a restore -- and then nothing else is read;
        `nodes`, the nodes touched (None for the whole record); `rows`,
        (who, node, seq, recorded_at, why) for each of them -- why 0 named in
        `field`, 1 `addressed` later, 2 replying to a node of theirs, the
        first that holds.

        TOUCHED is what can change a node's answer: the node itself, a
        `home` or `replies` link from it, an entry a `replies` link from it
        points at, or an `addressed` act on it (its `turn`). Each touched
        node's set is recomputed from the record with `toward_page`'s
        predicate, per person -- the same rows, never a running count.

        COST. Unmoved: one statement, of primary-key lookups only -- the
        last row of each table and the rows at `applied`. Moved: two more,
        the first walking the rows after `applied` by primary key, the
        second reading each touched node as `toward_page` reads one node.
        With `applied` None it visits every node of `kind`, as
        `toward_page` does. Read-only and additive."""
        if not isinstance(field, str) or not field.isidentifier():
            raise ValueError("a body field is a plain identifier")
        es, eid, os_, oid = applied or (0, None, 0, None)
        args = {"kind": kind, "home": home, "replies": replies,
                "addressed": addressed, "es": int(es), "os": int(os_)}
        with self._reading() as conn:
            probe = conn.execute("""
                SELECT (SELECT corpus_id FROM corpus),
                       (SELECT seq FROM entry ORDER BY seq DESC LIMIT 1),
                       (SELECT id FROM entry ORDER BY seq DESC LIMIT 1),
                       (SELECT seq FROM operational ORDER BY seq DESC LIMIT 1),
                       (SELECT id FROM operational ORDER BY seq DESC LIMIT 1),
                       (SELECT id FROM entry WHERE seq = :es),
                       (SELECT id FROM operational WHERE seq = :os)""",
                args).fetchone()
            etop, otop = probe[1] or 0, probe[3] or 0
            out = {"corpus": probe[0], "at": (etop, probe[2], otop, probe[4]),
                   "moved": False, "foreign": False, "nodes": [], "rows": []}
            if applied is not None:
                if probe[5] != eid or probe[6] != oid:
                    out["foreign"] = True
                    return out
                if (etop, otop) == (es, os_):
                    return out
            args.update(etop=etop, otop=otop)
            out["moved"] = True
            if applied is None:
                which, kind_is, nodes = "entry e", "e.def_name = :kind", None
            else:
                nodes = [r[0] for r in conn.execute("""
                    SELECT id FROM entry
                    WHERE seq > :es AND seq <= :etop AND link_relation IS NULL
                    UNION SELECT link_from FROM entry
                    WHERE seq > :es AND seq <= :etop
                      AND link_relation IN (:home, :replies)
                    UNION SELECT r.link_from FROM entry n JOIN entry r
                      ON r.link_to = n.id AND r.link_relation = :replies
                    WHERE n.seq > :es AND n.seq <= :etop
                    UNION SELECT turn FROM operational
                    WHERE seq > :os AND seq <= :otop AND act = :addressed
                      AND turn IS NOT NULL""", args)]
                out["nodes"] = nodes
                if not nodes:
                    return out
                # FROM THE LIST, by the UNIQUE id: CROSS JOIN fixes the order
                # and `+def_name` keeps SQLite off `idx_entry_definition`,
                # which it otherwise prefers -- a walk of every node of `kind`
                which = ("json_each(:nodes) k CROSS JOIN entry e "
                         "ON e.id = k.value")
                kind_is = "+e.def_name = :kind"
                args["nodes"] = json.dumps(nodes)
            out["rows"] = [tuple(r) for r in conn.execute(f"""
                WITH node AS MATERIALIZED (
                    SELECT e.id, e.seq, e.recorded_at, e.attributed_to, e.body
                    FROM {which}
                    WHERE {kind_is} AND +e.family = 'entry'
                      AND e.link_relation IS NULL AND e.seq <= :etop
                      AND EXISTS (SELECT 1 FROM entry h
                                  WHERE h.link_from = e.id
                                    AND h.link_relation = :home
                                    AND +h.seq <= :etop)),
                -- FROM EACH NODE, by its own indexes: CROSS JOIN and `+seq`
                -- keep SQLite from walking `operational` or `entry` by
                -- primary key up to the bound instead (measured: 34 ms for
                -- two nodes on the real Brain, against well under one)
                turned(id, who, why) AS (
                    SELECT n.id, j.value, 0
                    FROM node n, json_each(n.body, '$.{field}') j
                    UNION ALL
                    SELECT n.id, j.value, 1
                    FROM node n CROSS JOIN operational o
                         CROSS JOIN json_each(o.about) j
                    WHERE o.turn = n.id AND o.act = :addressed
                      AND +o.seq <= :otop
                    UNION ALL
                    SELECT n.id, p.attributed_to, 2
                    FROM node n CROSS JOIN entry r CROSS JOIN entry p
                    WHERE r.link_from = n.id AND r.link_relation = :replies
                      AND +r.seq <= :etop AND p.id = r.link_to
                      AND +p.seq <= :etop)
                SELECT t.who, t.id, n.seq, n.recorded_at, MIN(t.why)
                FROM turned t JOIN node n ON n.id = t.id
                WHERE typeof(t.who) = 'text' AND t.who != n.attributed_to
                GROUP BY t.id, t.who""", args)]
        return out

    def stream_page(self, *, kind, home, before=None, after=None,
                    limit=50) -> dict:
        """THE NODES OF `kind` THAT HAVE A `home` LINK, by record position
        (`seq`), one page: every Conversation's posts at once, each once.
        A later version of a node has no `home` link and is never a row.

        `before` / `after` are seqs, exclusive; neither is the newest page.
        Rows come newest first: (id, seq, recorded_at, home) -- `home` the
        target of the node's first `home` link. `more` says whether more
        rows lie past the page in the direction it was read; `beyond`
        whether any lie on the other side of the cursor (False with none).

        COST. One statement. It walks the primary key from the cursor --
        `+def_name` keeps SQLite off `idx_entry_definition`, which would sort
        every node of `kind` -- and stops at `limit + 1` rows; each visited
        row's `home` link is read through `idx_entry_link_from`. So it grows
        with the page and the rows between its nodes, never with how many
        nodes the record holds. No body is read."""
        limit = max(1, int(limit))
        args = {"kind": kind, "home": home, "limit": limit + 1}
        is_node = """+{a}.def_name = :kind AND +{a}.family = 'entry'
              AND {a}.link_relation IS NULL
              AND EXISTS (SELECT 1 FROM entry h WHERE h.link_from = {a}.id
                            AND h.link_relation = :home)"""
        cursor, direction, beyond = "", "DESC", "0"
        if before is not None:
            cursor = "AND e.seq < :edge"
            beyond = (f"EXISTS (SELECT 1 FROM entry x WHERE x.seq >= :edge "
                      f"AND {is_node.format(a='x')} ORDER BY x.seq)")
            args["edge"] = int(before)
        elif after is not None:
            cursor, direction = "AND e.seq > :edge", "ASC"
            beyond = (f"EXISTS (SELECT 1 FROM entry x WHERE x.seq <= :edge "
                      f"AND {is_node.format(a='x')} ORDER BY x.seq DESC)")
            args["edge"] = int(after)
        rows = self._rows(f"""
            SELECT e.id, e.seq, e.recorded_at,
                   (SELECT h.link_to FROM entry h WHERE h.link_from = e.id
                      AND h.link_relation = :home ORDER BY h.seq LIMIT 1),
                   (SELECT {beyond})
            FROM entry e
            WHERE {is_node.format(a='e')} {cursor}
            ORDER BY e.seq {direction}
            LIMIT :limit""", args)
        rows = [tuple(r) for r in rows]
        more = len(rows) > limit
        out = rows[:limit]
        if direction == "ASC":
            out.reverse()
        return {"rows": [r[:4] for r in out], "more": more,
                "beyond": bool(rows[0][4]) if rows else False}

    # -- portability --------------------------------------------------------

    def snapshot(self, path: str):
        """A consistent single-file copy of a LIVE corpus.

        SQLite's own backup, so it is safe while writers are active and it
        never leaves a `-wal` the destination depends on. This is the answer to
        "copy the corpus somewhere else" -- copying the files by hand while the
        corpus is open is not.
        """
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        dest = sqlite3.connect(path)
        try:
            with self._lock, dest:
                self._conn.backup(dest)
        finally:
            dest.close()

    def close(self):
        """Clean close: checkpoint, then close.

        SQLite removes `-wal` and `-shm` itself when the LAST connection to a
        database closes cleanly, so after the last close the corpus really is
        one file that can be copied, zipped, emailed or put on a stick.

        This deliberately does NOT switch journal mode back to DELETE. Doing so
        needs an exclusive lock, and a corpus with another writer still working
        in it cannot grant one -- measured: the other writer failed outright
        with "database is locked". Tidying one connection's exit is not worth
        breaking somebody else's write.
        """
        # The reading connections first, so the writer's is the last one and
        # its clean close is what removes `-wal` and `-shm`. One still in use
        # is closed by its reader when it is handed back.
        with self._idle_lock:
            self._closed = True
            idle, self._idle = self._idle, []
        for conn in idle:
            conn.close()
        with self._lock:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass                # another connection is busy; harmless
            self._conn.close()
        if self._open_lock is not None:
            self._open_lock.release()


def _dump(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _flatten(record: dict) -> dict:
    d = record.get("definition") or {}
    link = record.get("link") or {}
    return {
        "id": record["id"], "family": record["family"],
        "def_name": d.get("name"), "def_version": d.get("version"),
        "body": _dump(record["body"]),
        "attributed_to": record["attributed_to"],
        "written_by": record.get("written_by"),
        "recorded_at": record["recorded_at"],
        "origin": record.get("origin"),
        "link_from": link.get("from"), "link_to": link.get("to"),
        "link_relation": link.get("relation"),
        "link_relation_version": link.get("relation_version"),
    }


def _act_of(row) -> tuple:
    """One operational row as (seq, act): the act as every reader gets it."""
    d = dict(row)
    seq = d.pop("seq", None)
    # Integrity metadata, not content. A reader asking what happened
    # is asking about the act; the chain is how the record shows it
    # has not been edited, and `verify_chain` reads it directly.
    d.pop("prev_hash", None)
    d.pop("hash", None)
    d["about"] = json.loads(d["about"])
    d["detail"] = json.loads(d["detail"])
    return seq, d


def _inflate(row) -> dict:
    definition = None
    if row["def_name"] is not None:
        definition = {"name": row["def_name"], "version": row["def_version"]}
    link = None
    if row["link_relation"] is not None:
        link = {"from": row["link_from"], "to": row["link_to"],
                "relation": row["link_relation"],
                "relation_version": row["link_relation_version"]}
    return {
        "id": row["id"], "family": row["family"], "definition": definition,
        "body": json.loads(row["body"]), "attributed_to": row["attributed_to"],
        "written_by": row["written_by"], "recorded_at": row["recorded_at"],
        "origin": row["origin"], "link": link,
    }
