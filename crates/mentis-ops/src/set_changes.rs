//! `history set= since=`: `Surface.set_changes` and `form_changes`, `worker.py:1679`, `:1647`. `since`
//! is [`ReadRequest::cursor`]. A bad `since` is `BadRequest`, a set that isn't one is `NotFound`, and
//! what to do next, in words, is the door's. A page holding an interpretation reads the words it
//! quotes as well, and that page is Python's.

use mentis_record::{Flow, Id, Param, ReadScope};
use mentis_rules::{STATEMENTS, Versioned};
use serde::Serialize;

use crate::acts::{real, text};
use crate::forms::{self, Form};
use crate::stored::{Object, Stored, python_says};
use crate::{Budget, Cursor, OpError, ReadAnswer, ReadOp, ReadRequest, python};

const THE_SET: &str = "SELECT family, def_name, link_relation FROM entry WHERE id = ?1";

const MEMBER_IDS: &str = "SELECT link_from FROM entry \
     WHERE link_relation = 'in-response-set' AND link_to = ?1 ORDER BY seq";

const MEMBERS: &str = "SELECT id, def_name, attributed_to, recorded_at, body FROM entry \
     WHERE id IN (SELECT value FROM json_each(?1)) ORDER BY seq";

/// `PAGE`, and `SINCE_MAX`, the most one page gives.
const DEFAULT_LIMIT: u32 = 40;
const MOST: u32 = 200;

/// Changes in a response set or a decision form.
#[derive(Clone, Copy, Debug, Default)]
pub struct SetChanges;

/// The set or form. `since` is [`ReadRequest::cursor`].
#[derive(Clone, Debug, Default)]
pub struct SetChangesArgs {
    pub set: String,
}

/// The answer's one row.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ChangesPage {
    pub set: String,
    pub since: Option<String>,
    /// A change's fields are its body's, so they are as many as the set's answers hold. Each holds
    /// `entry`, `kind`, `at` and `when`, and a set's also `by` and `by_alias`.
    pub changes: Vec<Object>,
    pub cursor: String,
    pub not_returned: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub decision_form: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub open: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub closed: Option<bool>,
}

struct Member {
    id: String,
    kind: Option<String>,
    by: Option<String>,
    at: f64,
    body: Option<String>,
}

/// Where a page starts, or the door's refusal, in the words the route has always used.
fn start_of(since: Option<&str>, set: &str, ids: &[&str], not_one: &str) -> Result<usize, OpError> {
    let Some(since) = since.filter(|since| *since != set) else {
        return Ok(0);
    };
    match ids.iter().position(|id| *id == since) {
        Some(at) => Ok(at + 1),
        None => {
            let shown = python::repr(since)
                .ok_or_else(|| python_says("a `since` Python has to show itself"))?;
            Err(OpError::BadRequest {
                why: format!(
                    "{shown} is not {not_one}: pass the `cursor` an earlier read returned, or \
                     the {} itself to read from the start",
                    if not_one.contains("form") {
                        "form"
                    } else {
                        "set"
                    }
                ),
            })
        }
    }
}

impl ReadOp for SetChanges {
    type Args = SetChangesArgs;
    type Row = ChangesPage;

    const NAME: &'static str = "set_changes";
    /// The position, and either the set, its member ids, its members and their aliases, or the
    /// set's refusal and the form instead.
    const BUDGET: Budget = Budget {
        statements: 4 + STATEMENTS + forms::STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<SetChangesArgs>,
    ) -> Result<ReadAnswer<ChangesPage>, OpError> {
        let as_of = scope.position();
        let set = request.args.set.clone();
        let since = request
            .cursor
            .as_ref()
            .map(|Cursor(since)| python::strip(since))
            .filter(|since| !since.is_empty());
        // `max(1, min(int(limit or PAGE), SINCE_MAX))`.
        let limit = match request.limit {
            None | Some(0) => DEFAULT_LIMIT,
            Some(limit) => limit,
        }
        .min(MOST) as usize;

        let mut found: Option<(Option<String>, Option<String>, bool)> = None;
        scope.query(THE_SET, &[Param::Text(&set)], &mut |row| {
            found = Some((text(row, 0)?, text(row, 1)?, text(row, 2)?.is_some()));
            Ok(Flow::Stop)
        })?;
        let (page, more) = match &found {
            Some((Some(family), Some(kind), false))
                if family == "entry" && kind == "response-set" =>
            {
                of_a_set(scope, &set, since, limit)?
            }
            _ => {
                let refusal = match &found {
                    Some((family, _, is_link))
                        if family.as_deref() == Some("entry") && !is_link =>
                    {
                        format!("{set} is not a response set")
                    }
                    _ => "the record holds no such response set".to_owned(),
                };
                // A form this can't read goes to Python, whose `try` decides what it is.
                let form = forms::forms(scope, std::slice::from_ref(&set))?.pop();
                match form {
                    Some(form) => of_a_form(&form, since, limit)?,
                    None => return Err(OpError::NotFound { what: refusal }),
                }
            }
        };
        Ok(ReadAnswer {
            rows: vec![page],
            as_of,
            more,
            not_searched: Vec::new(),
        })
    }
}

fn of_a_form(
    form: &Form,
    since: Option<&str>,
    limit: usize,
) -> Result<(ChangesPage, Option<Cursor>), OpError> {
    let members = forms::members(form);
    let ids: Vec<&str> = members.iter().map(|m| m.entry.as_str()).collect();
    let start = start_of(
        since,
        &form.form,
        &ids,
        "an answer or withdrawal of this decision form",
    )?;
    let rest = &members[start..];
    let page = &rest[..limit.min(rest.len())];
    let changes = page
        .iter()
        .map(|member| {
            let mut fields = member.fields.clone();
            fields.set("when", Stored::of(&python::when(member.at)));
            fields
        })
        .collect();
    let cursor = page
        .last()
        .map(|last| last.entry.clone())
        .unwrap_or_else(|| since.unwrap_or(&form.form).to_owned());
    let more = (rest.len() > page.len()).then(|| Cursor(cursor.clone()));
    Ok((
        ChangesPage {
            set: form.form.clone(),
            since: since.map(str::to_owned),
            changes,
            cursor,
            not_returned: (rest.len() - page.len()) as u64,
            decision_form: Some(true),
            open: Some(form.open),
            closed: Some(form.closed),
        },
        more,
    ))
}

fn of_a_set(
    scope: &mut dyn ReadScope,
    set: &str,
    since: Option<&str>,
    limit: usize,
) -> Result<(ChangesPage, Option<Cursor>), OpError> {
    let mut linked: Vec<String> = Vec::new();
    scope.query(MEMBER_IDS, &[Param::Text(set)], &mut |row| {
        linked.extend(text(row, 0)?);
        Ok(Flow::Continue)
    })?;
    let mut members: Vec<Member> = Vec::new();
    if !linked.is_empty() {
        let asked = mentis_rules::id_list(linked.iter().map(String::as_str));
        scope.query(MEMBERS, &[Param::Text(&asked)], &mut |row| {
            members.push(Member {
                id: text(row, 0)?.unwrap_or_default(),
                kind: text(row, 1)?,
                by: text(row, 2)?,
                at: real(row, 3)?,
                body: text(row, 4)?,
            });
            Ok(Flow::Continue)
        })?;
    }
    // `(recorded_at, order.get(id))`, and a repeated link leaves its last place in `order`.
    let place = |id: &str| linked.iter().rposition(|linked| linked == id).unwrap_or(0);
    members.sort_by(|a, b| {
        a.at.total_cmp(&b.at)
            .then_with(|| place(&a.id).cmp(&place(&b.id)))
    });

    let ids: Vec<&str> = members.iter().map(|m| m.id.as_str()).collect();
    let start = start_of(since, set, &ids, "an entry of this response set")?;
    let rest = &members[start..];
    let page = &rest[..limit.min(rest.len())];

    let mut people: Vec<Id> = page
        .iter()
        .filter_map(|m| m.by.clone().filter(|by| !by.is_empty()))
        .map(Id)
        .collect();
    people.sort();
    people.dedup();
    let seen = mentis_rules::reads(scope, &people, Versioned::Participants)?;

    let mut changes = Vec::with_capacity(page.len());
    for member in page {
        if member.kind.as_deref() == Some("interpretation") {
            return Err(python_says(
                "an interpretation, which reads the words it quotes",
            ));
        }
        let mut body = Object::or_empty(member.body.as_deref().unwrap_or(""))?;
        body.remove("set");
        let by_alias = match &member.by {
            None => None,
            Some(by) => {
                let id = Id(by.clone());
                Some(
                    mentis_rules::alias_of(seen.get(&id), &id)
                        .ok_or_else(|| python_says("somebody this can't read"))?,
                )
            }
        };
        let mut fields = Object::default();
        fields.set("entry", Stored::of(&member.id));
        fields.set("kind", Stored::of(&member.kind));
        fields.set("by", Stored::of(&member.by));
        fields.set("by_alias", Stored::of(&by_alias));
        fields.set("at", Stored::of(&member.at));
        fields.set("when", Stored::of(&python::when(member.at)));
        // `**b`: what the body holds goes over what is named here, where it holds the same.
        for (key, value) in body.0 {
            fields.set(&key, value);
        }
        changes.push(fields);
    }
    let cursor = page
        .last()
        .map(|last| last.id.clone())
        .unwrap_or_else(|| since.unwrap_or(set).to_owned());
    let more = (rest.len() > page.len()).then(|| Cursor(cursor.clone()));
    Ok((
        ChangesPage {
            set: set.to_owned(),
            since: since.map(str::to_owned),
            changes,
            cursor,
            not_returned: (rest.len() - page.len()) as u64,
            decision_form: None,
            open: None,
            closed: None,
        },
        more,
    ))
}
