//! Durable response-set readings: a field's and the own words' history, and the accounting.
//!
//! **What takes the form's own check is Python's.** A set's state and a post's list of them need the
//! UI bundle's `_block_check`, and an interpretation's view reads the block's fields the same way,
//! which `render_check` keeps on Python until its write-side callers move
//! (`R4-R8-reconcile.md`, R5.1). So those forward, and so does a set the record doesn't hold: its
//! refusal is the route's own shape, and Python gives it.

use std::collections::{HashMap, HashSet};

use mentis_record::{Flow, Id, Param, ReadScope};

use crate::lists::{loaded, not_owned};
use crate::pyjson::{Py, dict};
use crate::window::collections::PyRow;
use crate::window::reads;
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest, python};

const SET_HEAD: &str = "SELECT family,def_name,link_relation,body FROM entry WHERE id=?1";
/// `_members`: by time, ties by each entry's last link, each entry once.
const MEMBERS: &str = "SELECT e.id,e.def_name,e.body,e.attributed_to,e.recorded_at \
 FROM entry e JOIN (SELECT link_from,MAX(seq) s FROM entry WHERE link_relation='in-response-set' AND link_to=?1 \
 GROUP BY link_from) l ON l.link_from=e.id ORDER BY e.recorded_at,l.s";

#[derive(Clone, Debug)]
pub enum ResponseRead {
    FieldHistory { set: String, field: String },
    WordsHistory { set: String, by: Option<String> },
    Accounting { set: String },
}

pub struct ResponseSets;

#[derive(Clone)]
struct Member {
    id: String,
    kind: String,
    body: Py,
    by: Option<String>,
    at: Py,
}

fn member_rows(scope: &mut dyn ReadScope, sid: &str) -> Result<Vec<Member>, OpError> {
    let mut out = Vec::new();
    let mut bodies = Vec::new();
    scope.query(MEMBERS, &[Param::Text(sid)], &mut |r| {
        bodies.push(reads::text(r, 2)?);
        out.push(Member {
            id: reads::text(r, 0)?.unwrap_or_default(),
            kind: reads::text(r, 1)?.unwrap_or_default(),
            body: Py::None,
            by: reads::text(r, 3)?,
            at: reads::number(r, 4)?,
        });
        Ok(Flow::Continue)
    })?;
    for (member, body) in out.iter_mut().zip(bodies) {
        member.body = loaded(&body.ok_or_else(|| not_owned("a member with no body"))?)?;
    }
    Ok(out)
}

/// `_set`, whose refusal is Python's to word.
fn set_exists(scope: &mut dyn ReadScope, sid: &str) -> Result<Py, OpError> {
    let mut body = None;
    scope.query(SET_HEAD, &[Param::Text(sid)], &mut |r| {
        if reads::text(r, 0)?.as_deref() == Some("entry")
            && reads::text(r, 1)?.as_deref() == Some("response-set")
            && reads::text(r, 2)?.is_none()
        {
            body = reads::text(r, 3)?;
        }
        Ok(Flow::Stop)
    })?;
    let body = body.ok_or_else(|| not_owned("a response set Python refuses"))?;
    loaded(&body)
}

/// What `accounting` asks of the form before it answers: `_fields_now` refuses a post whose current
/// version has no such text part, and that refusal is Python's. A deleted post isn't asked.
fn the_block_is_there(scope: &mut dyn ReadScope, set: &Py) -> Result<(), OpError> {
    let refused = || not_owned("a set whose form Python refuses");
    let post = set.get("post").and_then(Py::as_str).ok_or_else(refused)?;
    if set.get("block").is_none() {
        return Err(refused());
    }
    let id = Id(post.to_owned());
    let now = mentis_rules::now_reads(scope, std::slice::from_ref(&id))?;
    let reading = now
        .get(&id)
        .filter(|r| !r.python_says)
        .ok_or_else(refused)?;
    if reading.deleted.is_some() {
        return Ok(());
    }
    let part = match set.get("part") {
        None => 0,
        Some(Py::Int(digits)) => digits.parse::<usize>().map_err(|_| refused())?,
        Some(_) => return Err(refused()),
    };
    let body = loaded(&reading.body_json)?;
    let parts = body
        .get("parts")
        .filter(|parts| parts.truthy())
        .and_then(Py::as_list)
        .ok_or_else(refused)?;
    match parts.get(part) {
        Some(p)
            if p.is_dict()
                && p.get("type").and_then(Py::as_str) == Some("text")
                && p.get("text").and_then(Py::as_str).is_some() =>
        {
            Ok(())
        }
        _ => Err(refused()),
    }
}

fn aliases(
    scope: &mut dyn ReadScope,
    members: &[Member],
) -> Result<HashMap<String, String>, OpError> {
    let ids: Vec<Id> = members
        .iter()
        .filter_map(|m| m.by.as_ref())
        .map(|x| Id(x.clone()))
        .collect();
    crate::lists::aliases_of(scope, &ids)
}

fn by_alias(m: &Member, names: &HashMap<String, String>) -> Py {
    m.by.as_deref().map_or(Py::None, |by| {
        Py::str(names.get(by).map_or(by, String::as_str))
    })
}

/// `list(b.get("replaces") or [])`.
fn replaces(body: &Py) -> Result<Py, OpError> {
    match body.get("replaces").filter(|r| r.truthy()) {
        None => Ok(Py::List(vec![])),
        Some(list) if list.as_list().is_some() => Ok(list.clone()),
        Some(_) => Err(not_owned("a replaces that isn't a list")),
    }
}

fn answer_row(m: &Member, names: &HashMap<String, String>) -> Result<Py, OpError> {
    let b = &m.body;
    let (Some(field), Some(value)) = (b.get("field"), b.get("value")) else {
        return Err(not_owned("an answer Python raises on"));
    };
    Ok(dict([
        ("answer", Py::str(&m.id)),
        ("field", field.clone()),
        ("value", value.clone()),
        ("note", b.get("note").cloned().unwrap_or(Py::None)),
        ("replaces", replaces(b)?),
        ("version", b.get("version").cloned().unwrap_or(Py::None)),
        ("by", m.by.as_deref().map_or(Py::None, Py::str)),
        ("by_alias", by_alias(m, names)),
        ("at", m.at.clone()),
        ("check", b.get("check").cloned().unwrap_or(Py::None)),
        (
            "conversation",
            b.get("conversation").cloned().unwrap_or(Py::None),
        ),
    ]))
}

fn words_row(m: &Member, names: &HashMap<String, String>) -> Result<Py, OpError> {
    let b = &m.body;
    let text = b
        .get("text")
        .ok_or_else(|| not_owned("own words Python raises on"))?;
    Ok(dict([
        ("words", Py::str(&m.id)),
        ("text", text.clone()),
        ("replaces", replaces(b)?),
        (
            "conversation",
            b.get("conversation").cloned().unwrap_or(Py::None),
        ),
        ("by", m.by.as_deref().map_or(Py::None, Py::str)),
        ("by_alias", by_alias(m, names)),
        ("at", m.at.clone()),
    ]))
}

impl ReadOp for ResponseSets {
    type Args = ResponseRead;
    type Row = PyRow;
    const NAME: &'static str = "response_sets";
    const BUDGET: Budget = Budget {
        statements: 3 + mentis_rules::STATEMENTS * 2,
    };
    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let as_of = scope.position();
        let value = match &request.args {
            ResponseRead::FieldHistory { set, field } => {
                set_exists(scope, set)?;
                let all = member_rows(scope, set)?;
                let names = aliases(scope, &all)?;
                let mut history = Vec::new();
                for m in all.iter().filter(|m| m.kind == "answer") {
                    let held = m
                        .body
                        .get("field")
                        .ok_or_else(|| not_owned("an answer Python raises on"))?;
                    if held.as_str() == Some(field) {
                        history.push(answer_row(m, &names)?);
                    }
                }
                dict([
                    ("set", Py::str(set)),
                    ("field", Py::str(field)),
                    ("history", Py::List(history)),
                ])
            }
            ResponseRead::WordsHistory { set, by } => {
                set_exists(scope, set)?;
                let all = member_rows(scope, set)?;
                let names = aliases(scope, &all)?;
                let mut rows = Vec::new();
                for m in all.iter().filter(|m| {
                    m.kind == "own-words" && by.as_ref().is_none_or(|x| m.by.as_ref() == Some(x))
                }) {
                    rows.push(words_row(m, &names)?);
                }
                dict([("set", Py::str(set)), ("words", Py::List(rows))])
            }
            ResponseRead::Accounting { set } => {
                let head = set_exists(scope, set)?;
                the_block_is_there(scope, &head)?;
                let all = member_rows(scope, set)?;
                if all.iter().any(|m| m.kind == "interpretation") {
                    return Err(not_owned(
                        "an interpretation read against the block's fields",
                    ));
                }
                let names = aliases(scope, &all)?;
                let words: Vec<&Member> = all.iter().filter(|m| m.kind == "own-words").collect();
                let mut replaced: HashSet<&str> = HashSet::new();
                for w in &words {
                    let list = w.body.get("replaces").filter(|r| r.truthy());
                    for id in list.and_then(Py::as_list).unwrap_or(&[]) {
                        replaced.insert(
                            id.as_str()
                                .ok_or_else(|| not_owned("a replaces that isn't references"))?,
                        );
                    }
                }
                let mut out = Vec::new();
                for w in words.iter().filter(|w| !replaced.contains(w.id.as_str())) {
                    let text = w
                        .body
                        .get("text")
                        .and_then(Py::as_str)
                        .ok_or_else(|| not_owned("own words Python raises on"))?;
                    // `_gaps` with nothing cited: the whole, if it says anything.
                    let gaps = if python::strip(text).is_empty() {
                        vec![]
                    } else {
                        vec![dict([
                            ("start", Py::int(0)),
                            ("end", Py::int(text.chars().count())),
                            ("excerpt", Py::str(text)),
                        ])]
                    };
                    let mut row = words_row(w, &names)?;
                    row.set("passages", Py::List(vec![]));
                    row.set("not_cited", Py::List(gaps));
                    row.set("on_earlier_wording", Py::List(vec![]));
                    out.push(row);
                }
                dict([("set", Py::str(set)), ("words", Py::List(out))])
            }
        };
        Ok(ReadAnswer {
            rows: vec![PyRow(value)],
            as_of,
            more: None,
            not_searched: vec![],
        })
    }
}
