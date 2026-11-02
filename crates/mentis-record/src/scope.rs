//! The read scope: one connection, one read transaction, one position, ended at its limit.
//!
//! A snapshot pins the WAL for as long as it is held, whatever the holder is doing, so the limit
//! has to hold in three states:
//!
//! - **SQLite is running a statement:** the progress handler interrupts it.
//! - **Nothing is running:** the reaper takes the connection and ends the transaction.
//! - **A row callback is running:** the statement is open and SQLite isn't. So no row reaches a
//!   callback as a reference into SQLite, and the gate is not held across the callback. The reaper
//!   ends the transaction there too, and query answers ScopeExpired when the callback returns.

use std::cell::RefCell;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Condvar, Mutex, MutexGuard, PoisonError, TryLockError, Weak};
use std::thread;
use std::time::{Duration, Instant};

use rusqlite::types::ValueRef;
use rusqlite::{Connection, ErrorCode, ffi};

use crate::open::{Pooled, Shared};
use crate::{
    Flow, Param, Position, READ_SCOPE_LIMIT, ReadClass, ReadScope, RecordError, Row, Value,
};

/// The position's statement: three aggregates as one, so one snapshot fixes all three.
/// `Store.advance`'s numbers (`spine/store.py:1137-1143`).
const POSITION: &str = "SELECT (SELECT COALESCE(MAX(seq), 0) FROM entry), \
                        (SELECT COALESCE(MAX(seq), 0) FROM operational), \
                        (SELECT COALESCE(MAX(seq), 0) FROM delivery)";

/// How soon the reaper looks again at a scope whose gate was held: the holder is inside SQLite,
/// where the progress handler is about to end it.
const REAPER_RETRY: Duration = Duration::from_millis(2);

const NO_DEADLINE: u64 = u64::MAX;

/// The deadline a connection's progress handler watches, in nanoseconds from the reader's epoch.
pub(crate) struct Clock {
    epoch: Instant,
    deadline: AtomicU64,
}

impl Clock {
    pub(crate) fn new(epoch: Instant) -> Clock {
        Clock {
            epoch,
            deadline: AtomicU64::new(NO_DEADLINE),
        }
    }

    fn now(&self) -> u64 {
        self.epoch.elapsed().as_nanos() as u64
    }

    pub(crate) fn passed(&self) -> bool {
        self.now() >= self.deadline.load(Ordering::Relaxed)
    }

    fn set(&self, deadline: u64) {
        self.deadline.store(deadline, Ordering::Relaxed);
    }
}

/// A connection as a scope holds it, shared with the reaper.
struct Live {
    pooled: Pooled,
    /// Every use of `pooled.conn`, and of a statement prepared on it, is under this. SQLite is
    /// opened with `SQLITE_OPEN_NO_MUTEX`, so this is the only thing serialising it. Between two
    /// steps of a statement it is free, and that is how the reaper reaches an open statement.
    gate: Mutex<()>,
    ended: AtomicBool,
    deadline: u64,
}

// SAFETY: `Connection` isn't `Sync` because its cells and SQLite's handle aren't safe to use from
// two threads at once. Every use of `pooled.conn` and of anything prepared on it, in this module
// and nowhere else, is made holding `gate`, so no two ever overlap.
unsafe impl Sync for Live {}

impl Live {
    fn gate(&self) -> MutexGuard<'_, ()> {
        self.gate.lock().unwrap_or_else(PoisonError::into_inner)
    }

    fn conn(&self, _gate: &MutexGuard<'_, ()>) -> &Connection {
        &self.pooled.conn
    }

    fn is_ended(&self) -> bool {
        self.ended.load(Ordering::Relaxed)
    }

    /// Ends the transaction if nobody has, and with it the snapshot. A `ROLLBACK` alone doesn't:
    /// while a statement is open on the connection, SQLite keeps the read transaction for it. So
    /// open statements are reset first. A reset statement would start again if stepped, so
    /// `query` looks at `ended` before every step.
    fn end(&self, gate: &MutexGuard<'_, ()>) {
        if !self.ended.swap(true, Ordering::Relaxed) {
            let conn = self.conn(gate);
            // SAFETY: the handle is this live connection's, used under the gate as everything on
            // it is. No statement is being stepped, because that takes the gate too, and a reset
            // leaves each statement valid for its owner to reset and finalize again.
            unsafe {
                let handle = conn.handle();
                let mut statement = ffi::sqlite3_next_stmt(handle, std::ptr::null_mut());
                while !statement.is_null() {
                    ffi::sqlite3_reset(statement);
                    statement = ffi::sqlite3_next_stmt(handle, statement);
                }
            }
            let _ = conn.execute_batch("ROLLBACK");
        }
    }

    /// Past the limit, or already ended: `ScopeExpired`, with the snapshot released.
    fn check(&self, gate: &MutexGuard<'_, ()>) -> Result<(), RecordError> {
        if self.pooled.clock.passed() {
            self.end(gate);
        }
        if self.is_ended() {
            return Err(RecordError::ScopeExpired);
        }
        Ok(())
    }
}

struct ReaperState {
    scopes: Vec<Weak<Live>>,
    closing: bool,
}

/// One thread per reader, ending scopes nobody is ending. It holds nothing of the reader, so a
/// dropped reader's lock goes at once; the thread goes once the scopes that outlived it have.
pub(crate) struct Reaper {
    state: Mutex<ReaperState>,
    wake: Condvar,
}

impl Reaper {
    pub(crate) fn start() -> Arc<Reaper> {
        let reaper = Arc::new(Reaper {
            state: Mutex::new(ReaperState {
                scopes: Vec::new(),
                closing: false,
            }),
            wake: Condvar::new(),
        });
        let running = Arc::clone(&reaper);
        thread::Builder::new()
            .name("mentis-record-reaper".to_string())
            .spawn(move || running.run())
            .expect("a thread for the read scope reaper");
        reaper
    }

    fn state(&self) -> MutexGuard<'_, ReaperState> {
        self.state.lock().unwrap_or_else(PoisonError::into_inner)
    }

    pub(crate) fn close(&self) {
        self.state().closing = true;
        self.wake.notify_all();
    }

    fn watch(&self, live: &Arc<Live>) {
        self.state().scopes.push(Arc::downgrade(live));
        self.wake.notify_all();
    }

    fn run(&self) {
        let mut state = self.state();
        loop {
            let scopes: Vec<Arc<Live>> = state
                .scopes
                .iter()
                .filter_map(Weak::upgrade)
                .filter(|live| !live.is_ended())
                .collect();
            let wait = reap(&scopes);
            state.scopes = scopes
                .iter()
                .filter(|live| !live.is_ended())
                .map(Arc::downgrade)
                .collect();
            let empty = state.scopes.is_empty();
            // Nothing of a scope is held across the wait, so its drop can have its connection.
            drop(scopes);
            if state.closing && empty {
                return;
            }
            state = match wait {
                Some(wait) => {
                    self.wake
                        .wait_timeout(state, wait)
                        .unwrap_or_else(PoisonError::into_inner)
                        .0
                }
                None => self
                    .wake
                    .wait(state)
                    .unwrap_or_else(PoisonError::into_inner),
            };
        }
    }
}

/// Ends what has expired, and says how long until something else may have.
fn reap(scopes: &[Arc<Live>]) -> Option<Duration> {
    let mut next: Option<Duration> = None;
    for live in scopes {
        let now = live.pooled.clock.now();
        let left = if now < live.deadline {
            Duration::from_nanos(live.deadline - now)
        } else {
            match live.gate.try_lock() {
                Ok(gate) => {
                    live.end(&gate);
                    continue;
                }
                Err(TryLockError::Poisoned(gate)) => {
                    live.end(&gate.into_inner());
                    continue;
                }
                Err(TryLockError::WouldBlock) => REAPER_RETRY,
            }
        };
        next = Some(next.map_or(left, |n| n.min(left)));
    }
    next
}

/// One row, copied out of SQLite. Reused from row to row, so a read allocates for its largest row.
#[derive(Default)]
struct Copied {
    cells: Vec<Cell>,
    bytes: Vec<u8>,
}

enum Cell {
    Null,
    Integer(i64),
    Real(f64),
    Text(usize, usize),
    Blob(usize, usize),
}

impl Copied {
    fn fill(&mut self, row: &rusqlite::Row<'_>) -> rusqlite::Result<()> {
        self.cells.clear();
        self.bytes.clear();
        for column in 0..row.as_ref().column_count() {
            let cell = match row.get_ref(column)? {
                ValueRef::Null => Cell::Null,
                ValueRef::Integer(n) => Cell::Integer(n),
                ValueRef::Real(n) => Cell::Real(n),
                ValueRef::Text(held) => {
                    self.bytes.extend_from_slice(held);
                    Cell::Text(self.bytes.len() - held.len(), self.bytes.len())
                }
                ValueRef::Blob(held) => {
                    self.bytes.extend_from_slice(held);
                    Cell::Blob(self.bytes.len() - held.len(), self.bytes.len())
                }
            };
            self.cells.push(cell);
        }
        Ok(())
    }
}

impl Row for Copied {
    fn column_count(&self) -> usize {
        self.cells.len()
    }

    fn value(&self, column: usize) -> Result<Value<'_>, RecordError> {
        Ok(match self.cells.get(column) {
            None => return Err(RecordError::NoSuchColumn { column }),
            Some(Cell::Null) => Value::Null,
            Some(Cell::Integer(n)) => Value::Integer(*n),
            Some(Cell::Real(n)) => Value::Real(*n),
            Some(Cell::Text(from, to)) => Value::Text(&self.bytes[*from..*to]),
            Some(Cell::Blob(from, to)) => Value::Blob(&self.bytes[*from..*to]),
        })
    }
}

/// Takes the gate back before a statement and its rows drop, whichever way `query` is left, a
/// panicking callback included. Declared after them, so it drops first; what it takes is in
/// `held`, declared before them, so it drops last.
struct Relock<'h, 'g> {
    held: &'h RefCell<Option<MutexGuard<'g, ()>>>,
    live: &'g Live,
}

impl Drop for Relock<'_, '_> {
    fn drop(&mut self) {
        let mut held = self.held.borrow_mut();
        if held.is_none() {
            *held = Some(self.live.gate());
        }
    }
}

pub(crate) struct Scope {
    live: Option<Arc<Live>>,
    shared: Arc<Shared>,
    class: ReadClass,
    position: Position,
    statements: u32,
}

fn sqlite(error: rusqlite::Error) -> RecordError {
    RecordError::Sqlite {
        detail: error.to_string(),
    }
}

/// SQLite saying a statement was ended, by the handler or by the end of its transaction.
fn was_ended(error: &rusqlite::Error) -> bool {
    matches!(
        error.sqlite_error_code(),
        Some(ErrorCode::OperationInterrupted | ErrorCode::OperationAborted)
    )
}

impl Scope {
    pub(crate) fn begin(
        shared: Arc<Shared>,
        reaper: &Arc<Reaper>,
        class: ReadClass,
    ) -> Result<Scope, RecordError> {
        let pooled = shared.take(class)?;
        let position = match fix_snapshot(&pooled.conn) {
            Ok(position) => position,
            Err(error) => {
                // In doubt, so closed rather than pooled.
                shared.release(class, None);
                return Err(sqlite(error));
            }
        };
        // The limit runs from the snapshot, and the wait for one isn't part of it.
        let deadline = pooled
            .clock
            .now()
            .saturating_add(READ_SCOPE_LIMIT.as_nanos() as u64);
        pooled.clock.set(deadline);
        let live = Arc::new(Live {
            pooled,
            gate: Mutex::new(()),
            ended: AtomicBool::new(false),
            deadline,
        });
        reaper.watch(&live);
        Ok(Scope {
            live: Some(live),
            shared,
            class,
            position,
            statements: 1,
        })
    }
}

fn fix_snapshot(conn: &Connection) -> rusqlite::Result<Position> {
    conn.execute_batch("BEGIN")?;
    conn.query_row(POSITION, [], |row| {
        Ok(Position {
            entry: row.get::<_, i64>(0)? as u64,
            operational: row.get::<_, i64>(1)? as u64,
            delivery: row.get::<_, i64>(2)? as u64,
        })
    })
}

fn bind(statement: &mut rusqlite::Statement<'_>, params: &[Param<'_>]) -> rusqlite::Result<()> {
    if statement.parameter_count() != params.len() {
        return Err(rusqlite::Error::InvalidParameterCount(
            params.len(),
            statement.parameter_count(),
        ));
    }
    for (at, param) in params.iter().enumerate() {
        match *param {
            Param::Null => statement.raw_bind_parameter(at + 1, rusqlite::types::Null)?,
            Param::Integer(n) => statement.raw_bind_parameter(at + 1, n)?,
            Param::Real(n) => statement.raw_bind_parameter(at + 1, n)?,
            Param::Text(text) => statement.raw_bind_parameter(at + 1, text)?,
        }
    }
    Ok(())
}

/// Uses the gate that query holds at this point.
fn under<'g, R>(
    held: &RefCell<Option<MutexGuard<'g, ()>>>,
    use_it: impl FnOnce(&MutexGuard<'g, ()>) -> R,
) -> R {
    use_it(held.borrow().as_ref().expect("the gate is held here"))
}

impl ReadScope for Scope {
    fn position(&self) -> Position {
        self.position
    }

    fn query(
        &mut self,
        sql: &'static str,
        params: &[Param<'_>],
        each: &mut dyn FnMut(&dyn Row) -> Result<Flow, RecordError>,
    ) -> Result<(), RecordError> {
        let live = Arc::clone(self.live.as_ref().expect("a scope has its connection"));
        let live: &Live = &live;
        let held = RefCell::new(Some(live.gate()));
        under(&held, |gate| live.check(gate))?;
        self.statements += 1;
        let mut statement =
            under(&held, |gate| live.conn(gate).prepare_cached(sql)).map_err(sqlite)?;
        bind(&mut statement, params).map_err(sqlite)?;
        let mut rows = statement.raw_query();
        let _relock = Relock { held: &held, live };
        let mut copied = Copied::default();
        loop {
            // The gate is held here, each time round.
            match rows.next() {
                Ok(Some(row)) => copied.fill(row).map_err(sqlite)?,
                Ok(None) => return Ok(()),
                Err(error) if was_ended(&error) => {
                    under(&held, |gate| live.end(gate));
                    return Err(RecordError::ScopeExpired);
                }
                Err(error) => return Err(sqlite(error)),
            }
            *held.borrow_mut() = None;
            let flow = each(&copied)?;
            *held.borrow_mut() = Some(live.gate());
            if flow == Flow::Stop {
                return Ok(());
            }
            under(&held, |gate| live.check(gate))?;
        }
    }

    fn statements(&self) -> u32 {
        self.statements
    }
}

impl Drop for Scope {
    fn drop(&mut self) {
        let Some(live) = self.live.take() else {
            return;
        };
        let clean = {
            let gate = live.gate();
            let conn = live.conn(&gate);
            if !live.ended.swap(true, Ordering::Relaxed) {
                let _ = conn.execute_batch("COMMIT");
            }
            conn.is_autocommit()
        };
        // Only the reaper can still hold the `Live`, for a moment. Then this connection closes
        // with that last holder, as one in doubt would, and the place in the pool is free anyway.
        let back = Arc::into_inner(live).filter(|_| clean).map(|live| {
            live.pooled.clock.set(NO_DEADLINE);
            live.pooled
        });
        self.shared.release(self.class, back);
    }
}
