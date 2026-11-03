//! R4.1's lists through public `mentis_ops::run` on a real Brain's copy (`MENTIS_TEST_BRAIN`):
//! what no front can be made to show on demand, a poll with no marker, each projection's forward,
//! and how many statements each route takes against its budget.
//!
//! Ignored without a copy: `cargo test -p mentis-ops --test r41_lists -- --ignored`, with
//! `MENTIS_TEST_BRAIN` naming a backup-API copy.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};

use mentis_ops::annotations::{Anchors, AnchorsArgs};
use mentis_ops::changes::{Changes, ChangesArgs};
use mentis_ops::lists::{
    ConversationMode, Conversations, ConversationsArgs, Latest, LatestArgs, Participants,
    ParticipantsArgs, Selection, SelectionArgs, Stream, StreamArgs,
};
use mentis_ops::needs_you::{NeedsYou, NeedsYouArgs, NeedsYouMode};
use mentis_ops::overlay::{ActiveExecution, Overlay, RunObservations};
use mentis_ops::{OpError, ReadOp, ReadRequest};
use mentis_record::{Brain, BrainOpener, Flow, Param, Position, ReadClass, RecordReader};

type Reader = <Brain as BrainOpener>::Reader;

fn reader() -> Reader {
    let root = PathBuf::from(std::env::var_os("MENTIS_TEST_BRAIN").expect("MENTIS_TEST_BRAIN"));
    Brain::open(&root).expect("the copy opens")
}

fn ask<A>(args: A, limit: Option<u32>) -> ReadRequest<A> {
    ReadRequest {
        args,
        cursor: None,
        limit,
        deadline: Instant::now() + Duration::from_secs(60),
    }
}

fn first_text(reader: &Reader, sql: &'static str, params: &[Param<'_>]) -> String {
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    let mut out = String::new();
    scope
        .query(sql, params, &mut |row| {
            out = row.value(0)?.text().unwrap_or_default().to_owned();
            Ok(Flow::Stop)
        })
        .unwrap();
    out
}

fn a_conversation(reader: &Reader) -> String {
    first_text(
        reader,
        "SELECT link_to FROM entry WHERE link_relation='in-conversation' GROUP BY link_to \
         ORDER BY COUNT(*) DESC LIMIT 1",
        &[],
    )
}

fn a_participant(reader: &Reader) -> String {
    first_text(
        reader,
        "SELECT id FROM entry WHERE def_name='participant' AND family='entry' \
         AND link_relation IS NULL ORDER BY seq LIMIT 1",
        &[],
    )
}

fn here(reader: &Reader) -> Position {
    reader.read_scope(ReadClass::Foreground).unwrap().position()
}

fn working_here(reader: &Reader, marker: Option<Position>) -> Overlay {
    let active: ActiveExecution = serde_json::from_value(serde_json::json!({
        "reference": "live-r41",
        "participant": a_participant(reader),
        "conversation": a_conversation(reader),
        "runtime": "claude",
        "persona": null,
        "for_expectation": null,
    }))
    .unwrap();
    Overlay::from_decoded_poll_for_server(
        Some(Arc::new(vec![active])),
        Some(Arc::new(RunObservations::default())),
        marker,
    )
}

fn nobody(marker: Option<Position>) -> Overlay {
    Overlay::from_decoded_poll_for_server(
        Some(Arc::new(Vec::new())),
        Some(Arc::new(RunObservations::default())),
        marker,
    )
}

fn modes(reader: &Reader) -> [ConversationMode; 3] {
    [
        ConversationMode::Api,
        ConversationMode::Ids(vec![a_conversation(reader)]),
        ConversationMode::Activity {
            after: None,
            q: None,
        },
    ]
}

fn listed(
    reader: &Reader,
    mode: ConversationMode,
    overlay: Overlay,
) -> Result<mentis_ops::ReadAnswer<mentis_ops::window::collections::PyRow>, OpError> {
    mentis_ops::run(
        &Conversations,
        reader,
        ReadClass::Foreground,
        &ask(ConversationsArgs { mode, overlay }, Some(24)),
    )
}

fn forwards<T>(got: Result<T, OpError>, what: &str) {
    match got {
        Err(OpError::NotOwned { .. }) => {}
        Ok(_) => panic!("{what}: answered"),
        Err(other) => panic!("{what}: {other:?}"),
    }
}

#[test]
#[ignore = "needs MENTIS_TEST_BRAIN"]
fn a_markerless_poll_forwards_only_what_its_overlay_changes() {
    let reader = reader();
    for mode in modes(&reader) {
        listed(&reader, mode.clone(), nobody(None))
            .ok()
            .expect("nothing to change, nothing to forward");
        forwards(
            listed(&reader, mode, working_here(&reader, None)),
            "markerless",
        );
    }
}

#[test]
#[ignore = "needs MENTIS_TEST_BRAIN"]
fn a_poll_behind_the_read_in_any_component_forwards_what_its_overlay_changes() {
    let reader = reader();
    let at = here(&reader);
    let behind = [
        Position {
            entry: at.entry - 1,
            ..at
        },
        Position {
            operational: at.operational - 1,
            ..at
        },
        Position {
            delivery: at.delivery - 1,
            ..at
        },
    ];
    for marker in behind {
        for mode in modes(&reader) {
            listed(&reader, mode.clone(), nobody(Some(marker)))
                .ok()
                .expect("the overlay changes nothing");
            forwards(
                listed(&reader, mode, working_here(&reader, Some(marker))),
                "behind",
            );
        }
    }
}

#[test]
#[ignore = "needs MENTIS_TEST_BRAIN"]
fn a_coherent_poll_answers() {
    let reader = reader();
    let at = here(&reader);
    for mode in modes(&reader) {
        listed(&reader, mode, working_here(&reader, Some(at)))
            .ok()
            .expect("coherent");
    }
}

#[test]
#[ignore = "needs MENTIS_TEST_BRAIN"]
fn each_route_needs_only_its_own_fields() {
    let reader = reader();
    let at = Some(here(&reader));
    let [api, ids, activity] = modes(&reader);
    let only_runs = || {
        Overlay::from_decoded_poll_for_server(None, Some(Arc::new(RunObservations::default())), at)
    };
    let only_active =
        || Overlay::from_decoded_poll_for_server(Some(Arc::new(Vec::new())), None, at);
    forwards(
        listed(&reader, api.clone(), only_runs()),
        "count, no active",
    );
    listed(&reader, api, only_active())
        .ok()
        .expect("a count reads no run observations");
    for mode in [ids, activity] {
        forwards(
            listed(&reader, mode.clone(), only_runs()),
            "workers, no active",
        );
        forwards(listed(&reader, mode, only_active()), "workers, no runs");
    }
}

fn statements<O: ReadOp>(reader: &Reader, op: &O, request: &ReadRequest<O::Args>) -> u32 {
    let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
    let before = scope.statements();
    if let Err(OpError::NotOwned { why }) = op.read(scope.as_mut(), request) {
        println!("  forwarded: {why}");
    }
    scope.statements() - before
}

/// Statements per route on the copy. Python's census for the Fluid list is 1,047-1,475.
#[test]
#[ignore = "needs MENTIS_TEST_BRAIN"]
fn every_route_keeps_to_its_budget_at_this_size() {
    let reader = reader();
    let at = here(&reader);
    let conversation = a_conversation(&reader);
    let post = first_text(
        &reader,
        "SELECT link_to FROM entry WHERE link_relation='anchors-in' LIMIT 1",
        &[],
    );
    let ask_id = first_text(
        &reader,
        "SELECT id FROM operational WHERE act='expectation-recorded' ORDER BY seq DESC LIMIT 1",
        &[],
    );
    let mut seen: HashMap<&str, (u32, u32)> = HashMap::new();
    let mut note = |name: &'static str, count: u32, budget: u32| {
        println!("{name}: {count} statements, budget {budget}");
        assert!(count <= budget, "{name}: {count} over {budget}");
        seen.insert(name, (count, budget));
    };
    for (name, mode) in [
        ("api-conversations", ConversationMode::Api),
        (
            "conversations?ids",
            ConversationMode::Ids(vec![conversation.clone()]),
        ),
        (
            "conversations?activity",
            ConversationMode::Activity {
                after: None,
                q: None,
            },
        ),
        (
            "conversations?activity&q",
            ConversationMode::Activity {
                after: None,
                q: Some("a".into()),
            },
        ),
    ] {
        let request = ask(
            ConversationsArgs {
                mode,
                overlay: nobody(Some(at)),
            },
            Some(100),
        );
        note(
            name,
            statements(&reader, &Conversations, &request),
            Conversations::BUDGET.statements,
        );
    }
    let root = PathBuf::from(std::env::var_os("MENTIS_TEST_BRAIN").expect("MENTIS_TEST_BRAIN"));
    let window = mentis_ops::window::Window::new(&root, &root);
    let participants_op = Participants {
        window: Some(&window),
    };
    for (name, api) in [("fluid-participants", false), ("api-participants", true)] {
        let request = ask(
            ParticipantsArgs {
                q: None,
                runtimes: true,
                api,
            },
            Some(100),
        );
        note(
            name,
            statements(&reader, &participants_op, &request),
            Participants::BUDGET.statements,
        );
    }
    note(
        "stream",
        statements(&reader, &Stream, &ask(StreamArgs::default(), Some(200))),
        Stream::BUDGET.statements,
    );
    note(
        "selection",
        statements(
            &reader,
            &Selection,
            &ask(
                SelectionArgs {
                    ids: vec![post.clone()],
                },
                None,
            ),
        ),
        Selection::BUDGET.statements,
    );
    for (name, agent_work) in [("latest", false), ("latest&agent_work", true)] {
        let request = ask(
            LatestArgs {
                conversation: None,
                agent_work,
            },
            Some(50),
        );
        note(
            name,
            statements(&reader, &Latest, &request),
            Latest::BUDGET.statements,
        );
    }
    for (name, mode) in [
        ("home-needs-you", NeedsYouMode::Page { before: None }),
        ("needs-you-items", NeedsYouMode::Items),
        (
            "needs-you?ids",
            NeedsYouMode::Asks {
                ids: vec![ask_id.clone()],
            },
        ),
        ("needs-you?post", NeedsYouMode::On { post: post.clone() }),
    ] {
        let request = ask(NeedsYouArgs { mode }, Some(30));
        note(
            name,
            statements(&reader, &NeedsYou, &request),
            NeedsYou::BUDGET.statements,
        );
    }
    note(
        "anchors",
        statements(
            &reader,
            &Anchors,
            &ask(
                AnchorsArgs {
                    posts: vec![post.clone()],
                },
                None,
            ),
        ),
        Anchors::BUDGET.statements,
    );
    let since = format!(
        "f1.{}.{}.{}",
        at.entry.saturating_sub(100),
        at.operational.saturating_sub(100),
        at.delivery.saturating_sub(20)
    );
    let request = ask(
        ChangesArgs {
            since: Some(since),
            threads: true,
        },
        None,
    );
    note(
        "changes",
        statements(&reader, &Changes, &request),
        Changes::BUDGET.statements,
    );
}
