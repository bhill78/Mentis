//! `kinds`: `Surface.kinds`, `worker.py:1017`, over `register.standing_split`. The clock is an
//! argument, so this op reads none. What the groups mean, in words, is the door's.
//!
//! **One moment of the record, unlike Python's reads.** Python's `split_walked` and
//! `entries_unknown_because` say the record moved between two of its reads. A scope is one snapshot,
//! so neither can arise here, and what a read failure would say goes to Python, which says it.

use std::collections::HashMap;

use mentis_record::{Flow, Id, Param, ReadScope, Value};
use mentis_rules::{IncomingLinks, STANDING_STATEMENTS};
use serde::Serialize;

use crate::acts::text;
use crate::stored::{Counts, Stored, python_says};
use crate::vocabulary::{self, Ground, Group, Vocabulary};
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest, python};

/// `Store.count_of_links`.
const LINK_COUNTS: &str = "SELECT link_relation, COUNT(*) FROM entry \
     WHERE family = 'entry' AND link_relation IS NOT NULL \
     GROUP BY link_relation ORDER BY link_relation";

/// `entries_of_kind` of every Kind at once.
const NODES: &str = "SELECT id, def_name FROM entry \
     WHERE def_name IN (SELECT value FROM json_each(?1)) \
       AND family = 'entry' AND link_relation IS NULL ORDER BY seq";

/// Kinds.
#[derive(Clone, Copy, Debug, Default)]
pub struct Kinds;

/// The time to report, seconds as `time.time()` gives them. The door's clock, not the op's.
#[derive(Clone, Copy, Debug, Default)]
pub struct KindsArgs {
    pub at: f64,
}

/// How a Kind's entries divide. `None` is a heading nobody has said applies, never a count of zero.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize)]
pub struct Split {
    pub proposed: Option<u64>,
    pub recorded: Option<u64>,
    pub standing: Option<u64>,
    pub history: Option<u64>,
    pub unknown: Option<u64>,
}

/// A Kind's definition, and how many entries it holds and how they stand.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct KindRow {
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
    pub ground: String,
    pub entries: u64,
    pub split: Option<Split>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub split_because: Option<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub unknown_because: Vec<String>,
}

/// How many Kinds and Relations are declared.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct DefinitionCounts {
    pub kinds: u64,
    pub relations: u64,
}

/// How many links there are, by Relation.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct LinkCounts {
    pub total: u64,
    pub by_relation: Counts,
}

/// The answer's one row: the totals belong to no one Kind.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct KindsPage {
    pub as_read_at: String,
    pub kinds: Vec<KindRow>,
    pub definitions: DefinitionCounts,
    pub links: LinkCounts,
}

const SPLIT_NOT_MEANINGFUL: &str = "its Kind declares standing not meaningful, so its entries are \
     never proposed, standing or history";
const SPLIT_UNDECLARED: &str = "its Kind does not declare whether standing applies, so its entries \
     are not sorted into proposed, standing or history";

impl ReadOp for Kinds {
    type Args = KindsArgs;
    type Row = KindsPage;

    const NAME: &'static str = "kinds";
    /// The position, the definitions, the counts of Kinds and of links, the nodes walked, their
    /// standing, and the open requests of those that are candidates.
    const BUDGET: Budget = Budget {
        statements: 6 + STANDING_STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<KindsArgs>,
    ) -> Result<ReadAnswer<KindsPage>, OpError> {
        let as_of = scope.position();
        let page = read_page(scope, request.args.at).map_err(|failed| match failed {
            // Python says what it could not count, in the answer. So it answers this.
            OpError::Record(error) => python_says(&error.to_string()),
            other => other,
        })?;
        Ok(ReadAnswer {
            rows: vec![page],
            as_of,
            more: None,
            not_searched: Vec::new(),
        })
    }
}

fn read_page(scope: &mut dyn ReadScope, at: f64) -> Result<KindsPage, OpError> {
    let vocabulary = Vocabulary::read(scope)?;
    let definitions = vocabulary.kinds()?;
    let relations = vocabulary.relations()?;
    let counts = vocabulary::counts_of_kinds(scope)?;

    let mut linked: Vec<(String, u64)> = Vec::new();
    scope.query(LINK_COUNTS, &[], &mut |row| {
        if let (Some(name), Value::Integer(count)) = (text(row, 0)?, row.value(1)?) {
            linked.push((name, count as u64));
        }
        Ok(Flow::Continue)
    })?;
    let mut by_relation: Vec<(String, u64)> =
        relations.iter().map(|name| (name.clone(), 0)).collect();
    for (name, count) in linked {
        match by_relation.iter_mut().find(|(held, _)| *held == name) {
            Some((_, held)) => *held = count,
            None => by_relation.push((name, count)),
        }
    }
    let total = by_relation.iter().map(|(_, count)| count).sum();

    let mut walked = Vec::new();
    for (name, definition) in &definitions {
        if definition.ground()? != Ground::StandingNotMeaningful {
            walked.push(name.as_str());
        }
    }
    let mut nodes: Vec<(Id, String)> = Vec::new();
    if !walked.is_empty() {
        let names = mentis_rules::id_list(walked.iter().copied());
        scope.query(NODES, &[Param::Text(&names)], &mut |row| {
            if let (Some(id), Some(kind)) = (text(row, 0)?, text(row, 1)?) {
                nodes.push((Id(id), kind));
            }
            Ok(Flow::Continue)
        })?;
    }
    let ids: Vec<Id> = nodes.iter().map(|(id, _)| id.clone()).collect();
    let links = IncomingLinks::load(scope, &ids)?;

    // Which group each entry is in, before `recorded` is told from `proposed`.
    let mut sorted: Vec<(&str, &Id, Group)> = Vec::with_capacity(nodes.len());
    for (id, kind) in &nodes {
        let definition = &definitions[kind];
        let (_, group) = definition.group_of(&links.standing(id, None))?;
        sorted.push((kind, id, group));
    }
    let candidates: Vec<Id> = sorted
        .iter()
        .filter(|(_, _, group)| *group == Group::Proposed)
        .map(|(_, id, _)| (*id).clone())
        .collect();
    let open = vocabulary::with_open_requests(scope, &candidates)?;

    let mut tally: HashMap<&str, Split> = HashMap::new();
    for (kind, id, group) in sorted {
        let split = tally.entry(kind).or_default();
        let count = match group {
            Group::Proposed if open.contains(&id.0) => &mut split.proposed,
            Group::Proposed | Group::Recorded => &mut split.recorded,
            Group::Standing => &mut split.standing,
            Group::History => &mut split.history,
            Group::Unknown => &mut split.unknown,
        };
        *count = Some(count.unwrap_or(0) + 1);
    }

    let mut kinds = Vec::with_capacity(definitions.len());
    for (name, definition) in &definitions {
        let ground = definition.ground()?;
        let mut split_because = None;
        let mut unknown_because = Vec::new();
        let counted = tally.get(name.as_str()).copied().unwrap_or_default();
        let zero = |count: Option<u64>| Some(count.unwrap_or(0));
        let split = match ground {
            Ground::StandingNotMeaningful => {
                split_because = Some(SPLIT_NOT_MEANINGFUL.to_owned());
                None
            }
            Ground::StandingAptUnknown => {
                unknown_because.push(SPLIT_UNDECLARED.to_owned());
                Some(Split {
                    proposed: None,
                    recorded: None,
                    standing: None,
                    history: None,
                    unknown: zero(counted.unknown),
                })
            }
            _ => Some(Split {
                proposed: zero(counted.proposed),
                recorded: zero(counted.recorded),
                standing: zero(counted.standing),
                history: zero(counted.history),
                unknown: zero(counted.unknown),
            }),
        };
        kinds.push(KindRow {
            kind: name.clone(),
            fields: definition.fields.clone(),
            meaning: definition.meaning.clone(),
            truth_apt: definition.truth_apt.clone(),
            capturable: definition.capturable.clone(),
            standing_apt: definition.standing_apt.clone(),
            knowing: definition.knowing.clone(),
            expects_falsifier: definition.expects_falsifier.clone(),
            requires_basis: definition.requires_basis.clone(),
            authoring: definition.authoring.clone(),
            form: definition.form.clone(),
            version: definition.version,
            ground: ground.name().to_owned(),
            entries: counts.get(name).copied().unwrap_or(0),
            split,
            split_because,
            unknown_because,
        });
    }
    Ok(KindsPage {
        as_read_at: python::when(at),
        definitions: DefinitionCounts {
            kinds: kinds.len() as u64,
            relations: relations.len() as u64,
        },
        kinds,
        links: LinkCounts {
            total,
            by_relation: Counts(by_relation),
        },
    })
}
