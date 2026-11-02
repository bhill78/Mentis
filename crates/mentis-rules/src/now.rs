//! How entries now read: `presented`, `lineage` and `deletion_of` (`conversation/versions.py`), over
//! `Corpus.history` and `_superseded` (`spine/seam.py:1006`, `:858`).
//!
//! **The statements are fixed per call.** Everything the walks need is read first, all at once: the
//! entries, then every superseding link reachable from them in one recursive statement, then the
//! entries those links name. The walks then run in memory, in Python's order, so where a line forks
//! or a link was itself superseded the same branch is taken.

use std::collections::{HashMap, HashSet};

use mentis_record::{Flow, Id, Param, ReadScope, RecordError, Row, Value};

use crate::{Deleted, Reading, Revision, body};

/// `Corpus.superseding_relation`: the first definition carrying the role, from the data.
const SUPERSEDING_RELATION: &str = "SELECT json_extract(body, '$.relation') FROM entry \
     WHERE family = 'definition' AND json_extract(body, '$.substrate_role') = 'supersedes' \
     ORDER BY seq LIMIT 1";

/// Every link `_role` calls superseding that is reachable from `?1`, either way along the line, or
/// that supersedes such a link. `_role` reads the definition of the link's own relation version, the
/// first of them if there were two.
const LINE_LINKS: &str = "WITH RECURSIVE \
     roles(relation, version) AS ( \
       SELECT d.def_name, d.def_version FROM entry d \
       WHERE d.family = 'definition' \
         AND json_extract(d.body, '$.substrate_role') = 'supersedes' \
         AND d.seq = (SELECT MIN(x.seq) FROM entry x WHERE x.family = 'definition' \
                      AND x.def_name = d.def_name AND x.def_version = d.def_version)), \
     reach(id) AS ( \
       SELECT value FROM json_each(?1) \
       UNION SELECT l.id FROM reach r JOIN entry l ON l.link_to = r.id \
         WHERE (l.link_relation, l.link_relation_version) IN (SELECT relation, version FROM roles) \
       UNION SELECT l.link_from FROM reach r JOIN entry l ON l.link_to = r.id \
         WHERE (l.link_relation, l.link_relation_version) IN (SELECT relation, version FROM roles) \
       UNION SELECT l.id FROM reach r JOIN entry l ON l.link_from = r.id \
         WHERE (l.link_relation, l.link_relation_version) IN (SELECT relation, version FROM roles) \
       UNION SELECT l.link_to FROM reach r JOIN entry l ON l.link_from = r.id \
         WHERE (l.link_relation, l.link_relation_version) IN (SELECT relation, version FROM roles)) \
     SELECT l.id, l.link_from, l.link_to, l.link_relation \
     FROM reach r JOIN entry l ON l.id = r.id \
     WHERE (l.link_relation, l.link_relation_version) IN (SELECT relation, version FROM roles) \
     ORDER BY l.seq";

const ENTRIES: &str = "SELECT id, family, def_name, body, attributed_to, recorded_at, link_relation \
     FROM entry WHERE id IN (SELECT value FROM json_each(?1)) ORDER BY seq";

/// A list of ids as the one parameter `json_each` reads.
pub fn id_list<'a>(ids: impl IntoIterator<Item = &'a str>) -> String {
    let ids: Vec<&str> = ids.into_iter().collect();
    serde_json::to_string(&ids).expect("a list of strings is always JSON")
}

fn owned_text(row: &dyn Row, column: usize) -> Result<Option<String>, RecordError> {
    match row.value(column)? {
        Value::Null => Ok(None),
        Value::Text(bytes) => match std::str::from_utf8(bytes) {
            Ok(text) => Ok(Some(text.to_owned())),
            Err(_) => Err(RecordError::Sqlite {
                detail: format!("column {column} is not UTF-8"),
            }),
        },
        _ => Err(RecordError::Sqlite {
            detail: format!("column {column} is not text"),
        }),
    }
}

/// One entry, as far as these rules read it.
#[derive(Clone, Debug)]
pub struct Entry {
    pub id: String,
    pub family: String,
    pub kind: Option<String>,
    pub body_json: String,
    pub attributed_to: Option<String>,
    pub recorded_at: f64,
    pub is_link: bool,
}

impl Entry {
    /// `is_node`.
    fn is_node(&self) -> bool {
        self.family == "entry" && !self.is_link
    }

    /// `is_deletion`.
    fn is_deletion(&self) -> bool {
        self.is_node() && self.kind.as_deref() == Some("deletion")
    }

    /// `keeps_root_identity`.
    fn keeps_root_identity(&self) -> bool {
        self.is_node()
            && matches!(
                self.kind.as_deref(),
                Some("contribution" | "topic" | "conversation" | "participant")
            )
    }

    /// `_is_conversation` or `_is_participant`: what `_names` reads under its current version.
    pub fn is_named_by_version(&self) -> bool {
        self.is_node() && matches!(self.kind.as_deref(), Some("conversation" | "participant"))
    }

    /// What `Conversations.alias` reads under its current version.
    pub fn is_participant(&self) -> bool {
        self.is_node() && self.kind.as_deref() == Some("participant")
    }

    /// This entry's own row, with nothing walked.
    pub fn as_it_is(&self) -> Reading {
        Reading {
            root: Id(self.id.clone()),
            body_json: self.body_json.clone(),
            revision: None,
            deleted: None,
            python_says: false,
        }
    }
}

/// Entries, by id.
#[derive(Debug, Default)]
pub struct Held(pub HashMap<String, Entry>);

impl Held {
    /// One statement.
    pub fn read(&mut self, scope: &mut dyn ReadScope, ids: &str) -> Result<(), RecordError> {
        let held = &mut self.0;
        scope.query(ENTRIES, &[Param::Text(ids)], &mut |row| {
            let recorded_at = match row.value(5)? {
                Value::Real(at) => at,
                Value::Integer(at) => at as f64,
                _ => 0.0,
            };
            let id = owned_text(row, 0)?.unwrap_or_default();
            held.insert(
                id.clone(),
                Entry {
                    id,
                    family: owned_text(row, 1)?.unwrap_or_default(),
                    kind: owned_text(row, 2)?,
                    body_json: owned_text(row, 3)?.unwrap_or_default(),
                    attributed_to: owned_text(row, 4)?,
                    recorded_at,
                    is_link: !matches!(row.value(6)?, Value::Null),
                },
            );
            Ok(Flow::Continue)
        })
    }
}

/// A superseding link.
#[derive(Clone, Debug)]
struct Link {
    id: String,
    from: String,
    to: String,
    relation: String,
}

/// The superseding links touching what was asked about, each list in the record's order.
#[derive(Debug, Default)]
pub struct Lines {
    /// `superseding_relation()`.
    relation: Option<String>,
    to: HashMap<String, Vec<Link>>,
    from: HashMap<String, Vec<Link>>,
    named: HashSet<String>,
}

impl Lines {
    /// Two statements.
    pub fn load(scope: &mut dyn ReadScope, ids: &str) -> Result<Lines, RecordError> {
        let mut lines = Lines::default();
        scope.query(SUPERSEDING_RELATION, &[], &mut |row| {
            lines.relation = owned_text(row, 0)?;
            Ok(Flow::Stop)
        })?;
        let (to, from, named) = (&mut lines.to, &mut lines.from, &mut lines.named);
        scope.query(LINE_LINKS, &[Param::Text(ids)], &mut |row| {
            let link = Link {
                id: owned_text(row, 0)?.unwrap_or_default(),
                from: owned_text(row, 1)?.unwrap_or_default(),
                to: owned_text(row, 2)?.unwrap_or_default(),
                relation: owned_text(row, 3)?.unwrap_or_default(),
            };
            named.insert(link.from.clone());
            named.insert(link.to.clone());
            to.entry(link.to.clone()).or_default().push(link.clone());
            from.entry(link.from.clone()).or_default().push(link);
            Ok(Flow::Continue)
        })?;
        Ok(lines)
    }

    /// The entries these links name that aren't held yet.
    pub fn named_entries<'a>(&'a self, held: &Held) -> Vec<&'a str> {
        self.named
            .iter()
            .filter(|id| !held.0.contains_key(*id))
            .map(String::as_str)
            .collect()
    }

    /// `_superseded`: is this link itself ended by a link that still counts?
    fn superseded(&self, link: &str, memo: &mut HashMap<String, bool>) -> bool {
        if let Some(known) = memo.get(link) {
            return *known;
        }
        memo.insert(link.to_owned(), false);
        for other in self.to.get(link).map_or(&[][..], Vec::as_slice) {
            if !self.superseded(&other.id, memo) {
                memo.insert(link.to_owned(), true);
                return true;
            }
        }
        false
    }

    /// The last link in this list that still counts: `found[-1]` of `history`'s `counted`.
    fn last_counted<'a>(
        &self,
        links: Option<&'a Vec<Link>>,
        memo: &mut HashMap<String, bool>,
    ) -> Option<&'a Link> {
        // `counted` asks of every link in order, so the memo fills as Python's does.
        let mut last = None;
        for link in links.map_or(&[][..], Vec::as_slice) {
            if !self.superseded(&link.id, memo) {
                last = Some(link);
            }
        }
        last
    }

    /// `Corpus.history`: the chain through this entry, oldest first.
    pub fn history(&self, entry: &str) -> Vec<String> {
        let mut memo = HashMap::new();
        let mut chain = vec![entry.to_owned()];
        let mut seen: HashSet<String> = chain.iter().cloned().collect();
        let mut current = entry.to_owned();
        while let Some(link) = self.last_counted(self.from.get(&current), &mut memo) {
            if !seen.insert(link.to.clone()) {
                break;
            }
            chain.insert(0, link.to.clone());
            current.clone_from(&link.to);
        }
        current = entry.to_owned();
        while let Some(link) = self.last_counted(self.to.get(&current), &mut memo) {
            if !seen.insert(link.from.clone()) {
                break;
            }
            chain.push(link.from.clone());
            current.clone_from(&link.from);
        }
        chain
    }

    /// `corpus.stands(entry)["superseded_by"]`.
    fn superseded_by(&self, entry: &str) -> Vec<String> {
        let mut memo = HashMap::new();
        let mut found: Vec<String> = self
            .to
            .get(entry)
            .map_or(&[][..], Vec::as_slice)
            .iter()
            .filter(|link| !self.superseded(&link.id, &mut memo))
            .map(|link| link.from.clone())
            .collect();
        found.sort();
        found
    }

    /// `corpus.links(relation=superseding_relation(), to=entry)`, which `presented` asks first.
    fn is_touched(&self, entry: &str) -> bool {
        self.to.get(entry).is_some_and(|links| {
            links
                .iter()
                .any(|link| self.relation.as_deref() == Some(&link.relation))
        })
    }
}

/// How this entry now reads: `presented`.
pub fn presented(entry: &Entry, lines: &Lines, held: &Held) -> Reading {
    let as_it_is = || entry.as_it_is();
    if !entry.is_node() || !lines.is_touched(&entry.id) {
        return as_it_is();
    }
    let (versions, deletion): (Vec<&Entry>, Option<&Entry>) = if entry.keeps_root_identity() {
        // `lineage`, read forward from this entry.
        let chain = lines.history(&entry.id);
        let at = chain
            .iter()
            .position(|id| *id == entry.id)
            .expect("the chain holds the entry it was asked about");
        let ordered: Vec<&Entry> = chain[at..].iter().filter_map(|id| held.0.get(id)).collect();
        match ordered.split_last() {
            Some((last, rest)) if !rest.is_empty() && last.is_deletion() => {
                (rest.to_vec(), Some(*last))
            }
            _ => (ordered, None),
        }
    } else {
        // `deletion_of`: only a deletion of this very entry.
        let by = lines.superseded_by(&entry.id);
        let deletion = by
            .iter()
            .find_map(|by| held.0.get(by).filter(|found| found.is_deletion()));
        match deletion {
            Some(deletion) => (vec![entry], Some(deletion)),
            None => return as_it_is(),
        }
    };
    if versions.len() <= 1 && deletion.is_none() {
        return as_it_is();
    }
    let mut reading = as_it_is();
    if versions.len() > 1 {
        let head = versions[versions.len() - 1];
        reading.body_json.clone_from(&head.body_json);
        reading.revision = Some(Revision {
            versions: versions.len() as u32,
            current: Id(head.id.clone()),
            edited_at: head.recorded_at,
            edited_by: head.attributed_to.clone().map(Id),
        });
    }
    if let Some(deletion) = deletion {
        let read = body::blank(&entry.body_json).zip(because(&deletion.body_json));
        reading.python_says = read.is_none();
        let (blanked, because) = read.unwrap_or_default();
        reading.body_json = blanked;
        reading.deleted = Some(Deleted {
            record: Id(deletion.id.clone()),
            at: deletion.recorded_at,
            by: deletion.attributed_to.clone().map(Id),
            because,
        });
    }
    reading
}

/// `(d["body"] or {}).get("reason") or None`, or `None` where that raises or isn't text.
fn because(body_json: &str) -> Option<Option<String>> {
    match body::fields(body_json, &["reason"])?.pop()? {
        body::Field::Text(reason) => Some(Some(reason)),
        body::Field::Nothing => Some(None),
        body::Field::NotText => None,
    }
}
