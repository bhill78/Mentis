//! `find`: `Surface.find`, `worker.py:1800`. Locate things by identity, by coordinate, or by name. The
//! one read behind worker `find` and `GET /api/references?q=`, so the picker and the workers can't
//! disagree about what exists.
//!
//! **Its identity and text work is here, and its acquired material isn't.** R5.2 owns the source scan
//! `find`'s content hits come from, so **a Brain with a source declared forwards the whole request**
//! ([`acquired`] is the seam: what R5.2 replaces). There is no second scan and no half-answer.
//!
//! [`OpError::NotOwned`], beside that, so Python answers:
//!
//! - **A matching Turn with a fillable block,** whose `block` hits ask the render engine what it takes.
//! - **Whatever `resolve` keeps** (a held artifact, an Anchor, a form), asked by its identity.
//! - **What Python raises on:** a Participant, Conversation or Topic with no name that reads as text.
//! - **A bare number in other digits,** which `int` reads and `isdigit` doesn't always.
//!
//! **A step to a scope.** `find` reads every Turn of every Conversation at worst, which no one scope's
//! limit would hold. Each step's statements are fixed, and the scope goes between steps.

use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};
use std::time::Instant;

use mentis_record::{Flow, Id, Param, READ_SCOPE_LIMIT, ReadClass, ReadScope, RecordReader};
use mentis_rules::{
    Reading, alias_reads, now_reads, now_reads_walking_only_what_changed, standing_many,
};

use crate::pyjson::{self, Py, dict};
use crate::resolve::{Resolve, ResolveArgs, Resolved, Shape};
use crate::stored::Stored;
use crate::turn_line::turn_line;
use crate::window::python_says;
use crate::window::reads::{CONVERSATION, as_f64, links_from, links_to, number, text};
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest, python};

/// `search.PHRASE_CHARS`: a longer phrase is refused by the scan, and `not_searched` says none ran.
const PHRASE_CHARS: usize = 500;
/// How much a hit shows of its Turn.
const SAID_MAX: usize = 160;
/// How many Turns one step reads at most, while reading on.
const TURN_BATCH: usize = 100;

const PARTICIPANT: &str = "participant";
const IN_CONVERSATION_SQL: &str = "SELECT e.id, e.recorded_at FROM entry e \
     WHERE e.id IN (SELECT l.link_from FROM entry l \
                    WHERE l.link_relation = 'in-conversation' AND l.link_to = ?1) \
       AND e.family = 'entry' AND e.def_name = 'contribution' ORDER BY e.seq";

/// `corpus.operational(act=DECLARED)`, `sources/__init__.py:113`: is any source declared at all.
const ANY_DECLARED: &str =
    "SELECT 1 FROM operational WHERE act = 'source-collection-declared' LIMIT 1";

/// `entries_of_kind`.
const OF_KIND: &str = "SELECT id FROM entry \
     WHERE def_name = ?1 AND family = 'entry' AND link_relation IS NULL ORDER BY seq";

/// `corpus.superseding_relation()`.
const SUPERSEDING: &str = "SELECT json_extract(body, '$.relation') FROM entry \
     WHERE family = 'definition' AND json_extract(body, '$.substrate_role') = 'supersedes' \
     ORDER BY seq LIMIT 1";

/// `Conversations.topics`, for many: each Topic once under each home, in the order `read` gives them.
const TOPICS: &str = "SELECT DISTINCT l.link_to, e.id, e.seq FROM entry l \
     JOIN entry e ON e.id = l.link_from \
     WHERE l.link_relation = 'topic-of' \
       AND l.link_to IN (SELECT value FROM json_each(?1)) ORDER BY e.seq";

/// `corpus.links(relation=needle)`.
const LINKS_OF: &str = "SELECT id, link_from, link_to FROM entry \
     WHERE link_relation IS NOT NULL AND link_relation = ?1 ORDER BY seq";

/// What `find` asks.
#[derive(Clone, Debug)]
pub struct FindAsk {
    pub q: String,
    pub limit: usize,
    /// `here`: decides a coordinate, and what's offered first. Never a filter.
    pub here: Option<String>,
}

/// One step of the walk, in a scope of its own.
struct Step<F>(F);

impl<T, F> ReadOp for Step<F>
where
    T: Send,
    F: Fn(&mut dyn ReadScope) -> Result<T, OpError> + Send + Sync,
{
    type Args = ();
    type Row = crate::window::Prepared<T>;

    const NAME: &'static str = "find";
    /// The worst step: every Participant and every Conversation, each of [`all_of_kind`]'s five
    /// statements and the walk of those renamed.
    const BUDGET: Budget = Budget {
        statements: 2 * (5 + mentis_rules::STATEMENTS),
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        _request: &ReadRequest<()>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let at = scope.position();
        Ok(ReadAnswer {
            rows: vec![crate::window::Prepared((self.0)(scope)?)],
            as_of: at,
            more: None,
            not_searched: Vec::new(),
        })
    }
}

fn step<T: Send>(
    record: &dyn RecordReader,
    class: ReadClass,
    read: impl Fn(&mut dyn ReadScope) -> Result<T, OpError> + Send + Sync,
) -> Result<T, OpError> {
    let request = ReadRequest {
        args: (),
        cursor: None,
        limit: None,
        deadline: Instant::now() + READ_SCOPE_LIMIT,
    };
    let mut got = crate::run(&Step(read), record, class, &request)?;
    let crate::window::Prepared(row) = got
        .rows
        .pop()
        .ok_or_else(|| python_says("a step with no answer"))?;
    Ok(row)
}

/// Each entry of a Kind that isn't a later version of another, as it now reads: `all_conversations` and
/// `all_participants`, with their quirk. Only what something supersedes is read through `presented`, and
/// not even that where nothing of the Kind is a later version.
fn all_of_kind(scope: &mut dyn ReadScope, kind: &str) -> Result<Vec<(String, Py)>, OpError> {
    let mut ids: Vec<String> = Vec::new();
    scope.query(OF_KIND, &[Param::Text(kind)], &mut |row| {
        ids.push(text(row, 0)?.unwrap_or_default());
        Ok(Flow::Continue)
    })?;
    if ids.is_empty() {
        return Ok(Vec::new());
    }
    let mut relation = None;
    scope.query(SUPERSEDING, &[], &mut |row| {
        relation = text(row, 0)?;
        Ok(Flow::Stop)
    })?;
    let relation = relation.unwrap_or_default();
    let named: Vec<&str> = ids.iter().map(String::as_str).collect();
    let later: HashSet<String> = links_from(scope, &relation, &named)?
        .into_iter()
        .map(|link| link.from)
        .collect();
    let renamed: HashSet<String> = if later.is_empty() {
        HashSet::new()
    } else {
        links_to(scope, &relation, &named)?
            .into_iter()
            .map(|link| link.to)
            .collect()
    };
    let keeping: Vec<Id> = ids
        .iter()
        .filter(|id| !later.contains(*id))
        .map(|id| Id(id.clone()))
        .collect();
    let walking: Vec<Id> = keeping
        .iter()
        .filter(|id| renamed.contains(&id.0))
        .cloned()
        .collect();
    let seen = now_reads(scope, &walking)?;
    let raw = raw_bodies(scope, &keeping)?;
    let mut out = Vec::with_capacity(keeping.len());
    for id in keeping {
        let body = if renamed.contains(&id.0) {
            let reading = seen
                .get(&id)
                .ok_or_else(|| python_says("an entry that went between two reads"))?;
            if reading.python_says {
                return Err(python_says("an entry Python has to read"));
            }
            pyjson::loads(&reading.body_json)
        } else {
            raw.get(&id.0).and_then(|body| pyjson::loads(body))
        };
        out.push((
            id.0,
            body.ok_or_else(|| python_says("a body this can't read"))?,
        ));
    }
    Ok(out)
}

const BODIES_OF: &str = "SELECT id, body FROM entry WHERE id IN (SELECT value FROM json_each(?1))";

fn raw_bodies(scope: &mut dyn ReadScope, ids: &[Id]) -> Result<HashMap<String, String>, OpError> {
    let list = mentis_rules::id_list(ids.iter().map(|id| id.0.as_str()));
    let mut out = HashMap::with_capacity(ids.len());
    scope.query(BODIES_OF, &[Param::Text(&list)], &mut |row| {
        out.insert(
            text(row, 0)?.unwrap_or_default(),
            text(row, 1)?.unwrap_or_default(),
        );
        Ok(Flow::Continue)
    })?;
    Ok(out)
}

/// `body[name]` as text, and `.lower()` of it: what Python raises on, a missing or a mistyped name, is
/// Python's to say.
fn name_of<'a>(body: &'a Py, field: &str) -> Result<(&'a str, String), OpError> {
    let name = body
        .get(field)
        .and_then(Py::as_str)
        .ok_or_else(|| python_says("a name that isn't text"))?;
    let lowered =
        python::lower(name).ok_or_else(|| python_says("a name in letters newer than Python's"))?;
    Ok((name, lowered))
}

/// `Conversations.topics` for each Conversation: home -> (Topic, body), in `read`'s order.
fn topics_of(
    scope: &mut dyn ReadScope,
    conversations: &[&str],
) -> Result<HashMap<String, Vec<(String, Py)>>, OpError> {
    let list = mentis_rules::id_list(conversations.iter().copied());
    let mut rows: Vec<(String, String)> = Vec::new();
    scope.query(TOPICS, &[Param::Text(&list)], &mut |row| {
        rows.push((
            text(row, 0)?.unwrap_or_default(),
            text(row, 1)?.unwrap_or_default(),
        ));
        Ok(Flow::Continue)
    })?;
    let ids: Vec<Id> = {
        let mut ids: Vec<Id> = rows.iter().map(|(_, topic)| Id(topic.clone())).collect();
        ids.sort();
        ids.dedup();
        ids
    };
    let readings = now_reads_walking_only_what_changed(scope, &ids)?;
    let mut out: HashMap<String, Vec<(String, Py)>> = HashMap::new();
    for (home, topic) in rows {
        let reading = readings
            .get(&Id(topic.clone()))
            .ok_or_else(|| python_says("a Topic that went between two reads"))?;
        if reading.python_says {
            return Err(python_says("a Topic Python has to read"));
        }
        let body = pyjson::loads(&reading.body_json)
            .ok_or_else(|| python_says("a body this can't read"))?;
        out.entry(home).or_default().push((topic, body));
    }
    Ok(out)
}

/// One Conversation's Turns, in `contributions`' order, with the time they're numbered by.
fn turns_of(scope: &mut dyn ReadScope, conversation: &str) -> Result<Vec<(String, f64)>, OpError> {
    let mut rows = Vec::new();
    scope.query(
        IN_CONVERSATION_SQL,
        &[Param::Text(conversation)],
        &mut |row| {
            rows.push((text(row, 0)?.unwrap_or_default(), as_f64(&number(row, 1)?)));
            Ok(Flow::Continue)
        },
    )?;
    Ok(rows)
}

/// `Conversations.turns`' numbering: by time, stably, from 1.
fn numbered(turns: &[(String, f64)]) -> Vec<&str> {
    let mut ordered: Vec<&(String, f64)> = turns.iter().collect();
    ordered.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(Ordering::Equal));
    ordered.into_iter().map(|(id, _)| id.as_str()).collect()
}

/// `_FILL_FENCE.search(said)`: does this line of the Turn's text open a fillable block.
fn has_fill_fence(said: &str) -> bool {
    said.split('\n').any(|line| {
        let line = line.trim_start_matches([' ', '\t']);
        let Some(mark) = line.chars().next().filter(|c| matches!(c, '`' | '~')) else {
            return false;
        };
        let run = line.chars().take_while(|c| *c == mark).count();
        if run < 3 {
            return false;
        }
        let info = line[run..].trim_start_matches([' ', '\t']);
        // `\b` would refuse `formal`: the cheap test forwards it, which is always correct.
        ["form", "checklist", "table", "pad", "panel"]
            .iter()
            .any(|word| info.starts_with(word))
    })
}

fn first_chars(text: &str, most: usize) -> String {
    text.chars().take(most).collect()
}

fn stored_py(value: &Stored) -> Result<Py, OpError> {
    pyjson::loads(value.text()).ok_or_else(|| python_says("a stored value this can't read"))
}

/// The row an identity's `resolve` becomes: `got.get("name") or got.get("alias")`, its number and where.
fn identity_row(needle: &str, got: &Resolved) -> Result<Py, OpError> {
    let mut name = Py::None;
    let mut number = Py::None;
    let mut conversation = Py::None;
    let mut said = Py::None;
    match &got.shape {
        Shape::Turn {
            conversation: home,
            number: at,
            said: words,
            ..
        } => {
            conversation = Py::opt_str(home.as_deref());
            number = at.map_or(Py::None, Py::int);
            said = Py::str(words.as_str());
        }
        Shape::Conversation { name: named, .. } => {
            let named = stored_py(named)?;
            if named.truthy() {
                name = named;
            }
        }
        Shape::Participant { alias, .. } => name = Py::opt_str(alias.as_deref()),
        Shape::Topic {
            name: named,
            conversation: home,
            ..
        } => {
            let named = stored_py(named)?;
            if named.truthy() {
                name = named;
            }
            conversation = Py::opt_str(home.as_deref());
        }
        Shape::Reaction { .. } | Shape::Other { .. } => {}
    }
    let what = got
        .kind
        .as_deref()
        .filter(|kind| !kind.is_empty())
        .unwrap_or("entry");
    Ok(dict([
        ("what", Py::str(what)),
        ("ref", Py::str(needle)),
        ("exact", Py::str("identity")),
        ("name", name),
        ("number", number),
        ("conversation", conversation),
        ("said", said),
    ]))
}

/// `ENTRY_REF`, of what's already lower case.
fn is_entry_ref(needle: &str) -> bool {
    let Some(hex) = ["ent-", "opr-", "adm-"]
        .iter()
        .find_map(|prefix| needle.strip_prefix(prefix))
    else {
        return false;
    };
    !hex.is_empty() && hex.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

/// What `_acquired_hits` and `_content_hits` add, for a Brain with nothing declared: no hits, and the
/// `not_searched` of a scan of nothing, or of no scan at all past the phrase's limit.
///
/// **The seam R5.2 replaces.** A Brain with a source declared forwards, which is `find`'s whole request.
fn acquired(scope: &mut dyn ReadScope) -> Result<(), OpError> {
    let mut any = false;
    scope.query(ANY_DECLARED, &[], &mut |_| {
        any = true;
        Ok(Flow::Stop)
    })?;
    if any {
        return Err(python_says(
            "acquired material: R5.2's source scan answers it",
        ));
    }
    Ok(())
}

fn nothing_scanned(raw: &str) -> Py {
    let phrase = raw.trim_start_matches(['@', '#']);
    if python::strip(phrase).chars().count() > PHRASE_CHARS {
        return Py::None;
    }
    dict([
        ("non_text", Py::int(0)),
        ("by_type", Py::Dict(Vec::new())),
        ("extraction", Py::Dict(Vec::new())),
        ("extraction_files", Py::List(Vec::new())),
        ("unreadable", Py::int(0)),
        ("unreadable_files", Py::List(Vec::new())),
        ("over_budget", Py::int(0)),
    ])
}

fn resolve_identity(
    record: &dyn RecordReader,
    class: ReadClass,
    needle: &str,
) -> Result<Option<Py>, OpError> {
    let request = ReadRequest {
        args: ResolveArgs {
            reference: needle.to_owned(),
        },
        cursor: None,
        limit: None,
        deadline: Instant::now() + READ_SCOPE_LIMIT,
    };
    match crate::run(&Resolve, record, class, &request) {
        Ok(mut got) => {
            let row = got
                .rows
                .pop()
                .ok_or_else(|| python_says("resolve answered nothing"))?;
            Ok(Some(identity_row(needle, &row)?))
        }
        Err(OpError::NotFound { .. }) => Ok(None),
        Err(other) => Err(other),
    }
}

/// `self._entry(ref)`'s body's `name`, or nothing if the record doesn't hold it. Past that, whatever
/// the name is, as stored.
fn conversation_name_now(
    readings: &HashMap<Id, Reading>,
    conversation: &str,
) -> Result<Py, OpError> {
    let Some(reading) = readings.get(&Id(conversation.to_owned())) else {
        return Ok(Py::None);
    };
    if reading.python_says {
        return Err(python_says("a Conversation Python has to read"));
    }
    let body =
        pyjson::loads(&reading.body_json).ok_or_else(|| python_says("a body this can't read"))?;
    if !body.is_dict() {
        return Err(python_says("a body that isn't an object"));
    }
    Ok(body.get("name").cloned().unwrap_or(Py::None))
}

/// The coordinate grammar: the Turn at this number in each Conversation in scope.
fn coordinate(
    record: &dyn RecordReader,
    class: ReadClass,
    number: i128,
    scope_ids: &[String],
) -> Result<Vec<Py>, OpError> {
    let mut exact = Vec::new();
    for cid in scope_ids {
        let found = step(record, class, |scope| {
            let turns = turns_of(scope, cid)?;
            let ordered = numbered(&turns);
            let Some(tid) = usize::try_from(number)
                .ok()
                .and_then(|at| at.checked_sub(1))
                .and_then(|at| ordered.get(at))
            else {
                return Ok(None);
            };
            let tid = Id((*tid).to_owned());
            let asked = [tid.clone(), Id(cid.clone())];
            let readings = now_reads_walking_only_what_changed(scope, &asked)?;
            let reading = readings
                .get(&tid)
                .ok_or_else(|| python_says("a Turn that went between two reads"))?;
            if reading.python_says {
                return Err(python_says("a Turn Python has to read"));
            }
            Ok(Some((
                tid.0.clone(),
                conversation_name_now(&readings, cid)?,
                first_chars(&turn_line(reading)?, SAID_MAX),
            )))
        })?;
        if let Some((tid, name, said)) = found {
            exact.push(dict([
                ("what", Py::str("turn")),
                ("ref", Py::Str(tid)),
                ("exact", Py::str("coordinate")),
                ("conversation", Py::str(cid.as_str())),
                ("conversation_name", name),
                ("number", Py::int(number)),
                ("said", Py::Str(said)),
            ]));
        }
    }
    Ok(exact)
}

/// One link of the relation asked about, read for its row.
struct LinkHit {
    id: String,
    from: String,
    to: String,
}

/// `LINKS OF A NAMED RELATION`: a Link's relation is its name.
fn link_rows(scope: &mut dyn ReadScope, relation: &str) -> Result<Vec<Py>, OpError> {
    let mut hits: Vec<LinkHit> = Vec::new();
    scope.query(LINKS_OF, &[Param::Text(relation)], &mut |row| {
        hits.push(LinkHit {
            id: text(row, 0)?.unwrap_or_default(),
            from: text(row, 1)?.unwrap_or_default(),
            to: text(row, 2)?.unwrap_or_default(),
        });
        Ok(Flow::Continue)
    })?;
    if hits.is_empty() {
        return Ok(Vec::new());
    }
    let ids: Vec<Id> = hits.iter().map(|hit| Id(hit.id.clone())).collect();
    let standing = standing_many(scope, &ids, None)?;
    let froms: Vec<Id> = {
        let mut froms: Vec<Id> = hits.iter().map(|hit| Id(hit.from.clone())).collect();
        froms.sort();
        froms.dedup();
        froms
    };
    let aliases = alias_reads(scope, &froms)?;
    let mut out = Vec::with_capacity(hits.len());
    for hit in hits {
        let stands = standing
            .get(&Id(hit.id.clone()))
            .ok_or_else(|| python_says("no standing"))?
            .stands;
        let alias = aliases
            .get(&Id(hit.from.clone()))
            .ok_or_else(|| python_says("no alias"))?
            .as_ref()
            .ok_or_else(|| python_says("an alias this can't read"))?
            .clone()
            .unwrap_or_else(|| hit.from.clone());
        out.push(dict([
            ("what", Py::str("link")),
            ("ref", Py::Str(hit.id)),
            ("relation", Py::str(relation)),
            ("links_from", Py::Str(hit.from)),
            ("links_to", Py::Str(hit.to)),
            ("stands", Py::Bool(stands)),
            ("name", Py::Str(format!("{relation}: {alias}"))),
        ]));
    }
    Ok(out)
}

/// `Surface.find`: what's answered here for a Brain with no source declared, and `NotOwned` otherwise.
/// Blocking.
pub fn find(record: &dyn RecordReader, class: ReadClass, ask: &FindAsk) -> Result<Py, OpError> {
    let raw = python::strip(&ask.q);
    let lowered = python::lower(raw).ok_or_else(|| python_says("a question in newer letters"))?;
    if !lowered.trim_start_matches(['@', '#']).is_empty() {
        step(record, class, acquired)?;
    }
    record_hits(record, class, ask)
}

/// `find`'s identity and text work: exact, block and record hits, and what a scan of nothing says. What
/// R5.2's acquired hits go after. Blocking.
pub fn record_hits(
    record: &dyn RecordReader,
    class: ReadClass,
    ask: &FindAsk,
) -> Result<Py, OpError> {
    let raw = python::strip(&ask.q);
    let lowered = python::lower(raw).ok_or_else(|| python_says("a question in newer letters"))?;
    let needle = lowered.trim_start_matches(['@', '#']);
    if needle.is_empty() {
        return Ok(dict([
            ("found", Py::List(Vec::new())),
            ("matched", Py::int(0)),
            ("why_not", Py::str("nothing to search for")),
        ]));
    }

    let (participants, conversations) = step(record, class, |scope| {
        Ok((
            all_of_kind(scope, PARTICIPANT)?,
            all_of_kind(scope, CONVERSATION)?,
        ))
    })?;
    let cids: Vec<&str> = conversations.iter().map(|(id, _)| id.as_str()).collect();

    let mut exact: Vec<Py> = Vec::new();
    if is_entry_ref(needle)
        && let Some(row) = resolve_identity(record, class, needle)?
    {
        exact.push(row);
    }
    // `needle.isdigit()`: past ASCII, `int` reads what it reads and raises on some.
    if !needle.is_ascii() && needle.chars().all(char::is_numeric) {
        return Err(python_says("a number in other digits"));
    }
    if needle.bytes().all(|b| b.is_ascii_digit()) {
        let at = match python::int(needle) {
            python::PythonInt::Value(at) => at,
            _ => return Err(python_says("a number past what `int` reads")),
        };
        let scope_ids: Vec<String> = match &ask.here {
            Some(here) if !here.is_empty() => vec![here.clone()],
            _ => cids.iter().map(|id| (*id).to_owned()).collect(),
        };
        exact.extend(coordinate(record, class, at, &scope_ids)?);
    }

    let mut found: Vec<Py> = Vec::new();
    for (id, body) in &participants {
        let (alias, lowered) = name_of(body, "alias")?;
        if lowered.contains(needle) {
            found.push(dict([
                ("what", Py::str(PARTICIPANT)),
                ("ref", Py::str(id.as_str())),
                ("name", Py::str(alias)),
            ]));
        }
    }
    let topics = step(record, class, |scope| topics_of(scope, &cids))?;
    for (id, body) in &conversations {
        let (name, lowered) = name_of(body, "name")?;
        if lowered.contains(needle) {
            found.push(dict([
                ("what", Py::str(CONVERSATION)),
                ("ref", Py::str(id.as_str())),
                ("name", Py::str(name)),
            ]));
        }
        for (topic, body) in topics.get(id).map_or(&[][..], Vec::as_slice) {
            let (name, lowered) = name_of(body, "name")?;
            if lowered.contains(needle) {
                found.push(dict([
                    ("what", Py::str("topic")),
                    ("ref", Py::str(topic.as_str())),
                    ("name", Py::str(name)),
                    ("conversation", Py::str(id.as_str())),
                ]));
            }
        }
    }
    if needle.contains('-') {
        found.extend(step(record, class, |scope| link_rows(scope, needle))?);
    }

    let seen: HashSet<String> = exact
        .iter()
        .filter_map(|row| row.get("ref").and_then(Py::as_str))
        .map(str::to_owned)
        .collect();
    let cap = ask.limit.saturating_mul(3);
    for (cid, body) in &conversations {
        let conversation_name = name_of(body, "name")?.0;
        let turns = step(record, class, |scope| turns_of(scope, cid))?;
        let walking: Vec<&(String, f64)> =
            turns.iter().filter(|(id, _)| !seen.contains(id)).collect();
        let mut numbers: Option<HashMap<&str, usize>> = None;
        let mut at = 0;
        'walk: while at < walking.len() {
            // Past the cap only the next Turn of this Conversation is read.
            let size = if found.len() >= cap { 1 } else { TURN_BATCH };
            let batch = &walking[at..walking.len().min(at + size)];
            let ids: Vec<Id> = batch.iter().map(|(id, _)| Id(id.clone())).collect();
            let readings = step(record, class, |scope| {
                now_reads_walking_only_what_changed(scope, &ids).map_err(OpError::from)
            })?;
            for (id, _) in batch {
                let reading = readings
                    .get(&Id(id.clone()))
                    .ok_or_else(|| python_says("a Turn that went between two reads"))?;
                if reading.python_says {
                    return Err(python_says("a Turn Python has to read"));
                }
                let said = turn_line(reading)?;
                let low =
                    python::lower(&said).ok_or_else(|| python_says("words in newer letters"))?;
                if low.contains(needle) {
                    if has_fill_fence(&said) {
                        return Err(python_says(
                            "a matching Turn with a fillable block: the render engine",
                        ));
                    }
                    let numbering = numbers.get_or_insert_with(|| {
                        let mut out = HashMap::with_capacity(turns.len());
                        for (n, tid) in numbered(&turns).into_iter().enumerate() {
                            out.entry(tid).or_insert(n + 1);
                        }
                        out
                    });
                    found.push(dict([
                        ("what", Py::str("turn")),
                        ("ref", Py::str(id.as_str())),
                        ("conversation", Py::str(cid.as_str())),
                        ("conversation_name", Py::str(conversation_name)),
                        (
                            "number",
                            numbering.get(id.as_str()).map_or(Py::None, |n| Py::int(*n)),
                        ),
                        ("said", Py::Str(first_chars(&said, SAID_MAX))),
                    ]));
                }
                at += 1;
                if found.len() >= cap {
                    break 'walk;
                }
            }
        }
    }

    // `here` doesn't filter: it only decides what is offered first.
    if let Some(here) = ask.here.as_deref().filter(|here| !here.is_empty()) {
        found.sort_by_key(|row| {
            i32::from(row.get("conversation").and_then(Py::as_str) != Some(here))
        });
    }

    let exact_count = exact.len();
    let mut rows = exact;
    rows.extend(found);
    let matched = rows.len();
    rows.truncate(ask.limit);
    Ok(dict([
        ("found", Py::List(rows)),
        ("matched", Py::int(matched)),
        ("exact", Py::int(exact_count)),
        ("ambiguous", Py::Bool(exact_count > 1)),
        ("not_returned", Py::int(matched.saturating_sub(ask.limit))),
        ("not_searched", nothing_scanned(raw)),
        (
            "pending",
            dict([
                ("extractions", Py::int(0)),
                ("by_type", Py::Dict(Vec::new())),
            ]),
        ),
    ]))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_fence_is_as_the_cheap_test_reads_it_or_wider() {
        assert!(has_fill_fence("```form name=x"));
        assert!(has_fill_fence("words\n \t~~~~ checklist\n"));
        assert!(has_fill_fence("```table"));
        assert!(has_fill_fence("```formal"));
        assert!(!has_fill_fence("``form"));
        assert!(!has_fill_fence("a ```form"));
        assert!(!has_fill_fence("```chart"));
        assert!(!has_fill_fence("\r```form"));
    }

    #[test]
    fn an_entry_ref_is_lower_case_hex_after_its_prefix() {
        assert!(is_entry_ref("ent-0a"));
        assert!(is_entry_ref("adm-9"));
        assert!(!is_entry_ref("ent-"));
        assert!(!is_entry_ref("ent-xyz"));
        assert!(!is_entry_ref("def-0a"));
    }

    #[test]
    fn a_phrase_past_the_scan_s_limit_has_no_scan_to_report() {
        assert!(matches!(nothing_scanned("#word"), Py::Dict(_)));
        assert_eq!(nothing_scanned(&"x".repeat(501)), Py::None);
        assert!(matches!(nothing_scanned(&"x".repeat(500)), Py::Dict(_)));
    }

    #[test]
    fn numbering_is_by_time_and_stable() {
        let turns = vec![
            ("a".to_owned(), 2.0),
            ("b".to_owned(), 1.0),
            ("c".to_owned(), 2.0),
        ];
        assert_eq!(numbered(&turns), ["b", "a", "c"]);
    }
}
