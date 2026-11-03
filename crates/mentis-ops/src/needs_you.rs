//! Home's one "needs you" rule, shared by its page, badge rows, and request detail reads.
//!
//! An expectation asks the owner exactly while its current carrier is the owner and no response is
//! present (`home.asking_owner`). As in `Conversations.expectations`, the carriers are read first,
//! all at once, and only what the owner carries is read in full. With no owner named Python says
//! "unknown", and that wording is left to it: a Brain with no owner forwards.

use std::collections::{HashMap, HashSet};

use mentis_record::{Flow, Id, Param, ReadScope};

use crate::acts::{Act, text};
use crate::expectation_states::{ExpectationState, ExpectationStates, ExpectationStatesArgs};
use crate::lists::{flow_text, loaded, not_owned, refused};
use crate::pyjson::{Py, dict};
use crate::window::collections::PyRow;
use crate::window::reads::{self, ABOUT_TOPIC};
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest, python};

const EXPECTATIONS: &str = concat!(
    "SELECT seq, ",
    crate::act_columns!(),
    " FROM operational WHERE act='expectation-recorded' ORDER BY seq"
);
/// These asks' assignments, in write order, through the cause's index: `_read_carriers`.
const ASSIGNED: &str = concat!(
    "SELECT ",
    crate::act_columns!(),
    " FROM operational WHERE caused_by IN (SELECT value FROM json_each(?1)) \
     AND act='expectation-assigned' ORDER BY seq"
);
const FORM_POSTS: &str = "SELECT f.id,f.turn,(SELECT a.turn FROM operational a WHERE \
 a.caused_by=f.id AND a.act='decision-form-attached' AND a.turn IS NOT NULL AND a.turn<>'' ORDER BY a.seq LIMIT 1) \
 FROM operational f WHERE f.id IN (SELECT value FROM json_each(?1))";
const RAW_BODIES: &str = "SELECT id,body FROM entry WHERE id IN (SELECT value FROM json_each(?1))";

#[derive(Clone, Debug)]
pub enum NeedsYouMode {
    Page { before: Option<String> },
    Items,
    On { post: String },
    Asks { ids: Vec<String> },
}

#[derive(Clone, Debug)]
pub struct NeedsYouArgs {
    pub mode: NeedsYouMode,
}

pub struct NeedsYou;

#[derive(Clone)]
pub(crate) struct Asked {
    pub seq: i64,
    pub act: Act,
}

fn owner_or_python(scope: &mut dyn ReadScope) -> Result<String, OpError> {
    crate::window::classify::owner_of(scope)?
        .ok_or_else(|| not_owned("a record that names no owner"))
}

fn py_stored(value: &crate::stored::Stored) -> Result<Py, OpError> {
    crate::pyjson::loads(value.text())
        .ok_or_else(|| not_owned("a needs-you value Python has to present"))
}

fn detail(act: &Act, name: &str) -> Result<Py, OpError> {
    act.detail_object()?
        .get(name)
        .map(py_stored)
        .transpose()
        .map(|v| v.unwrap_or(Py::None))
}

fn read_expectations(scope: &mut dyn ReadScope) -> Result<Vec<Asked>, OpError> {
    let mut out = Vec::new();
    scope.query(EXPECTATIONS, &[], &mut |row| {
        out.push(Asked {
            seq: row.value(0)?.integer().unwrap_or_default(),
            act: Act::read(row, 1)?,
        });
        Ok(Flow::Continue)
    })?;
    Ok(out)
}

/// `_carriers`: of the assignments an expectation caused that name somebody, in write order, the
/// latest by `at` under a stable sort; else its own `about[0]`; else nobody.
pub(crate) fn carriers(
    scope: &mut dyn ReadScope,
    asks: &[&Act],
) -> Result<HashMap<String, Option<String>>, OpError> {
    let mut assigned: HashMap<String, (f64, Option<String>)> = HashMap::new();
    let wanted = mentis_rules::id_list(asks.iter().map(|act| act.id.as_str()));
    let mut acts = Vec::new();
    scope.query(ASSIGNED, &[Param::Text(&wanted)], &mut |row| {
        acts.push(Act::read(row, 0)?);
        Ok(Flow::Continue)
    })?;
    for act in &acts {
        if act.about_items()?.is_empty() {
            continue;
        }
        let cause = act.caused_by.clone().unwrap_or_default();
        let newer = assigned.get(&cause).is_none_or(|held| act.at >= held.0);
        if newer {
            assigned.insert(cause, (act.at, crate::forms::first_about(act)?));
        }
    }
    let mut out = HashMap::with_capacity(asks.len());
    for act in asks {
        let carrier = match assigned.remove(&act.id) {
            Some((_, carrier)) => carrier,
            None if act.about_items()?.is_empty() => None,
            None => crate::forms::first_about(act)?,
        };
        out.insert(act.id.clone(), carrier);
    }
    Ok(out)
}

fn states(
    scope: &mut dyn ReadScope,
    asks: &[&Asked],
) -> Result<HashMap<String, ExpectationState>, OpError> {
    let request = ReadRequest {
        args: ExpectationStatesArgs {
            ids: asks.iter().map(|a| a.act.id.clone()).collect(),
        },
        cursor: None,
        limit: None,
        deadline: std::time::Instant::now() + mentis_record::READ_SCOPE_LIMIT,
    };
    Ok(ExpectationStates
        .read(scope, &request)?
        .rows
        .into_iter()
        .map(|state| (state.expectation.clone(), state))
        .collect())
}

/// `asking_owner`: what asks the owner now, with its state, newest first.
fn asking<'a>(
    scope: &mut dyn ReadScope,
    owner: &str,
    asks: &'a [Asked],
) -> Result<(Vec<&'a Asked>, HashMap<String, ExpectationState>), OpError> {
    let acts: Vec<&Act> = asks.iter().map(|a| &a.act).collect();
    let carried = carriers(scope, &acts)?;
    let mine: Vec<&Asked> = asks
        .iter()
        .filter(|a| {
            carried
                .get(&a.act.id)
                .is_some_and(|carrier| carrier.as_deref() == Some(owner))
        })
        .collect();
    let state = states(scope, &mine)?;
    let mut out: Vec<&Asked> = mine
        .into_iter()
        .filter(|ask| {
            state.get(&ask.act.id).is_some_and(|state| {
                state.expected_of.as_deref() == Some(owner) && !state.response_present
            })
        })
        .collect();
    out.sort_by(|a, b| {
        b.act
            .at
            .total_cmp(&a.act.at)
            .then_with(|| a.seq.cmp(&b.seq))
            .then_with(|| a.act.id.cmp(&b.act.id))
    });
    Ok((out, state))
}

/// `read.needs_you_in`: of these Conversations' expectations, how many ask the owner. The owner's
/// count, by the same rule. Only what they carry is read in full.
pub(crate) fn counts_by_conversation(
    scope: &mut dyn ReadScope,
    conversations: &[String],
) -> Result<HashMap<String, usize>, OpError> {
    if conversations.is_empty() {
        return Ok(HashMap::new());
    }
    let owner = owner_or_python(scope)?;
    let wanted: HashSet<&str> = conversations.iter().map(String::as_str).collect();
    let mut asks = read_expectations(scope)?;
    asks.retain(|ask| {
        ask.act
            .conversation
            .as_deref()
            .is_some_and(|c| wanted.contains(c))
    });
    let (open, _) = asking(scope, &owner, &asks)?;
    let mut out: HashMap<String, usize> = HashMap::new();
    for ask in open {
        if let Some(conversation) = &ask.act.conversation {
            *out.entry(conversation.clone()).or_default() += 1;
        }
    }
    Ok(out)
}

/// `cv.asked_on`'s `_form_post` of every form these asks name.
fn form_posts(
    scope: &mut dyn ReadScope,
    asks: &[&Asked],
) -> Result<HashMap<String, Option<String>>, OpError> {
    let mut forms: Vec<String> = Vec::new();
    for ask in asks {
        let form = detail(&ask.act, "form")?;
        if form.truthy() {
            forms.push(
                form.as_str()
                    .ok_or_else(|| not_owned("a form that isn't a reference"))?
                    .to_owned(),
            );
        }
    }
    let mut out = HashMap::new();
    if forms.is_empty() {
        return Ok(out);
    }
    let list = mentis_rules::id_list(forms.iter().map(String::as_str));
    scope.query(FORM_POSTS, &[Param::Text(&list)], &mut |row| {
        let form = text(row, 0)?.unwrap_or_default();
        let own = text(row, 1)?.filter(|turn| !turn.is_empty());
        out.insert(form, own.or(text(row, 2)?));
        Ok(Flow::Continue)
    })?;
    Ok(out)
}

fn asked_on(
    ask: &Asked,
    forms: &HashMap<String, Option<String>>,
) -> Result<Option<String>, OpError> {
    let form = detail(&ask.act, "form")?;
    Ok(if form.truthy() {
        form.as_str()
            .and_then(|form| forms.get(form).cloned())
            .flatten()
    } else {
        ask.act.turn.clone()
    })
}

/// `corpus.read(ids)`'s bodies, unread by any version.
fn raw_bodies(scope: &mut dyn ReadScope, ids: &[Id]) -> Result<HashMap<String, Py>, OpError> {
    let mut out = HashMap::with_capacity(ids.len());
    if ids.is_empty() {
        return Ok(out);
    }
    let list = mentis_rules::id_list(ids.iter().map(|id| id.0.as_str()));
    let mut unreadable = false;
    scope.query(RAW_BODIES, &[Param::Text(&list)], &mut |row| {
        let id = text(row, 0)?.unwrap_or_default();
        let Some(body) = text(row, 1)?.and_then(|b| crate::pyjson::loads(&b)) else {
            unreadable = true;
            return Ok(Flow::Stop);
        };
        out.insert(id, body);
        Ok(Flow::Continue)
    })?;
    if unreadable {
        return Err(not_owned("a body Python has to read"));
    }
    Ok(out)
}

/// `_input_block`.
fn input_block(bodies: &HashMap<String, Py>, ask: &Asked) -> Result<Py, OpError> {
    let set = detail(&ask.act, "response_set")?;
    if !set.truthy() {
        return Ok(Py::None);
    }
    let set = set
        .as_str()
        .ok_or_else(|| not_owned("a response set that isn't a reference"))?;
    let Some(body) = bodies.get(set) else {
        return Ok(Py::None);
    };
    if !body.is_dict() {
        return Err(not_owned("a response set body Python has to present"));
    }
    Ok(dict([
        ("set", Py::str(set)),
        ("block", body.get("block").cloned().unwrap_or(Py::None)),
        (
            "part",
            body.get("part")
                .filter(|v| v.truthy())
                .cloned()
                .unwrap_or_else(|| Py::int(0)),
        ),
        ("type", body.get("type").cloned().unwrap_or(Py::None)),
    ]))
}

/// `_lead`: a post's first line of words, as a list row heads it.
fn lead(reads: &HashMap<Id, mentis_rules::Reading>, post: Option<&str>) -> Result<Py, OpError> {
    let Some(post) = post else {
        return Ok(Py::None);
    };
    let Some(read) = reads.get(&Id(post.to_owned())) else {
        return Ok(Py::None);
    };
    if read.python_says {
        return Err(not_owned("a post Python has to present"));
    }
    let words = flow_text(&loaded(&read.body_json)?)?;
    let line = python::lines(&words).find_map(|line| {
        let line = line
            .trim_start_matches(|c: char| matches!(c, '#' | '>' | '*' | '-') || python::is_space(c))
            .replace("**", "");
        let line = python::strip(&line).to_owned();
        (!line.is_empty()).then_some(line)
    });
    Ok(line.map_or(Py::None, |line| Py::Str(crate::lists::cut_160(line))))
}

/// `_parse_key(before, 2)`, as far as a cursor this route gave out reads.
fn page_mark(raw: &str) -> Result<(f64, i64), OpError> {
    let python_reads = || not_owned("a cursor Python has to read");
    let bits: Vec<&str> = raw.split('_').collect();
    if bits.len() != 2 {
        return Err(refused("not a paging cursor: ", raw));
    }
    let plain = |digits: &str| !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit());
    let time = bits[0]
        .split_once('.')
        .map_or(plain(bits[0]), |(whole, part)| plain(whole) && plain(part));
    if !time || !plain(bits[1]) {
        return Err(python_reads());
    }
    Ok((
        bits[0].parse().map_err(|_| python_reads())?,
        bits[1].parse().map_err(|_| python_reads())?,
    ))
}

fn page(limit: usize, owner: &str, all: Vec<&Asked>, before: Option<&str>) -> Result<Py, OpError> {
    let total = all.len();
    let mark = match before {
        None => None,
        Some(id) if id.starts_with("opr-") => Some(
            all.iter()
                .find(|a| a.act.id == id)
                .map(|a| (a.act.at, a.seq))
                .ok_or_else(|| refused("not asking the owner now: ", id))?,
        ),
        Some(raw) => Some(page_mark(raw)?),
    };
    let left: Vec<&Asked> = all
        .into_iter()
        .filter(|a| mark.is_none_or(|(at, seq)| b_after(a.act.at, a.seq, at, seq)))
        .collect();
    let shown: Vec<&Asked> = left.iter().take(limit).copied().collect();
    let cursor = match shown.last() {
        Some(last) if left.len() > shown.len() => Py::str(format!(
            "{}_{}",
            crate::pyjson::float_repr(last.act.at),
            last.seq
        )),
        _ => Py::None,
    };
    Ok(dict([
        ("key", Py::str("home:needs-you")),
        (
            "items",
            Py::List(shown.iter().map(|a| Py::str(&a.act.id)).collect()),
        ),
        ("before", cursor),
        ("total", Py::int(total)),
        ("owner", Py::str(owner)),
        ("limit", Py::int(limit)),
    ]))
}

/// `(-at, seq) > (-mark_at, mark_seq)`.
fn b_after(at: f64, seq: i64, mark_at: f64, mark_seq: i64) -> bool {
    at < mark_at || (at == mark_at && seq > mark_seq)
}

fn names_or_id(names: &HashMap<String, String>, id: Option<&str>) -> Py {
    id.map_or(Py::None, |id| {
        Py::str(names.get(id).map_or(id, String::as_str))
    })
}

fn items(scope: &mut dyn ReadScope, owner: &str, asking: Vec<&Asked>) -> Result<Py, OpError> {
    let forms = form_posts(scope, &asking)?;
    let mut on = HashMap::new();
    for ask in &asking {
        on.insert(ask.act.id.clone(), asked_on(ask, &forms)?);
    }
    let turns: Vec<&str> = on.values().filter_map(|v| v.as_deref()).collect();
    let homes = reads::homes_of(scope, &turns)?;
    let numbers = reads::numbers_of(scope, &homes)?;
    let people: Vec<&str> = asking
        .iter()
        .filter_map(|a| a.act.actor.as_deref())
        .chain(homes.values().map(String::as_str))
        .collect();
    let names = reads::names_of(scope, &people)?;
    let mut sets = Vec::new();
    for ask in &asking {
        let set = detail(&ask.act, "response_set")?;
        if let Some(set) = set.as_str() {
            sets.push(Id(set.to_owned()));
        }
    }
    let bodies = raw_bodies(scope, &sets)?;
    let posts: Vec<Id> = turns.iter().map(|post| Id((*post).to_owned())).collect();
    let post_reads = mentis_rules::now_reads(scope, &posts)?;
    let mut rows: Vec<Py> = Vec::new();
    let mut keys = HashSet::new();
    let mut counts = [0usize; 3];
    for ask in asking {
        let form = detail(&ask.act, "form")?;
        let key = form
            .as_str()
            .filter(|_| form.truthy())
            .unwrap_or(&ask.act.id)
            .to_owned();
        if !keys.insert(key.clone()) {
            if let Some(Py::Dict(fields)) = rows
                .iter_mut()
                .find(|r| r.get("key").and_then(Py::as_str) == Some(key.as_str()))
                && let Some((_, Py::List(ids))) = fields.iter_mut().find(|(k, _)| k == "asks")
            {
                ids.push(Py::str(&ask.act.id));
            }
            continue;
        }
        let expects = detail(&ask.act, "expects")?;
        let kind = if form.truthy() || expects.as_str() == Some("decision") {
            counts[0] += 1;
            "decision"
        } else if expects.as_str() == Some("input") {
            counts[1] += 1;
            "input"
        } else {
            counts[2] += 1;
            "request"
        };
        let post = on.get(&ask.act.id).cloned().flatten();
        let conversation = post
            .as_ref()
            .and_then(|p| homes.get(p))
            .cloned()
            .or_else(|| ask.act.conversation.clone());
        let block = if kind == "input" {
            input_block(&bodies, ask)?
        } else {
            Py::None
        };
        let anchor = if kind == "input" {
            match block.get("block") {
                None => Py::None,
                Some(Py::None) => Py::str("block:None"),
                Some(named) => Py::str(format!(
                    "block:{}",
                    named
                        .as_str()
                        .ok_or_else(|| not_owned("a block name that isn't text"))?
                )),
            }
        } else if kind == "decision" {
            Py::str(format!("decision-form:{key}"))
        } else {
            Py::None
        };
        rows.push(dict([
            ("key", Py::str(key)),
            ("kind", Py::str(kind)),
            ("expects", expects),
            ("form", form),
            ("asks", Py::List(vec![Py::str(&ask.act.id)])),
            ("question", detail(&ask.act, "question")?),
            ("block", block),
            ("anchor", anchor),
            ("post", post.as_deref().map_or(Py::None, Py::str)),
            (
                "post_number",
                post.as_ref()
                    .and_then(|p| numbers.get(p))
                    .map_or(Py::None, Py::int),
            ),
            ("lead", lead(&post_reads, post.as_deref())?),
            (
                "conversation",
                conversation.as_deref().map_or(Py::None, Py::str),
            ),
            (
                "conversation_name",
                conversation
                    .as_ref()
                    .and_then(|c| names.get(c))
                    .map_or(Py::None, Py::str),
            ),
            (
                "asked_by",
                ask.act.actor.as_deref().map_or(Py::None, Py::str),
            ),
            (
                "asked_by_name",
                names_or_id(&names, ask.act.actor.as_deref()),
            ),
            (
                "because",
                ask.act.because.as_deref().map_or(Py::None, Py::str),
            ),
            ("at", Py::Float(ask.act.at)),
        ]));
    }
    let words = [
        ("decision", "decisions", counts[0]),
        ("input", "inputs", counts[1]),
        ("request", "requests", counts[2]),
    ]
    .into_iter()
    .filter(|x| x.2 > 0)
    .map(|(one, many, n)| format!("{n} {}", if n == 1 { one } else { many }))
    .collect::<Vec<_>>()
    .join(", ");
    Ok(dict([
        ("key", Py::str("needs-you:items")),
        ("items", Py::List(rows)),
        (
            "counts",
            dict([
                ("decision", Py::int(counts[0])),
                ("input", Py::int(counts[1])),
                ("request", Py::int(counts[2])),
                ("total", Py::int(counts.iter().sum::<usize>())),
            ]),
        ),
        ("words", Py::str(words)),
        ("owner", Py::str(owner)),
    ]))
}

/// `_ask_rows`, one row per ask, in the order given.
fn ask_rows(
    scope: &mut dyn ReadScope,
    owner: &str,
    asks: &[&Asked],
    states: &HashMap<String, ExpectationState>,
    asking: &HashSet<String>,
) -> Result<Vec<Py>, OpError> {
    let forms = form_posts(scope, asks)?;
    let mut on = HashMap::new();
    for a in asks {
        on.insert(a.act.id.clone(), asked_on(a, &forms)?);
    }
    let turns: Vec<&str> = on.values().filter_map(|x| x.as_deref()).collect();
    let homes = reads::homes_of(scope, &turns)?;
    let numbers = reads::numbers_of(scope, &homes)?;
    let heads = reads::heads(scope, &turns)?;
    let raw_filings = reads::links_from(scope, ABOUT_TOPIC, &turns)?;
    let filings = reads::in_force(scope, raw_filings)?;
    let topic_ids: Vec<&str> = filings.iter().map(|link| link.to.as_str()).collect();
    let topic_homes = reads::first_to(&reads::links_from(scope, reads::TOPIC_OF, &topic_ids)?);
    let satisfied: Vec<&str> = asks
        .iter()
        .filter_map(|ask| states.get(&ask.act.id))
        .flat_map(|state| state.satisfied_by.iter().map(String::as_str))
        .collect();
    let met_list = mentis_rules::id_list(satisfied.iter().copied());
    let met: HashMap<String, Act> = crate::forms::read_acts(scope, crate::forms::BY_ID, &met_list)?
        .into_iter()
        .map(|act| (act.id.clone(), act))
        .collect();
    let carriers: Vec<&str> = asks
        .iter()
        .filter_map(|ask| states.get(&ask.act.id))
        .filter_map(|state| state.expected_of.as_deref())
        .collect();
    let people: Vec<&str> = asks
        .iter()
        .filter_map(|a| a.act.actor.as_deref())
        .chain(carriers.iter().copied())
        .chain(homes.values().map(String::as_str))
        .collect();
    let names = reads::names_of(scope, &people)?;
    let mut sets = Vec::new();
    for ask in asks {
        if detail(&ask.act, "expects")?.as_str() == Some("input") {
            let set = detail(&ask.act, "response_set")?;
            if let Some(set) = set.as_str() {
                sets.push(Id(set.to_owned()));
            }
        }
    }
    let bodies = raw_bodies(scope, &sets)?;
    let mut out = Vec::with_capacity(asks.len());
    for ask in asks {
        let s = states
            .get(&ask.act.id)
            .ok_or_else(|| not_owned("a request Python has to read"))?;
        let post = on.get(&ask.act.id).cloned().flatten();
        let conv = post
            .as_ref()
            .and_then(|p| homes.get(p))
            .cloned()
            .or_else(|| ask.act.conversation.clone());
        let withdrawn = s.withdrawn.is_some();
        let lapsed = s.lapsed.is_some();
        let answered = s.response_present && !withdrawn && !lapsed;
        let owner_withdrew = s
            .withdrawn
            .as_ref()
            .is_some_and(|w| w.by.as_deref() == Some(owner));
        let reconsideration = detail(&ask.act, "reconsideration")?.truthy();
        let mut owner_met = false;
        for id in &s.satisfied_by {
            let Some(act) = met.get(id) else { continue };
            let d = act.detail_object()?;
            if act.actor.as_deref() == Some(owner)
                && !d.is_truthy("withdrawn")?
                && (!reconsideration || d.get("selections").is_some())
            {
                owner_met = true;
            }
        }
        let expects = detail(&ask.act, "expects")?;
        let is_input = expects.as_str() == Some("input");
        let owner_answered = s.expected_of.as_deref() == Some(owner)
            && if is_input {
                s.input.as_ref().is_some_and(|i| !i.ready.is_empty())
            } else {
                (!reconsideration && !s.replies_from_expected.is_empty()) || owner_met
            };
        let state = if asking.contains(&ask.act.id) {
            "open"
        } else if owner_withdrew {
            "withdrawn"
        } else if s.expected_of.as_deref() != Some(owner) {
            "elsewhere"
        } else if owner_answered {
            "answered"
        } else {
            "closed"
        };
        let mut fields = vec![
            ("id".to_owned(), Py::str(&ask.act.id)),
            ("expects".into(), expects),
            ("options".into(), py_stored(&s.options)?),
            (
                "because".into(),
                ask.act.because.as_deref().map_or(Py::None, Py::str),
            ),
            (
                "asked_by".into(),
                ask.act.actor.as_deref().map_or(Py::None, Py::str),
            ),
            (
                "asked_by_name".into(),
                names_or_id(&names, ask.act.actor.as_deref()),
            ),
            (
                "carrier".into(),
                s.expected_of.as_deref().map_or(Py::None, Py::str),
            ),
            (
                "carrier_name".into(),
                names_or_id(&names, s.expected_of.as_deref()),
            ),
            ("open".into(), Py::Bool(state == "open")),
            ("state".into(), Py::str(state)),
            ("answered".into(), Py::Bool(answered)),
            ("withdrawn".into(), Py::Bool(withdrawn)),
            ("lapsed".into(), Py::Bool(lapsed)),
            ("post".into(), post.as_deref().map_or(Py::None, Py::str)),
            (
                "post_number".into(),
                post.as_ref()
                    .and_then(|p| numbers.get(p))
                    .map_or(Py::None, Py::int),
            ),
            (
                "post_author".into(),
                post.as_ref()
                    .and_then(|p| heads.get(p))
                    .and_then(|h| h.attributed_to.as_deref())
                    .map_or(Py::None, Py::str),
            ),
            (
                "post_topics".into(),
                Py::List(
                    post.as_ref()
                        .map(|p| {
                            filings
                                .iter()
                                .filter(|link| {
                                    &link.from == p
                                        && conv.as_ref().is_none_or(|home| {
                                            topic_homes.get(&link.to) == Some(home)
                                        })
                                })
                                .map(|link| Py::str(&link.to))
                                .collect()
                        })
                        .unwrap_or_default(),
                ),
            ),
            (
                "conversation".into(),
                conv.as_deref().map_or(Py::None, Py::str),
            ),
            (
                "conversation_name".into(),
                conv.as_ref()
                    .and_then(|c| names.get(c))
                    .map_or(Py::None, Py::str),
            ),
            ("at".into(), Py::Float(ask.act.at)),
        ];
        if s.form.is_some() {
            let shown = |value: &Option<crate::stored::Stored>| {
                value
                    .as_ref()
                    .map(py_stored)
                    .transpose()
                    .map(|v| v.unwrap_or(Py::None))
            };
            fields.push(("form".into(), shown(&s.form)?));
            fields.push(("index".into(), shown(&s.index)?));
            fields.push(("question".into(), shown(&s.question)?));
        }
        if is_input {
            fields.push(("block".into(), input_block(&bodies, ask)?));
        }
        out.push(Py::Dict(fields));
    }
    Ok(out)
}

impl ReadOp for NeedsYou {
    type Args = NeedsYouArgs;
    type Row = PyRow;
    const NAME: &'static str = "needs_you";
    const BUDGET: Budget = Budget {
        statements: 32 + ExpectationStates::BUDGET.statements * 2 + mentis_rules::STATEMENTS * 5,
    };
    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let as_of = scope.position();
        if let NeedsYouMode::On { post } = &request.args.mode {
            let heads = reads::heads(scope, &[post])?;
            if !heads.get(post).is_some_and(|h| h.is_post()) {
                return Err(refused("not a post: ", post));
            }
        }
        let owner = owner_or_python(scope)?;
        let asks = read_expectations(scope)?;
        let (open, mut state) = asking(scope, &owner, &asks)?;
        let answer = match &request.args.mode {
            NeedsYouMode::Page { before } => page(
                request.limit.unwrap_or(30) as usize,
                &owner,
                open,
                before.as_deref(),
            )?,
            NeedsYouMode::Items => items(scope, &owner, open)?,
            NeedsYouMode::Asks { ids } => {
                let asked = mentis_rules::id_list(ids.iter().map(String::as_str));
                let found: HashMap<String, Act> =
                    crate::forms::read_acts(scope, crate::forms::BY_ID, &asked)?
                        .into_iter()
                        .map(|act| (act.id.clone(), act))
                        .collect();
                let by_id: HashMap<&str, &Asked> =
                    asks.iter().map(|a| (a.act.id.as_str(), a)).collect();
                let mut seen = HashSet::new();
                let wanted: Vec<&Asked> = ids
                    .iter()
                    .filter(|id| seen.insert(id.as_str()))
                    .filter_map(|id| by_id.get(id.as_str()).copied())
                    .collect();
                let missing: Vec<&Asked> = wanted
                    .iter()
                    .copied()
                    .filter(|a| !state.contains_key(&a.act.id))
                    .collect();
                state.extend(states(scope, &missing)?);
                let open_ids: HashSet<String> = open.iter().map(|a| a.act.id.clone()).collect();
                let rows = ask_rows(scope, &owner, &wanted, &state, &open_ids)?;
                let shown: HashMap<&str, Py> = wanted
                    .iter()
                    .zip(rows)
                    .map(|(a, r)| (a.act.id.as_str(), r))
                    .collect();
                let listed = ids
                    .iter()
                    .map(|id| {
                        shown.get(id.as_str()).cloned().unwrap_or_else(|| {
                            let error = if found.contains_key(id) {
                                "not a request"
                            } else {
                                "the record holds no such act"
                            };
                            dict([("id", Py::str(id)), ("error", Py::str(error))])
                        })
                    })
                    .collect();
                dict([("asks", Py::List(listed)), ("limit", Py::int(64))])
            }
            NeedsYouMode::On { post } => {
                let mut thread = HashSet::from([post.clone()]);
                for r in reads::closures(scope, &[post])?
                    .remove(post)
                    .unwrap_or_default()
                {
                    thread.insert(r.id);
                }
                let forms = form_posts(scope, &open)?;
                let mut refs: Vec<&Asked> = Vec::new();
                for ask in &open {
                    if asked_on(ask, &forms)?.is_some_and(|p| thread.contains(&p)) {
                        refs.push(ask);
                    }
                }
                let open_ids: HashSet<String> = open.iter().map(|a| a.act.id.clone()).collect();
                let rows = ask_rows(scope, &owner, &refs, &state, &open_ids)?;
                dict([
                    ("key", Py::str(format!("needs-you:{post}"))),
                    ("post", Py::str(post)),
                    (
                        "items",
                        Py::List(refs.iter().map(|a| Py::str(&a.act.id)).collect()),
                    ),
                    ("asks", Py::List(rows)),
                    ("posts", Py::int(thread.len())),
                    ("owner", Py::str(&owner)),
                ])
            }
        };
        Ok(ReadAnswer {
            rows: vec![PyRow(answer)],
            as_of,
            more: None,
            not_searched: vec![],
        })
    }
}
