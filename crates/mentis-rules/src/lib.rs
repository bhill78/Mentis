//! What the record means. Contract: `docs/rust/contracts/ops.md`.
//!
//! Signatures only until the packages that fill them: `now_reads` and `names` are P1.3's,
//! `standing_many` is R3's. Each answers facts without policy: what a consumer does with a deleted
//! entry stays that consumer's (census, `op-now`).
//!
//! **A fixed number of statements per call, not per id.** Walking a chain only for touched ids
//! stays allowed. A memo may not be needed to meet that.

use std::collections::HashMap;

use mentis_record::{Id, ReadScope, RecordError};

/// How an entry now reads: `presented`, `conversation/versions.py:266`, without the entry's other
/// columns. `Id`s the record does not hold are absent from the answer.
#[derive(Clone, Debug, PartialEq)]
pub struct Reading {
    /// Identity does not move with a version.
    pub root: Id,
    /// The current version's body, as the JSON text the record stores. Blanked by the same rule
    /// as `_blank` when the line ends in a deletion.
    pub body_json: String,
    pub revision: Option<Revision>,
    pub deleted: Option<Deleted>,
}

/// `presented`'s `revision`. Present only when there is more than one version.
#[derive(Clone, Debug, PartialEq)]
pub struct Revision {
    pub versions: u32,
    pub current: Id,
    /// The current version's `recorded_at`, seconds as stored.
    pub edited_at: f64,
    pub edited_by: Option<Id>,
}

/// `presented`'s `deleted`: the deletion's own record.
#[derive(Clone, Debug, PartialEq)]
pub struct Deleted {
    pub record: Id,
    pub at: f64,
    pub by: Option<Id>,
    /// The deletion's stated reason. Empty counts as none, as in Python.
    pub because: Option<String>,
}

/// What the record says about an entry: `Corpus.stands`, `spine/seam.py:877`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Standing {
    pub entry: Id,
    pub stands: bool,
    /// Sorted, as `stands` sorts them.
    pub established_by: Vec<Id>,
    pub superseded_by: Vec<Id>,
    /// Incoming links of every other relation, by relation, each sorted.
    pub incoming: Vec<(String, Vec<Id>)>,
}

/// The rules, against one scope. A check before a write reads through the writer, which is not
/// here: these are for scopes that cannot write.
pub trait Rules {
    /// As it now reads, for each id the record holds.
    fn now_reads(
        &self,
        scope: &mut dyn ReadScope,
        ids: &[Id],
    ) -> Result<HashMap<Id, Reading>, RecordError>;

    /// The current name of each Conversation, Topic or Participant asked about. A held id with no
    /// name is `None`; an id the record does not hold is absent. The route decides how each shows
    /// (census, `op-names`).
    fn names(
        &self,
        scope: &mut dyn ReadScope,
        ids: &[Id],
    ) -> Result<HashMap<Id, Option<String>>, RecordError>;

    /// Standing now, or as at a recorded time (`as_at`, seconds as `recorded_at` holds them).
    fn standing_many(
        &self,
        scope: &mut dyn ReadScope,
        ids: &[Id],
        as_at: Option<f64>,
    ) -> Result<HashMap<Id, Standing>, RecordError>;
}
