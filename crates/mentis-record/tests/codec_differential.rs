//! The codec against Python's own `Store._canonical`, at PY_COMMIT: `R1-acceptance.md`, section G.
//! Each case goes to Python as what Python would hold, and comes back as bytes and a hash.

mod support;

use std::io::Write;
use std::process::Stdio;

use mentis_record::{
    Brain, BrainOpener, ChainVerifier, Chains, CodecRefused, RecordError, Value, canonical,
    row_hash,
};
use serde_json::{Value as Json, json};
use support::{fixtures, python, scratch_brain, writer};

const COLUMNS: [(&str, usize); 3] = [("entry", 13), ("operational", 12), ("delivery", 10)];

/// One line in per case, one line out. The hash is `_link_in_chain`'s arithmetic.
const OTHER_SIDE: &str = r#"
import hashlib, json, struct, sys
from mentis.spine.store import Store

def value(f):
    k = f["k"]
    if k == "null": return None
    if k == "text": return bytes.fromhex(f["v"]).decode("utf-8", "surrogatepass")
    if k == "int": return int(f["v"])
    if k == "real": return struct.unpack(">d", bytes.fromhex(f["v"]))[0]
    if k == "blob": return bytes.fromhex(f["v"])
    if k == "bool": return f["v"]
    raise ValueError(k)

for line in sys.stdin:
    case = json.loads(line)
    values = {f"c{i}": value(f) for i, f in enumerate(case["fields"])}
    try:
        material = Store._canonical(case["table"], list(values), values)
        raw = material.encode("utf-8")
        digest = hashlib.sha256((case["prev"] + chr(30) + material).encode("utf-8")).hexdigest()
        print(json.dumps({"canonical": raw.hex(), "hash": digest}))
    except UnicodeEncodeError:
        print(json.dumps({"refused": "UnicodeEncodeError"}))
"#;

/// A case in both forms: what Python holds, and what Rust reads back from the column.
enum Field {
    Null,
    Text(Vec<u8>),
    Int(i64),
    Real(f64),
    Blob(Vec<u8>),
    /// Python's value is `True`, or an integer past 64 bits: it never reaches SQLite as that. What
    /// the column holds is the text `str()` made of it.
    PythonOnly(Json, String),
}

fn text(s: &str) -> Field {
    Field::Text(s.as_bytes().to_vec())
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

impl Field {
    fn to_python(&self) -> Json {
        match self {
            Field::Null => json!({"k": "null"}),
            Field::Text(held) => json!({"k": "text", "v": hex(held)}),
            Field::Int(n) => json!({"k": "int", "v": n.to_string()}),
            Field::Real(n) => json!({"k": "real", "v": hex(&n.to_bits().to_be_bytes())}),
            Field::Blob(held) => json!({"k": "blob", "v": hex(held)}),
            Field::PythonOnly(value, _) => value.clone(),
        }
    }

    fn to_value(&self) -> Value<'_> {
        match self {
            Field::Null => Value::Null,
            Field::Text(held) => Value::Text(held),
            Field::Int(n) => Value::Integer(*n),
            Field::Real(n) => Value::Real(*n),
            Field::Blob(held) => Value::Blob(held),
            Field::PythonOnly(_, stored) => Value::Text(stored.as_bytes()),
        }
    }
}

struct Case {
    table: &'static str,
    prev: String,
    fields: Vec<Field>,
}

fn case(fields: Vec<Field>) -> Case {
    Case {
        table: "entry",
        prev: String::new(),
        fields,
    }
}

fn python_answers(cases: &[Case]) -> Vec<Json> {
    let code = fixtures().join("py-b8e324c");
    let mut child = python(&code)
        .arg("-c")
        .arg(OTHER_SIDE)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("Python starts");
    let mut stdin = child.stdin.take().unwrap();
    let lines: String = cases
        .iter()
        .map(|c| {
            let fields: Vec<Json> = c.fields.iter().map(Field::to_python).collect();
            json!({"table": c.table, "prev": c.prev, "fields": fields}).to_string() + "\n"
        })
        .collect();
    let feeding = std::thread::spawn(move || stdin.write_all(lines.as_bytes()));
    let done = child.wait_with_output().unwrap();
    feeding.join().unwrap().unwrap();
    assert!(done.status.success(), "Python failed");
    let answers: Vec<Json> = String::from_utf8(done.stdout)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    assert_eq!(answers.len(), cases.len());
    answers
}

/// Both sides, every case, the same bytes and the same hash, or both refusing.
fn agree(cases: &[Case]) {
    for (at, (c, want)) in cases.iter().zip(python_answers(cases)).enumerate() {
        let fields: Vec<Value<'_>> = c.fields.iter().map(Field::to_value).collect();
        match canonical(c.table, &fields) {
            Ok(got) => {
                assert_eq!(
                    Json::String(hex(&got)),
                    want["canonical"],
                    "case {at}: {}",
                    String::from_utf8_lossy(&got)
                );
                assert_eq!(
                    Json::String(row_hash(c.prev.as_bytes(), &got)),
                    want["hash"],
                    "case {at}"
                );
            }
            Err(CodecRefused::NotUtf8) => {
                assert_eq!(want["refused"], "UnicodeEncodeError", "case {at}");
            }
            Err(other) => panic!("case {at}: refused as {other}"),
        }
    }
}

fn the_bytes_of(fields: &[Value<'_>]) -> String {
    String::from_utf8(canonical("entry", fields).unwrap()).unwrap()
}

#[test]
fn null_against_empty_string() {
    assert_eq!(
        the_bytes_of(&[Value::Null, Value::Text(b"")]),
        "entry\u{1e}-\u{1e}0:"
    );
    agree(&[case(vec![Field::Null, text("")])]);
}

#[test]
fn a_value_cannot_shift_a_field_boundary() {
    let rs_inside = case(vec![text("owner\u{1e}observed:x"), Field::Null]);
    let rs_apart = case(vec![text("owner"), text("observed:x")]);
    let bytes = |c: &Case| {
        let fields: Vec<Value<'_>> = c.fields.iter().map(Field::to_value).collect();
        canonical(c.table, &fields).unwrap()
    };
    assert_ne!(bytes(&rs_inside), bytes(&rs_apart));
    agree(&[
        rs_inside,
        rs_apart,
        case(vec![text("3:abc"), text("-"), text(":"), text("--:--")]),
    ]);
}

#[test]
fn unicode_lengths_are_bytes_and_a_lone_surrogate_is_refused() {
    agree(&[
        case(vec![text("é"), text("日本語"), text("𝄞😀"), text("a\0b")]),
        // U+D800 as Python's surrogatepass writes it: both sides refuse.
        case(vec![Field::Text(vec![b'a', 0xed, 0xa0, 0x80])]),
        case(vec![Field::Text(vec![0xed, 0xbf, 0xbf])]),
    ]);
    assert_eq!(
        canonical("entry", &[Value::Text(&[0xed, 0xa0, 0x80])]),
        Err(CodecRefused::NotUtf8)
    );
    assert_eq!(
        canonical("entry", &[Value::Text(&[0xff])]),
        Err(CodecRefused::NotUtf8)
    );
}

#[test]
fn integers_are_decimal() {
    let past_64_bits = 2u128.pow(70).to_string();
    agree(&[case(vec![
        Field::Int(0),
        Field::Int(-1),
        Field::Int(7),
        Field::Int(i64::MAX),
        Field::Int(i64::MIN),
        Field::PythonOnly(json!({"k": "int", "v": past_64_bits}), past_64_bits.clone()),
    ])]);
}

#[test]
fn booleans_are_the_value_stored() {
    agree(&[case(vec![
        // Hashed by Python as `True` and read back from text: the form a written value takes.
        Field::PythonOnly(json!({"k": "bool", "v": true}), "True".to_string()),
        Field::PythonOnly(json!({"k": "bool", "v": false}), "False".to_string()),
        // The other form: a column holding SQLite's integer is hashed as that integer.
        Field::Int(1),
        Field::Int(0),
    ])]);
}

// The tie is the point of two of these values, so they are written out exactly.
#[allow(clippy::excessive_precision)]
#[test]
fn floats_are_python_repr() {
    let floats = [
        1e16,
        1e-5,
        1e15,
        1e22,
        1.5e300,
        5e-324,
        f64::MAX,
        f64::MIN_POSITIVE,
        0.0,
        -0.0,
        1.0,
        -1.0,
        100.0,
        0.1,
        0.0001,
        0.00001,
        123456789012345680.0,
        9999999999999998.0,
        1793572515.5909765,
        // Exactly between two shortest candidates, where Python rounds half to even.
        810299654.76953125,
        -810299654.76953125,
    ];
    let text_of = |n: f64| {
        the_bytes_of(&[Value::Real(n)])
            .rsplit(':')
            .next()
            .unwrap()
            .to_string()
    };
    assert_eq!(text_of(1e16), "1e+16");
    assert_eq!(text_of(1e-5), "1e-05");
    assert_eq!(text_of(-0.0), "-0.0");
    assert_eq!(text_of(1.0), "1.0");
    assert_eq!(text_of(810299654.76953125), "810299654.7695312");
    agree(&[case(floats.iter().map(|n| Field::Real(*n)).collect())]);
}

#[test]
fn non_finite_is_refused() {
    for n in [f64::INFINITY, f64::NEG_INFINITY, f64::NAN] {
        assert_eq!(
            canonical("entry", &[Value::Real(n)]),
            Err(CodecRefused::NonFinite)
        );
    }
    // One already in a Brain is reported, naming its row, and isn't hashed past.
    let root = scratch_brain("non-finite");
    writer(&root)
        .execute_batch(
            "INSERT INTO operational (seq, id, at, prev_hash, hash) \
             VALUES (7, 'opr-x', 9e999, '', 'abc');",
        )
        .unwrap();
    let reader = Brain::open(&root).unwrap();
    let answer = Chains.verify_chains(&reader);
    let Err(RecordError::ChainRefused { table, seq, .. }) = answer else {
        panic!("it is refused, and got {answer:?}");
    };
    assert_eq!((table, seq), ("operational", 7));
}

/// SplitMix64: a fixed seed gives these rows on every machine.
struct Generated(u64);

impl Generated {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9e37_79b9_7f4a_7c15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
        z ^ (z >> 31)
    }

    fn below(&mut self, n: u64) -> u64 {
        self.next() % n
    }

    fn field(&mut self) -> Field {
        const PIECES: [&str; 10] = [
            "\u{1e}",
            ":",
            "-",
            "0:",
            "é",
            "日本",
            "😀",
            "ent-3f",
            "{\"a\":1}",
            "\n\t\\",
        ];
        match self.below(9) {
            0 => Field::Null,
            1 => text(""),
            2 | 3 => {
                let mut held = String::new();
                for _ in 0..self.below(8) {
                    held.push_str(PIECES[self.below(PIECES.len() as u64) as usize]);
                }
                text(&held)
            }
            4 => Field::Int(self.next() as i64),
            5 => Field::Int(self.below(2000) as i64 - 1000),
            6 => {
                let n = f64::from_bits(self.next());
                Field::Real(if n.is_finite() { n } else { 0.5 })
            }
            7 => Field::Real(self.below(1 << 40) as f64 / 1024.0),
            _ => {
                let held: Vec<u8> = (0..self.below(12)).map(|_| self.next() as u8).collect();
                Field::Blob(held)
            }
        }
    }
}

#[test]
fn ten_thousand_generated_rows_at_a_fixed_seed() {
    let mut generated = Generated(0x4d65_6e74_6973_5231);
    let mut cases: Vec<Case> = Vec::with_capacity(10_000);
    let mut prev = String::new();
    for row in 0..10_000usize {
        let (table, columns) = COLUMNS[row % COLUMNS.len()];
        let fields: Vec<Field> = (0..columns).map(|_| generated.field()).collect();
        let values: Vec<Value<'_>> = fields.iter().map(Field::to_value).collect();
        let next = row_hash(prev.as_bytes(), &canonical(table, &values).unwrap());
        cases.push(Case {
            table,
            prev: std::mem::replace(&mut prev, next),
            fields,
        });
    }
    agree(&cases);
}
