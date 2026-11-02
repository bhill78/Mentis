//! Where the record moved after a position: `web/moved.py`. It says where, never what, and only ever
//! narrows what is certain.
//!
//! **The statements are fixed per call.** Python's `_Placer` asks up to four questions per id, up to
//! three deep. Here the same questions are asked of all the ids at each depth at once, before any
//! placing, and [`Placer`] then runs Python's walk over the answers, so what it remembers and the
//! order it asks in come out the same.

use std::collections::{BTreeSet, HashMap, HashSet};

use mentis_record::{Flow, Param, Position, ReadScope, RecordError, Row, Value};
use serde::Serialize;

use crate::OpError;
use crate::python::{self, PythonInt};

/// `CAP`.
const CAP: i128 = 200;

/// `_Placer.of`'s `depth`.
const DEPTH: usize = 3;

/// The three reads of `Store.since`, and at each depth the five questions `_Placer._find` asks.
pub const STATEMENTS: u32 = 3 + 5 * DEPTH as u32;

/// `CONVERSATION_MATERIAL`.
const CONVERSATION_MATERIAL: [&str; 20] = [
    "contribution",
    "in-conversation",
    "replies-to",
    "about-topic",
    "topic",
    "topic-of",
    "participates-in",
    "conversation",
    "produced",
    "admission",
    "anchor",
    "anchors-in",
    "reaction",
    "reacts-to",
    "linked-into",
    "opened-from",
    "pictured-by",
    "deletion",
    "carries-intake",
    "designated-as",
];

/// `PEOPLE`.
const PEOPLE: [&str; 4] = ["participant", "persona", "participates-in", "designated-as"];

/// `RUN_ONLY_ACTS`.
const RUN_ONLY_ACTS: [&str; 2] = ["operation-answered", "consent-set"];

/// `_TO_CONVERSATION`.
const TO_CONVERSATION: [&str; 4] = [
    "in-conversation",
    "topic-of",
    "participates-in",
    "linked-into",
];

const SINCE_ENTRIES: &str = "SELECT id, def_name, link_from, link_to, link_relation FROM entry \
     WHERE seq > ?1 ORDER BY seq";
const SINCE_ACTS: &str = "SELECT act, conversation, execution, turn FROM operational \
     WHERE seq > ?1 ORDER BY seq";
const SINCE_DELIVERED: &str = "SELECT conversation, execution FROM delivery \
     WHERE seq > ?1 ORDER BY seq";

const KINDS: &str = "SELECT id, def_name FROM entry \
     WHERE id IN (SELECT value FROM json_each(?1)) ORDER BY seq";
const LINKS_FROM: &str = "SELECT link_from, link_relation, link_to FROM entry \
     WHERE link_relation IS NOT NULL AND link_from IN (SELECT value FROM json_each(?1)) \
     ORDER BY seq";
const PRODUCED_TO: &str = "SELECT link_to, link_from FROM entry \
     WHERE link_relation = 'produced' AND link_to IN (SELECT value FROM json_each(?1)) \
     ORDER BY seq";
const ACTS_BY_ID: &str = "SELECT id, conversation FROM operational \
     WHERE id IN (SELECT value FROM json_each(?1))";
/// `operational(execution=x, limit=1)`: the first act of each.
const ACTS_BY_EXECUTION: &str = "SELECT j.value, (SELECT o.conversation FROM operational o \
     WHERE o.execution = j.value ORDER BY o.seq LIMIT 1) FROM json_each(?1) j";

/// `moved`'s answer when it can say.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize)]
pub struct Moved {
    pub conversations: Vec<String>,
    pub executions: Vec<String>,
    pub governed: bool,
    pub people: bool,
    pub loose: bool,
}

/// `_parse`: three `int`s or nothing. `Err` where Python's `int` has to be asked.
fn parse(since: &str) -> Result<Option<[i128; 3]>, OpError> {
    let mut found = Vec::new();
    for part in since.split('.') {
        match python::int(part) {
            PythonInt::Value(value) => found.push(value),
            PythonInt::NotInt => return Ok(None),
            PythonInt::Unsure => {
                return Err(OpError::NotOwned {
                    why: "a position in another script's digits is Python's to read".into(),
                });
            }
        }
    }
    Ok(<[i128; 3]>::try_from(found).ok())
}

fn text(row: &dyn Row, column: usize) -> Result<Option<String>, RecordError> {
    match row.value(column)? {
        Value::Text(_) => row.value(column)?.text().map(str::to_owned).map_or_else(
            || {
                Err(RecordError::Sqlite {
                    detail: format!("column {column} is not UTF-8"),
                })
            },
            |text| Ok(Some(text)),
        ),
        _ => Ok(None),
    }
}

/// Reading an entry's place.
fn has_entry_prefix(id: &str) -> bool {
    id.starts_with("ent-") || id.starts_with("adm-")
}

/// One id list as the parameter `json_each` reads.
fn list<'a>(ids: impl IntoIterator<Item = &'a String>) -> String {
    serde_json::to_string(&ids.into_iter().collect::<Vec<_>>())
        .expect("a list of strings is always JSON")
}

/// What `_Placer._find` asks of the record, already answered.
#[derive(Debug, Default)]
struct Known {
    /// `c.read([x])`'s Kind, for what is held.
    kinds: HashMap<String, Option<String>>,
    /// `c.links(frm=x)`, in order: relation, to.
    links_from: HashMap<String, Vec<(String, String)>>,
    /// `c.links(relation="produced", to=x)`, in order: from.
    produced_to: HashMap<String, Vec<String>>,
    /// `c.operational(id=x)`: its Conversation, for an act held.
    acts: HashMap<String, Option<String>>,
    /// `c.operational(execution=x, limit=1)`: the first act's Conversation.
    executions: HashMap<String, Option<String>>,
    asked: HashSet<String>,
}

impl Known {
    /// Asks about all of these, at most five statements, and answers what the next depth asks of.
    fn ask(
        &mut self,
        scope: &mut dyn ReadScope,
        ids: Vec<String>,
    ) -> Result<Vec<String>, RecordError> {
        let ids: Vec<String> = ids
            .into_iter()
            .filter(|id| !id.is_empty() && self.asked.insert(id.clone()))
            .collect();
        let (entries, others): (Vec<&String>, Vec<&String>) =
            ids.iter().partition(|id| has_entry_prefix(id));
        let mut next = Vec::new();
        if !entries.is_empty() {
            let wanted = list(entries.iter().copied());
            let param = [Param::Text(&wanted)];
            scope.query(KINDS, &param, &mut |row| {
                if let Some(id) = text(row, 0)? {
                    self.kinds.insert(id, text(row, 1)?);
                }
                Ok(Flow::Continue)
            })?;
            scope.query(LINKS_FROM, &param, &mut |row| {
                if let (Some(from), Some(relation), Some(to)) =
                    (text(row, 0)?, text(row, 1)?, text(row, 2)?)
                {
                    if !matches!(
                        relation.as_str(),
                        "in-conversation" | "topic-of" | "participates-in" | "linked-into"
                    ) {
                        next.push(to.clone());
                    }
                    self.links_from
                        .entry(from)
                        .or_default()
                        .push((relation, to));
                }
                Ok(Flow::Continue)
            })?;
            scope.query(PRODUCED_TO, &param, &mut |row| {
                if let (Some(to), Some(from)) = (text(row, 0)?, text(row, 1)?) {
                    next.push(from.clone());
                    self.produced_to.entry(to).or_default().push(from);
                }
                Ok(Flow::Continue)
            })?;
        }
        if !others.is_empty() {
            let wanted = list(others.iter().copied());
            let param = [Param::Text(&wanted)];
            let acts: Vec<&String> = others
                .iter()
                .copied()
                .filter(|id| id.starts_with("opr-"))
                .collect();
            if !acts.is_empty() {
                let of_acts = list(acts);
                scope.query(ACTS_BY_ID, &[Param::Text(&of_acts)], &mut |row| {
                    if let Some(id) = text(row, 0)? {
                        self.acts.insert(id, text(row, 1)?);
                    }
                    Ok(Flow::Continue)
                })?;
            }
            scope.query(ACTS_BY_EXECUTION, &param, &mut |row| {
                if let Some(id) = text(row, 0)? {
                    self.executions.insert(id, text(row, 1)?);
                }
                Ok(Flow::Continue)
            })?;
        }
        Ok(next)
    }
}

/// `_Placer`, over what [`Known`] holds.
struct Placer<'a> {
    known: &'a Known,
    placed: HashMap<String, Option<String>>,
}

impl Placer<'_> {
    fn of(&mut self, x: Option<&str>, depth: usize) -> Option<String> {
        let x = x.filter(|x| !x.is_empty())?;
        if depth == 0 {
            return None;
        }
        if let Some(found) = self.placed.get(x) {
            return found.clone();
        }
        self.placed.insert(x.to_owned(), None);
        let found = self.find(x, depth);
        self.placed.insert(x.to_owned(), found.clone());
        found
    }

    fn find(&mut self, x: &str, depth: usize) -> Option<String> {
        let known = self.known;
        if !has_entry_prefix(x) {
            let act = if x.starts_with("opr-") {
                known.acts.get(x)
            } else {
                None
            };
            let conversation = match act {
                Some(conversation) => conversation.as_ref(),
                None => known.executions.get(x).and_then(Option::as_ref),
            };
            return conversation.filter(|c| !c.is_empty()).cloned();
        }
        if known
            .kinds
            .get(x)
            .is_some_and(|kind| kind.as_deref() == Some("conversation"))
        {
            return Some(x.to_owned());
        }
        for (relation, to) in known.links_from.get(x).map_or(&[][..], Vec::as_slice) {
            if matches!(relation.as_str(), "in-conversation" | "topic-of") {
                return Some(to.clone());
            }
            if matches!(relation.as_str(), "participates-in" | "linked-into") {
                continue;
            }
            if let Some(found) = self.of(Some(to), depth - 1) {
                return Some(found);
            }
        }
        for from in known.produced_to.get(x).map_or(&[][..], Vec::as_slice) {
            if let Some(found) = self.of(Some(from), depth - 1) {
                return Some(found);
            }
        }
        None
    }
}

type EntryRow = (
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
);
type ActRow = (
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
);

fn truthy(text: &Option<String>) -> Option<&str> {
    text.as_deref().filter(|text| !text.is_empty())
}

/// `moved(corpus, since)`, with `since` not empty. `Ok(None)` is Python's `None`: everything is to
/// reread. At most [`STATEMENTS`], and `now` is the scope's own position, which `Store.since` reads
/// again where a scope needn't.
pub fn moved(
    scope: &mut dyn ReadScope,
    now: Position,
    since: &str,
) -> Result<Option<Moved>, OpError> {
    let Some([seq, ops, outs]) = parse(since)? else {
        return Ok(None);
    };
    let now = [
        i128::from(now.entry),
        i128::from(now.operational),
        i128::from(now.delivery),
    ];
    if now[0] < seq || now[1] < ops || now[2] < outs {
        return Ok(None);
    }
    if now[0] - seq > CAP || now[1] - ops > CAP || now[2] - outs > CAP {
        return Ok(None);
    }

    // Each fits: a value more than CAP behind `now` went above, and one past it before that.
    let at = |value: i128| Param::Integer(value as i64);
    let mut entries: Vec<EntryRow> = Vec::new();
    scope.query(SINCE_ENTRIES, &[at(seq)], &mut |row| {
        entries.push((
            text(row, 0)?,
            text(row, 1)?,
            text(row, 2)?,
            text(row, 3)?,
            text(row, 4)?,
        ));
        Ok(Flow::Continue)
    })?;
    let mut acts: Vec<ActRow> = Vec::new();
    scope.query(SINCE_ACTS, &[at(ops)], &mut |row| {
        acts.push((text(row, 0)?, text(row, 1)?, text(row, 2)?, text(row, 3)?));
        Ok(Flow::Continue)
    })?;
    let mut delivered: Vec<(Option<String>, Option<String>)> = Vec::new();
    scope.query(SINCE_DELIVERED, &[at(outs)], &mut |row| {
        delivered.push((text(row, 0)?, text(row, 1)?));
        Ok(Flow::Continue)
    })?;

    let mut asking = Vec::new();
    for (id, _, from, to, relation) in &entries {
        match relation.as_deref() {
            None => asking.extend(id.clone()),
            Some("linked-into") => asking.extend(from.clone()),
            Some(relation) if TO_CONVERSATION.contains(&relation) => {}
            Some(_) => {
                asking.extend(from.clone());
                asking.extend(to.clone());
            }
        }
    }
    for (_, _, _, turn) in &acts {
        asking.extend(turn.clone());
    }
    let mut known = Known::default();
    for _ in 0..DEPTH {
        asking = known.ask(scope, asking)?;
    }

    let mut place = Placer {
        known: &known,
        placed: HashMap::new(),
    };
    let mut conversations = BTreeSet::new();
    let mut executions = BTreeSet::new();
    let (mut governed, mut people, mut loose) = (false, false, false);
    for (id, kind, from, to, relation) in &entries {
        let kind = kind
            .as_deref()
            .filter(|kind| !kind.is_empty())
            .or(relation.as_deref().filter(|relation| !relation.is_empty()));
        if !kind.is_some_and(|kind| CONVERSATION_MATERIAL.contains(&kind)) {
            governed = true;
        }
        if kind.is_some_and(|kind| PEOPLE.contains(&kind)) {
            people = true;
        }
        let relation = relation.as_deref();
        if relation.is_some_and(|relation| TO_CONVERSATION.contains(&relation)) {
            conversations.extend(to.clone());
            if relation == Some("linked-into")
                && let Some(home) = place.of(from.as_deref(), DEPTH)
            {
                conversations.insert(home);
            }
            continue;
        }
        let place_it = if relation.is_some_and(|relation| !relation.is_empty()) {
            place
                .of(from.as_deref(), DEPTH)
                .or_else(|| place.of(to.as_deref(), DEPTH))
        } else {
            place.of(id.as_deref(), DEPTH)
        };
        match place_it {
            Some(found) => {
                conversations.insert(found);
            }
            None if kind != Some("admission") => loose = true,
            None => {}
        }
    }
    for (act, conversation, execution, turn) in &acts {
        let act = act.as_deref().unwrap_or("");
        if RUN_ONLY_ACTS.contains(&act) {
            match truthy(execution) {
                Some(execution) => {
                    executions.insert(execution.to_owned());
                }
                None => loose = true,
            }
            continue;
        }
        match truthy(conversation) {
            Some(conversation) => {
                conversations.insert(conversation.to_owned());
            }
            None => loose = true,
        }
        if let Some(home) = truthy(turn).and_then(|turn| place.of(Some(turn), DEPTH)) {
            conversations.insert(home);
        }
        if let Some(execution) = truthy(execution) {
            executions.insert(execution.to_owned());
        }
        if act.starts_with("material-") || act.starts_with("governance-") {
            governed = true;
        }
    }
    for (conversation, execution) in &delivered {
        match truthy(conversation) {
            Some(conversation) => {
                conversations.insert(conversation.to_owned());
            }
            None => loose = true,
        }
        executions.extend(execution.clone());
    }
    Ok(Some(Moved {
        conversations: conversations.into_iter().collect(),
        executions: executions.into_iter().collect(),
        governed,
        people,
        loose,
    }))
}
