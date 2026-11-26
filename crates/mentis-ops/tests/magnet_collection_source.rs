//! THE COLLECTION-SCOPED FILE SOURCE, over a shared Rust/Python Brain.
//!
//! A `file` source names one object, every object under a prefix, or a whole declared collection.
//! `tools/magnet_collection_source_fixture.py` builds the Brain and then checks every row this
//! produced against Python's own verifier and the real private activation door, so the two halves
//! agree on one row shape.
use mentis_ops::{
    ReadClass, ReadRequest,
    magnet::{
        COLLECTION_ADMISSIONS_MOST, COLLECTION_OBJECTS_MOST, COLLECTION_ROWS_MOST,
        FILE_ROW_BYTES_MOST, MagnetArgs, MagnetDefinition, MagnetMode, MagnetRead,
    },
    window::{Prepared, Window},
};
use mentis_record::{Brain, BrainOpener};
use serde_json::{Value as Json, json};
use std::{
    path::PathBuf,
    process::Command,
    sync::Arc,
    time::{Duration, Instant},
};

const MAGNET: &str = "mag-a1c7e2f09b3d4e68";

fn python() -> String {
    std::env::var("MENTIS_COLLECTION_PYTHON").unwrap_or("python".into())
}

fn objects_of(source: &Json) -> Vec<String> {
    source["results"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| row["value"]["path"].as_str().unwrap().to_owned())
        .collect()
}

#[test]
fn a_whole_collection_a_prefix_and_an_exact_file_read_as_rows_python_verifies() {
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let root = PathBuf::from(env!("CARGO_TARGET_TMPDIR"))
        .join(format!("collection-source-{}", std::process::id()));
    let built = Command::new(python())
        .current_dir(&repo)
        .env("PYTHONPATH", &repo)
        .args(["-m", "tools.magnet_collection_source_fixture"])
        .arg(&root)
        .output()
        .unwrap();
    assert!(
        built.status.success(),
        "{}",
        String::from_utf8_lossy(&built.stderr)
    );
    let plan: Json =
        serde_json::from_slice(&std::fs::read(root.join("collection-cases.json")).unwrap()).unwrap();
    let reader = Brain::open(&root).unwrap();
    let window = Window::new(&root, &root);

    let mut pages = Vec::new();
    for case in plan["cases"].as_array().unwrap() {
        let definition = case["definition"].to_string();
        let request = ReadRequest {
            args: MagnetArgs {
                magnet: MagnetDefinition::parse(MAGNET, &definition).unwrap(),
                mode: MagnetMode::Page {
                    source: None,
                    types: None,
                },
                bundle: Err("a file source needs no post extraction".into()),
                gone: Arc::default(),
            },
            cursor: None,
            limit: None,
            deadline: Instant::now() + Duration::from_secs(20),
        };
        let mut answer = mentis_ops::run(
            &MagnetRead { window: &window },
            &reader,
            ReadClass::Background,
            &request,
        )
        .unwrap();
        let Prepared(got) = answer.rows.pop().unwrap();
        let until = Instant::now() + Duration::from_secs(20);
        let page: Json =
            serde_json::from_str(&got.finish(&window, &|| Instant::now() >= until).dumps())
                .unwrap();
        assert_eq!(
            page["sources"].as_array().unwrap().len(),
            case["definition"]["sources"].as_array().unwrap().len()
        );
        pages.push(page);
    }
    let named = |name: &str| -> &Json {
        let at = plan["cases"]
            .as_array()
            .unwrap()
            .iter()
            .position(|c| c["name"] == name)
            .unwrap();
        &pages[at]
    };

    // THE WHOLE COLLECTION. Every object whose latest observation is present, held and text, and
    // nothing else -- and what it could not read is named, never silently dropped.
    let whole = &named("whole")["sources"][0];
    let mut got = objects_of(whole);
    got.sort();
    assert_eq!(
        got,
        ["docs/one.md", "docs/sub/three.md", "docs/two.md", "notes/four.md"]
    );
    assert_eq!(whole["status"], "partial", "{whole}");
    let why = whole["reason"].as_str().unwrap();
    for absent in ["docs/gone.md", "docs/purged.md", "docs/binary.bin"] {
        assert!(why.contains(absent), "{absent} is not reported in {why:?}");
    }
    assert!(why.contains("purged") && why.contains("not text"), "{why:?}");

    // EVERY ROW CITES ITS OWN ADMISSION, and that citation resolves to the bytes it carries.
    for row in whole["results"].as_array().unwrap() {
        let v = &row["value"];
        let (reference, digest) = (v["ref"].as_str().unwrap(), v["digest"].as_str().unwrap());
        assert_eq!(row["id"], v["ref"]);
        assert_eq!(row["version"], v["ref"]);
        assert_eq!(row["via"], "held-source");
        assert!(row["conversation"].is_null() && row["author"].is_null());
        assert_eq!(row["at"], v["acquired_at"]);
        assert_eq!(
            v["citation"].as_str().unwrap(),
            format!("{reference}@{}[0:{}]", &digest[..12], v["end"])
        );
        assert_eq!(v["text"].as_str().unwrap().len() as u64, v["end"].as_u64().unwrap());
        assert!(v["end"].as_u64().unwrap() <= FILE_ROW_BYTES_MOST as u64);
        assert_eq!(v["shortened"], false);
        assert_eq!(v["offset"], 0);
    }

    // A PREFIX. Only what is under it, the deeper path included; a sibling folder is not.
    let prefix = &named("prefix")["sources"][0];
    let mut got = objects_of(prefix);
    got.sort();
    assert_eq!(got, ["docs/one.md", "docs/sub/three.md", "docs/two.md"]);

    // A GIT COLLECTION AND ONE HELD FILE, which is the Magnet this part is for. A commit object is a
    // row like any other, and the exact-file source beside it still answers for itself.
    let git = named("git-and-held-file");
    let mut got = objects_of(&git["sources"][0]);
    got.sort();
    let sha: Vec<String> = plan["sha"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| format!(".git/commits/{}", s.as_str().unwrap()))
        .collect();
    assert_eq!(
        got,
        [
            sha[0].clone(),
            sha[1].clone(),
            "docs/overview.md".to_owned(),
            "schema/schema.json".to_owned()
        ]
    );
    assert_eq!(git["sources"][0]["status"], "ok", "{}", git["sources"][0]);
    let commits: Vec<&Json> = git["sources"][0]["results"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["value"]["path"].as_str().unwrap().starts_with(".git/commits/"))
        .collect();
    assert_eq!(commits.len(), 2);
    assert!(commits.iter().all(|r| r["value"]["text"]
        .as_str()
        .unwrap()
        .starts_with("commit ")));
    assert_eq!(objects_of(&git["sources"][1]), ["docs/one.md"]);
    assert_eq!(git["sources"][1]["status"], "ok");

    // NO LIST OF CONNECTORS. `col-feed` is declared for `rss-atom`, which this build does not
    // implement yet: the reader reads what the record shows it admitted, so Part W's connectors read
    // the moment they land, with no change here.
    let feed = &named("unavailable-connector")["sources"][0];
    let mut got = objects_of(feed);
    got.sort();
    assert_eq!(got, ["entry/one", "entry/two"]);
    assert_eq!(feed["status"], "ok", "{feed}");

    // THE BOUNDS, each said from its own constant. A source reads at most its hundred objects; a
    // batch holds at most its two hundred rows, shared by every collection-scoped source in it.
    let bounds = named("bounds");
    let many = plan["many"].as_u64().unwrap() as usize;
    assert!(many > COLLECTION_OBJECTS_MOST, "the fixture must exceed it");
    assert_eq!(COLLECTION_ROWS_MOST, 2 * COLLECTION_OBJECTS_MOST);
    let counted: Vec<usize> = bounds["sources"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| s["results"].as_array().unwrap().len())
        .collect();
    assert_eq!(
        counted,
        [COLLECTION_OBJECTS_MOST, COLLECTION_OBJECTS_MOST, 0]
    );
    assert_eq!(counted.iter().sum::<usize>(), COLLECTION_ROWS_MOST);
    assert!(
        bounds["sources"][0]["reason"]
            .as_str()
            .unwrap()
            .contains(&format!("{COLLECTION_OBJECTS_MOST} objects one source reads")),
        "{}",
        bounds["sources"][0]
    );
    assert_eq!(bounds["sources"][2]["status"], "unavailable");
    assert!(
        bounds["sources"][2]["reason"]
            .as_str()
            .unwrap()
            .contains(&format!("{COLLECTION_ROWS_MOST} rows one batch holds")),
        "{}",
        bounds["sources"][2]
    );
    assert!(COLLECTION_ADMISSIONS_MOST > COLLECTION_OBJECTS_MOST);

    // A COLLECTION NOBODY DECLARED IS READ BY NOTHING, whatever a definition says.
    let undeclared = &named("undeclared")["sources"][0];
    assert_eq!(undeclared["status"], "unavailable");
    assert_eq!(undeclared["results"], json!([]));
    assert!(
        undeclared["reason"]
            .as_str()
            .unwrap()
            .contains("no collection of that id is declared here"),
        "{undeclared}"
    );

    std::fs::write(
        root.join("captured-collection-pages.json"),
        serde_json::to_vec(&pages).unwrap(),
    )
    .unwrap();
    let checked = Command::new(python())
        .current_dir(&repo)
        .env("PYTHONPATH", &repo)
        .args(["-m", "tools.magnet_collection_source_fixture", "--check"])
        .arg(&root)
        .output()
        .unwrap();
    assert!(
        checked.status.success(),
        "{}",
        String::from_utf8_lossy(&checked.stderr)
    );
}

/// LIVE: a real upstream repository, acquired by https address into a Brain made outside the
/// suite, read whole as one Magnet source beside one exact held file. `#[ignore]` because it needs
/// that Brain: build it with `tools/magnet_live_git_brain.py`, then
/// `MENTIS_LIVE_GIT_BRAIN=<brain> cargo test -p mentis-ops --test magnet_collection_source -- --ignored`.
/// Never part of the focused run: nothing in the suite reaches the network.
#[test]
#[ignore = "needs MENTIS_LIVE_GIT_BRAIN, built from a real upstream repository"]
fn a_real_upstream_git_collection_and_one_held_file_collect_one_batch() {
    let root = PathBuf::from(std::env::var("MENTIS_LIVE_GIT_BRAIN").expect("a live Brain"));
    let definition = std::fs::read_to_string(root.join("live-definition.json")).unwrap();
    let reader = Brain::open(&root).unwrap();
    let window = Window::new(&root, &root);
    let request = ReadRequest {
        args: MagnetArgs {
            magnet: MagnetDefinition::parse(MAGNET, &definition).unwrap(),
            mode: MagnetMode::Page {
                source: None,
                types: None,
            },
            bundle: Err("a file source needs no post extraction".into()),
            gone: Arc::default(),
        },
        cursor: None,
        limit: None,
        deadline: Instant::now() + Duration::from_secs(30),
    };
    let mut answer = mentis_ops::run(
        &MagnetRead { window: &window },
        &reader,
        ReadClass::Background,
        &request,
    )
    .unwrap();
    let Prepared(got) = answer.rows.pop().unwrap();
    let until = Instant::now() + Duration::from_secs(60);
    let page: Json =
        serde_json::from_str(&got.finish(&window, &|| Instant::now() >= until).dumps()).unwrap();
    // THE COMMITS, by their prefix: real upstream commit objects, each one row with its own
    // Admission and a citation that names it.
    let commits = &page["sources"][0];
    let rows = commits["results"].as_array().unwrap();
    assert!(rows.len() >= 5, "real commit rows: {}", commits["reason"]);
    for row in rows {
        let v = &row["value"];
        assert!(
            v["path"].as_str().unwrap().starts_with(".git/commits/"),
            "{v}"
        );
        assert_eq!(
            v["citation"].as_str().unwrap(),
            format!(
                "{}@{}[0:{}]",
                v["ref"].as_str().unwrap(),
                &v["digest"].as_str().unwrap()[..12],
                v["end"]
            )
        );
        println!(
            "commit {} -> {}",
            v["citation"].as_str().unwrap(),
            v["text"]
                .as_str()
                .unwrap()
                .lines()
                .find(|l| !l.is_empty() && !l.starts_with("commit "))
                .unwrap_or("")
        );
    }
    // THE COLLECTION WHOLE, bounded and saying so rather than claiming to hold a repository.
    let whole = &page["sources"][1];
    assert_eq!(whole["status"], "partial");
    let why = whole["reason"].as_str().unwrap();
    assert!(why.contains("objects one source reads"), "{why}");
    println!("whole collection: {why}");
    // THE ONE EXACT HELD FILE, beside them, unchanged in behaviour.
    let held = &page["sources"][2];
    assert_eq!(held["results"].as_array().unwrap().len(), 1, "{held}");
    assert!(
        held["results"][0]["value"]["text"]
            .as_str()
            .unwrap()
            .contains("Mentis"),
        "the held AGENTS.md"
    );
    println!("held file: {}", held["results"][0]["value"]["citation"]);
}

#[test]
fn a_summary_says_a_file_source_is_captured_in_a_page_not_that_a_collection_cannot_be_read() {
    let definition = json!({
        "id": MAGNET, "schema_version": 1, "selection": {},
        "sources": [{"kind": "file", "collection": "col-anything"}],
    });
    let parsed = MagnetDefinition::parse(MAGNET, &definition.to_string()).unwrap();
    let why = parsed.sources[0].unavailable.as_deref().unwrap();
    assert!(why.contains("page mode"), "{why}");
    assert!(
        !why.contains("collection-wide"),
        "the lifted refusal must not survive: {why}"
    );
}
