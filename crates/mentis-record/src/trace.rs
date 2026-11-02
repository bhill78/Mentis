//! The statement trace, for test builds: only with the `sql-trace` feature, and then only when
//! `WORKLOAD_TRACE_DIR` is set (`contracts/bench.md`). Each statement is one line of
//! `trace-<pid>.log` there, as `tools/bench/trace/sitecustomize.py` writes Python's:
//! `<seconds>\trust:<thread>\t<statement>`. The bench counts them per route.

use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::Path;
use std::sync::{Mutex, OnceLock, PoisonError};
use std::time::{SystemTime, UNIX_EPOCH};

use rusqlite::Connection;
use rusqlite::trace::{TraceEvent, TraceEventCodes};

/// As long as Python's trace keeps of a statement.
const KEPT: usize = 400;

/// The process's log, or nothing if the trace wasn't asked for. A build asked to trace that can't
/// stops, since an empty log would read as no statements.
fn log() -> Option<&'static Mutex<File>> {
    static LOG: OnceLock<Option<Mutex<File>>> = OnceLock::new();
    LOG.get_or_init(|| {
        let dir = std::env::var_os("WORKLOAD_TRACE_DIR")?;
        let path = Path::new(&dir).join(format!("trace-{}.log", std::process::id()));
        let file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&path)
            .unwrap_or_else(|error| panic!("no statement trace at {}: {error}", path.display()));
        Some(Mutex::new(file))
    })
    .as_ref()
}

fn write(log: &Mutex<File>, sql: &str) {
    let at = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64();
    let thread = std::thread::current();
    let thread = thread.name().unwrap_or("unnamed");
    let sql: String = sql
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .chars()
        .take(KEPT)
        .collect();
    let line = format!("{at:.4}\trust:{thread}\t{sql}\n");
    let mut file = log.lock().unwrap_or_else(PoisonError::into_inner);
    // A trace that can't write must not change how a read goes.
    let _ = file.write_all(line.as_bytes());
}

/// `conn`, tracing if the trace was asked for.
pub(crate) fn switched_on(mut conn: Connection) -> rusqlite::Result<Connection> {
    if let Some(log) = log() {
        conn.trace_v2(
            TraceEventCodes::SQLITE_TRACE_STMT,
            Some(move |event: TraceEvent<'_>| {
                if let TraceEvent::Stmt(_, sql) = event {
                    write(log, sql);
                }
            }),
        )?;
    }
    Ok(conn)
}
