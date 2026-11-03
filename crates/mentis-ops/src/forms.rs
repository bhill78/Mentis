//! A decision form as the record holds it: `Conversations.decision_form`,
//! `conversation/__init__.py:3877`, and `Surface._form_members`, `worker.py:1624`, for `resolve` of a
//! Turn and `history set=<form>`.
//!
//! **Only what `decision_form` reads of `expectation_state`.** Which runs are live is in that state
//! and not in a form, so nothing here looks at an execution. A question that is a reconsideration or
//! an input takes other reads, and those forms are Python's.

use std::collections::{HashMap, HashSet};

use mentis_record::{Flow, Param, ReadScope};
use serde::Serialize;

use crate::acts::{Act, text};
use crate::stored::{Object, Stored, python_says};
use crate::{OpError, act_columns};

/// `decision_forms_on`.
const ON_TURN: &str = "SELECT id, act, caused_by FROM operational WHERE turn = ?1 ORDER BY seq";

pub(crate) const BY_ID: &str = concat!(
    "SELECT ",
    act_columns!(),
    " FROM operational WHERE id IN (SELECT value FROM json_each(?1)) ORDER BY seq"
);

/// What the forms' requests caused, for each form's questions.
const QUESTIONS: &str = concat!(
    "SELECT ",
    act_columns!(),
    " FROM operational WHERE caused_by IN (SELECT value FROM json_each(?1)) \
     AND act = 'expectation-recorded' ORDER BY seq"
);

/// `_own_acts` of every question at once: everything under them, going no further than another
/// expectation. [`own_acts`] then walks it for each one, in Python's order.
pub(crate) const UNDER: &str = concat!(
    "WITH RECURSIVE under(id, act) AS ( \
       SELECT o.id, o.act FROM operational o \
       WHERE o.caused_by IN (SELECT value FROM json_each(?1)) \
       UNION SELECT o.id, o.act FROM under u JOIN operational o ON o.caused_by = u.id \
         WHERE u.act IS NOT 'expectation-recorded') \
     SELECT ",
    act_columns!(),
    " FROM operational WHERE id IN (SELECT id FROM under) ORDER BY seq"
);

/// The forms' attachments, for `_form_post`.
pub(crate) const ATTACHED: &str = "SELECT caused_by, turn FROM operational \
     WHERE caused_by IN (SELECT value FROM json_each(?1)) AND act = 'decision-form-attached' \
     ORDER BY seq";

/// The statements [`forms`] runs: the forms, the questions, what is under them, the attachments.
pub const STATEMENTS: u32 = 4;
/// And [`on_turn`], which asks which forms first.
pub const ON_TURN_STATEMENTS: u32 = STATEMENTS + 1;

/// A question's answer, by the reply that named it.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Answer {
    pub reply: Stored,
    pub act: String,
    pub at: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub option: Option<Stored>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub label: Option<Stored>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub words: Option<Stored>,
}

/// Who withdrew a question, when and why.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Withdrawn {
    pub act: String,
    pub by: Option<String>,
    pub at: f64,
    pub because: Option<String>,
    pub reply: Stored,
}

/// Why a run's permission question stopped being asked.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Lapsed {
    pub act: String,
    pub by: Option<String>,
    pub at: f64,
    pub because: Option<String>,
    pub reason: Stored,
    pub run: Stored,
}

/// One question, and what became of it.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Question {
    pub expectation: String,
    pub index: Stored,
    pub question: Stored,
    pub options: Stored,
    pub because: Option<String>,
    pub of: Option<String>,
    pub answered: bool,
    pub answer: Option<Answer>,
    pub withdrawn: Option<Withdrawn>,
    pub lapsed: Option<Lapsed>,
    pub open: bool,
    pub closed_at: Option<f64>,
}

/// One form. `cursor` is what `history set=<form>` reads on from. How to read it is the door's to
/// say.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Form {
    pub form: String,
    pub post: Option<String>,
    pub pending: bool,
    pub on: Option<String>,
    pub conversation: Option<String>,
    pub asked_by: Option<String>,
    pub execution: Option<String>,
    pub request: Option<String>,
    pub at: f64,
    pub because: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub operation: Option<Stored>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub run: Option<Stored>,
    pub questions: Vec<Question>,
    pub open: u64,
    pub closed: bool,
    pub closed_at: Option<f64>,
    pub cursor: String,
}

/// One thing that became of a form's question, oldest first.
#[derive(Clone, Debug, PartialEq)]
pub struct Member {
    pub entry: String,
    pub at: f64,
    /// As the row reads, with its `when` still to come.
    pub fields: Object,
}

/// `_form_members`.
pub fn members(form: &Form) -> Vec<Member> {
    let mut rows: Vec<Member> = Vec::new();
    for q in &form.questions {
        let base = |fields: &mut Object| {
            fields.set("expectation", Stored::of(&q.expectation));
            fields.set("index", q.index.clone());
            fields.set("question", q.question.clone());
        };
        if let Some(a) = &q.answer {
            let mut fields = Object::default();
            fields.set("entry", Stored::of(&a.act));
            fields.set("kind", Stored::of(&"decision-answered"));
            fields.set("at", Stored::of(&a.at));
            base(&mut fields);
            fields.set("reply", a.reply.clone());
            for (key, value) in [
                ("option", &a.option),
                ("label", &a.label),
                ("words", &a.words),
            ] {
                if let Some(value) = value {
                    fields.set(key, value.clone());
                }
            }
            rows.push(Member {
                entry: a.act.clone(),
                at: a.at,
                fields,
            });
        }
        if let Some(w) = &q.withdrawn {
            let mut fields = Object::default();
            fields.set("entry", Stored::of(&w.act));
            fields.set("kind", Stored::of(&"decision-withdrawn"));
            fields.set("at", Stored::of(&w.at));
            fields.set("by", Stored::of(&w.by));
            base(&mut fields);
            fields.set("because", Stored::of(&w.because));
            fields.set("reply", w.reply.clone());
            rows.push(Member {
                entry: w.act.clone(),
                at: w.at,
                fields,
            });
        }
    }
    // `sorted` by time is stable, and an act only ever appears once here.
    rows.sort_by(|a, b| a.at.total_cmp(&b.at));
    rows
}

pub(crate) fn read_acts(
    scope: &mut dyn ReadScope,
    statement: &'static str,
    ids: &str,
) -> Result<Vec<Act>, OpError> {
    let mut acts = Vec::new();
    scope.query(statement, &[Param::Text(ids)], &mut |row| {
        acts.push(Act::read(row, 0)?);
        Ok(Flow::Continue)
    })?;
    Ok(acts)
}

/// `_descendants(root, through_expectations=False)`: level by level, in write order within each
/// parent, then by time, which keeps that order among equal times.
pub(crate) fn own_acts<'a>(root: &str, children: &HashMap<&str, Vec<&'a Act>>) -> Vec<&'a Act> {
    let mut out: Vec<&Act> = Vec::new();
    let mut seen: HashSet<&str> = HashSet::from([root]);
    let mut frontier: Vec<&str> = vec![root];
    while !frontier.is_empty() {
        let mut next = Vec::new();
        for parent in frontier {
            for act in children.get(parent).map_or(&[][..], Vec::as_slice) {
                if !seen.insert(&act.id) {
                    continue;
                }
                out.push(act);
                if !act.is("expectation-recorded") {
                    next.push(act.id.as_str());
                }
            }
        }
        frontier = next;
    }
    out.sort_by(|a, b| a.at.total_cmp(&b.at));
    out
}

/// The first of `about`, as a Participant. A list's first item that isn't text would be compared
/// with an actor in Python, and match nothing we can show.
pub(crate) fn first_about(act: &Act) -> Result<Option<String>, OpError> {
    let items = act.about_items()?;
    let Some(first) = items.first() else {
        return Ok(None);
    };
    if first.is_null() {
        return Ok(None);
    }
    first
        .string()?
        .map(Some)
        .ok_or_else(|| python_says("a carrier that isn't a reference"))
}

/// `assigned_carrier`'s `carrier`: the latest assignment, or who it was asked of.
fn carrier(expectation: &Act, children: &[&Act]) -> Result<Option<String>, OpError> {
    let mut assignments = Vec::new();
    for act in children {
        if act.is("expectation-assigned") && !act.about_items()?.is_empty() {
            assignments.push(*act);
        }
    }
    assignments.sort_by(|a, b| a.at.total_cmp(&b.at));
    match assignments.last() {
        Some(latest) => first_about(latest),
        None => first_about(expectation),
    }
}

/// `expectation_state`'s `withdrawn`: the first `expectation-met` by the responder marked so.
pub(crate) fn withdrawn_in(
    mine: &[&Act],
    responder: Option<&String>,
) -> Result<Option<Withdrawn>, OpError> {
    for act in mine {
        if act.is("expectation-met")
            && responder.is_some()
            && act.actor.as_ref() == responder
            && act.detail_object()?.is_truthy("withdrawn")?
        {
            return Ok(Some(Withdrawn {
                act: act.id.clone(),
                by: act.actor.clone(),
                at: act.at,
                because: act.because.clone(),
                reply: act.detail_object()?.get_or_null("reply"),
            }));
        }
    }
    Ok(None)
}

/// `expectation_state`'s `lapsed`: the first `expectation-met` marked so, by anybody.
pub(crate) fn lapsed_in(mine: &[&Act]) -> Result<Option<Lapsed>, OpError> {
    for act in mine {
        if act.is("expectation-met") && act.detail_object()?.is_truthy("lapsed")? {
            let said = act.detail_object()?.get_or_null("lapsed");
            let said = Object::exactly(said.text())?;
            return Ok(Some(Lapsed {
                act: act.id.clone(),
                by: act.actor.clone(),
                at: act.at,
                because: act.because.clone(),
                reason: said.get_or_null("reason"),
                run: said.get_or_null("run"),
            }));
        }
    }
    Ok(None)
}

/// `expectation_state`'s `answer`, of the reply that answered a question.
pub(crate) fn answer_of(act: &Act) -> Result<Answer, OpError> {
    let said = act.detail_object()?;
    Ok(Answer {
        reply: said.get_or_null("reply"),
        act: act.id.clone(),
        at: act.at,
        option: said.get("option").cloned(),
        label: said.get("label").cloned(),
        words: said.get("words").cloned(),
    })
}

/// One question, from `expectation_state`'s reads.
fn question(expectation: &Act, children: &HashMap<&str, Vec<&Act>>) -> Result<Question, OpError> {
    let detail = expectation.detail_object()?;
    if detail.is_truthy("reconsideration")? || detail.says("expects", "input")? {
        return Err(python_says("a question that takes other reads"));
    }
    let direct = children
        .get(expectation.id.as_str())
        .map_or(&[][..], Vec::as_slice);
    let responder = carrier(expectation, direct)?;
    let mine = own_acts(&expectation.id, children);

    let by_responder = |act: &Act| responder.is_some() && act.actor == responder;
    let answers: Vec<&&Act> = mine
        .iter()
        .filter(|act| act.is("decision-answered") && by_responder(act))
        .collect();
    let any_met = mine.iter().any(|act| act.is("expectation-met"));

    let withdrawn = withdrawn_in(&mine, responder.as_ref())?;
    let lapsed = lapsed_in(&mine)?;
    let answer = answers.first().map(|act| answer_of(act)).transpose()?;
    let response_present = any_met || !answers.is_empty();
    let closed_at = answer
        .as_ref()
        .map(|a| a.at)
        .or(withdrawn.as_ref().map(|w| w.at))
        .or(lapsed.as_ref().map(|l| l.at));
    Ok(Question {
        expectation: expectation.id.clone(),
        index: detail.get_or_null("index"),
        question: detail.get_or_null("question"),
        options: detail.get_or_null("options"),
        because: expectation.because.clone(),
        of: responder,
        answered: answer.is_some(),
        answer,
        withdrawn,
        lapsed,
        open: !response_present,
        closed_at,
    })
}

/// `detail.get("index", 0)`, as it sorts. A list of forms with an index that isn't a whole number
/// is Python's.
fn index_of(act: &Act) -> Result<i64, OpError> {
    match act.detail_object()?.get("index") {
        None => Ok(0),
        Some(index) => index
            .text()
            .parse()
            .map_err(|_| python_says("a question's index that isn't a whole number")),
    }
}

/// `decision_form` of each id that is a form, in the order asked, with the cursor each reads on
/// from. An id that isn't one is left out, as `None` is there.
pub fn forms(scope: &mut dyn ReadScope, ids: &[String]) -> Result<Vec<Form>, OpError> {
    if ids.is_empty() {
        return Ok(Vec::new());
    }
    let asked = mentis_rules::id_list(ids.iter().map(String::as_str));
    let acts = read_acts(scope, BY_ID, &asked)?;
    let mut found: Vec<&Act> = Vec::new();
    for id in ids {
        if let Some(act) = acts.iter().find(|a| a.id == *id && a.is("decision-form")) {
            found.push(act);
        }
    }
    if found.is_empty() {
        return Ok(Vec::new());
    }
    // With no request, Python reads every act there is for this form's questions. There is no such
    // form to be had through a door, and Python can say so if there ever is.
    let mut requests = Vec::with_capacity(found.len());
    for form in &found {
        match form.caused_by.as_deref().filter(|c| !c.is_empty()) {
            Some(request) => requests.push(request),
            None => return Err(python_says("a decision form with no request")),
        }
    }

    let questions = read_acts(
        scope,
        QUESTIONS,
        &mentis_rules::id_list(requests.iter().copied()),
    )?;
    let mut mine: Vec<&Act> = Vec::new();
    let mut of_form: HashMap<&str, Vec<&Act>> = HashMap::new();
    for act in &questions {
        let named = act.detail_object()?.text("form");
        if let Ok(Some(named)) = named
            && let Some(form) = found.iter().find(|form| form.id == named)
            && form.caused_by == act.caused_by
        {
            mine.push(act);
            of_form.entry(form.id.as_str()).or_default().push(act);
        }
    }

    let under = if mine.is_empty() {
        Vec::new()
    } else {
        read_acts(
            scope,
            UNDER,
            &mentis_rules::id_list(mine.iter().map(|act| act.id.as_str())),
        )?
    };
    let mut children: HashMap<&str, Vec<&Act>> = HashMap::new();
    for act in &under {
        if let Some(cause) = act.caused_by.as_deref() {
            children.entry(cause).or_default().push(act);
        }
    }

    let mut attached: HashMap<String, String> = HashMap::new();
    let forms_asked = mentis_rules::id_list(found.iter().map(|form| form.id.as_str()));
    scope.query(ATTACHED, &[Param::Text(&forms_asked)], &mut |row| {
        if let (Some(form), Some(turn)) = (text(row, 0)?, text(row, 1)?)
            && !turn.is_empty()
        {
            attached.entry(form).or_insert(turn);
        }
        Ok(Flow::Continue)
    })?;

    let mut out = Vec::with_capacity(found.len());
    for form in found {
        let mut asked: Vec<(&Act, i64)> = Vec::new();
        for act in of_form.get(form.id.as_str()).map_or(&[][..], Vec::as_slice) {
            asked.push((act, index_of(act)?));
        }
        asked.sort_by_key(|(_, index)| *index);
        let mut questions = Vec::with_capacity(asked.len());
        for (act, _) in asked {
            questions.push(question(act, &children)?);
        }
        let open = questions.iter().filter(|q| q.open).count() as u64;
        let closed = !questions.is_empty() && open == 0;
        let closed_at = if closed {
            let times: Vec<Option<f64>> = questions.iter().map(|q| q.closed_at).collect();
            // `max` raises on a `None` beside a number, and answers it when alone.
            if times.len() > 1 && times.iter().any(Option::is_none) {
                return Err(python_says("a closed question with no time"));
            }
            times.into_iter().flatten().max_by(f64::total_cmp)
        } else {
            None
        };
        let post = form
            .turn
            .clone()
            .filter(|turn| !turn.is_empty())
            .or_else(|| attached.get(&form.id).cloned());
        let detail = form.detail_object()?;
        let operation = detail.is_truthy("operation")?;
        let mut made = Form {
            form: form.id.clone(),
            pending: post.is_none(),
            post,
            on: form.turn.clone(),
            conversation: form.conversation.clone(),
            asked_by: form.actor.clone(),
            execution: form.execution.clone(),
            request: form.caused_by.clone(),
            at: form.at,
            because: form.because.clone(),
            operation: operation.then(|| detail.get_or_null("operation")),
            run: operation.then(|| detail.get_or_null("run")),
            questions,
            open,
            closed,
            closed_at,
            cursor: form.id.clone(),
        };
        if let Some(last) = members(&made).last() {
            made.cursor = last.entry.clone();
        }
        out.push(made);
    }
    Ok(out)
}

/// `Surface._decision_forms`: the forms on this post, asked `on` it or attached to it, oldest first.
pub fn on_turn(scope: &mut dyn ReadScope, root: &str) -> Result<Vec<Form>, OpError> {
    let mut ids: Vec<String> = Vec::new();
    scope.query(ON_TURN, &[Param::Text(root)], &mut |row| {
        let found = match text(row, 1)?.as_deref() {
            Some("decision-form") => text(row, 0)?,
            Some("decision-form-attached") => text(row, 2)?.filter(|cause| !cause.is_empty()),
            _ => None,
        };
        if let Some(found) = found
            && !ids.contains(&found)
        {
            ids.push(found);
        }
        Ok(Flow::Continue)
    })?;
    forms(scope, &ids)
}
