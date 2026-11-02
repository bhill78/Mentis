# Contract: reading the record

Code: `crates/mentis-record/src/lib.rs`. P1.1 implements these traits and the rest of the workspace programs against them. The traits only gain: new methods with defaults, new variants of `#[non_exhaustive]` enums.

## Rules that hold until the first Rust write (R7)

- **Rust never writes the Brain:** not `corpus.db`, `artifacts/`, `instances/`, `presentation/` or `mentis-corpus.json`.
- **`corpus.db*` is opened only through SQLite.** Closing any other handle on it drops SQLite's POSIX locks. P1.1 adds a source check that fails the build's tests on any other open.
- **Only `mentis-record` depends on `rusqlite`.** Nothing else can reach a connection.

## Opening

`BrainOpener::open(root)` returns a `RecordReader`, or refuses in words, first match wins:

| Order | Condition | Refusal | Python's equivalent |
|---|---|---|---|
| 1 | No `corpus.db` | `Missing` | `BrainMissing`, `spine/migrations.py:829` |
| 2 | `.mentis.restoring` exists | `Restoring` | `refuse_if_restoring`, `spine/brainlock.py:165` |
| 3 | `.mentis.lock` held exclusive | `Exclusive` | `brainlock.shared`, `:177` |
| 4 | A ledger this build doesn't name | `UnsupportedSchema` | `migrations.inspect` |

**Locks.** Hold `.mentis.lock` shared, by the same OS lock and byte range as `spine/brainlock.py:77-81` (`LockFileEx`, one byte at offset 0) and `flock` on POSIX, for the reader's whole life. It releases on death. Never touch `.mentis.serve.lock` or `.mentis.serve.json`: those are Python's, and the second-server refusal stays Python's.

**The ledger.** A build names the `schema_migration` rows it reads: id and checksum, in order. A test in P1.1 generates that list from Python's `migrations` list and fails when they differ, so a Python migration can't pass unnoticed. Python's migrate takes `.mentis.lock` exclusive, so it refuses while a front is up: a schema can't change under a running front.

**Every connection:** `OPEN_FLAGS` and `OPEN_PRAGMAS` (`SQLITE_OPEN_READ_ONLY`, `query_only=ON`, `busy_timeout=5000`, as `spine/store.py:307-314`), never `immutable`. The bundled SQLite is 3.54.1; Python's is 3.49.1. `R1-acceptance.md` row H has the report to make of that.

**Sidecars.** `SQLITE_OPEN_READ_ONLY` covers `corpus.db`, not SQLite's WAL files: without `immutable`, a reader needs the shared memory index. So on a Brain with neither, opening makes SQLite create `corpus.db-shm` (32,768 bytes here) and an empty `corpus.db-wal`, and closing leaves them, because a read-only connection can't remove them. Python's own `mode=ro` connections do the same. `corpus.db` doesn't change, a reader adds no frame to `-wal`, and SQLite updates `-shm` as readers come and go. The next read-write connection to close last removes both. These two files are the only thing a front adds to a Brain besides the lock file. They stay SQLite's: no Rust code opens, removes or reads them by name.

## The read scope

`RecordReader::read_scope(class)` returns one connection, one read transaction, one position, for one operation.

| Moment | What happens |
|---|---|
| Class at its cap | `RecordError::Busy`, at once. Never queued behind another class |
| Open | `BEGIN`, then `SELECT` the three `MAX(seq)` (`spine/store.py:1137-1143`) as one statement: that **fixes the snapshot and the position together** |
| Wait for a snapshot | At most `BUSY_TIMEOUT` (5 s), then an error. It isn't part of the 2 s, because nothing is pinned until the snapshot exists. Readers meet this only during WAL recovery or an exclusive lock |
| From the snapshot | **`READ_SCOPE_LIMIT`, 2 s** |
| A statement running at 2 s | Ended by the progress handler, every 1,000 VM steps: `ScopeExpired` |
| **Nothing running at 2 s** | The progress handler can't see an idle transaction, and an idle transaction pins the WAL just as well. So one reaper thread per reader takes the expired scope's connection and ends its transaction. The next call on that scope answers `ScopeExpired` |
| Ended | `READ_SCOPE_ENDED_WITHIN`, 2.5 s from the snapshot, always (row H2) |
| Drop | `COMMIT`, then the connection goes back to its class's pool. A connection in any doubt is closed instead |

**Using a scope.**

- **It blocks,** so it runs on a blocking thread and never on a tokio worker. `Send`, not `Sync`.
- **`position()` is the route's change cursor.** It costs no statement after opening, and nobody asks a second time. That retires the double `advance` per Fluid read (census, `op-position`).
- **`query` takes `&'static str`.** A statement is text in the source. A list of ids is one `Text` parameter holding a JSON array, read with `json_each(?1)`.
- **`statements()`** is what budgets are tested against, with the position's statement counted. P1.4's SQL trace is the independent check.
- **Don't hold a lock across a statement,** and don't do slow work between statements. The limit won't wait for you, and the reader doesn't get a longer one.

**Classes.** `Foreground`, `Agent`, `Background`, `Connector`, each with its own pool and cap, in one table in `mentis-record`. P1.1 sets the sizes; R1 exercises only `Foreground`.

## Position

`Position` is `Store.advance`'s three numbers in its order: `entry`, `operational`, `delivery`. It displays and parses as `a.b.c`, the durable half of a pulse token. The parse is strict. What a route does with a malformed `since` is that route's, and `web/moved.py:114` says what Python does.

## The chain verifier

`ChainVerifier::verify_chains` uses the normative codec in `R1-acceptance.md`, section G, reading many scopes in `seq` order, each within the limit, so a whole-Brain verification can't pin the WAL. It answers per table: rows, head, the first `seq` that doesn't follow. It must agree with Python's `verify_chain` over the whole `BRAIN-COPY`.

## Errors and what they become

| Error | At a door |
|---|---|
| `Busy` | `OpError::Busy` |
| `ScopeExpired` | `OpError::Record`, then 503 with the reason. Never a partial answer unless the op promised one |
| `Sqlite` | `OpError::Record`, then 500 with SQLite's words, as Python's routes answer exceptions |
