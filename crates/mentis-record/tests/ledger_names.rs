//! The ledger this build names is Python's `migrations` list, read from this clone's Python.

mod support;

use mentis_record::LEDGER;
use serde_json::Value;
use support::run_python;

const PYTHONS_LIST: &str = "import json\nfrom mentis.spine import migrations\n\
    print(json.dumps([[m.id, m.checksum] for m in migrations.migrations()]))";

#[test]
fn names_every_python_migration() {
    let listed: Value = serde_json::from_str(&run_python(PYTHONS_LIST, &[])).unwrap();
    let python: Vec<(String, String)> = listed
        .as_array()
        .unwrap()
        .iter()
        .map(|row| {
            (
                row[0].as_str().unwrap().to_string(),
                row[1].as_str().unwrap().to_string(),
            )
        })
        .collect();
    let named: Vec<(String, String)> = LEDGER
        .iter()
        .map(|(id, sum)| (id.to_string(), sum.to_string()))
        .collect();
    assert!(!python.is_empty(), "Python declares at least its adoption");
    assert_eq!(named, python, "a Python migration this build does not name");
}
