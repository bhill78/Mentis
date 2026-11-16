//! A changed BRAIN-SEED, and Python's answers on it. `crates/mentis-ops/tests` uses this too.
#![allow(dead_code)]

use std::path::{Path, PathBuf};
use std::process::Command;

/// R1's fixtures. These tests fail without them: nothing here skips.
pub fn fixtures() -> PathBuf {
    PathBuf::from(
        std::env::var("MENTIS_R1_FIXTURES").expect("MENTIS_R1_FIXTURES names R1's fixtures"),
    )
}

pub fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

/// The test environment's Python, with this clone's `mentis` importable.
pub fn python() -> Command {
    let exe = fixtures().join("venv").join("Scripts").join("python.exe");
    assert!(exe.is_file(), "no test environment at {}", exe.display());
    let mut command = Command::new(exe);
    command
        .current_dir(repo_root())
        .env("PYTHONPATH", repo_root())
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONIOENCODING", "utf-8");
    command
}

fn run(command: &mut Command) -> String {
    let done = command.output().expect("Python starts");
    assert!(
        done.status.success(),
        "Python failed: {}",
        String::from_utf8_lossy(&done.stderr)
    );
    String::from_utf8(done.stdout).expect("Python's output is UTF-8")
}

/// This side's script: its path, from either crate's tests.
pub fn side(arg: &str, brain: &Path) -> String {
    let script = repo_root()
        .join("crates")
        .join("mentis-rules")
        .join("tests")
        .join("support")
        .join("python_side.py");
    run(python().arg(script).arg(arg).arg(brain))
}

/// BRAIN-SEED at `dest`, as `seed_brain.py` builds it, and its identity checked by that script;
/// then brought to this clone's schema by this clone's `mentis.migrate` (0002-erasure raises
/// `min_reader`, and this build's ledger names it).
pub fn seed(dest: &Path) {
    let script = repo_root().join("tools").join("r1").join("seed_brain.py");
    let _ = std::fs::remove_dir_all(dest);
    std::fs::create_dir_all(dest.parent().unwrap()).unwrap();
    run(python().arg(script).arg(dest));
    run(python()
        .args(["-m", "mentis.migrate"])
        .arg(dest)
        .args(["--apply", "--allow-breaking"]));
}

/// A new scratch directory holding a BRAIN-SEED with the changes written.
pub fn changed_seed(target_tmp: &Path, name: &str) -> PathBuf {
    let dest = target_tmp
        .join(format!("{name}-{}", std::process::id()))
        .join("brain");
    seed(&dest);
    side("change", &dest);
    dest
}
