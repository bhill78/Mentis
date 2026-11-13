//! Where a Conversation is listed (Active, Archived, Trash): the Conversation lists against
//! Python's on a BRAIN-SEED whose Conversations Python's own command archived, trashed and brought
//! back (`python_side.py states`). Each answer is compared as bytes with `json.dumps`'s.

#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::path::PathBuf;
use std::sync::{Arc, OnceLock};
use std::time::{Duration, Instant};

use mentis_ops::ReadRequest;
use mentis_ops::lists::{ConversationMode, Conversations, ConversationsArgs, ListState};
use mentis_ops::overlay::{Overlay, RunObservations};
use mentis_record::{Brain, BrainOpener, ReadClass, RecordReader};
use serde_json::Value;

fn world() -> &'static (PathBuf, Value) {
    static WORLD: OnceLock<(PathBuf, Value)> = OnceLock::new();
    WORLD.get_or_init(|| {
        let dest = PathBuf::from(env!("CARGO_TARGET_TMPDIR"))
            .join(format!("states-{}", std::process::id()))
            .join("brain");
        support::seed(&dest);
        let answers = support::side("states", &dest);
        (dest, serde_json::from_str(&answers).unwrap())
    })
}

fn listed(mode: ConversationMode, limit: Option<u32>) -> String {
    let reader = Brain::open(&world().0).unwrap();
    let at = reader.read_scope(ReadClass::Foreground).unwrap().position();
    let overlay = Overlay::from_decoded_poll_for_server(
        Some(Arc::new(Vec::new())),
        Some(Arc::new(RunObservations::default())),
        Some(at),
    );
    let request = ReadRequest {
        args: ConversationsArgs { mode, overlay },
        cursor: None,
        limit,
        deadline: Instant::now() + Duration::from_secs(20),
    };
    let mut answer = mentis_ops::run(&Conversations, &reader, ReadClass::Foreground, &request)
        .unwrap_or_else(|e| panic!("answered here, not forwarded: {e}"));
    answer.rows.pop().unwrap().0.dumps()
}

fn text(v: &Value) -> Option<String> {
    v.as_str().map(str::to_owned)
}

#[test]
fn each_state_lists_as_python_s_at_every_limit_cursor_and_search() {
    let (_, answers) = world();
    let states = answers["states"].as_object().unwrap();
    let held = |s: &str| states.values().filter(|v| *v == s).count();
    assert!(held("archived") >= 2 && held("trashed") >= 2, "{states:?}");
    let lists = answers["lists"].as_array().unwrap();
    assert!(lists.len() > 100);
    // Rows left active by an Unarchive or Restore say that act's time and who made it.
    let all: Value = serde_json::from_str(answers["by_ids"].as_str().unwrap()).unwrap();
    let moved_back = all["conversations"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| {
            r["state"] == "active" && r["state_at"].is_number() && r["state_by"].is_string()
        })
        .count();
    assert!(moved_back >= 3, "{moved_back} active rows with a state act");
    for case in lists {
        let state = text(&case["state"]).map(|s| ListState::named(&s).unwrap());
        let mode = ConversationMode::Activity {
            after: text(&case["after"]),
            q: text(&case["q"]),
            state,
        };
        let limit = case["limit"].as_u64().unwrap() as u32;
        assert_eq!(
            listed(mode, Some(limit)),
            case["answer"].as_str().unwrap(),
            "state {:?} q {:?} limit {limit} after {:?}",
            case["state"],
            case["q"],
            case["after"]
        );
    }
}

#[test]
fn rows_asked_by_id_say_where_each_is_listed_as_python_s() {
    let (_, answers) = world();
    let ids = answers["ids"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap().to_owned())
        .collect();
    assert_eq!(
        listed(ConversationMode::Ids(ids), None),
        answers["by_ids"].as_str().unwrap()
    );
}
