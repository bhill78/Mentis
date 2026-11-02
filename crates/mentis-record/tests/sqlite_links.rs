//! The pinned SQLite builds and links here, and has what the read scope contract relies on.
//! Temporary files only: no Brain is opened. P1.1's tests replace this with the real thing.

use mentis_record::{OPEN_FLAGS, OPEN_PRAGMAS};
use rusqlite::Connection;

fn scratch(name: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("mentis-record-{}-{name}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir.join("scratch.db")
}

#[test]
fn a_connection_opened_as_the_contract_says_refuses_to_write() {
    let path = scratch("readonly");
    let writer = Connection::open(&path).unwrap();
    writer
        .execute_batch("PRAGMA journal_mode=WAL; CREATE TABLE t(x); INSERT INTO t VALUES (1);")
        .unwrap();

    let reader = Connection::open_with_flags(&path, OPEN_FLAGS).unwrap();
    reader.execute_batch(OPEN_PRAGMAS).unwrap();
    assert!(reader.execute_batch("INSERT INTO t VALUES (2)").is_err());
    let rows: i64 = reader
        .query_row("SELECT COUNT(*) FROM t", [], |r| r.get(0))
        .unwrap();
    assert_eq!(rows, 1);

    drop((reader, writer));
    let _ = std::fs::remove_dir_all(path.parent().unwrap());
}

#[test]
fn a_list_of_ids_is_one_parameter_through_json_each() {
    let db = Connection::open_in_memory().unwrap();
    db.execute_batch("CREATE TABLE t(id TEXT); INSERT INTO t VALUES ('a'), ('b'), ('c');")
        .unwrap();
    let found: i64 = db
        .query_row(
            "SELECT COUNT(*) FROM t WHERE id IN (SELECT value FROM json_each(?1))",
            ["[\"a\",\"c\",\"missing\"]"],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(found, 2);
}

#[test]
fn the_progress_handler_can_end_a_running_statement() {
    let mut db = Connection::open_in_memory().unwrap();
    db.progress_handler(1000, Some(|| true)).unwrap();
    let endless = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) \
                   SELECT COUNT(*) FROM n";
    let ended = db.query_row(endless, [], |r| r.get::<_, i64>(0));
    assert!(ended.is_err());
}

/// Stated in the output so the integrator can put it in the report (appendix A, `H`).
#[test]
fn the_bundled_sqlite_says_what_it_is() {
    let db = Connection::open_in_memory().unwrap();
    let version: String = db
        .query_row("SELECT sqlite_version()", [], |r| r.get(0))
        .unwrap();
    println!("bundled sqlite {version}");
    assert!(version.starts_with("3."));
}
