//! How the engine `Scope` runs says it will run the two recursive statements. Their cost is their
//! plan: with an automatic index over `entry`, or `entry` scanned to find what the walk reached, one
//! id costs what the whole table costs, and no answer changes (`ent-8b57ada623fc`). So nothing else
//! would catch it coming back, whether through an edit or a `rusqlite` upgrade. `MENTIS_RULES_BRAIN`
//! names a Brain copy to read instead, with nothing written to it.

#[path = "support/mod.rs"]
mod support;

use std::path::PathBuf;

use mentis_record::{
    Brain, BrainOpener, Flow, Id, Param, Position, ReadClass, ReadScope, RecordError, RecordReader,
    Row, Value,
};

/// What a scan may read: the walk's own rows, the ids asked about, and the materialized roles.
const MAY_SCAN: &[&str] = &["r", "roles", "o", "json_each"];

/// What an automatic index may be over: the materialized roles, which are a few rows and are read
/// once. Over anything else it was built from the table, or from the walk, for each call.
const MAY_INDEX: &[&str] = &["roles", "o"];

/// The steps of a plan this read must not take.
fn offences(plan: &[String]) -> Vec<&String> {
    plan.iter()
        .filter(|step| {
            let words: Vec<&str> = step.split_whitespace().collect();
            match words[..] {
                ["SCAN", table, ..] => !MAY_SCAN.contains(&table),
                ["SEARCH", table, ..] => step.contains("AUTOMATIC") && !MAY_INDEX.contains(&table),
                _ => false,
            }
        })
        .collect()
}

/// A scope that remembers what it was asked to run, since the statements are the rules' own.
struct Recording<'a> {
    inner: Box<dyn ReadScope>,
    seen: &'a mut Vec<&'static str>,
}

impl ReadScope for Recording<'_> {
    fn position(&self) -> Position {
        self.inner.position()
    }

    fn query(
        &mut self,
        sql: &'static str,
        params: &[Param<'_>],
        each: &mut dyn FnMut(&dyn Row) -> Result<Flow, RecordError>,
    ) -> Result<(), RecordError> {
        self.seen.push(sql);
        self.inner.query(sql, params, each)
    }

    fn statements(&self) -> u32 {
        self.inner.statements()
    }
}

fn brain() -> PathBuf {
    match std::env::var("MENTIS_RULES_BRAIN") {
        Ok(brain) => PathBuf::from(brain),
        Err(_) => support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "plans"),
    }
}

/// The one recursive statement `read` runs, and its plan.
fn plan_of_what_runs(
    reader: &dyn RecordReader,
    read: impl FnOnce(&mut dyn ReadScope) -> Result<(), RecordError>,
) -> Vec<String> {
    let mut seen = Vec::new();
    let inner = reader.read_scope(ReadClass::Background).unwrap();
    read(&mut Recording {
        inner,
        seen: &mut seen,
    })
    .unwrap();
    let recursive: Vec<&str> = seen
        .into_iter()
        .filter(|sql| sql.starts_with("WITH RECURSIVE"))
        .collect();
    let [sql] = recursive[..] else {
        panic!("{recursive:#?}");
    };
    let explain: &'static str = Box::leak(format!("EXPLAIN QUERY PLAN {sql}").into_boxed_str());
    let mut scope = reader.read_scope(ReadClass::Background).unwrap();
    let mut plan = Vec::new();
    scope
        .query(explain, &[Param::Text("[\"x\"]")], &mut |row| {
            if let Value::Text(step) = row.value(3)? {
                plan.push(String::from_utf8(step.to_vec()).unwrap());
            }
            Ok(Flow::Continue)
        })
        .unwrap();
    plan
}

#[test]
fn neither_recursive_statement_builds_an_index_over_entry_or_scans_it() {
    let reader = Brain::open(&brain()).unwrap();
    let asked = [Id("ent-nothing-holds-this".to_owned())];
    let reaching = plan_of_what_runs(&reader, |scope| {
        mentis_rules::standing_many(scope, &asked, None).map(|_| ())
    });
    let line = plan_of_what_runs(&reader, |scope| {
        mentis_rules::roots(scope, &asked).map(|_| ())
    });
    for plan in [&reaching, &line] {
        assert_eq!(offences(plan), Vec::<&String>::new(), "{plan:#?}");
        // `reach` drives, by the indexes on `entry`, and the roles are read once.
        assert!(
            plan.iter().any(|step| step == "MATERIALIZE roles"),
            "{plan:#?}"
        );
        assert!(
            plan.iter()
                .any(|step| step.starts_with("SEARCH l USING INDEX sqlite_autoindex_entry_1")),
            "{plan:#?}"
        );
    }
    assert!(
        reaching
            .iter()
            .any(|step| step.starts_with("SEARCH l USING INDEX idx_entry_link_to")),
        "{reaching:#?}"
    );
    for index in ["idx_entry_link_to", "idx_entry_link_from"] {
        let at = format!("SEARCH l USING INDEX {index}");
        assert!(line.iter().any(|step| step.starts_with(&at)), "{line:#?}");
    }
}

/// The steps that made these statements slow, as a copied real Brain's plans printed them.
#[test]
fn the_check_refuses_the_steps_it_is_there_to_stop() {
    let refused = [
        "SEARCH l USING AUTOMATIC COVERING INDEX (link_relation_version=? AND link_relation=?)",
        "SCAN l",
        "SEARCH r USING AUTOMATIC COVERING INDEX (id=?)",
        "SCAN d",
    ];
    for step in refused {
        let plan = [step.to_owned()];
        assert_eq!(offences(&plan).len(), 1, "{step}");
    }
    let allowed = [
        "SCAN r",
        "SCAN roles",
        "SCAN json_each VIRTUAL TABLE INDEX 1:",
        "SEARCH roles USING AUTOMATIC PARTIAL COVERING INDEX (role=?)",
        "SEARCH o USING AUTOMATIC COVERING INDEX (relation=? AND version=?)",
        "SEARCH l USING INDEX idx_entry_link_to (link_to=? AND link_relation=?)",
    ];
    for step in allowed {
        let plan = [step.to_owned()];
        assert_eq!(offences(&plan).len(), 0, "{step}");
    }
}
