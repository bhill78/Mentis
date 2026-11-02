//! What the crate's tests share: scratch Brains, and Python as the other side of a differential.
//! Each test target uses part of this.
#![allow(dead_code)]

use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU32, Ordering};

use mentis_record::LEDGER;
use rusqlite::{Connection, params};

/// The fixtures' root. Row G fails without it: nothing here skips.
pub fn fixtures() -> PathBuf {
    PathBuf::from(
        std::env::var("MENTIS_R1_FIXTURES").expect("MENTIS_R1_FIXTURES names R1's fixtures"),
    )
}

pub fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

/// A Python of the test environment, with `code` importable.
pub fn python(code: &Path) -> Command {
    let exe = fixtures().join("venv").join("Scripts").join("python.exe");
    assert!(exe.is_file(), "no test environment at {}", exe.display());
    let mut command = Command::new(exe);
    command
        .current_dir(code)
        .env("PYTHONPATH", code)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONIOENCODING", "utf-8");
    command
}

/// Runs a script of this clone's Python, and answers its stdout. Failing fails the test.
pub fn run_python(script: &str, args: &[&str]) -> String {
    let done = python(&repo_root())
        .arg("-c")
        .arg(script)
        .args(args)
        .output()
        .expect("Python starts");
    assert!(
        done.status.success(),
        "Python failed: {}",
        String::from_utf8_lossy(&done.stderr)
    );
    String::from_utf8(done.stdout).expect("Python's output is UTF-8")
}

/// A new directory for one test, under the target directory.
pub fn scratch_dir(name: &str) -> PathBuf {
    static NEXT: AtomicU32 = AtomicU32::new(0);
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR")).join(format!(
        "{name}-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

const SCHEMA: &str = "
    PRAGMA journal_mode=WAL;
    CREATE TABLE corpus (one INTEGER PRIMARY KEY, corpus_id TEXT, chained_from_first INTEGER);
    INSERT INTO corpus VALUES (1, 'corpus-under-test', 1);
    CREATE TABLE schema_migration (seq INTEGER PRIMARY KEY, id TEXT, checksum TEXT);
    CREATE TABLE entry (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, family TEXT, def_name TEXT,
        def_version INTEGER, body TEXT, attributed_to TEXT, written_by TEXT, recorded_at REAL,
        origin TEXT, link_from TEXT, link_to TEXT, link_relation TEXT,
        link_relation_version INTEGER, prev_hash TEXT, hash TEXT);
    CREATE TABLE operational (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, at REAL, actor TEXT,
        act TEXT, conversation TEXT, turn TEXT, execution TEXT, runtime TEXT, because TEXT,
        caused_by TEXT, about TEXT, detail TEXT, prev_hash TEXT, hash TEXT);
    CREATE TABLE delivery (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, execution TEXT,
        conversation TEXT, participant TEXT, runtime TEXT, mechanism TEXT, at REAL, material TEXT,
        behavioural_sources TEXT, operation_ok INTEGER, prev_hash TEXT, hash TEXT);
";

/// A scratch Brain with the chained tables' columns and the ledger this build names.
pub fn scratch_brain(name: &str) -> PathBuf {
    let root = scratch_dir(name);
    let db = writer(&root);
    db.execute_batch(SCHEMA).unwrap();
    for (seq, (id, checksum)) in LEDGER.iter().enumerate() {
        db.execute(
            "INSERT INTO schema_migration VALUES (?1, ?2, ?3)",
            params![seq as i64 + 1, id, checksum],
        )
        .unwrap();
    }
    root
}

/// A writing connection on a scratch Brain, the way Python's writer sits beside a reader. It
/// never waits, so a checkpoint answers at once whether a reader is pinning it.
pub fn writer(root: &Path) -> Connection {
    let db = Connection::open(root.join("corpus.db")).unwrap();
    db.execute_batch("PRAGMA busy_timeout=0;").unwrap();
    db
}

pub fn add_entries(db: &Connection, how_many: usize) {
    for at in 0..how_many {
        db.execute("INSERT INTO entry (id) VALUES (?1)", [format!("ent-{at}")])
            .unwrap();
    }
}

/// Whether a full checkpoint can finish now, which it can't while a reader holds a snapshot of
/// something the WAL would have to give up.
pub fn checkpoint_completes(db: &Connection) -> bool {
    let busy: i64 = db
        .query_row("PRAGMA wal_checkpoint(TRUNCATE)", [], |row| row.get(0))
        .unwrap();
    busy == 0
}

/// A Python process holding what its script takes, until dropped.
pub struct Holder(Child);

impl Holder {
    /// `take` is an expression using `root`, say `brainlock.exclusive(root, 'test')`.
    pub fn start(root: &Path, take: &str) -> Holder {
        let script = format!(
            "import sys\nfrom mentis.spine import brainlock\nroot = sys.argv[1]\n\
             held = {take}\nprint('held', flush=True)\nsys.stdin.read()\n"
        );
        let mut child = python(&repo_root())
            .arg("-c")
            .arg(script)
            .arg(root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .expect("Python starts");
        let mut line = String::new();
        BufReader::new(child.stdout.as_mut().unwrap())
            .read_line(&mut line)
            .unwrap();
        assert_eq!(line.trim(), "held", "Python did not take its lock");
        Holder(child)
    }
}

impl Drop for Holder {
    fn drop(&mut self) {
        let _ = self.0.stdin.as_mut().unwrap().write_all(b"\n");
        self.0.stdin = None;
        let _ = self.0.wait();
    }
}
