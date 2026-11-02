//! `corpus.db*` is opened only through SQLite (`contracts/record.md`): closing any other handle on
//! it drops SQLite's POSIX locks. This reads the workspace's Rust source, and its manifests.

mod support;

use std::path::{Path, PathBuf};

use support::repo_root;

/// Whatever opens a file, or reads or writes one by path.
const OPENS_A_FILE: &[&str] = &[
    "File::open",
    "File::create",
    "File::options",
    "OpenOptions",
    "fs::read",
    "fs::write",
    "fs::copy",
    "fs::rename",
    "fs::remove_file",
    "fs::hard_link",
    "fs::OpenOptions",
    "CreateFile",
    "libc::open",
];

const NAMES_THE_DATABASE: &[&str] = &["corpus.db", "CORPUS_DB"];

/// Every way to open a connection, so one that isn't `open.rs`'s can't arrive unnoticed.
const OPENS_A_CONNECTION: &[&str] = &[
    "Connection::open",
    "open_with_flags",
    "open_in_memory",
    "immutable",
    "sqlite3_open",
];

fn rust_files(under: &Path, out: &mut Vec<PathBuf>) {
    for found in std::fs::read_dir(under).unwrap() {
        let path = found.unwrap().path();
        if path.is_dir() {
            rust_files(&path, out);
        } else if path.extension().is_some_and(|e| e == "rs") {
            out.push(path);
        }
    }
}

/// The code of a source file, without its comments.
fn code_lines(text: &str) -> Vec<&str> {
    text.lines()
        .map(|line| line.split("//").next().unwrap_or_default())
        .collect()
}

/// A file naming the database may not open any file. So the check needs no path analysis, and a
/// lock file's open lives apart from what names the database.
fn wrong_opens(text: &str) -> Vec<String> {
    let lines = code_lines(text);
    if !lines
        .iter()
        .any(|line| NAMES_THE_DATABASE.iter().any(|name| line.contains(name)))
    {
        return Vec::new();
    }
    lines
        .iter()
        .filter(|line| OPENS_A_FILE.iter().any(|open| line.contains(open)))
        .map(|line| line.trim().to_string())
        .collect()
}

#[test]
fn corpus_db_is_opened_only_through_sqlite() {
    // The check can see what it is for.
    let planted = "let db = root.join(CORPUS_DB);\nlet raw = File::open(&db)?;\n";
    assert_eq!(wrong_opens(planted), ["let raw = File::open(&db)?;"]);
    let harmless = "// corpus.db, in a comment\nlet raw = File::open(&lock)?;\n";
    assert!(wrong_opens(harmless).is_empty());

    let crates = repo_root().join("crates");
    let mut files = Vec::new();
    rust_files(&crates, &mut files);
    assert!(files.len() > 5, "the workspace's source is where it was");
    let this_check = Path::new(file!()).file_name().unwrap();
    let mut wrong = Vec::new();
    for file in &files {
        if file.file_name() == Some(this_check) {
            continue;
        }
        let text = std::fs::read_to_string(file).unwrap();
        for line in wrong_opens(&text) {
            wrong.push(format!("{}: {line}", file.display()));
        }
    }
    assert!(
        wrong.is_empty(),
        "opened other than through SQLite: {wrong:#?}"
    );

    // In the crate's source, one place opens a connection, read-only with the contract's flags.
    let src = crates.join("mentis-record").join("src");
    let mut sources = Vec::new();
    rust_files(&src, &mut sources);
    let mut opening = Vec::new();
    for file in &sources {
        let text = std::fs::read_to_string(file).unwrap();
        for line in code_lines(&text) {
            if OPENS_A_CONNECTION.iter().any(|open| line.contains(open)) {
                let name = file.file_name().unwrap().to_string_lossy().into_owned();
                opening.push((name, line.trim().to_string()));
            }
        }
    }
    assert_eq!(
        opening,
        [(
            "open.rs".to_string(),
            "let conn = Connection::open_with_flags(db, OPEN_FLAGS)?;".to_string()
        )]
    );

    // Only this crate can reach a connection at all.
    for found in std::fs::read_dir(&crates).unwrap() {
        let member = found.unwrap().path();
        let manifest = std::fs::read_to_string(member.join("Cargo.toml")).unwrap();
        let is_this_crate = member.file_name().is_some_and(|n| n == "mentis-record");
        assert!(
            is_this_crate || !manifest.contains("rusqlite"),
            "{} depends on rusqlite",
            member.display()
        );
    }
}
