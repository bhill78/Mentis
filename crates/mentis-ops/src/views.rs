//! Durable R4.2 view foundations.  These are the small record-only projections shared by the
//! owner HTTP routes; live expectation booleans remain in [`crate::overlay`], where the durable
//! read and poll marker are checked in one scope.

use std::collections::{HashMap, HashSet};

use mentis_record::{Flow, Id, Param, ReadScope, Value};
use mentis_rules::{NameRead, name_reads, now_reads, standing_many};

use crate::acts::Act;
use crate::expectation_states::{ExpectationState, ExpectationStates, ExpectationStatesArgs};
use crate::forms;
use crate::overlay::{Overlay, execution_bool};
use crate::pyjson::{Py, dict, loads};
use crate::stored::python_says;
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

fn aliases(scope: &mut dyn ReadScope, ids: &[String]) -> Result<HashMap<String, String>, OpError> {
    let asked: Vec<Id> = ids.iter().cloned().map(Id).collect();
    let mut out = HashMap::new();
    for (id, read) in name_reads(scope, &asked)? {
        let name = match read {
            NameRead::Named(name) => name,
            NameRead::Unnamed => id.0.clone(),
            NameRead::NotPlain => return Err(python_says("a participant alias this cannot read")),
        };
        out.insert(id.0, name);
    }
    Ok(out)
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

#[derive(Clone)]
struct TurnEntry {
    kind: Option<String>,
    by: Option<String>,
    written_by: Option<String>,
    at: f64,
}

impl ReadOp for TurnView {
    type Args = TurnViewArgs;
    type Row = ViewRow;
    const NAME: &'static str = "turn-view";
    const BUDGET: Budget = Budget { statements: 45 };

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

fn turn_entry(scope: &mut dyn ReadScope, id: &str) -> Result<TurnEntry, OpError> {
    let mut got = None;
    scope.query(TURN, &[Param::Text(id)], &mut |row| {
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
                kind,
                by: text(row, 4)?,
                written_by: text(row, 5)?,
                at,
            });
        }
        Ok(Flow::Stop)
    })?;
    got.ok_or_else(|| OpError::NotFound {
        what: id.to_owned(),
    })
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

fn home_and_number(
    scope: &mut dyn ReadScope,
    turn: &str,
) -> Result<(Option<String>, Option<i64>), OpError> {
    let mut home = None;
    scope.query(TURN_LINKS_FROM, &[Param::Text(turn)], &mut |row| {
        if text(row, 2)?.as_deref() == Some("in-conversation") && home.is_none() {
            home = text(row, 1)?;
        }
        Ok(Flow::Continue)
    })?;
    let Some(cid) = home.clone() else {
        return Ok((None, None));
    };
    let mut ids = Vec::new();
    scope.query(CONVERSATION_TURNS, &[Param::Text(&cid)], &mut |row| {
        ids.push(text(row, 0)?.unwrap_or_default());
        Ok(Flow::Continue)
    })?;
    let number = ids.iter().position(|id| id == turn).map(|i| i as i64 + 1);
    Ok((home, number))
}

fn aliases_for_states(
    scope: &mut dyn ReadScope,
    states: &[ExpectationState],
    author: Option<&str>,
) -> Result<HashMap<String, String>, OpError> {
    let mut ids = Vec::new();
    if let Some(id) = author {
        ids.push(id.to_owned());
    }
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

fn expectation_py(
    scope: &mut dyn ReadScope,
    state: &ExpectationState,
    overlay: &Overlay,
    names: &HashMap<String, String>,
) -> Result<Py, OpError> {
    let mut unresolved = None;
    let sql = "SELECT because FROM operational WHERE caused_by = ?1 AND act = 'assignment-unresolved' ORDER BY seq";
    scope.query(sql, &[Param::Text(&state.expectation)], &mut |row| {
        unresolved = text(row, 0)?;
        Ok(Flow::Stop)
    })?;
    let alias =
        |id: Option<&String>| id.map(|id| names.get(id).cloned().unwrap_or_else(|| id.clone()));
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
        ("answered_by", Py::None),
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
        ("continues_work", Py::Bool(false)),
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

fn turn_view(
    scope: &mut dyn ReadScope,
    turn: &str,
    overlay: &Overlay,
    shown_in: Option<&str>,
) -> Result<Py, OpError> {
    let entry = turn_entry(scope, turn)?;
    let line = mentis_rules::lines_of(scope, &[Id(turn.to_owned())])?
        .remove(&Id(turn.to_owned()))
        .ok_or_else(|| OpError::NotFound {
            what: turn.to_owned(),
        })?;
    line.versions
        .last()
        .ok_or_else(|| python_says("a Turn with no version"))?;
    let reading = now_reads(scope, &[Id(turn.to_owned())])?
        .remove(&Id(turn.to_owned()))
        .ok_or_else(|| OpError::NotFound {
            what: turn.to_owned(),
        })?;
    if reading.python_says {
        return Err(python_says("a Turn version this cannot read"));
    }
    let body = py_body(&reading.body_json)?;
    let parts = match body.get("parts") {
        None | Some(Py::None) => Vec::new(),
        Some(Py::List(v)) => v.clone(),
        _ => return Err(python_says("parts that are not a list")),
    };
    if parts
        .iter()
        .any(|p| p.get("type").and_then(Py::as_str) != Some("text"))
    {
        return Err(python_says("a Turn with annotated parts"));
    }
    let (home, number) = home_and_number(scope, turn)?;
    let shown = shown_in.or(home.as_deref());
    let ops = acts(scope, turn)?;
    let forms = forms::on_turn(scope, turn)?;
    let mut expectation_ids: Vec<String> = ops
        .iter()
        .filter(|a| a.is("expectation-recorded"))
        .map(|a| a.id.clone())
        .collect();
    for form in &forms {
        expectation_ids.extend(form.questions.iter().map(|q| q.expectation.clone()));
    }
    let asked = ReadRequest {
        args: ExpectationStatesArgs {
            ids: expectation_ids,
        },
        cursor: None,
        limit: None,
        deadline: std::time::Instant::now() + std::time::Duration::from_secs(5),
    };
    let states = ExpectationStates.read(scope, &asked)?.rows;
    // These durable facts require projections that are not part of this package's shared seam.
    // Never answer a plausible subset: the front forwards the whole request to Python until the
    // answering-reply, filing/history, and agent-work packages move with their own contracts.
    if states.iter().any(|state| state.response_present)
        || line.versions.len() != 1
        || reading.revision.is_some()
        || reading.deleted.is_some()
        || ops.iter().any(|act| {
            act.is("result-returned")
                || act.is("result-recovered")
                || act.is("work-discovered")
                || act.is("turn-addressed")
        })
    {
        return Err(python_says(
            "a Turn detail projection this package does not own",
        ));
    }
    let names = aliases_for_states(scope, &states, entry.by.as_deref())?;
    let expectations = states
        .iter()
        .map(|s| expectation_py(scope, s, overlay, &names))
        .collect::<Result<Vec<_>, _>>()?;
    let author_alias = entry
        .by
        .as_ref()
        .map(|id| names.get(id).cloned().unwrap_or_else(|| id.clone()));
    let ran = ops.iter().rfind(|a| {
        a.execution.is_some() && !a.is("execution-started") && a.conversation.as_deref() == shown
    });
    let mut replies = Vec::new();
    let mut answering = None;
    let mut topics = Vec::new();
    let mut linked = Vec::new();
    scope.query(TURN_LINKS_FROM, &[Param::Text(turn)], &mut |row| {
        match text(row, 2)?.as_deref() {
            Some("replies-to") if answering.is_none() => answering = text(row, 1)?,
            Some("about-topic") => topics.push(text(row, 1)?.unwrap_or_default()),
            Some("linked-into") => linked.push(text(row, 1)?.unwrap_or_default()),
            _ => {}
        }
        Ok(Flow::Continue)
    })?;
    if !topics.is_empty() {
        return Err(python_says("a Turn's filing history"));
    }
    scope.query(TURN_LINKS_TO, &[Param::Text(turn)], &mut |row| {
        if text(row, 2)?.as_deref() == Some("replies-to") {
            replies.push(text(row, 1)?.unwrap_or_default())
        }
        Ok(Flow::Continue)
    })?;
    if answering.is_some() {
        return Err(python_says("a reply's inherited address and thread root"));
    }
    let chose = ops
        .iter()
        .filter(|a| a.is("turn-said"))
        .find_map(|a| a.detail_object().ok()?.text("chose").ok().flatten());
    let recovered = ops
        .iter()
        .find(|a| {
            a.is("result-recovered")
                && a.detail_object()
                    .ok()
                    .and_then(|d| d.text("response_owner").ok().flatten())
                    .as_deref()
                    != Some("respond")
        })
        .map(|a| {
            dict([
                ("act", Py::str(&a.id)),
                ("by", Py::opt_str(a.actor.as_deref())),
                (
                    "by_alias",
                    Py::str(
                        a.actor
                            .as_ref()
                            .and_then(|id| names.get(id))
                            .cloned()
                            .or_else(|| a.actor.clone())
                            .unwrap_or_default(),
                    ),
                ),
                ("at", Py::Float(a.at)),
                ("because", Py::opt_str(a.because.as_deref())),
                ("source", Py::None),
            ])
        })
        .unwrap_or(Py::None);
    let versions = version_history(&line, &names)?;
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
    let mut out = dict([
        ("id", Py::str(turn)),
        ("number", number.map_or(Py::None, Py::int)),
        ("parts", Py::List(parts)),
        ("anchors", Py::List(vec![])),
        ("returned_with", Py::List(vec![])),
        ("recovered", recovered),
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
        ("addressees", addressees(scope, &states, &names, turn)?),
        (
            "topics",
            Py::List(topics.into_iter().map(Py::str).collect()),
        ),
        (
            "linked_into",
            Py::List(linked.into_iter().map(Py::str).collect()),
        ),
        ("answering", Py::opt_str(answering.as_deref())),
        (
            "replies",
            Py::List(replies.into_iter().map(Py::str).collect()),
        ),
        ("chose", Py::opt_str(chose.as_deref())),
        ("expectations", Py::List(expectations)),
        ("decision_forms", serde_py(&forms)?),
        ("operational_acts", Py::int(ops.len())),
        ("discovered_under", Py::None),
        ("agent_work", Py::None),
        ("revision", revision_py(&reading, &names)),
        ("deleted", deleted_py(&reading, &names)),
    ]);
    out.set("versions", versions);
    out.set("filings", Py::List(vec![]));
    out.set(
        "inspector",
        dict([
            ("kind", Py::opt_str(entry.kind.as_deref())),
            ("stands", Py::Bool(standing.stands)),
            ("incoming", incoming),
            ("operational", Py::List(operational)),
            ("deliveries", Py::List(deliveries)),
            ("conversation", Py::opt_str(home.as_deref())),
            ("root", Py::str(&line.root)),
            ("number", number.map_or(Py::None, Py::int)),
        ]),
    );
    Ok(out)
}

fn revision_py(read: &mentis_rules::Reading, _names: &HashMap<String, String>) -> Py {
    match &read.revision {
        None => Py::None,
        Some(r) => dict([
            ("versions", Py::int(r.versions)),
            ("current", Py::str(&r.current.0)),
            ("edited_at", Py::Float(r.edited_at)),
            (
                "edited_by",
                Py::opt_str(r.edited_by.as_ref().map(|x| x.0.as_str())),
            ),
        ]),
    }
}

fn deleted_py(read: &mentis_rules::Reading, names: &HashMap<String, String>) -> Py {
    match &read.deleted {
        None => Py::None,
        Some(d) => {
            let by_alias =
                d.by.as_ref()
                    .map(|x| names.get(&x.0).cloned().unwrap_or_else(|| x.0.clone()));
            dict([
                ("record", Py::str(&d.record.0)),
                ("at", Py::Float(d.at)),
                ("by", Py::opt_str(d.by.as_ref().map(|x| x.0.as_str()))),
                ("because", Py::opt_str(d.because.as_deref())),
                ("by_alias", Py::opt_str(by_alias.as_deref())),
            ])
        }
    }
}

fn version_history(
    line: &mentis_rules::Line,
    names: &HashMap<String, String>,
) -> Result<Py, OpError> {
    let last = line.versions.last().map(|v| v.id.as_str());
    let mut rows = Vec::new();
    for (i, v) in line.versions.iter().enumerate() {
        let b = py_body(&v.body_json)?;
        let parts = match b.get("parts") {
            Some(Py::List(x)) => x.clone(),
            None | Some(Py::None) => vec![],
            _ => return Err(python_says("version parts")),
        };
        rows.push(dict([
            ("entry", Py::str(&v.id)),
            ("version", Py::int(i + 1)),
            ("at", Py::Float(v.recorded_at)),
            ("by", Py::opt_str(v.attributed_to.as_deref())),
            (
                "by_alias",
                Py::opt_str(
                    v.attributed_to
                        .as_ref()
                        .map(|id| names.get(id).cloned().unwrap_or_else(|| id.clone()))
                        .as_deref(),
                ),
            ),
            ("written_by", Py::None),
            ("because", Py::None),
            ("current", Py::Bool(last == Some(v.id.as_str()))),
            ("parts", Py::List(parts)),
        ]));
    }
    Ok(dict([
        ("entry", Py::str(&line.root)),
        ("versions", Py::List(rows)),
        ("current", Py::opt_str(last)),
        ("deleted", Py::None),
    ]))
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

fn addressees(
    scope: &mut dyn ReadScope,
    states: &[ExpectationState],
    names: &HashMap<String, String>,
    turn: &str,
) -> Result<Py, OpError> {
    let mut ids: Vec<String> = states
        .iter()
        .filter_map(|s| s.expected_of.clone())
        .collect();
    ids.sort();
    ids.dedup();
    let mut rows = Vec::new();
    for id in ids {
        let delivered_sql =
            "SELECT 1 FROM delivery WHERE participant=?1 AND material LIKE ?2 LIMIT 1";
        let mut delivered = false;
        let like = format!("%{turn}%");
        scope.query(
            delivered_sql,
            &[Param::Text(&id), Param::Text(&like)],
            &mut |_| {
                delivered = true;
                Ok(Flow::Stop)
            },
        )?;
        rows.push(dict([
            ("participant", Py::str(&id)),
            (
                "alias",
                Py::str(names.get(&id).cloned().unwrap_or_else(|| id.clone())),
            ),
            ("addressed", Py::Bool(true)),
            ("delivered", Py::Bool(delivered)),
            ("responded", Py::Bool(false)),
            ("failed", Py::None),
            ("addressed_later", Py::Bool(false)),
            ("addressed_by", Py::None),
            ("addressed_because", Py::None),
        ]));
    }
    Ok(Py::List(rows))
}

const INTAKE_LINKS: &str = "SELECT id, link_from, link_to, attributed_to, written_by, recorded_at \
    FROM entry WHERE link_relation = 'carries-intake' ORDER BY seq";
const UNRESOLVED: &str = "SELECT id, caused_by, at FROM operational WHERE act = \
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

fn resumable(scope: &mut dyn ReadScope, overlay: &Overlay) -> Result<Vec<String>, OpError> {
    let mut candidates = Vec::new();
    let mut seen = HashSet::new();
    scope.query(UNRESOLVED, &[], &mut |row| {
        if let Some(id) = text(row, 1)?
            && seen.insert(id.clone())
        {
            candidates.push(id)
        }
        Ok(Flow::Continue)
    })?;
    let asked = ReadRequest {
        args: ExpectationStatesArgs {
            ids: candidates.clone(),
        },
        cursor: None,
        limit: None,
        deadline: std::time::Instant::now() + std::time::Duration::from_secs(5),
    };
    let states = ExpectationStates.read(scope, &asked)?.rows;
    let mut out = Vec::new();
    for state in states {
        if !state.unassigned
            || !state.satisfied_by.is_empty()
            || execution_bool(overlay, &state, scope)?
        {
            continue;
        }
        let Some(turn) = state.turn.as_deref() else {
            continue;
        };
        let mut replied = false;
        scope.query(REPLIES_TO, &[Param::Text(turn)], &mut |row| {
            let by = text(row, 0)?;
            if by != state.requested_by {
                replied = true
            }
            Ok(Flow::Continue)
        })?;
        if !replied {
            out.push(state.expectation)
        }
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
        statements: 64 * 45,
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
    const BUDGET: Budget = Budget {
        statements: 64 * 45,
    };
    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<ViewRow>, OpError> {
        let (home, _) = home_and_number(scope, &request.args.root)?;
        if home.as_deref() != Some(&request.args.conversation) {
            return Err(OpError::BadRequest {
                why: format!("{} is not a turn of this conversation", request.args.root),
            });
        }
        let links = crate::window::reads::links_from(scope, "replies-to", &[&request.args.root])?;
        if let Some(parent) = links.first() {
            return Err(OpError::BadRequest {
                why: format!(
                    "{} is a reply, not a thread root; its thread is {}",
                    request.args.root, parent.to
                ),
            });
        }
        let mut head = turn_view(
            scope,
            &request.args.root,
            &request.args.overlay,
            Some(&request.args.conversation),
        )?;
        strip_detail(&mut head);
        let replies = crate::window::reads::closures(scope, &[&request.args.root])?
            .remove(&request.args.root)
            .unwrap_or_default();
        let mut number_by = HashMap::new();
        let mut all = Vec::new();
        scope.query(
            CONVERSATION_TURNS,
            &[Param::Text(&request.args.conversation)],
            &mut |row| {
                all.push(text(row, 0)?.unwrap_or_default());
                Ok(Flow::Continue)
            },
        )?;
        for (i, id) in all.iter().enumerate() {
            number_by.insert(id.clone(), i as i64 + 1);
        }
        place(
            &mut head,
            &request.args.root,
            None,
            &number_by,
            &replies,
            scope,
        )?;
        let mut shown = Vec::new();
        for reply in &replies {
            let mut row = turn_view(
                scope,
                &reply.id,
                &request.args.overlay,
                Some(&request.args.conversation),
            )?;
            strip_detail(&mut row);
            place(
                &mut row,
                &request.args.root,
                reply.parent.as_deref(),
                &number_by,
                &replies,
                scope,
            )?;
            shown.push(row)
        }
        let answer = dict([
            ("conversation", Py::str(&request.args.conversation)),
            ("root", Py::str(&request.args.root)),
            ("turn", head),
            ("replies_total", Py::int(replies.len())),
            ("replies", Py::List(shown)),
        ]);
        Ok(ReadAnswer {
            rows: vec![ViewRow(answer)],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

fn strip_detail(row: &mut Py) {
    if let Py::Dict(items) = row {
        items.retain(|(key, _)| !matches!(key.as_str(), "versions" | "filings" | "inspector"));
    }
}

fn place(
    row: &mut Py,
    root: &str,
    parent: Option<&str>,
    numbers: &HashMap<String, i64>,
    replies: &[crate::window::reads::Reply],
    scope: &mut dyn ReadScope,
) -> Result<(), OpError> {
    let id = row
        .get("id")
        .and_then(Py::as_str)
        .unwrap_or_default()
        .to_owned();
    let kids: Vec<_> = replies
        .iter()
        .filter(|r| r.parent.as_deref() == Some(&id))
        .collect();
    let mut repliers = Vec::new();
    let kid_ids: Vec<&str> = kids.iter().map(|r| r.id.as_str()).collect();
    if !kid_ids.is_empty() {
        let heads = crate::window::reads::heads(scope, &kid_ids)?;
        for kid in kids.iter().rev() {
            if let Some(by) = heads.get(&kid.id).and_then(|h| h.attributed_to.clone())
                && !repliers.contains(&by)
            {
                repliers.push(by);
                if repliers.len() == 3 {
                    break;
                }
            }
        }
    }
    row.set("root", Py::str(root));
    row.set(
        "answering_number",
        parent
            .and_then(|p| numbers.get(p).copied())
            .map_or(Py::None, Py::int),
    );
    row.set(
        "parent_in_scope",
        parent
            .map(|p| Py::Bool(numbers.contains_key(p)))
            .unwrap_or(Py::None),
    );
    row.set("thread_replies", Py::int(kids.len()));
    row.set(
        "thread_repliers",
        Py::List(repliers.into_iter().map(Py::str).collect()),
    );
    Ok(())
}

#[derive(Clone, Debug)]
pub struct DecisionsViewArgs {
    pub post: Option<String>,
    pub ids: Vec<String>,
    pub overlay: Overlay,
    pub owner: Option<String>,
}
#[derive(Clone, Copy, Debug, Default)]
pub struct DecisionsView;
impl ReadOp for DecisionsView {
    type Args = DecisionsViewArgs;
    type Row = ViewRow;
    const NAME: &'static str = "decisions-view";
    const BUDGET: Budget = Budget {
        statements: 64 * 45,
    };
    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<ViewRow>, OpError> {
        let held_owner = match &request.args.owner {
            Some(id) => Some(id.clone()),
            None => owner(scope)?,
        };
        let answer = if let Some(post) = &request.args.post {
            let view = turn_view(scope, post, &request.args.overlay, None)?;
            let home = home_and_number(scope, post)?.0;
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
                (
                    "deleted",
                    Py::Bool(view.get("deleted").is_some_and(Py::truthy)),
                ),
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
            let forms = forms::forms(scope, &request.args.ids)?;
            let mut wanted = Vec::new();
            for f in &forms {
                wanted.extend(f.questions.iter().map(|q| q.expectation.clone()))
            }
            let form_ids: HashSet<_> = wanted.iter().cloned().collect();
            for id in &request.args.ids {
                if !form_ids.contains(id) {
                    wanted.push(id.clone())
                }
            }
            let asked = ReadRequest {
                args: ExpectationStatesArgs { ids: wanted },
                cursor: None,
                limit: None,
                deadline: std::time::Instant::now() + std::time::Duration::from_secs(5),
            };
            let states = ExpectationStates.read(scope, &asked)?.rows;
            let names = aliases_for_states(scope, &states, None)?;
            let views = states
                .iter()
                .map(|s| expectation_py(scope, s, &request.args.overlay, &names))
                .collect::<Result<Vec<_>, _>>()?;
            dict([
                ("post", Py::None),
                ("you", Py::opt_str(held_owner.as_deref())),
                ("expectations", Py::List(views)),
                ("decision_forms", serde_py(&forms)?),
            ])
        };
        Ok(ReadAnswer {
            rows: vec![ViewRow(answer)],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

fn owner(scope: &mut dyn ReadScope) -> Result<Option<String>, OpError> {
    let sql = "SELECT id, body FROM entry WHERE family='entry' AND def_name='participant' AND link_relation IS NULL ORDER BY seq";
    let mut out = None;
    scope.query(sql, &[], &mut |row| {
        let id = text(row, 0)?.unwrap_or_default();
        let body = text(row, 1)?.and_then(|raw| loads(&raw));
        if body
            .as_ref()
            .and_then(|b| b.get("about"))
            .and_then(Py::as_str)
            == Some("the owner")
        {
            out = Some(id);
            return Ok(Flow::Stop);
        }
        Ok(Flow::Continue)
    })?;
    Ok(out)
}
