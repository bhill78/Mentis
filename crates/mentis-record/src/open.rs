//! Opening a Brain, the class pools, and the one place a connection is opened.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, MutexGuard, PoisonError};
use std::time::Instant;

use rusqlite::Connection;

use crate::lock::{NotTaken, OpenLock};
use crate::scope::{Clock, Reaper, Scope};
use crate::{
    BrainOpener, CORPUS_DB, OPEN_FLAGS, OPEN_LOCK, OPEN_PRAGMAS, OpenRefused, RESTORING, ReadClass,
    ReadScope, RecordError, RecordReader,
};

/// The `schema_migration` rows this build reads: id and checksum, in order.
/// `tests/ledger_names.rs` holds this to Python's `migrations` list, so a Python migration can't
/// pass unnoticed.
pub const LEDGER: &[(&str, &str)] = &[
    (
        "0001-adopt",
        "d33bb0262da6f313f2f8b859a1ccc3f610773f9e75cdd91b2948e214cf3c39bb",
    ),
    // Attested erasure and the reference index (`erasure-design.md`), additive, min_reader 2.
    (
        "0002-erasure",
        "b63e365b2978a121f7d26a1dc4040860f3ba56a01a06948d001df0721beddeae",
    ),
];

/// Each class's cap on open scopes: the one table of them. Foreground and Agent each take what
/// `spine/store.py`'s readers keep idle (`_IDLE_READERS`). Only Foreground is exercised in R1.
pub const READER_CAPS: [(ReadClass, usize); 4] = [
    (ReadClass::Foreground, 8),
    (ReadClass::Agent, 8),
    (ReadClass::Background, 2),
    (ReadClass::Connector, 2),
];

/// VM steps between looks at the clock (`contracts/record.md`).
const PROGRESS_EVERY: i32 = 1000;

/// Every connection in this crate is opened here, and nowhere else.
fn open_connection(db: &Path) -> rusqlite::Result<Connection> {
    let conn = Connection::open_with_flags(db, OPEN_FLAGS)?;
    #[cfg(feature = "sql-trace")]
    let conn = crate::trace::switched_on(conn)?;
    conn.execute_batch(OPEN_PRAGMAS)?;
    Ok(conn)
}

/// A connection, with the clock its progress handler watches.
pub(crate) struct Pooled {
    pub(crate) conn: Connection,
    pub(crate) clock: Arc<Clock>,
}

#[derive(Default)]
struct PoolState {
    in_use: usize,
    idle: Vec<Pooled>,
}

/// What a reader and its scopes share. The lock goes when the last of them does, so no connection
/// outlives the hold on `.mentis.lock`.
pub(crate) struct Shared {
    db: PathBuf,
    epoch: Instant,
    pools: [Mutex<PoolState>; READER_CAPS.len()],
    opened: AtomicUsize,
    _lock: OpenLock,
}

fn index_of(class: ReadClass) -> usize {
    READER_CAPS
        .iter()
        .position(|(c, _)| *c == class)
        .expect("every class is in the table")
}

fn name_of(class: ReadClass) -> &'static str {
    match class {
        ReadClass::Foreground => "foreground",
        ReadClass::Agent => "agent",
        ReadClass::Background => "background",
        ReadClass::Connector => "connector",
    }
}

impl Shared {
    fn pool(&self, class: ReadClass) -> MutexGuard<'_, PoolState> {
        self.pools[index_of(class)]
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
    }

    fn connect(&self) -> rusqlite::Result<Pooled> {
        let mut conn = open_connection(&self.db)?;
        let clock = Arc::new(Clock::new(self.epoch));
        let watching = Arc::clone(&clock);
        conn.progress_handler(PROGRESS_EVERY, Some(move || watching.passed()))?;
        self.opened.fetch_add(1, Ordering::Relaxed);
        Ok(Pooled { conn, clock })
    }

    /// A place in `class`'s pool, and a connection to go with it.
    pub(crate) fn take(&self, class: ReadClass) -> Result<Pooled, RecordError> {
        let held = {
            let mut pool = self.pool(class);
            if pool.in_use >= READER_CAPS[index_of(class)].1 {
                return Err(RecordError::Busy {
                    class: name_of(class),
                });
            }
            pool.in_use += 1;
            pool.idle.pop()
        };
        match held {
            Some(pooled) => Ok(pooled),
            None => self.connect().map_err(|error| {
                self.release(class, None);
                RecordError::Sqlite {
                    detail: error.to_string(),
                }
            }),
        }
    }

    /// Gives up a place, and the connection with it unless it is in any doubt.
    pub(crate) fn release(&self, class: ReadClass, back: Option<Pooled>) {
        let mut pool = self.pool(class);
        pool.in_use -= 1;
        if let Some(pooled) = back {
            pool.idle.push(pooled);
        }
    }
}

/// A Brain opened for reading.
pub struct Reader {
    shared: Arc<Shared>,
    reaper: Arc<Reaper>,
    corpus_id: String,
    /// The Brain's directory, whose deletion ledger is checked again whenever it changes.
    root: PathBuf,
    gate: Mutex<Gate>,
}

/// THE LEDGER GATE (Python's `Store.ledger_gate`, round 5): the ledger and its erase sets as last
/// checked, and what that check said. A scope is only begun after the ledger is seen unchanged
/// since a check that passed, so content a deletion took is never read again once the ledger
/// says it was taken. Stat only, while nothing changes.
#[derive(Default)]
struct Gate {
    seen: Option<crate::deletions::Signature>,
    refused: Option<String>,
}

impl Reader {
    /// Connections waiting in `class`'s pool. What a test can see of a return to the pool.
    pub fn idle_connections(&self, class: ReadClass) -> usize {
        self.shared.pool(class).idle.len()
    }

    /// Connections opened so far, in every class.
    pub fn connections_opened(&self) -> usize {
        self.shared.opened.load(Ordering::Relaxed)
    }
}

impl RecordReader for Reader {
    fn read_scope(&self, class: ReadClass) -> Result<Box<dyn ReadScope>, RecordError> {
        self.ledger_gate()?;
        let scope = Scope::begin(Arc::clone(&self.shared), &self.reaper, class)?;
        Ok(Box::new(scope))
    }

    fn corpus_id(&self) -> &str {
        &self.corpus_id
    }
}

impl Reader {
    /// The ledger gate: when the ledger or its erase sets changed since they were last checked,
    /// check them again (on a connection of its own), and refuse every scope while they list a
    /// deletion this Brain does not hold.
    fn ledger_gate(&self) -> Result<(), RecordError> {
        let now = crate::deletions::signature(&self.root);
        let mut gate = self.gate.lock().unwrap_or_else(PoisonError::into_inner);
        if gate.seen.as_ref() != Some(&now) {
            let conn = open_connection(&self.shared.db).map_err(|error| RecordError::Sqlite {
                detail: error.to_string(),
            })?;
            gate.refused = crate::deletions::problems(&conn, &self.root, &self.corpus_id);
            gate.seen = Some(now);
        }
        match &gate.refused {
            Some(detail) => Err(RecordError::DeletionsNotHeld {
                detail: detail.clone(),
            }),
            None => Ok(()),
        }
    }
}

impl Drop for Reader {
    fn drop(&mut self) {
        self.reaper.close();
    }
}

/// The opener: `Brain::open(root)`.
pub struct Brain;

impl BrainOpener for Brain {
    type Reader = Reader;

    fn open(root: &Path) -> Result<Reader, OpenRefused> {
        let shown = || root.display().to_string();
        let db = root.join(CORPUS_DB);
        if !db.is_file() {
            return Err(OpenRefused::Missing { root: shown() });
        }
        if root.join(RESTORING).exists() {
            return Err(OpenRefused::Restoring { root: shown() });
        }
        let lock = OpenLock::shared(root).map_err(|why| match why {
            NotTaken::Exclusive => OpenRefused::Exclusive { root: shown() },
            NotTaken::Failed(error) => OpenRefused::Unreadable {
                detail: format!("{OPEN_LOCK}: {error}"),
            },
        })?;
        let shared = Arc::new(Shared {
            db,
            epoch: Instant::now(),
            pools: Default::default(),
            opened: AtomicUsize::new(0),
            _lock: lock,
        });
        let first = shared.connect().map_err(unreadable)?;
        check_ledger(&first.conn)?;
        let corpus_id: String = first
            .conn
            .query_row("SELECT corpus_id FROM corpus", [], |row| row.get(0))
            .map_err(|error| OpenRefused::UnsupportedSchema {
                detail: format!("it has no corpus identity: {error}"),
            })?;
        // A Brain restored from before a permanent deletion its ledger lists is not served.
        let seen = crate::deletions::signature(root);
        if let Some(detail) = crate::deletions::problems(&first.conn, root, &corpus_id) {
            return Err(OpenRefused::DeletionsNotHeld { detail });
        }
        shared.pool(ReadClass::Foreground).idle.push(first);
        let reaper = Reaper::start();
        #[cfg(feature = "row-h-probe")]
        crate::probe::start(Arc::downgrade(&shared), Arc::clone(&reaper));
        Ok(Reader {
            shared,
            reaper,
            corpus_id,
            root: root.to_path_buf(),
            gate: Mutex::new(Gate {
                seen: Some(seen),
                refused: None,
            }),
        })
    }
}

fn unreadable(error: rusqlite::Error) -> OpenRefused {
    OpenRefused::Unreadable {
        detail: error.to_string(),
    }
}

fn check_ledger(conn: &Connection) -> Result<(), OpenRefused> {
    let tables: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'schema_migration'",
            [],
            |row| row.get(0),
        )
        .map_err(unreadable)?;
    if tables == 0 {
        return Err(OpenRefused::UnsupportedSchema {
            detail: "it has no schema ledger".to_string(),
        });
    }
    let mut rows = conn
        .prepare("SELECT id, checksum FROM schema_migration ORDER BY seq")
        .map_err(unreadable)?;
    let found: Vec<(String, String)> = rows
        .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))
        .map_err(unreadable)?
        .collect::<Result<_, _>>()
        .map_err(unreadable)?;
    let same = found.len() == LEDGER.len()
        && found
            .iter()
            .zip(LEDGER)
            .all(|((id, sum), (want_id, want_sum))| id == want_id && sum == want_sum);
    if same {
        return Ok(());
    }
    let ids: Vec<&str> = found.iter().map(|(id, _)| id.as_str()).collect();
    let named: Vec<&str> = LEDGER.iter().map(|(id, _)| *id).collect();
    Err(OpenRefused::UnsupportedSchema {
        detail: format!(
            "its ledger holds {ids:?}, and this build names {named:?} with their checksums"
        ),
    })
}
