//! The Brain, read only. Contract: `docs/rust/contracts/record.md`.
//!
//! The traits are frozen for R1's packages: a later release may add methods with defaults and
//! new variants of the `#[non_exhaustive]` enums, and may not change what is here. P1.1
//! implements them, in the modules below. Only this crate may depend on `rusqlite`, and nothing in
//! the workspace opens `corpus.db*` except through SQLite.

mod chain;
mod deletions;
mod lock;
mod open;
#[cfg(feature = "row-h-probe")]
mod probe;
mod scope;
#[cfg(feature = "sql-trace")]
mod trace;

pub use chain::{
    Chains, CodecRefused, DELETION_ACT, canonical, erasure_digest, erasure_marker,
    is_erasure_marker, python_float, row_hash, sha256_hex,
};
pub use deletions::{LEDGER_SUFFIX, ledger_path};
pub use open::{Brain, LEDGER, READER_CAPS, Reader};

use std::fmt;
use std::path::Path;
use std::str::FromStr;
use std::time::Duration;

/// How long a read scope may hold its snapshot, from the moment the snapshot exists.
pub const READ_SCOPE_LIMIT: Duration = Duration::from_secs(2);

/// A read past [`READ_SCOPE_LIMIT`] is ended within this, measured from the snapshot
/// (appendix A, `H`: a stuck reader).
pub const READ_SCOPE_ENDED_WITHIN: Duration = Duration::from_millis(2500);

/// `PRAGMA busy_timeout` on every connection, matching `spine/store.py`'s readers. It bounds the
/// wait for a snapshot, which is not part of [`READ_SCOPE_LIMIT`]: nothing is pinned until the
/// snapshot exists.
pub const BUSY_TIMEOUT: Duration = Duration::from_millis(5000);

/// How a connection is opened, in full. No connection in this crate is opened any other way.
pub const OPEN_FLAGS: rusqlite::OpenFlags = rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY
    .union(rusqlite::OpenFlags::SQLITE_OPEN_NO_MUTEX)
    .union(rusqlite::OpenFlags::SQLITE_OPEN_EXRESCODE);

/// Run on each connection straight after opening. `immutable` is never used: the Brain is live.
pub const OPEN_PRAGMAS: &str = "PRAGMA query_only=ON; PRAGMA busy_timeout=5000;";

/// The Brain's files this crate reads by name. Lock files are opened for locking only.
pub const CORPUS_DB: &str = "corpus.db";
pub const OPEN_LOCK: &str = ".mentis.lock";
pub const RESTORING: &str = ".mentis.restoring";

/// An entry, operational act or delivery id (`ent-`, `opr-`, ... + 12 hex). Never parsed for
/// meaning here: an id the record does not hold is simply absent from an answer.
#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Id(pub String);

impl fmt::Display for Id {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

/// How far the record has got: the greatest visible `seq` of `entry`, `operational` and
/// `delivery`, or zero (`Store.advance`, `spine/store.py:1121`). Something to compare, not a
/// clock. Formats and parses as `"<entry>.<operational>.<delivery>"`, the durable half of a pulse
/// token.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub struct Position {
    pub entry: u64,
    pub operational: u64,
    pub delivery: u64,
}

impl fmt::Display for Position {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}.{}.{}", self.entry, self.operational, self.delivery)
    }
}

/// Not three unsigned decimal fields.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BadPosition;

impl FromStr for Position {
    type Err = BadPosition;

    fn from_str(s: &str) -> Result<Self, BadPosition> {
        let mut fields = s.split('.').map(|part| {
            if part.is_empty() || !part.bytes().all(|b| b.is_ascii_digit()) {
                return Err(BadPosition);
            }
            part.parse::<u64>().map_err(|_| BadPosition)
        });
        let position = Position {
            entry: fields.next().ok_or(BadPosition)??,
            operational: fields.next().ok_or(BadPosition)??,
            delivery: fields.next().ok_or(BadPosition)??,
        };
        if fields.next().is_some() {
            return Err(BadPosition);
        }
        Ok(position)
    }
}

/// Who a read is for. Each class has its own reader pool and cap, so one class cannot queue
/// another; sizes are P1.1's, in one table, and only `Foreground` is exercised in R1.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ReadClass {
    /// Fluid, on behalf of the person looking at it.
    Foreground,
    /// An agent's read through the door.
    Agent,
    /// Magnets and the palette.
    Background,
    /// Connectors.
    Connector,
}

/// A value bound to a statement. A list of ids is one statement with one `Text` parameter holding
/// a JSON array, read through `json_each(?1)`, so a statement count never grows with the ids.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Param<'a> {
    Null,
    Integer(i64),
    Real(f64),
    Text(&'a str),
}

/// A column as SQLite holds it. `Text` is bytes because that is what is stored; the chain
/// verifier hashes them as stored and [`Value::text`] is for everything else.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Value<'a> {
    Null,
    Integer(i64),
    Real(f64),
    Text(&'a [u8]),
    Blob(&'a [u8]),
}

impl<'a> Value<'a> {
    /// The text of a `Text` value, `None` for any other type or for bytes that are not UTF-8.
    pub fn text(self) -> Option<&'a str> {
        match self {
            Value::Text(bytes) => std::str::from_utf8(bytes).ok(),
            _ => None,
        }
    }

    pub fn integer(self) -> Option<i64> {
        match self {
            Value::Integer(n) => Some(n),
            _ => None,
        }
    }
}

/// One row, valid only inside the call that receives it.
pub trait Row {
    fn column_count(&self) -> usize;
    /// `Err(RecordError::NoSuchColumn)` past the end.
    fn value(&self, column: usize) -> Result<Value<'_>, RecordError>;
}

/// What a row callback tells the scope.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Flow {
    Continue,
    /// Stop reading this statement's rows; the scope stays open.
    Stop,
}

/// One connection, one read transaction, one position, for one operation.
///
/// **Blocking.** A scope runs on a blocking thread and never on a tokio worker. `Send` so it can
/// be moved to one; not `Sync`, because a scope serves one operation at a time.
pub trait ReadScope: Send {
    /// The position this scope reads at, read once as the statement that fixed the snapshot.
    /// A route's change cursor is this value; nobody asks a second time.
    fn position(&self) -> Position;

    /// Run one statement, calling `each` per row.
    ///
    /// `sql` is `'static` on purpose: a statement is text in the source, so its count is fixed by
    /// the code and a statement cannot be built from a request. Ends in
    /// [`RecordError::ScopeExpired`] once the scope's limit has passed, whether or not a statement
    /// was running. A statement that would write is refused by SQLite and surfaces as
    /// [`RecordError::Sqlite`].
    fn query(
        &mut self,
        sql: &'static str,
        params: &[Param<'_>],
        each: &mut dyn FnMut(&dyn Row) -> Result<Flow, RecordError>,
    ) -> Result<(), RecordError>;

    /// How many statements this scope has run, position's included. What a budget is checked
    /// against in tests; never a reason to behave differently.
    fn statements(&self) -> u32;
}

/// A Brain opened for reading, holding `.mentis.lock` shared for as long as it lives.
pub trait RecordReader: Send + Sync + 'static {
    /// A new scope in `class`'s pool. Fails fast with [`RecordError::Busy`] when that class is at
    /// its cap: a read is never queued behind another class, and the caller answers rather than
    /// waits. Blocks for at most [`BUSY_TIMEOUT`] for SQLite to give it a snapshot.
    fn read_scope(&self, class: ReadClass) -> Result<Box<dyn ReadScope>, RecordError>;

    /// Durable identity, `corpus.corpus_id`. It moves with the corpus, unlike the path.
    fn corpus_id(&self) -> &str;
}

/// Opening a Brain. The one way to get a [`RecordReader`].
pub trait BrainOpener {
    type Reader: RecordReader;

    /// In order, refusing with the first that applies: no `corpus.db` ([`OpenRefused::Missing`]);
    /// `.mentis.restoring` exists ([`OpenRefused::Restoring`]); `.mentis.lock` held exclusive
    /// ([`OpenRefused::Exclusive`]); a ledger this build does not name
    /// ([`OpenRefused::UnsupportedSchema`]). Creates the empty lock file a guarded opener creates
    /// today, and SQLite creates `corpus.db-shm` and an empty `corpus.db-wal` if they are missing,
    /// and leaves them on close, as for any reader of a WAL database: `contracts/record.md`. Writes
    /// nothing to `corpus.db`, and never touches `.mentis.serve.lock`, which is Python's.
    fn open(root: &Path) -> Result<Self::Reader, OpenRefused>;
}

/// Why the Brain was not opened, in words for the person starting the front.
#[derive(Clone, Debug, PartialEq, Eq)]
#[non_exhaustive]
pub enum OpenRefused {
    Missing {
        root: String,
    },
    Restoring {
        root: String,
    },
    Exclusive {
        root: String,
    },
    UnsupportedSchema {
        detail: String,
    },
    /// Past the four above: the lock file or the database could not be read at all.
    Unreadable {
        detail: String,
    },
    /// The deletion ledger beside the Brain lists permanent deletions this Brain does not hold:
    /// it was restored from before them (`deletions.rs`).
    DeletionsNotHeld {
        detail: String,
    },
}

impl fmt::Display for OpenRefused {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            OpenRefused::Missing { root } => write!(f, "no Brain at {root}"),
            OpenRefused::Restoring { root } => {
                write!(f, "the Brain at {root} is being restored")
            }
            OpenRefused::Exclusive { root } => {
                write!(
                    f,
                    "the Brain at {root} is held by migrate, reconcile or restore"
                )
            }
            OpenRefused::UnsupportedSchema { detail } => {
                write!(f, "this build does not read this Brain's schema: {detail}")
            }
            OpenRefused::Unreadable { detail } => {
                write!(f, "the Brain could not be read: {detail}")
            }
            OpenRefused::DeletionsNotHeld { detail } => f.write_str(detail),
        }
    }
}

impl std::error::Error for OpenRefused {}

/// A read that did not produce an answer. Nothing here means the record changed.
#[derive(Clone, Debug, PartialEq, Eq)]
#[non_exhaustive]
pub enum RecordError {
    /// The class is at its cap. Nothing ran.
    Busy { class: &'static str },
    /// The scope's limit passed. Its snapshot has been released.
    ScopeExpired,
    /// A row callback asked for a column past the end.
    NoSuchColumn { column: usize },
    /// SQLite's own words.
    Sqlite { detail: String },
    /// A chained row holds a value the codec refuses (section G): a non-finite float, or text
    /// that is not UTF-8. Reported rather than hashed, so it is never silently accepted.
    ChainRefused {
        table: &'static str,
        seq: u64,
        detail: String,
    },
}

impl fmt::Display for RecordError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            RecordError::Busy { class } => write!(f, "the {class} readers are all in use"),
            RecordError::ScopeExpired => f.write_str("the read ran past its limit and was ended"),
            RecordError::NoSuchColumn { column } => write!(f, "no column {column}"),
            RecordError::Sqlite { detail } => write!(f, "SQLite: {detail}"),
            RecordError::ChainRefused { table, seq, detail } => {
                write!(f, "{table} row {seq} cannot be verified: {detail}")
            }
        }
    }
}

impl std::error::Error for RecordError {}

/// The chained tables, in `Store.CHAINED`'s order of statement (`spine/store.py:553`).
pub const CHAINED_TABLES: [&str; 3] = ["entry", "operational", "delivery"];

/// One table's result. Field for field what Python's verifier reports (appendix A, `G`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TableChain {
    pub table: &'static str,
    pub rows: u64,
    /// The last row's hash, `None` for an empty table.
    pub head: Option<String>,
    /// The first row that does not follow, `None` when the table verifies.
    pub broke_at_seq: Option<u64>,
    /// Rows accepted as attested erasures (`erasure-design.md` 1.4), and pre-chain rows that hold
    /// the marker of their erasure row: Python's `streams[table]["erased"]`.
    pub erased: u64,
    /// Rows whose hash followed, erased ones included: Python's `chained`.
    pub chained: u64,
    /// Unhashed rows before the chain began: Python's `before_the_chain`.
    pub before_the_chain: u64,
    /// The break, as Python's `broken_at` says it: `seq`, `id` and why.
    pub broken_at: Option<ChainBreak>,
}

/// Where a table's chain breaks, and why, in Python's words.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ChainBreak {
    pub seq: u64,
    pub id: Option<String>,
    pub why: &'static str,
}

/// What the `erasure` table and its `conversation-deleted` acts come to (`erasure-design.md` 1.4:
/// Python's `verify_chain()["erasures"]`, zeros without the table).
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Erasures {
    /// `conversation-deleted` acts in the record.
    pub acts: u64,
    /// Erasure rows.
    pub rows: u64,
    /// Attested rows whose hash still recomputes: a deletion not completed.
    pub pending: u64,
    /// The first erasure that does not account for itself, `None` when they all do.
    pub broken: Option<ErasureBroken>,
}

/// Why the erasures do not verify: Python's `{"deletion", "why"}` or `{"table", "id", "why"}`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ErasureBroken {
    Act {
        deletion: String,
        why: &'static str,
    },
    Row {
        table: String,
        id: String,
        why: &'static str,
    },
}

impl ErasureBroken {
    pub fn why(&self) -> &'static str {
        match self {
            ErasureBroken::Act { why, .. } | ErasureBroken::Row { why, .. } => why,
        }
    }
}

/// The whole verify: each table, and the erasures.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ChainReport {
    pub tables: Vec<TableChain>,
    pub erasures: Erasures,
    /// `corpus.chained_from_first`, Python's `chained_from_first_row`.
    pub chained_from_first_row: bool,
}

impl ChainReport {
    /// Python's `intact`: no table breaks and the erasures account for themselves.
    pub fn intact(&self) -> bool {
        self.erasures.broken.is_none() && self.tables.iter().all(|t| t.broke_at_seq.is_none())
    }
}

/// Verifying the chains read-only, to the normative codec in `docs/rust/R1-acceptance.md`, `G`.
pub trait ChainVerifier {
    /// Runs over many scopes as needed, each within [`READ_SCOPE_LIMIT`]: a whole-Brain verify
    /// must not pin the WAL. So it reads in `seq` order from where the last scope stopped, and
    /// the result is as at the first scope's position, with rows past it left unread.
    fn verify_chains(&self, reader: &dyn RecordReader) -> Result<Vec<TableChain>, RecordError>;

    /// The tables and the erasures together. A verifier that knows nothing of erasures reports
    /// none.
    fn verify_report(&self, reader: &dyn RecordReader) -> Result<ChainReport, RecordError> {
        Ok(ChainReport {
            tables: self.verify_chains(reader)?,
            erasures: Erasures::default(),
            chained_from_first_row: false,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn position_is_the_durable_half_of_a_pulse_token() {
        let at = Position {
            entry: 86012,
            operational: 41,
            delivery: 7,
        };
        assert_eq!(at.to_string(), "86012.41.7");
        assert_eq!("86012.41.7".parse(), Ok(at));
    }

    #[test]
    fn a_position_is_exactly_three_unsigned_fields() {
        for bad in [
            "", "1", "1.2", "1.2.3.4", "1..3", "+1.2.3", "-1.2.3", " 1.2.3", "1.2.x",
        ] {
            assert_eq!(bad.parse::<Position>(), Err(BadPosition), "{bad:?}");
        }
    }

    #[test]
    fn a_value_is_text_only_when_it_is_text_and_utf8() {
        assert_eq!(Value::Text(b"name").text(), Some("name"));
        assert_eq!(Value::Text(b"\xff").text(), None);
        assert_eq!(Value::Blob(b"name").text(), None);
        assert_eq!(Value::Integer(3).integer(), Some(3));
        assert_eq!(Value::Null.integer(), None);
    }
}
