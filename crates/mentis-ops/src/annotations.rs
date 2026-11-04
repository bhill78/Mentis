//! A post's anchors, `anchored.of_post`: `anchors.anchors_on` with each anchor's reaction history
//! beside it, read for all the posts asked at once.
//!
//! **A reaction some other act superseded forwards.** Its `replaced_by` and `replaces` say who did
//! it and with what, and no record this was measured on holds one.

use std::collections::{HashMap, HashSet};

use mentis_record::{Flow, Id, Param, ReadScope};

use crate::lists::{loaded, not_owned};
use crate::pyjson::{Py, dict};
use crate::window::collections::PyRow;
use crate::window::reads;
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest};

const ANCHORS_IN: &str = "anchors-in";
const REACTS_TO: &str = "reacts-to";
const OPENED_FROM: &str = "opened-from";

const ENTRIES: &str = "SELECT id,family,def_name,attributed_to,recorded_at,link_relation,body \
 FROM entry WHERE id IN (SELECT value FROM json_each(?1))";
const CHANGES: &str = "SELECT actor,about FROM operational WHERE act='reaction-changed' \
 AND actor IN (SELECT value FROM json_each(?1)) ORDER BY seq";
const SUPERSEDING: &str = "SELECT link_from,link_to FROM entry WHERE link_relation=(SELECT def_name \
 FROM entry WHERE family='definition' AND json_extract(body,'$.substrate_role')='supersedes' ORDER BY seq LIMIT 1) \
 AND (link_from IN (SELECT value FROM json_each(?1)) OR link_to IN (SELECT value FROM json_each(?1)))";

#[derive(Clone, Debug)]
pub struct AnchorsArgs {
    pub posts: Vec<String>,
}
pub struct Anchors;

struct Held {
    family: String,
    kind: Option<String>,
    by: Option<String>,
    at: Py,
    is_link: bool,
    body: Py,
}

impl Held {
    fn is_node(&self, kind: &str) -> bool {
        self.family == "entry" && !self.is_link && self.kind.as_deref() == Some(kind)
    }
}

fn entries(scope: &mut dyn ReadScope, ids: &[&str]) -> Result<HashMap<String, Held>, OpError> {
    let mut out = HashMap::with_capacity(ids.len());
    if ids.is_empty() {
        return Ok(out);
    }
    let list = mentis_rules::id_list(ids.iter().copied());
    let mut unreadable = false;
    scope.query(ENTRIES, &[Param::Text(&list)], &mut |r| {
        let Some(body) = reads::text(r, 6)?.and_then(|b| crate::pyjson::loads(&b)) else {
            unreadable = true;
            return Ok(Flow::Stop);
        };
        out.insert(
            reads::text(r, 0)?.unwrap_or_default(),
            Held {
                family: reads::text(r, 1)?.unwrap_or_default(),
                kind: reads::text(r, 2)?,
                by: reads::text(r, 3)?,
                at: reads::number(r, 4)?,
                is_link: reads::text(r, 5)?.is_some(),
                body,
            },
        );
        Ok(Flow::Continue)
    })?;
    if unreadable {
        return Err(not_owned("an annotation body Python has to read"));
    }
    Ok(out)
}

fn as_index(value: Option<&Py>) -> Option<i128> {
    match value {
        Some(Py::Int(digits)) => digits.parse().ok(),
        _ => None,
    }
}

/// `graphemes.codepoint_to_utf16`.
fn utf16(chars: &[char], offset: usize) -> usize {
    chars[..offset].iter().map(|c| c.len_utf16()).sum()
}

/// A reaction's own line, by its reactor's own `reaction-changed` acts, held per actor in the order
/// `own_changes`' dict keeps: first insertion's place, the last value.
struct OwnChanges(Vec<(String, String)>);

impl OwnChanges {
    fn to(&self, old: &str) -> Option<&str> {
        self.0
            .iter()
            .find(|(from, _)| from == old)
            .map(|(_, to)| to.as_str())
    }

    fn line(&self, id: &str) -> Vec<String> {
        let mut line = vec![id.to_owned()];
        while let Some(next) = self.to(line.last().expect("never empty")) {
            if line.iter().any(|held| held == next) {
                break;
            }
            line.push(next.to_owned());
        }
        line
    }

    fn changes(&self, id: &str) -> Option<&str> {
        self.0
            .iter()
            .find(|(_, to)| to == id)
            .map(|(from, _)| from.as_str())
    }
}

fn own_changes(
    scope: &mut dyn ReadScope,
    actors: &[&str],
) -> Result<HashMap<String, OwnChanges>, OpError> {
    let mut out: HashMap<String, OwnChanges> = HashMap::new();
    if actors.is_empty() {
        return Ok(out);
    }
    let list = mentis_rules::id_list(actors.iter().copied());
    let mut unreadable = false;
    scope.query(CHANGES, &[Param::Text(&list)], &mut |r| {
        let actor = reads::text(r, 0)?.unwrap_or_default();
        let about = reads::text(r, 1)?.and_then(|a| crate::pyjson::loads(&a));
        let Some(Py::List(about)) = about else {
            unreadable = true;
            return Ok(Flow::Stop);
        };
        if about.len() >= 3 {
            let (Some(new), Some(old)) = (about[0].as_str(), about[2].as_str()) else {
                unreadable = true;
                return Ok(Flow::Stop);
            };
            let held = &mut out.entry(actor).or_insert_with(|| OwnChanges(Vec::new())).0;
            match held.iter_mut().find(|(from, _)| from == old) {
                Some(place) => place.1 = new.to_owned(),
                None => held.push((old.to_owned(), new.to_owned())),
            }
        }
        Ok(Flow::Continue)
    })?;
    if unreadable {
        return Err(not_owned("a reaction change Python has to read"));
    }
    Ok(out)
}

fn alias_map(
    scope: &mut dyn ReadScope,
    ids: Vec<String>,
) -> Result<HashMap<String, String>, OpError> {
    let asked: Vec<Id> = ids.into_iter().map(Id).collect();
    crate::lists::aliases_of(scope, &asked)
}

fn alias_or_id(aliases: &HashMap<String, String>, id: Option<&str>) -> Py {
    id.map_or(Py::None, |id| {
        Py::str(aliases.get(id).map_or(id, String::as_str))
    })
}

/// Everything one call needs, read once.
struct Read {
    roots: HashMap<String, String>,
    homes: HashMap<String, String>,
    entries: HashMap<String, Held>,
    now: HashMap<Id, mentis_rules::Reading>,
    reactions: HashMap<String, Vec<String>>,
    replies: HashMap<String, Vec<String>>,
    dives: HashMap<String, Vec<String>>,
    changes: HashMap<String, OwnChanges>,
    superseding: Vec<(String, String)>,
    aliases: HashMap<String, String>,
}

fn reading<'a>(read: &'a Read, id: &str) -> Result<&'a mentis_rules::Reading, OpError> {
    read.now
        .get(&Id(id.to_owned()))
        .filter(|r| !r.python_says)
        .ok_or_else(|| not_owned("an annotated entry Python has to present"))
}

/// `source_deletion`, and the current version and body of the anchor's Turn.
fn view(read: &Read, aid: &str) -> Result<Py, OpError> {
    let anchor = read
        .entries
        .get(aid)
        .filter(|a| a.is_node("anchor"))
        .ok_or_else(|| not_owned("an anchor Python refuses"))?;
    let sel = anchor
        .body
        .get("selector")
        .filter(|s| s.is_dict())
        .cloned()
        .unwrap_or_else(|| Py::Dict(vec![]));
    let root = read.roots.get(aid);
    let conv = root.and_then(|r| read.homes.get(r));
    let vid = sel
        .get("version")
        .and_then(Py::as_str)
        .filter(|v| !v.is_empty());
    let mut deleted = false;
    if let Some(root) = root {
        deleted |= reading(read, root)?.deleted.is_some();
    }
    let version = vid.and_then(|v| read.entries.get(v).map(|e| (v, e)));
    if let Some((v, held)) = version
        && held.family == "entry"
        && !held.is_link
    {
        if !held.is_node("contribution") {
            return Err(not_owned("an anchor on something other than a Turn"));
        }
        deleted |= reading(read, v)?.deleted.is_some();
    }
    let root_entry = root.and_then(|r| read.entries.get(r));
    let current = match root {
        Some(root) => {
            let now = reading(read, root)?;
            Some(
                now.revision
                    .as_ref()
                    .map_or(root.as_str(), |r| r.current.0.as_str()),
            )
        }
        None => None,
    };
    let mut out = dict([
        ("anchor", Py::str(aid)),
        ("selector", sel.clone()),
        ("turn", root.map_or(Py::None, Py::str)),
        ("conversation", conv.map_or(Py::None, Py::str)),
        ("by", anchor.by.as_deref().map_or(Py::None, Py::str)),
        ("at", anchor.at.clone()),
        (
            "author",
            root_entry
                .and_then(|e| e.by.as_deref())
                .map_or(Py::None, Py::str),
        ),
        ("deleted", Py::Bool(deleted)),
        (
            "version_is_current",
            Py::Bool(
                !deleted && current.is_some() && current == sel.get("version").and_then(Py::as_str),
            ),
        ),
        (
            "current_version",
            if deleted {
                Py::None
            } else {
                current.map_or(Py::None, Py::str)
            },
        ),
    ]);
    if deleted {
        out.set("excerpt", Py::None);
        out.set(
            "excerpt_withheld",
            Py::str("the anchored material was deleted; its words are not shown"),
        );
        return Ok(out);
    }
    let unresolvable = |mut out: Py, why: &str| {
        out.set("excerpt", Py::None);
        out.set("unresolvable", Py::str(why));
        Ok(out)
    };
    let Some((v, held)) = version.filter(|(_, h)| h.family == "entry" && !h.is_link) else {
        return unresolvable(out, "the record holds no version this anchor names");
    };
    if sel.get("type").and_then(Py::as_str) != Some("text-range") {
        out.set("excerpt", Py::None);
        return Ok(out);
    }
    let parts = held
        .body
        .get("parts")
        .filter(|p| p.truthy())
        .map_or(Some(&[][..]), Py::as_list)
        .ok_or_else(|| not_owned("parts that aren't a list"))?;
    let part = as_index(sel.get("part"))
        .filter(|p| *p >= 0 && (*p as usize) < parts.len())
        .map(|p| &parts[p as usize])
        .filter(|p| p.is_dict() && p.get("type").and_then(Py::as_str) == Some("text"));
    let Some(part) = part else {
        return unresolvable(out, "that version has no such text part");
    };
    let words = match part.get("text") {
        None | Some(Py::None) => "",
        Some(text) => text
            .as_str()
            .ok_or_else(|| not_owned("a part's text that isn't text"))?,
    };
    let chars: Vec<char> = words.chars().collect();
    let range = match (as_index(sel.get("start")), as_index(sel.get("end"))) {
        (Some(start), Some(end)) if 0 <= start && start < end && end <= chars.len() as i128 => {
            Some((start as usize, end as usize))
        }
        _ => None,
    };
    let Some((start, end)) = range else {
        return unresolvable(out, "that text part has no such range");
    };
    let excerpt: String = chars[start..end].iter().collect();
    out.set("excerpt", Py::str(&excerpt));
    out.set(
        "utf16",
        dict([
            ("start", Py::int(utf16(&chars, start))),
            ("end", Py::int(utf16(&chars, end))),
        ]),
    );
    if let Some(root) = root
        && current.is_some_and(|c| c != v)
    {
        let now = loaded(&reading(read, root)?.body_json)?;
        let mut whole = String::new();
        let parts = now
            .get("parts")
            .and_then(Py::as_list)
            .ok_or_else(|| not_owned("parts Python raises on"))?;
        for part in parts {
            if !part.is_dict() {
                return Err(not_owned("a part that isn't an object"));
            }
            if part.get("type").and_then(Py::as_str) == Some("text") {
                match part.get("text") {
                    None | Some(Py::None) => {}
                    Some(text) => whole.push_str(
                        text.as_str()
                            .ok_or_else(|| not_owned("a part's text that isn't text"))?,
                    ),
                }
            }
        }
        out.set(
            "likeness_in_current",
            dict([
                (
                    "occurrences",
                    Py::int(whole.matches(excerpt.as_str()).count()),
                ),
                ("is_identity", Py::Bool(false)),
            ]),
        );
    }
    Ok(out)
}

/// `interactions`: `(current, every reaction in time order)`.
fn reaction_rows(read: &Read, aid: &str) -> Result<(Vec<Py>, Vec<Py>), OpError> {
    let mut rows: Vec<(f64, Py)> = Vec::new();
    for rid in read.reactions.get(aid).map_or(&[][..], Vec::as_slice) {
        let held = read
            .entries
            .get(rid)
            .ok_or_else(|| not_owned("a reaction link to nothing"))?;
        let by = held.by.as_deref();
        let now = reading(read, rid)?;
        let deletion = now.deleted.as_ref();
        let deleted_by = deletion.and_then(|d| d.by.as_ref()).map(|d| d.0.as_str());
        let withdrawn = deletion.is_some() && deleted_by == by;
        let by_other = deletion.is_some() && !withdrawn;
        let mine = by.and_then(|by| read.changes.get(by));
        let line = mine.map_or_else(|| vec![rid.clone()], |m| m.line(rid));
        let changed_to = line.get(1).map(String::as_str);
        let changes = mine.and_then(|m| m.changes(rid));
        // Anything else that supersedes it is `replaced_by`/`replaces`: Python says who did it.
        let deletion_id = deletion.map(|d| d.record.0.as_str());
        for (from, to) in &read.superseding {
            let other_later = to == rid
                && Some(from.as_str()) != deletion_id
                && Some(from.as_str()) != changed_to;
            let other_earlier = from == rid && Some(to.as_str()) != changes;
            if other_later || other_earlier {
                return Err(not_owned("a reaction another act superseded"));
            }
        }
        let mut in_withdrawn_line = false;
        for member in &line {
            let d = reading(read, member)?.deleted.as_ref();
            if d.is_some_and(|d| d.by.as_ref().map(|b| b.0.as_str()) == by) {
                in_withdrawn_line = true;
            }
        }
        let current = deletion.is_none() && changed_to.is_none();
        let token = if by_other {
            Py::None
        } else {
            held.body.get("token").cloned().unwrap_or(Py::None)
        };
        let by_alias = alias_or_id(&read.aliases, by);
        let mut row = dict([
            ("reaction", Py::str(rid)),
            ("token", token),
            ("by", by.map_or(Py::None, Py::str)),
            ("by_alias", by_alias.clone()),
            ("at", held.at.clone()),
            ("changes", changes.map_or(Py::None, Py::str)),
            ("changed_to", changed_to.map_or(Py::None, Py::str)),
            ("withdrawn", Py::Bool(withdrawn)),
            ("in_withdrawn_line", Py::Bool(in_withdrawn_line)),
            ("deleted", Py::Bool(deletion.is_some())),
            ("replaced_by", Py::List(vec![])),
            ("replaces", Py::List(vec![])),
            ("current", Py::Bool(current)),
        ]);
        if let Some(d) = deletion {
            let alias = alias_or_id(&read.aliases, deleted_by);
            row.set("deletion", Py::str(&d.record.0));
            row.set("deleted_by", deleted_by.map_or(Py::None, Py::str));
            row.set("deleted_by_alias", alias.clone());
            row.set("deleted_at", Py::Float(d.at));
            if by_other {
                let (Some(who), Some(whom)) = (by_alias.as_str(), alias.as_str()) else {
                    return Err(not_owned("a reaction Python has to word"));
                };
                row.set(
                    "token_withheld",
                    Py::str(format!(
                        "a reaction by {who} was deleted by {whom}; its token is not shown"
                    )),
                );
            }
        }
        rows.push((reads::as_f64(&held.at), row));
    }
    rows.sort_by(|a, b| a.0.total_cmp(&b.0));
    let mut counted: Vec<(String, usize)> = Vec::new();
    for (_, row) in &rows {
        if matches!(row.get("current"), Some(Py::Bool(true))) {
            let token = row
                .get("token")
                .and_then(Py::as_str)
                .ok_or_else(|| not_owned("a reaction token that isn't text"))?;
            match counted.iter_mut().find(|held| held.0 == token) {
                Some(held) => held.1 += 1,
                None => counted.push((token.to_owned(), 1)),
            }
        }
    }
    let current = counted
        .into_iter()
        .map(|(token, count)| dict([("token", Py::str(token)), ("count", Py::int(count))]))
        .collect();
    Ok((current, rows.into_iter().map(|row| row.1).collect()))
}

/// Whether a reply's parts, as it now reads or else as it was written, name this anchor.
fn reply_names(read: &Read, reply: &str, aid: &str) -> Result<bool, OpError> {
    let Some(held) = read.entries.get(reply) else {
        return Ok(false);
    };
    let now = loaded(&reading(read, reply)?.body_json)?;
    let parts = now
        .get("parts")
        .filter(|p| p.truthy())
        .or_else(|| held.body.get("parts"))
        .filter(|p| p.truthy());
    let Some(parts) = parts else {
        return Ok(false);
    };
    let parts = parts
        .as_list()
        .ok_or_else(|| not_owned("parts that aren't a list"))?;
    Ok(parts.iter().any(|p| {
        p.is_dict()
            && p.get("type").and_then(Py::as_str) == Some("anchor")
            && p.get("ref").and_then(Py::as_str) == Some(aid)
    }))
}

fn anchor_row(read: &Read, aid: &str) -> Result<Py, OpError> {
    let mut out = view(read, aid)?;
    let (current, history) = reaction_rows(read, aid)?;
    let mut replies = Vec::new();
    if let Some(root) = read.roots.get(aid) {
        for reply in read.replies.get(root).map_or(&[][..], Vec::as_slice) {
            if reply_names(read, reply, aid)? {
                replies.push(Py::str(reply));
            }
        }
    }
    let dives = read
        .dives
        .get(aid)
        .map_or(&[][..], Vec::as_slice)
        .iter()
        .map(Py::str)
        .collect();
    out.set("reactions", Py::List(current));
    out.set("replies", Py::List(replies));
    out.set("deep_dives", Py::List(dives));
    out.set("history", Py::List(history));
    Ok(out)
}

impl ReadOp for Anchors {
    type Args = AnchorsArgs;
    type Row = PyRow;
    const NAME: &'static str = "anchors";
    const BUDGET: Budget = Budget {
        statements: 16 + mentis_rules::STATEMENTS * 4,
    };
    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let as_of = scope.position();
        let asked: Vec<&str> = request.args.posts.iter().map(String::as_str).collect();
        let asked_ids: Vec<Id> = asked.iter().map(|id| Id((*id).to_owned())).collect();
        let heads = reads::heads(scope, &asked)?;
        let lines = mentis_rules::roots(scope, &asked_ids)?;
        let is_post = |id: &str| {
            heads.get(id).is_some_and(|h| h.is_post())
                && lines.get(&Id(id.to_owned())).is_some_and(|r| r.0 == id)
        };
        let posts: Vec<&str> = asked.iter().copied().filter(|id| is_post(id)).collect();

        let on_posts = reads::links_to(scope, ANCHORS_IN, &posts)?;
        let mut anchors_of: HashMap<&str, Vec<&str>> = HashMap::new();
        for link in &on_posts {
            anchors_of
                .entry(link.to.as_str())
                .or_default()
                .push(link.from.as_str());
        }
        let aids: Vec<&str> = on_posts.iter().map(|l| l.from.as_str()).collect();
        let roots = reads::first_to(&reads::links_from(scope, ANCHORS_IN, &aids)?);
        let root_ids: Vec<&str> = roots.values().map(String::as_str).collect();
        let homes = reads::homes_of(scope, &root_ids)?;

        let reacting = reads::links_to(scope, REACTS_TO, &aids)?;
        let mut reactions: HashMap<String, Vec<String>> = HashMap::new();
        for link in &reacting {
            reactions
                .entry(link.to.clone())
                .or_default()
                .push(link.from.clone());
        }
        let reaction_ids: Vec<&str> = reacting.iter().map(|l| l.from.as_str()).collect();
        let replying = reads::links_to(scope, reads::REPLIES_TO, &root_ids)?;
        let mut replies: HashMap<String, Vec<String>> = HashMap::new();
        for link in &replying {
            replies
                .entry(link.to.clone())
                .or_default()
                .push(link.from.clone());
        }
        let opened = reads::links_to(scope, OPENED_FROM, &aids)?;
        let mut dives: HashMap<String, Vec<String>> = HashMap::new();
        for link in &opened {
            dives
                .entry(link.to.clone())
                .or_default()
                .push(link.from.clone());
        }

        let mut first: Vec<&str> = aids.clone();
        first.extend(reaction_ids.iter().copied());
        first.extend(root_ids.iter().copied());
        first.extend(replying.iter().map(|l| l.from.as_str()));
        let mut held = entries(scope, &first)?;

        let versions: Vec<String> = aids
            .iter()
            .filter_map(|aid| held.get(*aid))
            .filter_map(|a| a.body.get("selector"))
            .filter_map(|s| s.get("version"))
            .filter_map(Py::as_str)
            .map(str::to_owned)
            .collect();
        let version_refs: Vec<&str> = versions.iter().map(String::as_str).collect();
        held.extend(entries(scope, &version_refs)?);

        let actors: Vec<String> = reaction_ids
            .iter()
            .filter_map(|id| held.get(*id))
            .filter_map(|r| r.by.clone())
            .collect::<HashSet<_>>()
            .into_iter()
            .collect();
        let actor_refs: Vec<&str> = actors.iter().map(String::as_str).collect();
        let changes = own_changes(scope, &actor_refs)?;

        let mut wanted: HashSet<String> = HashSet::new();
        wanted.extend(root_ids.iter().map(|id| (*id).to_owned()));
        wanted.extend(
            versions
                .iter()
                .filter(|v| {
                    held.get(*v)
                        .is_some_and(|e| e.family == "entry" && !e.is_link)
                })
                .cloned(),
        );
        wanted.extend(reaction_ids.iter().map(|id| (*id).to_owned()));
        wanted.extend(replying.iter().map(|l| l.from.clone()));
        for own in changes.values() {
            for (old, new) in &own.0 {
                wanted.insert(old.clone());
                wanted.insert(new.clone());
            }
        }
        let wanted: Vec<Id> = wanted.into_iter().map(Id).collect();
        let now = mentis_rules::now_reads(scope, &wanted)?;

        let mut superseding = Vec::new();
        if !reaction_ids.is_empty() {
            let list = mentis_rules::id_list(reaction_ids.iter().copied());
            scope.query(SUPERSEDING, &[Param::Text(&list)], &mut |r| {
                superseding.push((
                    reads::text(r, 0)?.unwrap_or_default(),
                    reads::text(r, 1)?.unwrap_or_default(),
                ));
                Ok(Flow::Continue)
            })?;
        }
        let mut people = actors;
        people.extend(
            reaction_ids
                .iter()
                .filter_map(|id| now.get(&Id((*id).to_owned())))
                .filter_map(|r| r.deleted.as_ref())
                .filter_map(|d| d.by.as_ref().map(|b| b.0.clone())),
        );
        let aliases = alias_map(scope, people)?;

        let read = Read {
            roots,
            homes,
            entries: held,
            now,
            reactions,
            replies,
            dives,
            changes,
            superseding,
            aliases,
        };
        let mut shown = Vec::with_capacity(posts.len());
        let mut missing = Vec::new();
        for id in &asked {
            if !is_post(id) {
                missing.push(Py::str(*id));
                continue;
            }
            let mut rows = Vec::new();
            for aid in anchors_of.get(id).map_or(&[][..], Vec::as_slice) {
                rows.push(anchor_row(&read, aid)?);
            }
            shown.push(((*id).to_owned(), Py::List(rows)));
        }
        Ok(ReadAnswer {
            rows: vec![PyRow(dict([
                ("posts", Py::Dict(shown)),
                ("missing", Py::List(missing)),
            ]))],
            as_of,
            more: None,
            not_searched: vec![],
        })
    }
}
