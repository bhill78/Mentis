//! `BrainOpener::open`'s refusals, in order, against Python's own locks (`spine/brainlock.py`).

mod support;

use std::path::Path;

use mentis_record::{
    Brain, BrainOpener, OPEN_LOCK, OpenRefused, RESTORING, ReadClass, RecordReader,
};
use support::{Holder, run_python, scratch_brain, scratch_dir, writer};

const SERVE_LOCK: &str = ".mentis.serve.lock";
const SERVE_INFO: &str = ".mentis.serve.json";

fn refusal(root: &Path) -> OpenRefused {
    Brain::open(root).err().expect("the open is refused")
}

fn is_open_to_python(root: &Path) -> bool {
    let script = "import sys\nfrom mentis.spine import brainlock\n\
                  print(brainlock.is_open(sys.argv[1]))";
    run_python(script, &[root.to_str().unwrap()]).trim() == "True"
}

#[test]
fn refuses_a_missing_brain() {
    let root = scratch_dir("missing");
    assert!(matches!(refusal(&root), OpenRefused::Missing { .. }));
    assert_eq!(
        std::fs::read_dir(&root).unwrap().count(),
        0,
        "refusing a missing Brain creates nothing"
    );
}

#[test]
fn refuses_while_restoring() {
    let root = scratch_brain("restoring");
    std::fs::write(root.join(RESTORING), "{}").unwrap();
    assert!(matches!(refusal(&root), OpenRefused::Restoring { .. }));
}

#[test]
fn refuses_while_held_exclusive() {
    let root = scratch_brain("exclusive");
    let held = Holder::start(&root, "brainlock.exclusive(root, 'test')");
    assert!(matches!(refusal(&root), OpenRefused::Exclusive { .. }));
    drop(held);
    assert!(
        Brain::open(&root).is_ok(),
        "the refusal lasts as the lock does"
    );
}

#[test]
fn refuses_a_ledger_this_build_does_not_name() {
    let added = scratch_brain("ledger-added");
    writer(&added)
        .execute_batch("INSERT INTO schema_migration VALUES (2, '0002-later', 'abc');")
        .unwrap();
    let changed = scratch_brain("ledger-changed");
    writer(&changed)
        .execute_batch("UPDATE schema_migration SET checksum = 'abc' WHERE seq = 1;")
        .unwrap();
    let emptied = scratch_brain("ledger-emptied");
    writer(&emptied)
        .execute_batch("DELETE FROM schema_migration;")
        .unwrap();
    let dropped = scratch_brain("ledger-dropped");
    writer(&dropped)
        .execute_batch("DROP TABLE schema_migration;")
        .unwrap();
    for root in [added, changed, emptied, dropped] {
        assert!(
            matches!(refusal(&root), OpenRefused::UnsupportedSchema { .. }),
            "{}",
            root.display()
        );
    }
}

#[test]
fn takes_the_first_refusal_in_order() {
    // Nothing else counts where there is no Brain.
    let root = scratch_dir("order-missing");
    std::fs::write(root.join(RESTORING), "{}").unwrap();
    assert!(matches!(refusal(&root), OpenRefused::Missing { .. }));

    // Restoring comes before the lock, which a restore in progress holds.
    let root = scratch_brain("order-restoring");
    let held = Holder::start(
        &root,
        "brainlock.exclusive(root, 'test', restoring_ok=True)",
    );
    std::fs::write(root.join(RESTORING), "{}").unwrap();
    assert!(matches!(refusal(&root), OpenRefused::Restoring { .. }));
    drop(held);

    // The lock comes before the ledger, which isn't read without it.
    let root = scratch_brain("order-exclusive");
    writer(&root)
        .execute_batch("INSERT INTO schema_migration VALUES (2, '0002-later', 'abc');")
        .unwrap();
    let held = Holder::start(&root, "brainlock.exclusive(root, 'test')");
    assert!(matches!(refusal(&root), OpenRefused::Exclusive { .. }));
    drop(held);
    assert!(matches!(
        refusal(&root),
        OpenRefused::UnsupportedSchema { .. }
    ));
}

#[test]
fn holds_the_lock_shared_until_dropped() {
    let root = scratch_brain("held");
    assert!(!is_open_to_python(&root));
    let reader = Brain::open(&root).unwrap();
    assert_eq!(reader.corpus_id(), "corpus-under-test");
    assert!(root.join(OPEN_LOCK).is_file());
    assert!(is_open_to_python(&root), "Python's probe sees the hold");
    // Shared: a guarded opener can stand beside it, and a second reader too.
    drop(Holder::start(&root, "brainlock.shared(root)"));
    let second = Brain::open(&root).unwrap();
    drop(second);
    assert!(is_open_to_python(&root), "the first reader still holds it");
    let scope = reader.read_scope(ReadClass::Foreground).unwrap();
    drop(scope);
    drop(reader);
    assert!(!is_open_to_python(&root), "dropped, it is gone at once");
}

#[test]
fn never_touches_the_serve_lock() {
    let root = scratch_brain("serve");
    let reader = Brain::open(&root).unwrap();
    drop(reader.read_scope(ReadClass::Foreground).unwrap());
    assert!(!root.join(SERVE_LOCK).exists());
    assert!(!root.join(SERVE_INFO).exists());
    drop(reader);

    // Python serving this Brain is nothing to the opener, and what it wrote stays as it wrote it.
    let held = Holder::start(&root, "brainlock.serve(root, port=1)");
    let info = std::fs::read(root.join(SERVE_INFO)).unwrap();
    let reader = Brain::open(&root).unwrap();
    drop(reader.read_scope(ReadClass::Foreground).unwrap());
    drop(reader);
    assert_eq!(std::fs::read(root.join(SERVE_INFO)).unwrap(), info);
    drop(held);
}
