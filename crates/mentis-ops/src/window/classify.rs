//! `conversation/agent_work.py`: which posts are agents writing to each other, told from the record.
//! `classify` stays in Python for `web/__init__.py:763` and `fluid/latest.py`. This is the window's.
//!
//! **Statements are fixed per call.** Python's walk is one statement a level, at most eight; here all
//! eight levels are one recursive statement, and the levels are then walked in memory as Python
//! walks them, so `unread` and the order of replies come out the same.

use std::collections::{HashMap, HashSet};

use mentis_record::{Flow, Id, Param, ReadScope, RecordError};
use mentis_rules::id_list;

use super::python_says;
use super::reads::{self, REPLIES_TO, links_from, links_to, text};
use crate::OpError;
use crate::pyjson::{self, Py, dict};

const MAX_DEPTH: usize = 8;
const ANCHORS_IN: &str = "anchors-in";
const REACTS_TO: &str = "reacts-to";
const RESPONDS_TO: &str = "responds-to";
const UNATTRIBUTED: &str = "unattributed-local-request";
const FORM_ACTS: [&str; 2] = ["decision-form", "decision-form-attached"];
const OWNER_ABOUT: &str = "the owner";
static NOBODY: Py = Py::None;

/// `_owner`: the first row of the Kind whose `about` says so. Through the definition index, as
/// `entries_of_kind` reads it, with SQLite reading the one field.
const OWNER: &str = "SELECT id FROM entry WHERE def_name = 'participant' AND family = 'entry' \
     AND link_relation IS NULL AND json_extract(body, '$.about') = ?1 ORDER BY seq LIMIT 1";

/// Every `replies-to` link at or above the eighth level of the walk from `?1`. A node at the eighth
/// level has its replies unread, as in Python, so only the links under the nodes above it are here.
const WALK: &str = "WITH RECURSIVE w(id, depth) AS ( \
       SELECT value, 0 FROM json_each(?1) \
       UNION \
       SELECT l.link_from, w.depth + 1 FROM w JOIN entry l ON l.link_to = w.id \
       WHERE l.link_relation = 'replies-to' AND w.depth < 8), \
     nodes(id, depth) AS (SELECT id, MIN(depth) FROM w GROUP BY id) \
     SELECT l.link_from, l.link_to FROM nodes n JOIN entry l ON l.link_to = n.id \
     WHERE l.link_relation = 'replies-to' AND n.depth < 8 ORDER BY l.seq";

const ENTRIES: &str = "SELECT id, attributed_to, written_by, body FROM entry \
     WHERE id IN (SELECT value FROM json_each(?1))";

const ACTS_ON: &str = "SELECT id, act, turn, actor, at, about, detail, caused_by FROM operational \
     WHERE turn IN (SELECT value FROM json_each(?1)) ORDER BY seq";
const ACTS_BY_ID: &str = "SELECT id, act, turn, actor, at, about, detail, caused_by FROM operational \
     WHERE id IN (SELECT value FROM json_each(?1)) ORDER BY seq";
const ASSIGNED: &str = "SELECT id, act, turn, actor, at, about, detail, caused_by FROM operational \
     WHERE caused_by IN (SELECT value FROM json_each(?1)) AND act = 'expectation-assigned' \
     ORDER BY seq";

/// The most statements [`classify`] runs: the owner; the walk; the entries; the acts; who carries the
/// expectations; what was asked; the parents; their authors; the anchors; the reactions; the responses;
/// and how the agents named are called.
pub const STATEMENTS: u32 = 11 + mentis_rules::STATEMENTS;

/// `operational`'s columns that `classify` reads.
#[derive(Clone, Debug)]
pub(crate) struct Act {
    pub id: String,
    pub act: String,
    pub turn: Option<String>,
    pub actor: Option<String>,
    pub at: Py,
    pub about: Py,
    pub detail: Py,
    pub caused_by: Option<String>,
}

pub(crate) fn acts(
    scope: &mut dyn ReadScope,
    sql: &'static str,
    list: &str,
) -> Result<Vec<Act>, OpError> {
    let mut out = Vec::new();
    let mut unread = false;
    scope.query(sql, &[Param::Text(list)], &mut |row| {
        let about = text(row, 5)?;
        let detail = text(row, 6)?;
        let (Some(about), Some(detail)) = (
            about.as_deref().and_then(pyjson::loads),
            detail.as_deref().and_then(pyjson::loads),
        ) else {
            unread = true;
            return Ok(Flow::Stop);
        };
        out.push(Act {
            id: text(row, 0)?.unwrap_or_default(),
            act: text(row, 1)?.unwrap_or_default(),
            turn: text(row, 2)?,
            actor: text(row, 3)?,
            at: reads::number(row, 4)?,
            about,
            detail,
            caused_by: text(row, 7)?,
        });
        Ok(Flow::Continue)
    })?;
    if unread {
        return Err(python_says("an act this can't read"));
    }
    Ok(out)
}

/// `(a.get("detail") or {}).get(name)`. Of a true detail that isn't an object, Python raises.
pub(crate) fn detail_field<'a>(act: &'a Act, name: &str) -> Result<Option<&'a Py>, OpError> {
    if !act.detail.truthy() {
        return Ok(None);
    }
    if !act.detail.is_dict() {
        return Err(python_says("an act's detail that isn't an object"));
    }
    Ok(act.detail.get(name))
}

/// `value in (about or ())`, for the shapes a record holds.
fn names(about: &Py, who: &str) -> Result<bool, OpError> {
    if !about.truthy() {
        return Ok(false);
    }
    match about {
        Py::List(items) => Ok(items.iter().any(|item| item.as_str() == Some(who))),
        _ => Err(python_says("a list of people that isn't a list")),
    }
}

/// `Conversations._read_carriers`: expectation id -> its current carrier.
fn carriers(scope: &mut dyn ReadScope, exps: &[&Act]) -> Result<HashMap<String, Py>, OpError> {
    if exps.is_empty() {
        return Ok(HashMap::new());
    }
    let list = id_list(exps.iter().map(|act| act.id.as_str()));
    let mut assigned: HashMap<String, Vec<Act>> = HashMap::new();
    for act in acts(scope, ASSIGNED, &list)? {
        if act.about.truthy()
            && let Some(by) = act.caused_by.clone()
        {
            assigned.entry(by).or_default().push(act);
        }
    }
    let first_of = |about: &Py| -> Result<Py, OpError> {
        match about {
            Py::List(items) => Ok(items.first().cloned().unwrap_or(Py::None)),
            _ => Err(python_says("a carrier that isn't in a list")),
        }
    };
    let mut out = HashMap::with_capacity(exps.len());
    for exp in exps {
        let carrier = match assigned.get_mut(&exp.id) {
            Some(found) => {
                // Stable, as `sorted(key=at)`: of equal times the later in write order stays last.
                found.sort_by(|a, b| reads::as_f64(&a.at).total_cmp(&reads::as_f64(&b.at)));
                first_of(&found[found.len() - 1].about)?
            }
            None if exp.about.truthy() => first_of(&exp.about)?,
            None => Py::None,
        };
        out.insert(exp.id.clone(), carrier);
    }
    Ok(out)
}

/// The owner Participant, as the baseline identifies them. `None` where the record names nobody.
pub(crate) fn owner_of(scope: &mut dyn ReadScope) -> Result<Option<String>, RecordError> {
    let mut owner = None;
    scope.query(OWNER, &[Param::Text(OWNER_ABOUT)], &mut |row| {
        owner = text(row, 0)?;
        Ok(Flow::Stop)
    })?;
    Ok(owner)
}

/// One level at a time, from every link the statement found: what `_walk` keeps.
fn levels(roots: &[&str], links: &HashMap<String, Vec<String>>) -> Walk {
    let mut kids: HashMap<String, Vec<String>> = HashMap::new();
    let mut seen: HashSet<String> = roots.iter().map(|root| (*root).to_owned()).collect();
    let mut frontier: Vec<String> = seen.iter().cloned().collect();
    frontier.sort();
    let mut depth = 0;
    while !frontier.is_empty() && depth < MAX_DEPTH {
        depth += 1;
        let mut next = Vec::new();
        for parent in &frontier {
            for child in links.get(parent).map_or(&[][..], Vec::as_slice) {
                kids.entry(parent.clone()).or_default().push(child.clone());
                if seen.insert(child.clone()) {
                    next.push(child.clone());
                }
            }
        }
        next.sort();
        frontier = next;
    }
    Walk {
        kids,
        unread: frontier.into_iter().collect(),
    }
}

struct Walk {
    kids: HashMap<String, Vec<String>>,
    unread: HashSet<String>,
}

#[derive(Clone, Debug)]
struct Kind {
    kind: &'static str,
    to: Option<String>,
}

#[derive(Debug)]
struct Written {
    attributed_to: Option<String>,
    written_by: Option<String>,
    body: Py,
}

/// `(e.get("body") or {}).get("addressed_to")`.
fn addressed_to(written: &Written) -> Result<Option<&Py>, OpError> {
    if !written.body.truthy() {
        return Ok(None);
    }
    if !written.body.is_dict() {
        return Err(python_says("a body that isn't an object"));
    }
    Ok(written.body.get("addressed_to"))
}

struct Facts<'a> {
    owner: &'a str,
    entries: HashMap<String, Written>,
    on: HashMap<String, Vec<&'a Act>>,
    carriers: HashMap<String, Py>,
    asked: HashMap<String, Act>,
    parent: HashMap<String, String>,
    authors: HashMap<String, Option<String>>,
    reacted: HashSet<String>,
    answered: HashSet<String>,
}

impl Facts<'_> {
    fn author_of(&self, id: Option<&str>) -> Option<&str> {
        self.authors.get(id?)?.as_deref()
    }

    /// `base`: `n` on its own, nothing under it read. A kind, or `None`.
    fn base(&self, n: &str) -> Result<Option<Kind>, OpError> {
        let Some(e) = self.entries.get(n) else {
            return Ok(None);
        };
        let owner = self.owner;
        if e.attributed_to.as_deref() == Some(owner) {
            return Ok(None);
        }
        let none = Vec::new();
        let mine = self.on.get(n).unwrap_or(&none);
        let written_to = addressed_to(e)?;
        let to_owner = match written_to {
            Some(list) => names(list, owner)?,
            None => false,
        };
        let mut addressed = to_owner;
        if !addressed {
            for act in mine {
                if act.act == "turn-addressed" && names(&act.about, owner)? {
                    addressed = true;
                    break;
                }
            }
        }
        if addressed || self.reacted.contains(n) || self.answered.contains(n) {
            return Ok(None);
        }
        if self.author_of(self.parent.get(n).map(String::as_str)) == Some(owner) {
            return Ok(None);
        }
        if mine.iter().any(|act| FORM_ACTS.contains(&act.act.as_str())) {
            return Ok(None);
        }
        let carried: Vec<&Py> = mine
            .iter()
            .filter(|act| act.act == "expectation-recorded")
            .map(|act| self.carriers.get(&act.id).unwrap_or(&NOBODY))
            .collect();
        if carried
            .iter()
            .any(|carrier| carrier.as_str() == Some(owner))
        {
            return Ok(None);
        }
        let mut results: Vec<Option<String>> = Vec::new();
        for act in mine {
            if act.act != "turn-said" {
                continue;
            }
            let Some(req) = detail_field(act, "answers_request")?.filter(|req| req.truthy()) else {
                continue;
            };
            let Some(req) = req.as_str() else {
                return Err(python_says("a request that isn't an id"));
            };
            let Some(r) = self.asked.get(req) else {
                return Ok(None); // an answer to the owner, or unknown
            };
            if r.actor.as_deref() == Some(owner) || self.author_of(r.turn.as_deref()) == Some(owner)
            {
                return Ok(None);
            }
            results.push(r.actor.clone());
        }
        if let Some(brief) = mine.iter().find(|act| act.act == "work-delegated") {
            let to = match detail_field(brief, "participant")? {
                None | Some(Py::None) => None,
                Some(Py::Str(who)) => Some(who.clone()),
                Some(_) => return Err(python_says("a delegation to something that isn't an id")),
            };
            return Ok(Some(Kind { kind: "brief", to }));
        }
        if let Some(first) = results.into_iter().next() {
            return Ok(Some(Kind {
                kind: "result",
                to: first,
            }));
        }
        if mine.iter().any(|act| act.act == "work-discovered") {
            return Ok(Some(Kind {
                kind: "finding",
                to: None,
            }));
        }
        let by_run = e
            .written_by
            .as_deref()
            .is_some_and(|written| !written.is_empty() && written != UNATTRIBUTED);
        if by_run
            && !self.parent.contains_key(n)
            && !written_to.is_some_and(Py::truthy)
            && !mine.iter().any(|act| act.act == "turn-addressed")
            && !carried.iter().any(|carrier| carrier.truthy())
        {
            return Ok(Some(Kind {
                kind: "follow-up",
                to: None,
            }));
        }
        Ok(None)
    }
}

/// `hidden`: agent work, and so is everything under it. A reply's `deleted` never reads true here, as
/// it never does in Python: `corpus.read` hands back the record's own row, which has no such field.
fn hidden(
    n: &str,
    path: &mut Vec<String>,
    kinds: &HashMap<String, Option<Kind>>,
    walk: &Walk,
    memo: &mut HashMap<String, bool>,
) -> bool {
    if let Some(known) = memo.get(n) {
        return *known;
    }
    let is_kind = kinds.get(n).is_some_and(Option::is_some);
    if !is_kind || walk.unread.contains(n) || path.iter().any(|on_path| on_path == n) {
        memo.insert(n.to_owned(), false);
        return false;
    }
    let mut out = true;
    path.push(n.to_owned());
    for child in walk.kids.get(n).map_or(&[][..], Vec::as_slice) {
        if !hidden(child, path, kinds, walk, memo) {
            out = false;
            break;
        }
    }
    path.pop();
    memo.insert(n.to_owned(), out);
    out
}

/// `classify(cv, pids, owner_of(cv))`: post -> `{"kind", "why", "to", "to_name"}`, or `None`.
pub fn classify(scope: &mut dyn ReadScope, pids: &[&str]) -> Result<HashMap<String, Py>, OpError> {
    let mut wanted: Vec<&str> = Vec::with_capacity(pids.len());
    for pid in pids {
        if !pid.is_empty() && !wanted.contains(pid) {
            wanted.push(pid);
        }
    }
    let unknown = || {
        wanted
            .iter()
            .map(|pid| ((*pid).to_owned(), Py::None))
            .collect()
    };
    if wanted.is_empty() {
        return Ok(unknown());
    }
    let Some(owner) = owner_of(scope)? else {
        return Ok(unknown());
    };

    let mut replies: HashMap<String, Vec<String>> = HashMap::new();
    let list = id_list(wanted.iter().copied());
    scope.query(WALK, &[Param::Text(&list)], &mut |row| {
        if let (Some(from), Some(to)) = (text(row, 0)?, text(row, 1)?) {
            replies.entry(to).or_default().push(from);
        }
        Ok(Flow::Continue)
    })?;
    let walk = levels(&wanted, &replies);

    let mut nodes: Vec<&str> = wanted.clone();
    nodes.extend(walk.kids.values().flatten().map(String::as_str));
    nodes.sort_unstable();
    nodes.dedup();
    let list = id_list(nodes.iter().copied());

    let mut entries = HashMap::with_capacity(nodes.len());
    let mut unread = false;
    scope.query(ENTRIES, &[Param::Text(&list)], &mut |row| {
        let Some(body) = text(row, 3)?.as_deref().and_then(pyjson::loads) else {
            unread = true;
            return Ok(Flow::Stop);
        };
        entries.insert(
            text(row, 0)?.unwrap_or_default(),
            Written {
                attributed_to: text(row, 1)?,
                written_by: text(row, 2)?,
                body,
            },
        );
        Ok(Flow::Continue)
    })?;
    if unread {
        return Err(python_says("a body this can't read"));
    }

    let on_nodes = acts(scope, ACTS_ON, &list)?;
    let mut on: HashMap<String, Vec<&Act>> = HashMap::new();
    for act in &on_nodes {
        if let Some(turn) = &act.turn {
            on.entry(turn.clone()).or_default().push(act);
        }
    }
    let exps: Vec<&Act> = on_nodes
        .iter()
        .filter(|act| act.act == "expectation-recorded")
        .collect();
    let carried = carriers(scope, &exps)?;

    let mut asked_ids: Vec<&str> = Vec::new();
    for act in on_nodes.iter().filter(|act| act.act == "turn-said") {
        if let Some(req) = detail_field(act, "answers_request")?.filter(|req| req.truthy()) {
            match req.as_str() {
                Some(req) => asked_ids.push(req),
                None => return Err(python_says("a request that isn't an id")),
            }
        }
    }
    asked_ids.sort_unstable();
    asked_ids.dedup();
    let asked: HashMap<String, Act> = if asked_ids.is_empty() {
        HashMap::new()
    } else {
        acts(scope, ACTS_BY_ID, &id_list(asked_ids.iter().copied()))?
            .into_iter()
            .map(|act| (act.id.clone(), act))
            .collect()
    };

    let parent = reads::first_to(&links_from(scope, REPLIES_TO, &nodes)?);
    let mut named: Vec<&str> = parent.values().map(String::as_str).collect();
    named.extend(asked.values().filter_map(|act| act.turn.as_deref()));
    let authors: HashMap<String, Option<String>> = reads::heads(scope, &named)?
        .into_iter()
        .map(|(id, head)| (id, head.attributed_to))
        .collect();

    // `{from: to}`: of a from with two, the last.
    let mut anchors: HashMap<String, String> = HashMap::new();
    for link in links_to(scope, ANCHORS_IN, &nodes)? {
        anchors.insert(link.from, link.to);
    }
    let anchored: Vec<&str> = anchors.keys().map(String::as_str).collect();
    let reacted: HashSet<String> = links_to(scope, REACTS_TO, &anchored)?
        .into_iter()
        .filter(|link| link.attributed_to.as_deref() == Some(owner.as_str()))
        .filter_map(|link| anchors.get(&link.to).cloned())
        .collect();
    let answered: HashSet<String> = links_to(scope, RESPONDS_TO, &nodes)?
        .into_iter()
        .map(|link| link.to)
        .collect();

    let facts = Facts {
        owner: &owner,
        entries,
        on,
        carriers: carried,
        asked,
        parent,
        authors,
        reacted,
        answered,
    };
    let mut kinds: HashMap<String, Option<Kind>> = HashMap::with_capacity(nodes.len());
    for n in &nodes {
        kinds.insert((*n).to_owned(), facts.base(n)?);
    }

    let mut memo = HashMap::new();
    let mut path = Vec::new();
    let shown: Vec<bool> = wanted
        .iter()
        .map(|n| hidden(n, &mut path, &kinds, &walk, &mut memo))
        .collect();

    let mut targets: Vec<Id> = Vec::new();
    for (n, is_hidden) in wanted.iter().zip(&shown) {
        if *is_hidden
            && let Some(Some(Kind { to: Some(to), .. })) = kinds.get(*n)
            && !to.is_empty()
        {
            targets.push(Id(to.clone()));
        }
    }
    targets.sort();
    targets.dedup();
    let aliases = mentis_rules::alias_reads(scope, &targets)?;

    let mut out = HashMap::with_capacity(wanted.len());
    for (n, is_hidden) in wanted.iter().zip(&shown) {
        let found = if *is_hidden {
            kinds.get(*n).and_then(Option::as_ref)
        } else {
            None
        };
        let Some(kind) = found else {
            out.insert((*n).to_owned(), Py::None);
            continue;
        };
        let to_name: Option<String> = match &kind.to {
            None => None,
            // `names.get(k["to"]) if k.get("to") else None`.
            Some(to) if to.is_empty() => None,
            Some(to) => match aliases.get(&Id(to.clone())) {
                Some(Some(Some(alias))) => Some(alias.clone()),
                Some(Some(None)) | None => Some(to.clone()),
                Some(None) => return Err(python_says("a body this can't read")),
            },
        };
        let shown_to = to_name.as_deref().filter(|name| !name.is_empty());
        let why = match kind.kind {
            "brief" => {
                shown_to.map_or("delegation brief".to_owned(), |to| format!("brief to {to}"))
            }
            "result" => shown_to.map_or("result to an agent".to_owned(), |to| {
                format!("result to {to}")
            }),
            "finding" => "finding".to_owned(),
            _ => "follow-up".to_owned(),
        };
        out.insert(
            (*n).to_owned(),
            dict([
                ("kind", Py::str(kind.kind)),
                ("why", Py::Str(why)),
                ("to", Py::opt_str(kind.to.as_deref())),
                ("to_name", Py::opt_str(to_name.as_deref())),
            ]),
        );
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn links(pairs: &[(&str, &str)]) -> HashMap<String, Vec<String>> {
        let mut out: HashMap<String, Vec<String>> = HashMap::new();
        for (parent, child) in pairs {
            out.entry((*parent).to_owned())
                .or_default()
                .push((*child).to_owned());
        }
        out
    }

    #[test]
    fn a_walk_stops_at_eight_levels_and_says_what_it_did_not_read() {
        let chain: Vec<(String, String)> = (0..10)
            .map(|n| (format!("n{n}"), format!("n{}", n + 1)))
            .collect();
        let pairs: Vec<(&str, &str)> = chain
            .iter()
            .map(|(a, b)| (a.as_str(), b.as_str()))
            .collect();
        let walk = levels(&["n0"], &links(&pairs));
        assert_eq!(walk.unread, HashSet::from(["n8".to_owned()]));
        assert!(walk.kids.contains_key("n7"));
        assert!(!walk.kids.contains_key("n8"));
    }

    #[test]
    fn a_cycle_does_not_walk_twice() {
        let walk = levels(&["a"], &links(&[("a", "b"), ("b", "a")]));
        assert!(walk.unread.is_empty());
        assert_eq!(walk.kids["a"], ["b"]);
        assert_eq!(walk.kids["b"], ["a"]);
    }

    #[test]
    fn hidden_needs_everything_under_it_to_be_agent_work() {
        let walk = levels(&["a"], &links(&[("a", "b")]));
        let work = || {
            Some(Kind {
                kind: "brief",
                to: None,
            })
        };
        let mut kinds: HashMap<String, Option<Kind>> = HashMap::new();
        kinds.insert("a".to_owned(), work());
        kinds.insert("b".to_owned(), work());
        assert!(hidden(
            "a",
            &mut Vec::new(),
            &kinds,
            &walk,
            &mut HashMap::new()
        ));
        kinds.insert("b".to_owned(), None);
        assert!(!hidden(
            "a",
            &mut Vec::new(),
            &kinds,
            &walk,
            &mut HashMap::new()
        ));
    }
}
