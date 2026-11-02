//! The post window's budgets (`contracts/ops.md`): statements fixed per call, not per id. Fixtures as
//! `differential.rs`'s. Answers are compared with Python's over HTTP, in `tests/front/test_r2_window.py`.

#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::path::PathBuf;
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use mentis_extract::Bundle;
use mentis_ops::window::Window;
use mentis_ops::window::collections::{
    ConversationArgs, ConversationCollection, ThreadArgs, ThreadCollection,
};
use mentis_ops::window::objects::{Objects, ObjectsArgs, ObjectsAsk};
use mentis_ops::window::posts::{Posts, PostsArgs};
use mentis_ops::{OpError, ReadClass, ReadOp, ReadRequest};
use mentis_record::{
    Brain, BrainOpener, Flow, Param, Position, ReadScope, RecordError, RecordReader, Row, Value,
};

fn world() -> &'static PathBuf {
    static WORLD: OnceLock<PathBuf> = OnceLock::new();
    WORLD.get_or_init(|| match std::env::var("MENTIS_RULES_BRAIN") {
        Ok(brain) => PathBuf::from(brain),
        Err(_) => support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "window"),
    })
}

fn request<A>(args: A, limit: Option<u32>) -> ReadRequest<A> {
    ReadRequest {
        args,
        cursor: None,
        limit,
        deadline: Instant::now() + Duration::from_secs(5),
    }
}

/// A scope that remembers how many statements it ran, for after the op has given it back.
struct Counted<'a> {
    inner: Box<dyn ReadScope>,
    seen: &'a mut u32,
}

impl ReadScope for Counted<'_> {
    fn position(&self) -> Position {
        self.inner.position()
    }

    fn query(
        &mut self,
        sql: &'static str,
        params: &[Param<'_>],
        each: &mut dyn FnMut(&dyn Row) -> Result<Flow, RecordError>,
    ) -> Result<(), RecordError> {
        let result = self.inner.query(sql, params, each);
        *self.seen = self.inner.statements();
        result
    }

    fn statements(&self) -> u32 {
        self.inner.statements()
    }
}

fn spent<O: ReadOp>(
    op: &O,
    reader: &dyn RecordReader,
    asked: &ReadRequest<O::Args>,
) -> (u32, Result<(), OpError>) {
    let mut seen = 1;
    let got = {
        let inner = reader.read_scope(ReadClass::Foreground).unwrap();
        let mut scope = Counted {
            inner,
            seen: &mut seen,
        };
        op.read(&mut scope, asked).map(|_| ())
    };
    (seen, got)
}

fn column(reader: &dyn RecordReader, sql: &'static str) -> Vec<String> {
    let mut scope = reader.read_scope(ReadClass::Background).unwrap();
    let mut out = Vec::new();
    scope
        .query(sql, &[], &mut |row| {
            if let Value::Text(text) = row.value(0)? {
                out.push(String::from_utf8(text.to_vec()).unwrap());
            }
            Ok(Flow::Continue)
        })
        .unwrap();
    out
}

const POST_IDS: &str = "SELECT DISTINCT e.id FROM entry e JOIN entry l ON l.link_from = e.id \
     AND l.link_relation = 'in-conversation' WHERE e.family = 'entry' \
     AND e.def_name = 'contribution' AND e.link_relation IS NULL ORDER BY e.seq";
const CONVERSATION_IDS: &str = "SELECT id FROM entry WHERE family = 'entry' \
     AND def_name = 'conversation' AND link_relation IS NULL ORDER BY seq";

fn bundle() -> Bundle {
    Bundle::of_source(
        "budget.js",
        "var MentisRenderCheck = {extractPost: function () { return {objects: []} }};",
    )
}

#[test]
fn posts_take_the_same_statements_for_one_id_or_a_batch_and_stay_within_budget() {
    let reader = Brain::open(world()).unwrap();
    let window = Window::new(world(), "no-dist".as_ref());
    let op = Posts { window: &window };
    let ids = column(&reader, POST_IDS);
    assert!(ids.len() > 3, "{ids:?}");
    let batch: Vec<String> = ids.iter().take(64).cloned().collect();
    for thread in [None, Some(bundle())] {
        let (one, got) = spent(
            &op,
            &reader,
            &request(
                PostsArgs {
                    ids: batch[..1].to_vec(),
                    thread: thread.clone(),
                },
                None,
            ),
        );
        got.unwrap();
        let (many, got) = spent(
            &op,
            &reader,
            &request(
                PostsArgs {
                    ids: batch.clone(),
                    thread: thread.clone(),
                },
                None,
            ),
        );
        got.unwrap();
        assert!(many <= Posts::BUDGET.statements, "{many}");
        assert!(one <= Posts::BUDGET.statements, "{one}");
    }
}

#[test]
fn a_page_of_a_conversation_stays_within_budget_at_any_size() {
    let reader = Brain::open(world()).unwrap();
    for id in column(&reader, CONVERSATION_IDS) {
        for limit in [1, 200] {
            let args = ConversationArgs {
                id: id.clone(),
                ..ConversationArgs::default()
            };
            let (count, got) = spent(&ConversationCollection, &reader, &request(args, Some(limit)));
            assert!(
                got.is_ok() || matches!(got, Err(OpError::NotOwned { .. })),
                "{got:?}"
            );
            assert!(count <= ConversationCollection::BUDGET.statements, "{count}");
        }
    }
}

#[test]
fn a_thread_stays_within_budget() {
    let reader = Brain::open(world()).unwrap();
    for root in column(&reader, POST_IDS) {
        let args = ThreadArgs {
            root,
            ..ThreadArgs::default()
        };
        let (count, got) = spent(&ThreadCollection, &reader, &request(args, None));
        got.unwrap();
        assert!(count <= ThreadCollection::BUDGET.statements, "{count}");
    }
}

#[test]
fn objects_stay_within_budget_for_every_way_of_asking() {
    let reader = Brain::open(world()).unwrap();
    let window = Window::new(world(), "no-dist".as_ref());
    let op = Objects { window: &window };
    let ids = column(&reader, POST_IDS);
    let conversations = column(&reader, CONVERSATION_IDS);
    let first = ids[0].clone();
    let mut asks = vec![
        ObjectsAsk::Posts {
            ids: ids.iter().take(64).cloned().collect(),
        },
        ObjectsAsk::Thread {
            root: first.clone(),
        },
        ObjectsAsk::Post {
            root: first.clone(),
            version: None,
        },
        ObjectsAsk::One {
            address: format!("live:{first}:no-such-key"),
            format: "json".into(),
        },
        ObjectsAsk::One {
            address: format!("exact:{first}:0:no-such-key"),
            format: "json".into(),
        },
    ];
    for id in conversations {
        asks.push(ObjectsAsk::Conversation {
            id,
            before: None,
            limit: 200,
        });
    }
    for ask in asks {
        let asked = request(
            ObjectsArgs {
                bundle: bundle(),
                ask: ask.clone(),
            },
            None,
        );
        let (count, got) = spent(&op, &reader, &asked);
        assert!(
            got.is_ok()
                || matches!(
                    got,
                    Err(OpError::NotOwned { .. } | OpError::BadRequest { .. })
                ),
            "{ask:?}: {got:?}"
        );
        assert!(count <= Objects::BUDGET.statements, "{ask:?}: {count}");
    }
}
