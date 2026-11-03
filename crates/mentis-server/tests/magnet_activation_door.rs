//! A Magnet's manual activation (`docs/magnets/M1-contract.md`, "Manual activation"): what the front
//! already has of its door, held against `tests/fixtures/magnet-conformance/activation/door.json`. The
//! route itself isn't built, and its own 413 and 415 aren't here until it is.

use std::path::PathBuf;

use mentis_server::front::answers;
use mentis_server::front::head::{self, Reads, Refusal};

fn door() -> serde_json::Value {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures/magnet-conformance/activation/door.json");
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

fn rows(door: &serde_json::Value) -> Vec<serde_json::Value> {
    door["rows"].as_array().unwrap().clone()
}

/// The request's head, as `tests/test_magnet_activation_contract.py` writes it to Python.
fn head_of(door: &serde_json::Value, row: &serde_json::Value) -> Vec<u8> {
    let mut text = format!("POST {} HTTP/1.1\r\n", door["target"].as_str().unwrap());
    let headers = row["headers"].as_array().unwrap();
    if !headers
        .iter()
        .any(|h| h[0].as_str().unwrap().trim().eq_ignore_ascii_case("host"))
    {
        text.push_str("Host: 127.0.0.1:8760\r\n");
    }
    for header in headers {
        text.push_str(&format!(
            "{}: {}\r\n",
            header[0].as_str().unwrap(),
            header[1].as_str().unwrap()
        ));
    }
    text.push_str("\r\n");
    text.into_bytes()
}

fn body_of(written: &answers::Written) -> String {
    let text = String::from_utf8(written.bytes.clone()).unwrap();
    text.split_once("\r\n\r\n").unwrap().1.to_owned()
}

fn status_of(written: &answers::Written) -> u64 {
    let text = String::from_utf8_lossy(&written.bytes);
    text.split(' ').nth(1).unwrap().parse().unwrap()
}

fn the_same(written: &answers::Written, row: &serde_json::Value) {
    assert_eq!(status_of(written), row["expect"]["status"], "{}", row["id"]);
    assert_eq!(body_of(written), row["expect"]["body"], "{}", row["id"]);
    assert!(written.closes, "{}", row["id"]);
}

#[test]
fn a_head_python_refuses_the_front_refuses_in_the_same_bytes() {
    let door = door();
    let mut seen = 0;
    for row in rows(&door) {
        let Some(want) = row["head_refusal"].as_str() else {
            continue;
        };
        seen += 1;
        let got = head::parse(head_of(&door, &row));
        let refusal = got.refusal.unwrap_or_else(|| panic!("{}", row["id"]));
        let named = match refusal {
            Refusal::ContentLengthNotDigits => "ContentLengthNotDigits",
            Refusal::MoreThanOneContentLength => "MoreThanOneContentLength",
            Refusal::NotNameValue => "NotNameValue",
            ref other => panic!("{other:?}"),
        };
        assert_eq!(named, want, "{}", row["id"]);
        the_same(&answers::refusal(&refusal, false), &row);
    }
    assert!(seen >= 14, "{seen} rows");
}

#[test]
fn a_length_python_accepts_the_front_accepts() {
    let door = door();
    for row in rows(&door) {
        if row["head_refusal"].is_string() {
            continue;
        }
        let got = head::parse(head_of(&door, &row));
        assert_eq!(got.refusal, None, "{}", row["id"]);
        if row["stage"] == "accepted" {
            let body = row["body_text"].as_str().unwrap();
            assert_eq!(got.content_length(), body.len() as u64, "{}", row["id"]);
        }
    }
}

#[test]
fn the_body_limit_s_boundary_is_read_from_the_length() {
    let door = door();
    for (id, length) in [
        ("body-limit-65536-accepted", 65_536),
        ("body-limit-65537-refused", 65_537),
    ] {
        let row = rows(&door).into_iter().find(|row| row["id"] == id).unwrap();
        assert_eq!(head::parse(head_of(&door, &row)).content_length(), length);
    }
}

#[test]
fn the_words_the_front_already_has_are_the_door_s() {
    let door = door();
    let target = door["target"].as_str().unwrap();
    for row in rows(&door) {
        let written = match row["id"].as_str().unwrap() {
            "host-refused" | "host-before-framing" => {
                answers::refused_host(Some("evil.example"), true)
            }
            "framing-chunked" | "framing-any-other" => answers::transfer_encoding_refused(),
            "client-missing" | "client-not-one" | "over-limit-door-first-client" => {
                answers::missing_client(true)
            }
            "grant-without-client"
            | "grant-with-client"
            | "grant-before-content-type"
            | "over-limit-door-first-grant" => answers::grant_refused(
                "a worker grant authorises /api/worker and nothing else",
                target,
                true,
            ),
            _ => continue,
        };
        the_same(&written, &row);
    }
}

#[test]
fn the_private_paths_are_decided_before_the_table_and_never_forwarded() {
    let door = door();
    let port = &door["private"]["public_port"];
    let written = answers::no_such_surface(true);
    assert_eq!(status_of(&written), port["status"]);
    assert_eq!(body_of(&written), port["body"]);
    for target in port["targets"].as_array().unwrap() {
        assert_eq!(head::python_reads(target.as_str().unwrap()), Reads::Private);
    }
}
