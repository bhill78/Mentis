//! `Conversations.expectation_state`, `conversation/__init__.py:3675`, at its full width and in a
//! batch, as `_expectation_states` asks it. `forms.rs` reads the part of this a decision form needs;
//! this reads all of it, for every kind of expectation.
//!
//! **Only what the record says.** Python's `live_execution` is the union of what the record holds
//! open and what this process holds live, and only Python holds the second half. So a row carries
//! [`ExpectationState::durable_open`] and no `live_execution`, and nothing can show the durable half
//! as if it were the whole: [`crate::overlay::Overlay::live_execution`] makes the union.

use std::collections::{HashMap, HashSet};

use mentis_record::{Flow, Param, ReadScope};
use serde::Serialize;

use crate::acts::{Act, real, text};
use crate::forms::{self, Answer, Lapsed, Withdrawn};
use crate::stored::{Object, Stored, python_says};
use crate::window::reads;
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest};

/// What ends a run, `RUN_ENDS`.
const RUN_ENDS: [&str; 3] = ["result-returned", "delivery-failed", "result-recovered"];

/// `corpus.read(ids)`, as far as `_input_given` reads an entry.
const MEMBERS: &str = "SELECT id, def_name, attributed_to, recorded_at, body FROM entry \
     WHERE id IN (SELECT value FROM json_each(?1)) ORDER BY seq";

/// Expectations' states, as the record holds them.
#[derive(Clone, Copy, Debug, Default)]
pub struct ExpectationStates;

/// Which expectations, in the order to answer them.
#[derive(Clone, Debug, Default)]
pub struct ExpectationStatesArgs {
    pub ids: Vec<String>,
}

/// `assigned_carrier`.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Assigned {
    pub carrier: Option<String>,
    pub by: Option<String>,
    pub at: Option<f64>,
    pub assignment: Option<String>,
    pub history: Vec<String>,
}

/// A `delivery-failed` under this expectation.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Failure {
    pub act: String,
    pub because: Option<String>,
    pub at: f64,
}

/// A `work-delegated` under this expectation.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Delegation {
    pub act: String,
    pub expectation: Stored,
    pub by: Option<String>,
    pub at: f64,
}

/// `_act_of`, as `latest_activity` gives it.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ActRow {
    pub id: String,
    pub at: f64,
    pub actor: Option<String>,
    pub act: Option<String>,
    pub conversation: Option<String>,
    pub turn: Option<String>,
    pub execution: Option<String>,
    pub runtime: Option<String>,
    pub because: Option<String>,
    pub caused_by: Option<String>,
    pub about: Stored,
    pub detail: Stored,
}

/// A marked-ready that answers an input, with what it covered.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct MarkedReady {
    pub marked_ready: String,
    pub answers: Vec<Stored>,
    pub at: f64,
}

/// `_input_given`.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct InputGiven {
    pub set: Stored,
    pub ready: Vec<MarkedReady>,
}

/// One row: `expectation_state`'s members, with `live_execution` replaced by
/// [`ExpectationState::durable_open`]. `input` and the form's members are absent where Python's are.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ExpectationState {
    pub expectation: String,
    pub turn: Option<String>,
    pub conversation: Option<String>,
    pub expects: Stored,
    pub requires: Vec<Stored>,
    pub options: Stored,
    pub material: Vec<Stored>,
    pub because: Option<String>,
    pub recorded_by: Option<String>,
    pub requested_by: Option<String>,
    pub expected_of: Option<String>,
    pub assigned: Assigned,
    pub unassigned: bool,
    pub response_present: bool,
    pub satisfied_by: Vec<String>,
    pub withdrawn: Option<Withdrawn>,
    pub lapsed: Option<Lapsed>,
    pub replies_from_expected: Vec<Stored>,
    /// The executions this expectation's own start acts name and no end has closed, sorted. A part
    /// of Python's `live_execution`, never all of it.
    pub durable_open: Vec<String>,
    pub failures: Vec<Failure>,
    pub delegations: Vec<Delegation>,
    pub latest_activity: Option<ActRow>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub input: Option<InputGiven>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub form: Option<Stored>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub index: Option<Stored>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub question: Option<Stored>,
    /// Present, and `None`, on a question nobody answered.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub answer: Option<Option<Answer>>,
}

impl ReadOp for ExpectationStates {
    type Args = ExpectationStatesArgs;
    type Row = ExpectationState;

    const NAME: &'static str = "expectation_states";
    /// The position, the expectations, what is under them, the replies, the forms and their
    /// attachments, an input's members and their entries.
    const BUDGET: Budget = Budget { statements: 8 };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<ExpectationStatesArgs>,
    ) -> Result<ReadAnswer<ExpectationState>, OpError> {
        Ok(ReadAnswer {
            rows: states(scope, &request.args.ids)?,
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

/// `_act_of` raises at the first act it can't decode, whichever act that is.
fn row_of(act: &Act) -> Result<ActRow, OpError> {
    Ok(ActRow {
        id: act.id.clone(),
        at: act.at,
        actor: act.actor.clone(),
        act: act.act.clone(),
        conversation: act.conversation.clone(),
        turn: act.turn.clone(),
        execution: act.execution.clone(),
        runtime: act.runtime.clone(),
        because: act.because.clone(),
        caused_by: act.caused_by.clone(),
        about: act.about()?.clone(),
        detail: act.detail()?.clone(),
    })
}

/// `assigned_carrier`, from the acts this expectation directly caused.
fn assigned(expectation: &Act, direct: &[&Act]) -> Result<Assigned, OpError> {
    let mut acts = Vec::new();
    for act in direct {
        if act.is("expectation-assigned") && !act.about_items()?.is_empty() {
            acts.push(*act);
        }
    }
    acts.sort_by(|a, b| a.at.total_cmp(&b.at));
    if let Some(latest) = acts.last() {
        return Ok(Assigned {
            carrier: forms::first_about(latest)?,
            by: latest.actor.clone(),
            at: Some(latest.at),
            assignment: Some(latest.id.clone()),
            history: acts.iter().map(|act| act.id.clone()).collect(),
        });
    }
    if !expectation.about_items()?.is_empty() {
        return Ok(Assigned {
            carrier: forms::first_about(expectation)?,
            by: expectation.actor.clone(),
            at: Some(expectation.at),
            assignment: None,
            history: Vec::new(),
        });
    }
    Ok(Assigned {
        carrier: None,
        by: None,
        at: None,
        assignment: None,
        history: Vec::new(),
    })
}

fn execution_of(act: &Act) -> Option<&str> {
    act.execution.as_deref().filter(|id| !id.is_empty())
}

/// `closed_starts`, then the `live` it leaves. `order` is write order.
fn durable_open(mine: &[&Act], order: &HashMap<&str, usize>) -> Vec<String> {
    let key = |act: &Act| order.get(act.id.as_str()).copied();
    let is_end = |act: &Act| {
        act.act
            .as_deref()
            .is_some_and(|name| RUN_ENDS.contains(&name))
    };
    let starts: HashMap<&str, &Act> = mine
        .iter()
        .filter(|act| act.is("execution-started") && execution_of(act).is_some())
        .map(|act| (act.id.as_str(), *act))
        .collect();
    let mut latest: HashMap<&str, Option<usize>> = HashMap::new();
    let mut named: HashSet<&str> = HashSet::new();
    for end in mine.iter().filter(|act| is_end(act)) {
        let Some(execution) = execution_of(end) else {
            continue;
        };
        let own = end
            .caused_by
            .as_deref()
            .and_then(|cause| starts.get(cause).copied());
        let mark = key(own.unwrap_or(end));
        let held = latest.entry(execution).or_insert(mark);
        if *held < mark {
            *held = mark;
        }
        if let Some(own) = own
            && execution_of(own) == Some(execution)
        {
            named.insert(own.id.as_str());
        }
    }
    let mut open: Vec<String> = starts
        .values()
        .filter_map(|start| {
            let execution = execution_of(start)?;
            let closed = latest
                .get(execution)
                .is_some_and(|mark| named.contains(start.id.as_str()) || key(start) < *mark);
            (!closed).then(|| execution.to_owned())
        })
        .collect();
    open.sort();
    open.dedup();
    open
}

/// An entry linked into a response set, as far as `_input_given` reads it.
#[derive(Clone)]
struct Member {
    id: String,
    kind: Option<String>,
    by: Option<String>,
    at: f64,
    body: Option<String>,
}

/// `responses._members` of each set, in link order, before `_input_given` sorts them.
fn members(
    scope: &mut dyn ReadScope,
    sets: &[&str],
) -> Result<HashMap<String, Vec<Member>>, OpError> {
    let links = reads::links_to(scope, "in-response-set", sets)?;
    let mut read: HashMap<String, Member> = HashMap::new();
    if !links.is_empty() {
        let list = mentis_rules::id_list(links.iter().map(|link| link.from.as_str()));
        scope.query(MEMBERS, &[Param::Text(&list)], &mut |row| {
            let member = Member {
                id: text(row, 0)?.unwrap_or_default(),
                kind: text(row, 1)?,
                by: text(row, 2)?,
                at: real(row, 3)?,
                body: text(row, 4)?,
            };
            read.insert(member.id.clone(), member);
            Ok(Flow::Continue)
        })?;
    }
    let mut out: HashMap<String, Vec<Member>> = HashMap::new();
    for link in &links {
        if let Some(member) = read.get(&link.from) {
            out.entry(link.to.clone()).or_default().push(member.clone());
        }
    }
    Ok(out)
}

/// `_input_given`.
fn input_given(
    detail: &Object,
    responder: Option<&String>,
    sets: &HashMap<String, Vec<Member>>,
) -> Result<InputGiven, OpError> {
    let set = detail.get_or_null("response_set");
    let mut ready = Vec::new();
    if let (Some(sid), Some(responder)) = (detail.text("response_set")?, responder)
        && !sid.is_empty()
    {
        let mut before = HashSet::new();
        for id in detail.get_or_null("ready_before").items_or_none()? {
            before.insert(id.string()?);
        }
        let mut rows: Vec<(usize, &Member)> = sets
            .get(&sid)
            .map_or(&[][..], Vec::as_slice)
            .iter()
            .enumerate()
            .filter(|(_, member)| member.kind.as_deref() == Some("marked-ready"))
            .collect();
        rows.sort_by(|a, b| a.1.at.total_cmp(&b.1.at).then(a.0.cmp(&b.0)));
        for (_, member) in rows {
            if before.contains(&Some(member.id.clone())) || member.by.as_ref() != Some(responder) {
                continue;
            }
            let body = member
                .body
                .as_deref()
                .ok_or_else(|| python_says("a marked-ready with no body"))?;
            ready.push(MarkedReady {
                marked_ready: member.id.clone(),
                answers: Object::exactly(body)?
                    .get_or_null("answers")
                    .items_or_none()?,
                at: member.at,
            });
        }
    }
    Ok(InputGiven { set, ready })
}

/// `_form_post` of each form named. A form the record doesn't hold has none.
fn form_posts(
    scope: &mut dyn ReadScope,
    named: &[&str],
) -> Result<HashMap<String, Option<String>>, OpError> {
    let mut out = HashMap::new();
    if named.is_empty() {
        return Ok(out);
    }
    let list = mentis_rules::id_list(named.iter().copied());
    for act in forms::read_acts(scope, forms::BY_ID, &list)? {
        out.insert(act.id.clone(), act.turn.filter(|turn| !turn.is_empty()));
    }
    let mut attached: Vec<(String, String)> = Vec::new();
    scope.query(forms::ATTACHED, &[Param::Text(&list)], &mut |row| {
        if let (Some(form), Some(turn)) = (text(row, 0)?, text(row, 1)?)
            && !turn.is_empty()
        {
            attached.push((form, turn));
        }
        Ok(Flow::Continue)
    })?;
    for (form, turn) in attached {
        if let Some(held) = out.get_mut(&form) {
            held.get_or_insert(turn);
        }
    }
    Ok(out)
}

/// What one batch read, for [`state`] to assemble each row from.
struct Batch<'a> {
    children: HashMap<&'a str, Vec<&'a Act>>,
    order: HashMap<&'a str, usize>,
    replies: HashMap<&'a str, Vec<&'a reads::Link>>,
    posts: HashMap<String, Option<String>>,
    sets: HashMap<String, Vec<Member>>,
}

fn state(expectation: &Act, batch: &Batch<'_>) -> Result<ExpectationState, OpError> {
    let detail = Object::exactly(expectation.detail()?.text())?;
    let direct = batch
        .children
        .get(expectation.id.as_str())
        .map_or(&[][..], Vec::as_slice);
    let assigned = assigned(expectation, direct)?;
    let responder = assigned.carrier.clone();
    let mine = forms::own_acts(&expectation.id, &batch.children);
    for act in &mine {
        act.about()?;
        act.detail()?;
    }

    let by_responder = |act: &Act| responder.is_some() && act.actor == responder;
    let satisfied_by: Vec<String> = mine
        .iter()
        .filter(|act| act.is("expectation-met"))
        .map(|act| act.id.clone())
        .collect();
    let is_form = detail.is_truthy("form")?;
    let answers: Vec<&&Act> = mine
        .iter()
        .filter(|act| is_form && act.is("decision-answered") && by_responder(act))
        .collect();
    let replies_from_expected: Vec<Stored> = if is_form {
        let mut said = Vec::with_capacity(answers.len());
        for act in &answers {
            said.push(act.detail_object()?.get_or_null("reply"));
        }
        said
    } else {
        // `turn=None` asks for every reply link in the record, which is what an expectation with
        // no Turn has always been compared with. That read is Python's.
        let turn = expectation
            .turn
            .as_deref()
            .ok_or_else(|| python_says("an expectation with no Turn"))?;
        batch
            .replies
            .get(turn)
            .map_or(&[][..], Vec::as_slice)
            .iter()
            .filter(|link| responder.is_some() && link.attributed_to == responder)
            .map(|link| Stored::of(&link.from))
            .collect()
    };
    let withdrawn = forms::withdrawn_in(&mine, responder.as_ref())?;
    let lapsed = forms::lapsed_in(&mine)?;

    let mut present = !satisfied_by.is_empty() || !replies_from_expected.is_empty();
    if detail.is_truthy("reconsideration")? {
        present = withdrawn.is_some();
        for act in &mine {
            present = present
                || (act.is("expectation-met")
                    && act.actor == responder
                    && act.detail_object()?.get("selections").is_some());
        }
    }
    let input = if detail.says("expects", "input")? {
        let given = input_given(&detail, responder.as_ref(), &batch.sets)?;
        present = withdrawn.is_some() || !given.ready.is_empty();
        Some(given)
    } else {
        None
    };

    let form = if is_form {
        Some(
            detail
                .text("form")?
                .ok_or_else(|| python_says("a form that isn't a reference"))?,
        )
    } else {
        None
    };
    let turn = match &form {
        Some(form) => batch.posts.get(form).cloned().flatten(),
        None => expectation.turn.clone(),
    };
    let mut failures = Vec::new();
    let mut delegations = Vec::new();
    for act in &mine {
        if act.is("delivery-failed") {
            failures.push(Failure {
                act: act.id.clone(),
                because: act.because.clone(),
                at: act.at,
            });
        } else if act.is("work-delegated") {
            delegations.push(Delegation {
                act: act.id.clone(),
                expectation: act
                    .about_items()?
                    .into_iter()
                    .next()
                    .unwrap_or_else(Stored::null),
                by: act.actor.clone(),
                at: act.at,
            });
        }
    }
    // `max` keeps the first of equal times, and `mine` is already in time order.
    let mut latest: Option<&Act> = None;
    for act in &mine {
        if latest.is_none_or(|held| act.at > held.at) {
            latest = Some(act);
        }
    }
    Ok(ExpectationState {
        expectation: expectation.id.clone(),
        turn,
        conversation: expectation.conversation.clone(),
        expects: detail.get_or_null("expects"),
        requires: detail.get_or_null("requires").items_or_none()?,
        options: detail.get_or_null("options"),
        material: detail.get_or_null("material").items_or_none()?,
        because: expectation.because.clone(),
        recorded_by: expectation.actor.clone(),
        requested_by: expectation.actor.clone(),
        unassigned: responder.is_none(),
        expected_of: responder,
        assigned,
        response_present: present,
        satisfied_by,
        withdrawn,
        lapsed,
        replies_from_expected,
        durable_open: durable_open(&mine, &batch.order),
        failures,
        delegations,
        latest_activity: latest.map(row_of).transpose()?,
        input,
        index: is_form.then(|| detail.get_or_null("index")),
        question: is_form.then(|| detail.get_or_null("question")),
        answer: if is_form {
            Some(
                answers
                    .first()
                    .map(|act| forms::answer_of(act))
                    .transpose()?,
            )
        } else {
            None
        },
        form: form.as_ref().map(Stored::of),
    })
}

/// `_expectation_states(rows, open_only=False)` of these ids, in the order asked. An id that isn't
/// an expectation is left out, where Python raises at it: what that means is the route's to say.
fn states(scope: &mut dyn ReadScope, ids: &[String]) -> Result<Vec<ExpectationState>, OpError> {
    if ids.is_empty() {
        return Ok(Vec::new());
    }
    let asked = mentis_rules::id_list(ids.iter().map(String::as_str));
    let acts = forms::read_acts(scope, forms::BY_ID, &asked)?;
    let found: HashMap<&str, &Act> = acts
        .iter()
        .filter(|act| act.is("expectation-recorded"))
        .map(|act| (act.id.as_str(), act))
        .collect();
    if found.is_empty() {
        return Ok(Vec::new());
    }

    let roots = mentis_rules::id_list(found.keys().copied());
    let under = forms::read_acts(scope, forms::UNDER, &roots)?;
    let mut order = HashMap::with_capacity(under.len());
    let mut children: HashMap<&str, Vec<&Act>> = HashMap::new();
    for (seq, act) in under.iter().enumerate() {
        order.insert(act.id.as_str(), seq);
        if let Some(cause) = act.caused_by.as_deref() {
            children.entry(cause).or_default().push(act);
        }
    }

    let mut turns: Vec<&str> = Vec::new();
    let mut named: Vec<String> = Vec::new();
    let mut wanted: Vec<String> = Vec::new();
    for act in found.values() {
        let detail = Object::exactly(act.detail()?.text())?;
        if detail.is_truthy("form")? {
            named.extend(detail.text("form")?);
        } else if let Some(turn) = act.turn.as_deref() {
            turns.push(turn);
        }
        if detail.says("expects", "input")? {
            wanted.extend(detail.text("response_set")?.filter(|set| !set.is_empty()));
        }
    }
    let links = reads::links_to(scope, reads::REPLIES_TO, &turns)?;
    let mut replies: HashMap<&str, Vec<&reads::Link>> = HashMap::new();
    for link in &links {
        replies.entry(link.to.as_str()).or_default().push(link);
    }
    let named: Vec<&str> = named.iter().map(String::as_str).collect();
    let posts = form_posts(scope, &named)?;
    let wanted: Vec<&str> = wanted.iter().map(String::as_str).collect();
    let sets = members(scope, &wanted)?;

    let batch = Batch {
        children,
        order,
        replies,
        posts,
        sets,
    };
    let mut out = Vec::with_capacity(ids.len());
    for id in ids {
        if let Some(act) = found.get(id.as_str()) {
            out.push(state(act, &batch)?);
        }
    }
    Ok(out)
}
