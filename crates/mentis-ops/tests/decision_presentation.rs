#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::path::PathBuf;
use std::sync::{Arc, OnceLock};
use std::time::{Duration, Instant};

use mentis_ops::decision_presentation::fields;
use mentis_ops::expectation_states::{ExpectationStates, ExpectationStatesArgs};
use mentis_ops::forms;
use mentis_ops::needs_you::{NeedsYou, NeedsYouArgs, NeedsYouMode};
use mentis_ops::overlay::{Overlay, RunObservations};
use mentis_ops::stored::Object;
use mentis_ops::views::{
    DecisionsView, DecisionsViewArgs, ThreadView, ThreadViewArgs, TurnView, TurnViewArgs,
};
use mentis_ops::{OpError, ReadClass, ReadRequest};
use mentis_record::{Brain, BrainOpener, Position, RecordReader};
use serde_json::Value;

fn request<A>(args: A) -> ReadRequest<A> {
    ReadRequest {
        args,
        cursor: None,
        limit: None,
        deadline: Instant::now() + Duration::from_secs(30),
    }
}

fn overlay() -> Overlay {
    Overlay::from_decoded_poll_for_server(
        Some(Arc::new(vec![])),
        Some(Arc::new(RunObservations::default())),
        Some(Position {
            entry: u64::MAX,
            operational: u64::MAX,
            delivery: u64::MAX,
        }),
    )
}

fn json_of(value: &impl serde::Serialize) -> Value {
    serde_json::from_str(&serde_json::to_string(value).unwrap()).unwrap()
}

fn world() -> &'static (PathBuf, Value) {
    static WORLD: OnceLock<(PathBuf, Value)> = OnceLock::new();
    WORLD.get_or_init(|| {
        let root = PathBuf::from(env!("CARGO_TARGET_TMPDIR"))
            .join(format!("decision-presentation-{}", std::process::id()));
        assert!(!root.exists(), "each process gets its own fixture Brain");
        let done = support::python()
            .arg(
                support::repo_root()
                    .join("crates/mentis-ops/tests/support/decision_presentation_side.py"),
            )
            .arg(&root)
            .output()
            .unwrap();
        assert!(
            done.status.success(),
            "{}",
            String::from_utf8_lossy(&done.stderr)
        );
        let fixture: Value = serde_json::from_slice(&done.stdout).unwrap();
        if std::env::var_os("MENTIS_DECISION_PYTHON_ROOT").is_some() {
            let vectors: Value =
                serde_json::from_str(include_str!("support/presentation_cases.json")).unwrap();
            assert_eq!(
                fixture["oracle"], vectors["canonical_sha256"],
                "test the pinned canonical classifier"
            );
        }
        eprintln!("Python oracle: {}", fixture["oracle"]);
        (root, fixture)
    })
}

#[test]
fn classifier_matches_canonical_python_vectors_or_forwards() {
    let vectors: Value =
        serde_json::from_str(include_str!("support/presentation_cases.json")).unwrap();
    let mut native = 0;
    let mut forwarded = 0;
    for case in vectors["cases"].as_array().unwrap() {
        let detail = Object::parse(&case["detail"].to_string()).unwrap();
        let got = fields(&detail, case["because"].as_str(), case["generated"] == true);
        if case["native"] == true {
            assert_eq!(
                serde_json::to_value(got.unwrap()).unwrap(),
                case["fields"],
                "{}",
                case["name"]
            );
            native += 1;
        } else {
            assert!(
                matches!(got, Err(OpError::NotOwned { .. })),
                "{}: {got:?}",
                case["name"]
            );
            forwarded += 1;
        }
    }
    assert!(native >= 20 && forwarded >= 20);
    eprintln!("canonical Python classifier: {native} native, {forwarded} forwarded");
}

#[test]
fn forms_and_expectations_preserve_metadata_and_closure_or_forward() {
    let (_, fixture) = world();
    for case in fixture["scenarios"].as_array().unwrap() {
        let root = PathBuf::from(case["brain"].as_str().unwrap());
        let reader = Brain::open(&root).unwrap();
        let before = std::fs::read(root.join("corpus.db")).unwrap();
        let form = case["form"].as_str().unwrap().to_owned();
        let ids: Vec<String> = serde_json::from_value(case["ids"].clone()).unwrap();
        let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
        let got_form = forms::forms(&mut *scope, &[form]);
        let got_states = mentis_ops::run(
            &ExpectationStates,
            &reader,
            ReadClass::Foreground,
            &request(ExpectationStatesArgs { ids }),
        );
        if case["native"] == true {
            let mut form = json_of(&got_form.unwrap()[0]);
            form.as_object_mut().unwrap().remove("cursor");
            assert_eq!(form, case["form_answer"], "form {}", case["name"]);
            assert_eq!(
                json_of(&got_states.unwrap().rows),
                case["states"],
                "states {}",
                case["name"]
            );
        } else {
            assert!(
                matches!(got_form, Err(OpError::NotOwned { .. })),
                "form {}",
                case["name"]
            );
            assert!(
                matches!(got_states, Err(OpError::NotOwned { .. })),
                "state {}",
                case["name"]
            );
        }
        assert_eq!(
            before,
            std::fs::read(root.join("corpus.db")).unwrap(),
            "reads never rewrite the Brain"
        );
    }
}

#[test]
fn views_threads_and_needs_you_details_match_additive_python_contract() {
    let (_, fixture) = world();
    for case in fixture["scenarios"].as_array().unwrap() {
        let reader = Brain::open(std::path::Path::new(case["brain"].as_str().unwrap())).unwrap();
        let ids: Vec<String> = serde_json::from_value(case["ids"].clone()).unwrap();
        let decisions = mentis_ops::run(
            &DecisionsView,
            &reader,
            ReadClass::Foreground,
            &request(DecisionsViewArgs {
                ids: ids.clone(),
                post: None,
                overlay: overlay(),
            }),
        );
        let asks = mentis_ops::run(
            &NeedsYou,
            &reader,
            ReadClass::Foreground,
            &request(NeedsYouArgs {
                mode: NeedsYouMode::Asks { ids },
            }),
        );
        if case["native"] == true {
            let mut got: Value =
                serde_json::from_str(&decisions.unwrap().rows[0].0.dumps()).unwrap();
            got.as_object_mut().unwrap().remove("cursor");
            let mut expected = case["decisions"].clone();
            expected.as_object_mut().unwrap().remove("cursor");
            assert_eq!(got, expected, "decisions {}", case["name"]);
            assert_eq!(
                serde_json::from_str::<Value>(&asks.unwrap().rows[0].0.dumps()).unwrap(),
                case["asks"],
                "asks {}",
                case["name"]
            );
        } else {
            assert!(matches!(decisions, Err(OpError::NotOwned { .. })));
            // Needs You reads every currently open owner question. An unclassifiable question
            // deliberately forwards this whole read rather than returning a partial owner list.
            assert!(matches!(asks, Err(OpError::NotOwned { .. })));
        }
        if let Some(post) = case["post"].as_str() {
            let turn = mentis_ops::run(
                &TurnView,
                &reader,
                ReadClass::Foreground,
                &request(TurnViewArgs {
                    turn: post.into(),
                    overlay: overlay(),
                }),
            );
            let thread = mentis_ops::run(
                &ThreadView,
                &reader,
                ReadClass::Foreground,
                &request(ThreadViewArgs {
                    conversation: case["conversation"].as_str().unwrap().into(),
                    root: post.into(),
                    overlay: overlay(),
                }),
            );
            if case["native"] == true && case["name"] != "closed" {
                assert_eq!(
                    serde_json::from_str::<Value>(&turn.unwrap().rows[0].0.dumps()).unwrap(),
                    case["turn_view"],
                    "turn {}",
                    case["name"]
                );
                assert_eq!(
                    serde_json::from_str::<Value>(&thread.unwrap().rows[0].0.dumps()).unwrap(),
                    case["thread"],
                    "thread {}",
                    case["name"]
                );
            } else {
                assert!(matches!(turn, Err(OpError::NotOwned { .. })));
                assert!(matches!(thread, Err(OpError::NotOwned { .. })));
            }
        }
    }
}

#[test]
fn grouped_needs_you_forwards_live_state_and_inspection_roles() {
    let (_, fixture) = world();
    let reader = Brain::open(std::path::Path::new(
        fixture["scenarios"][0]["brain"].as_str().unwrap(),
    ))
    .unwrap();
    let got = mentis_ops::run(
        &NeedsYou,
        &reader,
        ReadClass::Foreground,
        &request(NeedsYouArgs {
            mode: NeedsYouMode::Items,
        }),
    );
    assert!(matches!(got, Err(OpError::NotOwned { .. })));
}
