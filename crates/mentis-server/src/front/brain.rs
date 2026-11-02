//! Where the front meets `mentis-record`, written to the traits alone but for the two lines that name
//! its implementation: [`Opener`] and [`verifier`].

use std::path::Path;
use std::sync::Arc;

use mentis_record::{Brain, BrainOpener, ChainVerifier, Chains, OpenRefused, RecordReader};

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
/// opener and scopes as the front, so it refuses what the front refuses.
pub fn verify_chains_report<O: BrainOpener, V: ChainVerifier>(
    root: &Path,
    verifier: &V,
) -> Result<String, String> {
    let reader = O::open(root).map_err(|why| why.to_string())?;
    let tables = verifier
        .verify_chains(&reader)
        .map_err(|why| why.to_string())?;
    let rows: Vec<serde_json::Value> = tables
        .iter()
        .map(|table| {
            serde_json::json!({
                "table": table.table,
                "rows": table.rows,
                "head": table.head,
                "broke_at_seq": table.broke_at_seq,
            })
        })
        .collect();
    Ok(serde_json::Value::Array(rows).to_string())
}
