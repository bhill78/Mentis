//! `magnet_read`: what a Magnet's sources hold now, for `GET /fluid/api/magnets/<id>/read`. Contract:
//! `docs/magnets/M1-contract.md`. **Composition only:** a page is the window's own [`collected`] and
//! [`Objects`], and a summary the tally `linked_node_tally` runs, with [`mentis_rules::now_reads`] for
//! what names it. No second retrieval, and no index, thread, store or service.
//!
//! It knows no grant and reads no live state. The definition comes in `Args`, already read and checked
//! by the route, which is the only part that touches a file. The class is the caller's: Background.
//!
//! **One source never fails the others.** Each gets a share of what is left of the deadline and answers
//! for itself: `ok`, `partial`, `unavailable` with a reason, or `busy`. A statement already running is
//! bounded by the scope's own limit, not by that share: a share is looked at when a statement starts and
//! at each row, so a statement yielding no rows can use up the request. No class place at all is
//! [`OpError::Busy`] for the whole request.
//!
//! **Extraction takes the window's engines,** which are one queue with no notion of class, and it comes
//! after the scope has gone, so the class's cap doesn't cover it. [`MagnetPlan::finish`] therefore holds
//! one of [`FINISH_PLACES`] for any extraction, runs them one at a time, and does at most
//! [`UNCACHED_MOST`] per request. What is already kept costs no engine. What's left answers `partial`,
//! and asking again gets further, because what was read stays kept.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::time::Instant;

use mentis_extract::Bundle;
use mentis_record::{Flow, Id, Param, Position, ReadScope, RecordError, Row};
use mentis_rules::body::{self, Field};
use serde_json::Value as Json;

use crate::pyjson::{self, Py, dict};
use crate::window::collections::{self, ConversationArgs};
use crate::window::objects::{Objects, ObjectsArgs, ObjectsAsk, ObjectsPlan};
use crate::window::reads::{
    self, CONVERSATION, IN_CONVERSATION, LINKED_INTO, as_f64, in_force, links_to,
};
use crate::window::{Prepared, Window};
use crate::{Budget, Cursor, OpError, ReadAnswer, ReadOp, ReadRequest};

/// What a definition may hold, `mentis.magnet.schema`'s.
pub const SOURCES_MOST: usize = 20;
/// `mentis.magnet.schema.SCHEMA_VERSION`. A later one is never read as this one.
pub const SCHEMA_VERSION: u64 = 1;
/// Roots on one source's page.
pub const PAGE: u32 = 20;
/// Extractions one request may start. What is kept already doesn't count.
pub const UNCACHED_MOST: usize = 4;
/// Requests that may extract at once. The class's cap doesn't reach past its scope, and this is that
/// cap's number: a Magnet read holds at most this many of the engines' turns.
pub const FINISH_PLACES: usize = 2;
/// The most a summary of one source can run: the kinds, how it reads, its tally, what's linked into it
/// and which of that is in force. Nothing else: no post, no object and no page.
pub const SUMMARY_ONE: u32 = 1 + mentis_rules::STATEMENTS + 1 + 1 + mentis_rules::STATEMENTS;
/// The types a definition that names none collects, as `conversation.ts` has always read it.
const DEFAULT_TYPES: [&str; 3] = ["post", "file", "image"];
const OBJECT_TYPES: [&str; 5] = ["file", "image", "attachment", "link", "form"];
const ALL_TYPES: [&str; 7] = [
    "post",
    "file",
    "image",
    "attachment",
    "link",
    "form",
    "other",
];
/// `selection`'s words kept and not applied: phrase semantics aren't decided, and search over a Brain
/// waits on Track A's `text_scan`.
const KEPT_WHY: &str = "kept with the Magnet, not applied: what it means for a source isn't decided, \
                        and searching waits on the shared text scan";

/// `linked_node_tally`.
const TALLY: &str = "SELECT COUNT(DISTINCT e.id), MAX(e.recorded_at) \
     FROM entry l JOIN entry e ON e.id = l.link_from \
     WHERE l.link_relation = ?1 AND l.link_to = ?2 \
     AND e.def_name = 'contribution' AND e.family = 'entry' AND e.link_relation IS NULL";

/// Why a definition can't be used. The route forwards the first, and answers each source unavailable
/// for the second: a definition from a later schema is never read as if it were this one.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum NotADefinition {
    Malformed(String),
    LaterSchema(String),
}

/// One source of a definition.
#[derive(Clone, Debug)]
pub struct MagnetSource {
    /// `model.ts` `sourceKey`: what `source=` names, and what results are held under.
    pub key: String,
    /// As the definition has it.
    pub said: Py,
    /// The one kind this build reads.
    pub conversation: Option<String>,
    /// Why it can't be read, when it can't.
    pub unavailable: Option<String>,
}

/// One end of `selection.dates`: what was said, and when that is, if this can read it.
#[derive(Clone, Debug, PartialEq)]
pub struct DateBound {
    pub said: String,
    pub at: Option<f64>,
}

/// A checked definition, as far as a read needs it.
#[derive(Clone, Debug)]
pub struct MagnetDefinition {
    pub id: String,
    pub sources: Vec<MagnetSource>,
    pub types: Option<Vec<String>>,
    pub after: Option<DateBound>,
    pub before: Option<DateBound>,
    /// Which of `selection`'s facets it holds and this doesn't apply.
    pub kept: Vec<String>,
}

fn text_of<'a>(v: &'a Json, name: &str) -> Option<&'a str> {
    v.get(name).and_then(Json::as_str)
}

/// `model.ts` `sourceKey`, and the kinds it didn't always know: `kind:` and what names it.
fn source_key(v: &Json, kind: &str) -> String {
    let t = |name: &str| text_of(v, name).unwrap_or("");
    match kind {
        "brain" => format!("brain:{}", t("brain")),
        "conversation" => format!("conversation:{}", t("conversation")),
        "connector" => format!("connector:{}:{}", t("connector"), t("location")),
        "web" => format!("web:{}:{}", t("url"), t("domain")),
        "other" => format!("other:{}:{}", t("type"), t("ref")),
        "agent-results" => format!("agent-results:{}:{}", t("conversation"), t("runtime")),
        "file" => format!("file:{}:{}", t("collection"), t("path")),
        "database" => format!("database:{}:{}", t("collection"), t("table")),
        other => format!("{other}:"),
    }
}

fn unavailable_why(kind: &str) -> String {
    match kind {
        "brain" | "agent-results" => {
            format!("reading a {kind} source waits on the shared text scan")
        }
        "web" => "reading the web is not in this build".to_owned(),
        "connector" => "no connector is connected here".to_owned(),
        "file" | "database" => format!("reading a {kind} source is not in this build"),
        other => format!("nothing in this build reads a {other} source yet"),
    }
}

fn is_magnet_id(id: &str) -> bool {
    id.len() > 4
        && id.len() <= 64
        && id.starts_with("mag-")
        && id[4..]
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-'))
}

impl MagnetDefinition {
    /// A definition file's text. `mentis.magnet` wrote it and checks it fully. This checks what a read
    /// leans on, and refuses anything it can't be sure of: an unknown `schema_version` is never defaulted.
    pub fn parse(id: &str, text: &str) -> Result<MagnetDefinition, NotADefinition> {
        let bad = |why: &str| NotADefinition::Malformed(format!("the definition {id} {why}"));
        if !is_magnet_id(id) {
            return Err(bad("has no well-formed id"));
        }
        let v: Json = serde_json::from_str(text).map_err(|_| bad("is not JSON"))?;
        if !v.is_object() {
            return Err(bad("is not a mapping"));
        }
        match v.get("schema_version") {
            None => {}
            Some(found)
                if found
                    .as_u64()
                    .is_some_and(|n| (1..=SCHEMA_VERSION).contains(&n)) => {}
            Some(found) => {
                return Err(NotADefinition::LaterSchema(format!(
                    "the definition {id} has schema_version {found}, and this build reads 1..{SCHEMA_VERSION}"
                )));
            }
        }
        if text_of(&v, "id") != Some(id) {
            return Err(bad("names another id"));
        }
        let listed = v.get("sources").and_then(Json::as_array);
        let listed = listed
            .filter(|s| !s.is_empty() && s.len() <= SOURCES_MOST)
            .ok_or_else(|| bad("has no list of 1..20 sources"))?;
        let mut sources = Vec::with_capacity(listed.len());
        for s in listed {
            let kind = text_of(s, "kind").ok_or_else(|| bad("has a source of no kind"))?;
            let said =
                pyjson::loads(&s.to_string()).ok_or_else(|| bad("has an unreadable source"))?;
            let conversation = (kind == "conversation")
                .then(|| text_of(s, "conversation").map(str::to_owned))
                .flatten();
            if kind == "conversation" && conversation.is_none() {
                return Err(bad("has a conversation source naming none"));
            }
            sources.push(MagnetSource {
                key: source_key(s, kind),
                said,
                unavailable: (kind != "conversation").then(|| unavailable_why(kind)),
                conversation,
            });
        }
        let selection = v.get("selection").filter(|s| s.is_object());
        let selection = selection.ok_or_else(|| bad("has no selection"))?;
        let types = match selection.get("informationTypes") {
            None => None,
            Some(list) => Some(
                list.as_array()
                    .ok_or_else(|| bad("has informationTypes that aren't a list"))?
                    .iter()
                    .map(|t| t.as_str().map(str::to_owned))
                    .collect::<Option<Vec<_>>>()
                    .ok_or_else(|| bad("has informationTypes that aren't words"))?,
            ),
        };
        let date = |name: &str| {
            let said = selection.get("dates").and_then(|d| text_of(d, name))?;
            Some(DateBound {
                said: said.to_owned(),
                at: epoch_of(said),
            })
        };
        let mut kept = Vec::new();
        for facet in ["criteria", "phrases", "topics", "filters"] {
            let held = match selection.get(facet) {
                None | Some(Json::Null) => false,
                Some(Json::String(words)) => !words.trim().is_empty(),
                Some(Json::Array(list)) => !list.is_empty(),
                Some(Json::Object(map)) => !map.is_empty(),
                Some(_) => true,
            };
            if held {
                kept.push(facet.to_owned());
            }
        }
        Ok(MagnetDefinition {
            id: id.to_owned(),
            sources,
            types,
            after: date("after"),
            before: date("before"),
            kept,
        })
    }
}

/// Seconds since 1970 of `YYYY-MM-DD`, with `THH:MM[:SS[.fff]]` and `Z` or `±HH:MM` where given. With
/// no offset it is UTC. `None` for anything else, which is then said, never guessed.
pub fn epoch_of(said: &str) -> Option<f64> {
    let digits = |s: &str| -> Option<i64> {
        (!s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()))
            .then(|| s.parse().ok())
            .flatten()
    };
    let (date, rest) = if said.len() > 10 {
        said.split_at_checked(10)?
    } else {
        (said, "")
    };
    let mut parts = date.split('-');
    let (year, month, day) = (parts.next()?, parts.next()?, parts.next()?);
    if parts.next().is_some() || year.len() != 4 || month.len() != 2 || day.len() != 2 {
        return None;
    }
    let (y, m, d) = (digits(year)?, digits(month)?, digits(day)?);
    if !(1..=12).contains(&m) || !(1..=31).contains(&d) {
        return None;
    }
    let days = {
        // Days from civil, by the usual era arithmetic.
        let y = if m <= 2 { y - 1 } else { y };
        let era = y.div_euclid(400);
        let yoe = y - era * 400;
        let doy = (153 * (if m > 2 { m - 3 } else { m + 9 }) + 2) / 5 + d - 1;
        era * 146_097 + yoe * 365 + yoe / 4 - yoe / 100 + doy - 719_468
    };
    let mut seconds = days as f64 * 86_400.0;
    let Some(time) = rest.strip_prefix(['T', ' ']) else {
        return rest.is_empty().then_some(seconds);
    };
    let (clock, offset) = if let Some(clock) = time.strip_suffix(['Z', 'z']) {
        (clock, 0.0)
    } else if let Some(at) = time.rfind(['+', '-']) {
        let (clock, off) = time.split_at(at);
        let sign = if off.starts_with('-') { -1.0 } else { 1.0 };
        let (h, min) = off[1..].split_once(':').unwrap_or((&off[1..], "0"));
        (
            clock,
            sign * (digits(h)? as f64 * 3600.0 + digits(min)? as f64 * 60.0),
        )
    } else {
        (time, 0.0)
    };
    let mut bits = clock.split(':');
    let hours = digits(bits.next()?)?;
    let minutes = digits(bits.next()?)?;
    let secs: f64 = match bits.next() {
        None => 0.0,
        Some(s) if s.bytes().all(|b| b.is_ascii_digit() || b == b'.') => s.parse().ok()?,
        Some(_) => return None,
    };
    if bits.next().is_some() || hours > 23 || minutes > 59 || secs >= 61.0 {
        return None;
    }
    seconds += hours as f64 * 3600.0 + minutes as f64 * 60.0 + secs - offset;
    Some(seconds)
}

/// Which of the seven an object row is, or none (a section of a post's own words). `objectTypeOf` in
/// `conversation.ts`: the conformance fixtures hold both to one set of rows.
pub fn object_type(row: &Py, want: &[String]) -> Option<&'static str> {
    let preview = row.get("preview");
    let is = preview.and_then(|p| p.get("is")).filter(|is| is.truthy());
    fn word<'a>(of: Option<&'a Py>, name: &str) -> Option<&'a str> {
        of.and_then(|o| o.get(name)).and_then(Py::as_str)
    }
    if let Some(is) = is {
        if is.get("fillable").is_some_and(Py::truthy) {
            return Some("form");
        }
        match word(Some(is), "family").filter(|f| !f.is_empty()) {
            Some("media") => return Some("image"),
            Some("link") => return Some("link"),
            Some("file") => {
                let attached = word(Some(is), "source") == Some("attachment");
                return Some(if attached && want.iter().any(|t| t == "attachment") {
                    "attachment"
                } else {
                    "file"
                });
            }
            Some(_) => return None,
            None => {}
        }
    }
    let said = format!(
        "{} {} {} {}",
        word(Some(row), "kind").unwrap_or(""),
        word(preview, "type").unwrap_or(""),
        word(preview, "media_type").unwrap_or(""),
        word(is, "filter").unwrap_or("")
    )
    .to_lowercase();
    let any = |words: &[&str]| words.iter().any(|w| said.contains(w));
    if any(&[
        "image", "picture", "photo", "png", "jpg", "jpeg", "gif", "webp", "svg", "video", "audio",
    ]) {
        return Some("image");
    }
    if any(&[
        "file",
        "document",
        "pdf",
        "attachment",
        "sheet",
        "data",
        "code",
        "zip",
        "archive",
    ]) {
        return Some("file");
    }
    None
}

/// What a request asks.
#[derive(Clone, Debug)]
pub enum MagnetMode {
    /// Title, activity and post count. Never the object index, whatever the selection.
    Summary,
    Page {
        /// One source's key, or every source's first page.
        source: Option<String>,
        /// What `types=` asked, or the selection's.
        types: Option<Vec<String>>,
    },
}

/// The op's arguments. `cursor` is `ReadRequest.cursor`, and needs `source`: there is one per source.
pub struct MagnetArgs {
    pub magnet: MagnetDefinition,
    pub mode: MagnetMode,
    /// For `Page`, what objects are read with. `Err` says why they can't be, for the sources' reasons.
    pub bundle: Result<Bundle, String>,
    /// The client has gone: every statement stops, and the place goes back.
    pub gone: Arc<AtomicBool>,
}

/// The op. No state of its own.
pub struct MagnetRead<'w> {
    pub window: &'w Window,
}

/// A scope no statement of which goes past `until`, or past the client's leaving.
struct Share<'a> {
    scope: &'a mut dyn ReadScope,
    until: Instant,
    gone: &'a AtomicBool,
}

impl ReadScope for Share<'_> {
    fn position(&self) -> Position {
        self.scope.position()
    }

    fn query(
        &mut self,
        sql: &'static str,
        params: &[Param<'_>],
        each: &mut dyn FnMut(&dyn Row) -> Result<Flow, RecordError>,
    ) -> Result<(), RecordError> {
        let (until, gone) = (self.until, self.gone);
        let over = move || Instant::now() >= until || gone.load(Ordering::Relaxed);
        if over() {
            return Err(RecordError::ScopeExpired);
        }
        self.scope.query(sql, params, &mut |row| {
            if over() {
                return Err(RecordError::ScopeExpired);
            }
            each(row)
        })
    }

    fn statements(&self) -> u32 {
        self.scope.statements()
    }
}

/// What a source answers. `status` is one of the four.
struct SourcePlan {
    key: String,
    said: Py,
    status: &'static str,
    reason: Option<String>,
    summary: Option<Py>,
    results: Vec<Py>,
    next: Py,
    dates: Py,
    /// What's left to read once the scope has gone.
    objects: Option<ObjectsWork>,
}

struct ObjectsWork {
    plan: ObjectsPlan,
    conversation: String,
    types: Vec<String>,
    after: Option<f64>,
}

/// The whole read, its statements done.
pub struct MagnetPlan {
    magnet: String,
    mode: &'static str,
    as_of: Position,
    sources: Vec<SourcePlan>,
    kept: Vec<String>,
}

fn dates_of(magnet: &MagnetDefinition) -> Py {
    let one = |bound: &Option<DateBound>| match bound {
        None => Py::None,
        Some(bound) => dict([
            ("said", Py::str(bound.said.as_str())),
            ("applied", Py::Bool(bound.at.is_some())),
        ]),
    };
    dict([
        ("after", one(&magnet.after)),
        ("before", one(&magnet.before)),
    ])
}

fn plan_of(source: &MagnetSource, magnet: &MagnetDefinition) -> SourcePlan {
    SourcePlan {
        key: source.key.clone(),
        said: source.said.clone(),
        status: if source.unavailable.is_some() {
            "unavailable"
        } else {
            "ok"
        },
        reason: source.unavailable.clone(),
        summary: None,
        results: Vec::new(),
        next: Py::None,
        dates: dates_of(magnet),
        objects: None,
    }
}

impl MagnetDefinition {
    /// Every source of it, each unavailable for the same reason: a definition this can't use at all.
    pub fn all_unavailable(id: &str, why: &str) -> Py {
        dict([
            ("magnet", Py::str(id)),
            ("unavailable", Py::str(why)),
            ("sources", Py::List(Vec::new())),
        ])
    }
}

/// A failed read, as the source says it.
fn mark(plan: &mut SourcePlan, error: OpError) {
    let (status, why) = match error {
        OpError::Busy { why } => ("busy", why),
        OpError::Record(RecordError::ScopeExpired) => (
            "busy",
            "it took its share of this read; ask again".to_owned(),
        ),
        OpError::NotOwned { why } => ("unavailable", why),
        OpError::BadRequest { why } => ("unavailable", why),
        OpError::NotFound { what } => ("unavailable", what),
        other => ("unavailable", other.to_string()),
    };
    plan.status = status;
    plan.reason = Some(why);
}

impl MagnetRead<'_> {
    /// Title, activity and post count of one Conversation: its tally and what's linked into it, and
    /// never a post's body or its objects. `read.py`'s `_conversation_rows`.
    fn summary(
        &self,
        scope: &mut dyn ReadScope,
        id: &str,
        kind_of: &HashMap<String, reads::Head>,
        now: &HashMap<Id, mentis_rules::Reading>,
    ) -> Result<Py, OpError> {
        let held = kind_of.get(id).filter(|h| {
            h.family == "entry" && !h.is_link && h.kind.as_deref() == Some(CONVERSATION)
        });
        if held.is_none() {
            return Err(OpError::NotFound {
                what: format!("not a conversation: {id}"),
            });
        }
        let reading = now
            .get(&Id(id.to_owned()))
            .ok_or_else(|| OpError::NotFound {
                what: format!("not a conversation: {id}"),
            })?;
        if reading.python_says || reading.deleted.is_some() {
            return Err(OpError::NotFound {
                what: format!("the conversation {id} was deleted"),
            });
        }
        let fields = body::fields(&reading.body_json, &["name", "about"]).unwrap_or_default();
        let word = |at: usize| match fields.get(at) {
            Some(Field::Text(text)) => Some(text.clone()),
            _ => None,
        };
        let mut posts = 0_i64;
        let mut newest = Py::None;
        scope.query(
            TALLY,
            &[Param::Text(IN_CONVERSATION), Param::Text(id)],
            &mut |row| {
                posts = row.value(0)?.integer().unwrap_or(0);
                newest = reads::number(row, 1)?;
                Ok(Flow::Stop)
            },
        )?;
        let linked = links_to(scope, LINKED_INTO, &[id])?;
        let linked = in_force(scope, linked)?;
        for link in &linked {
            if as_f64(&link.recorded_at) > as_f64(&newest) {
                newest = link.recorded_at.clone();
            }
        }
        Ok(dict([
            (
                "title",
                word(0).map_or_else(|| Py::str("Conversation"), Py::Str),
            ),
            ("about", word(1).map_or(Py::None, Py::Str)),
            ("activity", newest),
            ("posts", Py::int(posts)),
        ]))
    }

    /// One source's bounded page: its posts where asked, and its objects' plan where asked.
    fn page(
        &self,
        scope: &mut dyn ReadScope,
        plan: &mut SourcePlan,
        conversation: &str,
        args: &MagnetArgs,
        types: &[String],
        (cursor, limit): (Option<&str>, u32),
    ) -> Result<(), OpError> {
        let magnet = &args.magnet;
        let after = magnet.after.as_ref().and_then(|b| b.at);
        // A date's end is a place to page from, read by the page's own cursor rule.
        let dated = magnet
            .before
            .as_ref()
            .and_then(|b| b.at)
            .map(|at| format!("{at:?}_{}", i64::MAX));
        let before = cursor.map(str::to_owned).or(dated);
        let posts_asked = types.iter().any(|t| t == "post");
        let objects_asked = types.iter().any(|t| OBJECT_TYPES.contains(&t.as_str()));
        if !posts_asked && !objects_asked {
            return Ok(());
        }
        if posts_asked {
            let args = ConversationArgs {
                id: conversation.to_owned(),
                before: before.clone(),
                ..ConversationArgs::default()
            };
            let page = collections::collected(scope, &args, limit)?;
            let ids: Vec<Id> = page.ids.iter().cloned().map(Id).collect();
            let list: Vec<&str> = page.ids.iter().map(String::as_str).collect();
            let heads = reads::heads(scope, &list)?;
            let now = mentis_rules::now_reads(scope, &ids)?;
            let items = page
                .answer
                .get("items")
                .and_then(Py::as_list)
                .unwrap_or(&[]);
            let mut older_than_asked = false;
            for item in items.iter().rev() {
                let Some(id) = item.get("id").and_then(Py::as_str) else {
                    continue;
                };
                let head = heads.get(id);
                let at = head.map_or(Py::None, |h| h.recorded_at.clone());
                if after.is_some_and(|floor| as_f64(&at) < floor) {
                    older_than_asked = true;
                    continue;
                }
                let reading = now.get(&Id(id.to_owned()));
                let version = reading.map_or_else(
                    || id.to_owned(),
                    |r| match (&r.deleted, &r.revision) {
                        (Some(deleted), _) => deleted.record.0.clone(),
                        (None, Some(revision)) => revision.current.0.clone(),
                        (None, None) => id.to_owned(),
                    },
                );
                let home = item
                    .get("home")
                    .and_then(Py::as_str)
                    .unwrap_or(conversation);
                plan.results.push(dict([
                    ("kind", Py::str("post")),
                    ("id", Py::str(id)),
                    ("version", Py::Str(version)),
                    ("conversation", Py::str(home)),
                    (
                        "author",
                        Py::opt_str(head.and_then(|h| h.attributed_to.as_deref())),
                    ),
                    ("at", at),
                    ("number", item.get("number").cloned().unwrap_or(Py::None)),
                    ("via", item.get("via").cloned().unwrap_or(Py::None)),
                    (
                        "deleted",
                        Py::Bool(reading.is_some_and(|r| r.deleted.is_some())),
                    ),
                ]));
            }
            plan.next = if older_than_asked {
                Py::None
            } else {
                page.before
            };
        }
        if objects_asked {
            let bundle = match &args.bundle {
                Ok(bundle) => bundle.clone(),
                Err(why) => {
                    plan.status = "partial";
                    plan.reason = Some(format!("its objects can't be read here: {why}"));
                    return Ok(());
                }
            };
            let asked = ReadRequest {
                args: ObjectsArgs {
                    bundle,
                    ask: ObjectsAsk::Conversation {
                        id: conversation.to_owned(),
                        before,
                        limit,
                    },
                },
                cursor: None,
                limit: None,
                deadline: Instant::now(),
            };
            let op = Objects {
                window: self.window,
            };
            let mut read = op.read(scope, &asked)?;
            let Prepared(work) = read.rows.pop().expect("objects answers one plan");
            if !posts_asked {
                plan.next = work.page_before().unwrap_or(Py::None);
            }
            plan.objects = Some(ObjectsWork {
                plan: work,
                conversation: conversation.to_owned(),
                types: types.to_vec(),
                after,
            });
        }
        Ok(())
    }
}

impl ReadOp for MagnetRead<'_> {
    type Args = MagnetArgs;
    type Row = Prepared<MagnetPlan>;

    const NAME: &'static str = "magnet_read";
    /// The position, then at most: for a summary, the sources' kinds and how they read, and each one's
    /// tally, what's linked in and which of that is in force. For a page, each source's collection, its
    /// heads, how they read, and the whole of [`Objects`]. A page is the larger, so it's the bound, and
    /// it grows with the sources in a definition and never with what a Conversation holds.
    const BUDGET: Budget = Budget {
        statements: 1
            + (SOURCES_MOST as u32)
                * (collections::COLLECTED_STATEMENTS
                    + 1
                    + mentis_rules::STATEMENTS
                    + <Objects<'static> as ReadOp>::BUDGET.statements),
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<MagnetArgs>,
    ) -> Result<ReadAnswer<Prepared<MagnetPlan>>, OpError> {
        let args = &request.args;
        let magnet = &args.magnet;
        let as_of = scope.position();
        let cursor = request.cursor.as_ref().map(|Cursor(text)| text.as_str());
        let limit = request.limit.unwrap_or(PAGE).clamp(1, PAGE);
        let (asked_source, mode, page_types) = match &args.mode {
            MagnetMode::Summary => (None, "summary", None),
            MagnetMode::Page { source, types } => {
                let types = types
                    .clone()
                    .or_else(|| magnet.types.clone().filter(|t| !t.is_empty()))
                    .unwrap_or_else(|| DEFAULT_TYPES.iter().map(|t| (*t).to_owned()).collect());
                (source.as_deref(), "page", Some(types))
            }
        };
        if cursor.is_some() && asked_source.is_none() {
            return Err(OpError::BadRequest {
                why: "a cursor is one source's: name it with source=".to_owned(),
            });
        }
        if let Some(asked) = asked_source
            && !magnet.sources.iter().any(|s| s.key == asked)
        {
            return Err(OpError::BadRequest {
                why: format!("{asked:?} is not one of this Magnet's sources"),
            });
        }
        let chosen: Vec<&MagnetSource> = magnet
            .sources
            .iter()
            .filter(|s| asked_source.is_none_or(|asked| s.key == asked))
            .collect();
        let mut plans: Vec<SourcePlan> = chosen.iter().map(|s| plan_of(s, magnet)).collect();

        // What a summary reads together, once, under the whole deadline.
        let mut kinds = HashMap::new();
        let mut now = HashMap::new();
        if mode == "summary" {
            let mut seen = HashSet::new();
            let ids: Vec<&str> = chosen
                .iter()
                .filter_map(|s| s.conversation.as_deref())
                .filter(|id| seen.insert(*id))
                .collect();
            let asked: Vec<Id> = ids.iter().map(|id| Id((*id).to_owned())).collect();
            let mut share = Share {
                scope: &mut *scope,
                until: request.deadline,
                gone: &args.gone,
            };
            let read = reads::heads(&mut share, &ids).and_then(|heads| {
                mentis_rules::now_reads(&mut share, &asked).map(|readings| (heads, readings))
            });
            match read {
                Ok((heads, readings)) => {
                    kinds = heads;
                    now = readings;
                }
                Err(error) => {
                    let error = OpError::from(error);
                    for plan in plans.iter_mut().filter(|p| p.status == "ok") {
                        mark(plan, error.clone());
                    }
                }
            }
        }

        let mut left = plans.iter().filter(|p| p.status == "ok").count();
        for (source, plan) in chosen.iter().zip(&mut plans) {
            if args.gone.load(Ordering::Relaxed) {
                break;
            }
            let (Some(id), "ok") = (source.conversation.as_deref(), plan.status) else {
                continue;
            };
            let at = Instant::now();
            let room = request.deadline.saturating_duration_since(at);
            let parts = u32::try_from(left.max(1)).unwrap_or(1);
            let mut share = Share {
                scope: &mut *scope,
                until: at + room / parts,
                gone: &args.gone,
            };
            let got = match &page_types {
                None => self
                    .summary(&mut share, id, &kinds, &now)
                    .map(|summary| plan.summary = Some(summary)),
                Some(types) => self.page(&mut share, plan, id, args, types, (cursor, limit)),
            };
            left = left.saturating_sub(1);
            match got {
                Ok(()) => {}
                // A cursor is the asker's: what's wrong with it is for the whole request to be told.
                Err(OpError::BadRequest { why }) if cursor.is_some() => {
                    return Err(OpError::BadRequest { why });
                }
                Err(error) => {
                    mark(plan, error);
                    // Its posts were read before its objects failed, and they still answer.
                    if !plan.results.is_empty() {
                        plan.status = "partial";
                    }
                }
            }
        }
        if args.gone.load(Ordering::Relaxed) {
            return Err(OpError::Busy {
                why: "the client has gone".to_owned(),
            });
        }
        Ok(ReadAnswer {
            rows: vec![Prepared(MagnetPlan {
                magnet: magnet.id.clone(),
                mode,
                as_of,
                sources: plans,
                kept: magnet.kept.clone(),
            })],
            as_of,
            more: None,
            not_searched: Vec::new(),
        })
    }
}

/// How many are extracting now, and a place among them.
static FINISHING: AtomicUsize = AtomicUsize::new(0);

struct Place;

impl Place {
    fn take() -> Option<Place> {
        if FINISHING.fetch_add(1, Ordering::SeqCst) < FINISH_PLACES {
            return Some(Place);
        }
        FINISHING.fetch_sub(1, Ordering::SeqCst);
        None
    }
}

impl Drop for Place {
    fn drop(&mut self) {
        FINISHING.fetch_sub(1, Ordering::SeqCst);
    }
}

impl MagnetPlan {
    /// The rest of the read, with no scope and no statement: objects for the sources that asked, then
    /// the answer. `stop` is the deadline or the client's leaving, and is looked at before each post.
    pub fn finish(self, window: &Window, stop: &dyn Fn() -> bool) -> Py {
        let MagnetPlan {
            magnet,
            mode,
            as_of,
            sources,
            kept,
        } = self;
        let asks = sources.iter().any(|s| s.objects.is_some());
        let place = if asks { Place::take() } else { None };
        let mut allowed = if place.is_some() { UNCACHED_MOST } else { 0 };
        let mut said = Vec::with_capacity(sources.len());
        for mut source in sources {
            if let Some(work) = source.objects.take() {
                read_objects(
                    &mut source,
                    work,
                    window,
                    stop,
                    &mut allowed,
                    place.is_some(),
                );
            }
            said.push(dict([
                ("source", source.said),
                ("key", Py::Str(source.key)),
                ("status", Py::str(source.status)),
                ("reason", source.reason.map_or(Py::None, Py::Str)),
                ("summary", source.summary.unwrap_or(Py::None)),
                ("results", Py::List(source.results)),
                ("next", source.next),
                ("dates", source.dates),
            ]));
        }
        drop(place);
        let kept: Vec<Py> = kept
            .into_iter()
            .map(|facet| dict([("facet", Py::Str(facet)), ("reason", Py::str(KEPT_WHY))]))
            .collect();
        dict([
            ("magnet", Py::Str(magnet)),
            ("mode", Py::str(mode)),
            ("sources", Py::List(said)),
            ("kept", Py::List(kept)),
            ("cursor", reads::change_cursor(as_of)),
            ("uncached_most", Py::int(UNCACHED_MOST)),
        ])
    }
}

fn read_objects(
    source: &mut SourcePlan,
    work: ObjectsWork,
    window: &Window,
    stop: &dyn Fn() -> bool,
    allowed: &mut usize,
    placed: bool,
) {
    let ObjectsWork {
        plan,
        conversation,
        types,
        after,
    } = work;
    let mut may_extract = || {
        if *allowed == 0 {
            return false;
        }
        *allowed -= 1;
        true
    };
    let read = match plan.read_conversation_within(window, stop, &mut may_extract) {
        Ok(read) => read,
        Err(error) => {
            source.status = "partial";
            source.reason = Some(format!("its objects could not be read: {error}"));
            return;
        }
    };
    for object in read.rows {
        if after.is_some_and(|floor| as_f64(&object.at) < floor) {
            // Older pages are older still.
            source.next = Py::None;
            continue;
        }
        let Some(kind) = object_type(&object.row, &types) else {
            continue;
        };
        if !types.iter().any(|t| t == kind) {
            continue;
        }
        let id = object.row.get("address").cloned().unwrap_or(Py::None);
        source.results.push(dict([
            ("kind", Py::str(kind)),
            ("id", id),
            ("version", Py::Str(object.version)),
            (
                "conversation",
                Py::str(object.home.as_deref().unwrap_or(&conversation)),
            ),
            ("author", Py::opt_str(object.author.as_deref())),
            ("at", object.at),
            ("post", Py::Str(object.post)),
            ("value", object.row),
        ]));
    }
    if read.left > 0 || read.failed.is_some() {
        source.status = "partial";
        source.reason = Some(match read.failed {
            Some(why) => format!("{} posts' objects were not read: {why}", read.left),
            None if !placed => format!(
                "{} posts' objects were not read: other Magnets are reading objects; ask again",
                read.left
            ),
            None => format!(
                "{} posts' objects were not read yet: a request starts at most {UNCACHED_MOST} \
                 readings, and what it read is kept; ask again",
                read.left
            ),
        });
    }
}

/// Whether a page of these types reads objects at all, so a route reads the bundle only then.
pub fn reads_objects(types: Option<&[String]>, magnet: &MagnetDefinition) -> bool {
    match types.or(magnet.types.as_deref().filter(|t| !t.is_empty())) {
        Some(types) => types.iter().any(|t| OBJECT_TYPES.contains(&t.as_str())),
        None => true,
    }
}

/// The types `types=` may name.
pub fn is_information_type(word: &str) -> bool {
    ALL_TYPES.contains(&word)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn minimal(extra: &str) -> String {
        format!(
            r#"{{"id":"mag-a","sources":[{{"kind":"conversation","conversation":"ent-1"}},{{"kind":"web","domain":"x"}}],"selection":{{}}{extra}}}"#
        )
    }

    #[test]
    fn a_definition_says_its_sources_keys_as_the_client_does() {
        let d = MagnetDefinition::parse("mag-a", &minimal("")).unwrap();
        assert_eq!(d.sources[0].key, "conversation:ent-1");
        assert_eq!(d.sources[1].key, "web::x");
        assert!(d.sources[1].unavailable.is_some() && d.sources[0].unavailable.is_none());
    }

    #[test]
    fn an_unknown_schema_version_is_never_defaulted() {
        for later in [
            r#","schema_version":2"#,
            r#","schema_version":"1""#,
            r#","schema_version":0"#,
        ] {
            assert!(matches!(
                MagnetDefinition::parse("mag-a", &minimal(later)),
                Err(NotADefinition::LaterSchema(_))
            ));
        }
        assert!(MagnetDefinition::parse("mag-a", &minimal(r#","schema_version":1"#)).is_ok());
    }

    #[test]
    fn what_a_read_leans_on_is_checked() {
        for bad in ["{", "[]", r#"{"id":"mag-a"}"#] {
            assert!(matches!(
                MagnetDefinition::parse("mag-a", bad),
                Err(NotADefinition::Malformed(_))
            ));
        }
        assert!(MagnetDefinition::parse("mag-b", &minimal("")).is_err());
        assert!(MagnetDefinition::parse("../x", &minimal("")).is_err());
    }

    #[test]
    fn dates_are_read_or_said_never_guessed() {
        assert_eq!(epoch_of("1970-01-01"), Some(0.0));
        assert_eq!(epoch_of("1970-01-02"), Some(86_400.0));
        assert_eq!(epoch_of("2026-10-30T12:00:00Z"), Some(1_793_361_600.0));
        assert_eq!(epoch_of("2026-10-30T13:00:00+01:00"), Some(1_793_361_600.0));
        assert_eq!(epoch_of("2026-10-30T12:00"), Some(1_793_361_600.0));
        for odd in [
            "yesterday",
            "2026-13-01",
            "2026-1-1",
            "2026-10-30T25:00",
            "2026-10-30x",
        ] {
            assert_eq!(epoch_of(odd), None, "{odd}");
        }
    }
}
