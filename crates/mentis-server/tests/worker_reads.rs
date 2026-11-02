//! **Byte equality on the wire.** Each moved read, across its arguments and every `resolve` kind
//! present, answers the exact bytes of Python's `json.dumps(_result(...), default=str)` on the same
//! Brain, or is forwarded. `support/worker_reads_side.py` says what Python says.
//!
//! A read that always forwarded would pass silently, so each is counted, per op and per kind, the
//! counts are printed (`-- --nocapture`), and what must be answered is asserted to have been.

#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use mentis_ops::resolve::{Resolve, ResolveArgs};
use mentis_ops::{OpError, ReadClass, ReadRequest};
use mentis_record::{Brain, BrainOpener, RecordReader};
use mentis_server::worker_reads::{MOVED, Read, python_text, read};
use serde_json::{Map, Value};

fn side(arg: &str, brain: &Path) -> String {
    let script = support::repo_root()
        .join("crates")
        .join("mentis-server")
        .join("tests")
        .join("support")
        .join("worker_reads_side.py");
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

fn world() -> &'static (PathBuf, Value) {
    static WORLD: OnceLock<(PathBuf, Value)> = OnceLock::new();
    WORLD.get_or_init(|| {
        let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "worker-reads");
        side("change", &brain);
        let answers = side("wire", &brain);
        (brain, serde_json::from_str(&answers).unwrap())
    })
}

#[derive(Default, Clone, Copy)]
struct Count {
    answered: u32,
    /// By the door's own rule, on arguments it won't carry.
    by_the_door: u32,
    /// With arguments it would carry: the op said `NotOwned`, or the words want a `repr` it can't say.
    by_the_op: u32,
}

/// A resolve Python answers and this forwards: why, by the op's own words.
fn why_forwarded(reader: &dyn RecordReader, args: &Map<String, Value>) -> String {
    let Some(reference) = args.get("ref").and_then(Value::as_str) else {
        return "the door: `ref` isn't text".to_owned();
    };
    let request = ReadRequest {
        args: ResolveArgs {
            reference: reference.to_owned(),
        },
        cursor: None,
        limit: None,
        deadline: Instant::now() + Duration::from_secs(20),
    };
    match mentis_ops::run(&Resolve, reader, ReadClass::Agent, &request) {
        Err(OpError::NotOwned { why }) => why,
        Ok(_) => "the door: the op answered and the door forwarded".to_owned(),
        Err(other) => format!("{other}"),
    }
}

#[test]
fn every_moved_read_is_python_s_bytes_or_forwarded() {
    let (brain, world) = world();
    let reader = Brain::open(brain).unwrap();
    let at = world["at"].as_f64().unwrap();
    let cases = world["cases"].as_array().unwrap();

    let mut counts: BTreeMap<(String, String), Count> = BTreeMap::new();
    let mut reasons: BTreeMap<String, u32> = BTreeMap::new();
    let mut failures: Vec<String> = Vec::new();
    let mut other_forwards: Vec<String> = Vec::new();
    let mut compared: Vec<String> = Vec::new();
    let mut python_failed_and_forwarded = 0;
    for case in cases {
        let op = case["op"].as_str().unwrap();
        let args = case["args"].as_object().unwrap();
        let must_forward = case["forward"].as_bool().unwrap();
        let body = case.get("body").and_then(Value::as_str);
        let sort = case["sort"].as_str().unwrap();
        let got = read(op, args, &reader, at);
        let count = counts.entry((op.to_owned(), sort.to_owned())).or_default();
        match got {
            Read::Body(got) => {
                count.answered += 1;
                let got = String::from_utf8(got).expect("an answer is UTF-8");
                if must_forward {
                    failures.push(format!("{op} {args:?}: must forward, answered {got}"));
                } else if case.get("raises").is_some() {
                    failures.push(format!(
                        "{op} {args:?}: Python raised {}, this answered {got}",
                        case["raises"]
                    ));
                } else if body == Some(got.as_str()) {
                    compared.push(got);
                } else {
                    failures.push(format!(
                        "{op} {args:?}:\n  python {}\n  rust   {got}",
                        body.unwrap_or("?")
                    ));
                }
            }
            Read::NotOwned => {
                python_failed_and_forwarded += u32::from(case.get("raises").is_some());
                if must_forward {
                    count.by_the_door += 1;
                } else {
                    count.by_the_op += 1;
                    if op == "resolve" {
                        *reasons
                            .entry(format!("{sort}: {}", why_forwarded(&reader, args)))
                            .or_default() += 1;
                    } else {
                        other_forwards.push(format!("{op} {sort}: {}", case["args"]));
                    }
                }
            }
        }
    }

    println!("{} cases", cases.len());
    println!(
        "{:<18} {:<46} {:>8} {:>11} {:>10}",
        "op", "kind", "answered", "fwd by door", "fwd by op"
    );
    for ((op, sort), count) in &counts {
        println!(
            "{op:<18} {sort:<46} {:>8} {:>11} {:>10}",
            count.answered, count.by_the_door, count.by_the_op
        );
    }
    println!("other forwards, with arguments the door carries:");
    for one in &other_forwards {
        println!("  {one}");
    }
    println!("resolve, forwarded, why:");
    for (why, count) in &reasons {
        println!("  {count:>5}  {why}");
    }
    println!("Python itself failed and this forwarded: {python_failed_and_forwarded}");

    let shown = failures.len().min(12);
    assert!(
        failures.is_empty(),
        "{} differ, first {shown}:\n{}",
        failures.len(),
        failures[..shown].join("\n")
    );

    // What is hardest to get right in bytes, shown to have been among what compared equal.
    for needle in [
        "\"revision\": {\"versions\": ",
        "\"deleted\": {\"record\": ",
        "DELETED MATERIAL: this came in on a turn",
        "\"deleted_material\": \"adm-",
        "a decision form: each question",
        "an attributed occurrence",
        "\"standing\": \"governing: established",
        "\"standing\": \"ended: superseded by later material\"",
        "\"standing\": \"proposed: written down, established by nobody, and governing",
        "\"standing\": \"established: carried forward",
        "\"standing\": \"proposed: written down, established by nobody, and asserted",
        "more changes follow",
        "nothing after cursor yet",
        "\"decision_form\": true",
        "\"groups\": [\"proposed\", \"recorded\"",
        "\"hint\": \"ask /api/kinds",
        // The stored body and the act's detail, past Python's own `json`.
        "\"z\": {\"again\": true}, \"a\": [100.0, 1e+16, 1e-05, -0.0, 0, 12345678901234567890123]",
        "\"lone\": \"\\ud800\"",
        "\\u00e9 caf\\u00e9 \\u00fcber \\ud83d\\ude00",
        "\"f\": 1.5e+300",
        "\"small\": 1e-07",
        "\"whole\": 3.0",
        "\"n\": -0.0",
        "123456789012345678901234567890",
        "words\\nand \\\"quotes\\\" \\\\ too",
    ] {
        assert!(
            compared.iter().any(|body| body.contains(needle)),
            "no answer compared held {needle}"
        );
    }

    // A read that always forwards doesn't pass here.
    for op in MOVED {
        let answered: u32 = counts
            .iter()
            .filter(|((held, _), _)| held == op)
            .map(|(_, count)| count.answered)
            .sum();
        assert!(answered > 0, "{op} never answered");
    }
    let answered = |op: &str, sort: &str| {
        counts
            .get(&(op.to_owned(), sort.to_owned()))
            .map_or(0, |count| count.answered)
    };
    for what in [
        "a Turn",
        "a Conversation",
        "a Participant",
        "a Topic",
        "a Reaction",
        "a Link",
        "not known",
    ] {
        assert!(answered("resolve", what) > 0, "no {what} answered");
    }
    assert!(
        counts
            .keys()
            .any(|(op, sort)| op == "resolve" && sort.starts_with("an entry of kind")),
        "no entry of another kind"
    );
    for (op, sort) in [
        ("history", "page"),
        ("history", "refused"),
        ("history", "set changes"),
        ("owner_decisions", "page"),
        ("owner_decisions", "refused"),
        ("governed", "page"),
        ("governed", "refused"),
    ] {
        assert!(answered(op, sort) > 0, "no {op} {sort} answered");
    }
    // Section 4's: these wait for `held` and R2's `extract`, and this build keeps them.
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
            reasons.keys().any(|held| held.ends_with(why)),
            "nothing forwarded as {why}: {reasons:#?}"
        );
    }
}

#[test]
fn the_renderer_says_what_python_s_json_says_of_a_stored_body() {
    let (_, world) = world();
    assert_eq!(
        python_text(world["odd_body"].as_str().unwrap()).as_deref(),
        world["odd_body_dumped"].as_str()
    );
}
