//! **Byte equality against Python, or forwarded.** R5.1's routes through their handlers and its two
//! agent reads through the door's read, on one changed BRAIN-SEED holding edited and deleted posts,
//! attachments, damaged files and object references. `support/object_reads_side.py` says what Python
//! says, and the real bundle reads the same dist on both sides.
//!
//! A read that always forwarded would pass, so each is counted by what it is, the counts are printed
//! (`-- --nocapture`), and what must be answered is asserted to have been. So is what must forward.

#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::collections::BTreeMap;
use std::net::{Ipv4Addr, SocketAddr};
use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;
use std::sync::{Arc, OnceLock};
use std::time::{Duration, Instant};

use mentis_ops::post_search::{self, SearchAsk};
use mentis_ops::window::Window;
use mentis_ops::{OpError, ReadClass};
use mentis_record::{Brain, BrainOpener, RecordReader};
use mentis_server::front::snapshot::Snapshots;
use mentis_server::handlers::{self, Ask, Context, Reply};
use mentis_server::object_worker_reads;
use mentis_server::worker_reads::Read;
use serde_json::{Map, Value, json};

fn dist() -> PathBuf {
    support::fixtures()
        .join("py-b8e324c")
        .join("apps")
        .join("fluid-web")
        .join("dist")
}

fn side(args: &[&str]) -> String {
    let script = support::repo_root()
        .join("crates")
        .join("mentis-server")
        .join("tests")
        .join("support")
        .join("object_reads_side.py");
    let done = support::python()
        .env("MENTIS_FLUID_DIST", dist())
        .arg(script)
        .args(args)
        .output()
        .expect("Python starts");
    assert!(
        done.status.success(),
        "Python failed: {}",
        String::from_utf8_lossy(&done.stderr)
    );
    String::from_utf8(done.stdout).expect("Python's output is UTF-8")
}

fn on_brain(arg: &str, brain: &Path) -> String {
    side(&[arg, brain.to_str().unwrap()])
}

fn world() -> &'static (PathBuf, Value) {
    static WORLD: OnceLock<(PathBuf, Value)> = OnceLock::new();
    WORLD.get_or_init(|| {
        let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "object-reads");
        on_brain("change", &brain);
        let answers = on_brain("wire", &brain);
        (brain, serde_json::from_str(&answers).unwrap())
    })
}

fn context(brain: &Path) -> Context {
    let record: Arc<dyn RecordReader> = Arc::new(Brain::open(brain).unwrap());
    Context {
        dist: dist(),
        record,
        snapshots: Arc::new(Snapshots::new(
            SocketAddr::from((Ipv4Addr::LOCALHOST, 1)),
            String::new(),
        )),
        window: Arc::new(Window::new(brain, &dist())),
    }
}

fn ask(path: &str, query: &str) -> Ask {
    Ask {
        gone: Arc::new(AtomicBool::new(false)),
        method: "GET".to_owned(),
        path: path.to_owned(),
        query: query.to_owned(),
        headers: Vec::new(),
    }
}

/// `query` as a head holds it: anything past printable ASCII as Latin-1 text.
fn answered(name: &str, context: &Context, path: &str, query: &str) -> Reply {
    let route = handlers::find(name).expect("this build has the route");
    (route.answer)(context, &ask(path, query))
}

#[derive(Default, Clone, Copy)]
struct Count {
    answered: u32,
    forwarded: u32,
}

#[test]
fn every_read_is_python_s_bytes_or_forwarded() {
    let (brain, world) = world();
    let context = context(brain);
    let cases = world["cases"].as_array().unwrap();

    let mut counts: BTreeMap<(String, String), Count> = BTreeMap::new();
    let mut failures: Vec<String> = Vec::new();
    let mut compared: Vec<(String, String)> = Vec::new();
    let mut forwarded: Vec<String> = Vec::new();
    for case in cases {
        let sort = case["sort"].as_str().unwrap();
        let (name, shown, got) = if let Some(route) = case.get("route").and_then(Value::as_str) {
            let query = case["query"].as_str().unwrap();
            let path = case["path"].as_str().unwrap();
            let shown = format!("{route}?{query}");
            let got = match answered(route, &context, path, query) {
                Reply::Answer { status, body, .. } => {
                    Some((status, String::from_utf8(body).expect("an answer is UTF-8")))
                }
                Reply::NotOwned => None,
            };
            (route.to_owned(), shown, got)
        } else {
            let op = case["op"].as_str().unwrap();
            let args: Map<String, Value> = case["args"].as_object().unwrap().clone();
            let got = match object_worker_reads::read(op, &args, &*context.record, &context.window)
            {
                Read::Body(body) => {
                    Some((200, String::from_utf8(body).expect("an answer is UTF-8")))
                }
                Read::NotOwned => None,
            };
            (
                op.to_owned(),
                format!("{op} {}", cut(&case["args"].to_string())),
                got,
            )
        };
        let count = counts.entry((name.clone(), sort.to_owned())).or_default();
        match got {
            None => {
                count.forwarded += 1;
                forwarded.push(shown);
            }
            Some((status, body)) => {
                count.answered += 1;
                let want = case.get("body").and_then(Value::as_str);
                let want_status = case.get("status").and_then(Value::as_u64);
                if case.get("raises").is_some() {
                    failures.push(format!(
                        "{shown}: Python raised {}, this answered {status} {}",
                        case["raises"],
                        cut(&body)
                    ));
                } else if want != Some(body.as_str()) || want_status != Some(u64::from(status)) {
                    failures.push(format!(
                        "{shown}:\n  python {want_status:?} {}\n  rust   {status} {}",
                        cut(want.unwrap_or("?")),
                        cut(&body)
                    ));
                } else {
                    compared.push((sort.to_owned(), body));
                }
            }
        }
    }

    println!("{} cases", cases.len());
    println!(
        "{:<18} {:<20} {:>8} {:>9}",
        "read", "sort", "answered", "forwarded"
    );
    for ((name, sort), count) in &counts {
        println!(
            "{name:<18} {sort:<20} {:>8} {:>9}",
            count.answered, count.forwarded
        );
    }
    let shown = failures.len().min(12);
    assert!(
        failures.is_empty(),
        "{} differ, first {shown}:\n{}",
        failures.len(),
        failures[..shown].join("\n")
    );

    let answered = |name: &str, sort: &str| {
        counts
            .get(&(name.to_owned(), sort.to_owned()))
            .map_or(0, |count| count.answered)
    };
    let forwards = |name: &str, sort: &str| {
        counts
            .get(&(name.to_owned(), sort.to_owned()))
            .map_or(0, |count| count.forwarded)
    };
    // A read that always forwards doesn't pass here.
    for (name, sort) in [
        ("document", "held"),
        ("document", "no bytes"),
        ("document", "refused"),
        ("object-refs", "post"),
        ("object-refs", "not a post"),
        ("object-refs", "one part"),
        ("object-refs", "refused"),
        ("post-search", "needle"),
        ("post-search", "paged"),
        ("post-search", "refused"),
        ("references", "resolve"),
        ("references", "find"),
        ("find", "find"),
        ("check_rendering", "checked"),
        ("check_rendering", "too long"),
        ("check_rendering", "nothing given"),
    ] {
        assert!(answered(name, sort) > 0, "no {name} {sort} answered");
    }
    // What this package has said it forwards, shown to, and never answered.
    for (name, sort) in [
        ("post-search", "other letters"),
        ("post-search", "garbled"),
        ("references", "odd limit"),
        ("find", "odd arguments"),
        ("check_rendering", "forward: a list"),
        ("check_rendering", "forward: syntax"),
        ("check_rendering", "forward: odd"),
        ("check_rendering", "forward: a NUL"),
    ] {
        assert!(forwards(name, sort) > 0, "no {name} {sort} forwarded");
        assert_eq!(answered(name, sort), 0, "{name} {sort} answered");
    }

    // What is hardest to get right, shown to have been among what compared equal.
    for needle in [
        "\"cut\": true",
        "\"cut\": false",
        "\\ufffd",
        "no bytes to read: the artifact is held-but-missing",
        "no bytes to read: the artifact is held-but-corrupt",
        "no bytes to read: the artifact is purged",
        "no bytes to read: the artifact is unknown",
        "no bytes to read: the artifact is not-an-artifact",
        "\"resolves\": true",
        "\"resolves\": false",
        "\"exact_resolves\": true",
        "\"exact_resolves\": false",
        "\"exact_why\": ",
        "no longer resolves: the current version",
        "the post was deleted; its objects are not served",
        "the reference names no post and key",
        "not an object address",
        "\"snippet\": \"...",
        "...\", \"at\": ",
        "\"more\": true",
        "\"exact\": \"identity\"",
        "\"exact\": \"coordinate\"",
        "\"ambiguous\": true",
        "\"what\": \"participant\"",
        "\"what\": \"conversation\"",
        "\"what\": \"topic\"",
        "\"what\": \"link\"",
        "\"what\": \"turn\"",
        "\"not_searched\": null",
        "\"not_searched\": {\"non_text\": 0",
        "nothing to search for",
        "a dry run: nothing was written. No problems",
        "error(s) and",
        "\"built_from\": ",
        "shown as unresolved",
        "it is a ",
        "Mentis holds no entry with that id",
        "Its Markdown was NOT checked for rendering",
        "give `text` to check",
    ] {
        assert!(
            compared.iter().any(|(_, body)| body.contains(needle)),
            "no answer compared held {needle}"
        );
    }
    // A long list of forwards is a report's number. Printed so it is looked at.
    println!("forwarded: {}", forwarded.len());
}

fn cut(text: &str) -> String {
    let mut out: String = text.chars().take(600).collect();
    if out.len() < text.len() {
        out.push_str("...");
    }
    out
}

fn copy_dir(from: &Path, to: &Path) {
    std::fs::create_dir_all(to).unwrap();
    for entry in std::fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        let target = to.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy_dir(&entry.path(), &target);
        } else if entry.file_name() != ".mentis.lock" {
            std::fs::copy(entry.path(), target).unwrap();
        }
    }
}

/// `find`'s content hits are R5.2's source scan. Until it is here a Brain with a source declared forwards
/// the whole request, whichever door it came by, however the question reads.
#[test]
fn a_brain_with_a_source_declared_forwards_every_find() {
    let (brain, world) = world();
    let copy = brain.parent().unwrap().join("declared");
    let _ = std::fs::remove_dir_all(&copy);
    copy_dir(brain, &copy);
    on_brain("declare", &copy);
    let context = self::context(&copy);
    let known = world["world"]["known"].as_str().unwrap();
    for q in ["needle", "1", "ent-000000000000", "r1", "zzz-no-such"] {
        assert_eq!(
            answered("references", &context, "/api/references", &format!("q={q}")),
            Reply::NotOwned,
            "{q}"
        );
        let mut args = Map::new();
        args.insert("q".to_owned(), json!(q));
        assert_eq!(
            object_worker_reads::read("find", &args, &*context.record, &context.window),
            Read::NotOwned,
            "{q}"
        );
    }
    // A blank question reads nothing and is still answered, as is `ref=`: neither is the scan's.
    assert!(matches!(
        answered("references", &context, "/api/references", "q=%20"),
        Reply::Answer { status: 200, .. }
    ));
    assert!(matches!(
        answered(
            "references",
            &context,
            "/api/references",
            &format!("ref={known}")
        ),
        Reply::Answer { status: 200, .. }
    ));
}

/// A matching Turn with a fillable block asks the render engine what it takes, so it's Python's.
#[test]
fn a_matching_turn_with_a_fillable_block_forwards_and_nothing_else_does() {
    let (brain, _) = world();
    let context = self::context(brain);
    assert_eq!(
        answered("references", &context, "/api/references", "q=fencedword"),
        Reply::NotOwned
    );
    assert!(matches!(
        answered("references", &context, "/api/references", "q=kelvin"),
        Reply::Answer { status: 200, .. }
    ));
}

/// An engine failure's words hold Python's own exception, and a bundle that isn't there holds its path.
#[test]
fn a_missing_bundle_forwards_what_needs_it_and_answers_what_does_not() {
    let (brain, world) = world();
    let record: Arc<dyn RecordReader> = Arc::new(Brain::open(brain).unwrap());
    let context = Context {
        dist: dist(),
        record,
        snapshots: Arc::new(Snapshots::new(
            SocketAddr::from((Ipv4Addr::LOCALHOST, 1)),
            String::new(),
        )),
        window: Arc::new(Window::new(brain, "no-such-dist".as_ref())),
    };
    let mut args = Map::new();
    args.insert("text".to_owned(), json!("plain words"));
    assert_eq!(
        object_worker_reads::read("check_rendering", &args, &*context.record, &context.window),
        Read::NotOwned
    );
    let w = &world["world"];
    assert_eq!(
        answered(
            "object-refs",
            &context,
            "/fluid/api/object-refs",
            &format!("post={}", w["holder"].as_str().unwrap())
        ),
        Reply::NotOwned
    );
    // Neither of these has anything to extract.
    assert!(matches!(
        answered(
            "object-refs",
            &context,
            "/fluid/api/object-refs",
            &format!("post={}", w["plain_post"].as_str().unwrap())
        ),
        Reply::Answer { status: 200, .. }
    ));
    assert!(matches!(
        answered(
            "document",
            &context,
            "/fluid/api/document",
            &format!("ref={}", w["plain"].as_str().unwrap())
        ),
        Reply::Answer { status: 200, .. }
    ));
}

/// `re`'s own relation, for every printable ASCII needle and every code point: this is what makes an
/// ASCII needle Rust's to answer, and it fails if a new Python's tables move.
#[test]
fn an_ascii_needle_matches_what_re_matches() {
    let letters: Value = serde_json::from_str(&side(&["letters"])).unwrap();
    for (needle, matches) in letters.as_object().unwrap() {
        let needle = needle.chars().next().unwrap();
        let mut want: Vec<u32> = matches
            .as_array()
            .unwrap()
            .iter()
            .map(|c| c.as_u64().unwrap() as u32)
            .collect();
        want.sort_unstable();
        let got: Vec<u32> = (0..0x11_0000u32)
            .filter_map(char::from_u32)
            .filter(|c| post_search::matches_needle(needle, *c))
            .map(u32::from)
            .collect();
        assert_eq!(got, want, "{needle:?}");
    }
}

/// The same comparison on a copy of a real Brain, sampled: what each read answers there, how often it
/// forwards, and what it costs either side. `MENTIS_R5_BRAIN` names the copy, and nothing here is a line
/// it has to pass but equal bytes.
#[test]
#[ignore = "needs MENTIS_R5_BRAIN, a Brain copy made with the backup API"]
fn a_real_brain_copy_says_the_same() {
    let brain = PathBuf::from(std::env::var("MENTIS_R5_BRAIN").expect("MENTIS_R5_BRAIN"));
    let answers: Value = serde_json::from_str(&on_brain("sample", &brain)).unwrap();
    let context = self::context(&brain);
    println!(
        "declared sources {}; posts {}; holding object references {}; held artifacts {}; largest {}",
        answers["declared"],
        answers["posts"],
        answers["holding"],
        answers["held"],
        answers["sizes"]
    );
    struct Seen {
        answered: u32,
        forwarded: u32,
        rust_ms: Vec<f64>,
        python_ms: Vec<f64>,
    }
    let mut seen: BTreeMap<(String, String), Seen> = BTreeMap::new();
    let mut failures = Vec::new();
    let median = |values: &mut Vec<f64>| {
        values.sort_by(f64::total_cmp);
        values.get(values.len() / 2).copied().unwrap_or(0.0)
    };
    for case in answers["cases"].as_array().unwrap() {
        let sort = case["sort"].as_str().unwrap().to_owned();
        let started = Instant::now();
        let (name, shown, got) = if let Some(route) = case.get("route").and_then(Value::as_str) {
            let query = case["query"].as_str().unwrap();
            let got = match answered(route, &context, case["path"].as_str().unwrap(), query) {
                Reply::Answer { body, .. } => Some(String::from_utf8(body).unwrap()),
                Reply::NotOwned => None,
            };
            (route.to_owned(), format!("{route}?{query}"), got)
        } else if let Some(question) = case.get("record_hits").and_then(Value::as_str) {
            let asked = mentis_ops::find::FindAsk {
                q: question.to_owned(),
                limit: 40,
                here: None,
            };
            let got = mentis_ops::find::record_hits(&*context.record, ReadClass::Agent, &asked)
                .map(|value| value.dumps())
                .ok();
            (
                "find, record half".to_owned(),
                format!("find {question}"),
                got,
            )
        } else {
            let op = case["op"].as_str().unwrap();
            let args = case["args"].as_object().unwrap();
            let got = match object_worker_reads::read(op, args, &*context.record, &context.window) {
                Read::Body(body) => Some(String::from_utf8(body).unwrap()),
                Read::NotOwned => None,
            };
            (
                op.to_owned(),
                format!("{op} {}", cut(&case["args"].to_string())),
                got,
            )
        };
        let took = started.elapsed().as_secs_f64() * 1e3;
        let row = seen.entry((name, sort)).or_insert(Seen {
            answered: 0,
            forwarded: 0,
            rust_ms: Vec::new(),
            python_ms: Vec::new(),
        });
        match got {
            None => row.forwarded += 1,
            Some(body) => {
                row.answered += 1;
                row.rust_ms.push(took);
                row.python_ms.push(case["py_ms"].as_f64().unwrap_or(0.0));
                if case.get("body").and_then(Value::as_str) != Some(body.as_str()) {
                    failures.push(format!(
                        "{shown}:\n  python {}\n  rust   {}",
                        cut(case.get("body").and_then(Value::as_str).unwrap_or("?")),
                        cut(&body)
                    ));
                }
            }
        }
    }
    println!(
        "{:<20} {:<22} {:>8} {:>9} {:>12} {:>14}",
        "read", "sort", "answered", "forwarded", "rust med ms", "python med ms"
    );
    for ((name, sort), row) in &mut seen {
        println!(
            "{name:<20} {sort:<22} {:>8} {:>9} {:>12.2} {:>14.2}",
            row.answered,
            row.forwarded,
            median(&mut row.rust_ms),
            median(&mut row.python_ms)
        );
    }
    let shown = failures.len().min(8);
    assert!(
        failures.is_empty(),
        "{} differ, first {shown}:\n{}",
        failures.len(),
        failures[..shown].join("\n")
    );
}

/// What a search costs as a Conversation grows: printed for the report, with no line it has to pass.
/// `MENTIS_R5_SEARCH_SIZES` names the sizes.
#[test]
#[ignore = "an observation: run it to see the numbers"]
fn a_search_reports_its_cost_as_a_conversation_grows() {
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "search-cost");
    let sizes =
        std::env::var("MENTIS_R5_SEARCH_SIZES").unwrap_or_else(|_| "200,1000,4000".to_owned());
    let mut total = 0;
    println!("posts added, walk, pages, posts read, statements, Rust ms");
    for size in sizes.split(',') {
        let size: usize = size.parse().unwrap();
        let add = size - total;
        let home: Value =
            serde_json::from_str(&side(&["grow", brain.to_str().unwrap(), &add.to_string()]))
                .unwrap();
        total = size;
        let reader = Brain::open(&brain).unwrap();
        for (walk, q) in [("matches at once", "ordinary"), ("no match", "zzz-no-such")] {
            let asked = SearchAsk {
                conversation: home["home"].as_str().unwrap().to_owned(),
                q: Some(q.to_owned()),
                before: None,
                limit: 30,
            };
            let mut best = Duration::MAX;
            let mut cost = None;
            for _ in 0..3 {
                let started = Instant::now();
                let (_, spent) = post_search::conversation(&reader, ReadClass::Foreground, &asked)
                    .unwrap_or_else(|why: OpError| panic!("{why}"));
                best = best.min(started.elapsed());
                cost = Some(spent);
            }
            let cost = cost.unwrap();
            println!(
                "{size}, {walk}, {}, {}, {}, {:.2}",
                cost.pages,
                cost.posts,
                cost.statements,
                best.as_secs_f64() * 1e3
            );
        }
    }
}
