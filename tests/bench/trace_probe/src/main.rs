//! `trace-probe ledger`: the ledger a scratch Brain must hold, one `id checksum` a line.
//! `trace-probe read ROOT`: two scopes held together, so two connections, each running `MARK` once.

use std::path::Path;

use mentis_record::{Brain, BrainOpener, Flow, LEDGER, ReadClass, ReadScope, RecordReader};

const MARK: &str = "SELECT COUNT(*) AS trace_probe_mark FROM entry";

fn mark(scope: &mut dyn ReadScope) {
    scope.query(MARK, &[], &mut |_| Ok(Flow::Continue)).unwrap();
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args[0].as_str() {
        "ledger" => {
            for (id, checksum) in LEDGER {
                println!("{id} {checksum}");
            }
        }
        "read" => {
            let reader = Brain::open(Path::new(&args[1])).unwrap();
            let mut one = reader.read_scope(ReadClass::Foreground).unwrap();
            let mut two = reader.read_scope(ReadClass::Foreground).unwrap();
            mark(one.as_mut());
            mark(two.as_mut());
            println!("connections {}", reader.connections_opened());
        }
        other => panic!("no such thing as {other}"),
    }
}
