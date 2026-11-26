//! The same observation/damage/byte cases Python's source reader consumes.
use mentis_ops::{
    ReadClass, ReadRequest,
    magnet::{MagnetArgs, MagnetDefinition, MagnetMode, MagnetRead},
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

#[test]
fn shared_python_reading_cases_through_the_background_m1_composer() {
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let root = PathBuf::from(env!("CARGO_TARGET_TMPDIR"))
        .join(format!("held-files-{}", std::process::id()));
    let result = Command::new(std::env::var("MENTIS_COLLECTION_PYTHON").unwrap_or("python".into()))
        .current_dir(&repo)
        .env("PYTHONPATH", &repo)
        .args(["-m", "tools.magnet_held_file_fixture"])
        .arg(&root)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let cases: Vec<Json> =
        serde_json::from_slice(&std::fs::read(root.join("held-cases.json")).unwrap()).unwrap();
    let reader = Brain::open(&root).unwrap();
    let window = Window::new(&root, &root);
    let mut pages = Vec::new();
    for case in cases {
        let definition = json!({"id":"mag-held", "sources":[{"kind":"file", "collection":"col-held-conformance", "path":case["path"]}], "selection":{}});
        let request = ReadRequest {
            args: MagnetArgs {
                magnet: MagnetDefinition::parse("mag-held", &definition.to_string()).unwrap(),
                mode: MagnetMode::Page {
                    source: None,
                    types: None,
                },
                bundle: Err("no extraction".into()),
                gone: Arc::default(),
            },
            cursor: None,
            limit: None,
            deadline: Instant::now() + Duration::from_secs(2),
        };
        let mut answer = mentis_ops::run(
            &MagnetRead { window: &window },
            &reader,
            ReadClass::Background,
            &request,
        )
        .unwrap();
        let Prepared(plan) = answer.rows.pop().unwrap();
        let until = Instant::now() + Duration::from_secs(2);
        let page: Json =
            serde_json::from_str(&plan.finish(&window, &|| Instant::now() >= until).dumps())
                .unwrap();
        let source = &page["sources"][0];
        if case["available"] == true {
            let row = &source["results"][0];
            let v = &row["value"];
            assert_eq!(row["id"], case["ref"], "{case}");
            assert_eq!(row["version"], case["ref"]);
            assert!(row["conversation"].is_null() && row["author"].is_null());
            assert_eq!(row["at"], v["acquired_at"]);
            assert_eq!(v["digest"], case["digest"]);
            let size = case["size"].as_u64().unwrap();
            let end = case.get("end").and_then(Json::as_u64).unwrap_or(size);
            assert_eq!(v["end"], end);
            assert_eq!(v["text"].as_str().unwrap().len() as u64, end);
            assert_eq!(v["size"], size);
            assert_eq!(v["omitted_bytes"], size - end);
            assert_eq!(v["shortened"], end < size);
            assert_eq!(
                v["next_offset"],
                if end < size { json!(end) } else { Json::Null }
            );
            assert_eq!(source["status"], if end < size { "partial" } else { "ok" });
        } else {
            assert_eq!(source["status"], "unavailable", "{case}: {source}");
            assert_eq!(source["results"], json!([]));
        }
        pages.push(page);
    }
    std::fs::write(
        root.join("captured-pages.json"),
        serde_json::to_vec(&pages).unwrap(),
    )
    .unwrap();
    let definition = std::fs::read_to_string(root.join("held-definition.json")).unwrap();
    let request = ReadRequest {
        args: MagnetArgs {
            magnet: MagnetDefinition::parse("mag-a1c7e2f09b3d4e68", &definition).unwrap(),
            mode: MagnetMode::Page {
                source: None,
                types: None,
            },
            bundle: Err("posts only".into()),
            gone: Arc::default(),
        },
        cursor: None,
        limit: None,
        deadline: Instant::now() + Duration::from_secs(2),
    };
    let mut answer = mentis_ops::run(
        &MagnetRead { window: &window },
        &reader,
        ReadClass::Background,
        &request,
    )
    .unwrap();
    let Prepared(plan) = answer.rows.pop().unwrap();
    let until = Instant::now() + Duration::from_secs(2);
    let combined = plan.finish(&window, &|| Instant::now() >= until);
    let combined_json: Json = serde_json::from_str(&combined.dumps()).unwrap();
    for source in combined_json["sources"].as_array().unwrap().iter().skip(1) {
        assert_eq!(source["dates"]["after"]["applied"], false);
    }
    std::fs::write(root.join("captured-batch-page.json"), combined.dumps()).unwrap();
    // The fixture Brain holds other files and Conversations. File-only collection must
    // read exactly the configured files, including at both source-count bounds.
    let original: Json = serde_json::from_str(&definition).unwrap();
    let files: Vec<Json> = original["sources"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|s| s["kind"] == "file")
        .cloned()
        .collect();
    let mut file_only_batches = Vec::new();
    for count in [1, 20] {
        let mut config = original.clone();
        let selected: Vec<Json> = (0..count)
            .map(|i| {
                files.get(i).cloned().unwrap_or_else(|| {
                    json!({
                        "kind":"file", "collection":"col-held-conformance",
                        "path":format!("unobserved-{i}.txt")
                    })
                })
            })
            .collect();
        config["sources"] = json!(selected);
        let request = ReadRequest {
            args: MagnetArgs {
                magnet: MagnetDefinition::parse("mag-a1c7e2f09b3d4e68", &config.to_string())
                    .unwrap(),
                mode: MagnetMode::Page {
                    source: None,
                    types: None,
                },
                bundle: Err("file-only collection needs no post extraction".into()),
                gone: Arc::default(),
            },
            cursor: None,
            limit: None,
            deadline: Instant::now() + Duration::from_secs(2),
        };
        let mut answer = mentis_ops::run(
            &MagnetRead { window: &window },
            &reader,
            ReadClass::Background,
            &request,
        )
        .unwrap();
        let Prepared(plan) = answer.rows.pop().unwrap();
        let until = Instant::now() + Duration::from_secs(2);
        let page: Json =
            serde_json::from_str(&plan.finish(&window, &|| Instant::now() >= until).dumps())
                .unwrap();
        let sources = page["sources"].as_array().unwrap();
        assert_eq!(sources.len(), count);
        for (source, configured) in sources.iter().zip(&selected) {
            assert_eq!(&source["source"], configured);
            assert_eq!(source["dates"]["after"]["applied"], false);
            for row in source["results"].as_array().unwrap() {
                assert_eq!(row["kind"], "file");
                assert_eq!(row["value"]["path"], configured["path"]);
            }
        }
        assert_eq!(sources[0]["status"], "ok");
        assert_eq!(sources[0]["results"].as_array().unwrap().len(), 1);
        file_only_batches.push(json!({"definition":config, "page":page}));
    }
    std::fs::write(
        root.join("captured-file-only-batches.json"),
        serde_json::to_vec(&file_only_batches).unwrap(),
    )
    .unwrap();
    // THE LIFTED CHOICE, on this same conformance Brain. A `file` source naming no path reads the
    // whole collection, and the rows it returns are exactly the cases the exact reader can read --
    // every damaged or absent one reported in the source's reason, none silently dropped.
    let mut config = original.clone();
    config["sources"] = json!([{"kind": "file", "collection": "col-held-conformance"}]);
    let request = ReadRequest {
        args: MagnetArgs {
            magnet: MagnetDefinition::parse("mag-a1c7e2f09b3d4e68", &config.to_string()).unwrap(),
            mode: MagnetMode::Page {
                source: None,
                types: None,
            },
            bundle: Err("a file source needs no post extraction".into()),
            gone: Arc::default(),
        },
        cursor: None,
        limit: None,
        deadline: Instant::now() + Duration::from_secs(10),
    };
    let mut answer = mentis_ops::run(
        &MagnetRead { window: &window },
        &reader,
        ReadClass::Background,
        &request,
    )
    .unwrap();
    let Prepared(plan) = answer.rows.pop().unwrap();
    let until = Instant::now() + Duration::from_secs(10);
    let page: Json =
        serde_json::from_str(&plan.finish(&window, &|| Instant::now() >= until).dumps()).unwrap();
    let source = &page["sources"][0];
    let mut read: Vec<String> = source["results"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| row["value"]["path"].as_str().unwrap().to_owned())
        .collect();
    read.sort();
    let cases: Vec<Json> =
        serde_json::from_slice(&std::fs::read(root.join("held-cases.json")).unwrap()).unwrap();
    let mut want: Vec<String> = cases
        .iter()
        .filter(|c| c["available"] == true)
        .map(|c| c["path"].as_str().unwrap().to_owned())
        .collect();
    want.sort();
    assert_eq!(read, want, "{source}");
    assert_eq!(source["status"], "partial", "{source}");
    let why = source["reason"].as_str().unwrap();
    for case in cases.iter().filter(|c| c["available"] != true) {
        let path = case["path"].as_str().unwrap();
        // The one case never admitted at all is not an object of the collection, so it is not
        // something a collection-wide read can report missing.
        if case["damage"] == "unobserved" {
            assert!(!why.contains(path), "{path} was never admitted: {why}");
        } else {
            assert!(why.contains(path), "{path} is not reported: {why}");
        }
    }
    let result = Command::new(std::env::var("MENTIS_COLLECTION_PYTHON").unwrap_or("python".into()))
        .current_dir(&repo)
        .env("PYTHONPATH", &repo)
        .args(["-m", "tools.magnet_held_file_fixture", "--check"])
        .arg(&root)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}
