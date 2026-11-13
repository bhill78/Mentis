//! The verifier over attested erasures (`erasure-design.md` 1.4), on small Brains built here by
//! hand: each row chained the way `Store` chains it, then erased the way a deletion erases it.

mod support;

use mentis_record::{
    Brain, BrainOpener, ChainReport, ChainVerifier, Chains, canonical, erasure_digest, row_hash,
    sha256_hex,
};
use rusqlite::types::Value as Sql;
use rusqlite::{Connection, params_from_iter};
use support::{scratch_brain, writer};

const DELETION: &str = "opr-deletion0001";

const ERASURE: &str = "
    CREATE TABLE erasure (seq INTEGER PRIMARY KEY AUTOINCREMENT, deletion TEXT NOT NULL,
        tbl TEXT NOT NULL, row_id TEXT NOT NULL, row_hash TEXT NOT NULL, residual TEXT NOT NULL,
        UNIQUE (tbl, row_id));
";

fn columns(table: &str) -> &'static [&'static str] {
    match table {
        "entry" => &[
            "id",
            "family",
            "def_name",
            "def_version",
            "body",
            "attributed_to",
            "written_by",
            "recorded_at",
            "origin",
            "link_from",
            "link_to",
            "link_relation",
            "link_relation_version",
        ],
        "operational" => &[
            "id",
            "at",
            "actor",
            "act",
            "conversation",
            "turn",
            "execution",
            "runtime",
            "because",
            "caused_by",
            "about",
            "detail",
        ],
        "delivery" => &[
            "id",
            "execution",
            "conversation",
            "participant",
            "runtime",
            "mechanism",
            "at",
            "material",
            "behavioural_sources",
            "operation_ok",
        ],
        _ => unreachable!(),
    }
}

fn as_record(value: &Sql) -> mentis_record::Value<'_> {
    match value {
        Sql::Null => mentis_record::Value::Null,
        Sql::Integer(n) => mentis_record::Value::Integer(*n),
        Sql::Real(n) => mentis_record::Value::Real(*n),
        Sql::Text(s) => mentis_record::Value::Text(s.as_bytes()),
        Sql::Blob(b) => mentis_record::Value::Blob(b),
    }
}

fn material(table: &str, fields: &[Sql]) -> Vec<u8> {
    let values: Vec<_> = fields.iter().map(as_record).collect();
    canonical(table, &values).unwrap()
}

fn text(s: &str) -> Sql {
    Sql::Text(s.to_string())
}

/// One chained row: its fields in `Store.CHAINED` order.
fn entry(id: &str, body: &str) -> Vec<Sql> {
    vec![
        text(id),
        text("material"),
        text("post"),
        Sql::Integer(1),
        text(body),
        text("owner"),
        text("owner"),
        Sql::Real(1_700_000_000.5),
        Sql::Null,
        Sql::Null,
        Sql::Null,
        Sql::Null,
        Sql::Null,
    ]
}

fn act(id: &str, kind: &str, conversation: &str, because: Option<&str>, detail: &str) -> Vec<Sql> {
    vec![
        text(id),
        Sql::Real(1_700_000_001.25),
        text("owner"),
        text(kind),
        text(conversation),
        Sql::Null,
        Sql::Null,
        Sql::Null,
        because.map_or(Sql::Null, text),
        Sql::Null,
        text(&format!("[\"{conversation}\"]")),
        text(detail),
    ]
}

fn delivered(id: &str, conversation: &str, material: &str) -> Vec<Sql> {
    vec![
        text(id),
        text("exe-1"),
        text(conversation),
        text("claude"),
        text("claude"),
        text("acp"),
        Sql::Real(1_700_000_002.0),
        text(material),
        text("[]"),
        Sql::Integer(1),
    ]
}

fn marker(deletion: &str) -> String {
    format!("{{\"erased\": \"{deletion}\"}}")
}

/// Appends rows the way `Store` chains them, each table's chain from its own last hash.
struct Chainer {
    db: Connection,
    heads: std::collections::HashMap<&'static str, String>,
}

impl Chainer {
    fn append(&mut self, table: &'static str, fields: Vec<Sql>) -> String {
        let prev = self.heads.get(table).cloned().unwrap_or_default();
        let hash = row_hash(prev.as_bytes(), &material(table, &fields));
        let cols = columns(table);
        let sql = format!(
            "INSERT INTO {table} ({}, prev_hash, hash) VALUES ({})",
            cols.join(", "),
            vec!["?"; cols.len() + 2].join(", ")
        );
        let mut all = fields;
        all.push(text(&prev));
        all.push(text(&hash));
        self.db.execute(&sql, params_from_iter(all)).unwrap();
        self.heads.insert(table, hash.clone());
        hash
    }

    fn row(&self, table: &str, id: &str) -> (Vec<Sql>, String) {
        let cols = columns(table);
        let sql = format!(
            "SELECT {}, hash FROM {table} WHERE id = ?1",
            cols.join(", ")
        );
        self.db
            .query_row(&sql, [id], |row| {
                let fields = (0..cols.len())
                    .map(|i| row.get::<_, Sql>(i))
                    .collect::<Result<Vec<_>, _>>()?;
                Ok((fields, row.get::<_, String>(cols.len())?))
            })
            .unwrap()
    }
}

/// What to get wrong, if anything.
#[derive(Default, Clone)]
struct Build {
    /// Leave this row's content in place: the deletion has not completed.
    not_erased: Option<&'static str>,
    /// The act states this digest instead.
    digest: Option<&'static str>,
    /// The act states this count instead.
    rows: Option<u64>,
    /// No deletion act in the record.
    no_act: bool,
    /// The erased post's marker names this act instead.
    marker_names: Option<&'static str>,
    /// An erasure row for an entry that is not there.
    ghost: bool,
}

/// Erased: `ent-2` (a post), `opr-1` (an act of that conversation, with a `because`) and `dlv-1`
/// (its run's material). Kept: `ent-1`, `ent-3`, `opr-2`, and a row after each erased one.
fn build(name: &str, how: Build) -> std::path::PathBuf {
    let root = scratch_brain(name);
    let db = writer(&root);
    db.execute_batch(ERASURE).unwrap();
    let mut chain = Chainer {
        db,
        heads: Default::default(),
    };
    chain.append("entry", entry("ent-1", "{\"text\": \"kept\"}"));
    chain.append("entry", entry("ent-2", "{\"text\": \"SECRET post\"}"));
    chain.append("entry", entry("ent-3", "{\"text\": \"other\"}"));
    chain.append(
        "operational",
        act("opr-1", "posted", "cnv-1", Some("SECRET why"), "{\"x\": 1}"),
    );
    chain.append("operational", act("opr-2", "posted", "cnv-2", None, "{}"));
    chain.append(
        "delivery",
        delivered("dlv-1", "cnv-1", "{\"m\": \"SECRET\"}"),
    );

    // What the erasure will leave, row by row.
    let mut targets: Vec<(&str, &str, Vec<Sql>, String)> = Vec::new();
    for (table, id) in [
        ("entry", "ent-2"),
        ("operational", "opr-1"),
        ("delivery", "dlv-1"),
    ] {
        let (mut fields, hash) = chain.row(table, id);
        let names = how
            .marker_names
            .filter(|_| id == "ent-2")
            .unwrap_or(DELETION);
        match table {
            "entry" => fields[4] = text(&marker(names)),
            "operational" => {
                fields[11] = text(&marker(names));
                fields[8] = Sql::Null;
            }
            _ => fields[7] = text(&marker(names)),
        }
        targets.push((table, id, fields, hash));
    }
    let mut lines: Vec<(String, String, String, String)> = targets
        .iter()
        .map(|(table, id, fields, hash)| {
            (
                table.to_string(),
                id.to_string(),
                hash.clone(),
                sha256_hex(&material(table, fields)),
            )
        })
        .collect();
    if how.ghost {
        lines.push((
            "entry".into(),
            "ent-ghost".into(),
            "f".repeat(64),
            "e".repeat(64),
        ));
    }
    let digest = erasure_digest(
        lines
            .iter()
            .map(|(a, b, c, d)| (a.as_str(), b.as_str(), c.as_str(), d.as_str())),
    );
    let detail = format!(
        "{{\"erasure\": {{\"digest\": \"{}\", \"rows\": {}}}, \"impact\": {{\"posts\": 1}}}}",
        how.digest.map(str::to_string).unwrap_or(digest),
        how.rows.unwrap_or(lines.len() as u64)
    );
    if !how.no_act {
        chain.append(
            "operational",
            act(DELETION, "conversation-deleted", "cnv-1", None, &detail),
        );
    }
    // Rows after the erased ones, so the chain must carry on from their stored hashes.
    chain.append("entry", entry("ent-4", "{\"text\": \"later\"}"));
    chain.append("operational", act("opr-3", "posted", "cnv-2", None, "{}"));
    chain.append("delivery", delivered("dlv-2", "cnv-2", "{}"));

    for (table, id, hash, residual) in &lines {
        chain
            .db
            .execute(
                "INSERT INTO erasure (deletion, tbl, row_id, row_hash, residual) \
                 VALUES (?1, ?2, ?3, ?4, ?5)",
                [DELETION, table, id, hash, residual],
            )
            .unwrap();
    }
    for (table, id, fields, _) in &targets {
        if how.not_erased == Some(*id) {
            continue;
        }
        let column = match *table {
            "entry" => "body",
            "operational" => "detail",
            _ => "material",
        };
        let index = columns(table).iter().position(|c| *c == column).unwrap();
        let nulled = if *table == "operational" {
            ", because = NULL"
        } else {
            ""
        };
        chain
            .db
            .execute(
                &format!("UPDATE {table} SET {column} = ?1{nulled} WHERE id = ?2"),
                [fields[index].clone(), text(id)],
            )
            .unwrap();
    }
    root
}

fn verify(root: &std::path::Path) -> ChainReport {
    let reader = Brain::open(root).unwrap();
    Chains.verify_report(&reader).unwrap()
}

fn seq_of(root: &std::path::Path, table: &str, id: &str) -> u64 {
    writer(root)
        .query_row(
            &format!("SELECT seq FROM {table} WHERE id = ?1"),
            [id],
            |r| r.get::<_, i64>(0),
        )
        .unwrap() as u64
}

fn breaks(report: &ChainReport) -> Vec<(&str, Option<u64>)> {
    report
        .tables
        .iter()
        .map(|t| (t.table, t.broke_at_seq))
        .collect()
}

fn done(root: std::path::PathBuf) {
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn a_brain_without_the_erasure_table_verifies_as_before() {
    let root = scratch_brain("no-erasure");
    let mut chain = Chainer {
        db: writer(&root),
        heads: Default::default(),
    };
    let head = chain.append("entry", entry("ent-1", "{}"));
    let report = verify(&root);
    assert!(report.intact());
    assert_eq!(report.tables[0].head.as_deref(), Some(head.as_str()));
    assert_eq!(report.tables[0].erased, 0);
    assert_eq!(report.erasures, Default::default());
    done(root);
}

#[test]
fn intact_after_erasure() {
    let root = build("intact", Build::default());
    let report = verify(&root);
    assert!(report.intact(), "{report:?}");
    let erased: Vec<u64> = report.tables.iter().map(|t| t.erased).collect();
    assert_eq!(erased, [1, 1, 1]);
    assert_eq!(report.erasures.acts, 1);
    assert_eq!(report.erasures.rows, 3);
    assert_eq!(report.erasures.pending, 0);
    assert_eq!(report.erasures.broken, None);
    // The heads are the last rows' hashes, chained through the erased rows' stored hashes.
    let db = writer(&root);
    for t in &report.tables {
        let head: String = db
            .query_row(
                &format!("SELECT hash FROM {} ORDER BY seq DESC LIMIT 1", t.table),
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(t.head.as_deref(), Some(head.as_str()), "{}", t.table);
    }
    // And no secret is left in any row.
    for table in ["entry", "operational", "delivery"] {
        let left: i64 = db
            .query_row(
                &format!(
                    "SELECT COUNT(*) FROM {table} WHERE {} LIKE '%SECRET%'",
                    match table {
                        "entry" => "body",
                        "operational" => "COALESCE(detail,'') || COALESCE(because,'')",
                        _ => "material",
                    }
                ),
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(left, 0, "{table}");
    }
    drop(db);
    done(root);
}

#[test]
fn an_erasure_not_carried_out_is_pending_not_a_break() {
    let root = build(
        "pending",
        Build {
            not_erased: Some("dlv-1"),
            ..Default::default()
        },
    );
    let report = verify(&root);
    assert!(report.intact(), "{report:?}");
    let erased: Vec<u64> = report.tables.iter().map(|t| t.erased).collect();
    assert_eq!(erased, [1, 1, 0]);
    assert_eq!(report.erasures.rows, 3);
    assert_eq!(report.erasures.pending, 1);
    done(root);
}

#[test]
fn a_changed_structural_column_of_an_erased_row_breaks() {
    let root = build("structural", Build::default());
    writer(&root)
        .execute(
            "UPDATE entry SET attributed_to = 'mallory' WHERE id = 'ent-2'",
            [],
        )
        .unwrap();
    let report = verify(&root);
    assert!(!report.intact());
    let at = seq_of(&root, "entry", "ent-2");
    assert_eq!(
        breaks(&report),
        [
            ("entry", Some(at)),
            ("operational", None),
            ("delivery", None)
        ]
    );
    // An erased act's skeleton is covered as well.
    let root2 = build("structural-act", Build::default());
    writer(&root2)
        .execute(
            "UPDATE operational SET actor = 'mallory' WHERE id = 'opr-1'",
            [],
        )
        .unwrap();
    let report = verify(&root2);
    assert_eq!(
        breaks(&report)[1],
        ("operational", Some(seq_of(&root2, "operational", "opr-1")))
    );
    done(root);
    done(root2);
}

#[test]
fn content_put_back_or_changed_after_erasure_breaks() {
    let root = build("content", Build::default());
    writer(&root)
        .execute(
            "UPDATE delivery SET material = '{\"m\": \"forged\"}' WHERE id = 'dlv-1'",
            [],
        )
        .unwrap();
    let report = verify(&root);
    assert_eq!(
        breaks(&report)[2],
        ("delivery", Some(seq_of(&root, "delivery", "dlv-1")))
    );
    // A `because` written back onto an erased act.
    let root2 = build("because", Build::default());
    writer(&root2)
        .execute(
            "UPDATE operational SET because = 'x' WHERE id = 'opr-1'",
            [],
        )
        .unwrap();
    assert_eq!(
        breaks(&verify(&root2))[1],
        ("operational", Some(seq_of(&root2, "operational", "opr-1")))
    );
    done(root);
    done(root2);
}

#[test]
fn a_tampered_erasure_row_breaks() {
    let root = build("tampered-erasure", Build::default());
    writer(&root)
        .execute(
            "UPDATE erasure SET residual = ?1 WHERE row_id = 'ent-2'",
            ["0".repeat(64)],
        )
        .unwrap();
    let report = verify(&root);
    assert!(!report.intact());
    assert_eq!(
        breaks(&report)[0],
        ("entry", Some(seq_of(&root, "entry", "ent-2")))
    );
    let broken = report
        .erasures
        .broken
        .expect("the act's digest no longer matches");
    assert_eq!(broken.deletion, DELETION);
    assert!(broken.why.contains("digest"), "{}", broken.why);

    // A row_hash moved onto another row's hash.
    let root2 = build("tampered-hash", Build::default());
    writer(&root2)
        .execute(
            "UPDATE erasure SET row_hash = ?1 WHERE row_id = 'dlv-1'",
            ["a".repeat(64)],
        )
        .unwrap();
    let report = verify(&root2);
    assert_eq!(
        breaks(&report)[2],
        ("delivery", Some(seq_of(&root2, "delivery", "dlv-1")))
    );
    assert!(report.erasures.broken.is_some());

    // An erasure row removed: its row no longer accounts for itself, nor the act's count.
    let root3 = build("removed-erasure", Build::default());
    writer(&root3)
        .execute("DELETE FROM erasure WHERE row_id = 'opr-1'", [])
        .unwrap();
    let report = verify(&root3);
    assert_eq!(
        breaks(&report)[1],
        ("operational", Some(seq_of(&root3, "operational", "opr-1")))
    );
    assert!(report.erasures.broken.unwrap().why.contains("count"));
    done(root);
    done(root2);
    done(root3);
}

#[test]
fn a_wrong_digest_or_count_in_the_act_breaks() {
    let root = build(
        "wrong-digest",
        Build {
            digest: Some("0000000000000000000000000000000000000000000000000000000000000000"),
            ..Default::default()
        },
    );
    let report = verify(&root);
    assert!(!report.intact());
    // Every row verifies: only the act does not account for them.
    assert_eq!(
        breaks(&report),
        [("entry", None), ("operational", None), ("delivery", None)]
    );
    let broken = report.erasures.broken.unwrap();
    assert_eq!((broken.deletion.as_str(), broken.row), (DELETION, None));
    assert!(broken.why.contains("digest"));

    let root2 = build(
        "wrong-count",
        Build {
            rows: Some(2),
            ..Default::default()
        },
    );
    let report = verify(&root2);
    assert!(!report.intact());
    assert!(report.erasures.broken.unwrap().why.contains("count"));
    done(root);
    done(root2);
}

#[test]
fn a_missing_act_breaks() {
    let root = build(
        "no-act",
        Build {
            no_act: true,
            ..Default::default()
        },
    );
    let report = verify(&root);
    assert!(!report.intact());
    // The erased rows are not accepted without the act that attests them.
    assert_eq!(
        breaks(&report)[0],
        ("entry", Some(seq_of(&root, "entry", "ent-2")))
    );
    assert_eq!(report.erasures.acts, 0);
    let broken = report.erasures.broken.unwrap();
    assert_eq!(broken.deletion, DELETION);
    assert!(broken.why.contains("not in the record"), "{}", broken.why);

    // The act removed from under the chain afterwards.
    let root2 = build("act-removed", Build::default());
    writer(&root2)
        .execute("DELETE FROM operational WHERE id = ?1", [DELETION])
        .unwrap();
    let report = verify(&root2);
    assert!(!report.intact());
    assert!(report.erasures.broken.is_some());
    done(root);
    done(root2);
}

#[test]
fn a_marker_naming_another_act_breaks() {
    let root = build(
        "wrong-marker",
        Build {
            marker_names: Some("opr-someoneelse"),
            ..Default::default()
        },
    );
    let report = verify(&root);
    assert!(!report.intact());
    assert_eq!(
        breaks(&report),
        [
            ("entry", Some(seq_of(&root, "entry", "ent-2"))),
            ("operational", None),
            ("delivery", None)
        ]
    );
    done(root);
}

#[test]
fn an_erasure_row_for_a_row_that_is_not_there_breaks() {
    let root = build(
        "ghost",
        Build {
            ghost: true,
            ..Default::default()
        },
    );
    let report = verify(&root);
    assert!(!report.intact());
    assert_eq!(
        breaks(&report),
        [("entry", None), ("operational", None), ("delivery", None)]
    );
    let broken = report.erasures.broken.unwrap();
    assert_eq!(broken.row, Some(("entry".into(), "ent-ghost".into())));
    assert!(broken.why.contains("does not exist"));
    done(root);
}
