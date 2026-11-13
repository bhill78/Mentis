//! Reads over a permanently deleted Conversation (`erasure-design.md` 5): on a BRAIN-SEED whose
//! Conversations Python's own command archived and trashed (`python_side.py states`), one trashed
//! Conversation is then deleted the way the deletion leaves the record: a `conversation-deleted`
//! act, and its entry and posts holding the erasure marker. The lists leave it out and are still
//! answered here; what only Python presents (tombstones, a deleted Conversation by id) goes on to
//! Python; and no op is answered here from an erased row.

#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::{Arc, OnceLock};
use std::time::{Duration, Instant};

use mentis_ops::lists::{ConversationMode, Conversations, ConversationsArgs, ListState};
use mentis_ops::overlay::{Overlay, RunObservations};
use mentis_ops::{OpError, ReadRequest};
use mentis_record::{Brain, BrainOpener, ReadClass, RecordReader};
use serde_json::Value;

const DELETION: &str = "opr-0e1e7ed00001";

/// What a deletion leaves, written straight into the scratch Brain: Rust never writes, and this
/// is the shape, not the Python mechanism, under test.
const DELETE: &str = r#"
import json, sqlite3, sys, time
db = sqlite3.connect(sys.argv[1] + "/corpus.db")
cid, act = sys.argv[2], sys.argv[3]
for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall():
    db.execute(f'DROP TRIGGER "{name}"')
marker = json.dumps({"erased": act})
db.execute("INSERT INTO operational (id, at, actor, act, conversation, about, detail) "
           "VALUES (?, ?, 'owner', 'conversation-deleted', ?, ?, ?)",
           (act, time.time(), cid, json.dumps([cid]), json.dumps({"erasure": {"rows": 0}})))
posts = [r[0] for r in db.execute(
    "SELECT link_from FROM entry WHERE link_relation = 'in-conversation' AND link_to = ?", (cid,))]
for id in [cid] + posts:
    db.execute("UPDATE entry SET body = ? WHERE id = ?", (marker, id))
db.execute("UPDATE operational SET detail = ?, because = NULL WHERE conversation = ? AND id != ?",
           (marker, cid, act))
db.commit()
print(json.dumps({"posts": len(posts)}))
"#;

struct World {
    brain: PathBuf,
    /// Every Conversation, the deleted one among them.
    all: Vec<String>,
    deleted: String,
}

fn world() -> &'static World {
    static WORLD: OnceLock<World> = OnceLock::new();
    WORLD.get_or_init(|| {
        let brain = PathBuf::from(env!("CARGO_TARGET_TMPDIR"))
            .join(format!("erased-{}", std::process::id()))
            .join("brain");
        support::seed(&brain);
        let answers: Value = serde_json::from_str(&support::side("states", &brain)).unwrap();
        let states = answers["states"].as_object().unwrap();
        let deleted = states
            .iter()
            .find(|(_, s)| *s == "trashed")
            .map(|(id, _)| id.clone())
            .expect("a trashed Conversation");
        let all: Vec<String> = answers["ids"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(Value::as_str)
            .filter(|id| *id != "ent-nothing-holds-this")
            .map(str::to_owned)
            .collect();
        let done = support::python()
            .arg("-c")
            .arg(DELETE)
            .arg(&brain)
            .arg(&deleted)
            .arg(DELETION)
            .output()
            .expect("Python starts");
        assert!(
            done.status.success(),
            "{}",
            String::from_utf8_lossy(&done.stderr)
        );
        World {
            brain,
            all,
            deleted,
        }
    })
}

fn listed(mode: ConversationMode, limit: Option<u32>) -> Result<Value, OpError> {
    let reader = Brain::open(&world().brain).unwrap();
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
    let mut answer = mentis_ops::run(&Conversations, &reader, ReadClass::Foreground, &request)?;
    Ok(serde_json::from_str(&answer.rows.pop().unwrap().0.dumps()).unwrap())
}

fn ids_of(answer: &Value) -> Vec<String> {
    answer["conversations"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|r| r["id"].as_str().map(str::to_owned))
        .collect()
}

#[test]
fn every_list_leaves_the_deleted_conversation_out_and_is_answered_here() {
    let w = world();
    for state in [
        None,
        Some(ListState::Active),
        Some(ListState::Archived),
        Some(ListState::Trashed),
    ] {
        for q in [None, Some("r1"), Some("conversation")] {
            for limit in [1u32, 2, 100] {
                let mut after: Option<String> = None;
                let mut seen: Vec<String> = Vec::new();
                for _ in 0..40 {
                    let mode = ConversationMode::Activity {
                        after: after.clone(),
                        q: q.map(str::to_owned),
                        state,
                    };
                    let answer = listed(mode, Some(limit)).unwrap_or_else(|e| {
                        panic!("{state:?} {q:?} {limit}: forwarded, not answered: {e}")
                    });
                    let page = ids_of(&answer);
                    assert!(
                        !page.contains(&w.deleted),
                        "{state:?} {q:?} {limit}: {answer}"
                    );
                    seen.extend(page);
                    after = answer["next"].as_str().map(str::to_owned);
                    if after.is_none() {
                        break;
                    }
                }
                if state.is_none() && q.is_none() {
                    let want: HashSet<&String> =
                        w.all.iter().filter(|id| **id != w.deleted).collect();
                    let got: HashSet<&String> = seen.iter().collect();
                    // Every Conversation of the seed but the deleted one, each once.
                    assert!(want.is_subset(&got), "{limit}");
                    assert_eq!(seen.len(), got.len(), "{limit}: a row listed twice");
                }
            }
        }
    }
    // The whole list's total leaves it out too.
    let whole = listed(
        ConversationMode::Activity {
            after: None,
            q: None,
            state: None,
        },
        Some(500),
    )
    .unwrap();
    assert_eq!(
        whole["total"].as_u64().unwrap() as usize,
        ids_of(&whole).len()
    );
}

#[test]
fn the_api_list_leaves_it_out() {
    let w = world();
    let answer = listed(ConversationMode::Api, None).unwrap();
    let ids = ids_of(&answer);
    assert!(!ids.contains(&w.deleted));
    assert!(ids.len() >= w.all.len() - 1);
}

#[test]
fn tombstones_and_a_deleted_conversation_by_id_are_python_s() {
    let w = world();
    let tombstones = listed(
        ConversationMode::Activity {
            after: None,
            q: None,
            state: Some(ListState::Deleted),
        },
        Some(100),
    );
    assert!(matches!(tombstones, Err(OpError::NotOwned { .. })));
    let by_id = listed(ConversationMode::Ids(vec![w.deleted.clone()]), None);
    assert!(matches!(by_id, Err(OpError::NotOwned { .. })), "{by_id:?}");
    // The others by id are answered here, as before.
    let others: Vec<String> = w
        .all
        .iter()
        .filter(|id| **id != w.deleted)
        .cloned()
        .collect();
    let answer = listed(ConversationMode::Ids(others.clone()), None).unwrap();
    assert_eq!(ids_of(&answer), others);
}

#[test]
fn deleted_is_a_state_the_door_knows() {
    assert_eq!(ListState::named("deleted"), Some(ListState::Deleted));
}
