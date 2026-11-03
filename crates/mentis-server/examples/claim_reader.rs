//! The tail's own read of a claim, in a process of its own: the other half of
//! `tests/test_brainlock_claim.py`. Examples aren't part of any release.
//!
//!     claim_reader <brain>     for each line on stdin, a boot: "same" or "different"
//!
//! It takes the shared lock as the tail does, retrying only while the writer's exclusive one is
//! held, and reads from a new handle each time, so nothing it read before can answer.

use std::io::{BufRead, Write};
use std::path::PathBuf;

use mentis_server::front::grants::CLAIM;
use mentis_server::front::held::{BrainFile, Tried};

fn main() {
    let brain = PathBuf::from(std::env::args().nth(1).expect("a Brain"));
    let stdin = std::io::stdin();
    let mut out = std::io::stdout();
    for line in stdin.lock().lines() {
        let boot = line.expect("a line");
        let said = loop {
            let file = BrainFile::open(&brain.join(CLAIM)).expect("the claim opens");
            match file.try_shared() {
                Tried::Taken => {}
                Tried::Busy => continue,
                Tried::Failed => panic!("no clear answer from the lock"),
            }
            let same = file.says(&boot).expect("it reads");
            file.unlock();
            break same;
        };
        writeln!(out, "{}", if said { "same" } else { "different" }).expect("a pipe");
        out.flush().expect("a pipe");
    }
}
