//! R4.1's durable lists: both participant lists, the stream and selection, Latest, and the three
//! forms of the Conversation list. HTTP query parsing stays in `mentis-server`.
//!
//! **What isn't plainly the same forwards.** A value Python would show some way these reads can't
//! say, a body it would raise on, or words whose `repr` isn't plain is [`OpError::NotOwned`].

use std::collections::{HashMap, HashSet};

use mentis_record::{Flow, Id, Param, ReadScope};

use crate::overlay::{LiveWorkers, OpenRun, Overlay};
use crate::pyjson::{Py, dict};
use crate::window::collections::PyRow;
use crate::window::reads;
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest, python};

/// `f"{words}{raw!r}"` at the door, or Python's to say where that `repr` isn't plain.
pub(crate) fn refused(words: &str, raw: &str) -> OpError {
    match python::repr(raw) {
        Some(quoted) => OpError::BadRequest {
            why: format!("{words}{quoted}"),
        },
        None => not_owned("words whose repr Python has to give"),
    }
}

pub(crate) fn not_owned(why: &str) -> OpError {
    OpError::NotOwned { why: why.into() }
}

pub(crate) fn loaded(body: &str) -> Result<Py, OpError> {
    crate::pyjson::loads(body).ok_or_else(|| not_owned("a body Python has to read"))
}

/// `versions.flow_text`: text parts and the characters of inline references, in order.
pub(crate) fn flow_text(body: &Py) -> Result<String, OpError> {
    let mut words = String::new();
    let Some(parts) = body.get("parts").filter(|parts| parts.truthy()) else {
        return Ok(words);
    };
    let Some(parts) = parts.as_list() else {
        return Err(not_owned("parts that aren't a list"));
    };
    for part in parts {
        if !part.is_dict() {
            return Err(not_owned("a part that isn't an object"));
        }
        let kind = part.get("type").and_then(Py::as_str);
        if matches!(
            kind,
            Some("text" | "topic" | "turn" | "conversation" | "acquired" | "object")
        ) {
            match part.get("text") {
                None | Some(Py::None) => {}
                Some(text) if !text.truthy() && text.as_str().is_none() => {}
                Some(text) => words.push_str(
                    text.as_str()
                        .ok_or_else(|| not_owned("a part's text that isn't text"))?,
                ),
            }
        }
    }
    Ok(words)
}

/// `Conversations.alias` of these, where it says more than the reference it was given.
pub(crate) fn aliases_of(
    scope: &mut dyn ReadScope,
    ids: &[Id],
) -> Result<HashMap<String, String>, OpError> {
    let mut names = HashMap::with_capacity(ids.len());
    for (id, name) in mentis_rules::alias_reads(scope, ids)? {
        match name {
            None => return Err(not_owned("a body Python has to read")),
            Some(Some(alias)) if !alias.is_empty() => {
                names.insert(id.0, alias);
            }
            Some(_) => {}
        }
    }
    Ok(names)
}

/// `text[:159].rstrip() + "…"` past 160 characters.
pub(crate) fn cut_160(text: String) -> String {
    if text.chars().count() <= 160 {
        return text;
    }
    let cut: String = text.chars().take(159).collect();
    let mut cut = cut.trim_end_matches(python::is_space).to_owned();
    cut.push('\u{2026}');
    cut
}

// -- participants ---------------------------------------------------------------------------------

const PARTICIPANTS: &str = "SELECT e.id, e.body, \
       EXISTS(SELECT 1 FROM entry t WHERE t.link_to=e.id AND t.link_relation=(SELECT def_name FROM entry \
         WHERE family='definition' AND json_extract(body,'$.substrate_role')='supersedes' ORDER BY seq LIMIT 1)) \
     FROM entry e WHERE +e.family='entry' AND e.def_name='participant' AND e.link_relation IS NULL \
     AND NOT EXISTS (SELECT 1 FROM entry v WHERE v.link_from=e.id AND v.link_relation=(SELECT def_name \
       FROM entry WHERE family='definition' AND json_extract(body,'$.substrate_role')='supersedes' \
       ORDER BY seq LIMIT 1)) ORDER BY +e.seq";
const PARTICIPANT_CONVERSATIONS: &str = "SELECT link_from,link_to FROM entry WHERE link_relation='participates-in' \
 AND link_from IN (SELECT value FROM json_each(?1)) ORDER BY seq";
/// `_last_runtime`: of each one's newest 24 acts, the newest that says both. 24 rows each, through
/// the actor index, however many acts somebody has.
const LAST_RUNTIMES: &str = "SELECT w.value,(SELECT runtime FROM (SELECT runtime,execution,seq FROM operational o \
 WHERE o.actor=w.value ORDER BY o.seq DESC LIMIT 24) WHERE execution IS NOT NULL AND execution<>'' AND runtime IS NOT NULL \
 AND runtime<>'' ORDER BY seq DESC LIMIT 1) FROM json_each(?1) w";
const PARTICIPANT_LINKS: &str = "SELECT id,link_from,link_to,link_relation,recorded_at FROM entry WHERE \
 link_from IN (SELECT value FROM json_each(?1)) AND link_relation IN ('pictured-by','designated-as') ORDER BY +seq";
/// `intake_designations`: of anybody, listed or not. A relation alone has no index.
const INTAKE_LINKS: &str = "SELECT id,link_from,link_to,link_relation,recorded_at FROM entry WHERE \
 link_relation='carries-intake' ORDER BY seq";
const RUNTIME_DEFAULTS: &str = "SELECT id,body,recorded_at FROM entry WHERE +family='entry' \
 AND def_name='runtime-default' AND link_relation IS NULL ORDER BY +seq";

#[derive(Clone, Debug, Default)]
pub struct ParticipantsArgs {
    pub q: Option<String>,
    pub runtimes: bool,
    pub api: bool,
}

/// The durable participant palette shared by both participant routes. `window` is what says whether
/// a picture's bytes are still held; without one, a list that shows a picture forwards.
pub struct Participants<'w> {
    pub window: Option<&'w crate::window::Window>,
}

pub(crate) struct RuntimeDefault {
    pub(crate) declaration: String,
    pub(crate) runtime: Py,
    at: f64,
}

/// `runtime_defaults_now`.
pub(crate) fn runtime_defaults(
    scope: &mut dyn ReadScope,
) -> Result<HashMap<String, RuntimeDefault>, OpError> {
    let mut declarations = Vec::new();
    let mut unreadable = false;
    scope.query(RUNTIME_DEFAULTS, &[], &mut |r| {
        let id = reads::text(r, 0)?.unwrap_or_default();
        let Some(body) = reads::text(r, 1)?.and_then(|v| crate::pyjson::loads(&v)) else {
            unreadable = true;
            return Ok(Flow::Stop);
        };
        declarations.push((Id(id), body, reads::as_f64(&reads::number(r, 2)?)));
        Ok(Flow::Continue)
    })?;
    if unreadable {
        return Err(not_owned("a runtime declaration Python has to read"));
    }
    let standing = mentis_rules::standing_many(
        scope,
        &declarations.iter().map(|d| d.0.clone()).collect::<Vec<_>>(),
        None,
    )?;
    let mut defaults: HashMap<String, RuntimeDefault> = HashMap::new();
    for (id, body, at) in declarations {
        if !standing.get(&id).is_some_and(|s| s.stands) {
            continue;
        }
        let Some(participant) = body.get("participant").and_then(Py::as_str) else {
            return Err(not_owned("a runtime declaration Python has to read"));
        };
        let runtime = body.get("runtime").cloned().unwrap_or(Py::None);
        if defaults.get(participant).is_none_or(|old| old.at < at) {
            defaults.insert(
                participant.to_owned(),
                RuntimeDefault {
                    declaration: id.0,
                    runtime,
                    at,
                },
            );
        }
    }
    Ok(defaults)
}

impl ReadOp for Participants<'_> {
    type Args = ParticipantsArgs;
    type Row = PyRow;
    const NAME: &'static str = "participants";
    const BUDGET: Budget = Budget {
        statements: 6 + crate::window::objects::DESCRIBE_STATEMENTS + mentis_rules::STATEMENTS * 4,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let as_of = scope.position();
        let args = &request.args;
        let mut held = Vec::new();
        scope.query(PARTICIPANTS, &[], &mut |row| {
            held.push((
                reads::text(row, 0)?.unwrap_or_default(),
                reads::text(row, 1)?.unwrap_or_default(),
                row.value(2)?.integer() == Some(1),
            ));
            Ok(Flow::Continue)
        })?;
        let touched: Vec<Id> = held
            .iter()
            .filter(|row| row.2)
            .map(|row| Id(row.0.clone()))
            .collect();
        let now = mentis_rules::now_reads(scope, &touched)?;
        let want = python::lower(python::strip(args.q.as_deref().unwrap_or("")))
            .ok_or_else(|| not_owned("a search whose case Python has to fold"))?;
        let want = want.trim_start_matches('@');
        let mut rows = Vec::new();
        for (id, stored, renamed) in held {
            let body = if renamed {
                let reading = now
                    .get(&Id(id.clone()))
                    .ok_or_else(|| not_owned("a participant the record didn't give back"))?;
                if reading.python_says || reading.deleted.is_some() {
                    return Err(not_owned("a participant Python has to present"));
                }
                loaded(&reading.body_json)?
            } else {
                loaded(&stored)?
            };
            if !body.is_dict() {
                return Err(not_owned("a participant Python has to present"));
            }
            let alias = body.get("alias").cloned();
            let about = body.get("about").cloned();
            if args.api && (alias.is_none() || about.is_none()) {
                return Err(not_owned("a participant Python raises on"));
            }
            let alias = alias.unwrap_or(Py::None);
            let about = about.unwrap_or(Py::None);
            if !want.is_empty() {
                if args.api && alias.as_str().is_none() {
                    return Err(not_owned("an alias Python raises on"));
                }
                let words = if alias.truthy() {
                    alias
                        .as_str()
                        .ok_or_else(|| not_owned("an alias that isn't text"))?
                } else {
                    ""
                };
                let folded =
                    python::lower(words).ok_or_else(|| not_owned("an alias Python folds"))?;
                if !folded.trim_start_matches('@').contains(want) {
                    continue;
                }
            }
            rows.push((id, alias, about));
        }
        let matched = rows.len();
        let limit = request.limit.unwrap_or(u32::MAX) as usize;
        rows.truncate(limit);
        let answer = if args.api {
            api_participants(scope, self.window, rows, matched)?
        } else {
            let declared = if args.runtimes && !rows.is_empty() {
                runtime_defaults(scope)?
            } else {
                HashMap::new()
            };
            let shown = rows
                .into_iter()
                .map(|(id, alias, about)| {
                    let mut row = dict([("id", Py::str(&id)), ("alias", alias), ("about", about)]);
                    if args.runtimes {
                        let d = declared.get(&id);
                        row.set("default_runtime", d.map_or(Py::None, |d| d.runtime.clone()));
                        row.set("runtime_mode", Py::str(runtime_mode(d)));
                    }
                    row
                })
                .collect();
            let owner = crate::window::classify::owner_of(scope)?;
            dict([
                ("participants", Py::List(shown)),
                ("matched", Py::int(matched)),
                ("limit", Py::int(limit)),
                ("me", owner.map_or(Py::None, Py::Str)),
            ])
        };
        Ok(ReadAnswer {
            rows: vec![PyRow(answer)],
            as_of,
            more: None,
            not_searched: vec![],
        })
    }
}

pub(crate) fn runtime_mode(declared: Option<&RuntimeDefault>) -> &'static str {
    match declared {
        None => "undeclared",
        Some(d) if d.runtime.truthy() => "default",
        Some(_) => "auto",
    }
}

fn api_participants(
    scope: &mut dyn ReadScope,
    window: Option<&crate::window::Window>,
    rows: Vec<(String, Py, Py)>,
    matched: usize,
) -> Result<Py, OpError> {
    struct PLink {
        id: Id,
        from: String,
        to: String,
        relation: String,
        at: f64,
    }
    let list = mentis_rules::id_list(rows.iter().map(|r| r.0.as_str()));
    let mut conversations: HashMap<String, Vec<String>> = HashMap::new();
    scope.query(PARTICIPANT_CONVERSATIONS, &[Param::Text(&list)], &mut |r| {
        let p = reads::text(r, 0)?.unwrap_or_default();
        let c = reads::text(r, 1)?.unwrap_or_default();
        let xs = conversations.entry(p).or_default();
        if !xs.contains(&c) {
            xs.push(c)
        }
        Ok(Flow::Continue)
    })?;
    conversations.values_mut().for_each(|rows| rows.sort());
    let mut last_runtime = HashMap::new();
    scope.query(LAST_RUNTIMES, &[Param::Text(&list)], &mut |r| {
        if let (Some(p), Some(rt)) = (reads::text(r, 0)?, reads::text(r, 1)?) {
            last_runtime.entry(p).or_insert(rt);
        }
        Ok(Flow::Continue)
    })?;
    let mut links = Vec::new();
    for (sql, params) in [
        (PARTICIPANT_LINKS, vec![Param::Text(&list)]),
        (INTAKE_LINKS, vec![]),
    ] {
        scope.query(sql, &params, &mut |r| {
            links.push(PLink {
                id: Id(reads::text(r, 0)?.unwrap_or_default()),
                from: reads::text(r, 1)?.unwrap_or_default(),
                to: reads::text(r, 2)?.unwrap_or_default(),
                relation: reads::text(r, 3)?.unwrap_or_default(),
                at: reads::as_f64(&reads::number(r, 4)?),
            });
            Ok(Flow::Continue)
        })?;
    }
    let standing = mentis_rules::standing_many(
        scope,
        &links.iter().map(|l| l.id.clone()).collect::<Vec<_>>(),
        None,
    )?;
    let mut direct: HashMap<String, Vec<&PLink>> = HashMap::new();
    let mut intake = Vec::new();
    // `avatar_of`: of those that stand, the latest, the first of equals.
    let mut pictured: HashMap<&str, &PLink> = HashMap::new();
    for l in &links {
        if !standing.get(&l.id).is_some_and(|s| s.stands) {
            continue;
        }
        match l.relation.as_str() {
            "pictured-by" => {
                if pictured
                    .get(l.from.as_str())
                    .is_none_or(|held| held.at < l.at)
                {
                    pictured.insert(&l.from, l);
                }
            }
            "designated-as" => direct.entry(l.from.clone()).or_default().push(l),
            "carries-intake" => intake.push(l),
            _ => {}
        }
    }
    let intake = (intake.len() == 1).then(|| intake[0]);
    let persona_ids: Vec<Id> = links
        .iter()
        .filter(|l| l.relation == "designated-as" || l.relation == "carries-intake")
        .map(|l| Id(l.to.clone()))
        .collect();
    let personas = mentis_rules::now_reads(scope, &persona_ids)?;
    let persona_standing = mentis_rules::standing_many(scope, &persona_ids, None)?;
    let defaults = runtime_defaults(scope)?;
    let held = if pictured.is_empty() {
        HashSet::new()
    } else {
        let window = window.ok_or_else(|| not_owned("a picture with nothing to look for it"))?;
        let refs: Vec<&str> = pictured.values().map(|l| l.to.as_str()).collect();
        crate::window::objects::held_refs(window, scope, &refs)?
    };
    let mut shown = Vec::with_capacity(rows.len());
    for (id, alias, about) in rows {
        let declared = defaults.get(&id);
        const SEVERAL: &str = "several designations stand at once; which one \
             applies is a decision only a person can make";
        const UNHONOURED: &str = "the designated Persona is not established, or has been \
             superseded, so the designation cannot be honoured as it was made";
        let stands = |l: &PLink| {
            persona_standing
                .get(&Id(l.to.clone()))
                .is_some_and(|s| s.stands)
        };
        // `designated_persona`: the Participant's own, else the intake it alone carries.
        let (resolved, persona, source, why) = match direct.get(&id).map_or(&[][..], Vec::as_slice)
        {
            [_, _, ..] => (false, None, Some("designation"), Some(SEVERAL)),
            [one] if stands(one) => (true, Some(one.to.clone()), Some("designation"), None),
            [_] => (false, None, Some("designation"), Some(UNHONOURED)),
            [] => match intake.filter(|l| l.from == id && stands(l)) {
                Some(l) => (true, Some(l.to.clone()), Some("intake"), None),
                None => (
                    false,
                    None,
                    None,
                    Some("no Persona is designated for this Participant"),
                ),
            },
        };
        let name = match persona.as_ref().and_then(|p| personas.get(&Id(p.clone()))) {
            Some(reading) if reading.python_says => {
                return Err(not_owned("a Persona Python has to present"));
            }
            Some(reading) => loaded(&reading.body_json)?.get("name").cloned(),
            None => None,
        };
        let avatar = pictured
            .get(id.as_str())
            .filter(|l| held.contains(&l.to))
            .map_or(Py::None, |l| Py::str(&l.to));
        let mut out = vec![
            ("participant".to_owned(), Py::str(&id)),
            ("alias".into(), alias),
            ("about".into(), about),
            (
                "conversations".into(),
                Py::List(
                    conversations
                        .remove(&id)
                        .unwrap_or_default()
                        .into_iter()
                        .map(Py::str)
                        .collect(),
                ),
            ),
            ("avatar".into(), avatar),
            (
                "runtime".into(),
                last_runtime.remove(&id).map_or(Py::None, Py::Str),
            ),
            (
                "default_runtime".into(),
                declared.map_or(Py::None, |d| d.runtime.clone()),
            ),
            ("runtime_mode".into(), Py::str(runtime_mode(declared))),
        ];
        if let Some(d) = declared {
            out.push(("runtime_declaration".into(), Py::str(&d.declaration)));
        }
        out.push((
            "designated_persona".into(),
            dict([
                ("resolved", Py::Bool(resolved)),
                ("persona", persona.map_or(Py::None, Py::Str)),
                ("name", name.unwrap_or(Py::None)),
                ("source", source.map_or(Py::None, Py::str)),
                ("why", why.map_or(Py::None, Py::str)),
            ]),
        ));
        shown.push(Py::Dict(out));
    }
    Ok(dict([
        ("participants", Py::List(shown)),
        ("matched", Py::int(matched)),
    ]))
}

// -- the stream and a selection -------------------------------------------------------------------

/// `store.stream_page`: the primary key walked from the cursor, `limit + 1` rows. `(SELECT beyond)`
/// says whether any post lies on the other side of the cursor.
const STREAM_NEWEST: &str = "SELECT e.id, e.seq, e.recorded_at, \
       (SELECT h.link_to FROM entry h WHERE h.link_from=e.id AND h.link_relation='in-conversation' ORDER BY h.seq LIMIT 1), 0 \
     FROM entry e WHERE +e.def_name='contribution' AND +e.family='entry' AND e.link_relation IS NULL \
       AND EXISTS (SELECT 1 FROM entry h WHERE h.link_from=e.id AND h.link_relation='in-conversation') \
     ORDER BY e.seq DESC LIMIT ?1";
const STREAM_BEFORE: &str = "SELECT e.id, e.seq, e.recorded_at, \
       (SELECT h.link_to FROM entry h WHERE h.link_from=e.id AND h.link_relation='in-conversation' ORDER BY h.seq LIMIT 1), \
       (SELECT EXISTS (SELECT 1 FROM entry x WHERE x.seq>=?2 AND +x.def_name='contribution' AND +x.family='entry' \
          AND x.link_relation IS NULL AND EXISTS (SELECT 1 FROM entry h WHERE h.link_from=x.id AND h.link_relation='in-conversation') ORDER BY x.seq)) \
     FROM entry e WHERE +e.def_name='contribution' AND +e.family='entry' AND e.link_relation IS NULL \
       AND EXISTS (SELECT 1 FROM entry h WHERE h.link_from=e.id AND h.link_relation='in-conversation') \
       AND e.seq<?2 ORDER BY e.seq DESC LIMIT ?1";
const STREAM_AFTER: &str = "SELECT e.id, e.seq, e.recorded_at, \
       (SELECT h.link_to FROM entry h WHERE h.link_from=e.id AND h.link_relation='in-conversation' ORDER BY h.seq LIMIT 1), \
       (SELECT EXISTS (SELECT 1 FROM entry x WHERE x.seq<=?2 AND +x.def_name='contribution' AND +x.family='entry' \
          AND x.link_relation IS NULL AND EXISTS (SELECT 1 FROM entry h WHERE h.link_from=x.id AND h.link_relation='in-conversation') ORDER BY x.seq DESC)) \
     FROM entry e WHERE +e.def_name='contribution' AND +e.family='entry' AND e.link_relation IS NULL \
       AND EXISTS (SELECT 1 FROM entry h WHERE h.link_from=e.id AND h.link_relation='in-conversation') \
       AND e.seq>?2 ORDER BY e.seq ASC LIMIT ?1";

#[derive(Clone, Debug, Default)]
pub struct StreamArgs {
    pub before: Option<String>,
    pub after: Option<String>,
    pub start: Option<String>,
}

pub struct Stream;

/// `_page_key`'s seq. Only the seq moves a stream page, and a cursor's time is only checked.
fn page_seq(scope: &mut dyn ReadScope, raw: &str) -> Result<i64, OpError> {
    if raw.starts_with("ent-") || raw.starts_with("adm-") {
        let heads = reads::heads(scope, &[raw])?;
        return match heads.get(raw) {
            Some(head) => Ok(head.seq),
            None => Err(refused("no such entry to page from: ", raw)),
        };
    }
    let Some((at, seq)) = raw.rsplit_once('_') else {
        return Err(refused("not a paging cursor: ", raw));
    };
    let plain = |digits: &str| !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit());
    let time = at
        .split_once('.')
        .map_or(plain(at), |(whole, part)| plain(whole) && plain(part));
    if !time || !plain(seq) {
        // `float` and `int` read a good deal more than these, and Python says which.
        return Err(not_owned("a cursor Python has to read"));
    }
    seq.parse()
        .map_err(|_| not_owned("a cursor Python has to read"))
}

impl ReadOp for Stream {
    type Args = StreamArgs;
    type Row = PyRow;
    const NAME: &'static str = "collections/stream";
    const BUDGET: Budget = Budget { statements: 3 };
    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let args = &request.args;
        let given = [&args.before, &args.after, &args.start]
            .into_iter()
            .flatten()
            .count();
        if given > 1 {
            return Err(OpError::BadRequest {
                why: "page before a position, after it or from it -- one".into(),
            });
        }
        let as_of = scope.position();
        let (before, after) = match (&args.before, &args.after, &args.start) {
            (Some(raw), _, _) => (Some(page_seq(scope, raw)?), None),
            (_, Some(raw), _) => (None, Some(page_seq(scope, raw)?)),
            (_, _, Some(raw)) if raw == "start" => (None, Some(0)),
            (_, _, Some(raw)) => (None, Some(page_seq(scope, raw)? - 1)),
            _ => (None, None),
        };
        let limit = i64::from(request.limit.unwrap_or(50));
        let mut rows = Vec::new();
        let mut beyond = false;
        let wanted = Param::Integer(limit + 1);
        let (sql, params) = match (before, after) {
            (Some(edge), _) => (STREAM_BEFORE, vec![wanted, Param::Integer(edge)]),
            (_, Some(edge)) => (STREAM_AFTER, vec![wanted, Param::Integer(edge)]),
            _ => (STREAM_NEWEST, vec![wanted]),
        };
        scope.query(sql, &params, &mut |row| {
            beyond = row.value(4)?.integer() == Some(1);
            rows.push((
                reads::text(row, 0)?.unwrap_or_default(),
                row.value(1)?.integer().unwrap_or_default(),
                reads::number(row, 2)?,
                reads::text(row, 3)?,
            ));
            Ok(Flow::Continue)
        })?;
        let more = rows.len() as i64 > limit;
        rows.truncate(limit as usize);
        if after.is_some() {
            rows.reverse();
        }
        let (older, newer) = if after.is_some() {
            (beyond, more)
        } else {
            (more, beyond)
        };
        let edge = |row: Option<&(String, i64, Py, Option<String>)>| {
            row.map_or(Py::None, |r| Py::str(reads::page_cursor(&r.2, r.1)))
        };
        let items = rows
            .iter()
            .map(|r| {
                dict([
                    ("id", Py::str(&r.0)),
                    ("home", r.3.as_deref().map_or(Py::None, Py::str)),
                    ("at", r.2.clone()),
                ])
            })
            .collect();
        Ok(ReadAnswer {
            rows: vec![PyRow(dict([
                ("key", Py::str("stream")),
                ("items", Py::List(items)),
                ("before", if older { edge(rows.last()) } else { Py::None }),
                ("after", if newer { edge(rows.first()) } else { Py::None }),
                ("limit", Py::int(limit)),
            ]))],
            as_of,
            more: None,
            not_searched: vec![],
        })
    }
}

#[derive(Clone, Debug)]
pub struct SelectionArgs {
    pub ids: Vec<String>,
}
pub struct Selection;

impl ReadOp for Selection {
    type Args = SelectionArgs;
    type Row = PyRow;
    const NAME: &'static str = "collections/selection";
    const BUDGET: Budget = Budget { statements: 3 };
    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let as_of = scope.position();
        let refs: Vec<&str> = request.args.ids.iter().map(String::as_str).collect();
        let heads = reads::heads(scope, &refs)?;
        let posts: Vec<&str> = refs
            .iter()
            .copied()
            .filter(|id| heads.get(*id).is_some_and(|h| h.is_post()))
            .collect();
        let homes = reads::homes_of(scope, &posts)?;
        let mut known: Vec<&str> = refs
            .iter()
            .copied()
            .filter(|id| homes.contains_key(*id))
            .collect();
        known.sort_by_key(|id| heads.get(*id).map_or(0, |h| h.seq));
        let known_set: HashSet<&str> = known.iter().copied().collect();
        let mut items: Vec<Py> = known
            .into_iter()
            .map(|id| {
                dict([
                    ("id", Py::str(id)),
                    ("home", Py::str(&homes[id])),
                    ("known", Py::Bool(true)),
                ])
            })
            .collect();
        items.extend(
            refs.iter()
                .copied()
                .filter(|id| !known_set.contains(id))
                .map(|id| {
                    dict([
                        ("id", Py::str(id)),
                        ("home", Py::None),
                        ("known", Py::Bool(false)),
                    ])
                }),
        );
        Ok(ReadAnswer {
            rows: vec![PyRow(dict([
                ("key", Py::str("selection")),
                ("items", Py::List(items)),
            ]))],
            as_of,
            more: None,
            not_searched: vec![],
        })
    }
}

// -- latest ---------------------------------------------------------------------------------------

const LATEST_ALL: &str = "WITH RECURSIVE page(id,seq,at,author,home,parent) AS ( \
 SELECT e.id,e.seq,e.recorded_at,e.attributed_to, \
 (SELECT h.link_to FROM entry h WHERE h.link_from=e.id AND h.link_relation='in-conversation' ORDER BY h.seq LIMIT 1), \
 (SELECT r.link_to FROM entry r WHERE r.link_from=e.id AND r.link_relation='replies-to' ORDER BY r.seq LIMIT 1) \
 FROM entry e WHERE +e.def_name='contribution' AND +e.family='entry' AND e.link_relation IS NULL \
 AND e.seq < ?1 AND EXISTS(SELECT 1 FROM entry h WHERE h.link_from=e.id AND h.link_relation='in-conversation') \
 ORDER BY e.seq DESC LIMIT ?2), up(start,node,depth) AS (SELECT id,parent,1 FROM page WHERE parent IS NOT NULL \
 UNION SELECT up.start,(SELECT r.link_to FROM entry r WHERE r.link_from=up.node AND r.link_relation='replies-to' ORDER BY r.seq LIMIT 1),up.depth+1 \
 FROM up WHERE up.node IS NOT NULL AND up.depth<64), top(start,root,depth) AS \
 (SELECT start,node,MAX(depth) FROM up WHERE node IS NOT NULL GROUP BY start) \
 SELECT p.id,p.seq,p.at,p.author,p.home,p.parent,t.root FROM page p LEFT JOIN top t ON t.start=p.id ORDER BY p.seq DESC";
const LATEST_ONE: &str = "WITH RECURSIVE page(id,seq,at,author,home,parent) AS ( \
 SELECT e.id,e.seq,e.recorded_at,e.attributed_to, \
 (SELECT h.link_to FROM entry h WHERE h.link_from=e.id AND h.link_relation='in-conversation' ORDER BY h.seq LIMIT 1), \
 (SELECT r.link_to FROM entry r WHERE r.link_from=e.id AND r.link_relation='replies-to' ORDER BY r.seq LIMIT 1) \
 FROM entry l JOIN entry e ON e.id=l.link_from WHERE +e.def_name='contribution' AND +e.family='entry' AND e.link_relation IS NULL \
 AND e.seq < ?1 AND l.link_to=?3 AND l.link_relation='in-conversation' \
 AND l.seq=(SELECT MIN(x.seq) FROM entry x WHERE x.link_from=e.id AND x.link_relation='in-conversation') \
 ORDER BY e.seq DESC LIMIT ?2), up(start,node,depth) AS (SELECT id,parent,1 FROM page WHERE parent IS NOT NULL \
 UNION SELECT up.start,(SELECT r.link_to FROM entry r WHERE r.link_from=up.node AND r.link_relation='replies-to' ORDER BY r.seq LIMIT 1),up.depth+1 \
 FROM up WHERE up.node IS NOT NULL AND up.depth<64), top(start,root,depth) AS \
 (SELECT start,node,MAX(depth) FROM up WHERE node IS NOT NULL GROUP BY start) \
 SELECT p.id,p.seq,p.at,p.author,p.home,p.parent,t.root FROM page p LEFT JOIN top t ON t.start=p.id ORDER BY p.seq DESC";

#[derive(Clone, Debug, Default)]
pub struct LatestArgs {
    pub conversation: Option<String>,
    pub agent_work: bool,
}
pub struct Latest;

#[derive(Clone)]
struct LatestRow {
    id: String,
    seq: i64,
    at: Py,
    author: Option<String>,
    home: Option<String>,
    parent: Option<String>,
    root: Option<String>,
}

fn latest_page(
    scope: &mut dyn ReadScope,
    conversation: Option<&str>,
    before: i64,
    limit: usize,
) -> Result<Vec<LatestRow>, OpError> {
    let mut rows = Vec::new();
    let mut params = vec![Param::Integer(before), Param::Integer(limit as i64)];
    if let Some(id) = conversation {
        params.push(Param::Text(id));
    }
    scope.query(
        if conversation.is_some() {
            LATEST_ONE
        } else {
            LATEST_ALL
        },
        &params,
        &mut |row| {
            rows.push(LatestRow {
                id: reads::text(row, 0)?.unwrap_or_default(),
                seq: row.value(1)?.integer().unwrap_or_default(),
                at: reads::number(row, 2)?,
                author: reads::text(row, 3)?,
                home: reads::text(row, 4)?,
                parent: reads::text(row, 5)?,
                root: reads::text(row, 6)?,
            });
            Ok(Flow::Continue)
        },
    )?;
    Ok(rows)
}

fn excerpt(body: &Py) -> Result<String, OpError> {
    let words = flow_text(body)?;
    Ok(cut_160(python::words(&words).collect::<Vec<_>>().join(" ")))
}

/// `latest._why`.
fn why(kind: Option<&Py>) -> Py {
    match kind.filter(|kind| kind.truthy()) {
        Some(kind) => dict([
            ("kind", kind.get("kind").cloned().unwrap_or(Py::None)),
            ("why", kind.get("why").cloned().unwrap_or(Py::None)),
        ]),
        None => Py::None,
    }
}

impl ReadOp for Latest {
    type Args = LatestArgs;
    type Row = PyRow;
    const NAME: &'static str = "latest";
    const BUDGET: Budget = Budget {
        statements: 4 * (1 + crate::window::classify::STATEMENTS)
            + mentis_rules::STATEMENTS * 2
            + 4,
    };
    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let as_of = scope.position();
        let limit = request.limit.unwrap_or(10) as usize;
        let conversation = request.args.conversation.as_deref();
        if let Some(id) = conversation {
            let heads = reads::heads(scope, &[id])?;
            if !heads.get(id).is_some_and(|h| {
                h.family == "entry" && !h.is_link && h.kind.as_deref() == Some("conversation")
            }) {
                return Err(refused("not a conversation: ", id));
            }
        }
        const END: i64 = 1 << 62;
        let mut kept = Vec::new();
        let mut work = HashMap::new();
        let mut scanned = 0usize;
        let mut hidden = 0usize;
        if request.args.agent_work {
            kept = latest_page(scope, conversation, END, limit)?;
            let ids: Vec<&str> = kept.iter().map(|r| r.id.as_str()).collect();
            work = crate::window::classify::classify(scope, &ids)?;
            scanned = kept.len();
        } else {
            let chunk = (limit * 4).clamp(40, 400);
            let mut before = END;
            for _ in 0..4 {
                let want = chunk.min(400 - scanned);
                if want == 0 {
                    break;
                }
                let rows = latest_page(scope, conversation, before, want)?;
                if rows.is_empty() {
                    break;
                }
                let ids: Vec<&str> = rows.iter().map(|r| r.id.as_str()).collect();
                let classified = crate::window::classify::classify(scope, &ids)?;
                for row in &rows {
                    scanned += 1;
                    if classified.get(&row.id).is_some_and(Py::truthy) {
                        hidden += 1;
                        continue;
                    }
                    kept.push(row.clone());
                    if kept.len() >= limit {
                        break;
                    }
                }
                if kept.len() >= limit || rows.len() < want {
                    break;
                }
                before = rows.last().map_or(before, |r| r.seq);
            }
        }
        let ids: Vec<Id> = kept.iter().map(|r| Id(r.id.clone())).collect();
        let now = mentis_rules::now_reads(scope, &ids)?;
        let homes: HashMap<String, String> = kept
            .iter()
            .filter_map(|r| r.home.as_ref().map(|h| (r.id.clone(), h.clone())))
            .collect();
        let parent_ids: Vec<&str> = kept.iter().filter_map(|r| r.parent.as_deref()).collect();
        let parent_homes = reads::homes_of(scope, &parent_ids)?;
        let mut numbered = parent_homes.clone();
        numbered.extend(homes.clone());
        let numbers = reads::numbers_of(scope, &numbered)?;
        let mut named: Vec<&str> = homes.values().map(String::as_str).collect();
        named.extend(kept.iter().filter_map(|r| r.author.as_deref()));
        let names = reads::names_of(scope, &named)?;
        let mut items = Vec::new();
        for r in &kept {
            let reading = now
                .get(&Id(r.id.clone()))
                .filter(|reading| !reading.python_says)
                .ok_or_else(|| not_owned("a post Python has to present"))?;
            let deleted = reading.deleted.is_some();
            let mut fields = vec![
                ("id".to_owned(), Py::str(&r.id)),
                (
                    "conversation".into(),
                    r.home.as_deref().map_or(Py::None, Py::str),
                ),
                (
                    "conversation_name".into(),
                    r.home
                        .as_deref()
                        .map(|h| Py::str(names.get(h).map_or(h, String::as_str)))
                        .unwrap_or(Py::None),
                ),
                (
                    "number".into(),
                    numbers.get(&r.id).map_or(Py::None, |n| Py::int(*n)),
                ),
                (
                    "reply_to".into(),
                    r.parent.as_deref().map_or(Py::None, Py::str),
                ),
                (
                    "reply_to_number".into(),
                    r.parent
                        .as_ref()
                        .and_then(|p| numbers.get(p))
                        .map_or(Py::None, |n| Py::int(*n)),
                ),
                ("root".into(), Py::str(r.root.as_deref().unwrap_or(&r.id))),
                (
                    "author".into(),
                    r.author.as_deref().map_or(Py::None, Py::str),
                ),
                (
                    "author_alias".into(),
                    r.author
                        .as_deref()
                        .map(|a| Py::str(names.get(a).map_or(a, String::as_str)))
                        .unwrap_or(Py::None),
                ),
                ("at".into(), r.at.clone()),
                (
                    "excerpt".into(),
                    if deleted {
                        Py::None
                    } else {
                        Py::Str(excerpt(&loaded(&reading.body_json)?)?)
                    },
                ),
                ("deleted".into(), Py::Bool(deleted)),
            ];
            if request.args.agent_work {
                fields.push(("agent_work".into(), why(work.get(&r.id))));
            }
            items.push(Py::Dict(fields));
        }
        let count = if request.args.agent_work {
            kept.iter()
                .filter(|r| work.get(&r.id).is_some_and(Py::truthy))
                .count()
        } else {
            0
        };
        Ok(ReadAnswer {
            rows: vec![PyRow(dict([
                (
                    "key",
                    conversation
                        .map_or_else(|| Py::str("latest"), |c| Py::str(format!("latest:{c}"))),
                ),
                ("conversation", conversation.map_or(Py::None, Py::str)),
                ("items", Py::List(items)),
                ("limit", Py::int(limit)),
                ("agent_work", Py::Bool(request.args.agent_work)),
                ("scanned", Py::int(scanned)),
                ("hidden", Py::int(hidden)),
                ("agent_work_count", Py::int(count)),
            ]))],
            as_of,
            more: None,
            not_searched: vec![],
        })
    }
}

// -- the Conversation lists -----------------------------------------------------------------------

/// `all_conversations`' ids: not a rename's later version.
const ALL_CONVERSATIONS: &str = "SELECT e.id,e.recorded_at FROM entry e WHERE +e.family='entry' \
 AND e.def_name='conversation' AND e.link_relation IS NULL AND NOT EXISTS(SELECT 1 FROM entry v \
 WHERE v.link_from=e.id AND v.link_relation=(SELECT def_name FROM entry WHERE family='definition' \
 AND json_extract(body,'$.substrate_role')='supersedes' ORDER BY seq LIMIT 1)) ORDER BY +e.seq";
/// The same, of these ids.
const THESE_CONVERSATIONS: &str = "SELECT e.id,e.recorded_at FROM entry e WHERE +e.family='entry' \
 AND +e.def_name='conversation' AND e.link_relation IS NULL AND e.id IN (SELECT value FROM json_each(?1)) \
 AND NOT EXISTS(SELECT 1 FROM entry v WHERE v.link_from=e.id AND v.link_relation=(SELECT def_name FROM entry \
 WHERE family='definition' AND json_extract(body,'$.substrate_role')='supersedes' ORDER BY seq LIMIT 1)) ORDER BY +e.seq";
/// `store.activity_page`. `?2` -1 is every Conversation, which the search over the list reads.
const ACTIVITY_PAGE: &str = "WITH ends(r) AS (SELECT def_name FROM entry WHERE family='definition' \
   AND json_extract(body,'$.substrate_role')='supersedes' ORDER BY seq LIMIT 1), \
 nodes AS (SELECT id,seq,recorded_at FROM entry v WHERE def_name='conversation' AND +family='entry' \
   AND link_relation IS NULL AND NOT EXISTS (SELECT 1 FROM entry s WHERE s.link_from=v.id AND s.link_relation=(SELECT r FROM ends))), \
 posted AS (SELECT l.link_to AS id,MAX(e.recorded_at) AS t FROM nodes n JOIN entry l ON l.link_to=n.id \
   AND l.link_relation='in-conversation' JOIN entry e ON e.id=l.link_from WHERE e.def_name='contribution' \
   AND e.family='entry' AND e.link_relation IS NULL GROUP BY l.link_to), \
 included AS (SELECT l.link_to AS id,MAX(l.recorded_at) AS t FROM nodes n JOIN entry l ON l.link_to=n.id \
   AND l.link_relation='linked-into' WHERE NOT EXISTS (SELECT 1 FROM entry s WHERE s.link_to=l.id \
   AND s.link_relation=(SELECT r FROM ends)) GROUP BY l.link_to), \
 ranked AS (SELECT n.id,ROW_NUMBER() OVER (ORDER BY MAX(COALESCE(p.t,i.t,n.recorded_at),COALESCE(i.t,p.t,n.recorded_at)) DESC,n.seq DESC) pos, \
   COUNT(*) OVER () total FROM nodes n LEFT JOIN posted p ON p.id=n.id LEFT JOIN included i ON i.id=n.id) \
 SELECT id,total FROM ranked WHERE pos>COALESCE((SELECT pos FROM ranked WHERE id=?1),0) ORDER BY pos LIMIT ?2";
/// `Conversations.conversation_states`' acts: where a Conversation is listed, in write order, so
/// the last one per Conversation stands. `?1` names the Conversations; the other reads the Brain's.
const STATE_ACTS_OF: &str = "SELECT conversation,act,at,actor,seq FROM operational \
 WHERE conversation IN (SELECT value FROM json_each(?1)) AND act IN ('conversation-archived',\
 'conversation-restored','conversation-trashed','conversation-unarchived') ORDER BY seq";
const STATE_ACTS_ALL: &str = "SELECT conversation,act,at,actor,seq FROM operational \
 WHERE act IN ('conversation-archived','conversation-restored','conversation-trashed',\
 'conversation-unarchived') ORDER BY seq";
/// The relations each row counts, read once for all of them.
const CONVERSATION_FACTS: &str = "WITH wanted(id) AS (SELECT value FROM json_each(?1)), \
 home AS (SELECT l.link_to id,COUNT(DISTINCT e.id) posts,MAX(e.recorded_at) last FROM entry l JOIN entry e ON e.id=l.link_from \
 WHERE l.link_relation='in-conversation' AND l.link_to IN wanted AND e.family='entry' AND e.def_name='contribution' AND e.link_relation IS NULL GROUP BY l.link_to), \
 linked AS (SELECT l.link_to id,COUNT(*) n,MAX(l.recorded_at) last FROM entry l WHERE l.link_relation='linked-into' AND l.link_to IN wanted \
 AND NOT EXISTS(SELECT 1 FROM entry x WHERE x.link_to=l.id AND x.link_relation=(SELECT def_name FROM entry WHERE family='definition' AND json_extract(body,'$.substrate_role')='supersedes' ORDER BY seq LIMIT 1)) GROUP BY l.link_to), \
 people AS (SELECT link_to id,COUNT(DISTINCT link_from) n FROM entry WHERE link_relation='participates-in' AND link_to IN wanted GROUP BY link_to), \
 provisional AS (SELECT conversation id,1 yes FROM operational WHERE act='conversation-named-provisionally' AND conversation IN wanted GROUP BY conversation), \
 renamed AS (SELECT link_to id,1 yes FROM entry WHERE link_to IN wanted AND link_relation=(SELECT def_name FROM entry WHERE family='definition' AND json_extract(body,'$.substrate_role')='supersedes' ORDER BY seq LIMIT 1) GROUP BY link_to) \
 SELECT w.id,COALESCE(h.posts,0),h.last,COALESCE(l.n,0),l.last,COALESCE(p.n,0),COALESCE(v.yes,0),COALESCE(r.yes,0) FROM wanted w \
 LEFT JOIN home h ON h.id=w.id LEFT JOIN linked l ON l.id=w.id LEFT JOIN people p ON p.id=w.id LEFT JOIN provisional v ON v.id=w.id LEFT JOIN renamed r ON r.id=w.id";
const TOPICS_FOR: &str = "SELECT l.link_to,l.link_from FROM entry l WHERE l.link_relation='topic-of' \
 AND l.link_to IN (SELECT value FROM json_each(?1)) ORDER BY l.seq";
const TOPIC_COUNTS: &str = "SELECT l.link_to,COUNT(DISTINCT l.link_from) FROM entry l WHERE l.link_relation='about-topic' \
 AND l.link_to IN (SELECT value FROM json_each(?1)) AND NOT EXISTS(SELECT 1 FROM entry x WHERE x.link_to=l.id \
 AND x.link_relation=(SELECT def_name FROM entry WHERE family='definition' AND json_extract(body,'$.substrate_role')='supersedes' ORDER BY seq LIMIT 1)) GROUP BY l.link_to";
/// Each Turn at home in these, with who it addressed, and whether anything supersedes it.
const CONVERSATION_TURNS: &str = "SELECT DISTINCT h.link_to,e.id,json_extract(e.body,'$.addressed_to'),EXISTS(SELECT 1 FROM entry x WHERE x.link_to=e.id \
 AND x.link_relation=(SELECT def_name FROM entry WHERE family='definition' AND json_extract(body,'$.substrate_role')='supersedes' ORDER BY seq LIMIT 1)) \
 FROM entry h JOIN entry e ON e.id=h.link_from \
 WHERE h.link_relation='in-conversation' AND h.link_to IN (SELECT value FROM json_each(?1)) \
 AND e.family='entry' AND e.def_name='contribution' AND e.link_relation IS NULL";
const TURN_OBSERVATIONS: &str = "SELECT l.link_to,o.body FROM entry l JOIN entry o ON o.id=l.link_from \
 WHERE l.link_relation='observes' AND o.def_name='observation' AND o.family='entry' AND l.link_to IN (SELECT value FROM json_each(?1)) ORDER BY l.seq";
const RUN_MARKS: &str = "SELECT seq,id,act,execution,caused_by FROM operational \
 WHERE act IN ('execution-started','result-returned','delivery-failed','result-recovered') ORDER BY seq";
const OPEN_STARTS: &str = "SELECT id,actor,conversation,turn,at FROM operational \
 WHERE id IN (SELECT value FROM json_each(?1)) ORDER BY seq";

#[derive(Clone)]
pub enum ConversationMode {
    Api,
    Ids(Vec<String>),
    Activity {
        after: Option<String>,
        q: Option<String>,
        /// `state=`: `active`, `archived` or `trashed`, checked at the door. `None` lists all.
        state: Option<ListState>,
    },
}

/// `read.LIST_STATES`: where a Conversation is listed.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ListState {
    Active,
    Archived,
    Trashed,
}

impl ListState {
    /// `state=`'s words, or `None` for words that aren't one.
    pub fn named(words: &str) -> Option<ListState> {
        match words {
            "active" => Some(ListState::Active),
            "archived" => Some(ListState::Archived),
            "trashed" => Some(ListState::Trashed),
            _ => None,
        }
    }
    fn word(self) -> &'static str {
        match self {
            ListState::Active => "active",
            ListState::Archived => "archived",
            ListState::Trashed => "trashed",
        }
    }
}

/// One Conversation's latest state act: `_states_of`'s `{state, at, by}`, and its `seq`.
#[derive(Clone, Debug)]
struct Away {
    state: &'static str,
    at: Py,
    by: Py,
    /// The act's place in the record's append order (`operational_order`).
    seq: Py,
}

/// `Conversations._states_of(keep_active=True)` over the acts `sql` reads: each Conversation's
/// latest state act, whatever it left. The lists' filter keeps only the archived and trashed.
fn states(
    scope: &mut dyn ReadScope,
    sql: &'static str,
    params: &[Param<'_>],
) -> Result<HashMap<String, Away>, OpError> {
    let mut latest: HashMap<String, Away> = HashMap::new();
    scope.query(sql, params, &mut |r| {
        let Some(conversation) = reads::text(r, 0)?.filter(|c| !c.is_empty()) else {
            return Ok(Flow::Continue);
        };
        let state = match reads::text(r, 1)?.as_deref() {
            Some("conversation-archived") => "archived",
            Some("conversation-trashed") => "trashed",
            _ => "active",
        };
        latest.insert(
            conversation,
            Away {
                state,
                at: reads::number(r, 2)?,
                by: reads::text(r, 3)?.map_or(Py::None, Py::str),
                seq: r.value(4)?.integer().map_or(Py::None, Py::int),
            },
        );
        Ok(Flow::Continue)
    })?;
    Ok(latest)
}

/// These Conversations' states: one statement, none for none.
fn states_of(scope: &mut dyn ReadScope, ids: &[String]) -> Result<HashMap<String, Away>, OpError> {
    if ids.is_empty() {
        return Ok(HashMap::new());
    }
    let list = mentis_rules::id_list(ids.iter().map(String::as_str));
    states(scope, STATE_ACTS_OF, &[Param::Text(&list)])
}

/// A row's `state`, `state_at`, `state_by`, `state_seq`, as `_conversation_rows` sets them.
fn set_state(row: &mut Py, away: Option<&Away>) {
    match away {
        Some(a) => {
            row.set("state", Py::str(a.state));
            row.set("state_at", a.at.clone());
            row.set("state_by", a.by.clone());
            row.set("state_seq", a.seq.clone());
        }
        None => {
            row.set("state", Py::str("active"));
            row.set("state_at", Py::None);
            row.set("state_by", Py::None);
            row.set("state_seq", Py::None);
        }
    }
}
#[derive(Clone)]
pub struct ConversationsArgs {
    pub mode: ConversationMode,
    pub overlay: Overlay,
}
pub struct Conversations;

#[derive(Default, Clone)]
struct Facts {
    posts: i64,
    home_last: Option<Py>,
    included: i64,
    linked_last: Option<Py>,
    participants: i64,
    provisional: bool,
}

/// `_conversation_rows`' `max` of what isn't falsy, or `None`.
fn last_activity(f: &Facts) -> Py {
    [f.home_last.as_ref(), f.linked_last.as_ref()]
        .into_iter()
        .flatten()
        .filter(|t| t.truthy())
        .fold(None::<&Py>, |best, t| match best {
            Some(held) if reads::as_f64(held) >= reads::as_f64(t) => Some(held),
            _ => Some(t),
        })
        .cloned()
        .unwrap_or(Py::None)
}

fn conversation_facts(
    scope: &mut dyn ReadScope,
    list: &str,
) -> Result<HashMap<String, Facts>, OpError> {
    let mut facts = HashMap::new();
    let moment =
        |row: &dyn mentis_record::Row, column| -> Result<Option<Py>, mentis_record::RecordError> {
            Ok(match row.value(column)? {
                mentis_record::Value::Null => None,
                _ => Some(reads::number(row, column)?),
            })
        };
    scope.query(CONVERSATION_FACTS, &[Param::Text(list)], &mut |r| {
        facts.insert(
            reads::text(r, 0)?.unwrap_or_default(),
            Facts {
                posts: r.value(1)?.integer().unwrap_or_default(),
                home_last: moment(r, 2)?,
                included: r.value(3)?.integer().unwrap_or_default(),
                linked_last: moment(r, 4)?,
                participants: r.value(5)?.integer().unwrap_or_default(),
                provisional: r.value(6)?.integer() == Some(1) && r.value(7)?.integer() != Some(1),
            },
        );
        Ok(Flow::Continue)
    })?;
    Ok(facts)
}

/// Each Conversation's Topics under their current names, each with its Turn count.
fn conversation_topics(
    scope: &mut dyn ReadScope,
    list: &str,
) -> Result<HashMap<String, Vec<Py>>, OpError> {
    let mut pairs = Vec::new();
    scope.query(TOPICS_FOR, &[Param::Text(list)], &mut |r| {
        pairs.push((
            reads::text(r, 0)?.unwrap_or_default(),
            reads::text(r, 1)?.unwrap_or_default(),
        ));
        Ok(Flow::Continue)
    })?;
    let ids: Vec<Id> = pairs.iter().map(|x| Id(x.1.clone())).collect();
    let now = mentis_rules::now_reads(scope, &ids)?;
    let names = mentis_rules::id_list(ids.iter().map(|x| x.0.as_str()));
    let mut counts = HashMap::new();
    scope.query(TOPIC_COUNTS, &[Param::Text(&names)], &mut |r| {
        counts.insert(
            reads::text(r, 0)?.unwrap_or_default(),
            r.value(1)?.integer().unwrap_or_default(),
        );
        Ok(Flow::Continue)
    })?;
    let mut topics: HashMap<String, Vec<Py>> = HashMap::new();
    for (conversation, topic) in pairs {
        let Some(reading) = now.get(&Id(topic.clone())) else {
            continue;
        };
        if reading.python_says {
            return Err(not_owned("a Topic Python has to present"));
        }
        let name = loaded(&reading.body_json)?
            .get("name")
            .cloned()
            .ok_or_else(|| not_owned("a Topic Python raises on"))?;
        topics.entry(conversation).or_default().push(dict([
            ("id", Py::str(&topic)),
            ("name", name),
            ("turns", Py::int(*counts.get(&topic).unwrap_or(&0))),
        ]));
    }
    Ok(topics)
}

/// `_conversation_summaries`' `awaiting`, for every Conversation at once.
fn awaiting(scope: &mut dyn ReadScope, list: &str) -> Result<HashMap<String, usize>, OpError> {
    struct Turn {
        conversation: String,
        id: String,
        addressed: Option<String>,
        touched: bool,
    }
    let mut turns = Vec::new();
    scope.query(CONVERSATION_TURNS, &[Param::Text(list)], &mut |r| {
        turns.push(Turn {
            conversation: reads::text(r, 0)?.unwrap_or_default(),
            id: reads::text(r, 1)?.unwrap_or_default(),
            addressed: reads::text(r, 2)?,
            touched: r.value(3)?.integer() == Some(1),
        });
        Ok(Flow::Continue)
    })?;
    let touched: Vec<Id> = turns
        .iter()
        .filter(|t| t.touched)
        .map(|t| Id(t.id.clone()))
        .collect();
    let now = mentis_rules::now_reads(scope, &touched)?;
    // Only a Turn that addressed somebody asks anything further of the record.
    let mut owed: Vec<(&str, &str, Vec<String>)> = Vec::new();
    for turn in &turns {
        let addressed = if turn.touched {
            let reading = now
                .get(&Id(turn.id.clone()))
                .filter(|r| !r.python_says)
                .ok_or_else(|| not_owned("a Turn Python has to present"))?;
            loaded(&reading.body_json)?
                .get("addressed_to")
                .cloned()
                .ok_or_else(|| not_owned("a Turn Python raises on"))?
        } else {
            let Some(text) = turn.addressed.as_deref() else {
                return Err(not_owned("a Turn Python raises on"));
            };
            loaded(text)?
        };
        let list = addressed
            .as_list()
            .ok_or_else(|| not_owned("an addressing that isn't a list"))?;
        if list.is_empty() {
            continue;
        }
        let mut names = Vec::with_capacity(list.len());
        for who in list {
            names.push(
                who.as_str()
                    .ok_or_else(|| not_owned("an addressee that isn't text"))?
                    .to_owned(),
            );
        }
        owed.push((&turn.conversation, &turn.id, names));
    }
    let asked: Vec<&str> = owed.iter().map(|o| o.1).collect();
    let replies = reads::links_to(scope, reads::REPLIES_TO, &asked)?;
    let replied: HashSet<(&str, &str)> = replies
        .iter()
        .filter_map(|l| Some((l.to.as_str(), l.attributed_to.as_deref()?)))
        .collect();
    let asked_list = mentis_rules::id_list(asked.iter().copied());
    let mut failed: HashMap<String, Vec<String>> = HashMap::new();
    let mut unreadable = false;
    scope.query(TURN_OBSERVATIONS, &[Param::Text(&asked_list)], &mut |r| {
        let turn = reads::text(r, 0)?.unwrap_or_default();
        let Some(body) = reads::text(r, 1)?.and_then(|v| crate::pyjson::loads(&v)) else {
            unreadable = true;
            return Ok(Flow::Stop);
        };
        if body.get("what").is_none() {
            unreadable = true;
            return Ok(Flow::Stop);
        }
        if body.get("what").and_then(Py::as_str) == Some("delivery-failed") {
            match body.get("detail") {
                None => failed.entry(turn).or_default().push(String::new()),
                Some(detail) => match detail.as_str() {
                    Some(words) => failed.entry(turn).or_default().push(words.to_owned()),
                    None => {
                        unreadable = true;
                        return Ok(Flow::Stop);
                    }
                },
            }
        }
        Ok(Flow::Continue)
    })?;
    if unreadable {
        return Err(not_owned("an observation Python has to read"));
    }
    let mut out: HashMap<String, usize> = HashMap::new();
    for (conversation, turn, names) in owed {
        for who in names {
            if replied.contains(&(turn, who.as_str())) {
                continue;
            }
            if failed
                .get(turn)
                .is_some_and(|details| details.iter().any(|d| d.starts_with(&who)))
            {
                continue;
            }
            *out.entry(conversation.to_owned()).or_default() += 1;
        }
    }
    Ok(out)
}

/// `runs.live_by_conversation` and `_live`: who is working where, by the record's open runs and
/// what the snapshot holds of them. Untouched by a live field unless one changes the answer.
fn live_workers(
    scope: &mut dyn ReadScope,
    overlay: &Overlay,
) -> Result<HashMap<String, Vec<Py>>, OpError> {
    struct Mark {
        id: String,
        execution: Option<String>,
        caused_by: Option<String>,
    }
    let mut marks: Vec<(i64, String, Mark)> = Vec::new();
    scope.query(RUN_MARKS, &[], &mut |r| {
        marks.push((
            r.value(0)?.integer().unwrap_or_default(),
            reads::text(r, 2)?.unwrap_or_default(),
            Mark {
                id: reads::text(r, 1)?.unwrap_or_default(),
                execution: reads::text(r, 3)?.filter(|x| !x.is_empty()),
                caused_by: reads::text(r, 4)?,
            },
        ));
        Ok(Flow::Continue)
    })?;
    // `closed_starts`: closed by an end on its own handle that names it, or whose mark is later.
    let starts: HashMap<&str, (i64, Option<&str>)> = marks
        .iter()
        .filter(|m| m.1 == "execution-started")
        .map(|m| (m.2.id.as_str(), (m.0, m.2.execution.as_deref())))
        .collect();
    let mut latest: HashMap<&str, i64> = HashMap::new();
    let mut named: HashSet<&str> = HashSet::new();
    for (seq, act, mark) in &marks {
        if act == "execution-started" {
            continue;
        }
        let Some(execution) = mark.execution.as_deref() else {
            continue;
        };
        let own = mark
            .caused_by
            .as_deref()
            .and_then(|cause| starts.get_key_value(cause))
            .filter(|(_, start)| start.1.is_some());
        let place = own.map_or(*seq, |(_, start)| start.0);
        let held = latest.entry(execution).or_insert(place);
        *held = (*held).max(place);
        if let Some((id, start)) = own
            && start.1 == Some(execution)
        {
            named.insert(id);
        }
    }
    let mut open: Vec<&str> = Vec::new();
    for (seq, act, mark) in &marks {
        if act != "execution-started" {
            continue;
        }
        let closed = mark.execution.as_deref().is_some_and(|execution| {
            latest
                .get(execution)
                .is_some_and(|last| named.contains(mark.id.as_str()) || seq < last)
        });
        if !closed {
            open.push(mark.id.as_str());
        }
    }
    let mut details = Vec::new();
    if !open.is_empty() {
        let list = mentis_rules::id_list(open.iter().copied());
        scope.query(OPEN_STARTS, &[Param::Text(&list)], &mut |r| {
            details.push((
                reads::text(r, 0)?.unwrap_or_default(),
                reads::text(r, 1)?,
                reads::text(r, 2)?,
                reads::text(r, 3)?,
                reads::number(r, 4)?,
            ));
            Ok(Flow::Continue)
        })?;
    }
    let mut open_runs = Vec::with_capacity(details.len());
    for (run, actor, conversation, _, _) in &details {
        if let (Some(actor), Some(conversation)) = (actor, conversation) {
            open_runs.push(OpenRun {
                run: run.clone(),
                conversation: conversation.clone(),
                participant: actor.clone(),
            });
        }
    }
    let token = crate::overlay::read_token(scope);
    let changed = overlay.live_workers_changed(&token, &open_runs, &LiveWorkers::new())?;
    if !changed {
        return Ok(HashMap::new());
    }
    let active = overlay.active_executions(&token)?.to_vec();
    let held = overlay.run_observations(&token)?.clone();
    let mut who: Vec<Id> = active.iter().map(|e| Id(e.participant.clone())).collect();
    who.extend(open_runs.iter().map(|r| Id(r.participant.clone())));
    let aliases = aliases_of(scope, &who)?;
    let alias_of = |participant: &str| -> String {
        let name = aliases.get(participant).map_or(participant, String::as_str);
        name.trim_start_matches('@').to_owned()
    };
    let mut workers: HashMap<String, Vec<Py>> = HashMap::new();
    let mut covered = HashSet::new();
    for (run, actor, conversation, turn, at) in &details {
        if !held.get(run).is_some_and(|r| r.ended_at.is_none()) {
            continue;
        }
        let (Some(actor), Some(conversation)) = (actor, conversation) else {
            return Err(not_owned("an open run Python has to place"));
        };
        covered.insert((conversation.clone(), actor.clone()));
        workers.entry(conversation.clone()).or_default().push(dict([
            ("run", Py::str(run)),
            ("participant", Py::str(actor)),
            ("alias", Py::str(alias_of(actor))),
            ("turn", turn.as_deref().map_or(Py::None, Py::str)),
            ("since", at.clone()),
        ]));
    }
    for e in active {
        let conversation = e.conversation.unwrap_or_default();
        if covered.contains(&(conversation.clone(), e.participant.clone())) {
            continue;
        }
        workers.entry(conversation).or_default().push(dict([
            ("run", Py::None),
            ("alias", Py::str(alias_of(&e.participant))),
            ("participant", Py::str(e.participant)),
            ("turn", Py::None),
            ("since", Py::None),
        ]));
    }
    // `alias` was named before `participant` so the id could move: put them as Python does.
    for rows in workers.values_mut() {
        for row in rows.iter_mut() {
            if let Py::Dict(fields) = row {
                fields.sort_by_key(|(key, _)| match key.as_str() {
                    "run" => 0,
                    "participant" => 1,
                    "alias" => 2,
                    "turn" => 3,
                    _ => 4,
                });
            }
        }
    }
    Ok(workers)
}

/// What `_conversation_rows` gives one Conversation.
fn conversation_row(
    id: &str,
    now: &HashMap<Id, mentis_rules::Reading>,
    created: &Py,
    facts: &Facts,
    workers: Vec<Py>,
) -> Result<Py, OpError> {
    let reading = now
        .get(&Id(id.to_owned()))
        .filter(|r| !r.python_says)
        .ok_or_else(|| not_owned("a Conversation Python has to present"))?;
    let body = loaded(&reading.body_json)?;
    Ok(dict([
        ("id", Py::str(id)),
        ("name", body.get("name").cloned().unwrap_or(Py::None)),
        ("about", body.get("about").cloned().unwrap_or(Py::None)),
        ("provisional", Py::Bool(facts.provisional)),
        ("created", created.clone()),
        ("posts", Py::int(facts.posts)),
        ("included", Py::int(facts.included)),
        ("participants", Py::int(facts.participants)),
        ("last_activity", last_activity(facts)),
        ("working", Py::int(workers.len())),
        ("workers", Py::List(workers)),
    ]))
}

fn read_conversations(
    scope: &mut dyn ReadScope,
    sql: &'static str,
    params: &[Param<'_>],
) -> Result<Vec<(String, Py)>, OpError> {
    let mut rows = Vec::new();
    scope.query(sql, params, &mut |r| {
        rows.push((reads::text(r, 0)?.unwrap_or_default(), reads::number(r, 1)?));
        Ok(Flow::Continue)
    })?;
    Ok(rows)
}

fn api_list(scope: &mut dyn ReadScope, overlay: &Overlay) -> Result<Py, OpError> {
    let roots = read_conversations(scope, ALL_CONVERSATIONS, &[])?;
    let ids: Vec<Id> = roots.iter().map(|r| Id(r.0.clone())).collect();
    let list = mentis_rules::id_list(roots.iter().map(|r| r.0.as_str()));
    let now = mentis_rules::now_reads(scope, &ids)?;
    let facts = conversation_facts(scope, &list)?;
    let mut topics = conversation_topics(scope, &list)?;
    let awaits = awaiting(scope, &list)?;
    let zeros = roots.iter().map(|r| (r.0.clone(), 0usize)).collect();
    let token = crate::overlay::read_token(scope);
    let live = overlay.conversation_counts(&token, zeros)?;
    let mut rows = Vec::with_capacity(roots.len());
    for (id, created) in roots {
        let reading = now
            .get(&Id(id.clone()))
            .filter(|r| !r.python_says)
            .ok_or_else(|| not_owned("a Conversation Python has to present"))?;
        let body = loaded(&reading.body_json)?;
        let f = facts.get(&id).cloned().unwrap_or_default();
        let (Some(name), Some(about)) = (body.get("name"), body.get("about")) else {
            return Err(not_owned("a Conversation Python raises on"));
        };
        let last = f.home_last.clone().unwrap_or(Py::None);
        rows.push(dict([
            ("id", Py::str(&id)),
            ("name", name.clone()),
            ("about", about.clone()),
            ("turns", Py::int(f.posts)),
            ("linked", Py::int(f.included)),
            ("participants", Py::int(f.participants)),
            ("topics", Py::List(topics.remove(&id).unwrap_or_default())),
            ("awaiting", Py::int(*awaits.get(&id).unwrap_or(&0))),
            ("live_executions", Py::int(*live.get(&id).unwrap_or(&0))),
            ("last_activity", last),
            ("created", created),
        ]));
    }
    rows.sort_by(|a, b| {
        let at = |row: &Py| reads::as_f64(row.get("last_activity").unwrap_or(&Py::None));
        at(b).total_cmp(&at(a))
    });
    Ok(dict([("conversations", Py::List(rows))]))
}

fn listed_ids(
    scope: &mut dyn ReadScope,
    wanted: &[String],
    overlay: &Overlay,
) -> Result<Py, OpError> {
    let asked = mentis_rules::id_list(wanted.iter().map(String::as_str));
    let roots = read_conversations(scope, THESE_CONVERSATIONS, &[Param::Text(&asked)])?;
    let ids: Vec<Id> = roots.iter().map(|r| Id(r.0.clone())).collect();
    let list = mentis_rules::id_list(roots.iter().map(|r| r.0.as_str()));
    let now = mentis_rules::now_reads(scope, &ids)?;
    let facts = conversation_facts(scope, &list)?;
    let mut workers = live_workers(scope, overlay)?;
    let listed = states_of(
        scope,
        &roots.iter().map(|r| r.0.clone()).collect::<Vec<_>>(),
    )?;
    let mut shown: HashMap<String, Py> = HashMap::with_capacity(roots.len());
    for (id, created) in &roots {
        let f = facts.get(id).cloned().unwrap_or_default();
        let mut row = conversation_row(
            id,
            &now,
            created,
            &f,
            workers.remove(id).unwrap_or_default(),
        )?;
        set_state(&mut row, listed.get(id));
        shown.insert(id.clone(), row);
    }
    let rows = wanted
        .iter()
        .map(|ask| {
            shown.get(ask).cloned().unwrap_or_else(|| {
                dict([
                    ("id", Py::str(ask)),
                    ("error", Py::str("not a conversation")),
                ])
            })
        })
        .collect();
    Ok(dict([
        ("conversations", Py::List(rows)),
        ("limit", Py::int(64)),
    ]))
}

fn activity(
    scope: &mut dyn ReadScope,
    after: Option<&str>,
    q: Option<&str>,
    state: Option<ListState>,
    limit: usize,
    overlay: &Overlay,
) -> Result<Py, OpError> {
    let mut page = Vec::new();
    let mut total = 0i64;
    let searching = q.is_some();
    // `conversation_states()`: the Brain's, read only when a state is asked for.
    let mut away = match state {
        Some(_) => states(scope, STATE_ACTS_ALL, &[])?,
        None => HashMap::new(),
    };
    away.retain(|_, a| a.state != "active");
    match state {
        Some(listed @ (ListState::Archived | ListState::Trashed)) => {
            // Most recently changed first, then by id.
            let mut held: Vec<(&String, &Away)> = away
                .iter()
                .filter(|(_, a)| a.state == listed.word())
                .collect();
            held.sort_by(|a, b| {
                reads::as_f64(&b.1.at)
                    .total_cmp(&reads::as_f64(&a.1.at))
                    .then_with(|| a.0.cmp(b.0))
            });
            let ids: Vec<String> = held.into_iter().map(|(id, _)| id.clone()).collect();
            total = ids.len() as i64;
            page = if searching {
                ids
            } else {
                let start = after
                    .and_then(|id| ids.iter().position(|x| x == id))
                    .map_or(0, |at| at + 1);
                ids.into_iter().skip(start).take(limit).collect()
            };
        }
        _ => {
            let edge = match (searching, after) {
                (false, Some(id)) => Param::Text(id),
                _ => Param::Null,
            };
            let active = state == Some(ListState::Active);
            // Active without a search: Python reads page after page of `limit` until the page is
            // full; that never reads past `limit + away` rounded up to whole pages, so this one
            // statement holds every page it would read.
            let most = if searching {
                -1
            } else if active {
                (limit + away.len()).div_ceil(limit.max(1)) as i64 * limit as i64
            } else {
                limit as i64
            };
            scope.query(ACTIVITY_PAGE, &[edge, Param::Integer(most)], &mut |r| {
                page.push(reads::text(r, 0)?.unwrap_or_default());
                total = r.value(1)?.integer().unwrap_or_default();
                Ok(Flow::Continue)
            })?;
            if active && searching {
                page.retain(|id| !away.contains_key(id));
            } else if active {
                // `conversation_list`'s loop over those pages, each `total` as its page gave it
                // (0 for an empty page), the away left out.
                let all = std::mem::take(&mut page);
                let mut from = 0;
                let said = loop {
                    let part = &all[from.min(all.len())..(from + limit).min(all.len())];
                    page.extend(part.iter().filter(|id| !away.contains_key(*id)).cloned());
                    if page.len() >= limit || part.len() < limit {
                        break if part.is_empty() { 0 } else { total };
                    }
                    from += limit;
                };
                page.truncate(limit);
                total = (said - away.len() as i64).max(0);
            }
        }
    }
    let list = mentis_rules::id_list(page.iter().map(String::as_str));
    let roots = read_conversations(scope, THESE_CONVERSATIONS, &[Param::Text(&list)])?;
    let created: HashMap<String, Py> = roots.into_iter().collect();
    let ids: Vec<Id> = page.iter().map(|id| Id(id.clone())).collect();
    let now = mentis_rules::now_reads(scope, &ids)?;
    let facts = conversation_facts(scope, &list)?;
    let mut workers = live_workers(scope, overlay)?;
    let owed = crate::needs_you::counts_by_conversation(scope, &page)?;
    let mut topics = conversation_topics(scope, &list)?;
    // `_conversation_rows`' states (`latest=True`): the page's latest act each, active ones too.
    let listed = states_of(scope, &page)?;
    let mut rows = Vec::with_capacity(page.len());
    for id in &page {
        let at = created
            .get(id)
            .ok_or_else(|| not_owned("a Conversation the record didn't give back"))?;
        let f = facts.get(id).cloned().unwrap_or_default();
        let mut row = conversation_row(id, &now, at, &f, workers.remove(id).unwrap_or_default())?;
        set_state(&mut row, listed.get(id));
        row.set("needs_you", Py::int(*owed.get(id).unwrap_or(&0)));
        row.set("topics", Py::List(topics.remove(id).unwrap_or_default()));
        rows.push(row);
    }
    if let Some(q) = q {
        let folded = python::lower(q).ok_or_else(|| not_owned("a search Python folds"))?;
        let words: Vec<&str> = python::words(&folded).collect();
        let mut kept = Vec::with_capacity(rows.len());
        for row in rows {
            let mut hay: Vec<String> = Vec::new();
            let name = row.get("name").filter(|n| n.truthy());
            match name {
                Some(name) => hay.push(
                    name.as_str()
                        .ok_or_else(|| not_owned("a name that isn't text"))?
                        .to_owned(),
                ),
                None => hay.push(String::new()),
            }
            for topic in row.get("topics").and_then(Py::as_list).unwrap_or(&[]) {
                hay.push(
                    topic
                        .get("name")
                        .and_then(Py::as_str)
                        .ok_or_else(|| not_owned("a Topic name that isn't text"))?
                        .to_owned(),
                );
            }
            let hay =
                python::lower(&hay.join(" ")).ok_or_else(|| not_owned("a name Python folds"))?;
            if words.iter().all(|word| hay.contains(word)) {
                kept.push(row);
            }
        }
        total = kept.len() as i64;
        let start = after
            .and_then(|id| {
                kept.iter()
                    .position(|row| row.get("id").and_then(Py::as_str) == Some(id))
            })
            .map_or(0, |at| at + 1);
        rows = kept.into_iter().skip(start).take(limit).collect();
    }
    let next = if rows.len() == limit {
        rows.last()
            .and_then(|row| row.get("id").cloned())
            .unwrap_or(Py::None)
    } else {
        Py::None
    };
    Ok(dict([
        ("conversations", Py::List(rows)),
        ("total", Py::int(total)),
        ("limit", Py::int(limit)),
        ("next", next),
    ]))
}

impl ReadOp for Conversations {
    type Args = ConversationsArgs;
    type Row = PyRow;
    const NAME: &'static str = "conversations";
    const BUDGET: Budget = Budget {
        statements: 18
            + mentis_rules::STATEMENTS * 4
            + crate::needs_you::NeedsYou::BUDGET.statements,
    };
    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let as_of = scope.position();
        let overlay = &request.args.overlay;
        let answer = match &request.args.mode {
            ConversationMode::Api => api_list(scope, overlay)?,
            ConversationMode::Ids(wanted) => listed_ids(scope, wanted, overlay)?,
            ConversationMode::Activity { after, q, state } => activity(
                scope,
                after.as_deref(),
                q.as_deref(),
                *state,
                request.limit.unwrap_or(100) as usize,
                overlay,
            )?,
        };
        Ok(ReadAnswer {
            rows: vec![PyRow(answer)],
            as_of,
            more: None,
            not_searched: vec![],
        })
    }
}
