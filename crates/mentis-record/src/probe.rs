//! Row H's way to the front's own reader (`docs/rust/R1-acceptance.md`, "H: SQLite"), for test
//! builds: only with the `row-h-probe` feature, and then only when `ROW_H_PROBE_DIR` is set.
//!
//! The front names no way to hold a read scope stuck or to run a statement of a test's choosing, and
//! nothing may add one. So a test build watches that directory from inside the front's process. An
//! `ask-<mode>` file there takes a scope from the reader the front is serving from, in its
//! Foreground pool, and answers in `<mode>.snapshot` once the snapshot exists, then `<mode>.answer`.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Weak};
use std::thread;
use std::time::Duration;

use crate::open::Shared;
use crate::scope::{Reaper, Scope};
use crate::{Flow, ReadClass, ReadScope, RecordError};

const ENDLESS: &str = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) \
                       SELECT COUNT(*) FROM n";
const ALL_ENTRIES: &str = "SELECT id FROM entry ORDER BY seq";
const FORGED: &str = "INSERT INTO corpus (one) VALUES (2)";
const VERSION: &str = "SELECT sqlite_version()";
const OPTIONS: &str = "PRAGMA compile_options";

const MODES: [&str; 5] = ["report", "write", "running", "idle", "callback"];

/// How long a stuck reader stays stuck: well past when it must have been ended.
const STUCK_FOR: Duration = Duration::from_secs(4);

const LOOK_EVERY: Duration = Duration::from_millis(10);

/// Starts watching, if asked to. It holds nothing of the reader between looks, so the lock goes
/// when the reader does.
pub(crate) fn start(shared: Weak<Shared>, reaper: Arc<Reaper>) {
    let Some(dir) = std::env::var_os("ROW_H_PROBE_DIR") else {
        return;
    };
    let dir = PathBuf::from(dir);
    thread::Builder::new()
        .name("row-h-probe".to_string())
        .spawn(move || {
            while let Some(shared) = shared.upgrade() {
                for mode in MODES {
                    let ask = dir.join(format!("ask-{mode}"));
                    if fs::remove_file(&ask).is_ok() {
                        answer(&dir, mode, Arc::clone(&shared), &reaper);
                    }
                }
                drop(shared);
                thread::sleep(LOOK_EVERY);
            }
        })
        .expect("a thread for row H's probe");
}

/// Whole or not at all, so the test never reads half an answer.
fn say(dir: &Path, name: String, text: &str) {
    let part = dir.join(format!("{name}.part"));
    fs::write(&part, text).expect("row H's probe directory");
    fs::rename(&part, dir.join(name)).expect("row H's probe directory");
}

fn answer(dir: &Path, mode: &str, shared: Arc<Shared>, reaper: &Arc<Reaper>) {
    let mut scope = match Scope::begin(shared, reaper, ReadClass::Foreground) {
        Ok(scope) => scope,
        Err(error) => return say(dir, format!("{mode}.answer"), &error.to_string()),
    };
    say(
        dir,
        format!("{mode}.snapshot"),
        &scope.position().to_string(),
    );
    let answer = match mode {
        "report" => report(&mut scope),
        "write" => words(scope.query(FORGED, &[], &mut |_| Ok(Flow::Continue))),
        "running" => words(scope.query(ENDLESS, &[], &mut |_| Ok(Flow::Continue))),
        "idle" => {
            thread::sleep(STUCK_FOR);
            words(scope.query(ALL_ENTRIES, &[], &mut |_| Ok(Flow::Stop)))
        }
        _ => words(scope.query(ALL_ENTRIES, &[], &mut |_| {
            thread::sleep(STUCK_FOR);
            Ok(Flow::Continue)
        })),
    };
    drop(scope);
    say(dir, format!("{mode}.answer"), &answer);
}

fn words(answer: Result<(), RecordError>) -> String {
    match answer {
        Ok(()) => "ok".to_string(),
        Err(error) => error.to_string(),
    }
}

/// `sqlite_version()` and `PRAGMA compile_options`, one to a line.
fn report(scope: &mut Scope) -> String {
    let mut lines = Vec::new();
    for sql in [VERSION, OPTIONS] {
        let read = scope.query(sql, &[], &mut |row| {
            lines.push(row.value(0)?.text().unwrap_or_default().to_string());
            Ok(Flow::Continue)
        });
        if let Err(error) = read {
            lines.push(error.to_string());
        }
    }
    lines.join("\n")
}
