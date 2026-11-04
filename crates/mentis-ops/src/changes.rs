//! `read.changes`: what moved after a cursor. Where, never what: callers reread what it names.
//!
//! All of it comes from one record scope, and the outgoing cursor is what was read, so a commit
//! can't be skipped between the answer and its cursor. With no owner named Python says more than
//! this can, and a Brain with no owner forwards.

use std::collections::{BTreeSet, HashMap, HashSet};

use mentis_record::{Flow, Id, Param, Position, ReadScope};

use crate::acts::Act;
use crate::lists::{loaded, not_owned, refused};
use crate::pyjson::{Py, dict};
use crate::window::collections::PyRow;
use crate::window::reads::{
    self, ABOUT_TOPIC, CONTRIBUTION, CONVERSATION, IN_CONVERSATION, LINKED_INTO, REPLIES_TO,
    RETURNING_ACTS,
};
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest, act_columns};

const CAP: u64 = 200;
const CHAIN_DEPTH: usize = 64;
const REPLY_DEPTH: usize = 64;
const RUN_START: &str = "execution-started";
const RUN_ENDS: [&str; 3] = ["result-returned", "delivery-failed", "result-recovered"];
const PARTICIPATES_IN: &str = "participates-in";
const ANCHORS_IN: &str = "anchors-in";
const WORK: &str = "home:work";
const NEEDS_YOU: &str = "home:needs-you";
const ACTIVITY: &str = "home:activity";
const BRIEFING: &str = "home:briefing";
const FOR_YOU: &str = "home:for-you";
const ADDRESSED: &str = "turn-addressed";

const ENTRIES: &str =
    "SELECT id,def_name,link_from,link_to,link_relation FROM entry WHERE seq>?1 ORDER BY seq";
const ACTS: &str = concat!(
    "SELECT ",
    act_columns!(),
    " FROM operational WHERE seq>?1 ORDER BY seq"
);
const DELIVERIES: &str = "SELECT conversation,execution FROM delivery WHERE seq>?1 ORDER BY seq";
const FULL_HEADS: &str = "SELECT id,seq,def_name,link_from,link_to,link_relation,attributed_to \
 FROM entry WHERE id IN (SELECT value FROM json_each(?1))";
const SUPERSEDING_NAME: &str = "SELECT def_name FROM entry WHERE family='definition' \
 AND json_extract(body,'$.substrate_role')='supersedes' ORDER BY seq LIMIT 1";
const LINKED_IN_FORCE: &str = "SELECT link_from,link_to FROM entry WHERE link_relation='linked-into' \
 AND link_from IN (SELECT value FROM json_each(?1)) AND NOT EXISTS(SELECT 1 FROM entry x WHERE x.link_to=entry.id \
 AND x.link_relation=(SELECT def_name FROM entry WHERE family='definition' AND json_extract(body,'$.substrate_role')='supersedes' ORDER BY seq LIMIT 1)) ORDER BY seq";
const FIRST_REPLY: &str = "SELECT link_to FROM entry WHERE link_from=?1 AND link_relation='replies-to' ORDER BY seq LIMIT 1";
const PEOPLE_BEFORE: &str = "SELECT id,link_from,link_to FROM entry WHERE link_relation='participates-in' \
 AND link_to IN (SELECT value FROM json_each(?1))";
const ACTS_BY_ID: &str = concat!(
    "SELECT seq,",
    act_columns!(),
    " FROM operational WHERE id IN (SELECT value FROM json_each(?1)) ORDER BY seq"
);
const RUN_ACTS_ON: &str = concat!(
    "SELECT seq,",
    act_columns!(),
    " FROM operational WHERE execution IN (SELECT value FROM json_each(?1)) \
     AND act IN ('execution-started','result-returned','delivery-failed','result-recovered') ORDER BY seq"
);
const REQUESTS_ON_TURNS: &str = concat!(
    "SELECT seq,",
    act_columns!(),
    " FROM operational WHERE turn IN (SELECT value FROM json_each(?1)) AND act='expectation-recorded' ORDER BY seq"
);
const SAID_ON_TURNS: &str = concat!(
    "SELECT seq,",
    act_columns!(),
    " FROM operational WHERE turn IN (SELECT value FROM json_each(?1)) AND act='turn-said' ORDER BY seq"
);
const REQUESTS_IN: &str = "SELECT id FROM operational WHERE act='expectation-recorded' \
 AND conversation IN (SELECT value FROM json_each(?1))";
const ASSIGNED_UNDER: &str = concat!(
    "SELECT seq,",
    act_columns!(),
    " FROM operational WHERE caused_by IN (SELECT value FROM json_each(?1)) AND act='expectation-assigned' ORDER BY seq"
);
const BODIES: &str = "SELECT id,body FROM entry WHERE id IN (SELECT value FROM json_each(?1))";

#[derive(Clone, Debug, Default)]
pub struct ChangesArgs {
    pub since: Option<String>,
    pub threads: bool,
}

pub struct Changes;

#[derive(Clone)]
struct Entry {
    id: String,
    kind: Option<String>,
    from: Option<String>,
    to: Option<String>,
    relation: Option<String>,
}

#[derive(Clone)]
struct FullHead {
    seq: i64,
    kind: Option<String>,
    from: Option<String>,
    to: Option<String>,
    relation: Option<String>,
    by: Option<String>,
}

/// `parse_change_cursor`.
fn parse(raw: &str) -> Result<Position, OpError> {
    let bad = || refused("not a Fluid change cursor: ", raw);
    let bits: Vec<&str> = raw.split('.').collect();
    let [tag, a, b, c] = bits[..] else {
        return Err(bad());
    };
    if tag != "f1" {
        return Err(bad());
    }
    let plain = |digits: &str| !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit());
    if !(plain(a) && plain(b) && plain(c)) {
        // `int` reads signs, spaces and more, and Python says what of them.
        return Err(not_owned("a cursor Python has to read"));
    }
    let number = |digits: &str| {
        digits
            .parse::<u64>()
            .map_err(|_| not_owned("a cursor Python has to read"))
    };
    Ok(Position {
        entry: number(a)?,
        operational: number(b)?,
        delivery: number(c)?,
    })
}

fn cursor(position: Position) -> Py {
    reads::change_cursor(position)
}

fn list<'a>(values: impl IntoIterator<Item = &'a str>) -> String {
    mentis_rules::id_list(values)
}

fn version(id: &str, reading: &mentis_rules::Reading) -> String {
    if let Some(deleted) = &reading.deleted {
        return deleted.record.0.clone();
    }
    reading
        .revision
        .as_ref()
        .map_or_else(|| id.to_owned(), |r| r.current.0.clone())
}

fn answered(value: Py, as_of: Position) -> ReadAnswer<PyRow> {
    ReadAnswer {
        rows: vec![PyRow(value)],
        as_of,
        more: None,
        not_searched: vec![],
    }
}

fn acts_read(
    scope: &mut dyn ReadScope,
    sql: &'static str,
    ids: &[&str],
) -> Result<Vec<(i64, Act)>, OpError> {
    let mut out = Vec::new();
    if ids.is_empty() {
        return Ok(out);
    }
    let asked = list(ids.iter().copied());
    scope.query(sql, &[Param::Text(&asked)], &mut |row| {
        out.push((
            row.value(0)?.integer().unwrap_or_default(),
            Act::read(row, 1)?,
        ));
        Ok(Flow::Continue)
    })?;
    Ok(out)
}

/// `closed_starts`, with `key` the seq each act carries.
fn closed_starts(acts: &[&(i64, Act)]) -> HashSet<String> {
    let execution_of = |act: &Act| act.execution.clone().filter(|x| !x.is_empty());
    let starts: HashMap<&str, &(i64, Act)> = acts
        .iter()
        .filter(|a| a.1.is(RUN_START) && execution_of(&a.1).is_some())
        .map(|a| (a.1.id.as_str(), *a))
        .collect();
    let mut latest: HashMap<String, i64> = HashMap::new();
    let mut named: HashSet<&str> = HashSet::new();
    for end in acts {
        if !end
            .1
            .act
            .as_deref()
            .is_some_and(|name| RUN_ENDS.contains(&name))
        {
            continue;
        }
        let Some(execution) = execution_of(&end.1) else {
            continue;
        };
        let own = end
            .1
            .caused_by
            .as_deref()
            .and_then(|cause| starts.get(cause).copied());
        let mark = own.map_or(end.0, |start| start.0);
        let held = latest.entry(execution.clone()).or_insert(mark);
        *held = (*held).max(mark);
        if let Some(own) = own
            && execution_of(&own.1).as_deref() == Some(execution.as_str())
        {
            named.insert(own.1.id.as_str());
        }
    }
    starts
        .iter()
        .filter(|(id, start)| {
            execution_of(&start.1)
                .and_then(|x| latest.get(&x).copied())
                .is_some_and(|last| named.contains(**id) || start.0 < last)
        })
        .map(|(id, _)| (*id).to_owned())
        .collect()
}

/// `_requests_above`: every expectation at or above these acts on their causal chains, and the
/// nearest at or above each of `open_from`.
fn requests_above(
    scope: &mut dyn ReadScope,
    open_from: &HashSet<String>,
    closed_from: &HashSet<String>,
) -> Result<(HashSet<String>, HashMap<String, Act>), OpError> {
    let mut found = HashSet::new();
    let mut nearest = HashMap::new();
    let mut seen: HashSet<(String, bool)> = HashSet::new();
    let mut frontier: HashMap<String, bool> = closed_from
        .iter()
        .filter(|p| !p.is_empty())
        .map(|p| (p.clone(), false))
        .collect();
    frontier.extend(
        open_from
            .iter()
            .filter(|p| !p.is_empty())
            .map(|p| (p.clone(), true)),
    );
    for _ in 0..CHAIN_DEPTH {
        frontier.retain(|p, open| {
            !seen.contains(&(p.clone(), true)) && !seen.contains(&(p.clone(), *open))
        });
        if frontier.is_empty() {
            break;
        }
        seen.extend(frontier.iter().map(|(p, o)| (p.clone(), *o)));
        let ids: Vec<&str> = frontier.keys().map(String::as_str).collect();
        let rows = acts_read(scope, ACTS_BY_ID, &ids)?;
        let mut next: HashMap<String, bool> = HashMap::new();
        for (_, act) in rows {
            let looking = frontier.get(&act.id).copied().unwrap_or(false);
            let request = act.is("expectation-recorded");
            if request {
                found.insert(act.id.clone());
                if looking {
                    nearest.insert(act.id.clone(), act.clone());
                }
            }
            if let Some(cause) = act.caused_by.as_ref().filter(|c| !c.is_empty()) {
                let held = next.entry(cause.clone()).or_insert(false);
                *held = *held || (looking && !request);
            }
        }
        frontier = next;
    }
    Ok((found, nearest))
}

/// `_asks_owner_moved`.
fn asks_owner_moved(
    scope: &mut dyn ReadScope,
    nearest: &HashMap<String, Act>,
    acts: &[&Act],
    owner: &str,
) -> Result<bool, OpError> {
    if nearest.is_empty() {
        return Ok(false);
    }
    let requests: Vec<&Act> = nearest.values().collect();
    let carriers = crate::needs_you::carriers(scope, &requests)?;
    if carriers.values().any(|c| c.as_deref() == Some(owner)) {
        return Ok(true);
    }
    let moved: BTreeSet<&str> = acts
        .iter()
        .filter(|a| a.is("expectation-assigned"))
        .filter_map(|a| a.caused_by.as_deref())
        .filter(|cause| nearest.contains_key(*cause))
        .collect();
    if moved.is_empty() {
        return Ok(false);
    }
    let new: HashSet<&str> = acts.iter().map(|a| a.id.as_str()).collect();
    let ids: Vec<&str> = moved.iter().copied().collect();
    let mut earlier: HashMap<String, Vec<Act>> = HashMap::new();
    for (_, act) in acts_read(scope, ASSIGNED_UNDER, &ids)? {
        if !new.contains(act.id.as_str()) && !act.about_items()?.is_empty() {
            earlier
                .entry(act.caused_by.clone().unwrap_or_default())
                .or_default()
                .push(act);
        }
    }
    for id in moved {
        let was = match earlier.get(id).and_then(|got| {
            got.iter().fold(None::<&Act>, |best, act| match best {
                Some(held) if held.at > act.at => Some(held),
                _ => Some(act),
            })
        }) {
            Some(act) => crate::forms::first_about(act)?,
            None => {
                let act = &nearest[id];
                if act.about_items()?.is_empty() {
                    None
                } else {
                    crate::forms::first_about(act)?
                }
            }
        };
        if was.as_deref() == Some(owner) {
            return Ok(true);
        }
    }
    Ok(false)
}

/// `_toward_owner_moved`.
fn toward_owner_moved(
    scope: &mut dyn ReadScope,
    owner: &str,
    acts: &[&Act],
    entries: &[Entry],
    heads: &HashMap<String, FullHead>,
) -> Result<bool, OpError> {
    let posted: Vec<&str> = entries
        .iter()
        .filter(|e| e.relation.as_deref() == Some(IN_CONVERSATION))
        .filter_map(|e| e.from.as_deref())
        .collect();
    let replies: Vec<(&str, &str)> = entries
        .iter()
        .filter(|e| e.relation.as_deref() == Some(REPLIES_TO))
        .filter_map(|e| Some((e.from.as_deref()?, e.to.as_deref()?)))
        .collect();
    let later: Vec<&&Act> = acts
        .iter()
        .filter(|a| a.is(ADDRESSED) && a.turn.as_deref().is_some_and(|t| !t.is_empty()))
        .collect();
    if posted.is_empty() && replies.is_empty() && later.is_empty() {
        return Ok(false);
    }
    let by = |id: &str| heads.get(id).and_then(|h| h.by.as_deref());
    if replies
        .iter()
        .any(|(from, to)| by(to) == Some(owner) && by(from) != Some(owner))
    {
        return Ok(true);
    }
    let mut toward = Vec::new();
    for act in later {
        let mut names = false;
        for who in act.about_items()? {
            names |= who.string()?.as_deref() == Some(owner);
        }
        if names {
            toward.push(act.turn.as_deref().unwrap_or(""));
        }
    }
    if !toward.is_empty() {
        let authors = reads::heads(scope, &toward)?;
        if toward
            .iter()
            .any(|t| authors.get(*t).and_then(|h| h.attributed_to.as_deref()) != Some(owner))
        {
            return Ok(true);
        }
    }
    let theirs: BTreeSet<&str> = posted
        .iter()
        .copied()
        .filter(|p| by(p) != Some(owner))
        .collect();
    if theirs.is_empty() {
        return Ok(false);
    }
    let asked = list(theirs.iter().copied());
    let mut bodies = Vec::new();
    scope.query(BODIES, &[Param::Text(&asked)], &mut |row| {
        bodies.push(reads::text(row, 1)?.unwrap_or_default());
        Ok(Flow::Continue)
    })?;
    for body in bodies {
        let body = loaded(&body)?;
        let Some(addressed) = body.get("addressed_to").filter(|a| a.truthy()) else {
            continue;
        };
        let addressed = addressed
            .as_list()
            .ok_or_else(|| not_owned("an addressing that isn't a list"))?;
        if addressed.iter().any(|who| who.as_str() == Some(owner)) {
            return Ok(true);
        }
    }
    Ok(false)
}

/// What `home.changes_of` hears of one stretch.
#[allow(clippy::too_many_arguments)]
fn home_changes(
    scope: &mut dyn ReadScope,
    owner: &str,
    acts: &[&Act],
    entries: &[Entry],
    heads: &HashMap<String, FullHead>,
    edited: &HashSet<String>,
    renamed: &BTreeSet<String>,
) -> Result<(BTreeSet<String>, BTreeSet<String>), OpError> {
    let mut ents = BTreeSet::new();
    let mut keys = BTreeSet::new();
    let is_end = |a: &Act| a.act.as_deref().is_some_and(|n| RUN_ENDS.contains(&n));
    let starts: Vec<&&Act> = acts.iter().filter(|a| a.is(RUN_START)).collect();
    let ends: Vec<&&Act> = acts.iter().filter(|a| is_end(a)).collect();
    ents.extend(starts.iter().map(|a| format!("run:{}", a.id)));
    if !ends.is_empty() {
        let parents: Vec<&str> = ends
            .iter()
            .filter_map(|e| e.caused_by.as_deref())
            .filter(|c| !c.is_empty())
            .collect();
        for (_, parent) in acts_read(scope, ACTS_BY_ID, &parents)? {
            if parent.is(RUN_START) {
                ents.insert(format!("run:{}", parent.id));
            }
        }
        let handles: BTreeSet<&str> = ends
            .iter()
            .filter_map(|e| e.execution.as_deref())
            .filter(|x| !x.is_empty())
            .collect();
        let handles: Vec<&str> = handles.into_iter().collect();
        let around = acts_read(scope, RUN_ACTS_ON, &handles)?;
        if !around.is_empty() {
            let new: HashSet<&str> = ends.iter().map(|e| e.id.as_str()).collect();
            let all: Vec<&(i64, Act)> = around.iter().collect();
            let before: Vec<&(i64, Act)> = around
                .iter()
                .filter(|a| !new.contains(a.1.id.as_str()))
                .collect();
            let without = closed_starts(&before);
            ents.extend(
                closed_starts(&all)
                    .into_iter()
                    .filter(|id| !without.contains(id))
                    .map(|id| format!("run:{id}")),
            );
        }
    }
    if !starts.is_empty() || !ends.is_empty() {
        keys.insert(ACTIVITY.to_owned());
    }
    let mut up: HashSet<String> = acts
        .iter()
        .filter(|a| !a.is("expectation-recorded"))
        .filter_map(|a| a.caused_by.clone())
        .filter(|c| !c.is_empty())
        .collect();
    up.extend(
        acts.iter()
            .filter(|a| a.is("expectation-recorded"))
            .map(|a| a.id.clone()),
    );
    let parents_of_new: HashSet<String> = acts
        .iter()
        .filter(|a| a.is("expectation-recorded"))
        .filter_map(|a| a.caused_by.clone())
        .filter(|c| !c.is_empty())
        .collect();
    let loose: BTreeSet<&str> = acts
        .iter()
        .filter(|a| !a.is(RUN_START) && !is_end(a))
        .filter_map(|a| a.execution.as_deref())
        .filter(|x| !x.is_empty())
        .collect();
    if !loose.is_empty() {
        let handles: Vec<&str> = loose.into_iter().collect();
        let mut newest: HashMap<String, Option<String>> = HashMap::new();
        for (_, start) in acts_read(scope, RUN_ACTS_ON, &handles)? {
            if start.is(RUN_START) {
                newest.insert(start.execution.clone().unwrap_or_default(), start.caused_by);
            }
        }
        up.extend(newest.into_values().flatten().filter(|c| !c.is_empty()));
    }
    let replied: BTreeSet<&str> = entries
        .iter()
        .filter(|e| e.relation.as_deref() == Some(REPLIES_TO))
        .filter_map(|e| e.to.as_deref())
        .collect();
    let replied: Vec<&str> = replied.into_iter().collect();
    for (_, act) in acts_read(scope, REQUESTS_ON_TURNS, &replied)? {
        up.insert(act.id);
    }
    let readied: BTreeSet<&str> = acts
        .iter()
        .filter(|a| a.is("marked-ready"))
        .filter_map(|a| a.turn.as_deref())
        .filter(|t| !t.is_empty())
        .collect();
    let readied: Vec<&str> = readied.into_iter().collect();
    for (_, act) in acts_read(scope, REQUESTS_ON_TURNS, &readied)? {
        if act.detail_object()?.says("expects", "input")? {
            up.insert(act.id);
        }
    }
    let (requests, nearest) = requests_above(scope, &up, &parents_of_new)?;
    ents.extend(requests.iter().map(|id| format!("work:{id}")));
    if !requests.is_empty() {
        keys.insert(WORK.to_owned());
    }
    if asks_owner_moved(scope, &nearest, acts, owner)? {
        keys.insert(NEEDS_YOU.to_owned());
    }
    if !renamed.is_empty() {
        let asked = list(renamed.iter().map(String::as_str));
        scope.query(REQUESTS_IN, &[Param::Text(&asked)], &mut |row| {
            ents.insert(format!("work:{}", reads::text(row, 0)?.unwrap_or_default()));
            Ok(Flow::Continue)
        })?;
    }
    let mut briefed = false;
    for act in acts.iter().filter(|a| a.is("turn-said")) {
        briefed |= act.detail_object()?.is_truthy("answers_request")?;
    }
    if !briefed && !edited.is_empty() {
        let ids: Vec<Id> = edited.iter().map(|id| Id(id.clone())).collect();
        let lines = mentis_rules::roots(scope, &ids)?;
        let mut turns: BTreeSet<&str> = edited.iter().map(String::as_str).collect();
        turns.extend(lines.values().map(|root| root.0.as_str()));
        let turns: Vec<&str> = turns.into_iter().collect();
        for (_, said) in acts_read(scope, SAID_ON_TURNS, &turns)? {
            briefed |= said.detail_object()?.is_truthy("answers_request")?;
        }
    }
    if briefed {
        keys.insert(BRIEFING.to_owned());
    }
    if toward_owner_moved(scope, owner, acts, entries, heads)? {
        keys.insert(FOR_YOU.to_owned());
    }
    Ok((ents, keys))
}

/// `_needs_you_moved`.
fn needs_you_moved(
    scope: &mut dyn ReadScope,
    owner: &str,
    acts: &[&Act],
    entries: &[Entry],
) -> Result<bool, OpError> {
    let relevant: Vec<&Act> = acts
        .iter()
        .copied()
        .filter(|a| {
            a.is("expectation-recorded") || a.is("expectation-assigned") || a.is("expectation-met")
        })
        .collect();
    let mut up: HashSet<String> = relevant
        .iter()
        .filter_map(|a| {
            if a.is("expectation-recorded") {
                Some(a.id.clone())
            } else {
                a.caused_by.clone()
            }
        })
        .collect();
    let replied: BTreeSet<&str> = entries
        .iter()
        .filter(|e| e.relation.as_deref() == Some(REPLIES_TO))
        .filter_map(|e| e.to.as_deref())
        .collect();
    let replied: Vec<&str> = replied.into_iter().collect();
    for (_, act) in acts_read(scope, REQUESTS_ON_TURNS, &replied)? {
        up.insert(act.id);
    }
    up.retain(|id| !id.is_empty());
    if up.is_empty() {
        return Ok(false);
    }
    let (_, nearest) = requests_above(scope, &up, &HashSet::new())?;
    asks_owner_moved(scope, &nearest, &relevant, owner)
}

/// `anchored.changes_of`.
fn anchors_moved(scope: &mut dyn ReadScope, acts: &[&Act]) -> Result<BTreeSet<String>, OpError> {
    let mut posts = BTreeSet::new();
    let anchor_turn = |scope: &mut dyn ReadScope, aid: &str| -> Result<Option<String>, OpError> {
        let links = reads::links_from(scope, ANCHORS_IN, &[aid])?;
        Ok(links.into_iter().next().map(|l| l.to))
    };
    for act in acts {
        let turn = act.turn.as_deref().filter(|t| !t.is_empty());
        if act.is("anchor-created") || act.is("reaction-recorded") || act.is("reaction-changed") {
            if let Some(turn) = turn {
                posts.insert(turn.to_owned());
            }
        } else if act.is("conversation-opened") {
            let detail = act.detail_object()?;
            if detail.is_truthy("opened_from")? {
                let from = detail
                    .text("opened_from")?
                    .ok_or_else(|| not_owned("an opening that names no anchor"))?;
                posts.extend(anchor_turn(scope, &from)?);
            }
        } else if act.is("material-deleted") {
            let about = act.about_items()?;
            if let Some(first) = about.first().map(|a| a.string()).transpose()?.flatten() {
                let heads = reads::heads(scope, &[&first])?;
                if heads
                    .get(&first)
                    .is_some_and(|h| h.kind.as_deref() == Some("reaction"))
                {
                    let body = entry_body(scope, &first)?;
                    if let Some(aid) = body.get("about").and_then(Py::as_str) {
                        posts.extend(anchor_turn(scope, aid)?);
                    }
                }
            }
        } else if act.is("turn-said") || act.is("turn-edited") || act.is("turn-deleted") {
            let Some(turn) = turn else { continue };
            if !act.is("turn-said") && !reads::links_to(scope, ANCHORS_IN, &[turn])?.is_empty() {
                posts.insert(turn.to_owned());
            }
            let body = entry_body_or_none(scope, turn)?;
            if let Some(body) = body {
                let parts = body.get("parts").filter(|p| p.truthy());
                let parts = match parts {
                    None => &[][..],
                    Some(parts) => parts
                        .as_list()
                        .ok_or_else(|| not_owned("parts that aren't a list"))?,
                };
                for part in parts {
                    if part.is_dict()
                        && part.get("type").and_then(Py::as_str) == Some("anchor")
                        && let Some(aid) = part.get("ref").and_then(Py::as_str)
                    {
                        posts.extend(anchor_turn(scope, aid)?);
                        break;
                    }
                }
            }
        }
    }
    Ok(posts.into_iter().map(|p| format!("anchors:{p}")).collect())
}

fn entry_body_or_none(scope: &mut dyn ReadScope, id: &str) -> Result<Option<Py>, OpError> {
    let asked = list([id]);
    let mut body = None;
    scope.query(BODIES, &[Param::Text(&asked)], &mut |row| {
        body = reads::text(row, 1)?;
        Ok(Flow::Stop)
    })?;
    body.as_deref().map(loaded).transpose()
}

fn entry_body(scope: &mut dyn ReadScope, id: &str) -> Result<Py, OpError> {
    entry_body_or_none(scope, id)?.ok_or_else(|| not_owned("an entry the record didn't give back"))
}

/// `_ancestors`: the posts this answers, nearest first, first link winning.
fn ancestors(scope: &mut dyn ReadScope, post: &str) -> Result<Vec<String>, OpError> {
    let mut out = Vec::new();
    let mut seen = HashSet::from([post.to_owned()]);
    let mut up = post.to_owned();
    for _ in 0..REPLY_DEPTH {
        let mut next = None;
        scope.query(FIRST_REPLY, &[Param::Text(&up)], &mut |row| {
            next = reads::text(row, 0)?;
            Ok(Flow::Stop)
        })?;
        let Some(next) = next else { break };
        if !seen.insert(next.clone()) {
            break;
        }
        out.push(next.clone());
        up = next;
    }
    Ok(out)
}

impl ReadOp for Changes {
    type Args = ChangesArgs;
    type Row = PyRow;
    const NAME: &'static str = "changes";
    /// A stretch is at most [`CAP`] rows of each kind, and what it can ask of the record is bounded
    /// by that and the chain depths, so this is a ceiling and not a figure for a usual stretch.
    const BUDGET: Budget = Budget {
        statements: 20
            + (CHAIN_DEPTH as u32) * 2
            + (REPLY_DEPTH as u32) * (CAP as u32)
            + mentis_rules::STATEMENTS * 4
            + (CAP as u32) * 6,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let at = scope.position();
        let Some(raw) = request.args.since.as_deref().filter(|s| !s.is_empty()) else {
            let mut value = dict([
                ("cursor", cursor(at)),
                ("since", Py::None),
                ("start", Py::Bool(true)),
            ]);
            if request.args.threads {
                value.set("threads", Py::List(vec![]));
            }
            return Ok(answered(value, at));
        };
        let since = parse(raw)?;
        let threads_empty = |mut value: Py| {
            if request.args.threads {
                value.set("threads", Py::List(vec![]));
            }
            value
        };
        if since == at {
            let value = dict([
                ("cursor", cursor(at)),
                ("since", Py::str(raw)),
                ("posts", Py::List(vec![])),
                ("conversations", Py::List(vec![])),
                (
                    "memberships",
                    dict([("added", Py::List(vec![])), ("ended", Py::List(vec![]))]),
                ),
                ("collections", Py::List(vec![])),
                ("entities", Py::List(vec![])),
                ("work", Py::List(vec![])),
                ("other", Py::int(0)),
            ]);
            return Ok(answered(threads_empty(value), at));
        }
        if since.entry > at.entry
            || since.operational > at.operational
            || since.delivery > at.delivery
            || at.entry - since.entry > CAP
            || at.operational - since.operational > CAP
            || at.delivery - since.delivery > CAP
        {
            let value = dict([
                ("cursor", cursor(at)),
                ("since", Py::str(raw)),
                ("reread", Py::Bool(true)),
                (
                    "why",
                    Py::str(
                        "more than 200 rows were written since that cursor, or this record is not at or past it",
                    ),
                ),
            ]);
            return Ok(answered(threads_empty(value), at));
        }
        let owner = crate::window::classify::owner_of(scope)?
            .ok_or_else(|| not_owned("a record that names no owner"))?;

        let mut entries = Vec::new();
        scope.query(ENTRIES, &[Param::Integer(since.entry as i64)], &mut |row| {
            entries.push(Entry {
                id: reads::text(row, 0)?.unwrap_or_default(),
                kind: reads::text(row, 1)?,
                from: reads::text(row, 2)?,
                to: reads::text(row, 3)?,
                relation: reads::text(row, 4)?,
            });
            Ok(Flow::Continue)
        })?;
        let mut acts_held = Vec::new();
        scope.query(
            ACTS,
            &[Param::Integer(since.operational as i64)],
            &mut |row| {
                acts_held.push(Act::read(row, 0)?);
                Ok(Flow::Continue)
            },
        )?;
        let acts: Vec<&Act> = acts_held.iter().collect();
        let mut delivered = Vec::new();
        scope.query(
            DELIVERIES,
            &[Param::Integer(since.delivery as i64)],
            &mut |row| {
                delivered.push((reads::text(row, 0)?, reads::text(row, 1)?));
                Ok(Flow::Continue)
            },
        )?;

        let mut wanted: Vec<&str> = Vec::new();
        for e in &entries {
            wanted.push(e.id.as_str());
            wanted.extend(e.from.as_deref());
            wanted.extend(e.to.as_deref());
        }
        let mut heads: HashMap<String, FullHead> = HashMap::new();
        if !wanted.is_empty() {
            let asked = list(wanted.iter().copied());
            scope.query(FULL_HEADS, &[Param::Text(&asked)], &mut |row| {
                heads.insert(
                    reads::text(row, 0)?.unwrap_or_default(),
                    FullHead {
                        seq: row.value(1)?.integer().unwrap_or_default(),
                        kind: reads::text(row, 2)?,
                        from: reads::text(row, 3)?,
                        to: reads::text(row, 4)?,
                        relation: reads::text(row, 5)?,
                        by: reads::text(row, 6)?,
                    },
                );
                Ok(Flow::Continue)
            })?;
        }
        let top = entries
            .iter()
            .filter_map(|e| heads.get(&e.id))
            .map(|h| h.seq)
            .max()
            .unwrap_or(since.entry as i64);
        let next = Position {
            entry: top.max(since.entry as i64) as u64,
            operational: since.operational + acts.len() as u64,
            delivery: since.delivery + delivered.len() as u64,
        };
        let mut sup = None;
        scope.query(SUPERSEDING_NAME, &[], &mut |row| {
            sup = reads::text(row, 0)?;
            Ok(Flow::Stop)
        })?;

        let mut touched: BTreeSet<String> = BTreeSet::new();
        let mut convs: BTreeSet<String> = BTreeSet::new();
        let mut keys: BTreeSet<String> = BTreeSet::new();
        let mut work: BTreeSet<String> = BTreeSet::new();
        let mut added = Vec::new();
        let mut ended = Vec::new();
        let mut versions: BTreeSet<String> = BTreeSet::new();
        let mut superseded: HashSet<String> = HashSet::new();
        let mut renames: HashSet<String> = HashSet::new();
        let mut renamed: BTreeSet<String> = BTreeSet::new();
        let mut other = 0u64;
        let membership = |post: &str, conversation: &str, via: &str, link: &str| {
            dict([
                ("post", Py::str(post)),
                ("conversation", Py::str(conversation)),
                ("via", Py::str(via)),
                ("link", Py::str(link)),
            ])
        };
        for e in &entries {
            let kind_of = |x: &Option<String>| {
                x.as_ref()
                    .and_then(|id| heads.get(id))
                    .and_then(|h| h.kind.clone())
            };
            let Some(relation) = e.relation.as_deref().filter(|r| !r.is_empty()) else {
                match e.kind.as_deref() {
                    Some(CONTRIBUTION) => {
                        versions.insert(e.id.clone());
                    }
                    Some(CONVERSATION) => {
                        convs.insert(e.id.clone());
                        keys.insert("conversations".into());
                    }
                    Some("deletion") => {}
                    _ => other += 1,
                }
                continue;
            };
            let from = e.from.as_deref().unwrap_or_default();
            let to = e.to.as_deref().unwrap_or_default();
            if relation == IN_CONVERSATION {
                added.push(membership(from, to, "home", &e.id));
                touched.insert(from.to_owned());
                convs.insert(to.to_owned());
                keys.extend([
                    format!("conversation:{to}"),
                    "stream".to_owned(),
                    "conversations".to_owned(),
                ]);
            } else if relation == LINKED_INTO {
                added.push(membership(from, to, "linked", &e.id));
                touched.insert(from.to_owned());
                convs.insert(to.to_owned());
                keys.extend([format!("conversation:{to}"), "conversations".to_owned()]);
            } else if relation == REPLIES_TO {
                touched.insert(from.to_owned());
                touched.insert(to.to_owned());
                keys.insert(format!("thread:{to}"));
                for up in ancestors(scope, to)? {
                    keys.insert(format!("thread:{up}"));
                }
            } else if Some(relation) == sup.as_deref() {
                let h = heads.get(to);
                if h.is_some_and(|h| h.relation.as_deref() == Some(LINKED_INTO)) {
                    let h = h.expect("just looked");
                    let post = h.from.clone().unwrap_or_default();
                    let conversation = h.to.clone().unwrap_or_default();
                    ended.push(membership(&post, &conversation, "linked", to));
                    touched.insert(post);
                    keys.extend([
                        format!("conversation:{conversation}"),
                        "conversations".to_owned(),
                    ]);
                    convs.insert(conversation);
                } else if kind_of(&e.to).as_deref() == Some(CONTRIBUTION) {
                    versions.insert(to.to_owned());
                    superseded.insert(to.to_owned());
                } else if kind_of(&e.to).as_deref() == Some(CONVERSATION) {
                    let root = mentis_rules::roots(scope, &[Id(to.to_owned())])?
                        .remove(&Id(to.to_owned()))
                        .map_or_else(|| to.to_owned(), |id| id.0);
                    renames.insert(from.to_owned());
                    renamed.insert(root.clone());
                    convs.insert(root.clone());
                    keys.extend(["conversations".to_owned(), format!("conversation:{root}")]);
                } else if !h.is_some_and(|h| h.relation.as_deref().is_some_and(|r| !r.is_empty())) {
                    other += 1;
                }
            } else if relation == PARTICIPATES_IN {
                convs.insert(to.to_owned());
            } else if relation == ABOUT_TOPIC {
                touched.insert(from.to_owned());
            } else {
                let from_post = kind_of(&e.from).as_deref() == Some(CONTRIBUTION);
                let to_post = kind_of(&e.to).as_deref() == Some(CONTRIBUTION);
                if from_post {
                    touched.insert(from.to_owned());
                }
                if to_post {
                    touched.insert(to.to_owned());
                }
                if !from_post && !to_post {
                    other += 1;
                }
            }
        }
        let joined: Vec<&Entry> = entries
            .iter()
            .filter(|e| e.relation.as_deref() == Some(PARTICIPATES_IN))
            .collect();
        if !joined.is_empty() {
            let new: HashSet<&str> = joined.iter().map(|e| e.id.as_str()).collect();
            let rooms: BTreeSet<&str> = joined.iter().filter_map(|e| e.to.as_deref()).collect();
            let asked = list(rooms.iter().copied());
            let mut previous: HashSet<(String, String)> = HashSet::new();
            scope.query(PEOPLE_BEFORE, &[Param::Text(&asked)], &mut |row| {
                if !new.contains(reads::text(row, 0)?.unwrap_or_default().as_str()) {
                    previous.insert((
                        reads::text(row, 1)?.unwrap_or_default(),
                        reads::text(row, 2)?.unwrap_or_default(),
                    ));
                }
                Ok(Flow::Continue)
            })?;
            if joined.iter().any(|e| {
                !previous.contains(&(
                    e.from.clone().unwrap_or_default(),
                    e.to.clone().unwrap_or_default(),
                ))
            }) {
                keys.insert("conversations".into());
            }
        }
        convs.retain(|c| !renames.contains(c));
        let mut returned = HashSet::new();
        for a in &acts {
            if a.is("operation-answered") || a.is("consent-set") {
                if let Some(x) = a.execution.as_ref().filter(|x| !x.is_empty()) {
                    work.insert(x.clone());
                }
                continue;
            }
            if let Some(t) = a.turn.as_ref().filter(|t| !t.is_empty()) {
                touched.insert(t.clone());
                if a.act
                    .as_deref()
                    .is_some_and(|n| RETURNING_ACTS.contains(&n))
                {
                    returned.insert(t.clone());
                }
            }
            if let Some(c) = a.conversation.as_ref().filter(|c| !c.is_empty()) {
                convs.insert(c.clone());
            }
            if let Some(x) = a.execution.as_ref().filter(|x| !x.is_empty()) {
                work.insert(x.clone());
            }
        }
        for (c, x) in delivered {
            convs.extend(c.filter(|c| !c.is_empty()));
            work.extend(x.filter(|x| !x.is_empty()));
        }

        let mut asked: BTreeSet<&str> = versions.iter().map(String::as_str).collect();
        asked.extend(touched.iter().map(String::as_str));
        let asked: Vec<&str> = asked.into_iter().collect();
        let first_homes = reads::homes_of(scope, &asked)?;
        let unhomed: Vec<Id> = versions
            .iter()
            .filter(|v| !first_homes.contains_key(*v))
            .map(|v| Id(v.clone()))
            .collect();
        let lines = mentis_rules::roots(scope, &unhomed)?;
        let line_roots: Vec<&str> = lines.values().map(|root| root.0.as_str()).collect();
        let root_homes = reads::homes_of(scope, &line_roots)?;
        let mut more_touched = Vec::new();
        for v in &versions {
            if first_homes.contains_key(v) {
                more_touched.push(v.clone());
                if superseded.contains(v) {
                    keys.insert(format!("objects:{v}"));
                }
            } else if let Some(root) = lines.get(&Id(v.clone()))
                && root_homes.contains_key(&root.0)
            {
                more_touched.push(root.0.clone());
                keys.insert(format!("objects:{}", root.0));
            }
        }
        touched.extend(more_touched);
        let touched_refs: Vec<&str> = touched.iter().map(String::as_str).collect();
        let homes = reads::homes_of(scope, &touched_refs)?;
        keys.extend(
            returned
                .iter()
                .filter(|p| homes.contains_key(*p))
                .map(|p| format!("objects:{p}")),
        );
        let posts: Vec<String> = touched
            .iter()
            .filter(|p| homes.contains_key(*p))
            .cloned()
            .collect();

        let (entities, home_keys) = home_changes(
            scope,
            &owner,
            &acts,
            &entries,
            &heads,
            &superseded,
            &renamed,
        )?;
        let activity_moved = home_keys.contains(ACTIVITY);
        let needs_moved = home_keys.contains(NEEDS_YOU);
        keys.extend(home_keys);
        keys.extend(anchors_moved(scope, &acts)?);
        if !versions.is_empty() {
            keys.insert("stream".into());
        }
        if activity_moved
            || (!keys.contains("conversations")
                && needs_moved
                && needs_you_moved(scope, &owner, &acts, &entries)?)
        {
            keys.insert("conversations".into());
        }

        let post_refs: Vec<&str> = posts.iter().map(String::as_str).collect();
        let mut included: HashMap<String, Vec<String>> = HashMap::new();
        let included_list = list(post_refs.iter().copied());
        scope.query(
            LINKED_IN_FORCE,
            &[Param::Text(&included_list)],
            &mut |row| {
                if let (Some(p), Some(c)) = (reads::text(row, 0)?, reads::text(row, 1)?) {
                    included.entry(p).or_default().push(c);
                }
                Ok(Flow::Continue)
            },
        )?;
        let now =
            mentis_rules::now_reads(scope, &posts.iter().cloned().map(Id).collect::<Vec<_>>())?;
        let mut posts_out = Vec::with_capacity(posts.len());
        for p in &posts {
            let mut where_ = vec![homes[p].clone()];
            where_.extend(included.remove(p).unwrap_or_default());
            let held = where_.clone();
            for item in &ended {
                if item.get("post").and_then(Py::as_str) == Some(p)
                    && let Some(c) = item.get("conversation").and_then(Py::as_str)
                    && !held.iter().any(|x| x == c)
                {
                    where_.push(c.to_owned());
                }
            }
            let reading = now.get(&Id(p.clone()));
            if reading.is_some_and(|r| r.python_says) {
                return Err(not_owned("a post Python has to present"));
            }
            posts_out.push(dict([
                ("id", Py::str(p)),
                (
                    "version",
                    reading.map_or(Py::None, |r| Py::str(version(p, r))),
                ),
                (
                    "conversations",
                    Py::List(where_.into_iter().map(Py::str).collect()),
                ),
            ]));
        }
        let threads = if request.args.threads {
            let mut roots: BTreeSet<String> = keys
                .iter()
                .filter_map(|k| k.strip_prefix("thread:"))
                .map(str::to_owned)
                .collect();
            let objects: Vec<&str> = keys
                .iter()
                .filter_map(|k| k.strip_prefix("objects:"))
                .collect();
            for post in objects {
                roots.extend(ancestors(scope, post)?);
            }
            Some(Py::List(roots.into_iter().map(Py::str).collect()))
        } else {
            None
        };
        let mut value = dict([
            ("cursor", cursor(next)),
            ("since", Py::str(raw)),
            ("posts", Py::List(posts_out)),
            (
                "conversations",
                Py::List(convs.into_iter().map(Py::str).collect()),
            ),
            (
                "memberships",
                dict([("added", Py::List(added)), ("ended", Py::List(ended))]),
            ),
            (
                "collections",
                Py::List(keys.into_iter().map(Py::str).collect()),
            ),
            (
                "entities",
                Py::List(entities.into_iter().map(Py::str).collect()),
            ),
            ("work", Py::List(work.into_iter().map(Py::str).collect())),
            ("other", Py::int(other)),
        ]);
        if let Some(threads) = threads {
            value.set("threads", threads);
        }
        Ok(answered(value, at))
    }
}
