//! One read scope in a process of its own, for row H of `docs/rust/R1-acceptance.md`, which needs a
//! stuck reader beside Python's writes and the front names no way to hold one.
//!
//!     r1_reader <brain> report|write|running|idle|callback
//!
//! Prints one JSON line when the snapshot exists, and one with the answer.

use std::io::Write;
use std::path::Path;
use std::time::{Duration, Instant};

use mentis_record::{Brain, BrainOpener, Flow, READ_SCOPE_ENDED_WITHIN, ReadClass, RecordReader};

const ENDLESS: &str = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) \
                       SELECT COUNT(*) FROM n";
const ALL_ENTRIES: &str = "SELECT id FROM entry ORDER BY seq";
const FORGED: &str = "INSERT INTO corpus (one) VALUES (2)";
const VERSION: &str = "SELECT sqlite_version()";
const OPTIONS: &str = "PRAGMA compile_options";

/// How long a stuck reader stays stuck: well past when it must have been ended.
const STUCK_FOR: Duration = Duration::from_secs(4);

fn say(line: String) {
    let mut out = std::io::stdout();
    writeln!(out, "{line}").expect("stdout");
    out.flush().expect("stdout");
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let [_, brain, mode] = args.as_slice() else {
        panic!("r1_reader <brain> report|write|running|idle|callback");
    };
    let reader = match Brain::open(Path::new(brain)) {
        Ok(reader) => reader,
        Err(refused) => panic!("{refused}"),
    };
    let began = Instant::now();
    let mut scope = reader.read_scope(ReadClass::Foreground).expect("a scope");
    say(format!("{{\"snapshot\": \"{}\"}}", scope.position()));
    let answer = match mode.as_str() {
        "report" => {
            let mut lines = Vec::new();
            for sql in [VERSION, OPTIONS] {
                scope
                    .query(sql, &[], &mut |row| {
                        lines.push(row.value(0)?.text().unwrap_or_default().to_string());
                        Ok(Flow::Continue)
                    })
                    .expect("a report");
            }
            say(format!("{{\"lines\": {lines:?}}}"));
            return;
        }
        "write" => scope.query(FORGED, &[], &mut |_| Ok(Flow::Continue)),
        "running" => scope.query(ENDLESS, &[], &mut |_| Ok(Flow::Continue)),
        "idle" => {
            std::thread::sleep(STUCK_FOR);
            scope.query(ALL_ENTRIES, &[], &mut |_| Ok(Flow::Stop))
        }
        "callback" => scope.query(ALL_ENTRIES, &[], &mut |_| {
            std::thread::sleep(STUCK_FOR);
            Ok(Flow::Continue)
        }),
        other => panic!("no mode {other}"),
    };
    let words = match answer {
        Ok(()) => "ok".to_string(),
        Err(error) => error.to_string(),
    };
    let took = began.elapsed().as_millis();
    let within = READ_SCOPE_ENDED_WITHIN.as_millis();
    say(format!(
        "{{\"answer\": {words:?}, \"took_ms\": {took}, \"within_ms\": {within}}}"
    ));
}
