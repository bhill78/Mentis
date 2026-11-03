//! The R4.1 live-field seam against real Python producers and a fixture Brain.
//!
//! This drives coherence and decoded-row behavior through the real poller and public operation.
//! The external test cannot construct the opaque read token; `LiveSnapshotRead` mints it from the
//! operation's real scope.

#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::collections::BTreeMap;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use mentis_ops::expectation_states::{ExpectationState, ExpectationStates, ExpectationStatesArgs};
use mentis_ops::overlay::{
    LiveProjection, LiveProjectionResult, LiveSnapshotArgs, LiveSnapshotRead, LiveWorkers, OpenRun,
    Overlay,
};
use mentis_ops::{OpError, ReadOp, ReadRequest};
use mentis_record::{Brain, BrainOpener, Position, ReadClass, RecordReader};
use mentis_server::front::snapshot::Snapshots;
use mentis_server::live::Liveness;
use serde_json::{Value, json};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener;
use tokio::sync::{Notify, mpsc};

type Reader = <Brain as BrainOpener>::Reader;

fn script() -> PathBuf {
    support::repo_root()
        .join("crates")
        .join("mentis-server")
        .join("tests")
        .join("support")
        .join("live_seam_side.py")
}

struct Python {
    child: Child,
    to: ChildStdin,
    from: BufReader<ChildStdout>,
}

impl Python {
    fn start(brain: &Path) -> Self {
        let mut child = support::python()
            .arg(script())
            .arg("serve")
            .arg(brain)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .expect("Python starts");
        let to = child.stdin.take().unwrap();
        let from = BufReader::new(child.stdout.take().unwrap());
        Self { child, to, from }
    }

    fn ask(&mut self, command: &str, mut args: Value) -> Value {
        args["command"] = json!(command);
        writeln!(self.to, "{args}").unwrap();
        self.to.flush().unwrap();
        let mut line = String::new();
        loop {
            line.clear();
            assert!(self.from.read_line(&mut line).unwrap() > 0, "Python ended");
            if let Some(answer) = line.strip_prefix("@@ ") {
                return serde_json::from_str(answer).unwrap();
            }
        }
    }

    fn envelope(&mut self) -> String {
        self.ask("envelope", json!({}))["text"]
            .as_str()
            .unwrap()
            .to_owned()
    }
}

fn live(
    reader: &Reader,
    overlay: Overlay,
    projection: LiveProjection,
) -> Result<LiveProjectionResult, OpError> {
    let asked = ReadRequest {
        args: LiveSnapshotArgs {
            overlay,
            projection,
        },
        cursor: None,
        limit: None,
        deadline: Instant::now() + Duration::from_secs(20),
    };
    let mut rows = mentis_ops::run(&LiveSnapshotRead, reader, ReadClass::Foreground, &asked)?.rows;
    Ok(rows.remove(0))
}

fn forwarded<T>(got: Result<T, OpError>) -> bool {
    matches!(got, Err(OpError::NotOwned { .. }))
}

fn counts(value: &Value) -> BTreeMap<String, usize> {
    value
        .as_object()
        .unwrap()
        .iter()
        .map(|(key, value)| (key.clone(), value.as_u64().unwrap() as usize))
        .collect()
}

struct StandIn {
    address: std::net::SocketAddr,
    answer: Arc<Mutex<String>>,
    hold_next: Arc<Mutex<bool>>,
    never_answer: Arc<Mutex<bool>>,
    close_next: Arc<Mutex<bool>>,
    release: Arc<Notify>,
    resume: Arc<Notify>,
    requests: mpsc::UnboundedReceiver<()>,
}

async fn stand_in(answer: String) -> StandIn {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let answer = Arc::new(Mutex::new(answer));
    let hold_next = Arc::new(Mutex::new(false));
    let never_answer = Arc::new(Mutex::new(false));
    let close_next = Arc::new(Mutex::new(false));
    let release = Arc::new(Notify::new());
    let resume = Arc::new(Notify::new());
    let (told, requests) = mpsc::unbounded_channel();
    let (held_answer, held_hold, held_never, held_close, held_release, held_resume) = (
        answer.clone(),
        hold_next.clone(),
        never_answer.clone(),
        close_next.clone(),
        release.clone(),
        resume.clone(),
    );
    tokio::spawn(async move {
        loop {
            let (mut stream, _) = listener.accept().await.unwrap();
            let (answer, hold, never, close, release, resume, told) = (
                held_answer.clone(),
                held_hold.clone(),
                held_never.clone(),
                held_close.clone(),
                held_release.clone(),
                held_resume.clone(),
                told.clone(),
            );
            tokio::spawn(async move {
                let mut got = Vec::new();
                let mut chunk = [0; 4096];
                while !got.windows(4).any(|window| window == b"\r\n\r\n") {
                    match stream.read(&mut chunk).await {
                        Ok(0) | Err(_) => return,
                        Ok(count) => got.extend_from_slice(&chunk[..count]),
                    }
                }
                let _ = told.send(());
                if std::mem::take(&mut *close.lock().unwrap()) {
                    return;
                }
                if *never.lock().unwrap() {
                    resume.notified().await;
                }
                if std::mem::take(&mut *hold.lock().unwrap()) {
                    release.notified().await;
                }
                let body = answer.lock().unwrap().clone();
                let response = format!(
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                );
                let _ = stream.write_all(response.as_bytes()).await;
            });
        }
    });
    StandIn {
        address,
        answer,
        hold_next,
        never_answer,
        close_next,
        release,
        resume,
        requests,
    }
}

fn polling(address: std::net::SocketAddr, brain: &Path) -> (Arc<Snapshots>, Arc<Reader>) {
    let reader = Arc::new(Brain::open(brain).unwrap());
    let snapshots = Arc::new(Snapshots::sampling_for_server_test(
        address,
        "s".into(),
        reader.clone(),
    ));
    let polls = snapshots.clone();
    tokio::spawn(async move { polls.poll_while_asked().await });
    snapshots.asked();
    (snapshots, reader)
}

async fn fresh_overlay(snapshots: &Snapshots) -> Overlay {
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        snapshots.asked();
        if let Some(overlay) = snapshots.overlay() {
            return overlay;
        }
        assert!(Instant::now() < deadline, "never fresh");
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
}

async fn wait_until(mut condition: impl FnMut() -> bool) {
    let deadline = Instant::now() + Duration::from_secs(10);
    while !condition() {
        assert!(Instant::now() < deadline, "condition never became true");
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
}

async fn answer_once_then_stall(snapshots: &Snapshots, stand: &mut StandIn, answer: String) {
    *stand.answer.lock().unwrap() = answer;
    *stand.never_answer.lock().unwrap() = false;
    while stand.requests.try_recv().is_ok() {}
    *stand.hold_next.lock().unwrap() = true;
    snapshots.asked();
    while *stand.hold_next.lock().unwrap() {
        stand.requests.recv().await.unwrap();
    }
    *stand.never_answer.lock().unwrap() = true;
    stand.release.notify_one();
    wait_until(|| snapshots.overlay().is_none()).await;
}

impl Drop for Python {
    fn drop(&mut self) {
        let _ = writeln!(self.to, "{}", json!({"command": "quit"}));
        let _ = self.child.wait();
    }
}

fn world(name: &str) -> (PathBuf, Python, Value, Reader) {
    let brain = Path::new(env!("CARGO_TARGET_TMPDIR"))
        .join(format!("{name}-{}", std::process::id()))
        .join("brain");
    support::seed(&brain);
    let mut python = Python::start(&brain);
    let built = python.ask("build", json!({}));
    let reader = Brain::open(&brain).unwrap();
    (brain, python, built, reader)
}

fn states_of(
    reader: &Reader,
    ids: &[String],
) -> Result<(Vec<ExpectationState>, Position), OpError> {
    let asked = ReadRequest {
        args: ExpectationStatesArgs { ids: ids.to_vec() },
        cursor: None,
        limit: None,
        deadline: Instant::now() + Duration::from_secs(20),
    };
    let got = mentis_ops::run(&ExpectationStates, reader, ReadClass::Foreground, &asked)?;
    Ok((got.rows, got.as_of))
}

fn id_of(built: &Value, name: &str) -> String {
    built["ids"][name].as_str().unwrap().to_owned()
}

fn names(built: &Value) -> Vec<String> {
    built["ids"]
        .as_object()
        .unwrap()
        .keys()
        .filter(|name| *name != "not an expectation")
        .cloned()
        .collect()
}

fn without_live(mut value: Value) -> Value {
    let map = value.as_object_mut().unwrap();
    map.remove("live_execution");
    map.remove("durable_open");
    value
}

#[test]
fn every_state_reads_as_python_s_at_full_width_before_the_live_overlay() {
    let (_brain, mut python, built, reader) = world("states");
    let answers = python.ask("states", json!({}));
    let names = names(&built);
    let ids: Vec<String> = names.iter().map(|name| id_of(&built, name)).collect();
    let (rows, _) = states_of(&reader, &ids).unwrap();
    assert_eq!(rows.len(), ids.len());

    for (name, row) in names.iter().zip(&rows) {
        let want = &answers[name];
        let got: Value = serde_json::from_str(&serde_json::to_string(row).unwrap()).unwrap();
        assert_eq!(
            without_live(got.clone()),
            without_live(want["state"].clone()),
            "{name}"
        );
        assert_eq!(
            got["durable_open"], want["durable"]["live_execution"],
            "{name}: the durable half, before any live overlay"
        );
    }

    let of = |name: &str| rows[names.iter().position(|n| n == name).unwrap()].clone();
    assert!(of("input").response_present);
    assert!(!of("input with nothing yet").response_present);
    assert!(of("question on no post").turn.is_none());
    assert!(of("question attached later").turn.is_some());
    assert_eq!(of("reassigned").assigned.history.len(), 3);
    assert!(of("unassigned").unassigned);
    assert!(of("delegated").satisfied_by.is_empty(), "the child's own");
}

#[tokio::test(flavor = "multi_thread")]
async fn every_state_merges_to_python_s_real_raw_value_and_boolean() {
    let (brain, mut python, built, reader) = world("state-merge");
    let answers = python.ask("states", json!({}));
    let stand = stand_in(python.envelope()).await;
    let (snapshots, _) = polling(stand.address, &brain);
    let overlay = fresh_overlay(&snapshots).await;
    let mut shapes = (0, 0, 0);
    for name in names(&built) {
        let expectation = id_of(&built, &name);
        let refs = live(
            &reader,
            overlay.clone(),
            LiveProjection::ExecutionRefs {
                expectation: expectation.clone(),
            },
        )
        .unwrap();
        let boolean = live(
            &reader,
            overlay.clone(),
            LiveProjection::ExecutionBool { expectation },
        )
        .unwrap();
        let LiveProjectionResult::Refs(refs) = refs else {
            panic!("refs")
        };
        let LiveProjectionResult::Bool(boolean) = boolean else {
            panic!("bool")
        };
        assert_eq!(
            json!(refs),
            answers[&name]["state"]["live_execution"],
            "{name}"
        );
        assert_eq!(json!(boolean), answers[&name]["view"], "{name}");
        let durable = answers[&name]["durable"]["live_execution"]
            .as_array()
            .unwrap()
            .len();
        match (durable, refs.len()) {
            (1, 2) => shapes.0 += 1,
            (0, 1) => shapes.1 += 1,
            (1, 1) => shapes.2 += 1,
            _ => {}
        }
    }
    assert!(shapes.0 >= 1, "two-reference case");
    assert!(shapes.1 >= 2, "overlay-only cases");
    assert!(shapes.2 >= 2, "durable-only cases");
}

#[tokio::test(flavor = "multi_thread")]
async fn a_moved_record_with_an_unchanged_real_overlay_does_not_forward() {
    let (brain, mut python, built, _reader) = world("moved");
    let mut stand = stand_in(python.envelope()).await;
    let (snapshots, reader) = polling(stand.address, &brain);
    let overlay = fresh_overlay(&snapshots).await;
    let durable = counts(&python.ask("conversation-counts", json!({})));
    *stand.never_answer.lock().unwrap() = true;
    while stand.requests.try_recv().is_ok() {}
    stand.requests.recv().await.unwrap();
    python.ask("post", json!({}));
    assert_eq!(
        live(
            &reader,
            overlay.clone(),
            LiveProjection::ConversationCounts(durable.clone())
        ),
        Ok(LiveProjectionResult::ConversationCounts(durable))
    );
    assert_eq!(
        live(
            &reader,
            overlay,
            LiveProjection::ExecutionBool {
                expectation: id_of(&built, "plain"),
            },
        ),
        Ok(LiveProjectionResult::Bool(false))
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn a_durable_end_landing_during_a_real_poll_forwards() {
    let (brain, mut python, _built, _reader) = world("in-flight");
    let mut stand = stand_in(python.envelope()).await;
    let (snapshots, reader) = polling(stand.address, &brain);
    for attempt in 0..5 {
        let run = python.ask(
            "expect-running",
            json!({"name": format!("flight-{attempt}")}),
        );
        *stand.answer.lock().unwrap() = python.envelope();
        while stand.requests.try_recv().is_ok() {}
        *stand.hold_next.lock().unwrap() = true;
        snapshots.asked();
        while *stand.hold_next.lock().unwrap() {
            stand.requests.recv().await.unwrap();
        }
        let landed = Instant::now();
        python.ask("end-durably", run.clone());
        let in_time = landed.elapsed() < Duration::from_millis(150);
        stand.release.notify_one();
        tokio::time::sleep(Duration::from_millis(60)).await;
        let got = live(
            &reader,
            snapshots.overlay().expect("fresh"),
            LiveProjection::ExecutionBool {
                expectation: run["expectation"].as_str().unwrap().into(),
            },
        );
        if in_time && forwarded(got) {
            return;
        }
    }
    panic!("no durable end landed inside a poll");
}

#[tokio::test(flavor = "multi_thread")]
async fn the_window_before_a_durable_end_and_its_correcting_reread() {
    let (brain, mut python, _built, reader) = world("window");
    let run = python.ask("expect-running", json!({"name": "window"}));
    // Adopt a poll that contains the newly-opened run.
    let newer_answer = python.envelope();
    let stand = stand_in(newer_answer).await;
    let (newer_snapshots, _) = polling(stand.address, &brain);
    let held = fresh_overlay(&newer_snapshots).await;
    let before = counts(&python.ask("conversation-counts", json!({})));
    python.ask("end-handle", run.clone());
    let after_handle = counts(&python.ask("conversation-counts", json!({})));
    assert_ne!(before, after_handle);
    assert_eq!(
        live(
            &reader,
            held.clone(),
            LiveProjection::ConversationCounts(after_handle.clone())
        ),
        Ok(LiveProjectionResult::ConversationCounts(before))
    );
    python.ask("end-durably", run.clone());
    assert!(forwarded(live(
        &reader,
        held,
        LiveProjection::ConversationCounts(after_handle.clone())
    )));
    let stand = stand_in(python.envelope()).await;
    let (corrected, _) = polling(stand.address, &brain);
    let corrected = fresh_overlay(&corrected).await;
    assert_eq!(
        live(
            &reader,
            corrected,
            LiveProjection::ConversationCounts(after_handle.clone())
        ),
        Ok(LiveProjectionResult::ConversationCounts(after_handle))
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn the_byte_rule_uses_real_producers_and_an_omitted_field_forwards() {
    let (brain, mut python, _built, reader) = world("byte-rule");
    let stand = stand_in(python.envelope()).await;
    let (whole, _) = polling(stand.address, &brain);
    let whole = fresh_overlay(&whole).await;
    assert!(matches!(
        live(&reader, whole, LiveProjection::RunCount),
        Ok(LiveProjectionResult::Count(n)) if n >= 2
    ));
    let sized = python.ask("field-sizes", json!({}))["active_executions"]
        .as_u64()
        .unwrap();
    python.ask("cap", json!({"most": sized + 8}));
    let stand = stand_in(python.envelope()).await;
    let (snapshots, _) = polling(stand.address, &brain);
    let overlay = fresh_overlay(&snapshots).await;
    assert!(matches!(
        live(&reader, overlay.clone(), LiveProjection::ActiveCount),
        Ok(LiveProjectionResult::Count(n)) if n > 0
    ));
    assert!(forwarded(live(&reader, overlay, LiveProjection::RunCount)));
    python.ask("cap", json!({"most": 2}));
    let stand = stand_in(python.envelope()).await;
    let (snapshots, _) = polling(stand.address, &brain);
    assert!(forwarded(live(
        &reader,
        fresh_overlay(&snapshots).await,
        LiveProjection::ActiveCount
    )));
}

#[tokio::test(flavor = "multi_thread")]
async fn a_fresh_real_poll_matches_every_real_producer_row_and_value() {
    let (brain, mut python, _built, reader) = world("producer-rows");
    let expected = python.ask("fields", json!({}));
    let stand = stand_in(python.envelope()).await;
    let (snapshots, _) = polling(stand.address, &brain);
    let overlay = fresh_overlay(&snapshots).await;

    let LiveProjectionResult::ActiveRows(active) =
        live(&reader, overlay.clone(), LiveProjection::ActiveRows).unwrap()
    else {
        panic!("active rows")
    };
    assert_eq!(
        serde_json::to_value(&active).unwrap(),
        expected["active_executions"],
        "start order and all six members"
    );
    assert!(
        active.len() >= 2,
        "the order assertion needs more than one row"
    );

    let LiveProjectionResult::RunRows(runs) =
        live(&reader, overlay, LiveProjection::RunRows).unwrap()
    else {
        panic!("run rows")
    };
    assert_eq!(
        serde_json::to_value(&runs).unwrap(),
        expected["run_observations"],
        "fresh /private/live row parity"
    );

    let going = runs.get("opr-going").unwrap();
    assert_eq!(going.activity.as_deref(), Some("Run npm test"));
    assert!(going.running);
    assert_eq!(
        serde_json::to_value(&going.permission).unwrap(),
        expected["run_observations"]["opr-going"]["permission"]
    );
    assert_eq!(
        serde_json::to_value(&going.permissions).unwrap(),
        expected["run_observations"]["opr-going"]["permissions"]
    );

    let ended = runs.get("opr-ended").unwrap();
    assert!(ended.ended_at.is_some());
    assert!(!ended.running);
    assert_eq!(
        serde_json::to_value(ended.consent_applied.as_ref().unwrap()).unwrap(),
        expected["run_observations"]["opr-ended"]["consent_applied"]
    );
    assert_eq!(
        serde_json::to_value(ended.tooling.as_ref().unwrap()).unwrap(),
        expected["run_observations"]["opr-ended"]["tooling"]
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn the_real_poller_discards_bad_epochs_and_recovers_only_on_a_good_poll() {
    let (brain, mut python, _built, _reader) = world("poll-epochs");
    let good = python.envelope();
    let mut stand = stand_in(good.clone()).await;
    let (snapshots, _) = polling(stand.address, &brain);
    fresh_overlay(&snapshots).await;

    let mut lower: Value = serde_json::from_str(&good).unwrap();
    lower["generation"] = json!(lower["generation"].as_u64().unwrap().saturating_sub(1));
    answer_once_then_stall(&snapshots, &mut stand, lower.to_string()).await;
    *stand.answer.lock().unwrap() = good.clone();
    *stand.never_answer.lock().unwrap() = false;
    stand.resume.notify_waiters();
    fresh_overlay(&snapshots).await;

    let mut boot: Value = serde_json::from_str(&good).unwrap();
    boot["boot_id"] = json!("another-boot");
    answer_once_then_stall(&snapshots, &mut stand, boot.to_string()).await;
    *stand.answer.lock().unwrap() = good.clone();
    *stand.never_answer.lock().unwrap() = false;
    stand.resume.notify_waiters();
    fresh_overlay(&snapshots).await;

    answer_once_then_stall(
        &snapshots,
        &mut stand,
        r#"{"schema": 999, "anything": "else"}"#.into(),
    )
    .await;
    *stand.answer.lock().unwrap() = "not json".into();
    *stand.never_answer.lock().unwrap() = false;
    stand.resume.notify_waiters();
    tokio::time::sleep(Duration::from_millis(600)).await;
    assert!(
        snapshots.overlay().is_none(),
        "an unreadable poll is not recovery"
    );
    *stand.answer.lock().unwrap() = good;
    fresh_overlay(&snapshots).await;
}

#[tokio::test(flavor = "multi_thread")]
async fn the_real_poller_withholds_stale_and_unavailable_snapshots() {
    let (brain, mut python, _built, _reader) = world("poll-age");
    let stand = stand_in(python.envelope()).await;
    let (snapshots, _) = polling(stand.address, &brain);
    fresh_overlay(&snapshots).await;

    *stand.never_answer.lock().unwrap() = true;
    tokio::time::sleep(Duration::from_millis(2200)).await;
    assert!(snapshots.overlay().is_none());
    assert_eq!(snapshots.asked().state, Liveness::Stale);

    // A second real client gives a connection ending with no answer, the immediate-unavailable
    // path. The stalled connection above deliberately remains in hand.
    let mut gone = stand_in(python.envelope()).await;
    let (gone_snapshots, _) = polling(gone.address, &brain);
    fresh_overlay(&gone_snapshots).await;
    *gone.close_next.lock().unwrap() = true;
    while gone.requests.try_recv().is_ok() {}
    gone_snapshots.asked();
    gone.requests.recv().await.unwrap();
    wait_until(|| gone_snapshots.asked().state == Liveness::Unavailable).await;
    assert!(gone_snapshots.overlay().is_none());
}

#[tokio::test(flavor = "multi_thread")]
async fn the_real_poller_resumes_stale_until_its_first_good_answer() {
    let (brain, mut python, _built, _reader) = world("poll-resume");
    let stand = stand_in(python.envelope()).await;
    let (snapshots, _) = polling(stand.address, &brain);
    fresh_overlay(&snapshots).await;
    wait_until(|| snapshots.overlay().is_none()).await;
    let resumed = snapshots.asked();
    assert_eq!(resumed.state, Liveness::Stale);
    assert!(snapshots.overlay().is_none());
    fresh_overlay(&snapshots).await;
}

#[tokio::test(flavor = "multi_thread")]
async fn a_real_markerless_poll_forwards_through_every_path() {
    let (_brain, mut python, built, reader) = world("markerless");
    let stand = stand_in(python.envelope()).await;
    let snapshots = Arc::new(Snapshots::without_record_for_server_test(
        stand.address,
        "s".into(),
    ));
    let polls = snapshots.clone();
    tokio::spawn(async move { polls.poll_while_asked().await });
    snapshots.asked();
    let overlay = fresh_overlay(&snapshots).await;
    let projections = [
        LiveProjection::ActiveCount,
        LiveProjection::RunCount,
        LiveProjection::ConversationCounts(BTreeMap::from([(
            built["known"].as_str().unwrap().into(),
            0,
        )])),
        LiveProjection::LiveWorkersChanged {
            open_runs: vec![OpenRun {
                run: "opr-going".into(),
                conversation: built["known"].as_str().unwrap().into(),
                participant: built["agent"].as_str().unwrap().into(),
            }],
            durable: LiveWorkers::new(),
        },
        LiveProjection::ExecutionBool {
            expectation: id_of(&built, "unrecorded"),
        },
        LiveProjection::ExecutionRefs {
            expectation: id_of(&built, "unrecorded"),
        },
    ];
    for projection in projections {
        assert!(forwarded(live(&reader, overlay.clone(), projection)));
    }
    let unchanged = counts(&python.ask("conversation-counts", json!({})));
    assert_eq!(
        live(
            &reader,
            overlay,
            LiveProjection::ConversationCounts(unchanged.clone())
        ),
        Ok(LiveProjectionResult::ConversationCounts(unchanged))
    );
}

#[test]
fn one_call_stays_inside_its_budget_however_many_are_asked_and_what_isn_t_one_is_left_out() {
    let (_brain, _python, built, reader) = world("budget");
    let names = names(&built);
    let ids: Vec<String> = names.iter().map(|name| id_of(&built, name)).collect();
    let count = |ids: &[String]| {
        let mut scope = reader.read_scope(ReadClass::Foreground).unwrap();
        let asked = ReadRequest {
            args: ExpectationStatesArgs { ids: ids.to_vec() },
            cursor: None,
            limit: None,
            deadline: Instant::now() + Duration::from_secs(20),
        };
        ExpectationStates.read(scope.as_mut(), &asked).unwrap();
        scope.statements()
    };
    let all = count(&ids);
    assert!(all <= ExpectationStates::BUDGET.statements, "{all}");
    assert!(count(&ids[..1]) <= all);

    let not_one = id_of(&built, "not an expectation");
    let (rows, _) = states_of(&reader, &[not_one, ids[0].clone(), "opr-nothing".into()]).unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].expectation, ids[0]);
    assert!(states_of(&reader, &[]).unwrap().0.is_empty());
}

/// By hand: `MENTIS_R4_BRAIN` is a new fixture.build copy, read by Python in full first.
#[test]
#[ignore = "needs MENTIS_R4_BRAIN, a Brain copy, and minutes of Python"]
fn on_a_brain_copy_every_state_agrees_or_forwards() {
    let brain = PathBuf::from(std::env::var("MENTIS_R4_BRAIN").expect("MENTIS_R4_BRAIN"));
    let most = std::env::var("MENTIS_R4_SAMPLE").unwrap_or_else(|_| "1500".into());
    let side = |args: &[&str]| {
        let done = support::python().arg(script()).args(args).output().unwrap();
        assert!(
            done.status.success(),
            "{}",
            String::from_utf8_lossy(&done.stderr)
        );
        String::from_utf8(done.stdout).unwrap()
    };
    let where_ = brain.to_str().unwrap();
    let answers: Value = serde_json::from_str(&side(&["copy", where_, &most])).unwrap();
    let digest = side(&["digest", where_]);
    let reader = Brain::open(&brain).unwrap();
    let (mut agreed, mut forwarded_rows, mut python_raised) = (0, 0, 0);
    let mut differed = Vec::new();
    let started = Instant::now();
    for (id, want) in answers["answers"].as_object().unwrap() {
        if want.get("python_raised").is_some() {
            python_raised += 1;
            continue;
        }
        match states_of(&reader, std::slice::from_ref(id)) {
            Err(OpError::NotOwned { .. }) => forwarded_rows += 1,
            Err(other) => panic!("{id}: {other}"),
            Ok((rows, _)) => {
                let got: Value =
                    serde_json::from_str(&serde_json::to_string(&rows[0]).unwrap()).unwrap();
                let durable_agrees = got["durable_open"] == want["live_execution"];
                if durable_agrees && without_live(got.clone()) == without_live(want.clone()) {
                    agreed += 1;
                } else {
                    differed.push(id.clone());
                }
            }
        }
    }
    println!(
        "{} of {} expectations: {agreed} agreed, {forwarded_rows} forwarded, {python_raised} raised in Python, {} differed, in {:?}",
        answers["answers"].as_object().unwrap().len(),
        answers["total"],
        differed.len(),
        started.elapsed(),
    );
    assert!(differed.is_empty(), "{differed:?}");
    assert_eq!(side(&["digest", where_]), digest, "this side wrote nothing");
}
