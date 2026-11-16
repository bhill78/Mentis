//! The verifier against Python's own walk, over the whole of a fresh BRAIN-COPY and four altered
//! copies of it: `R1-acceptance.md`, section G. Each altered copy changes all three tables.

mod support;

use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::sync::atomic::{AtomicUsize, Ordering};

use mentis_record::{Brain, BrainOpener, CHAINED_TABLES, ChainVerifier, Chains, TableChain};
use serde_json::Value;
use support::{python, repo_root, scratch_dir};

/// This target's tests, so the last to finish can remove the copy they share.
const TESTS: usize = 5;
static FINISHED: AtomicUsize = AtomicUsize::new(0);
static COPY: OnceLock<PathBuf> = OnceLock::new();

/// One fresh copy for this target, checked against its manifest. Copying 3.3 GB per test would
/// only take longer: each altered copy is a backup of this one, and this one is only ever read.
fn brain_copy() -> &'static Path {
    COPY.get_or_init(|| {
        let brain = scratch_dir("brain-copy").join("brain");
        let manifest = repo_root()
            .join("docs")
            .join("rust")
            .join("evidence")
            .join("brain-copy-manifest.json");
        let done = python(&repo_root())
            .arg(repo_root().join("tools").join("r1").join("copy_brain.py"))
            .arg("fresh")
            .arg(&brain)
            .arg("--manifest")
            .arg(manifest)
            .output()
            .expect("Python starts");
        assert!(
            done.status.success(),
            "BRAIN-COPY: {}",
            String::from_utf8_lossy(&done.stderr)
        );
        // At this clone's schema, which is the one this build's ledger names.
        let migrated = python(&repo_root())
            .args(["-m", "mentis.migrate"])
            .arg(&brain)
            .args(["--apply", "--allow-breaking"])
            .output()
            .expect("Python starts");
        assert!(
            migrated.status.success(),
            "migrating BRAIN-COPY: {}",
            String::from_utf8_lossy(&migrated.stderr)
        );
        brain
    })
}

struct Finish;

impl Drop for Finish {
    fn drop(&mut self) {
        if FINISHED.fetch_add(1, Ordering::SeqCst) + 1 == TESTS
            && let Some(brain) = COPY.get()
        {
            let _ = std::fs::remove_dir_all(brain.parent().unwrap());
        }
    }
}

/// Python's verifier over a bare connection, as `tools/r1/copy_brain.py` runs it, at PY_COMMIT.
const PYTHONS_WALK: &str = r#"
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import copy_brain
print(json.dumps(copy_brain._chain(pathlib.Path(sys.argv[2]))))
"#;

fn python_walk(db: &Path) -> Value {
    let tools = repo_root().join("tools").join("r1");
    let done = python(&repo_root())
        .arg("-c")
        .arg(PYTHONS_WALK)
        .arg(tools)
        .arg(db)
        .output()
        .expect("Python starts");
    assert!(
        done.status.success(),
        "Python's walk: {}",
        String::from_utf8_lossy(&done.stderr)
    );
    serde_json::from_slice(&done.stdout).unwrap()
}

fn rust_walk(root: &Path) -> Vec<TableChain> {
    let reader = Brain::open(root).unwrap();
    Chains.verify_chains(&reader).unwrap()
}

/// The same rows, head and result per table.
fn assert_agree(rust: &[TableChain], python: &Value) {
    assert_eq!(rust.len(), CHAINED_TABLES.len());
    for chain in rust {
        let stream = &python["streams"][chain.table];
        assert_eq!(
            chain.rows,
            stream["rows"].as_u64().unwrap(),
            "{}",
            chain.table
        );
        assert_eq!(
            chain.head.as_deref(),
            stream["head"].as_str(),
            "{}",
            chain.table
        );
        assert_eq!(
            chain.broke_at_seq,
            stream["broken_at"]["seq"].as_u64(),
            "{}",
            chain.table
        );
    }
}

/// Makes the altered copy from the fresh one, through the backup API, with the append-only
/// triggers dropped from it. Prints the `seq` the break must be reported at, per table.
const ALTER: &str = r#"
import json, sqlite3, sys
source, dest, kind = sys.argv[1:4]
src = sqlite3.connect(f"file:{source}?mode=ro&immutable=1", uri=True)
dst = sqlite3.connect(dest)
src.backup(dst)
src.close()
for (name,) in dst.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall():
    dst.execute(f'DROP TRIGGER "{name}"')
expected = {}
for t in ("entry", "operational", "delivery"):
    seqs = [r[0] for r in dst.execute(f"SELECT seq FROM {t} ORDER BY seq")]
    mid = seqs[len(seqs) // 2]
    after = seqs[len(seqs) // 2 + 1]
    if kind == "field":
        dst.execute(f"UPDATE {t} SET id = id || 'x' WHERE seq = ?", (mid,))
        expected[t] = mid
    elif kind == "removed":
        dst.execute(f"DELETE FROM {t} WHERE seq = ?", (mid,))
        expected[t] = after
    elif kind == "reordered":
        dst.execute(f"UPDATE {t} SET seq = -1 WHERE seq = ?", (mid,))
        dst.execute(f"UPDATE {t} SET seq = ? WHERE seq = ?", (mid, after))
        dst.execute(f"UPDATE {t} SET seq = ? WHERE seq = -1", (after,))
        expected[t] = mid
    elif kind == "hash":
        dst.execute(f"UPDATE {t} SET hash = ? WHERE seq = ?", ("0" * 64, mid))
        expected[t] = mid
    else:
        raise SystemExit(kind)
dst.commit()
dst.close()
print(json.dumps(expected))
"#;

fn altered_copy_is_reported_alike(kind: &str) {
    let _finish = Finish;
    let source = brain_copy().join("corpus.db");
    let root = scratch_dir(&format!("altered-{kind}"));
    let db = root.join("corpus.db");
    let done = python(&repo_root())
        .arg("-c")
        .arg(ALTER)
        .arg(source.to_str().unwrap().replace('\\', "/"))
        .arg(&db)
        .arg(kind)
        .output()
        .expect("Python starts");
    assert!(
        done.status.success(),
        "altering: {}",
        String::from_utf8_lossy(&done.stderr)
    );
    let expected: Value = serde_json::from_slice(&done.stdout).unwrap();
    let python = python_walk(&db);
    assert_eq!(python["intact"], false, "Python sees it");
    let rust = rust_walk(&root);
    assert_agree(&rust, &python);
    for chain in &rust {
        assert_eq!(
            chain.broke_at_seq,
            expected[chain.table].as_u64(),
            "{kind} in {}",
            chain.table
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn agrees_across_the_whole_copy() {
    let _finish = Finish;
    let brain = brain_copy();
    let python = python_walk(&brain.join("corpus.db"));
    assert_eq!(python["intact"], true);
    let rust = rust_walk(brain);
    assert_agree(&rust, &python);
    for chain in &rust {
        assert_eq!(chain.broke_at_seq, None, "{}", chain.table);
        assert!(chain.rows > 0, "{}", chain.table);
    }
}

#[test]
fn a_changed_chained_field_is_reported_at_the_same_seq() {
    altered_copy_is_reported_alike("field");
}

#[test]
fn a_removed_row_is_reported_at_the_same_seq() {
    altered_copy_is_reported_alike("removed");
}

#[test]
fn a_reordering_is_reported_at_the_same_seq() {
    altered_copy_is_reported_alike("reordered");
}

#[test]
fn a_changed_stored_hash_is_reported_at_the_same_seq() {
    altered_copy_is_reported_alike("hash");
}
