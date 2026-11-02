//! R2's JS gate: `gate <bundle> <inputs.jsonl> <outputs.jsonl>`. Each input line is the JSON text
//! Python would hand the bundle. Each output line is what this build's engine hands back, or
//! `!<why>` for a failure. `tests/front/test_r2_js_gate.py` compares them with `quickjs-ng`'s.
//!
//! On stderr, one JSON object of what it cost, for the investigation of the 205 ms per extraction.

use std::io::{BufRead, Write};
use std::path::Path;
use std::time::{Duration, Instant};

use mentis_extract::{Bundle, Engines};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let [_, bundle, inputs, outputs] = args.as_slice() else {
        eprintln!("gate <bundle> <inputs.jsonl> <outputs.jsonl>");
        std::process::exit(2);
    };
    let started = Instant::now();
    let bundle = Bundle::read(Path::new(bundle)).expect("the bundle reads");
    let read_bundle = started.elapsed();
    let engines = Engines::new();
    let inputs = std::fs::File::open(inputs).expect("the inputs open");
    let mut outputs =
        std::io::BufWriter::new(std::fs::File::create(outputs).expect("the outputs open"));
    let mut calls: Vec<Duration> = Vec::new();
    let mut compile = Duration::ZERO;
    for line in std::io::BufReader::new(inputs).lines() {
        let line = line.expect("an input line is UTF-8");
        match engines.extract_measured(&bundle, &line) {
            Ok((text, spent)) => {
                compile += spent.compile;
                calls.push(spent.call);
                writeln!(outputs, "{text}").expect("the outputs write");
            }
            Err(why) => writeln!(
                outputs,
                "!{}",
                why.to_string().replace(['\r', '\n'], " ")
            )
            .expect("the outputs write"),
        }
    }
    outputs.flush().expect("the outputs write");
    calls.sort();
    let at = |share: f64| -> f64 {
        calls
            .get(((calls.len() as f64 * share) as usize).min(calls.len().saturating_sub(1)))
            .map_or(0.0, |d| d.as_secs_f64() * 1000.0)
    };
    let total: Duration = calls.iter().sum();
    eprintln!(
        "{{\"calls\": {}, \"read_bundle_ms\": {:.3}, \"compile_ms\": {:.3}, \"call_total_ms\": {:.3}, \"call_p50_ms\": {:.3}, \"call_p95_ms\": {:.3}, \"call_max_ms\": {:.3}}}",
        calls.len(),
        read_bundle.as_secs_f64() * 1000.0,
        compile.as_secs_f64() * 1000.0,
        total.as_secs_f64() * 1000.0,
        at(0.5),
        at(0.95),
        at(1.0),
    );
}
