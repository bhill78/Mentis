//! The verifier against Python's `Store.verify_chain` over the Brain Python's own permanent
//! deletion produced (`$MENTIS_R1_FIXTURES/erasure/brain`: one deleted Conversation, 20 rows
//! erased), and over copies of it altered under the chain. Every field Python reports but its
//! note must be the same.

mod support;

use std::path::{Path, PathBuf};

use mentis_record::{Brain, BrainOpener, ChainReport, ChainVerifier, Chains, ErasureBroken};
use serde_json::{Value, json};
use support::{fixtures, python, repo_root, scratch_dir};

fn fixture() -> PathBuf {
    let brain = fixtures().join("erasure").join("brain");
    assert!(
        brain.join("corpus.db").is_file(),
        "no erasure fixture at {}",
        brain.display()
    );
    brain
}

/// This clone's `Store.verify_chain` over a bare read-only connection, as `spine/backup.py`'s
/// `_chain` runs it (`tools/r1/copy_brain.py` runs the same at R1's pinned commit, which predates
/// erasure).
const PYTHONS_WALK: &str = r#"
import json, sqlite3, sys
from mentis.spine import backup
conn = sqlite3.connect(f"file:{sys.argv[2]}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
got = backup._chain(conn)
conn.close()
got.pop("note", None)
print(json.dumps(got, sort_keys=True))
"#;

/// This clone's `erasure.ledger_check` over the copy and the ledger beside it: what it lists.
const PYTHONS_LEDGER: &str = r#"
import json, sqlite3, sys
from mentis.spine import erasure
conn = sqlite3.connect(f"file:{sys.argv[2]}/corpus.db?mode=ro", uri=True)
print(json.dumps(len(erasure.ledger_check(conn, sys.argv[2]))))
conn.close()
"#;

fn python_ledger_missing(root: &Path) -> u64 {
    let done = python(&repo_root())
        .arg("-c")
        .arg(PYTHONS_LEDGER)
        .arg("-")
        .arg(root.to_str().unwrap().replace('\\', "/"))
        .output()
        .expect("Python starts");
    assert!(
        done.status.success(),
        "Python's ledger check: {}",
        String::from_utf8_lossy(&done.stderr)
    );
    serde_json::from_slice(&done.stdout).unwrap()
}

fn python_walk(db: &Path) -> Value {
    let done = python(&repo_root())
        .arg("-c")
        .arg(PYTHONS_WALK)
        .arg("-")
        .arg(db.to_str().unwrap().replace('\\', "/"))
        .output()
        .expect("Python starts");
    assert!(
        done.status.success(),
        "Python's walk: {}",
        String::from_utf8_lossy(&done.stderr)
    );
    serde_json::from_slice(&done.stdout).unwrap()
}

/// Rust's report in Python's shape (`mentis-server --verify-record` says the same).
fn as_python(report: &ChainReport) -> Value {
    let mut streams = serde_json::Map::new();
    for t in &report.tables {
        streams.insert(
            t.table.to_string(),
            json!({
                "rows": t.rows,
                "chained": t.chained,
                "before_the_chain": t.before_the_chain,
                "head": t.head,
                "broken_at": t.broken_at.as_ref().map(|b| json!({"seq": b.seq, "id": b.id, "why": b.why})),
                "erased": t.erased,
            }),
        );
    }
    let broken = report.erasures.broken.as_ref().map(|b| match b {
        ErasureBroken::Act { deletion, why } => json!({"deletion": deletion, "why": why}),
        ErasureBroken::Row { table, id, why } => json!({"table": table, "id": id, "why": why}),
    });
    json!({
        "intact": report.intact(),
        "streams": streams,
        "erasures": {
            "acts": report.erasures.acts,
            "rows": report.erasures.rows,
            "pending": report.erasures.pending,
            "broken": broken,
        },
        "chained_from_first_row": report.chained_from_first_row,
    })
}

fn rust_walk(root: &Path) -> Value {
    let reader = Brain::open(root).unwrap();
    as_python(&Chains.verify_report(&reader).unwrap())
}

/// A copy of the fixture through the backup API, the triggers dropped, then `change` applied.
const ALTER: &str = r#"
import json, sqlite3, sys
source, dest, change = sys.argv[1:4]
src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
dst = sqlite3.connect(dest)
src.backup(dst)
src.close()
for (name,) in dst.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall():
    dst.execute(f'DROP TRIGGER "{name}"')
ids = json.loads(sys.argv[4])
act = ids["deletion_act"]
post = ids["posts"][0]
if change == "none":
    pass
elif change == "structural":
    dst.execute("UPDATE entry SET attributed_to = 'mallory' WHERE id = ?", (post,))
elif change == "content":
    dst.execute("UPDATE entry SET body = '{\"parts\": []}' WHERE id = ?", (post,))
elif change == "marker-other-act":
    dst.execute("UPDATE entry SET body = '{\"erased\":\"opr-000000000000\"}' WHERE id = ?", (post,))
elif change == "marker-spaced":
    dst.execute("UPDATE entry SET body = ? WHERE id = ?", (json.dumps({"erased": act}), post))
elif change == "because":
    dst.execute("UPDATE operational SET because = 'x' WHERE id IN "
                "(SELECT row_id FROM erasure WHERE tbl = 'operational' LIMIT 1)")
elif change == "residual":
    dst.execute("UPDATE erasure SET residual = ? WHERE row_id = ?", ("0" * 64, post))
elif change == "row-hash":
    dst.execute("UPDATE erasure SET row_hash = ? WHERE row_id = ?", ("a" * 64, ids["delivery"]))
elif change == "erasure-removed":
    dst.execute("DELETE FROM erasure WHERE row_id = ?", (post,))
elif change == "all-erasure-removed":
    dst.execute("DELETE FROM erasure")
elif change == "act-removed":
    dst.execute("DELETE FROM operational WHERE id = ?", (act,))
elif change == "act-digest":
    d = json.loads(dst.execute("SELECT detail FROM operational WHERE id = ?", (act,)).fetchone()[0])
    d["erasure"]["digest"] = "0" * 64
    dst.execute("UPDATE operational SET detail = ? WHERE id = ?", (json.dumps(d), act))
elif change == "ghost":
    dst.execute("INSERT INTO erasure (deletion, tbl, row_id, row_hash, residual) "
                "VALUES (?, 'entry', 'ent-000000ghost0', '', '')", (act,))
elif change == "attest-intact":
    row = dst.execute("SELECT hash FROM entry WHERE id = ?", (ids["lesson"],)).fetchone()
    dst.execute("INSERT INTO erasure (deletion, tbl, row_id, row_hash, residual) "
                "VALUES (?, 'entry', ?, ?, 'x')", (act, ids["lesson"], row[0]))
elif change == "second-act-without-rows":
    dst.execute("INSERT INTO operational (id, at, actor, act, conversation, about, detail, prev_hash, hash) "
                "VALUES ('opr-0000000000aa', 1.0, 'o', 'conversation-deleted', 'c', '[]', "
                "'{\"erasure\": {\"rows\": 2, \"digest\": \"x\"}}', NULL, NULL)")
else:
    raise SystemExit(change)
dst.commit()
dst.close()
"#;

const CHANGES: &[&str] = &[
    "none",
    "structural",
    "content",
    "marker-other-act",
    "marker-spaced",
    "because",
    "residual",
    "row-hash",
    "erasure-removed",
    "all-erasure-removed",
    "act-removed",
    "act-digest",
    "ghost",
    "attest-intact",
    "second-act-without-rows",
];

#[test]
fn agrees_with_python_on_the_fixture_as_python_left_it() {
    let brain = fixture();
    let python = python_walk(&brain.join("corpus.db"));
    assert_eq!(python["intact"], true, "{python}");
    assert_eq!(python["erasures"]["rows"], 20);
    // Read through a copy: the fixture itself is never opened by the Rust reader's lock.
    let root = scratch_dir("erasure-fixture");
    std::fs::copy(brain.join("corpus.db"), root.join("corpus.db")).unwrap();
    assert_eq!(rust_walk(&root), python);
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn agrees_with_python_on_every_alteration() {
    let shapes: Value = serde_json::from_slice(
        &std::fs::read(fixtures().join("erasure").join("shapes.json")).unwrap(),
    )
    .unwrap();
    let ids = shapes["ids"].to_string();
    let source = fixture().join("corpus.db");
    let mut intact = 0;
    let mut refused = 0;
    for change in CHANGES {
        let root = scratch_dir(&format!("erasure-{change}"));
        let db = root.join("corpus.db");
        let done = python(&repo_root())
            .arg("-c")
            .arg(ALTER)
            .arg(source.to_str().unwrap().replace('\\', "/"))
            .arg(&db)
            .arg(change)
            .arg(&ids)
            .output()
            .expect("Python starts");
        assert!(
            done.status.success(),
            "{change}: {}",
            String::from_utf8_lossy(&done.stderr)
        );
        // The fixture's deletion ledger beside the copy, as beside the Brain it was written for.
        std::fs::copy(
            fixtures().join("erasure").join("brain.erasures.jsonl"),
            mentis_record::ledger_path(&root),
        )
        .unwrap();
        let python = python_walk(&db);
        let missing = python_ledger_missing(&root);
        let opened = Brain::open(&root);
        // The front refuses exactly the Brains Python's open check would not serve.
        assert_eq!(
            matches!(
                opened,
                Err(mentis_record::OpenRefused::DeletionsNotHeld { .. })
            ),
            missing > 0,
            "{change}: {:?}",
            opened.as_ref().err()
        );
        if missing > 0 {
            refused += 1;
        }
        drop(opened);
        let _ = std::fs::remove_file(mentis_record::ledger_path(&root));
        let rust = rust_walk(&root);
        assert_eq!(rust, python, "{change}");
        intact += usize::from(python["intact"] == true);
        let _ = std::fs::remove_dir_all(&root);
    }
    // Only the unaltered copy verifies: every alteration is seen, by both.
    assert_eq!(intact, 1);
    // Some alterations take the deletion out of the record, and both refuse those.
    assert!(refused >= 3, "{refused}");
}
