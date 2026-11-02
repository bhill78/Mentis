//! `now_reads` and `names` against Python on a changed BRAIN-SEED (`contracts/ops.md`, "Rules"). Where
//! they disagree it is a defect. `MENTIS_RULES_BRAIN` names a Brain copy to read instead, with
//! nothing written to it, for a one-off run on a real record's history.

#[path = "support/mod.rs"]
mod support;

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::OnceLock;

use mentis_record::{Brain, BrainOpener, Id, ReadClass, RecordReader};
use mentis_rules::{NameRead, RecordRules, Rules, STATEMENTS};
use serde_json::Value;

const BATCH: usize = 400;

/// The Brain, and Python's answers on it.
fn world() -> &'static (PathBuf, Value) {
    static WORLD: OnceLock<(PathBuf, Value)> = OnceLock::new();
    WORLD.get_or_init(|| {
        let brain = match std::env::var("MENTIS_RULES_BRAIN") {
            Ok(brain) => PathBuf::from(brain),
            Err(_) => support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "rules"),
        };
        let answers = support::side("answers", &brain);
        (brain, serde_json::from_str(&answers).unwrap())
    })
}

fn all_ids() -> Vec<Id> {
    let (_, answers) = world();
    answers["now"]
        .as_object()
        .unwrap()
        .keys()
        .map(|id| Id(id.clone()))
        .collect()
}

fn reader() -> impl RecordReader {
    Brain::open(&world().0).unwrap()
}

/// A time, sent as `repr`'s text so it arrives whole.
fn number(value: &Value) -> Option<f64> {
    value.as_str()?.parse().ok()
}

#[test]
fn how_every_entry_now_reads_is_how_python_says_it_reads() {
    let (_, answers) = world();
    let reader = reader();
    let ids = all_ids();
    let mut got = HashMap::new();
    // A real record's bodies don't fit in one scope's 2 s, and needn't.
    for some in ids.chunks(BATCH) {
        let mut scope = reader.read_scope(ReadClass::Background).unwrap();
        got.extend(RecordRules.now_reads(scope.as_mut(), some).unwrap());
    }
    assert_eq!(got.len(), ids.len());
    let mut edited = 0;
    let mut deleted = 0;
    for id in &ids {
        let want = &answers["now"][&id.0];
        let have = &got[id];
        assert_eq!(have.root.0, want["root"].as_str().unwrap(), "{id}");
        let body: Value = serde_json::from_str(&have.body_json)
            .unwrap_or_else(|why| panic!("{id}'s body: {why}"));
        assert_eq!(body, want["body"], "{id}'s body");
        match (&have.revision, want["revision"].as_object()) {
            (None, None) => {}
            (Some(revision), Some(wanted)) => {
                edited += 1;
                assert_eq!(
                    u64::from(revision.versions),
                    wanted["versions"].as_u64().unwrap(),
                    "{id}"
                );
                assert_eq!(revision.current.0, wanted["current"], "{id}");
                assert_eq!(
                    Some(revision.edited_at),
                    number(&wanted["edited_at"]),
                    "{id}"
                );
                assert_eq!(
                    revision.edited_by.as_ref().map(|by| by.0.as_str()),
                    wanted["edited_by"].as_str(),
                    "{id}"
                );
            }
            (have, want) => panic!("{id}: revision {have:?} against {want:?}"),
        }
        match (&have.deleted, want["deleted"].as_object()) {
            (None, None) => {}
            (Some(found), Some(wanted)) => {
                deleted += 1;
                assert_eq!(found.record.0, wanted["record"], "{id}");
                assert_eq!(Some(found.at), number(&wanted["at"]), "{id}");
                assert_eq!(
                    found.by.as_ref().map(|by| by.0.as_str()),
                    wanted["by"].as_str(),
                    "{id}"
                );
                assert_eq!(found.because.as_deref(), wanted["because"].as_str(), "{id}");
                // `_blank`'s keys in their order, as `json.dumps` writes them: the record's text.
                let text = serde_json::to_string(&want["body"]).unwrap();
                let spaced: Vec<&str> = have.body_json.split(": ").collect();
                assert_eq!(spaced.join(":").replace(", ", ","), text, "{id}");
            }
            (have, want) => panic!("{id}: deleted {have:?} against {want:?}"),
        }
    }
    if std::env::var("MENTIS_RULES_BRAIN").is_err() {
        assert!(edited >= 5, "{edited} edited: the fixture walks nothing");
        assert!(deleted >= 4, "{deleted} deleted: the fixture walks nothing");
    }
    println!("{} entries, {edited} edited, {deleted} deleted", ids.len());
}

#[test]
fn every_id_s_name_is_what_python_shows() {
    let (_, answers) = world();
    let reader = reader();
    let mut ids = all_ids();
    ids.push(Id("ent-nothing-holds-this".into()));
    ids.push(Id("opr-nothing".into()));
    let mut got = HashMap::new();
    for some in ids.chunks(BATCH) {
        let mut scope = reader.read_scope(ReadClass::Background).unwrap();
        got.extend(mentis_rules::name_reads(scope.as_mut(), some).unwrap());
    }
    let want = answers["names"].as_object().unwrap();
    let mut forwarded = 0;
    for id in &ids {
        match (got.get(id), want.get(&id.0)) {
            (None, None) => {}
            (Some(NameRead::Named(name)), Some(wanted)) => {
                assert_eq!(wanted.as_str(), Some(name.as_str()), "{id}");
            }
            (Some(NameRead::Unnamed), Some(wanted)) => {
                assert_eq!(wanted.as_str(), Some(id.0.as_str()), "{id}");
            }
            // Python's to say: that it isn't text is what makes it so.
            (Some(NameRead::NotPlain), Some(wanted)) => {
                forwarded += 1;
                assert!(!wanted.is_string(), "{id}: {wanted}");
            }
            (have, wanted) => panic!("{id}: {have:?} against {wanted:?}"),
        }
    }
    println!("{forwarded} names left to Python");
}

#[test]
fn the_trait_answers_what_the_functions_do() {
    let reader = reader();
    let ids: Vec<Id> = all_ids().into_iter().take(BATCH).collect();
    let mut scope = reader.read_scope(ReadClass::Background).unwrap();
    let names = RecordRules.names(scope.as_mut(), &ids).unwrap();
    let reads = mentis_rules::name_reads(scope.as_mut(), &ids).unwrap();
    let shown: HashMap<_, _> = reads
        .into_iter()
        .map(|(id, read)| match read {
            NameRead::Named(name) => (id, Some(name)),
            _ => (id, None),
        })
        .collect();
    assert_eq!(names, shown);
    // Against Python in `mentis-ops/tests/agent_reads.rs`, as its answers are made there.
    let standing = RecordRules.standing_many(scope.as_mut(), &ids, None);
    assert_eq!(
        standing.unwrap(),
        mentis_rules::standing_many(scope.as_mut(), &ids, None).unwrap()
    );
}

#[test]
fn nothing_asked_costs_no_statement() {
    let reader = reader();
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    let before = scope.statements();
    assert!(
        RecordRules
            .now_reads(scope.as_mut(), &[])
            .unwrap()
            .is_empty()
    );
    assert!(RecordRules.names(scope.as_mut(), &[]).unwrap().is_empty());
    assert_eq!(scope.statements(), before);
}

/// Deleted entries with bodies of every shape, which no command writes and the record can still
/// hold (`python_side.py`, `odd`). The generated fixture has only objects.
fn odd_bodies(name: &str) -> (impl RecordReader, Vec<Value>) {
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), name);
    let said: Value = serde_json::from_str(&support::side("odd", &brain)).unwrap();
    (
        Brain::open(&brain).unwrap(),
        said["cases"].as_array().unwrap().clone(),
    )
}

/// A reason Python holds that isn't text: `Deleted.because` has no way to say it, so it is left to
/// Python, though Python doesn't raise.
fn because_is_not_text(now: &Value) -> bool {
    !now["because"].is_null() && !now["because"].is_string()
}

#[test]
fn a_deleted_entry_python_can_read_reads_as_python_says_whatever_its_body_is() {
    let (reader, cases) = odd_bodies("rules-odd");
    let mut answered = 0;
    let readable = |case: &&Value| {
        let now = case["now"].get("answer");
        now.is_some_and(|now| !because_is_not_text(now))
    };
    for case in cases.iter().filter(readable) {
        let id = Id(case["id"].as_str().unwrap().to_owned());
        let want = &case["now"]["answer"];
        let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
        let got = RecordRules
            .now_reads(scope.as_mut(), std::slice::from_ref(&id))
            .unwrap_or_else(|why| panic!("{case}: {why}"));
        let have = &got[&id];
        let body: Value = serde_json::from_str(&have.body_json)
            .unwrap_or_else(|why| panic!("{case}: {why}, {:?}", have.body_json));
        assert_eq!(body, want["body"], "{case}");
        let deleted = have.deleted.as_ref().unwrap();
        assert_eq!(deleted.record.0, want["deleted"], "{case}");
        assert_eq!(
            deleted.because.as_deref(),
            want["because"].as_str(),
            "{case}"
        );
        answered += 1;
    }
    println!("{answered} of {} read as Python's", cases.len());
    assert!(answered >= 30, "{answered}");
}

#[test]
fn a_name_is_python_s_name_or_python_s_to_say_whatever_the_body_is() {
    let (reader, cases) = odd_bodies("rules-odd-names");
    let (mut named, mut left) = (0, 0);
    for case in &cases {
        let id = Id(case["id"].as_str().unwrap().to_owned());
        let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
        let got = mentis_rules::name_reads(scope.as_mut(), std::slice::from_ref(&id))
            .unwrap_or_else(|why| panic!("{case}: {why}"));
        match (&got[&id], case["name"].get("answer")) {
            (NameRead::NotPlain, _) => left += 1,
            (NameRead::Unnamed, Some(wanted)) => {
                named += 1;
                assert_eq!(wanted.as_str(), Some(id.0.as_str()), "{case}");
            }
            (NameRead::Named(name), Some(wanted)) => {
                named += 1;
                assert_eq!(wanted.as_str(), Some(name.as_str()), "{case}");
            }
            (have, _) => panic!("{case}: {have:?}, where Python failed"),
        }
    }
    println!("{named} named as Python's, {left} left to Python");
    assert!(named >= 20 && left >= 5, "{named}, {left}");
}

#[test]
fn a_deleted_entry_python_can_t_read_says_so_and_holds_nothing() {
    let (reader, cases) = odd_bodies("rules-odd-raises");
    let mut left = 0;
    for case in &cases {
        let id = Id(case["id"].as_str().unwrap().to_owned());
        let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
        let got = RecordRules
            .now_reads(scope.as_mut(), std::slice::from_ref(&id))
            .unwrap_or_else(|why| panic!("{case}: {why}"));
        let have = &got[&id];
        let answered = case["now"].get("answer");
        assert_eq!(
            have.python_says,
            answered.is_none_or(because_is_not_text),
            "{case}"
        );
        if have.python_says {
            left += 1;
            assert_eq!(have.body_json, "", "{case}");
            assert!(have.deleted.is_some(), "{case}");
        }
    }
    println!("{left} of {} left to Python", cases.len());
    assert!(left >= 18, "{left}");
}

/// Whatever is asked, however many, and warm, just after a commit, or cold.
#[test]
fn the_statements_are_fixed_per_call_warm_after_a_commit_and_cold() {
    let target: PathBuf = env!("CARGO_TARGET_TMPDIR").into();
    let brain = support::changed_seed(&target, "rules-budget");
    let reader = Brain::open(&brain).unwrap();
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    let ids: Vec<Id> = {
        let mut held = Vec::new();
        scope
            .query("SELECT id FROM entry", &[], &mut |row| {
                held.push(Id(row.value(0)?.text().unwrap().to_owned()));
                Ok(mentis_record::Flow::Continue)
            })
            .unwrap();
        held
    };
    // A Conversation that was renamed: its later versions aren't among what was asked, so the
    // fourth statement has to read them. This is the worst a call does.
    let mut renamed = Vec::new();
    scope
        .query(
            "SELECT e.id FROM entry e WHERE e.def_name = 'conversation' AND e.family = 'entry' \
             AND EXISTS (SELECT 1 FROM entry l WHERE l.link_to = e.id \
                         AND l.link_relation = 'supersedes') \
             AND NOT EXISTS (SELECT 1 FROM entry l WHERE l.link_from = e.id \
                             AND l.link_relation = 'supersedes')",
            &[],
            &mut |row| {
                renamed.push(Id(row.value(0)?.text().unwrap().to_owned()));
                Ok(mentis_record::Flow::Continue)
            },
        )
        .unwrap();
    assert_eq!(renamed.len(), 1);
    drop(scope);

    let spend = |reader: &dyn RecordReader, ids: &[Id]| {
        let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
        let at_start = scope.statements();
        RecordRules.now_reads(scope.as_mut(), ids).unwrap();
        let now_reads = scope.statements() - at_start;
        let at_start = scope.statements();
        RecordRules.names(scope.as_mut(), ids).unwrap();
        (now_reads, scope.statements() - at_start)
    };

    // Warm: the same reader, asked again. However many are asked, it is never more.
    let warm_one = spend(&reader, &renamed);
    assert_eq!(warm_one, (STATEMENTS, STATEMENTS));
    assert_eq!(spend(&reader, &renamed), warm_one);
    let warm_all = spend(&reader, &ids);
    assert!(
        warm_all.0 <= STATEMENTS && warm_all.1 <= STATEMENTS,
        "{warm_all:?}"
    );
    assert_eq!(spend(&reader, &ids), warm_all);

    // Just after a commit: the same, with nothing remembered to throw away.
    support::side("commit", &brain);
    assert_eq!(spend(&reader, &renamed), warm_one);
    assert_eq!(spend(&reader, &ids), warm_all);

    // Cold.
    drop(reader);
    let cold = Brain::open(&brain).unwrap();
    assert_eq!(spend(&cold, &renamed), warm_one);
    assert_eq!(spend(&cold, &ids), warm_all);
}
