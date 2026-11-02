//! `mentis_ops::python` against Python itself, every code point. A route's matching and order rest
//! on these, and two Unicode tables can differ.

#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::collections::HashMap;

use mentis_ops::python::{self, PythonInt};

const DUMP: &str = r#"
import json
lower, space = {}, []
for c in range(0x110000):
    if 0xD800 <= c <= 0xDFFF:
        continue
    text = chr(c)
    if text.lower() != text:
        lower[c] = text.lower()
    if text.isspace():
        space.append(c)
print(json.dumps({"lower": lower, "space": space}))
"#;

const INTS: &str = r#"
import json, sys
out = []
for text in json.loads(sys.argv[1]):
    try:
        out.append(str(int(text)))
    except ValueError:
        out.append(None)
print(json.dumps(out))
"#;

fn tables() -> serde_json::Value {
    let done = support::python().arg("-c").arg(DUMP).output().unwrap();
    assert!(done.status.success());
    serde_json::from_slice(&done.stdout).unwrap()
}

#[test]
fn lower_and_space_agree_with_python_at_every_code_point() {
    let tables = tables();
    let lower: HashMap<u32, String> = tables["lower"]
        .as_object()
        .unwrap()
        .iter()
        .map(|(c, to)| (c.parse().unwrap(), to.as_str().unwrap().to_owned()))
        .collect();
    let space: Vec<u32> = tables["space"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| c.as_u64().unwrap() as u32)
        .collect();
    let mut left_to_python = 0;
    for code in (0..0x11_0000u32).filter(|code| !(0xD800..=0xDFFF).contains(code)) {
        let c = char::from_u32(code).unwrap();
        let text = c.to_string();
        let want = lower.get(&code).cloned().unwrap_or_else(|| text.clone());
        match python::lower(&text) {
            Some(got) => assert_eq!(got, want, "U+{code:04X}"),
            None => {
                left_to_python += 1;
                // It is on the list because the two tables differ there, or the list is too long.
                assert_eq!(want, text, "U+{code:04X} is known to both");
            }
        }
        assert_eq!(python::is_space(c), space.contains(&code), "U+{code:04X}");
    }
    println!("{left_to_python} code points left to Python");
}

#[test]
fn a_final_sigma_is_as_python_lowers_it() {
    let texts = [
        "\u{3a3}",
        "A\u{3a3}",
        "A\u{3a3} B",
        "\u{3a3}A",
        "\u{3a3}\u{391}\u{3a3}",
        "A\u{3a3}.",
    ];
    let list = serde_json::to_string(&texts).unwrap();
    let script =
        "import json, sys\nprint(json.dumps([t.lower() for t in json.loads(sys.argv[1])]))";
    let done = support::python()
        .arg("-c")
        .arg(script)
        .arg(list)
        .output()
        .unwrap();
    assert!(done.status.success());
    let want: Vec<String> = serde_json::from_slice(&done.stdout).unwrap();
    for (text, want) in texts.iter().zip(want) {
        assert_eq!(python::lower(text).unwrap(), want, "{text}");
    }
}

#[test]
fn int_agrees_with_python() {
    let texts = [
        "0",
        "7",
        "007",
        "+7",
        "-7",
        " 7",
        "7 ",
        "\t7\n",
        "1_000",
        "1__0",
        "_1",
        "1_",
        "",
        " ",
        "+",
        "-",
        "--1",
        "+-1",
        "0x10",
        "1e3",
        "1.0",
        "a",
        "1 2",
        "\u{1c}7\u{1f}",
    ];
    let list = serde_json::to_string(&texts).unwrap();
    let done = support::python()
        .arg("-c")
        .arg(INTS)
        .arg(list)
        .output()
        .unwrap();
    assert!(done.status.success());
    let want: Vec<Option<String>> = serde_json::from_slice(&done.stdout).unwrap();
    for (text, want) in texts.iter().zip(want) {
        match (python::int(text), want) {
            (PythonInt::Value(got), Some(want)) => assert_eq!(got.to_string(), want, "{text:?}"),
            (PythonInt::NotInt, None) => {}
            (got, want) => panic!("{text:?}: {got:?} against {want:?}"),
        }
    }
}
