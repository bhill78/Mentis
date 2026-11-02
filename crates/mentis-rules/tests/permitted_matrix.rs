//! Rust's `permitted` and refusal words against `tests/front/permission_matrix.json`, generated from
//! `mentis.worker` by `tools/r3/permission_matrix.py`. `tests/front/test_permission_matrix.py` holds
//! the file to Python, so a difference on either side fails one of the two.
//!
//! Non-ASCII names check the door's forward, not Rust's wording (`R3-mirror.md`, section 6). Every
//! other refused operation's whole text is compared by its SHA-256.

use std::path::Path;

use mentis_rules::permitted::{
    OTHER_CORPUS_WORDS, TRANSIENT_SCOPE, not_permitted_words, permitted, refused_body,
    repr_is_simple,
};
use serde_json::Value;
use sha2::{Digest, Sha256};

fn matrix() -> Value {
    let file = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("tests")
        .join("front")
        .join("permission_matrix.json");
    serde_json::from_str(&std::fs::read_to_string(file).expect("the matrix is generated"))
        .expect("the matrix is JSON")
}

fn operations_of(shape: &Value) -> Option<Vec<String>> {
    shape["operations"].as_array().map(|names| {
        names
            .iter()
            .map(|name| name.as_str().unwrap().to_owned())
            .collect()
    })
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[test]
fn every_shape_permits_what_python_permits_in_python_s_order() {
    let matrix = matrix();
    let results = matrix["results"].as_array().unwrap();
    let shapes = matrix["shapes"].as_array().unwrap();
    assert_eq!(shapes.len(), 10 * (1 + 64 + 4));
    for shape in shapes {
        let scope = shape["scope"].as_str();
        let operations = operations_of(shape);
        let got = permitted(scope, operations.as_deref());
        let want: Vec<&str> = results[shape["permitted"].as_u64().unwrap() as usize]
            .as_array()
            .unwrap()
            .iter()
            .map(|name| name.as_str().unwrap())
            .collect();
        assert_eq!(got, want, "{scope:?} {operations:?}");
    }
}

#[test]
fn every_refused_operation_is_refused_in_python_s_words() {
    let matrix = matrix();
    let names: Vec<&str> = matrix["names"]
        .as_array()
        .unwrap()
        .iter()
        .map(|name| name.as_str().unwrap())
        .collect();
    let (mut compared, mut forwarded) = (0u32, 0u32);
    for shape in matrix["shapes"].as_array().unwrap() {
        let scope = shape["scope"].as_str();
        let operations = operations_of(shape);
        let allowed = permitted(scope, operations.as_deref());
        let refused = shape["refused"].as_array().unwrap();

        // Refused is exactly what isn't permitted, of the names asked.
        let want: Vec<usize> = (0..names.len())
            .filter(|at| !allowed.contains(&names[*at]))
            .collect();
        let got: Vec<usize> = refused
            .iter()
            .map(|one| one[0].as_u64().unwrap() as usize)
            .collect();
        assert_eq!(got, want, "{scope:?} {operations:?}");

        for one in refused {
            let op = names[one[0].as_u64().unwrap() as usize];
            if !repr_is_simple(op) || !scope.is_none_or(repr_is_simple) {
                forwarded += 1;
                continue;
            }
            let text = not_permitted_words(op, scope, &allowed);
            assert_eq!(
                hex(&Sha256::digest(text.as_bytes())),
                one[1].as_str().unwrap(),
                "{op:?} under {scope:?} {operations:?}: {text}"
            );
            compared += 1;
        }
    }
    println!("{compared} refusal texts compared by hash, {forwarded} the door forwards");
    assert!(
        compared > 5_000 && forwarded > 1_000,
        "{compared}, {forwarded}"
    );
}

#[test]
fn a_sampled_refusal_says_the_whole_text_and_body() {
    let matrix = matrix();
    let samples = matrix["samples"].as_array().unwrap();
    assert!(samples.len() >= 40, "{}", samples.len());
    let mut said = 0;
    for sample in samples {
        let scope = sample["scope"].as_str();
        let op = sample["op"].as_str().unwrap();
        if !repr_is_simple(op) || !scope.is_none_or(repr_is_simple) {
            continue;
        }
        let operations = operations_of(sample);
        let allowed = permitted(scope, operations.as_deref());
        let text = not_permitted_words(op, scope, &allowed);
        assert_eq!(text, sample["text"].as_str().unwrap());
        assert_eq!(refused_body(&text), sample["body"].as_str().unwrap());
        said += 1;
    }
    assert!(said >= 30, "{said}");
}

#[test]
fn the_other_corpus_refusal_is_python_s() {
    let matrix = matrix();
    let other = &matrix["other_corpus"];
    assert_eq!(OTHER_CORPUS_WORDS, other["text"].as_str().unwrap());
    assert_eq!(
        refused_body(OTHER_CORPUS_WORDS),
        other["body"].as_str().unwrap()
    );
}

#[test]
fn names_the_door_forwards_are_the_ones_rust_can_t_show() {
    let matrix = matrix();
    for name in matrix["names"].as_array().unwrap() {
        let name = name.as_str().unwrap();
        assert_eq!(repr_is_simple(name), name.is_ascii(), "{name:?}");
    }
    let scopes: Vec<Option<&str>> = matrix["shapes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|shape| shape["scope"].as_str())
        .collect();
    assert!(scopes.contains(&Some(TRANSIENT_SCOPE)));
    assert!(scopes.iter().flatten().any(|scope| !repr_is_simple(scope)));
}

#[test]
fn every_scope_holds_every_moved_read() {
    let matrix = matrix();
    for shape in matrix["shapes"].as_array().unwrap() {
        let scope = shape["scope"].as_str();
        let operations = operations_of(shape);
        let allowed = permitted(scope, operations.as_deref());
        for moved in [
            "kinds",
            "capabilities",
            "history",
            "owner_decisions",
            "governed",
            "resolve",
        ] {
            assert!(allowed.contains(&moved), "{moved} under {scope:?}");
        }
    }
}
