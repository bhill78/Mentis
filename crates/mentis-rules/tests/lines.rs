//! Standing, `now_reads` and `lines_of` against Python on what a real record may hold and no command
//! writes: lines and links that loop, links of links of links, forks of each, and relation versions
//! with other roles (`python_side.py`, `lines`). The real Brain has none of these, so this is where
//! the recursive statements' answers on them are checked. Each is asked of all the ids at once and
//! of each alone, because what one id's walk reaches must not depend on what else was asked.

#[path = "support/mod.rs"]
mod support;

use mentis_record::{Brain, BrainOpener, Id, ReadClass, ReadScope, RecordReader};
use mentis_rules::{Line, Reading, STANDING_STATEMENTS, STATEMENTS, Standing};
use serde_json::{Value, json};

fn shown_standing(standing: &Standing) -> Value {
    let list = |ids: &[Id]| ids.iter().map(|id| id.0.clone()).collect::<Vec<_>>();
    let incoming: serde_json::Map<String, Value> = standing
        .incoming
        .iter()
        .map(|(relation, ids)| (relation.clone(), json!(list(ids))))
        .collect();
    json!({
        "entry": standing.entry.0,
        "stands": standing.stands,
        "established_by": list(&standing.established_by),
        "superseded_by": list(&standing.superseded_by),
        "incoming": incoming,
    })
}

fn shown_reading(reading: &Reading) -> Value {
    let body: Value = serde_json::from_str(&reading.body_json).unwrap();
    json!({
        "root": reading.root.0,
        "body": body,
        "versions": reading.revision.as_ref().map(|revision| revision.versions),
        "current": reading.revision.as_ref().map(|revision| &revision.current.0),
        "deleted": reading.deleted.as_ref().map(|deleted| &deleted.record.0),
    })
}

fn shown_line(line: &Line) -> Value {
    json!({
        "root": line.root,
        "versions": line.versions.iter().map(|entry| &entry.id).collect::<Vec<_>>(),
        "deletion": line.deletion.as_ref().map(|entry| &entry.id),
    })
}

/// The answer to `key` for `id`, read with these `ids`, against Python's.
fn check(scope: &mut dyn ReadScope, said: &Value, ids: &[Id], times: &[f64], counts: &mut Counts) {
    let before = scope.statements();
    let now = mentis_rules::standing_many(scope, ids, None).unwrap();
    assert_eq!(scope.statements() - before, STANDING_STATEMENTS);
    for id in ids {
        let want = &said["stands"][&id.0];
        assert_eq!(shown_standing(&now[id]), want["now"], "{id}, now");
        counts.stands += usize::from(now[id].stands);
        counts.superseded += usize::from(!now[id].superseded_by.is_empty());
    }
    for (at, time) in times.iter().enumerate() {
        let then = mentis_rules::standing_many(scope, ids, Some(*time)).unwrap();
        for id in ids {
            let want = &said["stands"][&id.0];
            assert_eq!(
                shown_standing(&then[id]),
                want["then"][at],
                "{id}, as at {time}"
            );
            counts.differ_then += usize::from(want["then"][at] != want["now"]);
        }
    }

    let before = scope.statements();
    let reads = mentis_rules::now_reads(scope, ids).unwrap();
    assert!(scope.statements() - before <= STATEMENTS);
    let before = scope.statements();
    let lines = mentis_rules::lines_of(scope, ids).unwrap();
    assert!(scope.statements() - before <= STATEMENTS);
    for id in ids {
        match said["now"].get(&id.0) {
            Some(want) => {
                assert_eq!(shown_reading(&reads[id]), *want, "{id}, now_reads");
                counts.edited += usize::from(reads[id].revision.is_some());
                counts.deleted += usize::from(reads[id].deleted.is_some());
            }
            None => assert!(!reads.contains_key(id), "{id}"),
        }
        match said["lines"].get(&id.0) {
            Some(want) => assert_eq!(shown_line(&lines[id]), *want, "{id}, lines_of"),
            None => assert!(!lines.contains_key(id), "{id}"),
        }
    }
}

#[derive(Default)]
struct Counts {
    stands: usize,
    superseded: usize,
    differ_then: usize,
    edited: usize,
    deleted: usize,
}

fn number(value: &Value) -> f64 {
    value.as_str().unwrap().parse().unwrap()
}

#[test]
fn forks_loops_and_links_of_links_read_as_python_says() {
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "rules-lines");
    let said: Value = serde_json::from_str(&support::side("lines", &brain)).unwrap();
    let reader = Brain::open(&brain).unwrap();
    let ids: Vec<Id> = said["ids"]
        .as_array()
        .unwrap()
        .iter()
        .map(|id| Id(id.as_str().unwrap().to_owned()))
        .collect();
    let times: Vec<f64> = said["times"]
        .as_array()
        .unwrap()
        .iter()
        .map(number)
        .collect();

    let mut together = Counts::default();
    let mut scope = reader.read_scope(ReadClass::Background).unwrap();
    check(scope.as_mut(), &said, &ids, &times, &mut together);
    drop(scope);
    println!(
        "{} ids at {} times: {} stand, {} superseded, {} differ then, {} edited, {} deleted",
        ids.len(),
        times.len(),
        together.stands,
        together.superseded,
        together.differ_then,
        together.edited,
        together.deleted,
    );
    // Enough of each that the walks had something to walk.
    assert!(together.stands >= 1, "nothing stands");
    assert!(together.superseded >= 20, "{}", together.superseded);
    assert!(together.differ_then >= 40, "{}", together.differ_then);
    assert!(together.edited >= 8, "{}", together.edited);
    assert!(together.deleted >= 2, "{}", together.deleted);

    for id in &ids {
        let mut alone = Counts::default();
        let mut scope = reader.read_scope(ReadClass::Background).unwrap();
        check(
            scope.as_mut(),
            &said,
            std::slice::from_ref(id),
            &times,
            &mut alone,
        );
    }
}
