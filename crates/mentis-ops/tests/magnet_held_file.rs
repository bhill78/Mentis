//! The same observation/damage/byte cases Python's source reader consumes.
use std::{path::PathBuf, process::Command, sync::Arc, time::{Instant, Duration}};
use mentis_record::{Brain, BrainOpener};
use mentis_ops::{ReadRequest, ReadClass, magnet::{MagnetRead, MagnetArgs, MagnetDefinition, MagnetMode},
    window::{Window, Prepared}};
use serde_json::{Value as Json, json};

#[test]
fn shared_python_reading_cases_through_the_background_m1_composer() {
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let root = PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join(format!("held-files-{}", std::process::id()));
    let result = Command::new(std::env::var("MENTIS_COLLECTION_PYTHON").unwrap_or("python".into()))
        .current_dir(&repo).env("PYTHONPATH", &repo)
        .args(["-m", "tools.magnet_held_file_fixture"]).arg(&root).output().unwrap();
    assert!(result.status.success(), "{}", String::from_utf8_lossy(&result.stderr));
    let cases: Vec<Json> = serde_json::from_slice(&std::fs::read(root.join("held-cases.json")).unwrap()).unwrap();
    let reader = Brain::open(&root).unwrap();
    let window = Window::new(&root, &root);
    let mut pages = Vec::new();
    for case in cases {
        let definition = json!({"id":"mag-held", "sources":[{"kind":"file", "collection":"col-held-conformance", "path":case["path"]}], "selection":{}});
        let request = ReadRequest { args: MagnetArgs {
            magnet: MagnetDefinition::parse("mag-held", &definition.to_string()).unwrap(),
            mode: MagnetMode::Page { source: None, types: None }, bundle: Err("no extraction".into()),
            gone: Arc::default(),
        }, cursor: None, limit: None, deadline: Instant::now()+Duration::from_secs(2) };
        let mut answer = mentis_ops::run(&MagnetRead { window: &window }, &reader, ReadClass::Background, &request).unwrap();
        let Prepared(plan) = answer.rows.pop().unwrap();
        let until = Instant::now()+Duration::from_secs(2);
        let page: Json = serde_json::from_str(&plan.finish(&window, &|| Instant::now()>=until).dumps()).unwrap();
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
            assert_eq!(v["omitted_bytes"], size-end);
            assert_eq!(v["shortened"], end<size);
            assert_eq!(v["next_offset"], if end<size { json!(end) } else { Json::Null });
            assert_eq!(source["status"], if end<size { "partial" } else { "ok" });
        } else {
            assert_eq!(source["status"], "unavailable", "{case}: {source}");
            assert_eq!(source["results"], json!([]));
        }
        pages.push(page);
    }
    std::fs::write(root.join("captured-pages.json"), serde_json::to_vec(&pages).unwrap()).unwrap();
    let result = Command::new(std::env::var("MENTIS_COLLECTION_PYTHON").unwrap_or("python".into()))
        .current_dir(&repo).env("PYTHONPATH", &repo)
        .args(["-m", "tools.magnet_held_file_fixture", "--check"]).arg(&root).output().unwrap();
    assert!(result.status.success(), "{}", String::from_utf8_lossy(&result.stderr));
}
