//! Where the front meets `mentis-record`, written to the traits alone.
//!
//! **P1.1's implementation meets this package at two lines, [`Opener`] and [`verifier`].** Everything
//! else takes a [`BrainOpener`], a [`RecordReader`] or a [`ChainVerifier`], so changing those is all
//! the integration needs.

use std::path::Path;
use std::sync::Arc;

use mentis_record::{
    BrainOpener, CORPUS_DB, ChainVerifier, OpenRefused, ReadClass, ReadScope, RecordError,
    RecordReader, TableChain,
};

/// The opener this binary uses. P1.1's replaces [`NotYetOpened`] here at integration.
pub type Opener = NotYetOpened;

/// The verifier `--verify-chains` uses. P1.1's replaces [`NotYetOpened`] here at integration.
pub fn verifier() -> impl ChainVerifier {
    NotYetOpened
}

/// Open the Brain, or say why not. The reader holds `.mentis.lock` shared for as long as it lives.
pub fn open<O: BrainOpener>(root: &Path) -> Result<Arc<dyn RecordReader>, OpenRefused> {
    Ok(Arc::new(O::open(root)?))
}

/// Stands in until P1.1 is merged, and is removed then. It takes no lock and opens nothing, so
/// nothing can read through it: a front on this reader forwards and serves files only.
#[derive(Debug)]
pub struct NotYetOpened;

impl BrainOpener for NotYetOpened {
    type Reader = NotYetOpened;

    fn open(root: &Path) -> Result<NotYetOpened, OpenRefused> {
        if root.join(CORPUS_DB).is_file() {
            Ok(NotYetOpened)
        } else {
            Err(OpenRefused::Missing {
                root: root.display().to_string(),
            })
        }
    }
}

impl ChainVerifier for NotYetOpened {
    fn verify_chains(&self, _reader: &dyn RecordReader) -> Result<Vec<TableChain>, RecordError> {
        Err(RecordError::Sqlite {
            detail: "this build has no chain verifier yet".into(),
        })
    }
}

impl RecordReader for NotYetOpened {
    fn read_scope(&self, _class: ReadClass) -> Result<Box<dyn ReadScope>, RecordError> {
        Err(RecordError::Sqlite {
            detail: "this build has no record reader yet".into(),
        })
    }

    fn corpus_id(&self) -> &str {
        ""
    }
}

/// `--verify-chains <brain>`: each table's result, as JSON, field for field what
/// [`TableChain`] holds, for rows E and J15's "by both". It reads through the same opener and scopes
/// as the front, so it refuses what the front refuses.
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
