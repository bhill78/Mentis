//! Where the front meets `mentis-record`, written to the traits alone.
//!
//! **P1.1's implementation meets this package at one line, [`Opener`].** Everything else takes a
//! [`BrainOpener`] or a [`RecordReader`], so changing that line is all the integration needs.

use std::path::Path;
use std::sync::Arc;

use mentis_record::{
    BrainOpener, CORPUS_DB, OpenRefused, ReadClass, ReadScope, RecordError, RecordReader,
};

/// The opener this binary uses. P1.1's replaces [`NotYetOpened`] here at integration.
pub type Opener = NotYetOpened;

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
