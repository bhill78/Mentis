#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};

use mentis_ops::overlay::{ActiveExecution, Overlay, RunObservations};
use mentis_ops::views::{
    ConversationFields, ConversationFieldsArgs, DecisionsView, DecisionsViewArgs, IntakeView,
    IntakeViewArgs, Personas, ThreadView, ThreadViewArgs, TurnView, TurnViewArgs, TurnsView,
    TurnsViewArgs, ViewRow,
};
use mentis_ops::{Position, ReadClass, ReadRequest};
use mentis_record::{Brain, BrainOpener};
use serde_json::Value;

fn world() -> (PathBuf, Value) {
    let root =
        PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join(format!("views-{}", std::process::id()));
    if root.exists() {
        std::fs::remove_dir_all(&root).unwrap();
    }
    let script = support::repo_root().join("crates/mentis-ops/tests/support/views_side.py");
    let done = support::python().arg(script).arg(&root).output().unwrap();
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    (root, serde_json::from_slice(&done.stdout).unwrap())
}

fn request<A>(args: A) -> ReadRequest<A> {
    ReadRequest {
        args,
        cursor: None,
        limit: None,
        deadline: Instant::now() + Duration::from_secs(20),
    }
}
fn value(row: ViewRow) -> Value {
    serde_json::from_str(&row.0.dumps()).unwrap()
}
fn overlay_at(answer: &Value, marker: Option<Position>) -> Overlay {
    let active: Vec<ActiveExecution> = serde_json::from_value(answer["active"].clone()).unwrap();
    Overlay::from_decoded_poll_for_server(
        Some(Arc::new(active)),
        Some(Arc::new(RunObservations::default())),
        marker,
    )
}
fn overlay(answer: &Value) -> Overlay {
    overlay_at(
        answer,
        Some(Position {
            entry: u64::MAX,
            operational: u64::MAX,
            delivery: u64::MAX,
        }),
    )
}

#[test]
fn r42_fixture_views_match_python() {
    let (brain, answer) = world();
    let reader = Brain::open(&brain).unwrap();
    let live = overlay(&answer);
    assert_eq!(
        answer["raw_live"].as_array().unwrap().len(),
        2,
        "raw state has durable and boundary refs"
    );
    let run = |op: &dyn Fn() -> Value, want: &str| {
        let started = Instant::now();
        assert_eq!(op(), answer[want], "{want}");
        eprintln!("r42 route {want}: {:?}", started.elapsed());
    };
    run(
        &|| {
            value(
                mentis_ops::run(&Personas, &reader, ReadClass::Foreground, &request(()))
                    .unwrap()
                    .rows
                    .pop()
                    .unwrap(),
            )
        },
        "personas",
    );
    let cid = answer["conversation"].as_str().unwrap().to_owned();
    let turn = answer["turn"].as_str().unwrap().to_owned();
    let expectation = answer["expectation"].as_str().unwrap().to_owned();
    run(
        &|| {
            value(
                mentis_ops::run(
                    &ConversationFields,
                    &reader,
                    ReadClass::Foreground,
                    &request(ConversationFieldsArgs {
                        conversation: cid.clone(),
                        fields: vec![
                            "name".into(),
                            "about".into(),
                            "participants".into(),
                            "topics".into(),
                        ],
                    }),
                )
                .unwrap()
                .rows
                .pop()
                .unwrap(),
            )
        },
        "fields",
    );
    run(
        &|| {
            value(
                mentis_ops::run(
                    &IntakeView,
                    &reader,
                    ReadClass::Foreground,
                    &request(IntakeViewArgs {
                        overlay: live.clone(),
                    }),
                )
                .unwrap()
                .rows
                .pop()
                .unwrap(),
            )
        },
        "intake",
    );
    assert!(
        answer["intake_without_live"]["resumable"]
            .as_array()
            .unwrap()
            .iter()
            .any(|id| id == &answer["intake_expectation"])
    );
    assert!(
        !answer["intake"]["resumable"]
            .as_array()
            .unwrap()
            .iter()
            .any(|id| id == &answer["intake_expectation"])
    );
    run(
        &|| {
            value(
                mentis_ops::run(
                    &TurnView,
                    &reader,
                    ReadClass::Foreground,
                    &request(TurnViewArgs {
                        turn: turn.clone(),
                        overlay: live.clone(),
                    }),
                )
                .unwrap()
                .rows
                .pop()
                .unwrap(),
            )
        },
        "turn_view",
    );
    run(
        &|| {
            value(
                mentis_ops::run(
                    &TurnsView,
                    &reader,
                    ReadClass::Foreground,
                    &request(TurnsViewArgs {
                        turns: vec![turn.clone()],
                        overlay: live.clone(),
                    }),
                )
                .unwrap()
                .rows
                .pop()
                .unwrap(),
            )
        },
        "turns",
    );
    run(
        &|| {
            value(
                mentis_ops::run(
                    &ThreadView,
                    &reader,
                    ReadClass::Foreground,
                    &request(ThreadViewArgs {
                        conversation: cid.clone(),
                        root: turn.clone(),
                        overlay: live.clone(),
                    }),
                )
                .unwrap()
                .rows
                .pop()
                .unwrap(),
            )
        },
        "thread",
    );
    let mut decisions = value(
        mentis_ops::run(
            &DecisionsView,
            &reader,
            ReadClass::Foreground,
            &request(DecisionsViewArgs {
                post: None,
                ids: vec![expectation],
                overlay: live,
            }),
        )
        .unwrap()
        .rows
        .pop()
        .unwrap(),
    );
    decisions.as_object_mut().unwrap().insert(
        "cursor".into(),
        Value::String(format!(
            "f1.{}",
            mentis_ops::run(&Personas, &reader, ReadClass::Foreground, &request(()))
                .unwrap()
                .as_of
        )),
    );
    run(&|| decisions.clone(), "decisions");
    if let Some(form_expectation) = answer["form_expectation"].as_str() {
        let mut got = value(
            mentis_ops::run(
                &DecisionsView,
                &reader,
                ReadClass::Foreground,
                &request(DecisionsViewArgs {
                    post: None,
                    ids: vec![form_expectation.to_owned()],
                    overlay: overlay(&answer),
                }),
            )
            .unwrap()
            .rows
            .pop()
            .unwrap(),
        );
        got.as_object_mut()
            .unwrap()
            .insert("cursor".into(), answer["form_decisions"]["cursor"].clone());
        assert_eq!(
            got, answer["form_decisions"],
            "decision form by expectation"
        );
    }

    let mut exact_text_turns = 0;
    let mut forwarded_text_turns = 0;
    for case in answer["text_turns"].as_array().unwrap() {
        let id = case["id"].as_str().unwrap().to_owned();
        match mentis_ops::run(
            &TurnView,
            &reader,
            ReadClass::Foreground,
            &request(TurnViewArgs {
                turn: id.clone(),
                overlay: overlay(&answer),
            }),
        ) {
            Ok(got) => {
                assert_eq!(
                    value(got.rows.into_iter().next().unwrap()),
                    case["answer"],
                    "text Turn {id}"
                );
                exact_text_turns += 1;
            }
            Err(mentis_ops::OpError::NotOwned { .. }) => forwarded_text_turns += 1,
            Err(error) => panic!("text Turn {id}: {error}"),
        }
    }
    assert!(
        exact_text_turns > 1,
        "fixture must exercise owned Turn shapes"
    );
    assert!(
        forwarded_text_turns > 0,
        "fixture must exercise a durable compatibility boundary"
    );
    eprintln!(
        "r42 fixture Turns: {exact_text_turns} exact text, {forwarded_text_turns} durable fallback, {} held-file/anchor fallback",
        answer["held_turns"].as_array().unwrap().len()
    );
    for id in answer["held_turns"].as_array().unwrap() {
        let error = mentis_ops::run(
            &TurnView,
            &reader,
            ReadClass::Foreground,
            &request(TurnViewArgs {
                turn: id.as_str().unwrap().to_owned(),
                overlay: overlay(&answer),
            }),
        )
        .unwrap_err();
        assert!(matches!(error, mentis_ops::OpError::NotOwned { .. }));
    }

    // A markerless overlay adds only the second reference.  The durable instance already makes
    // `_expectation_view` true, so this exact boolean route need not forward.
    let markerless = overlay_at(&answer, None);
    let got = mentis_ops::run(
        &TurnView,
        &reader,
        ReadClass::Foreground,
        &request(TurnViewArgs {
            turn: turn.clone(),
            overlay: markerless,
        }),
    )
    .unwrap();
    let got = value(got.rows.into_iter().next().unwrap());
    assert_eq!(got["expectations"][0]["live_execution"], Value::Bool(true));
    assert!(
        got["expectations"][0]["live_execution"]
            .as_array()
            .is_none()
    );

    // An absent active field cannot establish an overlay-only answer.
    let absent = Overlay::from_decoded_poll_for_server(
        None,
        Some(Arc::new(RunObservations::default())),
        Some(Position::default()),
    );
    let err = mentis_ops::run(
        &TurnView,
        &reader,
        ReadClass::Foreground,
        &request(TurnViewArgs {
            turn,
            overlay: absent,
        }),
    )
    .unwrap_err();
    assert!(matches!(err, mentis_ops::OpError::NotOwned { .. }));

    // A markerless overlay that changes intake's resumable answer cannot be combined with this
    // durable read.  This is the answer-changing counterpart to the no-change assertion above.
    let err = mentis_ops::run(
        &IntakeView,
        &reader,
        ReadClass::Foreground,
        &request(IntakeViewArgs {
            overlay: overlay_at(&answer, None),
        }),
    )
    .unwrap_err();
    assert!(matches!(err, mentis_ops::OpError::NotOwned { .. }));
}

/// Each Turn of a copied Brain: `ANSWERED`, or the words it forwards with. With a marker past
/// everything and nothing running. What `tools/r4_2/compare.py` reads ownership from.
#[test]
#[ignore = "takes MENTIS_R4_BRAIN, a copied Brain, and R42_WHY, where to write"]
fn on_a_brain_copy_why_each_turn_forwards() {
    let brain = std::env::var("MENTIS_R4_BRAIN").unwrap();
    let out = std::env::var("R42_WHY").unwrap();
    let reader = Brain::open(std::path::Path::new(&brain)).unwrap();
    let ids = rusqlite_ids(&brain);
    let live = overlay(&serde_json::json!({"active": []}));
    let mut lines = Vec::with_capacity(ids.len());
    for id in ids {
        let got = mentis_ops::run(
            &TurnView,
            &reader,
            ReadClass::Foreground,
            &request(TurnViewArgs {
                turn: id.clone(),
                overlay: live.clone(),
            }),
        );
        let said = match got {
            Ok(_) => "ANSWERED".to_owned(),
            Err(mentis_ops::OpError::NotOwned { why }) => why,
            Err(other) => panic!("{id}: {other}"),
        };
        lines.push(format!("{id}\t{said}"));
    }
    std::fs::write(out, lines.join("\n")).unwrap();
}

/// The Turns, oldest first, read with Python so the test needs no driver of its own.
fn rusqlite_ids(brain: &str) -> Vec<String> {
    let script = "import sqlite3,sys;print('\\n'.join(r[0] for r in sqlite3.connect(\
        f'file:{sys.argv[1]}/corpus.db?mode=ro',uri=True).execute(\"select id from entry where \
        family='entry' and def_name='contribution' and link_relation is null order by seq\")))";
    let done = support::python()
        .args(["-c", script, brain])
        .output()
        .unwrap();
    assert!(done.status.success());
    String::from_utf8(done.stdout)
        .unwrap()
        .lines()
        .map(str::to_owned)
        .collect()
}
