//! What the record says about an entry: `Corpus.stands` and `_superseded`, `spine/seam.py:877`, `:858`.
//!
//! **One statement for any number of ids.** Every link pointing at what was asked about, and every
//! superseding link that reaches one of those, is read at once. The walks then run in memory in
//! Python's order, with Python's memo, so where a chain forks or loops the same answer comes out.

use std::collections::HashMap;

use mentis_record::{Flow, Id, Param, ReadScope, RecordError, Row, Value};

use crate::Standing;
use crate::now::id_list;

/// `seed.SUPERSEDES`, `seed.ESTABLISHES`: the two roles the engine names.
const SUPERSEDES: &str = "supersedes";
const ESTABLISHES: &str = "establishes";

/// `_role` reads the definition of the link's own relation version, the first of them if there were
/// two. A link nothing defines has no role.
const LINKS_REACHING: &str = "WITH RECURSIVE \
     roles(relation, version, role) AS MATERIALIZED ( \
       SELECT d.def_name, d.def_version, json_extract(d.body, '$.substrate_role') FROM entry d \
       WHERE d.family = 'definition' \
         AND d.seq = (SELECT MIN(x.seq) FROM entry x WHERE x.family = 'definition' \
                      AND x.def_name = d.def_name AND x.def_version = d.def_version)), \
     reach(id) AS ( \
       SELECT l.id FROM entry l \
       WHERE l.link_to IN (SELECT value FROM json_each(?1)) AND l.link_relation IS NOT NULL \
       UNION SELECT l.id FROM reach r JOIN entry l ON l.link_to = r.id \
         JOIN roles o ON o.relation = l.link_relation AND o.version = l.link_relation_version \
         WHERE o.role = 'supersedes') \
     SELECT l.id, l.link_from, l.link_to, l.link_relation, l.recorded_at, \
       (SELECT o.role FROM roles o WHERE o.relation = l.link_relation \
          AND o.version = l.link_relation_version) \
     FROM reach r CROSS JOIN entry l ON l.id = r.id ORDER BY l.seq";

/// A link, as far as standing reads it.
#[derive(Clone, Debug)]
struct Incoming {
    id: String,
    from: String,
    relation: String,
    recorded_at: f64,
    role: Option<String>,
}

fn text(row: &dyn Row, column: usize) -> Result<Option<String>, RecordError> {
    match row.value(column)? {
        Value::Null => Ok(None),
        Value::Text(bytes) => std::str::from_utf8(bytes)
            .map(|text| Some(text.to_owned()))
            .map_err(|_| RecordError::Sqlite {
                detail: format!("column {column} is not UTF-8"),
            }),
        _ => Ok(None),
    }
}

/// The links pointing at some entries, and the superseding links reaching those.
#[derive(Debug, Default)]
pub struct IncomingLinks {
    to: HashMap<String, Vec<Incoming>>,
}

impl IncomingLinks {
    /// One statement, or none for no ids.
    pub fn load(scope: &mut dyn ReadScope, ids: &[Id]) -> Result<IncomingLinks, RecordError> {
        let mut links = IncomingLinks::default();
        if ids.is_empty() {
            return Ok(links);
        }
        let asked = id_list(ids.iter().map(|id| id.0.as_str()));
        let to = &mut links.to;
        scope.query(LINKS_REACHING, &[Param::Text(&asked)], &mut |row| {
            let recorded_at = match row.value(4)? {
                Value::Real(at) => at,
                Value::Integer(at) => at as f64,
                _ => 0.0,
            };
            let target = text(row, 2)?.unwrap_or_default();
            to.entry(target).or_default().push(Incoming {
                id: text(row, 0)?.unwrap_or_default(),
                from: text(row, 1)?.unwrap_or_default(),
                relation: text(row, 3)?.unwrap_or_default(),
                recorded_at,
                role: text(row, 5)?,
            });
            Ok(Flow::Continue)
        })?;
        Ok(links)
    }

    /// `_superseded`. `memo` is Python's: one per `stands` call, so a cycle reads as it does there.
    pub fn superseded(
        &self,
        link: &str,
        as_at: Option<f64>,
        memo: &mut HashMap<String, bool>,
    ) -> bool {
        if let Some(known) = memo.get(link) {
            return *known;
        }
        memo.insert(link.to_owned(), false);
        for other in self.to.get(link).map_or(&[][..], Vec::as_slice) {
            if as_at.is_some_and(|at| other.recorded_at > at) {
                continue;
            }
            if other.role.as_deref() != Some(SUPERSEDES) {
                continue;
            }
            if !self.superseded(&other.id, as_at, memo) {
                memo.insert(link.to_owned(), true);
                return true;
            }
        }
        false
    }

    /// `stands`.
    pub fn standing(&self, entry: &Id, as_at: Option<f64>) -> Standing {
        let mut established_by = Vec::new();
        let mut superseded_by = Vec::new();
        let mut other: Vec<(String, Vec<Id>)> = Vec::new();
        let mut memo = HashMap::new();
        for link in self.to.get(&entry.0).map_or(&[][..], Vec::as_slice) {
            if as_at.is_some_and(|at| link.recorded_at > at) {
                continue;
            }
            if self.superseded(&link.id, as_at, &mut memo) {
                continue;
            }
            match link.role.as_deref() {
                Some(ESTABLISHES) => established_by.push(Id(link.id.clone())),
                Some(SUPERSEDES) => superseded_by.push(Id(link.from.clone())),
                _ => match other.iter_mut().find(|(name, _)| *name == link.relation) {
                    Some((_, ids)) => ids.push(Id(link.id.clone())),
                    None => other.push((link.relation.clone(), vec![Id(link.id.clone())])),
                },
            }
        }
        established_by.sort();
        superseded_by.sort();
        other.sort_by(|a, b| a.0.cmp(&b.0));
        for (_, ids) in &mut other {
            ids.sort();
        }
        Standing {
            entry: entry.clone(),
            stands: !established_by.is_empty() && superseded_by.is_empty(),
            established_by,
            superseded_by,
            incoming: other,
        }
    }
}

/// `Corpus.stands` for each id, whether the record holds it or not: an id it doesn't hold has no
/// links, so it stands on nothing, as in Python.
pub fn standing_many(
    scope: &mut dyn ReadScope,
    ids: &[Id],
    as_at: Option<f64>,
) -> Result<HashMap<Id, Standing>, RecordError> {
    let links = IncomingLinks::load(scope, ids)?;
    Ok(ids
        .iter()
        .map(|id| (id.clone(), links.standing(id, as_at)))
        .collect())
}
