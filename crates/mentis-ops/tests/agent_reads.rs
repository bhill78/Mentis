//! R3's reads against Python's on a changed BRAIN-SEED, **facts only.** What is compared is what
//! each op says against what Python's read says with the door's words taken off
//! (`support/agent_reads_side.py`), as JSON values. The door's wording and framing aren't built, so
//! **byte equality on the wire is not shown here.**
//!
//! `MENTIS_R3_BRAIN` names a Brain copy for the ignored test below, sampled, with nothing written by
//! the op side and the copy's content checked after.

#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use mentis_ops::capabilities::Capabilities;
use mentis_ops::governed::{Governed, GovernedArgs};
use mentis_ops::history::{History, HistoryArgs};
use mentis_ops::kinds::{Kinds, KindsArgs};
use mentis_ops::owner_decisions::{OwnerDecisions, OwnerDecisionsArgs};
use mentis_ops::resolve::{Resolve, ResolveArgs};
use mentis_ops::set_changes::{SetChanges, SetChangesArgs};
use mentis_ops::{Cursor, Id, OpError, ReadAnswer, ReadClass, ReadOp, ReadRequest};
use mentis_record::{Brain, BrainOpener, RecordError, RecordReader};
use serde::Serialize;
use serde_json::{Value, json};

fn side(arg: &str, brain: &Path) -> String {
    let script = support::repo_root()
        .join("crates")
        .join("mentis-ops")
        .join("tests")
        .join("support")
        .join("agent_reads_side.py");
    let done = support::python()
        .arg(script)
        .arg(arg)
        .arg(brain)
        .output()
        .expect("Python starts");
    assert!(
        done.status.success(),
        "Python failed: {}",
        String::from_utf8_lossy(&done.stderr)
    );
    String::from_utf8(done.stdout).expect("Python's output is UTF-8")
}

fn changed(name: &str) -> PathBuf {
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), name);
    side("change", &brain);
    brain
}

fn world() -> &'static (PathBuf, Value) {
    static WORLD: OnceLock<(PathBuf, Value)> = OnceLock::new();
    WORLD.get_or_init(|| {
        let brain = changed("agent-reads");
        let answers = side("answers", &brain);
        (brain, serde_json::from_str(&answers).unwrap())
    })
}

fn request<A>(args: A, limit: Option<u32>, cursor: Option<&str>) -> ReadRequest<A> {
    ReadRequest {
        args,
        cursor: cursor.map(|cursor| Cursor(cursor.to_owned())),
        limit,
        deadline: Instant::now() + Duration::from_secs(20),
    }
}

/// As JSON text and back, so both sides' floats go through one parser from their shortest digits.
fn json_of<T: Serialize>(value: &T) -> Value {
    serde_json::from_str(&serde_json::to_string(value).unwrap()).unwrap()
}

fn page<O: ReadOp>(
    op: &O,
    reader: &dyn RecordReader,
    asked: &ReadRequest<O::Args>,
) -> Result<ReadAnswer<O::Row>, OpError> {
    mentis_ops::run(op, reader, ReadClass::Agent, asked)
}

fn only<R: Serialize>(answer: &ReadAnswer<R>) -> Value {
    assert_eq!(answer.rows.len(), 1);
    json_of(&answer.rows[0])
}

/// Python's `known: true` answers carry `has_standing_sentence` for a Kind on a ladder, and the op
/// carries the Kind's `knowing`: the fact the door chooses the sentence by.
fn resolve_row_as_python_s(mut row: Value) -> Value {
    let map = row.as_object_mut().unwrap();
    if map.remove("knowing").is_some() {
        map.insert("has_standing_sentence".into(), json!(true));
    }
    row
}

#[test]
fn capabilities_name_what_python_names() {
    let (brain, answers) = world();
    let reader = Brain::open(brain).unwrap();
    let got = page(&Capabilities, &reader, &request((), None, None)).unwrap();
    assert_eq!(only(&got), answers["capabilities"]);
}

#[test]
fn kinds_count_and_split_as_python_does() {
    let (brain, answers) = world();
    let reader = Brain::open(brain).unwrap();
    let at = answers["at"].as_f64().unwrap();
    let got = page(&Kinds, &reader, &request(KindsArgs { at }, None, None)).unwrap();
    assert_eq!(only(&got), answers["kinds"]);
    // Something of every ground, or this says little.
    let grounds: Vec<&str> = answers["kinds"]["kinds"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| row["ground"].as_str().unwrap())
        .collect();
    for ground in [
        "directs_work",
        "standing_knowledge",
        "standing_not_meaningful",
    ] {
        assert!(grounds.contains(&ground), "no {ground} in {grounds:?}");
    }
}

#[test]
fn kinds_reads_no_clock_of_its_own() {
    let reader = Brain::open(&world().0).unwrap();
    let at = |at: f64| {
        let got = page(&Kinds, &reader, &request(KindsArgs { at }, None, None)).unwrap();
        got.rows[0].as_read_at.clone()
    };
    assert_eq!(at(0.0), "1970-01-01T00:00:00Z");
    assert_eq!(at(0.0), at(0.0));
    assert_eq!(at(1793500123.456), "2026-11-01T02:28:43Z");
}

#[test]
fn history_answers_as_python_s_at_every_filter_and_limit() {
    let (brain, answers) = world();
    let reader = Brain::open(brain).unwrap();
    let cases = answers["history"].as_array().unwrap();
    assert!(cases.len() >= 80, "{}", cases.len());
    let (mut with_acts, mut marked) = (0, 0);
    for case in cases {
        let text = |key: &str| case["args"][key].as_str().map(str::to_owned);
        let args = HistoryArgs {
            conversation: text("conversation"),
            turn: text("turn"),
            participant: text("participant"),
        };
        let limit = case["limit"].as_u64().unwrap() as u32;
        let got = page(&History, &reader, &request(args, Some(limit), None))
            .unwrap_or_else(|why| panic!("{case}: {why}"));
        assert_eq!(got.more, None, "this read has no continuation");
        let want = &case["answer"];
        assert_eq!(only(&got), *want, "{}", case["args"]);
        let acts = want["acts"].as_array().unwrap();
        with_acts += usize::from(!acts.is_empty());
        marked += acts.iter().filter(|a| a.get("deleted").is_some()).count();
    }
    assert!(with_acts >= 40, "{with_acts}");
    assert!(marked >= 1, "no act was marked as deleted material");
}

#[test]
fn a_history_limit_past_the_op_s_most_goes_to_python() {
    let reader = Brain::open(&world().0).unwrap();
    let args = HistoryArgs::default();
    let over = request(args, Some(History::MOST + 1), None);
    assert!(matches!(
        page(&History, &reader, &over),
        Err(OpError::NotOwned { .. })
    ));
}

#[test]
fn a_set_s_changes_answer_as_python_s_or_go_to_python() {
    let (brain, answers) = world();
    let reader = Brain::open(brain).unwrap();
    let cases = answers["set_changes"].as_array().unwrap();
    let (mut sets, mut forms, mut refused, mut forwarded) = (0, 0, 0, 0);
    for case in cases {
        let set = case["set"].as_str().unwrap().to_owned();
        let since = case["since"].as_str();
        let limit = case["limit"].as_u64().unwrap() as u32;
        let got = page(
            &SetChanges,
            &reader,
            &request(SetChangesArgs { set }, Some(limit), since),
        );
        let want = &case["answer"];
        match got {
            Ok(answer) => {
                assert_eq!(want.get("refused"), None, "{case}");
                let mut row = only(&answer);
                let map = row.as_object_mut().unwrap();
                map.insert("more".into(), json!(answer.more.is_some()));
                assert_eq!(row, *want, "{}", case["set"]);
                if let Some(more) = &answer.more {
                    assert_eq!(json!(more.0), want["cursor"]);
                }
                if want.get("decision_form").is_some() {
                    forms += 1;
                } else {
                    sets += 1;
                }
            }
            Err(OpError::BadRequest { why }) | Err(OpError::NotFound { what: why }) => {
                assert_eq!(want["refused"], json!(true), "{case}");
                assert_eq!(json!(why), want["why_not"], "{case}");
                refused += 1;
            }
            Err(OpError::NotOwned { why }) => {
                println!("forwarded: {why}: {}", case["set"]);
                forwarded += 1;
            }
            Err(other) => panic!("{case}: {other}"),
        }
    }
    println!("{sets} sets, {forms} forms, {refused} refused, {forwarded} forwarded");
    assert!(
        sets >= 20 && forms >= 40 && refused >= 20,
        "{sets} {forms} {refused}"
    );
    // The interpretation's page, and `since` it can't repr.
    assert!(forwarded >= 1, "{forwarded}");
}

#[test]
fn owner_decisions_answer_as_python_s() {
    let (brain, answers) = world();
    let reader = Brain::open(brain).unwrap();
    let cases = answers["owner_decisions"].as_array().unwrap();
    let (mut with_some, mut not_found) = (0, 0);
    for case in cases {
        let conversation = case["conversation"].as_str().unwrap().to_owned();
        let most = case["most"].as_u64().map(|most| most as u32);
        let got = page(
            &OwnerDecisions,
            &reader,
            &request(OwnerDecisionsArgs { conversation }, most, None),
        );
        let want = &case["answer"];
        match got {
            Ok(answer) => {
                assert_eq!(only(&answer), *want, "{case}");
                with_some += usize::from(want["open_count"].as_u64().unwrap() > 0);
            }
            Err(OpError::NotFound { .. }) => {
                assert_eq!(want["refused"], json!(true), "{case}");
                not_found += 1;
            }
            Err(other) => panic!("{case}: {other}"),
        }
    }
    assert!(with_some >= 4 && not_found >= 4, "{with_some}, {not_found}");
}

#[test]
fn governed_answers_as_python_s_at_every_question() {
    let (brain, answers) = world();
    let reader = Brain::open(brain).unwrap();
    let cases = answers["governed"].as_array().unwrap();
    let (mut pages, mut refused) = (0, 0);
    for case in cases {
        let args = &case["args"];
        let text = |key: &str| args[key].as_str().map(str::to_owned);
        let asked = request(
            GovernedArgs {
                kind: text("kind"),
                q: text("q"),
                state: text("state"),
            },
            Some(case["limit"].as_u64().unwrap() as u32),
            args["cursor"].as_str(),
        );
        let want = &case["answer"];
        match page(&Governed, &reader, &asked) {
            Ok(answer) => {
                assert_eq!(only(&answer), *want, "{args}");
                if let Some(next) = want.get("next_cursor").and_then(Value::as_str) {
                    assert_eq!(answer.more.as_ref().map(|c| c.0.as_str()), Some(next));
                } else {
                    assert_eq!(answer.more, None, "{args}");
                }
                pages += 1;
            }
            Err(OpError::BadRequest { why }) => {
                assert_eq!(json!(why), want["error"], "{args}");
                refused += 1;
            }
            // `repr` of what isn't plain, which is Python's to show.
            Err(OpError::NotOwned { why }) => {
                assert!(want.get("error").is_some(), "{args}: {why}");
            }
            Err(other) => panic!("{args}: {other}"),
        }
    }
    println!("{pages} pages, {refused} refused");
    assert!(pages >= 40 && refused >= 5, "{pages}, {refused}");

    // Every ground, group and field this read has, or the grid above says little.
    let whole = cases
        .iter()
        .find(|case| case["args"] == json!({}))
        .map(|case| &case["answer"])
        .or_else(|| {
            cases
                .iter()
                .find(|case| case["args"] == json!({"kind": null}))
                .map(|case| &case["answer"])
        })
        .unwrap();
    for group in ["proposed", "recorded", "standing", "history"] {
        assert!(
            whole["totals"][group].as_u64().unwrap() > 0,
            "no {group}: {whole}"
        );
    }
    let rows: Vec<&Value> = ["proposed", "recorded", "standing", "history"]
        .iter()
        .flat_map(|group| whole["groups"][group].as_array().unwrap())
        .collect();
    let any = |what: &dyn Fn(&Value) -> bool| rows.iter().any(|row| what(row));
    assert!(any(&|r| r["placed_at"][0].get("whole_brain").is_some()));
    assert!(any(&|r| r["placed_at"][0].get("persona").is_some()));
    assert!(any(&|r| !r["proposed_by"].as_array().unwrap().is_empty()));
    assert!(any(&|r| !r["open_disputes"].as_array().unwrap().is_empty()));
    assert!(any(&|r| !r["supersedes"].as_array().unwrap().is_empty()));
    assert!(any(
        &|r| r["proposed"]["successors"]["omitted"].as_u64() > Some(0)
    ));
    assert!(any(&|r| r["proposed"]["successors"]["withdrawn"].as_u64()
        > Some(0)
        || r["proposed"]["predecessors"]["withdrawn"].as_u64()
            > Some(0)));
}

/// Every entry the record holds: the same facts as Python, or forwarded for a stated reason.
#[test]
fn every_entry_resolves_as_python_s_or_goes_to_python() {
    let (brain, answers) = world();
    let reader = Brain::open(brain).unwrap();
    let asked = answers["resolve"].as_object().unwrap();
    let mut same: BTreeMap<String, u32> = BTreeMap::new();
    let mut forwarded: BTreeMap<String, u32> = BTreeMap::new();
    let mut not_found = 0;
    for (reference, want) in asked {
        let args = ResolveArgs {
            reference: reference.clone(),
        };
        match page(&Resolve, &reader, &request(args, None, None)) {
            Ok(answer) => {
                let raises = want.get("raises");
                assert_eq!(raises, None, "{reference}: Python raised and this answered");
                let row = resolve_row_as_python_s(only(&answer));
                assert_eq!(row, want["answer"], "{reference}");
                *same
                    .entry(want["answer"]["what"].as_str().unwrap().to_owned())
                    .or_default() += 1;
            }
            Err(OpError::NotOwned { why }) => *forwarded.entry(why).or_default() += 1,
            Err(OpError::NotFound { .. }) => {
                assert_eq!(want["answer"]["ref"], json!(reference), "{reference}");
                assert_eq!(want["answer"].get("what"), None, "{reference}");
                assert!(want["answer"].get("why_not").is_some(), "{reference}");
                not_found += 1;
            }
            Err(other) => panic!("{reference}: {other}"),
        }
    }
    println!("answered: {same:#?}\nforwarded: {forwarded:#?}\nnot found: {not_found}");
    assert_eq!(not_found, 1);
    for what in [
        "a Turn",
        "a Conversation",
        "a Participant",
        "a Topic",
        "a Reaction",
        "a Link",
    ] {
        assert!(
            same.get(what).is_some_and(|n| *n > 0),
            "none of {what}: {same:?}"
        );
    }
    assert!(
        same.keys().any(|what| what.starts_with("an entry of kind")),
        "{same:?}"
    );
    for why in [
        "a held artifact: held files",
        "an acquired observation: held files",
        "a response set: the render engine",
        "a Turn with a response set: the render engine",
        "a Turn with a fillable block: the render engine",
        "an Anchor",
        "a Turn holding an anchor part",
    ] {
        assert!(
            forwarded.contains_key(why),
            "nothing forwarded as {why}: {forwarded:#?}"
        );
    }
}

/// `decision_forms` in `resolve` is the hardest of what moves, so it is asked for by name.
#[test]
fn decision_forms_on_a_turn_read_as_python_s() {
    let (brain, answers) = world();
    let reader = Brain::open(brain).unwrap();
    let mut forms = 0;
    let (mut answered, mut withdrawn, mut lapsed, mut open, mut pending_then_put) = (0, 0, 0, 0, 0);
    for (reference, want) in answers["resolve"].as_object().unwrap() {
        let Some(on) = want["answer"].get("decision_forms") else {
            continue;
        };
        let args = ResolveArgs {
            reference: reference.clone(),
        };
        let got = page(&Resolve, &reader, &request(args, None, None))
            .unwrap_or_else(|why| panic!("{reference}: {why}"));
        assert_eq!(resolve_row_as_python_s(only(&got)), want["answer"]);
        for form in on.as_array().unwrap() {
            forms += 1;
            pending_then_put += usize::from(form["on"].is_null() && !form["post"].is_null());
            for q in form["questions"].as_array().unwrap() {
                answered += usize::from(!q["answer"].is_null());
                withdrawn += usize::from(!q["withdrawn"].is_null());
                lapsed += usize::from(!q["lapsed"].is_null());
                open += usize::from(q["open"] == json!(true));
            }
        }
    }
    println!(
        "{forms} forms: {answered} answered, {withdrawn} withdrawn, {lapsed} lapsed, {open} open"
    );
    assert!(forms >= 4, "{forms}");
    assert!(answered >= 2 && withdrawn >= 1 && lapsed >= 1 && open >= 2);
    assert!(pending_then_put >= 1);
}

#[test]
fn standing_many_says_what_stands_says_now_and_as_at_a_time() {
    let (brain, answers) = world();
    let reader = Brain::open(brain).unwrap();
    let as_at = answers["as_at"].as_f64().unwrap();
    let asked = answers["standing"].as_object().unwrap();
    let ids: Vec<Id> = asked.keys().cloned().map(Id).collect();
    let mut scope = reader.read_scope(ReadClass::Agent).unwrap();
    let before = scope.statements();
    let now = mentis_ops::rules::standing_many(scope.as_mut(), &ids, None).unwrap();
    assert_eq!(
        scope.statements() - before,
        mentis_ops::rules::STANDING_STATEMENTS
    );
    let then = mentis_ops::rules::standing_many(scope.as_mut(), &ids, Some(as_at)).unwrap();

    let shown = |standing: &mentis_ops::rules::Standing| {
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
    };
    let (mut stands, mut differs_then) = (0, 0);
    for id in &ids {
        let want = &asked[&id.0];
        assert_eq!(shown(&now[id]), want["now"], "{id}, now");
        assert_eq!(shown(&then[id]), want["then"], "{id}, as at {as_at}");
        stands += usize::from(now[id].stands);
        differs_then += usize::from(want["now"] != want["then"]);
    }
    println!(
        "{} ids, {stands} stand, {differs_then} differ as at {as_at}",
        ids.len()
    );
    assert!(stands >= 5 && differs_then >= 5, "{stands}, {differs_then}");
}

/// All seven, whoever asks: an op takes no grant, no door and no route, because it has none to take.
/// This file reaches them with `mentis-ops` and `mentis-record` alone, and each class's pool gives
/// the same answer, so a Magnet's `Background` read is the agent's read.
#[test]
fn each_op_runs_with_no_grant_door_or_route_in_reach_and_answers_every_class_alike() {
    let (brain, answers) = world();
    let reader = Brain::open(brain).unwrap();
    let at = answers["at"].as_f64().unwrap();
    let (known, reference) = known_conversation(&reader);

    fn alike<O: ReadOp>(op: &O, reader: &dyn RecordReader, args: impl Fn() -> O::Args)
    where
        O::Row: Serialize,
    {
        let mut seen: Vec<Value> = Vec::new();
        for class in [
            ReadClass::Foreground,
            ReadClass::Agent,
            ReadClass::Background,
            ReadClass::Connector,
        ] {
            let asked = request(args(), None, None);
            let got = mentis_ops::run(op, reader, class, &asked).expect(O::NAME);
            seen.push(json_of(&got));
        }
        assert!(
            seen.windows(2).all(|pair| pair[0] == pair[1]),
            "{}",
            O::NAME
        );
    }
    alike(&Capabilities, &reader, || ());
    alike(&Kinds, &reader, || KindsArgs { at });
    alike(&History, &reader, HistoryArgs::default);
    alike(&OwnerDecisions, &reader, || OwnerDecisionsArgs {
        conversation: known.clone(),
    });
    alike(&Governed, &reader, GovernedArgs::default);
    alike(&Resolve, &reader, || ResolveArgs {
        reference: reference.clone(),
    });
    let form = answers["set_changes"]
        .as_array()
        .unwrap()
        .iter()
        .find(|case| case["answer"].get("decision_form").is_some())
        .expect("a decision form");
    alike(&SetChanges, &reader, || SetChangesArgs {
        set: form["set"].as_str().unwrap().to_owned(),
    });
}

fn known_conversation(reader: &dyn RecordReader) -> (String, String) {
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    let mut found = None;
    scope
        .query(
            "SELECT e.id FROM entry e WHERE e.def_name = 'conversation' AND e.family = 'entry' \
             AND e.link_relation IS NULL \
             AND json_extract(e.body, '$.name') = 'R1 known conversation'",
            &[],
            &mut |row| {
                found = row.value(0)?.text().map(str::to_owned);
                Ok(mentis_record::Flow::Stop)
            },
        )
        .unwrap();
    let known = found.expect("the known conversation");
    (known.clone(), known)
}

/// The modules can't reach what they must not know of. `Cargo.toml` is what stops a dependency, and
/// this says what would be the first sign of one.
#[test]
fn no_op_names_a_grant_a_door_a_route_or_a_class() {
    let source = support::repo_root()
        .join("crates")
        .join("mentis-ops")
        .join("src");
    for module in [
        "capabilities.rs",
        "kinds.rs",
        "history.rs",
        "set_changes.rs",
        "owner_decisions.rs",
        "governed.rs",
        "resolve.rs",
        "forms.rs",
        "turn_line.rs",
        "vocabulary.rs",
        "stored.rs",
        "acts.rs",
    ] {
        let text = std::fs::read_to_string(source.join(module)).unwrap();
        for (number, line) in text.lines().enumerate() {
            let code = line.split("//").next().unwrap().to_lowercase();
            for word in [
                "grant",
                "permitted",
                "permits",
                "mirror",
                "lease",
                "/api/",
                "readclass",
                "system_time",
                "systemtime",
                "instant::now",
                "std::fs",
                "std::env",
                "mentis_server",
            ] {
                assert!(
                    !code.contains(word),
                    "{module}:{}: `{word}` in `{line}`",
                    number + 1
                );
            }
        }
    }
    let manifest = std::fs::read_to_string(
        support::repo_root()
            .join("crates")
            .join("mentis-ops")
            .join("Cargo.toml"),
    )
    .unwrap();
    assert!(!manifest.contains("mentis-server"));
}

fn most_statements<O: ReadOp>(
    op: &O,
    reader: &dyn RecordReader,
    asked: impl Iterator<Item = ReadRequest<O::Args>>,
) -> u32 {
    let mut most = 0;
    for one in asked {
        let mut scope = reader.read_scope(ReadClass::Agent).unwrap();
        // Whatever the answer is, what it cost is what is asked here.
        let _ = op.read(scope.as_mut(), &one);
        most = most.max(scope.statements());
    }
    most
}

/// Every op's budget, warm, just after a commit and cold. The same in all three because nothing is
/// remembered (`contracts/ops.md`), over the questions that cost each one most.
#[test]
fn every_agent_read_keeps_its_budget_warm_after_a_commit_and_cold() {
    let brain = changed("agent-reads-budget");
    let answers: Value = serde_json::from_str(&side("answers", &brain)).unwrap();
    let references: Vec<String> = answers["resolve"]
        .as_object()
        .unwrap()
        .keys()
        .cloned()
        .collect();
    let sets: Vec<String> = answers["set_changes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|case| case["set"].as_str().unwrap().to_owned())
        .collect();
    let conversations: Vec<String> = answers["owner_decisions"]
        .as_array()
        .unwrap()
        .iter()
        .map(|case| case["conversation"].as_str().unwrap().to_owned())
        .collect();

    let spend = |reader: &dyn RecordReader| {
        [
            (
                Resolve::NAME,
                Resolve::BUDGET.statements,
                most_statements(
                    &Resolve,
                    reader,
                    references.iter().map(|reference| {
                        request(
                            ResolveArgs {
                                reference: reference.clone(),
                            },
                            None,
                            None,
                        )
                    }),
                ),
            ),
            (
                Kinds::NAME,
                Kinds::BUDGET.statements,
                most_statements(
                    &Kinds,
                    reader,
                    std::iter::once(request(KindsArgs { at: 0.0 }, None, None)),
                ),
            ),
            (
                Capabilities::NAME,
                Capabilities::BUDGET.statements,
                most_statements(
                    &Capabilities,
                    reader,
                    std::iter::once(request((), None, None)),
                ),
            ),
            (
                History::NAME,
                History::BUDGET.statements,
                most_statements(
                    &History,
                    reader,
                    [40, 1000]
                        .into_iter()
                        .map(|limit| request(HistoryArgs::default(), Some(limit), None)),
                ),
            ),
            (
                SetChanges::NAME,
                SetChanges::BUDGET.statements,
                most_statements(
                    &SetChanges,
                    reader,
                    sets.iter()
                        .map(|set| request(SetChangesArgs { set: set.clone() }, None, None)),
                ),
            ),
            (
                OwnerDecisions::NAME,
                OwnerDecisions::BUDGET.statements,
                most_statements(
                    &OwnerDecisions,
                    reader,
                    conversations.iter().map(|conversation| {
                        request(
                            OwnerDecisionsArgs {
                                conversation: conversation.clone(),
                            },
                            None,
                            None,
                        )
                    }),
                ),
            ),
            (
                Governed::NAME,
                Governed::BUDGET.statements,
                most_statements(
                    &Governed,
                    reader,
                    std::iter::once(request(GovernedArgs::default(), Some(1000), None)),
                ),
            ),
        ]
    };
    let reader = Brain::open(&brain).unwrap();
    let warm = spend(&reader);
    println!("warm: {warm:?}");
    for (name, budget, spent) in warm {
        assert!(spent <= budget, "{name} ran {spent}, budget {budget}");
    }
    assert_eq!(spend(&reader), warm, "asked again");

    side("commit", &brain);
    let after_a_commit = spend(&reader);
    println!("just after a commit: {after_a_commit:?}");
    assert_eq!(after_a_commit, warm);

    drop(reader);
    let reader = Brain::open(&brain).unwrap();
    let cold = spend(&reader);
    println!("cold: {cold:?}");
    assert_eq!(cold, warm);
}

/// `run` holds these to a request's deadline as it holds every op.
#[test]
fn a_request_past_its_deadline_is_busy_at_every_agent_read() {
    fn late<O: ReadOp>(op: &O, reader: &dyn RecordReader, args: O::Args) {
        let mut asked = request(args, None, None);
        asked.deadline = Instant::now();
        let got = mentis_ops::run(op, reader, ReadClass::Agent, &asked);
        assert!(matches!(got, Err(OpError::Busy { .. })), "{}", O::NAME);
    }
    let reader = Brain::open(&world().0).unwrap();
    late(&Capabilities, &reader, ());
    late(&Kinds, &reader, KindsArgs::default());
    late(&History, &reader, HistoryArgs::default());
    late(&SetChanges, &reader, SetChangesArgs::default());
    late(&OwnerDecisions, &reader, OwnerDecisionsArgs::default());
    late(&Governed, &reader, GovernedArgs::default());
    late(&Resolve, &reader, ResolveArgs::default());
}

/// On a Brain copy: every read sampled, and the copy's bytes left as they were by the op side. Run
/// by hand with `MENTIS_R3_BRAIN`, which makes Python read the whole copy first.
#[test]
#[ignore = "needs MENTIS_R3_BRAIN, a Brain copy, and minutes of Python"]
fn on_a_brain_copy_every_read_agrees_or_forwards() {
    let brain = PathBuf::from(std::env::var("MENTIS_R3_BRAIN").expect("MENTIS_R3_BRAIN"));
    let started = Instant::now();
    let answers: Value = serde_json::from_str(&side("answers-copy", &brain)).unwrap();
    println!("python, the whole sample: {:?}", started.elapsed());
    // After Python, which may checkpoint what it opened, and before anything here reads it.
    let corpus_db = brain.join("corpus.db");
    let bytes_before = std::fs::read(&corpus_db).unwrap();
    let reader = Brain::open(&brain).unwrap();
    let at = answers["at"].as_f64().unwrap();

    let got = page(&Capabilities, &reader, &request((), None, None)).unwrap();
    assert_eq!(only(&got), answers["capabilities"]);

    let mut report: BTreeMap<&str, BTreeMap<String, u32>> = BTreeMap::new();
    let mut count = |op: &'static str, what: String| {
        *report.entry(op).or_default().entry(what).or_default() += 1;
    };

    // Timed, and never a gate. Past the scope's limit a read is forwarded or expired, not wrong, and
    // is counted so the report says how much of the sample was really compared. `kinds` and
    // `owner_decisions` forward a failed read, so it comes here as `NotOwned` with the failure's words.
    const PAST_LIMIT: &str = "past the scope's limit";
    let started = Instant::now();
    match page(&Kinds, &reader, &request(KindsArgs { at }, None, None)) {
        Ok(answer) => {
            println!("kinds: {:?}", started.elapsed());
            assert_eq!(only(&answer), answers["kinds"]);
            count("kinds", "same".into());
        }
        Err(OpError::NotOwned { why }) => {
            println!("kinds: {:?}, forwarded", started.elapsed());
            count("kinds", why);
        }
        Err(other) => panic!("kinds: {other}"),
    }

    let started = Instant::now();
    for case in answers["history"].as_array().unwrap() {
        let text = |key: &str| case["args"][key].as_str().map(str::to_owned);
        let args = HistoryArgs {
            conversation: text("conversation"),
            turn: text("turn"),
            participant: text("participant"),
        };
        let limit = case["limit"].as_u64().unwrap() as u32;
        match page(&History, &reader, &request(args, Some(limit), None)) {
            Ok(answer) => {
                assert_eq!(only(&answer), case["answer"], "history {}", case["args"]);
                count("history", "same".into());
            }
            Err(OpError::NotOwned { why }) => count("history", why),
            Err(OpError::Record(RecordError::ScopeExpired)) => count("history", PAST_LIMIT.into()),
            Err(other) => panic!("history {}: {other}", case["args"]),
        }
    }
    println!("history, all: {:?}", started.elapsed());
    let started = Instant::now();
    for case in answers["set_changes"].as_array().unwrap() {
        let set = case["set"].as_str().unwrap().to_owned();
        let limit = case["limit"].as_u64().unwrap() as u32;
        let asked = request(SetChangesArgs { set }, Some(limit), case["since"].as_str());
        let want = &case["answer"];
        match page(&SetChanges, &reader, &asked) {
            Ok(answer) => {
                let mut row = only(&answer);
                row.as_object_mut()
                    .unwrap()
                    .insert("more".into(), json!(answer.more.is_some()));
                assert_eq!(row, *want, "set {case}");
                count("set_changes", "same".into());
            }
            Err(OpError::BadRequest { why }) | Err(OpError::NotFound { what: why }) => {
                assert_eq!(json!(why), want["why_not"], "set {case}");
                count("set_changes", "same refusal".into());
            }
            Err(OpError::NotOwned { why }) => count("set_changes", why),
            Err(OpError::Record(RecordError::ScopeExpired)) => {
                count("set_changes", PAST_LIMIT.into())
            }
            Err(other) => panic!("set {case}: {other}"),
        }
    }
    println!("set_changes, all: {:?}", started.elapsed());
    let started = Instant::now();
    for case in answers["owner_decisions"].as_array().unwrap() {
        let conversation = case["conversation"].as_str().unwrap().to_owned();
        let most = case["most"].as_u64().map(|most| most as u32);
        let asked = request(OwnerDecisionsArgs { conversation }, most, None);
        match page(&OwnerDecisions, &reader, &asked) {
            Ok(answer) => {
                assert_eq!(only(&answer), case["answer"], "owner_decisions {case}");
                count("owner_decisions", "same".into());
            }
            Err(OpError::NotFound { .. }) => {
                assert_eq!(case["answer"]["refused"], json!(true), "{case}");
                count("owner_decisions", "same refusal".into());
            }
            Err(OpError::NotOwned { why }) => count("owner_decisions", why),
            Err(other) => panic!("owner_decisions {case}: {other}"),
        }
    }
    println!("owner_decisions, all: {:?}", started.elapsed());
    for case in answers["governed"].as_array().unwrap() {
        let args = &case["args"];
        let text = |key: &str| args[key].as_str().map(str::to_owned);
        let asked = request(
            GovernedArgs {
                kind: text("kind"),
                q: text("q"),
                state: text("state"),
            },
            Some(case["limit"].as_u64().unwrap() as u32),
            args["cursor"].as_str(),
        );
        let started = Instant::now();
        let got = page(&Governed, &reader, &asked);
        println!("governed {args}: {:?}", started.elapsed());
        match got {
            Ok(answer) => {
                assert_eq!(only(&answer), case["answer"], "governed {args}");
                count("governed", "same".into());
            }
            Err(OpError::BadRequest { why }) => {
                assert_eq!(json!(why), case["answer"]["error"], "governed {args}");
                count("governed", "same refusal".into());
            }
            Err(OpError::NotOwned { why }) => count("governed", why),
            Err(OpError::Record(RecordError::ScopeExpired)) => count("governed", PAST_LIMIT.into()),
            Err(other) => panic!("governed {args}: {other}"),
        }
    }
    let started = Instant::now();
    for (reference, want) in answers["resolve"].as_object().unwrap() {
        let args = ResolveArgs {
            reference: reference.clone(),
        };
        match page(&Resolve, &reader, &request(args, None, None)) {
            Ok(answer) => {
                assert_eq!(want.get("raises"), None, "{reference}");
                let row = resolve_row_as_python_s(only(&answer));
                assert_eq!(row, want["answer"], "resolve {reference}");
                count(
                    "resolve",
                    want["answer"]["what"].as_str().unwrap().to_owned(),
                );
            }
            Err(OpError::NotFound { .. }) => {
                assert_eq!(want["answer"]["ref"], json!(reference), "{reference}");
                assert_eq!(want["answer"].get("what"), None, "{reference}");
                assert!(want["answer"].get("why_not").is_some(), "{reference}");
                count("resolve", "not found".into());
            }
            Err(OpError::NotOwned { why }) => count("resolve", format!("forwarded: {why}")),
            Err(OpError::Record(RecordError::ScopeExpired)) => count("resolve", PAST_LIMIT.into()),
            Err(other) => panic!("resolve {reference}: {other}"),
        }
    }
    println!(
        "resolve, {} references: {:?}",
        answers["resolve"].as_object().unwrap().len(),
        started.elapsed()
    );
    // What stands, now and as at a time, on what a real record holds.
    let asked = answers["standing"].as_object().unwrap();
    let ids: Vec<Id> = asked.keys().cloned().map(Id).collect();
    let as_at = answers["as_at"].as_f64().unwrap();
    for (when, key) in [(None, "now"), (Some(as_at), "then")] {
        let mut scope = reader.read_scope(ReadClass::Agent).unwrap();
        let started = Instant::now();
        let got = match mentis_ops::rules::standing_many(scope.as_mut(), &ids, when) {
            Ok(got) => got,
            Err(RecordError::ScopeExpired) => {
                count("standing", PAST_LIMIT.into());
                continue;
            }
            Err(other) => panic!("standing {key}: {other}"),
        };
        println!("standing {key}: {:?}", started.elapsed());
        count("standing", "same".into());
        for id in &ids {
            let want = &asked[&id.0][key];
            let list = |ids: &[Id]| json!(ids.iter().map(|id| id.0.clone()).collect::<Vec<_>>());
            assert_eq!(json!(got[id].stands), want["stands"], "{id} {key}");
            assert_eq!(
                list(&got[id].established_by),
                want["established_by"],
                "{id} {key}"
            );
            assert_eq!(
                list(&got[id].superseded_by),
                want["superseded_by"],
                "{id} {key}"
            );
            let incoming: serde_json::Map<String, Value> = got[id]
                .incoming
                .iter()
                .map(|(relation, ids)| (relation.clone(), list(ids)))
                .collect();
            assert_eq!(Value::Object(incoming), want["incoming"], "{id} {key}");
        }
    }
    println!("standing: {} ids, now and as at {as_at}", ids.len());
    // Before the budgets and the bytes, so that either failing still leaves what was compared.
    println!("{report:#?}");

    // Budgets, on what a real record holds.
    let started = Instant::now();
    let references: Vec<String> = answers["resolve"]
        .as_object()
        .unwrap()
        .keys()
        .cloned()
        .collect();
    let most = most_statements(
        &Resolve,
        &reader,
        references.iter().map(|reference| {
            let args = ResolveArgs {
                reference: reference.clone(),
            };
            request(args, None, None)
        }),
    );
    println!(
        "resolve: at most {most} statements, budget {}",
        Resolve::BUDGET.statements
    );
    println!("resolve budget, all: {:?}", started.elapsed());
    assert!(most <= Resolve::BUDGET.statements);
    let most = most_statements(
        &Governed,
        &reader,
        std::iter::once(request(GovernedArgs::default(), Some(1000), None)),
    );
    println!(
        "governed: {most} statements, budget {}",
        Governed::BUDGET.statements
    );
    assert!(most <= Governed::BUDGET.statements);

    drop(reader);
    assert!(
        std::fs::read(&corpus_db).unwrap() == bytes_before,
        "reading changed the copy's corpus.db"
    );
    println!("the copy's corpus.db is byte for byte as it was");
}
