//! Durable R4.2 view foundations.  These are the small record-only projections shared by the
//! owner HTTP routes; live expectation booleans remain in [`crate::overlay`], where the durable
//! read and poll marker are checked in one scope.
//!
//! **Python's exact bytes, or nothing.** A field here is computed as Python computes it, or the
//! whole read is [`python_says`] and the route forwards. No field is filled with a null, a false or
//! an empty list because this can't work it out: each constant below is one a guard has proved.

use std::collections::{HashMap, HashSet};

use mentis_record::{Flow, Id, Param, ReadScope, Value};
use mentis_rules::{alias_reads, id_list, lines_of, now_reads, standing_many};

use crate::acts::Act;
use crate::expectation_states::{ExpectationState, ExpectationStates, ExpectationStatesArgs};
use crate::forms::{self, Form};
use crate::overlay::{Overlay, execution_bool};
use crate::pyjson::{Py, dict, loads};
use crate::python;
use crate::stored::python_says;
use crate::window::{classify, reads};
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest};

/// An answer already in Python's JSON shape. Adapters use [`Py::dumps`]; this implementation only
/// satisfies the read catalogue's row bound.
#[derive(Debug)]
pub struct ViewRow(pub Py);

impl serde::Serialize for ViewRow {
    fn serialize<S: serde::Serializer>(&self, to: S) -> Result<S::Ok, S::Error> {
        to.serialize_str(&self.0.dumps())
    }
}

const PERSONAS: &str = "SELECT id, body FROM entry WHERE family = 'entry' AND def_name = 'persona' \
    AND link_relation IS NULL ORDER BY seq";
const ROOT_KIND: &str = "SELECT def_name FROM entry WHERE id = ?1 LIMIT 1";
const LINKS_TO: &str = "SELECT id, link_from FROM entry WHERE link_relation = ?1 AND link_to = ?2 \
    ORDER BY seq";
const TOPICS: &str = "SELECT e.id FROM entry l JOIN entry e ON e.id = l.link_from \
    WHERE l.link_relation = 'topic-of' AND l.link_to = ?1 ORDER BY e.recorded_at, e.seq";
const TOPIC_TURNS: &str = "SELECT COUNT(DISTINCT link_from) FROM entry WHERE link_relation = \
    'about-topic' AND link_to = ?1 AND id NOT IN (SELECT link_to FROM entry WHERE link_relation = \
    (SELECT body FROM entry WHERE def_name = 'superseding-relation' LIMIT 1))";
const RUNTIME_DEFAULTS: &str = "SELECT id, body, recorded_at FROM entry WHERE family = 'entry' \
    AND def_name = 'runtime-default' AND link_relation IS NULL ORDER BY seq";

fn text(
    row: &dyn mentis_record::Row,
    n: usize,
) -> Result<Option<String>, mentis_record::RecordError> {
    match row.value(n)? {
        Value::Null => Ok(None),
        Value::Text(bytes) => std::str::from_utf8(bytes)
            .map(|s| Some(s.to_owned()))
            .map_err(|_| mentis_record::RecordError::Sqlite {
                detail: format!("column {n} is not UTF-8"),
            }),
        _ => Err(mentis_record::RecordError::Sqlite {
            detail: format!("column {n} is not text"),
        }),
    }
}

fn py_body(text: &str) -> Result<Py, OpError> {
    loads(text).ok_or_else(|| python_says("a body this cannot read"))
}

fn body_text(body: &Py, key: &str) -> Result<Option<String>, OpError> {
    if !body.is_dict() {
        return Err(python_says("a body that is not an object"));
    }
    match body.get(key) {
        None | Some(Py::None) => Ok(None),
        Some(Py::Str(value)) => Ok(Some(value.clone())),
        _ => Err(python_says("a field that is not text")),
    }
}

fn standing(
    scope: &mut dyn ReadScope,
    ids: &[String],
) -> Result<HashMap<String, mentis_rules::Standing>, OpError> {
    let asked: Vec<Id> = ids.iter().cloned().map(Id).collect();
    Ok(standing_many(scope, &asked, None)?
        .into_iter()
        .map(|(id, row)| (id.0, row))
        .collect())
}

/// `Conversations.alias`, for each of these.
fn aliases(scope: &mut dyn ReadScope, ids: &[String]) -> Result<HashMap<String, String>, OpError> {
    let asked: Vec<Id> = ids.iter().cloned().map(Id).collect();
    let mut out = HashMap::new();
    for (id, read) in alias_reads(scope, &asked)? {
        let name = match read {
            Some(Some(alias)) => alias,
            Some(None) => id.0.clone(),
            None => return Err(python_says("a participant alias this cannot read")),
        };
        out.insert(id.0, name);
    }
    Ok(out)
}

/// Each once, where it first came.
fn once(ids: impl IntoIterator<Item = String>) -> Vec<String> {
    let mut seen = HashSet::new();
    ids.into_iter()
        .filter(|id| seen.insert(id.clone()))
        .collect()
}

fn expectation_states(
    scope: &mut dyn ReadScope,
    ids: Vec<String>,
) -> Result<Vec<ExpectationState>, OpError> {
    let asked = ReadRequest {
        args: ExpectationStatesArgs { ids },
        cursor: None,
        limit: None,
        deadline: std::time::Instant::now() + std::time::Duration::from_secs(5),
    };
    Ok(ExpectationStates.read(scope, &asked)?.rows)
}

#[derive(Clone, Copy, Debug, Default)]
pub struct Personas;

impl ReadOp for Personas {
    type Args = ();
    type Row = ViewRow;
    const NAME: &'static str = "personas";
    const BUDGET: Budget = Budget { statements: 2 };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        _: &ReadRequest<()>,
    ) -> Result<ReadAnswer<ViewRow>, OpError> {
        let mut raw = Vec::new();
        scope.query(PERSONAS, &[], &mut |row| {
            raw.push((
                text(row, 0)?.unwrap_or_default(),
                text(row, 1)?.unwrap_or_default(),
            ));
            Ok(Flow::Continue)
        })?;
        let ids: Vec<String> = raw.iter().map(|(id, _)| id.clone()).collect();
        let states = standing(scope, &ids)?;
        let mut rows = Vec::new();
        for (id, body) in raw {
            if !states.get(&id).is_some_and(|state| state.stands) {
                continue;
            }
            let body = py_body(&body)?;
            rows.push(dict([
                ("persona", Py::str(id)),
                ("name", Py::opt_str(body_text(&body, "name")?.as_deref())),
                (
                    "behaviour",
                    Py::opt_str(body_text(&body, "behaviour")?.as_deref()),
                ),
                (
                    "about",
                    Py::str(body_text(&body, "about")?.unwrap_or_default()),
                ),
                ("stands", Py::Bool(true)),
            ]));
        }
        Ok(ReadAnswer {
            rows: vec![ViewRow(dict([("personas", Py::List(rows))]))],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

#[derive(Clone, Debug)]
pub struct ConversationFieldsArgs {
    pub conversation: String,
    pub fields: Vec<String>,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct ConversationFields;

impl ReadOp for ConversationFields {
    type Args = ConversationFieldsArgs;
    type Row = ViewRow;
    const NAME: &'static str = "conversation-fields";
    const BUDGET: Budget = Budget { statements: 13 };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<ViewRow>, OpError> {
        let id = &request.args.conversation;
        let mut kind = None;
        scope.query(ROOT_KIND, &[Param::Text(id)], &mut |row| {
            kind = text(row, 0)?;
            Ok(Flow::Stop)
        })?;
        if kind.as_deref() != Some("conversation") {
            return Err(OpError::NotFound { what: id.clone() });
        }
        let reads = now_reads(scope, &[Id(id.clone())])?;
        let now = reads
            .get(&Id(id.clone()))
            .ok_or_else(|| OpError::NotFound { what: id.clone() })?;
        if now.python_says {
            return Err(python_says("a Conversation version this cannot read"));
        }
        let body = py_body(&now.body_json)?;
        let mut out = dict([("id", Py::str(id))]);
        if request.args.fields.iter().any(|f| f == "name") {
            // `conv["body"]["name"]`, which raises where it is missing.
            if body.get("name").is_none() {
                return Err(python_says("a Conversation with no name"));
            }
            out.set("name", Py::opt_str(body_text(&body, "name")?.as_deref()));
        }
        if request.args.fields.iter().any(|f| f == "about") {
            out.set("about", Py::opt_str(body_text(&body, "about")?.as_deref()));
        }
        if request.args.fields.iter().any(|f| f == "participants") {
            out.set("participants", participants(scope, id)?);
        }
        if request.args.fields.iter().any(|f| f == "topics") {
            out.set("topics", topics(scope, id)?);
        }
        Ok(ReadAnswer {
            rows: vec![ViewRow(out)],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

fn participants(scope: &mut dyn ReadScope, conversation: &str) -> Result<Py, OpError> {
    let mut links = Vec::new();
    scope.query(
        LINKS_TO,
        &[Param::Text("participates-in"), Param::Text(conversation)],
        &mut |row| {
            links.push((
                text(row, 0)?.unwrap_or_default(),
                text(row, 1)?.unwrap_or_default(),
            ));
            Ok(Flow::Continue)
        },
    )?;
    let link_ids: Vec<String> = links.iter().map(|x| x.0.clone()).collect();
    let live_links = standing(scope, &link_ids)?;
    let mut ids: Vec<String> = links
        .into_iter()
        .filter(|(link, _)| {
            !live_links
                .get(link)
                .is_some_and(|s| !s.superseded_by.is_empty())
        })
        .map(|(_, p)| p)
        .collect();
    ids.sort();
    ids.dedup();
    let names = aliases(scope, &ids)?;

    let mut declarations = Vec::new();
    scope.query(RUNTIME_DEFAULTS, &[], &mut |row| {
        let at = match row.value(2)? {
            Value::Real(v) => v,
            Value::Integer(v) => v as f64,
            _ => 0.0,
        };
        declarations.push((
            text(row, 0)?.unwrap_or_default(),
            text(row, 1)?.unwrap_or_default(),
            at,
        ));
        Ok(Flow::Continue)
    })?;
    let declaration_ids: Vec<String> = declarations.iter().map(|x| x.0.clone()).collect();
    let declaration_states = standing(scope, &declaration_ids)?;
    let mut latest: HashMap<String, (String, Option<String>, f64)> = HashMap::new();
    for (entry, raw, at) in declarations {
        if !declaration_states.get(&entry).is_some_and(|s| s.stands) {
            continue;
        }
        let body = py_body(&raw)?;
        let Some(participant) = body_text(&body, "participant")? else {
            continue;
        };
        let runtime = body_text(&body, "runtime")?;
        if latest.get(&participant).is_none_or(|held| at > held.2) {
            latest.insert(participant, (entry, runtime, at));
        }
    }
    let rows = ids
        .into_iter()
        .map(|id| {
            let mut row = dict([
                ("participant", Py::str(&id)),
                (
                    "alias",
                    Py::str(names.get(&id).cloned().unwrap_or_else(|| id.clone())),
                ),
            ]);
            match latest.get(&id) {
                None => {
                    row.set("default_runtime", Py::None);
                    row.set("runtime_mode", Py::str("undeclared"));
                }
                Some((entry, runtime, _)) => {
                    row.set("default_runtime", Py::opt_str(runtime.as_deref()));
                    row.set(
                        "runtime_mode",
                        Py::str(if runtime.is_some() { "default" } else { "auto" }),
                    );
                    row.set("runtime_declaration", Py::str(entry));
                }
            }
            row
        })
        .collect();
    Ok(Py::List(rows))
}

fn topics(scope: &mut dyn ReadScope, conversation: &str) -> Result<Py, OpError> {
    let mut ids = Vec::new();
    scope.query(TOPICS, &[Param::Text(conversation)], &mut |row| {
        ids.push(text(row, 0)?.unwrap_or_default());
        Ok(Flow::Continue)
    })?;
    ids.dedup();
    let asked: Vec<Id> = ids.iter().cloned().map(Id).collect();
    let reads = now_reads(scope, &asked)?;
    let mut rows = Vec::new();
    for id in ids {
        let Some(read) = reads.get(&Id(id.clone())) else {
            continue;
        };
        if read.python_says {
            return Err(python_says("a Topic version this cannot read"));
        }
        let body = py_body(&read.body_json)?;
        // `t["body"]["name"]` and `["about"]`, which raise where they are missing.
        if body.get("name").is_none() || body.get("about").is_none() {
            return Err(python_says("a Topic missing a field"));
        }
        let mut count = 0i64;
        scope.query(TOPIC_TURNS, &[Param::Text(&id)], &mut |row| {
            count = row.value(0)?.integer().unwrap_or_default();
            Ok(Flow::Stop)
        })?;
        rows.push(dict([
            ("id", Py::str(id)),
            ("name", Py::opt_str(body_text(&body, "name")?.as_deref())),
            ("about", Py::opt_str(body_text(&body, "about")?.as_deref())),
            ("turns", Py::int(count)),
        ]));
    }
    Ok(Py::List(rows))
}

const TURN: &str = "SELECT id, family, def_name, body, attributed_to, written_by, recorded_at, \
    link_relation FROM entry WHERE id = ?1 LIMIT 1";
const TURN_ACTS: &str = "SELECT id, act, at, actor, conversation, turn, execution, runtime, because, \
    caused_by, about, detail FROM operational WHERE turn = ?1 ORDER BY seq";
const TURN_LINKS_FROM: &str = "SELECT id, link_to, link_relation, attributed_to, recorded_at FROM entry \
    WHERE link_from = ?1 AND link_relation IS NOT NULL ORDER BY seq";
const TURN_LINKS_TO: &str = "SELECT id, link_from, link_relation, attributed_to, recorded_at FROM entry \
    WHERE link_to = ?1 AND link_relation IS NOT NULL ORDER BY seq";
const TURN_DELIVERIES: &str = "SELECT id, execution, conversation, participant, runtime, mechanism, \
    at, material, behavioural_sources, operation_ok FROM delivery WHERE material LIKE ?1 ORDER BY seq";
const DELIVERED_TO: &str = "SELECT material FROM delivery WHERE participant = ?1 AND material LIKE ?2 \
    ORDER BY seq";
const CONVERSATION_TURNS: &str = "SELECT DISTINCT e.id, e.recorded_at, e.seq FROM entry l JOIN entry e \
    ON e.id = l.link_from WHERE l.link_relation = 'in-conversation' AND l.link_to = ?1 \
    AND e.family = 'entry' AND e.def_name = 'contribution' AND e.link_relation IS NULL \
    ORDER BY e.recorded_at, e.seq";

#[derive(Clone, Debug)]
pub struct TurnViewArgs {
    pub turn: String,
    pub overlay: Overlay,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct TurnView;

struct TurnEntry {
    by: Option<String>,
    written_by: Option<String>,
    at: f64,
    body: String,
}

impl ReadOp for TurnView {
    type Args = TurnViewArgs;
    type Row = ViewRow;
    const NAME: &'static str = "turn-view";
    const BUDGET: Budget = Budget { statements: 120 };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<ViewRow>, OpError> {
        let row = turn_view(scope, &request.args.turn, &request.args.overlay, None)?;
        Ok(ReadAnswer {
            rows: vec![ViewRow(row)],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

/// The record's row, for a Turn. No row is [`OpError::NotFound`], Python's `IndexError`. A row that
/// is not a Turn gets `KeyError` or something further on from Python, which is Python's to word.
fn turn_entry(scope: &mut dyn ReadScope, id: &str) -> Result<TurnEntry, OpError> {
    let mut got = None;
    let mut held = false;
    scope.query(TURN, &[Param::Text(id)], &mut |row| {
        held = true;
        let family = text(row, 1)?.unwrap_or_default();
        let kind = text(row, 2)?;
        let is_link = !matches!(row.value(7)?, Value::Null);
        if family == "entry" && kind.as_deref() == Some("contribution") && !is_link {
            let at = match row.value(6)? {
                Value::Real(v) => v,
                Value::Integer(v) => v as f64,
                _ => 0.0,
            };
            got = Some(TurnEntry {
                by: text(row, 4)?,
                written_by: text(row, 5)?,
                at,
                body: text(row, 3)?.unwrap_or_default(),
            });
        }
        Ok(Flow::Stop)
    })?;
    if !held {
        return Err(OpError::NotFound {
            what: id.to_owned(),
        });
    }
    got.ok_or_else(|| python_says("an entry that is not a Turn"))
}

/// Whether anything supersedes this entry or it supersedes anything: edited, deleted, or itself a
/// later version, which `history_view` reads back to the root's whole line.
fn on_an_edited_line(scope: &mut dyn ReadScope, turn: &str) -> Result<bool, OpError> {
    let id = Id(turn.to_owned());
    let line = lines_of(scope, std::slice::from_ref(&id))?
        .remove(&id)
        .ok_or_else(|| OpError::NotFound {
            what: turn.to_owned(),
        })?;
    Ok(line.root != turn || line.versions.len() != 1 || line.deletion.is_some())
}

fn acts(scope: &mut dyn ReadScope, turn: &str) -> Result<Vec<Act>, OpError> {
    let mut out = Vec::new();
    scope.query(TURN_ACTS, &[Param::Text(turn)], &mut |row| {
        out.push(Act::read(row, 0)?);
        Ok(Flow::Continue)
    })?;
    Ok(out)
}

fn act_py(act: &Act) -> Result<Py, OpError> {
    Ok(dict([
        ("id", Py::str(&act.id)),
        ("at", Py::Float(act.at)),
        ("actor", Py::opt_str(act.actor.as_deref())),
        ("act", Py::opt_str(act.act.as_deref())),
        ("conversation", Py::opt_str(act.conversation.as_deref())),
        ("turn", Py::opt_str(act.turn.as_deref())),
        ("execution", Py::opt_str(act.execution.as_deref())),
        ("runtime", Py::opt_str(act.runtime.as_deref())),
        ("because", Py::opt_str(act.because.as_deref())),
        ("caused_by", Py::opt_str(act.caused_by.as_deref())),
        ("about", py_body(act.about()?.text())?),
        ("detail", py_body(act.detail()?.text())?),
    ]))
}

/// `next(a["detail"]["chose"] for a in acts if a["act"] == "turn-said" and detail.get("chose"))`.
fn chose_of(ops: &[Act]) -> Result<Py, OpError> {
    for act in ops.iter().filter(|act| act.is("turn-said")) {
        let detail = act.detail_object()?;
        if detail.is_truthy("chose")? {
            return py_body(detail.get_or_null("chose").text());
        }
    }
    Ok(Py::None)
}

fn number_in(scope: &mut dyn ReadScope, turn: &str) -> Result<Option<i64>, OpError> {
    let homes = reads::homes_of(scope, &[turn])?;
    Ok(reads::numbers_of(scope, &homes)?.get(turn).copied())
}

fn aliases_for_states(
    scope: &mut dyn ReadScope,
    states: &[ExpectationState],
    also: &[String],
) -> Result<HashMap<String, String>, OpError> {
    let mut ids = also.to_vec();
    for state in states {
        if let Some(id) = &state.expected_of {
            ids.push(id.clone());
        }
        if let Some(id) = &state.recorded_by {
            ids.push(id.clone());
        }
        if let Some(w) = &state.withdrawn
            && let Some(id) = &w.by
        {
            ids.push(id.clone());
        }
        if let Some(l) = &state.lapsed
            && let Some(id) = &l.by
        {
            ids.push(id.clone());
        }
    }
    ids.sort();
    ids.dedup();
    aliases(scope, &ids)
}

/// `_answering_reply`. The newest reply by whoever carries it, as it now reads.
fn answered_by(scope: &mut dyn ReadScope, state: &ExpectationState) -> Result<Py, OpError> {
    let mut ids = Vec::with_capacity(state.replies_from_expected.len());
    for id in &state.replies_from_expected {
        ids.push(
            id.string()?
                .ok_or_else(|| python_says("an answering reply that isn't an id"))?,
        );
    }
    let asked: Vec<&str> = ids.iter().map(String::as_str).collect();
    let heads = reads::heads(scope, &asked)?;
    // `max` keeps the first of equal times.
    let mut newest: Option<(&str, &reads::Head)> = None;
    for id in &asked {
        if let Some(head) = heads.get(*id)
            && newest.is_none_or(|(_, held)| {
                reads::as_f64(&head.recorded_at) > reads::as_f64(&held.recorded_at)
            })
        {
            newest = Some((id, head));
        }
    }
    let Some((reply, head)) = newest else {
        return Ok(Py::None);
    };
    let id = Id(reply.to_owned());
    let reading = now_reads(scope, std::slice::from_ref(&id))?
        .remove(&id)
        .ok_or_else(|| python_says("an answering reply this cannot read"))?;
    if reading.python_says {
        return Err(python_says("an answering reply this cannot read"));
    }
    let body = py_body(&reading.body_json)?;
    let parts = match body.get("parts") {
        None | Some(Py::None) => Vec::new(),
        Some(Py::List(parts)) => parts.clone(),
        Some(_) => return Err(python_says("a reply's parts that are not a list")),
    };
    let mut said = Vec::new();
    for part in &parts {
        if !part.is_dict() {
            return Err(python_says("a reply's part that is not an object"));
        }
        if part.get("type").and_then(Py::as_str) == Some("text") {
            match part.get("text") {
                None | Some(Py::None) => said.push(""),
                Some(Py::Str(words)) => said.push(words.as_str()),
                Some(_) => return Err(python_says("a reply's text that is not text")),
            }
        }
    }
    let joined = said.join(" ");
    let number = number_in(scope, reply)?;
    let ops = acts(scope, reply)?;
    let withdrew = match &state.withdrawn {
        Some(w) => w.reply.string()?.as_deref() == Some(reply),
        None => false,
    };
    Ok(dict([
        ("turn", Py::str(reply)),
        ("number", number.map_or(Py::None, Py::int)),
        ("said", Py::str(python::strip(&joined))),
        ("author", Py::opt_str(head.attributed_to.as_deref())),
        ("chose", chose_of(&ops)?),
        ("withdrawn", Py::Bool(withdrew)),
    ]))
}

/// The post an ask is shown on, for `continues_work`: `entry["id"]` and `entry["attributed_to"]`.
#[derive(Clone, Copy)]
struct AskedOn<'a> {
    turn: &'a str,
    author: Option<&'a str>,
}

/// `continues_work`, where this can prove it false. `continuation_candidates` keeps only expectations
/// its requester recorded, nobody claimed met and its carrier carries, each found on the Turn or the
/// one it answers, or one step up `caused_by`. Taken over every such place, with no `steps_up` and no
/// authority yet read, that is at least what Python would keep: if none is left, Python has none. If
/// one is, whether it counts is Python's to say.
fn continues_work(
    scope: &mut dyn ReadScope,
    state: &ExpectationState,
    entry: Option<AskedOn<'_>>,
) -> Result<bool, OpError> {
    let (Some(entry), Some(requester)) = (entry, state.expected_of.as_deref()) else {
        return Ok(false);
    };
    if entry.author == Some(requester) {
        return Ok(false);
    }
    let mut turns = vec![entry.turn.to_owned()];
    for link in reads::links_from(scope, reads::REPLIES_TO, &[entry.turn])? {
        turns.push(link.to);
    }
    let mut candidates = Vec::new();
    for turn in once(turns) {
        for act in acts(scope, &turn)? {
            if act.is("expectation-recorded") {
                candidates.extend(act.caused_by.clone().filter(|cause| !cause.is_empty()));
                candidates.push(act.id);
            }
        }
    }
    let found = expectation_states(scope, once(candidates))?;
    if found.iter().any(|candidate| {
        candidate.recorded_by.as_deref() == Some(requester)
            && candidate.satisfied_by.is_empty()
            && candidate.expected_of.as_deref() == entry.author
    }) {
        return Err(python_says("an ask whose answer may continue work"));
    }
    Ok(false)
}

fn expectation_py(
    scope: &mut dyn ReadScope,
    state: &ExpectationState,
    overlay: &Overlay,
    names: &HashMap<String, String>,
    entry: Option<AskedOn<'_>>,
) -> Result<Py, OpError> {
    let mut unresolved = None;
    let sql = "SELECT because FROM operational WHERE caused_by = ?1 AND act = 'assignment-unresolved' ORDER BY seq";
    scope.query(sql, &[Param::Text(&state.expectation)], &mut |row| {
        unresolved = text(row, 0)?;
        Ok(Flow::Stop)
    })?;
    let alias =
        |id: Option<&String>| id.map(|id| names.get(id).cloned().unwrap_or_else(|| id.clone()));
    let answered = answered_by(scope, state)?;
    let continues = continues_work(scope, state, entry)?;
    let mut out = dict([
        ("id", Py::str(&state.expectation)),
        ("expects", py_body(state.expects.text())?),
        ("of", Py::opt_str(state.expected_of.as_deref())),
        (
            "of_alias",
            Py::opt_str(alias(state.expected_of.as_ref()).as_deref()),
        ),
        ("by", Py::opt_str(state.recorded_by.as_deref())),
        (
            "by_alias",
            Py::opt_str(alias(state.recorded_by.as_ref()).as_deref()),
        ),
        ("because", Py::opt_str(state.because.as_deref())),
        ("options", py_body(state.options.text())?),
        (
            "material",
            Py::List(
                state
                    .material
                    .iter()
                    .map(|v| py_body(v.text()))
                    .collect::<Result<_, _>>()?,
            ),
        ),
        ("response_present", Py::Bool(state.response_present)),
        (
            "live_execution",
            Py::Bool(execution_bool(overlay, state, scope)?),
        ),
        ("unassigned", Py::Bool(state.unassigned)),
        ("unresolved_because", Py::opt_str(unresolved.as_deref())),
        (
            "satisfied_by",
            Py::List(state.satisfied_by.iter().map(Py::str).collect()),
        ),
        (
            "withdrawn",
            match &state.withdrawn {
                None => Py::None,
                Some(w) => {
                    let mut v = serde_py(w)?;
                    v.set("by_alias", Py::opt_str(alias(w.by.as_ref()).as_deref()));
                    v
                }
            },
        ),
        (
            "lapsed",
            match &state.lapsed {
                None => Py::None,
                Some(l) => {
                    let mut v = serde_py(l)?;
                    v.set("by_alias", Py::opt_str(alias(l.by.as_ref()).as_deref()));
                    v
                }
            },
        ),
        ("answered_by", answered),
        ("delegations", serde_py(&state.delegations)?),
        ("failures", serde_py(&state.failures)?),
        (
            "requires",
            Py::List(
                state
                    .requires
                    .iter()
                    .map(|v| py_body(v.text()))
                    .collect::<Result<_, _>>()?,
            ),
        ),
        ("stopped_work", Py::None),
        ("continues_work", Py::Bool(continues)),
    ]);
    if let Some(form) = &state.form {
        out.set("form", py_body(form.text())?);
        out.set("index", py_body(state.index.as_ref().unwrap().text())?);
        out.set(
            "question",
            py_body(state.question.as_ref().unwrap().text())?,
        );
        out.set("answer", serde_py(&state.answer)?);
    }
    Ok(out)
}

fn serde_py<T: serde::Serialize>(value: &T) -> Result<Py, OpError> {
    py_body(&serde_json::to_string(value).map_err(|_| python_says("a value this cannot encode"))?)
}

/// `decision_form`'s answer, which has no `cursor`: that is `history set=<form>`'s, for the worker.
fn forms_py(forms: &[Form]) -> Result<Py, OpError> {
    let mut out = Vec::with_capacity(forms.len());
    for form in forms {
        let mut row = serde_py(form)?;
        if let Py::Dict(items) = &mut row {
            items.retain(|(key, _)| key != "cursor");
        }
        out.push(row);
    }
    Ok(Py::List(out))
}

fn turn_view(
    scope: &mut dyn ReadScope,
    turn: &str,
    overlay: &Overlay,
    shown_in: Option<&str>,
) -> Result<Py, OpError> {
    let entry = turn_entry(scope, turn)?;
    if on_an_edited_line(scope, turn)? {
        return Err(python_says("an edited or deleted Turn's line"));
    }
    let body = py_body(&entry.body)?;
    // `entry["body"]["parts"]` and `["addressed_to"]`, which raise where they are missing.
    let Some(Py::List(parts)) = body.get("parts") else {
        return Err(python_says("a Turn without a list of parts"));
    };
    let Some(Py::List(addressed_to)) = body.get("addressed_to") else {
        return Err(python_says("a Turn without a list of addressees"));
    };
    if parts
        .iter()
        .any(|p| p.get("type").and_then(Py::as_str) != Some("text"))
    {
        return Err(python_says("a Turn with annotated parts"));
    }
    let mut addressed = Vec::with_capacity(addressed_to.len());
    for who in addressed_to {
        addressed.push(
            who.as_str()
                .ok_or_else(|| python_says("an addressee that isn't an id"))?
                .to_owned(),
        );
    }
    let addressed = once(addressed);

    let mut home = None;
    let mut filed = false;
    let mut answers = false;
    scope.query(TURN_LINKS_FROM, &[Param::Text(turn)], &mut |row| {
        match text(row, 2)?.as_deref() {
            Some("in-conversation") if home.is_none() => home = text(row, 1)?,
            Some("about-topic" | "linked-into") => filed = true,
            Some("replies-to") => answers = true,
            _ => {}
        }
        Ok(Flow::Continue)
    })?;
    if filed {
        return Err(python_says("a Turn's filing or link history"));
    }
    if answers {
        return Err(python_says("a reply's inherited address and thread root"));
    }
    let Some(home) = home else {
        return Err(python_says("a Turn in no Conversation"));
    };
    let mut replies = Vec::new();
    let mut replied_by = Vec::new();
    let mut anchored = false;
    let mut observed = false;
    scope.query(TURN_LINKS_TO, &[Param::Text(turn)], &mut |row| {
        match text(row, 2)?.as_deref() {
            Some("replies-to") => {
                replies.push(text(row, 1)?.unwrap_or_default());
                replied_by.push(text(row, 3)?);
            }
            Some("anchors-in") => anchored = true,
            Some("observes") => observed = true,
            _ => {}
        }
        Ok(Flow::Continue)
    })?;
    if anchored {
        return Err(python_says("a Turn with anchors on it"));
    }
    // `status_of`'s `failed` reads each observation. With none, it is `None`.
    if observed && !addressed.is_empty() {
        return Err(python_says("an addressed Turn with observations"));
    }

    let ops = acts(scope, turn)?;
    for (act, why) in [
        ("result-returned", "a run's returned answer"),
        ("result-recovered", "a run's recovered answer"),
        ("work-discovered", "a discovered finding"),
        ("turn-addressed", "a Turn addressed later"),
    ] {
        if ops.iter().any(|a| a.is(act)) {
            return Err(python_says(why));
        }
    }
    let forms = forms::on_turn(scope, turn)?;
    let mut expectation_ids: Vec<String> = ops
        .iter()
        .filter(|a| a.is("expectation-recorded"))
        .map(|a| a.id.clone())
        .collect();
    for form in &forms {
        expectation_ids.extend(form.questions.iter().map(|q| q.expectation.clone()));
    }
    let states = expectation_states(scope, once(expectation_ids))?;
    // An answered ask on a Turn stays Python's: `answered_by` is right on `decisions?ids`, where it
    // was wrong, and this correction does not widen what the Turn route answers.
    if states.iter().any(|state| state.response_present) {
        return Err(python_says("a Turn with an answered ask"));
    }

    let mut who = addressed.clone();
    who.extend(entry.by.clone());
    let names = aliases_for_states(scope, &states, &who)?;
    let on = AskedOn {
        turn,
        author: entry.by.as_deref(),
    };
    let expectations = states
        .iter()
        .map(|s| expectation_py(scope, s, overlay, &names, Some(on)))
        .collect::<Result<Vec<_>, _>>()?;
    let number = number_in(scope, turn)?;
    let shown = shown_in.unwrap_or(&home);
    let author_alias = entry
        .by
        .as_ref()
        .map(|id| names.get(id).cloned().unwrap_or_else(|| id.clone()));
    let ran = ops.iter().rfind(|a| {
        a.execution.as_deref().is_some_and(|run| !run.is_empty())
            && !a.is("execution-started")
            && a.conversation.as_deref() == Some(shown)
    });
    let mut addressee_rows = Vec::with_capacity(addressed.len());
    for id in &addressed {
        addressee_rows.push(dict([
            ("participant", Py::str(id)),
            (
                "alias",
                Py::str(names.get(id).cloned().unwrap_or_else(|| id.clone())),
            ),
            ("addressed", Py::Bool(true)),
            ("delivered", Py::Bool(delivered_to(scope, turn, id)?)),
            (
                "responded",
                Py::Bool(replied_by.iter().any(|by| by.as_deref() == Some(id))),
            ),
            ("failed", Py::None),
            ("addressed_later", Py::Bool(false)),
            ("addressed_by", Py::None),
            ("addressed_because", Py::None),
        ]));
    }
    let agent_work = classify::classify(scope, &[turn])?
        .remove(turn)
        .unwrap_or(Py::None);
    let operational: Vec<Py> = ops.iter().map(act_py).collect::<Result<_, _>>()?;
    let deliveries = deliveries(scope, turn)?;
    let standing = standing(scope, &[turn.to_owned()])?.remove(turn).unwrap();
    let incoming = Py::Dict(
        standing
            .incoming
            .into_iter()
            .map(|(k, v)| (k, Py::List(v.into_iter().map(|id| Py::str(id.0)).collect())))
            .collect(),
    );
    // The guards above are what make each constant here Python's answer: an owned Turn is unedited,
    // undeleted, unfiled, unlinked, unanchored, no reply, returned by no run and no finding.
    let mut out = dict([
        ("id", Py::str(turn)),
        ("number", number.map_or(Py::None, Py::int)),
        ("parts", Py::List(parts.clone())),
        ("anchors", Py::List(vec![])),
        ("returned_with", Py::List(vec![])),
        ("recovered", Py::None),
        (
            "execution",
            Py::opt_str(ran.and_then(|a| a.execution.as_deref())),
        ),
        (
            "runtime",
            Py::opt_str(ran.and_then(|a| a.runtime.as_deref())),
        ),
        ("author", Py::opt_str(entry.by.as_deref())),
        ("author_alias", Py::opt_str(author_alias.as_deref())),
        ("written_by", Py::opt_str(entry.written_by.as_deref())),
        ("at", Py::Float(entry.at)),
        ("addressees", Py::List(addressee_rows)),
        ("topics", Py::List(vec![])),
        ("linked_into", Py::List(vec![])),
        ("answering", Py::None),
        (
            "replies",
            Py::List(replies.into_iter().map(Py::str).collect()),
        ),
        ("chose", chose_of(&ops)?),
        ("expectations", Py::List(expectations)),
        ("decision_forms", forms_py(&forms)?),
        ("operational_acts", Py::int(ops.len())),
        ("discovered_under", Py::None),
        ("agent_work", agent_work),
        ("revision", Py::None),
        ("deleted", Py::None),
    ]);
    // `history_view` of a line with one version.
    out.set(
        "versions",
        dict([
            ("entry", Py::str(turn)),
            (
                "versions",
                Py::List(vec![dict([
                    ("entry", Py::str(turn)),
                    ("version", Py::int(1)),
                    ("at", Py::Float(entry.at)),
                    ("by", Py::opt_str(entry.by.as_deref())),
                    ("by_alias", Py::opt_str(author_alias.as_deref())),
                    ("written_by", Py::opt_str(entry.written_by.as_deref())),
                    ("because", Py::None),
                    ("current", Py::Bool(true)),
                    ("parts", Py::List(parts.clone())),
                ])]),
            ),
            ("current", Py::str(turn)),
            ("deleted", Py::None),
        ]),
    );
    out.set("filings", Py::List(vec![]));
    out.set(
        "inspector",
        dict([
            ("kind", Py::str("contribution")),
            ("stands", Py::Bool(standing.stands)),
            ("incoming", incoming),
            ("operational", Py::List(operational)),
            ("deliveries", Py::List(deliveries)),
            ("conversation", Py::str(&home)),
            ("root", Py::str(turn)),
            ("number", number.map_or(Py::None, Py::int)),
        ]),
    );
    Ok(out)
}

fn deliveries(scope: &mut dyn ReadScope, turn: &str) -> Result<Vec<Py>, OpError> {
    let mut out = Vec::new();
    let like = format!("%{turn}%");
    scope.query(TURN_DELIVERIES, &[Param::Text(&like)], &mut |row| {
        let material = text(row, 7)?.and_then(|raw| loads(&raw)).ok_or_else(|| {
            mentis_record::RecordError::Sqlite {
                detail: "delivery material is not JSON".into(),
            }
        })?;
        let names_turn = material.as_list().is_some_and(|items| {
            items
                .iter()
                .any(|item| item.get("entry").and_then(Py::as_str) == Some(turn))
        });
        if !names_turn {
            return Ok(Flow::Continue);
        }
        let at = match row.value(6)? {
            Value::Real(v) => Py::Float(v),
            Value::Integer(v) => Py::int(v),
            _ => Py::None,
        };
        let sources = text(row, 8)?
            .and_then(|raw| loads(&raw))
            .unwrap_or(Py::List(vec![]));
        let ok = row.value(9)?.integer().is_some_and(|v| v != 0);
        out.push(dict([
            ("id", Py::opt_str(text(row, 0)?.as_deref())),
            ("execution", Py::opt_str(text(row, 1)?.as_deref())),
            ("conversation", Py::opt_str(text(row, 2)?.as_deref())),
            ("participant", Py::opt_str(text(row, 3)?.as_deref())),
            ("runtime", Py::opt_str(text(row, 4)?.as_deref())),
            ("mechanism", Py::opt_str(text(row, 5)?.as_deref())),
            ("at", at),
            ("material", material),
            ("behavioural_sources", sources),
            ("operation_ok", Py::Bool(ok)),
        ]));
        Ok(Flow::Continue)
    })?;
    Ok(out)
}

/// `status_of`'s `delivered`: a delivery to them whose material names this very entry, not one that
/// only holds its id somewhere.
fn delivered_to(scope: &mut dyn ReadScope, turn: &str, who: &str) -> Result<bool, OpError> {
    let like = format!("%{turn}%");
    let mut delivered = false;
    scope.query(
        DELIVERED_TO,
        &[Param::Text(who), Param::Text(&like)],
        &mut |row| {
            let material = text(row, 0)?.and_then(|raw| loads(&raw));
            delivered = material
                .as_ref()
                .and_then(Py::as_list)
                .is_some_and(|items| {
                    items
                        .iter()
                        .any(|item| item.get("entry").and_then(Py::as_str) == Some(turn))
                });
            Ok(if delivered {
                Flow::Stop
            } else {
                Flow::Continue
            })
        },
    )?;
    Ok(delivered)
}

const INTAKE_LINKS: &str = "SELECT id, link_from, link_to, attributed_to, written_by, recorded_at \
    FROM entry WHERE link_relation = 'carries-intake' ORDER BY seq";
const UNRESOLVED: &str = "SELECT caused_by, actor FROM operational WHERE act = \
    'assignment-unresolved' ORDER BY at, seq";
const REPLIES_TO: &str = "SELECT e.attributed_to FROM entry l JOIN entry e ON e.id = l.link_from \
    WHERE l.link_relation = 'replies-to' AND l.link_to = ?1 ORDER BY l.seq";

#[derive(Clone, Debug)]
pub struct IntakeViewArgs {
    pub overlay: Overlay,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct IntakeView;

impl ReadOp for IntakeView {
    type Args = IntakeViewArgs;
    type Row = ViewRow;
    const NAME: &'static str = "intake-view";
    const BUDGET: Budget = Budget { statements: 20 };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<ViewRow>, OpError> {
        let mut links = Vec::new();
        scope.query(INTAKE_LINKS, &[], &mut |row| {
            let at = match row.value(5)? {
                Value::Real(v) => v,
                Value::Integer(v) => v as f64,
                _ => 0.0,
            };
            links.push((
                text(row, 0)?.unwrap_or_default(),
                text(row, 1)?.unwrap_or_default(),
                text(row, 2)?.unwrap_or_default(),
                text(row, 3)?,
                text(row, 4)?,
                at,
            ));
            Ok(Flow::Continue)
        })?;
        let link_ids: Vec<String> = links.iter().map(|x| x.0.clone()).collect();
        let link_states = standing(scope, &link_ids)?;
        let persona_ids: Vec<String> = links.iter().map(|x| x.2.clone()).collect();
        let persona_states = standing(scope, &persona_ids)?;
        let people: Vec<String> = links.iter().map(|x| x.1.clone()).collect();
        let names = aliases(scope, &people)?;
        let persona_reads = now_reads(
            scope,
            &persona_ids.iter().cloned().map(Id).collect::<Vec<_>>(),
        )?;
        let mut rows = Vec::new();
        for (designation, participant, persona, by, written, at) in &links {
            let state = &link_states[designation];
            let pstate = &persona_states[persona];
            let pname = persona_reads
                .get(&Id(persona.clone()))
                .and_then(|r| loads(&r.body_json))
                .and_then(|b| body_text(&b, "name").ok().flatten());
            rows.push(dict([
                ("designation", Py::str(designation)),
                ("participant", Py::str(participant)),
                ("persona", Py::str(persona)),
                ("stands", Py::Bool(state.stands)),
                (
                    "established_by",
                    Py::List(state.established_by.iter().map(|x| Py::str(&x.0)).collect()),
                ),
                (
                    "superseded_by",
                    Py::List(state.superseded_by.iter().map(|x| Py::str(&x.0)).collect()),
                ),
                ("attributed_to", Py::opt_str(by.as_deref())),
                ("written_by", Py::opt_str(written.as_deref())),
                ("at", Py::Float(*at)),
                (
                    "alias",
                    Py::str(
                        names
                            .get(participant)
                            .cloned()
                            .unwrap_or_else(|| participant.clone()),
                    ),
                ),
                ("persona_name", Py::opt_str(pname.as_deref())),
                ("persona_stands", Py::Bool(pstate.stands)),
            ]));
        }
        let standing_rows: Vec<_> = links.iter().filter(|x| link_states[&x.0].stands).collect();
        let carrier = if standing_rows.is_empty() {
            dict([
                ("resolved", Py::Bool(false)),
                ("reason", Py::str("none in force")),
                (
                    "detail",
                    Py::str(if links.is_empty() {
                        "no Participant is designated to carry requests addressed to nobody in this Brain".into()
                    } else {
                        format!("{} designation(s) written, none standing", links.len())
                    }),
                ),
                ("candidates", Py::List(vec![])),
            ])
        } else if standing_rows.len() > 1 {
            dict([
                ("resolved", Py::Bool(false)),
                ("reason", Py::str("more than one in force")),
                (
                    "detail",
                    Py::str(
                        "several designations stand at once; which one applies is a decision only a person can make",
                    ),
                ),
                (
                    "candidates",
                    Py::List(standing_rows.iter().map(|x| Py::str(&x.0)).collect()),
                ),
            ])
        } else {
            let x = standing_rows[0];
            if !persona_states[&x.2].stands {
                dict([
                    ("resolved", Py::Bool(false)),
                    ("reason", Py::str("persona does not stand")),
                    (
                        "detail",
                        Py::str(
                            "the designated Persona is not established, or has been superseded, so the designation cannot be honoured as it was made",
                        ),
                    ),
                    ("candidates", Py::List(vec![Py::str(&x.0)])),
                ])
            } else {
                dict([
                    ("resolved", Py::Bool(true)),
                    ("designation", Py::str(&x.0)),
                    ("participant", Py::str(&x.1)),
                    ("persona", Py::str(&x.2)),
                    (
                        "alias",
                        Py::str(names.get(&x.1).cloned().unwrap_or_else(|| x.1.clone())),
                    ),
                ])
            }
        };
        let resumable = resumable(scope, &request.args.overlay)?;
        let answer = dict([
            ("carrier", carrier),
            ("designations", Py::List(rows)),
            ("requires", Py::List(vec![Py::str("call_mentis_tools")])),
            (
                "resumable",
                Py::List(resumable.into_iter().map(Py::str).collect()),
            ),
            (
                "note",
                Py::str(
                    "one designation in force resolves; none or several is unresolved and is a person's decision, never a tie broken by recency",
                ),
            ),
        ]);
        Ok(ReadAnswer {
            rows: vec![ViewRow(answer)],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

/// `resumable_intake`: `_resume_refusal` of each, in its order, the record's refusals before the
/// live one so that a request already refused needs nothing from the overlay.
fn resumable(scope: &mut dyn ReadScope, overlay: &Overlay) -> Result<Vec<String>, OpError> {
    let mut candidates = Vec::new();
    let mut said_by: HashMap<String, Vec<Option<String>>> = HashMap::new();
    scope.query(UNRESOLVED, &[], &mut |row| {
        if let Some(id) = text(row, 0)?.filter(|id| !id.is_empty()) {
            if !said_by.contains_key(&id) {
                candidates.push(id.clone());
            }
            said_by.entry(id).or_default().push(text(row, 1)?);
        }
        Ok(Flow::Continue)
    })?;
    let states = expectation_states(scope, candidates)?;
    let mut out = Vec::new();
    for state in states {
        // `_unresolved_intake`: only the requester's own act says intake left it unassigned.
        let by_requester = said_by
            .get(&state.expectation)
            .is_some_and(|actors| actors.contains(&state.requested_by));
        if !by_requester || !state.unassigned || !state.satisfied_by.is_empty() {
            continue;
        }
        // With no Turn, `links(to=None)` reads every reply there is.
        let Some(turn) = state.turn.as_deref() else {
            return Err(python_says("an unassigned request with no Turn"));
        };
        let mut replied = false;
        scope.query(REPLIES_TO, &[Param::Text(turn)], &mut |row| {
            let by = text(row, 0)?;
            if by != state.requested_by {
                replied = true
            }
            Ok(Flow::Continue)
        })?;
        if replied || execution_bool(overlay, &state, scope)? {
            continue;
        }
        // `inert_refusal(turn)`: refused by a deleted line, and an edited one takes reading.
        let plain_turn = reads::heads(scope, &[turn])?
            .get(turn)
            .is_some_and(reads::Head::is_post);
        if !plain_turn || on_an_edited_line(scope, turn)? {
            return Err(python_says(
                "a resumable request on a Turn that isn't plain",
            ));
        }
        out.push(state.expectation)
    }
    Ok(out)
}

#[derive(Clone, Debug)]
pub struct TurnsViewArgs {
    pub turns: Vec<String>,
    pub overlay: Overlay,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct TurnsView;

impl ReadOp for TurnsView {
    type Args = TurnsViewArgs;
    type Row = ViewRow;
    const NAME: &'static str = "turns-view";
    const BUDGET: Budget = Budget {
        statements: 64 * 120,
    };
    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<ViewRow>, OpError> {
        let mut rows = Vec::new();
        for id in &request.args.turns {
            match turn_view(scope, id, &request.args.overlay, None) {
                Ok(turn) => rows.push(dict([("id", Py::str(id)), ("turn", turn)])),
                Err(OpError::NotFound { .. }) => rows.push(dict([
                    ("id", Py::str(id)),
                    ("turn", Py::None),
                    ("error", Py::str("list index out of range")),
                    ("kind", Py::str("IndexError")),
                ])),
                Err(error) => return Err(error),
            }
        }
        Ok(ReadAnswer {
            rows: vec![ViewRow(dict([
                ("turns", Py::List(rows)),
                ("limit", Py::int(64)),
            ]))],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

#[derive(Clone, Debug)]
pub struct ThreadViewArgs {
    pub conversation: String,
    pub root: String,
    pub overlay: Overlay,
}
#[derive(Clone, Copy, Debug, Default)]
pub struct ThreadView;
impl ReadOp for ThreadView {
    type Args = ThreadViewArgs;
    type Row = ViewRow;
    const NAME: &'static str = "thread-view";
    const BUDGET: Budget = Budget { statements: 120 };
    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<ViewRow>, OpError> {
        let row = thread_of(scope, &request.args)?;
        Ok(ReadAnswer {
            rows: vec![ViewRow(row)],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

/// The thread route, where its refusals are answers.
fn thread_of(scope: &mut dyn ReadScope, args: &ThreadViewArgs) -> Result<Py, OpError> {
    let root = args.root.as_str();
    let mut turns = Vec::new();
    scope.query(
        CONVERSATION_TURNS,
        &[Param::Text(&args.conversation)],
        &mut |row| {
            turns.push(text(row, 0)?.unwrap_or_default());
            Ok(Flow::Continue)
        },
    )?;
    let order: HashMap<&str, usize> = turns
        .iter()
        .enumerate()
        .map(|(i, id)| (id.as_str(), i))
        .collect();
    if !order.contains_key(root) {
        return Ok(dict([
            (
                "error",
                Py::str(format!("{root} is not a turn of this conversation")),
            ),
            ("thread", Py::str(root)),
        ]));
    }
    let asked: Vec<&str> = turns.iter().map(String::as_str).collect();
    let chain = reads::first_to(&reads::links_from(scope, reads::REPLIES_TO, &asked)?);
    let thread = thread_root(root, &chain, &order);
    if thread != root {
        return Ok(dict([
            (
                "error",
                Py::str(format!(
                    "{root} is a reply, not a thread root; its thread is {thread}"
                )),
            ),
            ("thread", Py::str(root)),
            ("root", Py::str(thread)),
        ]));
    }
    // Every reply is forwarded by its own view, so a thread with one is Python's whole.
    if chain
        .iter()
        .any(|(from, to)| to == root && from != root && order.contains_key(from.as_str()))
    {
        return Err(python_says("a thread with replies"));
    }
    let mut head = turn_view(scope, root, &args.overlay, Some(&args.conversation))?;
    if let Py::Dict(items) = &mut head {
        items.retain(|(key, _)| !matches!(key.as_str(), "versions" | "filings" | "inspector"));
    }
    // `_placed` of a root that answers nothing and has nothing under it, as the guards prove.
    head.set("root", Py::str(root));
    head.set("answering_number", Py::None);
    head.set("parent_in_scope", Py::None);
    head.set("thread_replies", Py::int(0));
    head.set("thread_repliers", Py::List(vec![]));
    Ok(dict([
        ("conversation", Py::str(&args.conversation)),
        ("root", Py::str(root)),
        ("turn", head),
        ("replies_total", Py::int(0)),
        ("replies", Py::List(vec![])),
    ]))
}

/// `_threads_of`'s `climb`: what this ultimately answers among these Turns, and of a cycle, its
/// oldest.
fn thread_root<'a>(
    turn: &'a str,
    chain: &'a HashMap<String, String>,
    order: &HashMap<&str, usize>,
) -> &'a str {
    let mut seen: HashSet<&str> = HashSet::new();
    let mut up = turn;
    loop {
        let Some(next) = chain.get(up).map(String::as_str) else {
            return up;
        };
        if !order.contains_key(next) {
            return up;
        }
        if seen.contains(next) || next == turn {
            seen.insert(up);
            seen.insert(next);
            return seen
                .into_iter()
                .min_by_key(|id| (order.get(id).copied().unwrap_or(0), *id))
                .unwrap_or(up);
        }
        seen.insert(up);
        up = next;
    }
}

#[derive(Clone, Debug)]
pub struct DecisionsViewArgs {
    pub post: Option<String>,
    pub ids: Vec<String>,
    pub overlay: Overlay,
}
#[derive(Clone, Copy, Debug, Default)]
pub struct DecisionsView;
impl ReadOp for DecisionsView {
    type Args = DecisionsViewArgs;
    type Row = ViewRow;
    const NAME: &'static str = "decisions-view";
    const BUDGET: Budget = Budget {
        statements: 64 * 120,
    };
    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<ViewRow>, OpError> {
        let held_owner = classify::owner_of(scope)?;
        let answer = if let Some(post) = &request.args.post {
            // `decisions_read` answers `None` of what is not a post, which the route says as 404.
            let is_post = reads::heads(scope, &[post.as_str()])?
                .get(post)
                .is_some_and(reads::Head::is_post);
            if !is_post {
                return Err(OpError::NotFound { what: post.clone() });
            }
            let view = turn_view(scope, post, &request.args.overlay, None)?;
            let home = reads::homes_of(scope, &[post.as_str()])?.remove(post);
            let summary = dict([
                ("id", Py::str(post)),
                ("number", view.get("number").cloned().unwrap_or(Py::None)),
                ("author", view.get("author").cloned().unwrap_or(Py::None)),
                (
                    "author_alias",
                    view.get("author_alias").cloned().unwrap_or(Py::None),
                ),
                (
                    "topics",
                    view.get("topics").cloned().unwrap_or(Py::List(vec![])),
                ),
                ("conversation", Py::opt_str(home.as_deref())),
                ("deleted", Py::Bool(false)),
            ]);
            dict([
                ("post", summary),
                ("you", Py::opt_str(held_owner.as_deref())),
                (
                    "expectations",
                    view.get("expectations")
                        .cloned()
                        .unwrap_or(Py::List(vec![])),
                ),
                (
                    "decision_forms",
                    view.get("decision_forms")
                        .cloned()
                        .unwrap_or(Py::List(vec![])),
                ),
            ])
        } else {
            decisions_of_ids(
                scope,
                &request.args.ids,
                &request.args.overlay,
                held_owner.as_deref(),
            )?
        };
        Ok(ReadAnswer {
            rows: vec![ViewRow(answer)],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

/// `decisions_read(ids=)`: of each ask, its whole form with every question, or itself.
fn decisions_of_ids(
    scope: &mut dyn ReadScope,
    ids: &[String],
    overlay: &Overlay,
    owner: Option<&str>,
) -> Result<Py, OpError> {
    let listed = id_list(ids.iter().map(String::as_str));
    let read = forms::read_acts(scope, forms::BY_ID, &listed)?;
    let by_id: HashMap<&str, &Act> = read.iter().map(|act| (act.id.as_str(), act)).collect();
    let mut form_ids = Vec::new();
    let mut asks = Vec::new();
    for id in ids {
        let Some(act) = by_id.get(id.as_str()) else {
            continue;
        };
        if !act.is("expectation-recorded") {
            continue;
        }
        let detail = act.detail_object()?;
        if detail.is_truthy("form")? {
            form_ids.push(
                detail
                    .text("form")?
                    .ok_or_else(|| python_says("a form that isn't a reference"))?,
            );
        } else {
            asks.push(id.clone());
        }
    }
    let forms = forms::forms(scope, &once(form_ids))?;
    let mut wanted: Vec<String> = forms
        .iter()
        .flat_map(|form| form.questions.iter().map(|q| q.expectation.clone()))
        .collect();
    wanted.extend(asks);
    let states = expectation_states(scope, once(wanted))?;
    let names = aliases_for_states(scope, &states, &[])?;
    let turns: Vec<&str> = states.iter().filter_map(|s| s.turn.as_deref()).collect();
    let heads = reads::heads(scope, &turns)?;
    let mut views = Vec::with_capacity(states.len());
    for state in &states {
        let on = state.turn.as_deref().and_then(|turn| {
            heads.get(turn).map(|head| AskedOn {
                turn,
                author: head.attributed_to.as_deref(),
            })
        });
        views.push(expectation_py(scope, state, overlay, &names, on)?);
    }
    Ok(dict([
        ("post", Py::None),
        ("you", Py::opt_str(owner)),
        ("expectations", Py::List(views)),
        ("decision_forms", forms_py(&forms)?),
    ]))
}
