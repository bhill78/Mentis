//! What the record means. Contract: `docs/rust/contracts/ops.md`.
//!
//! `now_reads` and `names` are P1.3's, `standing_many` is R3's. Each answers facts without policy:
//! what a consumer does with a deleted entry stays that consumer's (census, `op-now`).
//!
//! **A fixed number of statements per call, not per id:** at most [`STATEMENTS`], with no memo, so
//! an answer costs the same just after a commit as before it.

pub mod body;
mod now;
pub mod permitted;
pub mod standing;

use std::collections::{HashMap, HashSet};

pub use now::{Entry, id_list};

use body::Field;
use mentis_record::{Id, ReadScope, RecordError};

pub use standing::{IncomingLinks, standing_many};

/// The most statements [`now_reads`], [`name_reads`] or [`reads`] runs in one call, the scope's
/// position apart: the entries asked about, the superseding relation, the links along their lines,
/// and the entries those links name.
pub const STATEMENTS: u32 = 4;

/// The most statements [`now_reads_walking_only_what_changed`] runs in one call.
pub const CHANGED_STATEMENTS: u32 = 2 + STATEMENTS;

/// The statements [`standing_many`] runs in one call, for any number of ids.
pub const STANDING_STATEMENTS: u32 = 1;

/// The statements [`roots`] runs in one call: the superseding relation and the links.
pub const ROOTS_STATEMENTS: u32 = 2;

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
    /// `presented` raises on this entry, or reads it some way this can't say: a deleted body or a
    /// deletion's body that is true to Python and not an object, or a reason that isn't text. So
    /// `body_json` is empty and nothing is known of it here. A route forwards, and the answer,
    /// Python's 500 included, is Python's own.
    pub python_says: bool,
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

/// The rules this release has.
#[derive(Clone, Copy, Debug, Default)]
pub struct RecordRules;

/// What a name is, for a route that has to say exactly what Python would.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum NameRead {
    /// `body.get("name") or body.get("alias")`, as text.
    Named(String),
    /// Held, with neither. Python shows the id.
    Unnamed,
    /// A name that is not text, or a body that can't be read here. What it shows as is Python's
    /// to say, so a route forwards it.
    NotPlain,
}

fn name_read(body_json: &str) -> NameRead {
    match body::fields(body_json, &["name", "alias"]).as_deref() {
        Some([Field::Text(name), _]) | Some([Field::Nothing, Field::Text(name)]) => {
            NameRead::Named(name.clone())
        }
        Some([Field::Nothing, Field::Nothing]) => NameRead::Unnamed,
        _ => NameRead::NotPlain,
    }
}

/// As each id now reads: what [`Rules::now_reads`] answers.
pub fn now_reads(
    scope: &mut dyn ReadScope,
    ids: &[Id],
) -> Result<HashMap<Id, Reading>, RecordError> {
    let (held, lines) = load(scope, ids, |_| true)?;
    let mut out = HashMap::with_capacity(ids.len());
    for id in ids {
        if let Some(entry) = held.0.get(&id.0) {
            out.insert(id.clone(), now::presented(entry, &lines, &held));
        }
    }
    Ok(out)
}

/// [`now_reads`], the same answers, for a read of many entries few of which ever changed: `_now_reads`,
/// `fluid/read.py:252`. It asks once which of them anything supersedes, and only those pay for
/// [`LINE_LINKS`]'s walk, whose recursive statement costs tens of milliseconds on a real Brain however
/// few ids it's given. At most [`CHANGED_STATEMENTS`].
pub fn now_reads_walking_only_what_changed(
    scope: &mut dyn ReadScope,
    ids: &[Id],
) -> Result<HashMap<Id, Reading>, RecordError> {
    let mut out = HashMap::with_capacity(ids.len());
    if ids.is_empty() {
        return Ok(out);
    }
    let list = now::id_list(ids.iter().map(|id| id.0.as_str()));
    let mut held = now::Held::default();
    held.read(scope, &list)?;
    let touched = now::touched(scope, &list)?;
    let mut walking = Vec::new();
    for id in ids {
        if touched.contains(&id.0) {
            walking.push(id.clone());
        } else if let Some(entry) = held.0.get(&id.0) {
            out.insert(id.clone(), entry.as_it_is());
        }
    }
    out.extend(now_reads(scope, &walking)?);
    Ok(out)
}

/// `_names`, `fluid/read.py:194`: a Conversation or a Participant under its current version, and
/// anything else as its own body says. An id the record does not hold is absent.
pub fn name_reads(
    scope: &mut dyn ReadScope,
    ids: &[Id],
) -> Result<HashMap<Id, NameRead>, RecordError> {
    let (held, lines) = load(scope, ids, now::Entry::is_named_by_version)?;
    let mut out = HashMap::with_capacity(ids.len());
    for id in ids {
        let Some(entry) = held.0.get(&id.0) else {
            continue;
        };
        let read = if entry.is_named_by_version() {
            name_read(&now::presented(entry, &lines, &held).body_json)
        } else {
            name_read(&entry.body_json)
        };
        out.insert(id.clone(), read);
    }
    Ok(out)
}

/// A line's versions, read forward from the entry asked about: `versions.lineage`, and the first of
/// `Corpus.history`, which a later version needs to name its post.
#[derive(Clone, Debug)]
pub struct Line {
    pub root: String,
    pub versions: Vec<Entry>,
    pub deletion: Option<Entry>,
}

/// `objects._lines`: each id the record holds, its line. An entry nothing superseded is its own only
/// version. At most [`STATEMENTS`].
pub fn lines_of(scope: &mut dyn ReadScope, ids: &[Id]) -> Result<HashMap<Id, Line>, RecordError> {
    let (held, lines) = load(scope, ids, |_| true)?;
    let mut out = HashMap::with_capacity(ids.len());
    for id in ids {
        let Some(entry) = held.0.get(&id.0) else {
            continue;
        };
        let root = lines
            .history(&id.0)
            .into_iter()
            .next()
            .unwrap_or_else(|| id.0.clone());
        let line = if lines.is_touched(&id.0) {
            let (versions, deletion) = now::lineage(entry, &lines, &held);
            Line {
                root,
                versions: versions.into_iter().cloned().collect(),
                deletion: deletion.cloned(),
            }
        } else {
            Line {
                root,
                versions: vec![entry.clone()],
                deletion: None,
            }
        };
        out.insert(id.clone(), line);
    }
    Ok(out)
}

/// Which entries [`reads`] reads under their current version, as each read in Python does. Every
/// other entry reads as its own row.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Versioned {
    /// `Conversations.alias`.
    Participants,
    /// `register.governed`'s `named`, and `_names`.
    ConversationsAndParticipants,
    /// `presented` of everything.
    All,
}

/// An entry as a read saw it: its Kind beside how it reads.
#[derive(Clone, Debug, PartialEq)]
pub struct Seen {
    pub kind: Option<String>,
    pub reading: Reading,
}

/// How each id reads under `versioned`. An id the record does not hold is absent.
pub fn reads(
    scope: &mut dyn ReadScope,
    ids: &[Id],
    versioned: Versioned,
) -> Result<HashMap<Id, Seen>, RecordError> {
    let walked = |entry: &now::Entry| match versioned {
        Versioned::Participants => entry.is_participant(),
        Versioned::ConversationsAndParticipants => entry.is_named_by_version(),
        Versioned::All => true,
    };
    let (held, lines) = load(scope, ids, walked)?;
    let mut out = HashMap::with_capacity(ids.len());
    for id in ids {
        if let Some(entry) = held.0.get(&id.0) {
            let reading = if walked(entry) {
                now::presented(entry, &lines, &held)
            } else {
                entry.as_it_is()
            };
            let kind = entry.kind.clone();
            out.insert(id.clone(), Seen { kind, reading });
        }
    }
    Ok(out)
}

/// Which of these links something has ended: what `_in_force` leaves out, in two statements for the
/// set rather than a `stands` for each.
pub fn ended(scope: &mut dyn ReadScope, ids: &[&str]) -> Result<HashSet<String>, RecordError> {
    if ids.is_empty() {
        return Ok(HashSet::new());
    }
    let lines = now::Lines::load(scope, &id_list(ids.iter().copied()))?;
    Ok(ids
        .iter()
        .filter(|id| lines.is_touched(id) && !lines.superseded_by(id).is_empty())
        .map(|id| (*id).to_owned())
        .collect())
}

/// `Conversations.alias`, for many: a Participant's current alias, or anything else's own `alias`
/// field. `Some(None)` is the id shown as itself, as for one the record doesn't hold; `None` beside an
/// id is a body this can't read, for a route to forward. At most [`STATEMENTS`].
pub fn alias_reads(
    scope: &mut dyn ReadScope,
    ids: &[Id],
) -> Result<HashMap<Id, Option<Option<String>>>, RecordError> {
    let (held, lines) = load(scope, ids, now::Entry::is_participant_row)?;
    let mut out = HashMap::with_capacity(ids.len());
    for id in ids {
        let read = match held.0.get(&id.0) {
            None => Some(None),
            Some(entry) => {
                let presented;
                let body_json = if entry.is_participant_row() {
                    presented = now::presented(entry, &lines, &held);
                    &presented.body_json
                } else {
                    &entry.body_json
                };
                match body::fields(body_json, &["alias"]).as_deref() {
                    Some([Field::Text(alias)]) => Some(Some(alias.clone())),
                    Some(_) => Some(None),
                    None => None,
                }
            }
        };
        out.insert(id.clone(), read);
    }
    Ok(out)
}

/// What `Conversations.alias` answers: the name a Participant is shown by, and any other reference
/// as itself. `None` where Python raises or reads something this can't say, so a route forwards.
pub fn alias_of(seen: Option<&Seen>, id: &Id) -> Option<String> {
    let Some(seen) = seen else {
        return Some(id.0.clone());
    };
    if seen.reading.python_says {
        return None;
    }
    match body::fields(&seen.reading.body_json, &["alias"])?.pop()? {
        Field::Text(alias) => Some(alias),
        Field::Nothing | Field::NotText => Some(id.0.clone()),
    }
}

/// `corpus.history(id)[0]`: the oldest entry of each id's line, or the id itself when it has none.
/// [`ROOTS_STATEMENTS`], or none for no ids.
pub fn roots(scope: &mut dyn ReadScope, ids: &[Id]) -> Result<HashMap<Id, Id>, RecordError> {
    if ids.is_empty() {
        return Ok(HashMap::new());
    }
    let asked = now::id_list(ids.iter().map(|id| id.0.as_str()));
    let lines = now::Lines::load(scope, &asked)?;
    Ok(ids
        .iter()
        .map(|id| {
            let oldest = lines.history(&id.0).swap_remove(0);
            (id.clone(), Id(oldest))
        })
        .collect())
}

/// The entries, then the lines of those `walked` says read under their current version.
fn load(
    scope: &mut dyn ReadScope,
    ids: &[Id],
    walked: impl Fn(&now::Entry) -> bool,
) -> Result<(now::Held, now::Lines), RecordError> {
    let mut held = now::Held::default();
    if ids.is_empty() {
        return Ok((held, now::Lines::default()));
    }
    held.read(scope, &now::id_list(ids.iter().map(|id| id.0.as_str())))?;
    let walking: Vec<&str> = held
        .0
        .values()
        .filter(|entry| walked(entry))
        .map(|entry| entry.id.as_str())
        .collect();
    if walking.is_empty() {
        return Ok((held, now::Lines::default()));
    }
    let lines = now::Lines::load(scope, &now::id_list(walking))?;
    let more = now::id_list(lines.named_entries(&held));
    if more != "[]" {
        held.read(scope, &more)?;
    }
    Ok((held, lines))
}

impl Rules for RecordRules {
    fn now_reads(
        &self,
        scope: &mut dyn ReadScope,
        ids: &[Id],
    ) -> Result<HashMap<Id, Reading>, RecordError> {
        now_reads(scope, ids)
    }

    /// A name that is not text reads as none here. [`name_reads`] tells it apart, for a route.
    fn names(
        &self,
        scope: &mut dyn ReadScope,
        ids: &[Id],
    ) -> Result<HashMap<Id, Option<String>>, RecordError> {
        Ok(name_reads(scope, ids)?
            .into_iter()
            .map(|(id, read)| match read {
                NameRead::Named(name) => (id, Some(name)),
                NameRead::Unnamed | NameRead::NotPlain => (id, None),
            })
            .collect())
    }

    fn standing_many(
        &self,
        scope: &mut dyn ReadScope,
        ids: &[Id],
        as_at: Option<f64>,
    ) -> Result<HashMap<Id, Standing>, RecordError> {
        standing_many(scope, ids, as_at)
    }
}
