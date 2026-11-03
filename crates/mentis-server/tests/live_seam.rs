//! The R4.1 live-field seam against real Python producers and a fixture Brain.
//!
//! Coherence behavior itself is tested inside `mentis_ops::overlay`, where the opaque read token
//! can be minted from an op's scope. This external server test deliberately cannot construct one.

#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Stdio};
use std::time::{Duration, Instant};

use mentis_ops::expectation_states::{ExpectationState, ExpectationStates, ExpectationStatesArgs};
use mentis_ops::{OpError, ReadOp, ReadRequest};
use mentis_record::{Brain, BrainOpener, Position, ReadClass, RecordReader};
use serde_json::{Value, json};

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
