//! The read scope, on a scratch Brain with a writer beside it. A checkpoint that completes is the
//! evidence a snapshot has gone: a call answering `ScopeExpired` wouldn't show the WAL is free.

mod support;

use std::time::{Duration, Instant};

use mentis_record::{
    Brain, BrainOpener, Flow, Param, Position, READ_SCOPE_ENDED_WITHIN, READ_SCOPE_LIMIT,
    READER_CAPS, ReadClass, ReadScope, Reader, RecordError, RecordReader, Row,
};
use rusqlite::Connection;
use support::{add_entries, checkpoint_completes, scratch_brain, writer};

const ENDLESS: &str = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) \
                       SELECT COUNT(*) FROM n";
const COUNT_ENTRIES: &str = "SELECT COUNT(*) FROM entry";
const ALL_ENTRIES: &str = "SELECT id FROM entry ORDER BY seq";

fn opened(name: &str) -> (Reader, Connection) {
    let root = scratch_brain(name);
    let db = writer(&root);
    add_entries(&db, 3);
    (Brain::open(&root).unwrap(), db)
}

fn cap_of(class: ReadClass) -> usize {
    READER_CAPS.iter().find(|(c, _)| *c == class).unwrap().1
}

fn count_entries(scope: &mut dyn ReadScope) -> Result<i64, RecordError> {
    let mut rows = 0;
    scope.query(COUNT_ENTRIES, &[], &mut |row| {
        rows = row.value(0)?.integer().unwrap();
        Ok(Flow::Continue)
    })?;
    Ok(rows)
}

fn run_endless(scope: &mut dyn ReadScope) -> Result<(), RecordError> {
    scope.query(ENDLESS, &[], &mut |_| Ok(Flow::Continue))
}

#[test]
fn position_is_fixed_with_the_snapshot() {
    let (reader, db) = opened("position-fixed");
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    let at = Position {
        entry: 3,
        operational: 0,
        delivery: 0,
    };
    assert_eq!(scope.position(), at);
    add_entries(&db, 2);
    assert_eq!(scope.position(), at, "the position does not move");
    assert_eq!(
        count_entries(scope.as_mut()),
        Ok(3),
        "nor does what it reads"
    );
    drop(scope);
    let scope = reader.read_scope(ReadClass::Foreground).unwrap();
    assert_eq!(
        scope.position().entry,
        5,
        "the next scope is a new snapshot"
    );
}

#[test]
fn position_costs_no_statement_after_opening() {
    let (reader, _db) = opened("position-cost");
    let scope = reader.read_scope(ReadClass::Foreground).unwrap();
    for _ in 0..5 {
        scope.position();
    }
    assert_eq!(scope.statements(), 1);
}

#[test]
fn a_running_statement_ends_at_the_limit() {
    let (reader, _db) = opened("running");
    let before = Instant::now();
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    assert_eq!(run_endless(scope.as_mut()), Err(RecordError::ScopeExpired));
    let took = before.elapsed();
    assert!(
        took >= READ_SCOPE_LIMIT - Duration::from_millis(50),
        "{took:?}"
    );
    assert!(took < READ_SCOPE_ENDED_WITHIN, "{took:?}");
    assert_eq!(
        count_entries(scope.as_mut()),
        Err(RecordError::ScopeExpired)
    );
}

#[test]
fn an_idle_scope_is_ended_by_the_reaper() {
    let (reader, db) = opened("idle");
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    add_entries(&db, 1);
    assert!(!checkpoint_completes(&db), "the idle snapshot pins the WAL");
    std::thread::sleep(READ_SCOPE_ENDED_WITHIN);
    assert!(
        checkpoint_completes(&db),
        "with no call on the scope, the reaper has let go of it"
    );
    assert_eq!(
        count_entries(scope.as_mut()),
        Err(RecordError::ScopeExpired)
    );
}

/// Polls until a checkpoint completes, and answers how long after `since` that was.
fn released_after(db: &Connection, since: Instant) -> Duration {
    while !checkpoint_completes(db) {
        assert!(since.elapsed() < Duration::from_secs(10), "it never let go");
        std::thread::sleep(Duration::from_millis(10));
    }
    since.elapsed()
}

#[test]
fn a_scope_ends_within_2500_ms_of_its_snapshot() {
    // A statement in SQLite's hands, the whole time.
    let (reader, db) = opened("ended-running");
    let since = Instant::now();
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    add_entries(&db, 1);
    let running = std::thread::spawn(move || {
        let answer = run_endless(scope.as_mut());
        (answer, scope)
    });
    let released = released_after(&db, since);
    assert!(
        released >= READ_SCOPE_LIMIT - Duration::from_millis(50),
        "{released:?}"
    );
    assert!(released < READ_SCOPE_ENDED_WITHIN, "running: {released:?}");
    assert_eq!(running.join().unwrap().0, Err(RecordError::ScopeExpired));

    // Nothing running at all.
    let (reader, db) = opened("ended-idle");
    let since = Instant::now();
    let _scope = reader.read_scope(ReadClass::Foreground).unwrap();
    add_entries(&db, 1);
    let released = released_after(&db, since);
    assert!(released < READ_SCOPE_ENDED_WITHIN, "idle: {released:?}");

    // A statement open with a row callback stuck: SQLite isn't running and can't see the clock.
    let (reader, db) = opened("ended-callback");
    let since = Instant::now();
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    add_entries(&db, 1);
    let stuck = std::thread::spawn(move || {
        scope.query(ALL_ENTRIES, &[], &mut |row: &dyn Row| {
            assert!(row.value(0)?.text().is_some());
            std::thread::sleep(READ_SCOPE_ENDED_WITHIN + Duration::from_millis(500));
            Ok(Flow::Continue)
        })
    });
    let released = released_after(&db, since);
    assert!(released < READ_SCOPE_ENDED_WITHIN, "callback: {released:?}");
    assert_eq!(stuck.join().unwrap(), Err(RecordError::ScopeExpired));

    // However a callback comes back past the limit, the answer is that the limit passed.
    let past_it = READ_SCOPE_LIMIT + Duration::from_secs(1);
    let (reader, _db) = opened("stop-past-the-limit");
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    let answer = scope.query(ALL_ENTRIES, &[], &mut |_| {
        std::thread::sleep(past_it);
        Ok(Flow::Stop)
    });
    assert_eq!(answer, Err(RecordError::ScopeExpired), "Flow::Stop");
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    let answer = scope.query(ALL_ENTRIES, &[], &mut |_| {
        std::thread::sleep(past_it);
        Err(RecordError::NoSuchColumn { column: 9 })
    });
    assert_eq!(answer, Err(RecordError::ScopeExpired), "a callback's error");

    // Inside the limit they mean what they say, and the scope stays open.
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    assert_eq!(
        scope.query(ALL_ENTRIES, &[], &mut |_| Ok(Flow::Stop)),
        Ok(())
    );
    assert_eq!(
        scope.query(ALL_ENTRIES, &[], &mut |_| {
            Err(RecordError::NoSuchColumn { column: 9 })
        }),
        Err(RecordError::NoSuchColumn { column: 9 })
    );
    assert_eq!(count_entries(scope.as_mut()), Ok(3));
}

#[test]
fn busy_at_the_cap_answers_at_once() {
    let (reader, _db) = opened("busy");
    let held: Vec<_> = (0..cap_of(ReadClass::Foreground))
        .map(|_| reader.read_scope(ReadClass::Foreground).unwrap())
        .collect();
    let asked = Instant::now();
    let answer = reader.read_scope(ReadClass::Foreground).map(|_| ());
    assert_eq!(
        answer,
        Err(RecordError::Busy {
            class: "foreground"
        })
    );
    assert!(
        asked.elapsed() < Duration::from_millis(100),
        "{:?}",
        asked.elapsed()
    );
    drop(held);
    assert!(
        reader.read_scope(ReadClass::Foreground).is_ok(),
        "the places come back"
    );
}

#[test]
fn one_class_at_its_cap_does_not_stop_another() {
    let (reader, _db) = opened("classes");
    let _held: Vec<_> = (0..cap_of(ReadClass::Foreground))
        .map(|_| reader.read_scope(ReadClass::Foreground).unwrap())
        .collect();
    for class in [
        ReadClass::Agent,
        ReadClass::Background,
        ReadClass::Connector,
    ] {
        let mut scope = reader.read_scope(class).unwrap();
        assert_eq!(count_entries(scope.as_mut()), Ok(3));
    }
}

#[test]
fn statements_count_the_position() {
    let (reader, _db) = opened("statements");
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    assert_eq!(scope.statements(), 1);
    count_entries(scope.as_mut()).unwrap();
    assert_eq!(scope.statements(), 2);
    count_entries(scope.as_mut()).unwrap();
    assert_eq!(scope.statements(), 3);
}

#[test]
fn a_write_statement_is_refused() {
    let (reader, _db) = opened("write");
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    let answer = scope.query("INSERT INTO entry (id) VALUES ('forged')", &[], &mut |_| {
        Ok(Flow::Continue)
    });
    let Err(RecordError::Sqlite { detail }) = answer else {
        panic!("SQLite refuses it, and got {answer:?}");
    };
    assert!(detail.contains("readonly"), "{detail}");
    assert_eq!(count_entries(scope.as_mut()), Ok(3));
}

#[test]
fn a_list_of_ids_reads_through_json_each() {
    let (reader, _db) = opened("json-each");
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    let mut ids = Vec::new();
    scope
        .query(
            "SELECT id FROM entry WHERE id IN (SELECT value FROM json_each(?1)) ORDER BY seq",
            &[Param::Text(r#"["ent-0","ent-2","ent-missing"]"#)],
            &mut |row| {
                ids.push(row.value(0)?.text().unwrap().to_string());
                Ok(Flow::Continue)
            },
        )
        .unwrap();
    assert_eq!(ids, ["ent-0", "ent-2"]);
    assert_eq!(scope.statements(), 2, "one statement, however many ids");
}

#[test]
fn drop_commits_and_returns_the_connection() {
    let (reader, db) = opened("drop");
    let opened_before = reader.connections_opened();
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    count_entries(scope.as_mut()).unwrap();
    add_entries(&db, 1);
    assert!(
        !checkpoint_completes(&db),
        "its snapshot holds until it is dropped"
    );
    let idle = reader.idle_connections(ReadClass::Foreground);
    drop(scope);
    assert!(
        checkpoint_completes(&db),
        "dropped, its transaction is over"
    );
    assert_eq!(reader.idle_connections(ReadClass::Foreground), idle + 1);
    let scope = reader.read_scope(ReadClass::Foreground).unwrap();
    assert_eq!(
        scope.position().entry,
        4,
        "the same connection, at a new snapshot"
    );
    assert_eq!(
        reader.connections_opened(),
        opened_before,
        "none was opened"
    );

    // The reaper holds every scope for a moment each time one begins. A drop in that moment still
    // gets its connection back: it mustn't be left to close with the reaper, after the lock. Four
    // threads never need more than four connections unless one is lost.
    let (reader, _db) = opened("drop-under-the-reaper");
    std::thread::scope(|threads| {
        for _ in 0..4 {
            threads.spawn(|| {
                for _ in 0..3000 {
                    drop(reader.read_scope(ReadClass::Foreground).unwrap());
                }
            });
        }
    });
    assert!(
        reader.connections_opened() <= 4,
        "{} connections for four threads",
        reader.connections_opened()
    );
}
