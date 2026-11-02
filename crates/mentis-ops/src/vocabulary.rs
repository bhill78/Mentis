//! The definitions the record holds, and what `kinds` and `governed` both read from them:
//! `register.kind_definitions`, `_kinds`, `ground_of` and `group_of`, `conversation/register.py`.
//! One read of the vocabulary, as in Python, so the two can't disagree.

use std::collections::{BTreeMap, HashMap};

use mentis_record::{Flow, Id, Param, ReadScope, Value};
use mentis_rules::Standing;

use crate::OpError;
use crate::acts::text;
use crate::stored::{Object, Stored, python_says};

const DEFINITIONS: &str =
    "SELECT def_name, def_version, body FROM entry WHERE family = 'definition' ORDER BY seq";

/// `Store.count_of_definition` of every Kind at once.
const COUNTS: &str = "SELECT def_name, COUNT(*) FROM entry \
     WHERE family = 'entry' AND link_relation IS NULL AND def_name IS NOT NULL GROUP BY def_name";

/// `ladder_writes.requests`' reads, of every id at once.
const REQUESTS: &str = "SELECT link_to, id, link_relation, body FROM entry \
     WHERE link_relation IN ('proposes', 'declines') \
       AND link_to IN (SELECT value FROM json_each(?1)) ORDER BY seq";

/// A definition's name, version and body, as the statement gives them.
type RawDefinition = (Option<String>, Option<i64>, Option<String>);

/// One definition, of any version.
#[derive(Clone, Debug)]
struct Definition {
    name: Option<String>,
    version: i64,
    body: Object,
}

/// A Kind's current definition, as it declares itself. Absent stays absent: a field nobody wrote is
/// `null`.
#[derive(Clone, Debug)]
pub struct KindDefinition {
    pub kind: String,
    pub fields: Stored,
    pub meaning: Stored,
    pub truth_apt: Stored,
    pub capturable: Stored,
    pub standing_apt: Stored,
    pub knowing: Stored,
    pub expects_falsifier: Stored,
    pub requires_basis: Stored,
    pub authoring: Stored,
    pub form: Stored,
    pub version: i64,
}

impl KindDefinition {
    fn directs_work(&self) -> Result<bool, OpError> {
        Ok(self.knowing.string()?.as_deref() == Some("how"))
    }

    /// `ground_of`.
    pub fn ground(&self) -> Result<Ground, OpError> {
        Ok(if self.directs_work()? {
            Ground::DirectsWork
        } else if self.standing_apt.is_true() {
            Ground::StandingKnowledge
        } else if self.standing_apt.text() == "false" {
            Ground::StandingNotMeaningful
        } else {
            Ground::StandingAptUnknown
        })
    }

    /// `group_of`: an entry's `state` and register group, before `recorded` is told from
    /// `proposed`. `state` is `None` where standing doesn't apply.
    pub fn group_of(&self, standing: &Standing) -> Result<(Option<&'static str>, Group), OpError> {
        if self.standing_apt.is_true() || self.directs_work()? {
            let state = standing_state(standing);
            return Ok((Some(state), group_of_state(state)));
        }
        Ok((None, Group::Unknown))
    }
}

/// Why a Kind is, or isn't, walked by the register.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Ground {
    DirectsWork,
    StandingKnowledge,
    StandingNotMeaningful,
    StandingAptUnknown,
}

impl Ground {
    pub fn name(self) -> &'static str {
        match self {
            Ground::DirectsWork => "directs_work",
            Ground::StandingKnowledge => "standing_knowledge",
            Ground::StandingNotMeaningful => "standing_not_meaningful",
            Ground::StandingAptUnknown => "standing_apt_unknown",
        }
    }
}

/// The register's five groups.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Group {
    Proposed,
    Recorded,
    Standing,
    History,
    Unknown,
}

impl Group {
    pub fn name(self) -> &'static str {
        match self {
            Group::Proposed => "proposed",
            Group::Recorded => "recorded",
            Group::Standing => "standing",
            Group::History => "history",
            Group::Unknown => "unknown",
        }
    }

    /// `state not in GROUPS` is the other answer.
    pub fn named(name: &str) -> Option<Group> {
        [
            Group::Proposed,
            Group::Recorded,
            Group::Standing,
            Group::History,
            Group::Unknown,
        ]
        .into_iter()
        .find(|group| group.name() == name)
    }
}

/// `standing_state`.
pub fn standing_state(standing: &Standing) -> &'static str {
    if standing.stands {
        "stands"
    } else if !standing.superseded_by.is_empty() {
        if standing.established_by.is_empty() {
            "replaced"
        } else {
            "ended"
        }
    } else {
        "candidate"
    }
}

fn group_of_state(state: &str) -> Group {
    match state {
        "stands" => Group::Standing,
        "candidate" => Group::Proposed,
        _ => Group::History,
    }
}

/// The record's definitions, every version, in the order they were written.
#[derive(Clone, Debug, Default)]
pub struct Vocabulary {
    definitions: Vec<Definition>,
}

impl Vocabulary {
    /// One statement. Python's `b.get` raises on a body that isn't an object.
    pub fn read(scope: &mut dyn ReadScope) -> Result<Vocabulary, OpError> {
        let mut raw: Vec<RawDefinition> = Vec::new();
        scope.query(DEFINITIONS, &[], &mut |row| {
            let version = match row.value(1)? {
                Value::Integer(version) => Some(version),
                _ => None,
            };
            raw.push((text(row, 0)?, version, text(row, 2)?));
            Ok(Flow::Continue)
        })?;
        let mut definitions = Vec::with_capacity(raw.len());
        for (name, version, body) in raw {
            let version = version.ok_or_else(|| python_says("a definition with no version"))?;
            let body = Object::exactly(&body.unwrap_or_default())?;
            definitions.push(Definition {
                name,
                version,
                body,
            });
        }
        Ok(Vocabulary { definitions })
    }

    /// `kind_definitions`: every Kind's current definition, by name. The first of two at one
    /// version wins, as there and in `current_definition`. A definition whose name differs from
    /// the Kind it declares reads differently through those two, so Python says.
    pub fn kinds(&self) -> Result<BTreeMap<String, KindDefinition>, OpError> {
        let mut newest: BTreeMap<String, KindDefinition> = BTreeMap::new();
        for definition in &self.definitions {
            let body = &definition.body;
            let Some(kind) = body.get("kind") else {
                continue;
            };
            if kind.truthy() == Some(false) {
                continue;
            }
            let name = kind
                .string()?
                .ok_or_else(|| python_says("a Kind whose name isn't text"))?;
            if definition.name.as_deref() != Some(&name) {
                return Err(python_says("a definition named other than its Kind"));
            }
            if newest
                .get(&name)
                .is_some_and(|held| definition.version <= held.version)
            {
                continue;
            }
            newest.insert(
                name.clone(),
                KindDefinition {
                    kind: name,
                    fields: body
                        .get("fields")
                        .cloned()
                        .unwrap_or_else(|| Stored::of(&Vec::<String>::new())),
                    meaning: body
                        .get("meaning")
                        .cloned()
                        .unwrap_or_else(|| Stored::of(&"")),
                    truth_apt: body.get_or_null("truth_apt"),
                    capturable: body.get_or_null("capturable"),
                    standing_apt: body.get_or_null("standing_apt"),
                    knowing: body.get_or_null("knowing"),
                    expects_falsifier: body.get_or_null("expects_falsifier"),
                    requires_basis: body.get_or_null("requires_basis"),
                    authoring: body.get_or_null("authoring"),
                    form: body.get_or_null("form"),
                    version: definition.version,
                },
            );
        }
        Ok(newest)
    }

    /// `{(e["body"] or {}).get("relation") for e in definitions} - {None}`.
    pub fn relations(&self) -> Result<Vec<String>, OpError> {
        let mut found = Vec::new();
        for definition in &self.definitions {
            if let Some(name) = definition.body.text("relation")? {
                found.push(name);
            }
        }
        found.sort();
        found.dedup();
        Ok(found)
    }

    /// `superseding_relation`. Python raises where none declares the role.
    pub fn superseding_relation(&self) -> Result<String, OpError> {
        for definition in &self.definitions {
            if definition.body.says("substrate_role", "supersedes")? {
                return definition
                    .body
                    .text("relation")?
                    .ok_or_else(|| python_says("a superseding relation with no name"));
            }
        }
        Err(python_says("no relation declares the superseding role"))
    }

    /// `proposal_relation`. `None` is not declared, which isn't "none recorded".
    pub fn proposal_relation(&self) -> Result<Option<String>, OpError> {
        let mut best: Option<(i64, String)> = None;
        for definition in &self.definitions {
            if !definition.body.says("proposes_role", "supersedes")? {
                continue;
            }
            if best
                .as_ref()
                .is_none_or(|(version, _)| definition.version > *version)
            {
                let name = definition
                    .body
                    .text("relation")?
                    .ok_or_else(|| python_says("a proposing relation with no name"))?;
                best = Some((definition.version, name));
            }
        }
        Ok(best.map(|(_, name)| name))
    }

    /// `definition_for(entry)`'s `fields`: the first definition at that version.
    pub fn pinned_fields(&self, name: &str, version: Option<i64>) -> Option<&Stored> {
        let version = version?;
        self.definitions
            .iter()
            .find(|d| d.version == version && d.name.as_deref() == Some(name))
            .and_then(|d| d.body.get("fields"))
    }
}

/// `count_of_kind` of every Kind.
pub fn counts_of_kinds(scope: &mut dyn ReadScope) -> Result<HashMap<String, u64>, OpError> {
    let mut counts = HashMap::new();
    scope.query(COUNTS, &[], &mut |row| {
        if let (Some(name), Value::Integer(count)) = (text(row, 0)?, row.value(1)?) {
            counts.insert(name, count as u64);
        }
        Ok(Flow::Continue)
    })?;
    Ok(counts)
}

/// Which of these have an open `proposes` request: `requests(corpus, eid, open_only=True)`. One
/// statement, or none for no ids.
pub fn with_open_requests(
    scope: &mut dyn ReadScope,
    ids: &[Id],
) -> Result<std::collections::HashSet<String>, OpError> {
    let mut open = std::collections::HashSet::new();
    if ids.is_empty() {
        return Ok(open);
    }
    let mut rows: Vec<(String, String, String, Option<String>)> = Vec::new();
    let asked = mentis_rules::id_list(ids.iter().map(|id| id.0.as_str()));
    scope.query(REQUESTS, &[Param::Text(&asked)], &mut |row| {
        rows.push((
            text(row, 0)?.unwrap_or_default(),
            text(row, 1)?.unwrap_or_default(),
            text(row, 2)?.unwrap_or_default(),
            text(row, 3)?,
        ));
        Ok(Flow::Continue)
    })?;
    let mut declined: HashMap<&str, Vec<String>> = HashMap::new();
    for (to, _, relation, body) in &rows {
        if relation == "declines" {
            let body = Object::exactly(body.as_deref().unwrap_or(""))?;
            if let Some(request) = body.text("request")? {
                declined.entry(to).or_default().push(request);
            }
        }
    }
    for (to, id, relation, _) in &rows {
        let answered = declined
            .get(to.as_str())
            .is_some_and(|ids| ids.contains(id));
        if relation == "proposes" && !answered {
            open.insert(to.clone());
        }
    }
    Ok(open)
}
