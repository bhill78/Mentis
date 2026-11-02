//! `governed`: `register.governed`, `conversation/register.py:279`. One read with two callers, the
//! worker (`worker.py:2085`) and Fluid's routes (`fluid/__init__.py:168`), so `limit`'s default is
//! each door's, sent explicitly, and `cursor` is kept though the agent door never sends one. With no
//! cursor each group is cut separately, and with one a single page is cut.
//!
//! **Every set read once and not per row,** as Python's docstring has it, and here also each
//! question it asks per row (`stands`, the disputes, the proposals) is one statement for all of
//! them. `listed_because`, `governs_is_per_row`, `not_an_ask` and how a refusal is shaped are the
//! door's.

use std::collections::{HashMap, HashSet};

use mentis_record::{Flow, Id, Param, ReadScope, Value};
use mentis_rules::{IncomingLinks, STANDING_STATEMENTS, STATEMENTS, Seen, Versioned};
use serde::Serialize;

use crate::acts::{Act, real, text};
use crate::stored::{Counts, Object, Stored, python_says};
use crate::vocabulary::{self, Ground, Group, KindDefinition, Vocabulary, standing_state};
use crate::{Budget, Cursor, OpError, ReadAnswer, ReadOp, ReadRequest, act_columns, python};

const NODES: &str = "SELECT id, def_name, def_version, body, attributed_to, recorded_at FROM entry \
     WHERE def_name IN (SELECT value FROM json_each(?1)) \
       AND family = 'entry' AND link_relation IS NULL ORDER BY seq";

/// `whole_brain_ids` and the Personas, which are asked of the same index.
const DESTINATIONS: &str = "SELECT id, def_name FROM entry \
     WHERE def_name IN ('whole-brain', 'persona') AND family = 'entry' \
       AND link_relation IS NULL ORDER BY seq";

/// The placements of the rows, none that any superseding link names.
const PLACEMENTS: &str = "SELECT l.link_from, l.link_to FROM entry l \
     WHERE l.link_relation = 'scoped-to' AND l.link_from IN (SELECT value FROM json_each(?1)) \
       AND NOT EXISTS (SELECT 1 FROM entry s WHERE s.link_relation = ?2 AND s.link_to = l.id) \
     ORDER BY l.seq";

const PRODUCED_BY: &str = "SELECT link_to, link_from FROM entry \
     WHERE link_relation = 'produced' AND link_to IN (SELECT value FROM json_each(?1)) \
     ORDER BY seq";

const ACTS: &str = concat!(
    "SELECT ",
    act_columns!(),
    " FROM operational WHERE id IN (SELECT value FROM json_each(?1)) ORDER BY seq"
);

/// What each row replaced, and whether that was a link, which ends a placement rather than material.
const SUPERSEDES: &str = "SELECT l.link_from, l.link_to, \
       (SELECT t.link_relation FROM entry t WHERE t.id = l.link_to) \
     FROM entry l WHERE l.link_relation = ?2 \
       AND l.link_from IN (SELECT value FROM json_each(?1)) ORDER BY l.seq";

/// `disputes_of`'s reads.
const CHALLENGES: &str = "SELECT link_to, id, link_from, link_relation, body, attributed_to, \
       recorded_at FROM entry \
     WHERE link_relation IN ('disputes', 'supports', 'withdraws') \
       AND link_to IN (SELECT value FROM json_each(?1)) ORDER BY seq";

/// `corpus.proposed_supersessions`' two reads.
const PROPOSALS: &str = "SELECT id, link_from, link_to, body, attributed_to, written_by, \
       recorded_at FROM entry WHERE link_relation = ?2 \
       AND (link_to IN (SELECT value FROM json_each(?1)) \
            OR link_from IN (SELECT value FROM json_each(?1))) ORDER BY seq";

/// What `_said` reads of a proposal's other side.
const SAID: &str = "SELECT id, def_name, def_version, body FROM entry \
     WHERE id IN (SELECT value FROM json_each(?1)) ORDER BY seq";

/// `DEFAULT_LIMIT`, `MAX_LIMIT`, `REGISTER_PROPOSALS`.
const DEFAULT_LIMIT: u32 = 50;
const MAX_LIMIT: u32 = 1000;
const REGISTER_PROPOSALS: usize = 5;

const NOT_GOVERNED: &str =
    "its Kind declares standing not meaningful, so it is not governed material";
const CONFERS: &str = "nothing. Every predecessor named here stands exactly as it stood; only an \
     owner establishing a successor replaces anything, and that writes its own link.";

/// The governed-material register.
#[derive(Clone, Copy, Debug, Default)]
pub struct Governed;

/// As sent. `limit` and `cursor` are [`ReadRequest`]'s.
#[derive(Clone, Debug, Default)]
pub struct GovernedArgs {
    pub kind: Option<String>,
    pub q: Option<String>,
    pub state: Option<String>,
}

/// What was asked, as the register read it.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct GovernedQuery {
    pub kind: Option<String>,
    pub q: String,
    pub state: Option<String>,
    pub limit: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cursor: Option<String>,
}

/// One destination a row is placed at.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Placed {
    pub conversation: String,
    pub name: Stored,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub whole_brain: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub persona: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub destination_kind: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub carried_by: Option<String>,
}

/// The act a row was proposed by.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ProposedBy {
    pub act: String,
    pub act_type: Option<String>,
    pub actor: Option<String>,
    pub actor_alias: Stored,
    pub conversation: Option<String>,
    pub conversation_name: Stored,
    pub turn: Option<String>,
}

/// One proposal.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ProposalItem {
    pub entry: String,
    pub link: String,
    pub reason: Stored,
    pub attributed_to: Option<String>,
    pub written_by: Option<String>,
    pub at: f64,
    pub kind: Option<String>,
    pub summary: Option<String>,
    pub by_alias: Stored,
    pub stands: bool,
    pub state: String,
}

/// One direction of proposals.
#[derive(Clone, Debug, Default, PartialEq, Serialize)]
pub struct ProposalSide {
    pub items: Vec<ProposalItem>,
    pub total: u64,
    pub omitted: u64,
    pub withdrawn: u64,
}

/// What is proposed to replace a row, and what it proposes to replace.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Proposed {
    pub entry: String,
    pub relation: String,
    pub successors: ProposalSide,
    pub predecessors: ProposalSide,
    pub confers: String,
}

/// One entry of the register.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct GovernedRow {
    pub entry: String,
    pub kind: String,
    pub standing_apt: Stored,
    pub knowing: Stored,
    pub governs: bool,
    pub summary: String,
    pub secondary: String,
    pub attributed_to: Option<String>,
    pub author_alias: Stored,
    pub at: f64,
    pub placed_at: Vec<Placed>,
    pub proposed_by: Vec<ProposedBy>,
    pub established_by: Vec<String>,
    pub superseded_by: Vec<String>,
    pub supersedes: Vec<String>,
    pub disputed_by: Vec<String>,
    pub open_disputes: Vec<String>,
    pub proposed: Option<Proposed>,
    pub proposed_reach: Vec<String>,
    pub state: Option<String>,
    pub group: String,
}

/// One value per group.
#[derive(Clone, Debug, Default, PartialEq, Serialize)]
pub struct ByGroup<T> {
    pub proposed: T,
    pub recorded: T,
    pub standing: T,
    pub history: T,
    pub unknown: T,
}

impl<T> ByGroup<T> {
    fn of(&mut self, group: Group) -> &mut T {
        match group {
            Group::Proposed => &mut self.proposed,
            Group::Recorded => &mut self.recorded,
            Group::Standing => &mut self.standing,
            Group::History => &mut self.history,
            Group::Unknown => &mut self.unknown,
        }
    }
}

/// A Kind not walked, and how many entries it holds.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct KindCount {
    pub kind: String,
    pub entries: u64,
}

/// Which Kinds are listed, and on which ground.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct GovernedKinds {
    pub listed: Vec<String>,
    pub walked: Counts,
    pub directs_work: Vec<String>,
    pub standing_knowledge: Vec<String>,
    pub standing_not_meaningful: Vec<String>,
    pub standing_apt_unknown: Vec<KindCount>,
}

/// The answer's one row: totals and omissions beside the groups.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct GovernedPage {
    pub query: GovernedQuery,
    pub groups: ByGroup<Vec<GovernedRow>>,
    pub totals: ByGroup<u64>,
    pub omitted: ByGroup<u64>,
    pub matched: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_cursor: Option<Option<String>>,
    pub walked: u64,
    pub kinds: GovernedKinds,
    pub why_not: Option<String>,
}

struct Node {
    id: String,
    kind: String,
    version: Option<i64>,
    body: String,
    attributed_to: Option<String>,
    at: f64,
}

fn refused(why: String) -> OpError {
    OpError::BadRequest { why }
}

/// `repr` in a refusal, for what is plainly the same here.
fn shown(text: &str) -> Result<String, OpError> {
    python::repr(text).ok_or_else(|| python_says("a value Python has to show itself"))
}

/// `(value or "").strip() or None`.
fn stripped(value: &Option<String>) -> Option<String> {
    value
        .as_deref()
        .map(python::strip)
        .filter(|text| !text.is_empty())
        .map(str::to_owned)
}

/// `0` from `""` or `"start"`, `g1.<n>` otherwise, as the register reads a cursor.
fn offset_of(cursor: &str) -> Result<usize, OpError> {
    if cursor.is_empty() || cursor == "start" {
        return Ok(0);
    }
    let bad = || match shown(cursor) {
        Ok(words) => refused(format!("not a governed-material cursor: {words}")),
        Err(failed) => failed,
    };
    match python::int(cursor.strip_prefix("g1.").unwrap_or(cursor)) {
        python::PythonInt::Value(offset) if offset < 0 => Err(bad()),
        python::PythonInt::Value(offset) => Ok(usize::try_from(offset).unwrap_or(usize::MAX)),
        python::PythonInt::NotInt => Err(bad()),
        python::PythonInt::Unsure => Err(python_says("a cursor in another script's digits")),
    }
}

/// `_summary`: the principal statement and the one after it, in the Kind's own order.
fn summary(body: &Object, fields: &Stored) -> Result<(String, String), OpError> {
    let mut said: Vec<String> = Vec::new();
    for key in declared_then_rest(body, fields)? {
        if let Some(value) = body.get(&key)
            && let Some(words) = value.string()?
        {
            let words = python::strip(&words);
            if !words.is_empty() {
                said.push(words.to_owned());
                if said.len() == 2 {
                    break;
                }
            }
        }
    }
    let mut said = said.into_iter();
    Ok((
        said.next().unwrap_or_default(),
        said.next().unwrap_or_default(),
    ))
}

/// `list(fields) + [k for k in body if k not in fields]`. A field that isn't a name is Python's.
fn declared_then_rest(body: &Object, fields: &Stored) -> Result<Vec<String>, OpError> {
    let mut order = Vec::new();
    for field in fields.items_or_none()? {
        order.push(
            field
                .string()?
                .ok_or_else(|| python_says("a Kind's field that isn't a name"))?,
        );
    }
    for (key, _) in &body.0 {
        if !order.contains(key) {
            order.push(key.clone());
        }
    }
    Ok(order)
}

/// `pinned.get("body", {}).get("fields") or kinds[name]["fields"]`.
fn fields_for<'a>(
    vocabulary: &'a Vocabulary,
    kind: &str,
    version: Option<i64>,
    definition: &'a KindDefinition,
) -> Result<&'a Stored, OpError> {
    if let Some(pinned) = vocabulary.pinned_fields(kind, version)
        && pinned
            .truthy()
            .ok_or_else(|| python_says("a Kind's fields this can't read"))?
    {
        return Ok(pinned);
    }
    Ok(&definition.fields)
}

/// What the read names, as `(presented(x) or x)["body"] or {}`.
struct Named(HashMap<Id, Object>);

impl Named {
    fn read(scope: &mut dyn ReadScope, ids: &[Id]) -> Result<Named, OpError> {
        let seen = mentis_rules::reads(scope, ids, Versioned::ConversationsAndParticipants)?;
        let mut named = HashMap::with_capacity(seen.len());
        for (id, one) in seen {
            if one.reading.python_says {
                return Err(python_says("something named here that Python can't read"));
            }
            named.insert(id, Object::or_empty(&one.reading.body_json)?);
        }
        Ok(Named(named))
    }

    /// `named.get(p, {}).get("alias", p)`: a value the record holds under that key is what shows,
    /// null included.
    fn alias(&self, who: Option<&str>) -> Stored {
        let Some(who) = who else {
            return Stored::null();
        };
        match self
            .0
            .get(&Id(who.to_owned()))
            .and_then(|body| body.get("alias"))
        {
            Some(alias) => alias.clone(),
            None => Stored::of(&who),
        }
    }

    /// `named.get(c, {}).get("name")`.
    fn name(&self, conversation: Option<&str>) -> Stored {
        conversation
            .and_then(|c| self.0.get(&Id(c.to_owned())))
            .map_or_else(Stored::null, |body| body.get_or_null("name"))
    }
}

/// `value or ""`, for a haystack. `join` raises on anything else that is true.
fn words_of(value: &Stored) -> Result<String, OpError> {
    use mentis_rules::body::Field;
    match value.field() {
        Some(Field::Nothing) => Ok(String::new()),
        Some(Field::Text(words)) => Ok(words),
        _ => Err(python_says("a name that isn't text")),
    }
}

/// A `disputes`, `supports` or `withdraws` link.
struct Challenge {
    to: String,
    id: String,
    from: String,
    relation: String,
    body: Option<String>,
    attributed_to: Option<String>,
    at: f64,
}

/// A proposing link as the statement gives it.
type RawProposal = (
    String,
    String,
    String,
    Option<String>,
    Option<String>,
    Option<String>,
    f64,
);

/// A proposing link.
struct Proposal {
    id: String,
    from: String,
    to: String,
    reason: Stored,
    attributed_to: Option<String>,
    written_by: Option<String>,
    at: f64,
}

impl ReadOp for Governed {
    type Args = GovernedArgs;
    type Row = GovernedPage;

    const NAME: &'static str = "governed";
    /// The position, the definitions, the counts, the nodes, the destinations, the placements, what
    /// produced them, those acts, the rows' standing, what they replaced, the challenges, the open
    /// requests, the proposals, whether those were withdrawn, what they name and how it stands; and
    /// two reads of what all that names.
    const BUDGET: Budget = Budget {
        statements: 13 + 3 * STANDING_STATEMENTS + 2 * STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<GovernedArgs>,
    ) -> Result<ReadAnswer<GovernedPage>, OpError> {
        let as_of = scope.position();
        let vocabulary = Vocabulary::read(scope)?;
        let definitions = vocabulary.kinds()?;
        let args = &request.args;
        let kind = stripped(&args.kind);
        let state = stripped(&args.state);
        let q = args.q.clone().unwrap_or_default();
        let lowered =
            python::lower(&q).ok_or_else(|| python_says("a question in newer letters"))?;
        let tokens: Vec<String> = python::words(&lowered).map(str::to_owned).collect();
        let wanted_group = match &state {
            None => None,
            Some(state) => match Group::named(state) {
                Some(group) => Some(group),
                None => return Err(refused(format!("no such group {}", shown(state)?))),
            },
        };
        if let Some(kind) = &kind
            && !definitions.contains_key(kind)
        {
            return Err(refused(format!("no Kind is defined as {}", shown(kind)?)));
        }
        let cap = request.limit.unwrap_or(DEFAULT_LIMIT);
        if !(1..=MAX_LIMIT).contains(&cap) {
            return Err(refused(format!(
                "limit must be a whole number from 1 to {MAX_LIMIT}"
            )));
        }
        let offset = match &request.cursor {
            None => None,
            Some(Cursor(cursor)) => Some(offset_of(cursor)?),
        };

        let (mut listed, mut declined, mut unknown) = (Vec::new(), Vec::new(), Vec::new());
        let (mut directs_work, mut standing_knowledge) = (Vec::new(), Vec::new());
        for (name, definition) in &definitions {
            match definition.ground()? {
                Ground::DirectsWork => {
                    listed.push(name.clone());
                    directs_work.push(name.clone());
                }
                Ground::StandingKnowledge => {
                    listed.push(name.clone());
                    standing_knowledge.push(name.clone());
                }
                Ground::StandingNotMeaningful => declined.push(name.clone()),
                Ground::StandingAptUnknown => unknown.push(name.clone()),
            }
        }
        let walk: Vec<String> = match &kind {
            None => listed.clone(),
            Some(kind) if declined.contains(kind) => Vec::new(),
            Some(kind) => vec![kind.clone()],
        };
        let counts = vocabulary::counts_of_kinds(scope)?;

        // -- each set read once --------------------------------------------------------------
        let mut read_nodes: Vec<Node> = Vec::new();
        if !walk.is_empty() {
            let names = mentis_rules::id_list(walk.iter().map(String::as_str));
            scope.query(NODES, &[Param::Text(&names)], &mut |row| {
                let version = match row.value(2)? {
                    Value::Integer(version) => Some(version),
                    _ => None,
                };
                read_nodes.push(Node {
                    id: text(row, 0)?.unwrap_or_default(),
                    kind: text(row, 1)?.unwrap_or_default(),
                    version,
                    body: text(row, 3)?.unwrap_or_default(),
                    attributed_to: text(row, 4)?,
                    at: real(row, 5)?,
                });
                Ok(Flow::Continue)
            })?;
        }
        // Kind by Kind, in `walk`'s order, each in the record's: the order rows keep where two have
        // one time.
        let mut nodes: Vec<&Node> = Vec::with_capacity(read_nodes.len());
        let mut per_kind: Vec<(String, u64)> = Vec::with_capacity(walk.len());
        for name in &walk {
            let before = nodes.len();
            nodes.extend(read_nodes.iter().filter(|node| node.kind == *name));
            per_kind.push((name.clone(), (nodes.len() - before) as u64));
        }

        let mut whole_brain: HashSet<String> = HashSet::new();
        let mut personas: HashSet<String> = HashSet::new();
        scope.query(DESTINATIONS, &[], &mut |row| {
            if let (Some(id), Some(kind)) = (text(row, 0)?, text(row, 1)?) {
                if kind == "whole-brain" {
                    whole_brain.insert(id);
                } else {
                    personas.insert(id);
                }
            }
            Ok(Flow::Continue)
        })?;

        let ids: Vec<&str> = nodes.iter().map(|node| node.id.as_str()).collect();
        let asked = mentis_rules::id_list(ids.iter().copied());
        let mut placed_by: HashMap<String, Vec<String>> = HashMap::new();
        let mut made_by: HashMap<String, Vec<String>> = HashMap::new();
        let superseding = if ids.is_empty() {
            None
        } else {
            let relation = vocabulary.superseding_relation()?;
            scope.query(
                PLACEMENTS,
                &[Param::Text(&asked), Param::Text(&relation)],
                &mut |row| {
                    if let (Some(from), Some(to)) = (text(row, 0)?, text(row, 1)?) {
                        placed_by.entry(from).or_default().push(to);
                    }
                    Ok(Flow::Continue)
                },
            )?;
            scope.query(PRODUCED_BY, &[Param::Text(&asked)], &mut |row| {
                if let (Some(to), Some(from)) = (text(row, 0)?, text(row, 1)?) {
                    made_by.entry(to).or_default().push(from);
                }
                Ok(Flow::Continue)
            })?;
            Some(relation)
        };

        // Only the acts a row names.
        let mut acts: HashMap<String, Act> = HashMap::new();
        let named_acts: Vec<&str> = made_by.values().flatten().map(String::as_str).collect();
        if !named_acts.is_empty() {
            let asked = mentis_rules::id_list(named_acts.iter().copied());
            scope.query(ACTS, &[Param::Text(&asked)], &mut |row| {
                let act = Act::read(row, 0)?;
                acts.entry(act.id.clone()).or_insert(act);
                Ok(Flow::Continue)
            })?;
        }

        let mut named_ids: Vec<Id> = nodes
            .iter()
            .filter_map(|node| node.attributed_to.clone())
            .chain(acts.values().filter_map(|act| act.actor.clone()))
            .chain(placed_by.values().flatten().cloned())
            .chain(acts.values().filter_map(|act| act.conversation.clone()))
            .filter(|id| !id.is_empty())
            .map(Id)
            .collect();
        named_ids.sort();
        named_ids.dedup();
        let named = Named::read(scope, &named_ids)?;

        // The rows a search keeps, then what only they need.
        struct Kept<'a> {
            node: &'a Node,
            order: usize,
            placed: Vec<String>,
            proposed_by: Vec<ProposedBy>,
            author_alias: Stored,
        }
        let mut kept: Vec<Kept<'_>> = Vec::new();
        for (order, node) in nodes.iter().copied().enumerate() {
            let body = Object::or_empty(&node.body)?;
            let mut placed: Vec<String> = Vec::new();
            for place in placed_by.get(&node.id).map_or(&[][..], Vec::as_slice) {
                if !placed.contains(place) {
                    placed.push(place.clone());
                }
            }
            let mut proposed_by = Vec::new();
            for aid in made_by.get(&node.id).map_or(&[][..], Vec::as_slice) {
                if let Some(a) = acts.get(aid) {
                    proposed_by.push(ProposedBy {
                        act: aid.clone(),
                        act_type: a.act.clone(),
                        actor: a.actor.clone(),
                        actor_alias: named.alias(a.actor.as_deref()),
                        conversation: a.conversation.clone(),
                        conversation_name: named.name(a.conversation.as_deref()),
                        turn: a.turn.clone(),
                    });
                }
            }
            let author_alias = named.alias(node.attributed_to.as_deref());
            if !tokens.is_empty() {
                let mut hay = vec![node.id.clone(), node.kind.clone(), words_of(&author_alias)?];
                for (_, value) in &body.0 {
                    hay.extend(value.string()?);
                }
                for place in &placed {
                    hay.push(words_of(&named.name(Some(place)))?);
                }
                for by in &proposed_by {
                    hay.push(words_of(&by.actor_alias)?);
                    hay.push(words_of(&by.conversation_name)?);
                }
                let text = python::lower(&hay.join(" "))
                    .ok_or_else(|| python_says("words in newer letters"))?;
                if !tokens.iter().all(|token| text.contains(token.as_str())) {
                    continue;
                }
            }
            kept.push(Kept {
                node,
                order,
                placed,
                proposed_by,
                author_alias,
            });
        }

        // -- standing, only for what survived the search -------------------------------------
        let kept_ids: Vec<Id> = kept.iter().map(|k| Id(k.node.id.clone())).collect();
        let places_of_personas = kept
            .iter()
            .flat_map(|k| k.placed.iter())
            .filter(|place| personas.contains(*place))
            .map(|place| Id(place.clone()));
        let standing_of: Vec<Id> = kept_ids.iter().cloned().chain(places_of_personas).collect();
        let links = IncomingLinks::load(scope, &standing_of)?;

        let mut replaced: HashMap<String, Vec<String>> = HashMap::new();
        let mut challenges: Vec<Challenge> = Vec::new();
        if !kept_ids.is_empty() {
            let asked = mentis_rules::id_list(kept_ids.iter().map(|id| id.0.as_str()));
            let relation = superseding.as_deref().unwrap_or_default();
            scope.query(
                SUPERSEDES,
                &[Param::Text(&asked), Param::Text(relation)],
                &mut |row| {
                    if let (Some(from), Some(to)) = (text(row, 0)?, text(row, 1)?)
                        && matches!(row.value(2)?, Value::Null)
                    {
                        replaced.entry(from).or_default().push(to);
                    }
                    Ok(Flow::Continue)
                },
            )?;
            scope.query(CHALLENGES, &[Param::Text(&asked)], &mut |row| {
                challenges.push(Challenge {
                    to: text(row, 0)?.unwrap_or_default(),
                    id: text(row, 1)?.unwrap_or_default(),
                    from: text(row, 2)?.unwrap_or_default(),
                    relation: text(row, 3)?.unwrap_or_default(),
                    body: text(row, 4)?,
                    attributed_to: text(row, 5)?,
                    at: real(row, 6)?,
                });
                Ok(Flow::Continue)
            })?;
        }

        let mut states: HashMap<&str, (Option<&'static str>, Group)> = HashMap::new();
        let mut candidates: Vec<Id> = Vec::new();
        for k in &kept {
            let standing = links.standing(&Id(k.node.id.clone()), None);
            let (state, group) = definitions[&k.node.kind].group_of(&standing)?;
            if group == Group::Proposed {
                candidates.push(Id(k.node.id.clone()));
            }
            states.insert(k.node.id.as_str(), (state, group));
        }
        let open_requests = vocabulary::with_open_requests(scope, &candidates)?;

        // -- proposals ------------------------------------------------------------------------
        let proposing = vocabulary.proposal_relation()?;
        let mut proposals: Vec<Proposal> = Vec::new();
        if let Some(relation) = &proposing
            && !kept_ids.is_empty()
        {
            let asked = mentis_rules::id_list(kept_ids.iter().map(|id| id.0.as_str()));
            let mut raw: Vec<RawProposal> = Vec::new();
            scope.query(
                PROPOSALS,
                &[Param::Text(&asked), Param::Text(relation)],
                &mut |row| {
                    raw.push((
                        text(row, 0)?.unwrap_or_default(),
                        text(row, 1)?.unwrap_or_default(),
                        text(row, 2)?.unwrap_or_default(),
                        text(row, 3)?,
                        text(row, 4)?,
                        text(row, 5)?,
                        real(row, 6)?,
                    ));
                    Ok(Flow::Continue)
                },
            )?;
            for (id, from, to, body, attributed_to, written_by, at) in raw {
                let body = Object::or_empty(body.as_deref().unwrap_or(""))?;
                proposals.push(Proposal {
                    id,
                    from,
                    to,
                    reason: body.get_or_null("reason"),
                    attributed_to,
                    written_by,
                    at,
                });
            }
        }
        let proposal_ids: Vec<Id> = proposals.iter().map(|p| Id(p.id.clone())).collect();
        let withdrawn_links = IncomingLinks::load(scope, &proposal_ids)?;

        // Each row's two sides, as `view` cuts them, with one memo for the row.
        let mut sides: HashMap<&str, (ProposalSide, ProposalSide)> = HashMap::new();
        let mut items_named: Vec<Id> = Vec::new();
        let mut who_named: Vec<Id> = Vec::new();
        if proposing.is_some() {
            for k in &kept {
                let id = k.node.id.as_str();
                let mut memo = HashMap::new();
                let mut side = |theirs: &dyn Fn(&Proposal) -> Option<String>| {
                    let mut got = ProposalSide::default();
                    let mut rows: Vec<(&Proposal, String)> = Vec::new();
                    for proposal in &proposals {
                        if let Some(other) = theirs(proposal) {
                            if withdrawn_links.superseded(&proposal.id, None, &mut memo) {
                                got.withdrawn += 1;
                            } else {
                                rows.push((proposal, other));
                            }
                        }
                    }
                    rows.sort_by(|a, b| b.0.at.total_cmp(&a.0.at));
                    got.total = rows.len() as u64;
                    got.omitted = got.total.saturating_sub(REGISTER_PROPOSALS as u64);
                    rows.truncate(REGISTER_PROPOSALS);
                    (got, rows)
                };
                let (mut successors, rows) = side(&|p| (p.to == id).then(|| p.from.clone()));
                let mut fill = |into: &mut ProposalSide, rows: Vec<(&Proposal, String)>| {
                    for (proposal, other) in rows {
                        items_named.push(Id(other.clone()));
                        who_named.extend(
                            proposal
                                .attributed_to
                                .clone()
                                .filter(|w| !w.is_empty())
                                .map(Id),
                        );
                        into.items.push(ProposalItem {
                            entry: other,
                            link: proposal.id.clone(),
                            reason: proposal.reason.clone(),
                            attributed_to: proposal.attributed_to.clone(),
                            written_by: proposal.written_by.clone(),
                            at: proposal.at,
                            kind: None,
                            summary: None,
                            by_alias: Stored::null(),
                            stands: false,
                            state: String::new(),
                        });
                    }
                };
                fill(&mut successors, rows);
                let (mut predecessors, rows) = side(&|p| (p.from == id).then(|| p.to.clone()));
                fill(&mut predecessors, rows);
                sides.insert(id, (successors, predecessors));
            }
        }
        items_named.sort();
        items_named.dedup();

        let mut said: HashMap<String, Said> = HashMap::new();
        if !items_named.is_empty() {
            let asked = mentis_rules::id_list(items_named.iter().map(|id| id.0.as_str()));
            scope.query(SAID, &[Param::Text(&asked)], &mut |row| {
                let version = match row.value(2)? {
                    Value::Integer(version) => Some(version),
                    _ => None,
                };
                said.insert(
                    text(row, 0)?.unwrap_or_default(),
                    Said {
                        kind: text(row, 1)?,
                        version,
                        body: text(row, 3)?.unwrap_or_default(),
                    },
                );
                Ok(Flow::Continue)
            })?;
        }
        let item_links = IncomingLinks::load(scope, &items_named)?;

        // `_alias` reads everybody through `presented`, whichever Kind they are, and raises where
        // that does: the people behind the proposals and the challenges.
        who_named.extend(
            challenges
                .iter()
                .filter_map(|c| c.attributed_to.clone())
                .filter(|who| !who.is_empty())
                .map(Id),
        );
        who_named.sort();
        who_named.dedup();
        let who = mentis_rules::reads(scope, &who_named, Versioned::All)?;
        for one in who.values() {
            if one.reading.python_says {
                return Err(python_says("somebody this can't read"));
            }
        }

        // -- the rows -------------------------------------------------------------------------
        let mut rows: Vec<(usize, GovernedRow, Group)> = Vec::with_capacity(kept.len());
        for k in kept {
            let node = k.node;
            let definition = &definitions[&node.kind];
            let body = Object::or_empty(&node.body)?;
            let fields = fields_for(&vocabulary, &node.kind, node.version, definition)?;
            let (principal, second) = summary(&body, fields)?;
            let standing = links.standing(&Id(node.id.clone()), None);
            let (state, mut group) = states[node.id.as_str()];
            if group == Group::Proposed && !open_requests.contains(&node.id) {
                group = Group::Recorded;
            }
            let disputed_by: Vec<String> = standing
                .incoming
                .iter()
                .find(|(relation, _)| relation == "disputes")
                .map_or_else(Vec::new, |(_, ids)| {
                    ids.iter().map(|id| id.0.clone()).collect()
                });
            let open_disputes = if disputed_by.is_empty() {
                Vec::new()
            } else {
                open_challenges(&challenges, &node.id)?
            };

            let mut placed = Vec::with_capacity(k.placed.len());
            for c in &k.placed {
                let name = named.name(Some(c));
                let is_persona = personas.contains(c);
                let carried_by = if is_persona {
                    let shown = match name.truthy() {
                        Some(false) => c.clone(),
                        Some(true) => name
                            .string()?
                            .ok_or_else(|| python_says("a Persona's name that isn't text"))?,
                        None => return Err(python_says("a Persona's name this can't read")),
                    };
                    Some(if links.standing(&Id(c.clone()), None).stands {
                        format!("carried by Persona {shown}")
                    } else {
                        format!(
                            "placed on Persona {shown}, which does not stand; it carries nothing"
                        )
                    })
                } else {
                    None
                };
                placed.push(Placed {
                    conversation: c.clone(),
                    name,
                    whole_brain: whole_brain.contains(c).then_some(true),
                    persona: is_persona.then_some(true),
                    destination_kind: is_persona.then(|| "persona".to_owned()),
                    carried_by,
                });
            }

            let mut proposed = None;
            let mut proposed_reach = Vec::new();
            if let Some(relation) = &proposing {
                let (mut successors, mut predecessors) =
                    sides.remove(node.id.as_str()).unwrap_or_default();
                for side in [&mut successors, &mut predecessors] {
                    for item in &mut side.items {
                        let (kind, words) = said_of(&vocabulary, said.get(&item.entry))?;
                        item.kind = kind;
                        item.summary = words;
                        let standing = item_links.standing(&Id(item.entry.clone()), None);
                        item.stands = standing.stands;
                        item.state = standing_state(&standing).to_owned();
                        item.by_alias = alias_any(&who, item.attributed_to.as_deref())?;
                    }
                }
                for proposal in proposals.iter().filter(|p| p.from == node.id) {
                    for place in placed_by.get(&proposal.to).map_or(&[][..], Vec::as_slice) {
                        proposed_reach.push(place.clone());
                    }
                }
                proposed_reach.sort();
                proposed_reach.dedup();
                proposed = Some(Proposed {
                    entry: node.id.clone(),
                    relation: relation.clone(),
                    successors,
                    predecessors,
                    confers: CONFERS.to_owned(),
                });
            }

            rows.push((
                k.order,
                GovernedRow {
                    entry: node.id.clone(),
                    kind: node.kind.clone(),
                    standing_apt: definition.standing_apt.clone(),
                    knowing: definition.knowing.clone(),
                    governs: definition.ground()? == Ground::DirectsWork,
                    summary: principal,
                    secondary: second,
                    attributed_to: node.attributed_to.clone(),
                    author_alias: k.author_alias,
                    at: node.at,
                    placed_at: placed,
                    proposed_by: k.proposed_by,
                    established_by: standing
                        .established_by
                        .iter()
                        .map(|id| id.0.clone())
                        .collect(),
                    superseded_by: standing
                        .superseded_by
                        .iter()
                        .map(|id| id.0.clone())
                        .collect(),
                    supersedes: replaced.remove(&node.id).unwrap_or_default(),
                    disputed_by,
                    open_disputes,
                    proposed,
                    proposed_reach,
                    state: state.map(str::to_owned),
                    group: group.name().to_owned(),
                },
                group,
            ));
        }

        if let Some(wanted) = wanted_group {
            rows.retain(|(_, _, group)| *group == wanted);
        }
        // Newest first, and the later-written first among equal times: `sort(reverse=True)` of the
        // pair.
        rows.sort_by(|a, b| b.1.at.total_cmp(&a.1.at).then_with(|| b.0.cmp(&a.0)));
        let matched = rows.len() as u64;

        let mut totals: ByGroup<u64> = ByGroup::default();
        for (_, _, group) in &rows {
            *totals.of(*group) += 1;
        }
        let mut groups: ByGroup<Vec<GovernedRow>> = ByGroup::default();
        let mut next_cursor = None;
        let cap_rows = cap as usize;
        match offset {
            None => {
                for (_, row, group) in rows {
                    let held = groups.of(group);
                    if held.len() < cap_rows {
                        held.push(row);
                    }
                }
            }
            Some(offset) => {
                let end = offset.saturating_add(cap_rows);
                let taken = rows.len().min(end).saturating_sub(offset);
                for (_, row, group) in rows.into_iter().skip(offset).take(cap_rows) {
                    groups.of(group).push(row);
                }
                let at = offset.saturating_add(taken) as u64;
                next_cursor = Some((at < matched).then(|| format!("g1.{at}")));
            }
        }
        let mut omitted: ByGroup<u64> = ByGroup::default();
        for group in [
            Group::Proposed,
            Group::Recorded,
            Group::Standing,
            Group::History,
            Group::Unknown,
        ] {
            *omitted.of(group) = *totals.of(group) - groups.of(group).len() as u64;
        }

        let more = next_cursor.clone().flatten().map(Cursor);
        let is_declined = kind.as_ref().is_some_and(|kind| declined.contains(kind));
        let walked = nodes.len() as u64;
        let standing_apt_unknown = unknown
            .iter()
            .filter(|name| !walk.contains(name))
            .map(|name| KindCount {
                kind: name.clone(),
                entries: counts.get(name).copied().unwrap_or(0),
            })
            .collect();
        let page = GovernedPage {
            query: GovernedQuery {
                kind,
                q,
                state,
                limit: cap,
                cursor: request.cursor.as_ref().map(|Cursor(c)| c.clone()),
            },
            groups,
            totals,
            omitted,
            matched,
            next_cursor,
            walked,
            kinds: GovernedKinds {
                listed,
                walked: Counts(per_kind),
                directs_work,
                standing_knowledge,
                standing_not_meaningful: declined,
                standing_apt_unknown,
            },
            why_not: is_declined.then(|| NOT_GOVERNED.to_owned()),
        };
        Ok(ReadAnswer {
            rows: vec![page],
            as_of,
            more,
            not_searched: Vec::new(),
        })
    }
}

/// A proposal's other side, as `_said` reads it.
struct Said {
    kind: Option<String>,
    version: Option<i64>,
    body: String,
}

/// `_said`: a Kind and its principal statement, or nothing for what the record doesn't hold.
fn said_of(
    vocabulary: &Vocabulary,
    entry: Option<&Said>,
) -> Result<(Option<String>, Option<String>), OpError> {
    let Some(entry) = entry else {
        return Ok((None, None));
    };
    let kind = entry.kind.clone();
    let body = Object::or_empty(&entry.body)?;
    // `pinned.get("body") or {}`: this read has no second place to take fields from.
    let fields = match kind.as_deref() {
        Some(kind) => vocabulary
            .pinned_fields(kind, entry.version)
            .cloned()
            .unwrap_or_else(|| Stored::of(&Vec::<String>::new())),
        None => Stored::of(&Vec::<String>::new()),
    };
    for key in declared_then_rest(&body, &fields)? {
        if let Some(value) = body.get(&key)
            && let Some(words) = value.string()?
        {
            let words = python::strip(&words);
            if !words.is_empty() {
                return Ok((kind, Some(words.to_owned())));
            }
        }
    }
    Ok((kind, None))
}

/// `governance._alias`: anybody's, as they now read, `or` themselves.
fn alias_any(seen: &HashMap<Id, Seen>, who: Option<&str>) -> Result<Stored, OpError> {
    let Some(who) = who.filter(|who| !who.is_empty()) else {
        return Ok(Stored::null());
    };
    let Some(one) = seen.get(&Id(who.to_owned())) else {
        return Ok(Stored::of(&who));
    };
    let body = Object::or_empty(&one.reading.body_json)?;
    match body.get("alias") {
        Some(alias)
            if alias
                .truthy()
                .ok_or_else(|| python_says("an alias this can't read"))? =>
        {
            Ok(alias.clone())
        }
        _ => Ok(Stored::of(&who)),
    }
}

/// `[d["disputed_by"] for d in disputes_of(corpus, entry) if d["open"]]`, sorted by time as it is.
fn open_challenges(challenges: &[Challenge], entry: &str) -> Result<Vec<String>, OpError> {
    let mut set_aside: HashSet<String> = HashSet::new();
    let mut taken_back: HashSet<String> = HashSet::new();
    let mut disputes: Vec<&Challenge> = Vec::new();
    for c in challenges.iter().filter(|c| c.to == entry) {
        match c.relation.as_str() {
            "supports" => {
                let body = Object::or_empty(c.body.as_deref().unwrap_or(""))?;
                if body.is_truthy("sets_aside")? {
                    set_aside.extend(body.text("sets_aside")?);
                }
            }
            "withdraws" => {
                let body = Object::or_empty(c.body.as_deref().unwrap_or(""))?;
                if body.is_truthy("dispute")? {
                    taken_back.extend(body.text("dispute")?);
                }
            }
            _ => disputes.push(c),
        }
    }
    disputes.sort_by(|a, b| a.at.total_cmp(&b.at));
    Ok(disputes
        .into_iter()
        .filter(|d| !set_aside.contains(&d.id) && !taken_back.contains(&d.id))
        .map(|d| d.from.clone())
        .collect())
}
