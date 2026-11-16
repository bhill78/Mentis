//! Where the front meets `mentis-record`, written to the traits alone but for the two lines that name
//! its implementation: [`Opener`] and [`verifier`].

use std::path::Path;
use std::sync::Arc;

use mentis_record::{
    Brain, BrainOpener, ChainReport, ChainVerifier, Chains, ErasureBroken, OpenRefused,
    RecordReader,
};

/// The opener this binary uses.
pub type Opener = Brain;

/// The verifier `--verify-chains` uses.
pub fn verifier() -> impl ChainVerifier {
    Chains
}

/// Open the Brain, or say why not. The reader holds `.mentis.lock` shared for as long as it lives.
pub fn open<O: BrainOpener>(root: &Path) -> Result<Arc<dyn RecordReader>, OpenRefused> {
    Ok(Arc::new(O::open(root)?))
}

/// `--verify-chains <brain>`: each table's result, as JSON, field for field what
/// [`mentis_record::TableChain`] holds, for rows E and J15's "by both". It reads through the same
/// opener and scopes as the front, so it refuses what the front refuses. A table's erased rows are
/// those accepted as attested erasures; whether the erasures account for themselves is
/// `--verify-record`'s.
pub fn verify_chains_report<O: BrainOpener, V: ChainVerifier>(
    root: &Path,
    verifier: &V,
) -> Result<String, String> {
    let reader = O::open(root).map_err(|why| why.to_string())?;
    let report = verifier
        .verify_report(&reader)
        .map_err(|why| why.to_string())?;
    let rows: Vec<serde_json::Value> = report
        .tables
        .iter()
        .map(|table| {
            serde_json::json!({
                "table": table.table,
                "rows": table.rows,
                "head": table.head,
                "broke_at_seq": table.broke_at_seq,
                "erased": table.erased,
            })
        })
        .collect();
    Ok(serde_json::Value::Array(rows).to_string())
}

/// `--verify-record <brain>`: the whole verify in the shape of Python's `Store.verify_chain`:
/// `intact`, each stream, and the erasures (`erasure-design.md` 1.4).
pub fn verify_record_report<O: BrainOpener, V: ChainVerifier>(
    root: &Path,
    verifier: &V,
) -> Result<String, String> {
    let reader = O::open(root).map_err(|why| why.to_string())?;
    let report = verifier
        .verify_report(&reader)
        .map_err(|why| why.to_string())?;
    Ok(record_report_json(&report).to_string())
}

/// [`verify_record_report`]'s JSON: Python's `Store.verify_chain`, field for field.
pub fn record_report_json(report: &ChainReport) -> serde_json::Value {
    let mut streams = serde_json::Map::new();
    for table in &report.tables {
        streams.insert(
            table.table.to_string(),
            serde_json::json!({
                "rows": table.rows,
                "chained": table.chained,
                "before_the_chain": table.before_the_chain,
                "head": table.head,
                "broken_at": table.broken_at.as_ref().map(|b| serde_json::json!({
                    "seq": b.seq, "id": b.id, "why": b.why,
                })),
                "erased": table.erased,
            }),
        );
    }
    let erasures = &report.erasures;
    let broken = erasures.broken.as_ref().map(|broken| match broken {
        ErasureBroken::Act { deletion, why } => {
            serde_json::json!({"deletion": deletion, "why": why})
        }
        ErasureBroken::Row { table, id, why } => {
            serde_json::json!({"table": table, "id": id, "why": why})
        }
    });
    serde_json::json!({
        "intact": report.intact(),
        "streams": streams,
        "erasures": {
            "acts": erasures.acts,
            "rows": erasures.rows,
            "pending": erasures.pending,
            "broken": broken,
        },
        "chained_from_first_row": report.chained_from_first_row,
    })
}
