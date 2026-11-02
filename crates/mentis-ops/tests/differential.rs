//! `moved` and `topics` against Python on a changed BRAIN-SEED, and every op's budget warm, just after
//! a commit, and cold (`contracts/ops.md`). `MENTIS_RULES_BRAIN` names a Brain copy to read instead,
//! with nothing written to it.

#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::path::PathBuf;
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use mentis_ops::moved::Moved;
use mentis_ops::names::{Names, NamesArgs};
use mentis_ops::pulse::{Pulse, PulseArgs};
use mentis_ops::topics::{Topics, TopicsArgs};
use mentis_ops::{Id, OpError, ReadClass, ReadOp, ReadRequest};
use mentis_record::{Brain, BrainOpener, Position, RecordReader};
use serde_json::{Value, json};

fn world() -> &'static (PathBuf, Value) {
    static WORLD: OnceLock<(PathBuf, Value)> = OnceLock::new();
    WORLD.get_or_init(|| {
        let brain = match std::env::var("MENTIS_RULES_BRAIN") {
            Ok(brain) => PathBuf::from(brain),
            Err(_) => support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "ops"),
        };
        let answers = support::side("answers", &brain);
        (brain, serde_json::from_str(&answers).unwrap())
    })
}

fn request<A>(args: A, limit: Option<u32>) -> ReadRequest<A> {
    ReadRequest {
        args,
        cursor: None,
        limit,
        deadline: Instant::now() + Duration::from_secs(2),
    }
}

fn moved_json(moved: &Option<Moved>) -> Value {
    match moved {
        None => Value::Null,
        Some(moved) => serde_json::to_value(moved).unwrap(),
    }
}

/// The record's position as Python answered it, for `since`s it was asked at.
fn head() -> Position {
    let at = world().1["position"].as_array().unwrap();
    Position {
        entry: at[0].as_u64().unwrap(),
        operational: at[1].as_u64().unwrap(),
        delivery: at[2].as_u64().unwrap(),
    }
}

#[test]
fn where_the_record_moved_is_where_python_says_at_every_position_asked() {
    let (brain, answers) = world();
    let reader = Brain::open(brain).unwrap();
    let asked = answers["moved"].as_object().unwrap();
    assert!(asked.len() >= 60);
    let (mut placed, mut nothing, mut owned_by_python) = (0, 0, 0);
    let mut seen_loose = false;
    let mut seen_governed = false;
    let mut seen_people = false;
    let mut seen_executions = false;
    for (since, want) in asked {
        let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
        assert_eq!(scope.position(), head(), "the record moved under this test");
        match mentis_ops::moved::moved(scope.as_mut(), head(), since) {
            Ok(got) => {
                assert_eq!(&moved_json(&got), want, "since {since:?}");
                match got {
                    None => nothing += 1,
                    Some(moved) => {
                        placed += 1;
                        seen_loose |= moved.loose;
                        seen_governed |= moved.governed;
                        seen_people |= moved.people;
                        seen_executions |= !moved.executions.is_empty();
                    }
                }
            }
            Err(OpError::NotOwned { .. }) => owned_by_python += 1,
            Err(other) => panic!("since {since:?}: {other}"),
        }
    }
    println!("{placed} placed, {nothing} everything, {owned_by_python} left to Python");
    assert_eq!(owned_by_python, 0, "nothing asked here needs Python's int");
    if std::env::var("MENTIS_RULES_BRAIN").is_err() {
        assert!(placed >= 50 && nothing >= 15, "{placed} placed, {nothing}");
        assert!(seen_loose && seen_governed && seen_people && seen_executions);
    }
}

#[test]
fn a_position_in_another_script_s_digits_is_left_to_python() {
    let reader = Brain::open(&world().0).unwrap();
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    let got = mentis_ops::moved::moved(scope.as_mut(), head(), "\u{663}.0.0");
    assert!(matches!(got, Err(OpError::NotOwned { .. })));
}

#[test]
fn a_pulse_says_where_and_only_when_since_is_behind() {
    let reader = Brain::open(&world().0).unwrap();
    let durable = head();
    let at = |since: Option<String>| {
        let answer = mentis_ops::run(
            &Pulse,
            &reader,
            ReadClass::Foreground,
            &request(PulseArgs { since }, None),
        )
        .unwrap();
        assert_eq!(answer.as_of, durable);
        assert_eq!(answer.rows.len(), 1);
        answer.rows[0].clone()
    };
    assert_eq!(at(None).durable, durable);
    assert_eq!(at(None).moved, None);
    assert_eq!(at(Some(durable.to_string())).moved, None);
    assert_eq!(at(Some("x".into())).moved, Some(None));
    let behind = format!(
        "{}.{}.{}",
        durable.entry - 1,
        durable.operational,
        durable.delivery
    );
    assert!(matches!(at(Some(behind)).moved, Some(Some(_))));
}

#[test]
fn topics_answer_as_python_s_at_every_question_and_limit() {
    let (brain, answers) = world();
    let reader = Brain::open(brain).unwrap();
    let cases = answers["topics"].as_array().unwrap();
    assert!(cases.len() >= 50);
    let mut some_with_hits = 0;
    for case in cases {
        let q = case["q"].as_str().unwrap().to_owned();
        let limit = case["limit"].as_u64().map(|limit| limit as u32);
        let got = mentis_ops::run(
            &Topics,
            &reader,
            ReadClass::Foreground,
            &request(
                TopicsArgs { q: Some(q.clone()) },
                Some(limit.unwrap_or(100)),
            ),
        )
        .unwrap_or_else(|why| panic!("{q:?}: {why}"));
        let page = &got.rows[0];
        let want = &case["answer"];
        let rows = serde_json::to_value(&page.topics).unwrap();
        assert_eq!(rows, want["topics"], "q {q:?}, limit {limit:?}");
        assert_eq!(json!(page.matched), want["matched"], "q {q:?}");
        if page.matched > 0 {
            some_with_hits += 1;
        }
    }
    assert!(some_with_hits >= 10, "{some_with_hits}");
}

/// A deleted Topic is never offered, a renamed one reads under its new name, and a renamed
/// Conversation is named as it now reads. What the fixture changed, said plainly.
#[test]
fn a_renamed_topic_and_a_deleted_one_are_as_a_person_should_find_them() {
    if std::env::var("MENTIS_RULES_BRAIN").is_ok() {
        return;
    }
    let reader = Brain::open(&world().0).unwrap();
    let ask = |q: &str| {
        mentis_ops::run(
            &Topics,
            &reader,
            ReadClass::Foreground,
            &request(
                TopicsArgs {
                    q: Some(q.to_owned()),
                },
                Some(100),
            ),
        )
        .unwrap()
        .rows
        .remove(0)
    };
    assert_eq!(ask("review notes").matched, 0, "deleted");
    assert_eq!(ask("magnets").topics[0].name, "Lodestones and magnets");
    assert_eq!(
        ask("revisions").topics[0].conversation_name.as_deref(),
        Some("Caf\u{e9} \u{3a3}\u{391}\u{3a3} renamed again")
    );
}

fn ids_of(reader: &dyn RecordReader, sql: &'static str) -> Vec<Id> {
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    let mut held = Vec::new();
    scope
        .query(sql, &[], &mut |row| {
            held.push(Id(row.value(0)?.text().unwrap().to_owned()));
            Ok(mentis_record::Flow::Continue)
        })
        .unwrap();
    held
}

fn spent<O: ReadOp>(
    op: &O,
    reader: &dyn RecordReader,
    request: &ReadRequest<O::Args>,
) -> (u32, O::Row)
where
    O::Row: Clone,
{
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    let answer = op.read(scope.as_mut(), request).unwrap();
    (scope.statements(), answer.rows[0].clone())
}

/// Every op's budget, stated warm, just after a commit and cold, with the position counted. The
/// figures are equal in all three because nothing is remembered: the contract's "an answer costs
/// the same just after a commit as before it".
#[test]
fn every_op_keeps_its_budget_warm_after_a_commit_and_cold() {
    let target: PathBuf = env!("CARGO_TARGET_TMPDIR").into();
    let brain = support::changed_seed(&target, "ops-budget");
    let reader = Brain::open(&brain).unwrap();
    let renamed = ids_of(
        &reader,
        "SELECT e.id FROM entry e WHERE e.def_name = 'conversation' AND e.family = 'entry' \
         AND EXISTS (SELECT 1 FROM entry l WHERE l.link_to = e.id \
                     AND l.link_relation = 'supersedes') \
         AND NOT EXISTS (SELECT 1 FROM entry l WHERE l.link_from = e.id \
                         AND l.link_relation = 'supersedes')",
    );
    assert_eq!(renamed.len(), 1);
    let at = reader.read_scope(ReadClass::Foreground).unwrap().position();
    // Behind by enough to place every kind of thing the fixture wrote, and within CAP.
    let since = format!(
        "{}.{}.{}",
        at.entry.saturating_sub(60),
        at.operational.saturating_sub(10),
        at.delivery.saturating_sub(2)
    );

    #[derive(Debug, PartialEq, Eq, Clone, Copy)]
    struct Spend {
        pulse: u32,
        pulse_since: u32,
        topics: u32,
        names: u32,
    }
    let spend = |reader: &dyn RecordReader| {
        let (pulse, row) = spent(&Pulse, reader, &request(PulseArgs { since: None }, None));
        assert_eq!(row.moved, None);
        let (pulse_since, row) = spent(
            &Pulse,
            reader,
            &request(
                PulseArgs {
                    since: Some(since.clone()),
                },
                None,
            ),
        );
        assert!(matches!(row.moved, Some(Some(_))), "{row:?}");
        let (topics, _) = spent(&Topics, reader, &request(TopicsArgs { q: None }, Some(100)));
        let (names, _) = spent(
            &Names,
            reader,
            &request(
                NamesArgs {
                    ids: renamed.clone(),
                },
                None,
            ),
        );
        Spend {
            pulse,
            pulse_since,
            topics,
            names,
        }
    };

    let warm = spend(&reader);
    println!("warm: {warm:?}");
    assert_eq!(warm.pulse, 1, "a pulse with no `since` costs its position");
    assert!(warm.pulse_since <= Pulse::BUDGET.statements, "{warm:?}");
    assert_eq!(warm.topics, Topics::BUDGET.statements, "{warm:?}");
    assert_eq!(warm.names, Names::BUDGET.statements, "{warm:?}");
    assert_eq!(spend(&reader), warm, "asked again");

    support::side("commit", &brain);
    let after_a_commit = spend(&reader);
    println!("just after a commit: {after_a_commit:?}");
    assert_eq!(after_a_commit, warm);

    drop(reader);
    let reader = Brain::open(&brain).unwrap();
    let cold = spend(&reader);
    println!("cold: {cold:?}");
    assert_eq!(cold, warm);
}

#[test]
fn a_moved_read_past_any_number_of_rows_stays_within_its_budget() {
    let target: PathBuf = env!("CARGO_TARGET_TMPDIR").into();
    let brain = support::changed_seed(&target, "ops-worst");
    let reader = Brain::open(&brain).unwrap();
    let at = reader.read_scope(ReadClass::Foreground).unwrap().position();
    let mut most = 0;
    for behind in 0..=200 {
        let since = format!(
            "{}.{}.{}",
            at.entry.saturating_sub(behind),
            at.operational.saturating_sub(behind.min(30)),
            at.delivery.saturating_sub(behind.min(2))
        );
        let (statements, _) = spent(
            &Pulse,
            &reader,
            &request(PulseArgs { since: Some(since) }, None),
        );
        most = most.max(statements);
    }
    println!(
        "most statements seen: {most}, budget {}",
        Pulse::BUDGET.statements
    );
    assert!(most <= Pulse::BUDGET.statements);
    assert!(most >= 10, "{most}: nothing here placed anything");
}
