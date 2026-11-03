//! The R4.1 seam, against the real Python: `expectation_states` beside `expectation_state`, the merge
//! beside Python's raw `live_execution` and the boolean its views emit, and the coherence fixtures
//! with the record really moving. `support/live_seam_side.py` is a running `_State`, its producers
//! included; no stand-in says what either field holds. `MENTIS_R4_BRAIN` names a Brain copy for the
//! ignored test below, which is also read by Python and checked unchanged after.

#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use mentis_ops::OpError;
use mentis_ops::expectation_states::{ExpectationState, ExpectationStates, ExpectationStatesArgs};
use mentis_ops::overlay::Overlay;
use mentis_ops::{ReadOp, ReadRequest};
use mentis_record::{Brain, BrainOpener, Position, ReadClass, RecordReader};
use mentis_server::front::snapshot::Snapshots;
use mentis_server::live::{LiveSnapshot, PollAnswer};
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

/// The running Python, one command at a time.
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

    /// `GET /private/live`'s real body.
    fn envelope(&mut self) -> String {
        self.ask("envelope", json!({}))["text"]
            .as_str()
            .unwrap()
            .to_owned()
    }

    fn snapshot(&mut self) -> LiveSnapshot {
        match PollAnswer::read(self.envelope().as_bytes()) {
            PollAnswer::Snapshot(snapshot) => snapshot,
            other => panic!("the real envelope isn't one: {other:?}"),
        }
    }
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

fn state_of(reader: &Reader, id: &str) -> (ExpectationState, Position) {
    let (mut rows, at) = states_of(reader, &[id.to_owned()]).unwrap();
    assert_eq!(rows.len(), 1, "{id}");
    (rows.remove(0), at)
}

fn overlay_of(snapshot: &LiveSnapshot, marker: Option<Position>) -> Overlay {
    Overlay::new(
        snapshot.fields.active_executions.clone(),
        snapshot.fields.run_observations.clone(),
        marker,
    )
}

/// A read working out its own answer as `/api/conversations`' count does, against what its durable
/// rows already say.
fn live_count(overlay: &Overlay, read: Position, durable: usize) -> Result<usize, OpError> {
    overlay.work_out(read, durable, |durable, live| {
        let count = live.active_executions()?.len();
        Ok((count != *durable).then_some(count))
    })
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

fn forwarded<T: std::fmt::Debug>(got: Result<T, OpError>) -> bool {
    matches!(got, Err(OpError::NotOwned { .. }))
}

/// A row as Python's dict reads, with the one member that can't match taken out on both sides.
fn without_live(mut value: Value) -> Value {
    let map = value.as_object_mut().unwrap();
    map.remove("live_execution");
    map.remove("durable_open");
    value
}

#[test]
fn every_state_reads_as_python_s_at_full_width_and_merges_to_its_raw_value_and_boolean() {
    let (_brain, mut python, built, reader) = world("states");
    let answers = python.ask("states", json!({}));
    let snapshot = python.snapshot();
    let names = names(&built);
    let ids: Vec<String> = names.iter().map(|name| id_of(&built, name)).collect();
    let (rows, at) = states_of(&reader, &ids).unwrap();
    assert_eq!(rows.len(), ids.len());
    let overlay = overlay_of(&snapshot, Some(at));

    let (mut with_two, mut only_overlay, mut only_durable) = (0, 0, 0);
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
            "{name}: the durable half, Python's with nothing held live"
        );
        let live = overlay.live_execution(row, at).unwrap();
        assert_eq!(
            json!(live.refs().unwrap()),
            want["state"]["live_execution"],
            "{name}: the raw union"
        );
        assert_eq!(json!(live.as_bool().unwrap()), want["view"], "{name}");
        match (row.durable_open.len(), live.refs().unwrap().len()) {
            (1, 2) => with_two += 1,
            (0, 1) => only_overlay += 1,
            (1, 1) => only_durable += 1,
            _ => {}
        }
    }
    // Each case this exists for, or it says little.
    assert!(with_two >= 1, "no running dispatch with two references");
    assert!(only_overlay >= 2, "no unrecorded and fallback handles");
    assert!(only_durable >= 2, "nothing durably open alone");
    let of = |name: &str| rows[names.iter().position(|n| n == name).unwrap()].clone();
    assert!(of("input").response_present);
    assert!(!of("input with nothing yet").response_present);
    assert!(of("question on no post").turn.is_none());
    assert!(of("question attached later").turn.is_some());
    assert_eq!(of("reassigned").assigned.history.len(), 3);
    assert!(of("unassigned").unassigned);
    assert!(of("delegated").satisfied_by.is_empty(), "the child's own");
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

/// A stand-in for Python's transport, answering the real envelope a test gives it. Holds the next
/// request if asked to, and tells the test when one has come.
struct StandIn {
    address: std::net::SocketAddr,
    answer: Arc<Mutex<String>>,
    hold_next: Arc<Mutex<bool>>,
    never_answer: Arc<Mutex<bool>>,
    release: Arc<Notify>,
    requests: mpsc::UnboundedReceiver<()>,
}

async fn stand_in(answer: String) -> StandIn {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let answer = Arc::new(Mutex::new(answer));
    let hold_next = Arc::new(Mutex::new(false));
    let never_answer = Arc::new(Mutex::new(false));
    let release = Arc::new(Notify::new());
    let (told, requests) = mpsc::unbounded_channel();
    let (held_answer, held_hold, held_never, held_release) = (
        answer.clone(),
        hold_next.clone(),
        never_answer.clone(),
        release.clone(),
    );
    tokio::spawn(async move {
        loop {
            let (mut stream, _) = listener.accept().await.unwrap();
            let (answer, hold, never, release, told) = (
                held_answer.clone(),
                held_hold.clone(),
                held_never.clone(),
                held_release.clone(),
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
                if *never.lock().unwrap() {
                    tokio::time::sleep(Duration::from_secs(60)).await;
                    return;
                }
                let held = std::mem::take(&mut *hold.lock().unwrap());
                if held {
                    release.notified().await;
                }
                let body = answer.lock().unwrap().clone();
                let answer = format!(
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                );
                let _ = stream.write_all(answer.as_bytes()).await;
            });
        }
    });
    StandIn {
        address,
        answer,
        hold_next,
        never_answer,
        release,
        requests,
    }
}

/// The real client, polling, marking each poll from the real record.
fn polling(address: std::net::SocketAddr, brain: &Path) -> (Arc<Snapshots>, Arc<Reader>) {
    let reader = Arc::new(Brain::open(brain).unwrap());
    let snapshots = Arc::new(Snapshots::sampling(address, "s".into(), reader.clone()));
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

/// An end landing between a poll's marker and its answer. A poll's answer has 250 ms, so a machine
/// too slow to write inside that tries again, with a run of its own.
#[tokio::test(flavor = "multi_thread")]
async fn a_durable_end_landing_while_a_poll_is_in_flight_forwards_what_the_old_overlay_changes() {
    let (brain, mut python, _built, _reader) = world("in-flight");
    let mut stand = stand_in(python.envelope()).await;
    let (snapshots, reader) = polling(stand.address, &brain);
    for attempt in 0..5 {
        let run = python.ask(
            "expect-running",
            json!({"name": format!("flight-{attempt}")}),
        );
        let expectation = run["expectation"].as_str().unwrap().to_owned();
        // Lists the run, and is what the poll in flight will answer.
        *stand.answer.lock().unwrap() = python.envelope();
        let (_, asked_at) = state_of(&reader, &expectation);
        while stand.requests.try_recv().is_ok() {}
        *stand.hold_next.lock().unwrap() = true;
        snapshots.asked();
        // A poll that had already asked isn't this one, so wait for the one that holds.
        while *stand.hold_next.lock().unwrap() {
            stand.requests.recv().await.unwrap();
        }
        let landed = Instant::now();
        python.ask("end-durably", run.clone());
        let in_time = landed.elapsed() < Duration::from_millis(150);
        stand.release.notify_one();
        tokio::time::sleep(Duration::from_millis(60)).await;

        let (state, read) = state_of(&reader, &expectation);
        assert!(state.durable_open.is_empty(), "the end landed");
        let overlay = snapshots.overlay().expect("fresh");
        // Only to see the setup happened, as of before the end, where this poll is coherent.
        let names_it = overlay.active_executions(asked_at).is_ok_and(|held| {
            held.iter()
                .any(|e| e.for_expectation.as_deref() == Some(expectation.as_str()))
        });
        if !in_time || !names_it || overlay.coherent_with(read) {
            continue;
        }
        let live = overlay.live_execution(&state, read).unwrap();
        assert!(
            forwarded(live.as_bool()),
            "only the old poll says it's live"
        );
        assert!(forwarded(live.refs()));
        assert!(forwarded(overlay.active_executions(read)));
        assert!(forwarded(overlay.run_observations(read)));
        // Nothing here answered from the old poll: the forward asks Python, whose answer is current.
        return;
    }
    panic!("no attempt landed inside a poll");
}

#[tokio::test(flavor = "multi_thread")]
async fn a_moved_record_with_an_overlay_that_changes_nothing_does_not_forward() {
    let (brain, mut python, built, _reader) = world("moved");
    let mut stand = stand_in(python.envelope()).await;
    let (snapshots, reader) = polling(stand.address, &brain);
    let overlay = fresh_overlay(&snapshots).await;
    let (_, before) = state_of(&reader, &id_of(&built, "plain"));
    assert!(overlay.coherent_with(before), "the marker is the record's");
    // No later poll answers, so the one held stays the one that was marked before the move.
    *stand.never_answer.lock().unwrap() = true;
    while stand.requests.try_recv().is_ok() {}
    stand.requests.recv().await.unwrap();
    let overlay = snapshots.overlay().expect("still fresh");

    python.ask("post", json!({}));
    let (plain, read) = state_of(&reader, &id_of(&built, "plain"));
    assert_ne!(read, before, "the record moved");
    assert!(!overlay.coherent_with(read));

    // No handle concerns it, so the overlay makes no difference at all.
    let live = overlay.live_execution(&plain, read).unwrap();
    assert_eq!(live.as_bool(), Ok(false));
    assert!(live.refs().unwrap().is_empty());
    let held = overlay.active_executions(before).unwrap().len();
    assert_eq!(live_count(&overlay, read, held), Ok(held));
    assert!(forwarded(live_count(&overlay, read, held + 1)));
    // A read that shows the lists has said nothing about its answer, so it forwards.
    assert!(forwarded(overlay.active_executions(read)));
    assert!(forwarded(overlay.run_observations(read)));
    assert!(overlay.active_executions(before).is_ok());
    assert!(overlay.run_observations(before).is_ok());

    // Durably open, with its second reference in the overlay: the boolean doesn't change.
    let (running, read) = state_of(&reader, &id_of(&built, "running"));
    let live = overlay.live_execution(&running, read).unwrap();
    assert_eq!(live.as_bool(), Ok(true));
    assert!(forwarded(live.refs()), "the raw list does change");

    // A run only the overlay knows does change it.
    let (unrecorded, read) = state_of(&reader, &id_of(&built, "unrecorded"));
    let live = overlay.live_execution(&unrecorded, read).unwrap();
    assert!(forwarded(live.as_bool()));
}

#[test]
fn the_window_before_a_durable_end_and_the_correcting_reread_from_an_older_poll() {
    let (_brain, mut python, _built, reader) = world("reread");
    let run = python.ask("expect-running", json!({"name": "window"}));
    let expectation = run["expectation"].as_str().unwrap();
    let count_before = python.ask("active-count", json!({}))["count"]
        .as_u64()
        .unwrap() as usize;

    // The held poll: it names the run, and is marked at where the record then stood.
    let (_, marked_at) = state_of(&reader, expectation);
    let held = overlay_of(&python.snapshot(), Some(marked_at));
    assert_eq!(
        held.active_executions(marked_at).unwrap().len(),
        count_before
    );

    // `end_execution`, and no durable end yet. The record hasn't moved, so nothing forwards.
    python.ask("end-handle", run.clone());
    let python_count = python.ask("active-count", json!({}))["count"]
        .as_u64()
        .unwrap() as usize;
    assert_eq!(python_count, count_before - 1);
    let (state, read) = state_of(&reader, expectation);
    assert_eq!(read, marked_at);
    let live = held.live_execution(&state, read).unwrap();
    let python_state = python.ask("state", json!({"expectation": expectation}));
    assert_eq!(
        json!(live.as_bool().unwrap()),
        json!(
            !python_state["live_execution"]
                .as_array()
                .unwrap()
                .is_empty()
        ),
        "Turn views agree with the still-open record"
    );
    assert_eq!(
        live_count(&held, read, python_count),
        Ok(count_before),
        "the count can differ for up to one poll: the window the contract names"
    );

    // The durable end moves the record. The older poll still names the run: a reread forwards.
    python.ask("end-durably", run.clone());
    let (state, read) = state_of(&reader, expectation);
    assert_ne!(read, marked_at);
    assert!(state.durable_open.is_empty());
    assert!(forwarded(live_count(&held, read, python_count)));
    assert!(forwarded(held.active_executions(read)));
    let live = held.live_execution(&state, read).unwrap();
    assert!(forwarded(live.as_bool()));

    // A poll after the end has the right count and forwards nothing: the setup above is what the
    // forward needed, not the durable end alone.
    let newer = overlay_of(&python.snapshot(), Some(read));
    assert_eq!(newer.active_executions(read).unwrap().len(), python_count);
    assert_eq!(live_count(&newer, read, python_count + 1), Ok(python_count));
    let live = newer.live_execution(&state, read).unwrap();
    assert_eq!(live.as_bool(), Ok(false));
    let python_state = python.ask("state", json!({"expectation": expectation}));
    assert_eq!(python_state["live_execution"], json!([]));
}

#[test]
fn the_byte_rule_with_the_real_producers_forwards_exactly_the_field_it_omits() {
    let (_brain, mut python, built, reader) = world("over-cap");
    let whole = python.snapshot();
    let active = whole.fields.active_executions.clone().unwrap();
    assert!(!active.is_empty());
    let runs = whole.fields.run_observations.clone().unwrap();
    let going = runs.get("opr-going").unwrap();
    assert_eq!(going.activity.as_deref(), Some("Run npm test"));
    assert_eq!(going.permissions.len(), 1);
    assert_eq!(going.tooling, None, "absent until the run has ended");
    let ended = runs.get("opr-ended").unwrap();
    assert!(ended.ended_at.is_some());
    assert!(ended.consent_applied.as_ref().unwrap().is_null());
    assert_eq!(
        ended.tooling.as_ref().unwrap().text(),
        r#"{"mcp": ["mentis"], "n": 1.1}"#
    );
    let sized = python.ask("field-sizes", json!({}))["active_executions"]
        .as_u64()
        .unwrap();

    // Room for the first field and not the second: it keeps its place, and the second goes.
    python.ask("cap", json!({"most": sized + 8}));
    let cut = python.snapshot();
    assert_eq!(
        cut.fields.active_executions.as_ref().unwrap().len(),
        active.len()
    );
    assert_eq!(cut.fields.run_observations, None);
    assert_eq!(cut.live_hash, whole.live_hash);
    let (state, read) = state_of(&reader, &id_of(&built, "running"));
    let overlay = overlay_of(&cut, Some(read));
    assert!(overlay.live_execution(&state, read).is_ok());
    assert_eq!(overlay.active_executions(read).unwrap().len(), active.len());
    assert!(forwarded(overlay.run_observations(read)));
    assert!(forwarded(overlay.work_out(read, false, |_, live| {
        live.run_observations()?;
        Ok(None)
    })));

    // Room for neither: nothing reads the overlay, and the envelope still answers the pulse.
    python.ask("cap", json!({"most": 2}));
    let none = python.snapshot();
    assert_eq!(none.fields.active_executions, None);
    assert_eq!(none.live_hash, whole.live_hash);
    let overlay = overlay_of(&none, Some(read));
    assert!(forwarded(overlay.live_execution(&state, read)));
    assert!(forwarded(overlay.active_executions(read)));
    assert!(forwarded(live_count(&overlay, read, active.len())));
}

/// The real client with no record to sample, so every poll it holds is markerless, over the real
/// producers' fields.
#[tokio::test(flavor = "multi_thread")]
async fn a_markerless_poll_forwards_through_every_path_to_the_lists() {
    let (_brain, mut python, built, reader) = world("markerless");
    let envelope = python.snapshot();
    let stand = stand_in(python.envelope()).await;
    let snapshots = Arc::new(Snapshots::new(stand.address, "s".into()));
    let polls = snapshots.clone();
    tokio::spawn(async move { polls.poll_while_asked().await });
    snapshots.asked();
    let overlay = fresh_overlay(&snapshots).await;
    let (unrecorded, read) = state_of(&reader, &id_of(&built, "unrecorded"));

    assert!(forwarded(overlay.active_executions(read)));
    assert!(forwarded(overlay.run_observations(read)));
    assert!(forwarded(live_count(&overlay, read, usize::MAX)));
    let live = overlay.live_execution(&unrecorded, read).unwrap();
    assert!(forwarded(live.as_bool()));
    assert!(forwarded(live.refs()));

    // The same poll answers a read it makes no difference to: both fields are there. How many it
    // holds comes from the envelope, because the overlay won't say.
    let held = envelope.fields.active_executions.unwrap().len();
    assert!(held > 0, "the real producers listed the running handles");
    assert_eq!(live_count(&overlay, read, held), Ok(held));
    let both = overlay.work_out(read, 9usize, |_, live| {
        live.run_observations()?;
        live.active_executions()?;
        Ok(None)
    });
    assert_eq!(both, Ok(9));
}

/// By hand: `MENTIS_R4_BRAIN` is a copy, read by Python in full first.
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
