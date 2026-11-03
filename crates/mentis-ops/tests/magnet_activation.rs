//! A Magnet's manual activation (`docs/magnets/M1-contract.md`, "Manual activation"): what Rust already
//! does with `tests/fixtures/magnet-conformance/activation`. The processor isn't built: this holds that
//! `Py` writes the fixtures' exact bytes and `MagnetDefinition::parse` reads what Python would approve.

use mentis_ops::magnet::{MagnetDefinition, NotADefinition};
use mentis_ops::pyjson;

fn dir() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures/magnet-conformance/activation")
}

fn fixture(name: &str) -> serde_json::Value {
    serde_json::from_str(&std::fs::read_to_string(dir().join(name)).unwrap()).unwrap()
}

fn rows<'v>(value: &'v serde_json::Value, key: &str) -> &'v Vec<serde_json::Value> {
    value[key].as_array().unwrap()
}

#[test]
fn an_artifact_is_what_py_writes_of_it() {
    let all = fixture("artifacts.json");
    for (name, info) in all["artifacts"].as_object().unwrap() {
        let bytes = std::fs::read(dir().join(info["file"].as_str().unwrap())).unwrap();
        assert_eq!(bytes.len() as u64, info["size"].as_u64().unwrap(), "{name}");
        let text = String::from_utf8(bytes).unwrap();
        let read = pyjson::loads(&text).unwrap_or_else(|| panic!("{name} reads"));
        assert_eq!(read.dumps(), text, "{name}: one serialization");
    }
}

#[test]
fn a_public_body_is_the_same_bytes_whichever_side_says_it() {
    let refusals = fixture("refusals.json");
    for (name, row) in refusals.as_object().unwrap() {
        let bytes = row["bytes"].as_str().unwrap();
        assert_eq!(pyjson::loads(bytes).unwrap().dumps(), bytes, "{name}");
    }
    let results = fixture("results.json");
    for case in ["complete", "partial"] {
        for answer in ["first", "replay"] {
            let bytes = results[case][answer]["bytes"].as_str().unwrap();
            assert_eq!(
                pyjson::loads(bytes).unwrap().dumps(),
                bytes,
                "{case} {answer}"
            );
        }
    }
}

#[test]
fn a_private_answer_s_body_goes_on_as_python_would_send_it() {
    let refusals = fixture("refusals.json");
    let answers = fixture("answers.json");
    let mut quoted = 0;
    for row in rows(&answers, "rows") {
        let Some(wire) = row["wire_text"].as_str() else {
            continue;
        };
        let Ok(answer) = serde_json::from_str::<serde_json::Value>(wire) else {
            continue;
        };
        let (Some("refused"), Some(said)) = (
            answer["state"].as_str(),
            row["decides"].as_str().and_then(|name| refusals.get(name)),
        ) else {
            continue;
        };
        let read = pyjson::loads(wire).expect("a whole answer reads");
        let pyjson::Py::Dict(fields) = read else {
            panic!("{wire}")
        };
        // A row spoiling its answer decides something else, and has nothing to quote.
        let Some((_, body)) = fields.iter().find(|(key, _)| key == "body") else {
            continue;
        };
        if answer["status"] == said["status"] && answer["body"] == said["body"] {
            assert_eq!(
                body.dumps(),
                said["bytes"].as_str().unwrap(),
                "{}",
                row["id"]
            );
            quoted += 1;
        }
    }
    assert!(quoted >= 20, "{quoted} answers compared");
}

#[test]
fn what_python_would_approve_rust_reads() {
    let all = fixture("definitions.json");
    let id = all["magnet"].as_str().unwrap();
    for row in rows(&all, "executable") {
        let text = row["definition"].to_string();
        let got = MagnetDefinition::parse(id, &text);
        if row["id"] == "later-schema" {
            assert!(matches!(got, Err(NotADefinition::LaterSchema(_))));
        } else if row["answer"] == "ready" {
            let got = got.unwrap_or_else(|_| panic!("{} reads", row["id"]));
            assert_eq!(
                got.sources.len(),
                row["definition"]["sources"].as_array().unwrap().len(),
                "{}",
                row["id"]
            );
        }
    }
}

#[test]
fn a_definition_at_the_bound_reads_exactly() {
    let all = fixture("definitions.json");
    let id = all["magnet"].as_str().unwrap();
    let row = rows(&all, "files")
        .iter()
        .find(|row| row["id"] == "at-the-bound")
        .unwrap();
    let total = row["pad"]["total"].as_u64().unwrap() as usize;
    let mut text = row["pad"]["text"].as_str().unwrap().to_owned();
    text.push_str(&" ".repeat(total - text.len()));
    assert_eq!(text.len(), 262_144);
    assert!(MagnetDefinition::parse(id, &text).is_ok());
}

#[test]
fn the_definition_rust_refuses_is_the_one_the_answers_call_a_disagreement() {
    let all = fixture("answers.json");
    let id = all["magnet"].as_str().unwrap();
    let row = rows(&all, "rows")
        .iter()
        .find(|row| row["id"] == "ready-rust-rejects-what-python-approved")
        .unwrap();
    let answer: serde_json::Value =
        serde_json::from_str(row["wire_text"].as_str().unwrap()).unwrap();
    assert_eq!(row["decides"], "internal-protocol-error");
    assert!(matches!(
        MagnetDefinition::parse(id, answer["definition"]["raw"].as_str().unwrap()),
        Err(NotADefinition::Malformed(_))
    ));
}
