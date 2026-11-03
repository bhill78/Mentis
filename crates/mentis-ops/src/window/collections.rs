//! `GET /fluid/api/collections/conversation` and `collections/thread`: ordered ids and paging cursors,
//! never bodies. `read.conversation_collection`, `read.thread_collection`.

use std::collections::HashMap;

use mentis_record::{Flow, Id, Param, ReadScope, Value};

use super::reads::{
    self, ABOUT_TOPIC, CONTRIBUTION, CONVERSATION, IN_CONVERSATION, LINKED_INTO, Link, REPLIES_TO,
    TOPIC_OF, as_f64, by_home, closures, homes_of, in_force, links_from, links_to, number,
    page_cursor, text,
};
use super::{bad_request, python_says};
use crate::pyjson::{Py, dict, repr};
use crate::python::{self, PythonInt};
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest};

/// `members_page`, verbatim but for its parameters: `?1` to, `?2` home, `?3` kind, `?4` replies,
/// `?5` also, `?6` only, `?7` roots, `?8` limit, and `?9`, `?10` a cursor. One text for each way of
/// paging, because a statement is text in the source.
macro_rules! members_page {
    ($cursor:literal, $direction:literal) => {
        concat!(
            "WITH home AS (",
            " SELECT DISTINCT e.id, e.seq, e.recorded_at",
            " FROM entry l JOIN entry e ON e.id = l.link_from",
            " WHERE l.link_to = ?1 AND l.link_relation = ?2",
            " AND e.family = 'entry' AND e.def_name = ?3",
            " AND e.link_relation IS NULL),",
            " numbered AS (",
            " SELECT id, seq, recorded_at,",
            " ROW_NUMBER() OVER (ORDER BY recorded_at, seq) AS number",
            " FROM home),",
            " everyone AS (",
            " SELECT id, seq, recorded_at, number FROM numbered",
            " UNION ALL",
            " SELECT e.id, e.seq, e.recorded_at, NULL FROM entry e",
            " WHERE e.id IN (SELECT value FROM json_each(?5))",
            " AND e.id NOT IN (SELECT id FROM home)),",
            " scope AS (",
            " SELECT * FROM everyone",
            " WHERE ?6 IS NULL",
            " OR id IN (SELECT value FROM json_each(?6))),",
            " parented AS (",
            " SELECT a.*, (SELECT r.link_to FROM entry r",
            " WHERE r.link_from = a.id",
            " AND r.link_relation = ?4",
            " ORDER BY r.seq LIMIT 1) AS parent",
            " FROM scope a),",
            " units AS (",
            " SELECT p.*,",
            " ROW_NUMBER() OVER (ORDER BY recorded_at, seq) AS pos,",
            " COUNT(*) OVER () AS total",
            " FROM parented p",
            " WHERE ?7 = 0 OR parent IS NULL",
            " OR parent NOT IN (SELECT id FROM everyone))",
            " SELECT id, seq, recorded_at, number, parent, pos, total",
            " FROM units ",
            $cursor,
            " ORDER BY recorded_at ",
            $direction,
            ", seq ",
            $direction,
            " LIMIT ?8"
        )
    };
}

const PAGE_NEWEST: &str = members_page!("", "DESC");
const PAGE_BEFORE: &str = members_page!("WHERE (recorded_at, seq) < (?9, ?10)", "DESC");
const PAGE_AFTER: &str = members_page!("WHERE (recorded_at, seq) > (?9, ?10)", "ASC");

const KIND_OF: &str = "SELECT family, def_name, link_relation FROM entry WHERE id = ?1";

/// `_later_versions`.
const LATER: &str = "SELECT 1 FROM entry WHERE link_from = ?1 AND link_relation = \
     (SELECT json_extract(body, '$.relation') FROM entry \
      WHERE family = 'definition' AND json_extract(body, '$.substrate_role') = 'supersedes' \
      ORDER BY seq LIMIT 1) LIMIT 1";

/// `(recorded_at, seq)`, as `_page_key` reads one: `float` and `int`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct PageKey {
    at: f64,
    seq: i64,
}

/// `_page_key`. A cursor it gave out, or a member's id. Past the plain spellings of a number, what
/// `float` and `int` accept is Python's to read.
fn page_key(scope: &mut dyn ReadScope, raw: Option<&str>) -> Result<Option<PageKey>, OpError> {
    let Some(raw) = raw.filter(|raw| !raw.is_empty()) else {
        return Ok(None);
    };
    if raw.starts_with("ent-") || raw.starts_with("adm-") {
        let got = reads::heads(scope, &[raw])?;
        let Some(head) = got.get(raw) else {
            let shown = repr(raw).ok_or_else(|| python_says("a cursor to show in other words"))?;
            return Err(bad_request(format!("no such entry to page from: {shown}")));
        };
        return Ok(Some(PageKey {
            at: as_f64(&head.recorded_at),
            seq: head.seq,
        }));
    }
    let not_a_cursor = || -> OpError {
        match repr(raw) {
            Some(shown) => bad_request(format!("not a paging cursor: {shown}")),
            None => python_says("a cursor to show in other words"),
        }
    };
    let Some((at, seq)) = raw.rsplit_once('_') else {
        return Err(not_a_cursor());
    };
    let plain_float = !at.is_empty()
        && at
            .bytes()
            .all(|b| b.is_ascii_digit() || matches!(b, b'.' | b'-' | b'+' | b'e' | b'E'));
    let Some(at) = at.parse::<f64>().ok().filter(|_| plain_float) else {
        return Err(python_says("a cursor's time that Python has to read"));
    };
    match python::int(seq) {
        PythonInt::Value(seq) => match i64::try_from(seq) {
            Ok(seq) => Ok(Some(PageKey { at, seq })),
            Err(_) => Err(python_says("a cursor's place past what a row can hold")),
        },
        PythonInt::NotInt => Err(not_a_cursor()),
        PythonInt::Unsure => Err(python_says("a cursor's place in other digits")),
    }
}

/// `_window`: `(before, after)`.
fn page_window(
    scope: &mut dyn ReadScope,
    before: Option<&str>,
    after: Option<&str>,
    start: Option<&str>,
) -> Result<(Option<PageKey>, Option<PageKey>), OpError> {
    if [before, after, start].iter().flatten().count() > 1 {
        return Err(bad_request(
            "page before a position, after it or from it -- one".to_owned(),
        ));
    }
    let Some(start) = start.filter(|start| !start.is_empty()) else {
        let before = page_key(scope, before)?;
        let after = page_key(scope, after)?;
        return Ok((before, after));
    };
    if start == "start" {
        return Ok((
            None,
            Some(PageKey {
                at: f64::NEG_INFINITY,
                seq: 0,
            }),
        ));
    }
    let key = page_key(scope, Some(start))?.expect("`start` isn't empty");
    Ok((
        None,
        Some(PageKey {
            at: key.at,
            seq: key.seq - 1,
        }),
    ))
}

/// One row of `members_page`.
#[derive(Clone, Debug)]
struct Member {
    id: String,
    seq: i64,
    at: Py,
    number: Option<i64>,
    parent: Option<String>,
    pos: i64,
}

struct Page {
    rows: Vec<Member>,
    total: Option<i64>,
}

struct Scoped<'a> {
    conversation: &'a str,
    also: &'a [&'a str],
    only: Option<&'a [String]>,
    roots: bool,
}

fn members_page(
    scope: &mut dyn ReadScope,
    what: &Scoped<'_>,
    before: Option<PageKey>,
    after: Option<PageKey>,
    limit: u32,
) -> Result<Page, OpError> {
    let also = mentis_rules::id_list(what.also.iter().copied());
    let only = what
        .only
        .map(|only| mentis_rules::id_list(only.iter().map(String::as_str)));
    let mut params = vec![
        Param::Text(what.conversation),
        Param::Text(IN_CONVERSATION),
        Param::Text(CONTRIBUTION),
        Param::Text(REPLIES_TO),
        Param::Text(&also),
        only.as_deref().map_or(Param::Null, Param::Text),
        Param::Integer(i64::from(what.roots)),
        Param::Integer(i64::from(limit.max(1))),
    ];
    let (sql, ascending) = if let Some(key) = before {
        params.push(Param::Real(key.at));
        params.push(Param::Integer(key.seq));
        (PAGE_BEFORE, false)
    } else if let Some(key) = after {
        params.push(Param::Real(key.at));
        params.push(Param::Integer(key.seq));
        (PAGE_AFTER, true)
    } else {
        (PAGE_NEWEST, false)
    };
    let mut rows = Vec::new();
    let mut total = None;
    scope.query(sql, &params, &mut |row| {
        total = Some(row.value(6)?.integer().unwrap_or_default());
        rows.push(Member {
            id: text(row, 0)?.unwrap_or_default(),
            seq: row.value(1)?.integer().unwrap_or_default(),
            at: number(row, 2)?,
            number: row.value(3)?.integer(),
            parent: text(row, 4)?,
            pos: row.value(5)?.integer().unwrap_or_default(),
        });
        Ok(Flow::Continue)
    })?;
    if !ascending {
        rows.reverse();
    }
    Ok(Page { rows, total })
}

/// `read.conversation_scope`: the posts included from elsewhere, each once. A Conversation's own posts
/// are `members_page`'s to select.
pub(crate) fn conversation_scope(
    scope: &mut dyn ReadScope,
    cid: &str,
) -> Result<Vec<String>, OpError> {
    let mut kind: Option<String> = None;
    let mut found = false;
    scope.query(KIND_OF, &[Param::Text(cid)], &mut |row| {
        found = true;
        kind = text(row, 1)?;
        Ok(Flow::Stop)
    })?;
    if !found || kind.as_deref() != Some(CONVERSATION) {
        let shown = repr(cid).ok_or_else(|| python_says("an id to show in other words"))?;
        return Err(bad_request(format!("not a conversation: {shown}")));
    }
    let linked = links_to(scope, LINKED_INTO, &[cid])?;
    let linked = in_force(scope, linked)?;
    let mut also: Vec<String> = Vec::with_capacity(linked.len());
    for link in linked {
        if !also.contains(&link.from) {
            also.push(link.from);
        }
    }
    Ok(also)
}

/// `_page_key`, for what pages by a post or a cursor beside the collection.
pub(crate) fn page_key_of(
    scope: &mut dyn ReadScope,
    raw: Option<&str>,
) -> Result<Option<PageKey>, OpError> {
    page_key(scope, raw)
}

/// One post of [`posts_page`].
pub(crate) struct PagePost {
    pub id: String,
    pub at: Py,
    pub number: Option<i64>,
    pub key: PageKey,
}

/// `members_page(roots=False)`, oldest first, with what `before=` asks for to continue from each.
pub(crate) fn posts_page(
    scope: &mut dyn ReadScope,
    cid: &str,
    also: &[&str],
    before: Option<PageKey>,
    limit: u32,
) -> Result<Vec<PagePost>, OpError> {
    let what = Scoped {
        conversation: cid,
        also,
        only: None,
        roots: false,
    };
    let page = members_page(scope, &what, before, None, limit)?;
    Ok(page
        .rows
        .into_iter()
        .map(|row| PagePost {
            key: PageKey {
                at: as_f64(&row.at),
                seq: row.seq,
            },
            id: row.id,
            at: row.at,
            number: row.number,
        })
        .collect())
}

/// What `objects?conversation=` needs of a page, beside its shape.
#[derive(Clone, Debug)]
pub struct Collected {
    pub answer: Py,
    pub ids: Vec<String>,
    pub before: Py,
    pub total: i64,
}

/// What a request said.
#[derive(Clone, Debug, Default)]
pub struct ConversationArgs {
    pub id: String,
    pub before: Option<String>,
    pub after: Option<String>,
    pub start: Option<String>,
    /// As sent. `None` means `threads`.
    pub shape: Option<String>,
    pub topic: Option<String>,
}

/// The most statements [`collected`] runs: the kind; a cursor by id; the links, and which are in force;
/// the Topic's owner and filings, and which are in force; the page; whether it's a later version; its
/// total; and the homes of what's on it from elsewhere.
pub const COLLECTED_STATEMENTS: u32 = 1 + 1 + 1 + 2 + 1 + 1 + 2 + 1 + 1 + 1 + 1;

/// `conversation_collection`.
pub fn collected(
    scope: &mut dyn ReadScope,
    args: &ConversationArgs,
    limit: u32,
) -> Result<Collected, OpError> {
    let cid = args.id.as_str();
    let mut kind: Option<String> = None;
    let mut found = false;
    scope.query(KIND_OF, &[Param::Text(cid)], &mut |row| {
        found = true;
        kind = text(row, 1)?;
        Ok(Flow::Stop)
    })?;
    if !found || kind.as_deref() != Some(CONVERSATION) {
        let shown = repr(cid).ok_or_else(|| python_says("an id to show in other words"))?;
        return Err(bad_request(format!("not a conversation: {shown}")));
    }
    let (b_key, a_key) = page_window(
        scope,
        args.before.as_deref(),
        args.after.as_deref(),
        args.start.as_deref(),
    )?;
    let shape = args.shape.as_deref().unwrap_or("threads");
    if shape != "threads" && shape != "posts" {
        return Err(bad_request("shape is 'threads' or 'posts'".to_owned()));
    }
    let linked = links_to(scope, LINKED_INTO, &[cid])?;
    let linked = in_force(scope, linked)?;
    let mut link_of: HashMap<&str, &Link> = HashMap::with_capacity(linked.len());
    let mut also: Vec<&str> = Vec::with_capacity(linked.len());
    for link in &linked {
        if !link_of.contains_key(link.from.as_str()) {
            link_of.insert(&link.from, link);
            also.push(&link.from);
        }
    }

    let topic = args.topic.as_deref();
    let filed: Option<Vec<String>> = match topic {
        None => None,
        Some(topic) => {
            let owner = reads::first_to(&links_from(scope, TOPIC_OF, &[topic])?);
            if owner.get(topic).map(String::as_str) != Some(cid) {
                let shown =
                    repr(topic).ok_or_else(|| python_says("a Topic to show in other words"))?;
                return Err(bad_request(format!(
                    "not a topic of this conversation: {shown}"
                )));
            }
            let links = links_to(scope, ABOUT_TOPIC, &[topic])?;
            let links = in_force(scope, links)?;
            let mut filed: Vec<String> = links.into_iter().map(|link| link.from).collect();
            filed.sort();
            filed.dedup();
            Some(filed)
        }
    };
    let what = Scoped {
        conversation: cid,
        also: &also,
        only: filed.as_deref(),
        roots: topic.is_none() && shape == "threads",
    };
    let page = members_page(scope, &what, b_key, a_key, limit)?;
    let rows = page.rows;

    if rows.is_empty() {
        let mut later = false;
        scope.query(LATER, &[Param::Text(cid)], &mut |_| {
            later = true;
            Ok(Flow::Stop)
        })?;
        if later {
            return Err(python_says("a later version of a Conversation"));
        }
    }
    let total = match page.total {
        Some(total) => total,
        // `_topic_page`: nothing filed is no statement.
        None if filed.as_ref().is_some_and(Vec::is_empty) => 0,
        None => members_page(scope, &what, None, None, 1)?
            .total
            .unwrap_or(0),
    };
    let elsewhere = {
        let away: Vec<&str> = rows
            .iter()
            .filter(|row| row.number.is_none())
            .map(|row| row.id.as_str())
            .collect();
        homes_of(scope, &away)?
    };

    let mut items = Vec::with_capacity(rows.len());
    for row in &rows {
        let mut item = dict([
            ("id", Py::str(row.id.as_str())),
            (
                "via",
                Py::str(if row.number.is_some() {
                    "home"
                } else {
                    "linked"
                }),
            ),
            ("number", row.number.map_or(Py::None, Py::int)),
            ("reply_to", Py::opt_str(row.parent.as_deref())),
        ]);
        if row.number.is_none() {
            item.set(
                "home",
                Py::opt_str(elsewhere.get(&row.id).map(String::as_str)),
            );
            item.set(
                "link",
                Py::opt_str(link_of.get(row.id.as_str()).map(|link| link.id.as_str())),
            );
        }
        items.push(item);
    }
    let older = match (rows.first(), a_key) {
        (Some(first), _) => first.pos - 1,
        (None, None) => 0,
        (None, Some(_)) => total,
    };
    let newer = match (rows.last(), b_key) {
        (Some(last), _) => total - last.pos,
        (None, None) => 0,
        (None, Some(_)) => total,
    };
    let before = rows
        .first()
        .filter(|_| older != 0)
        .map_or(Py::None, |row| Py::Str(page_cursor(&row.at, row.seq)));
    let after = rows
        .last()
        .filter(|_| newer != 0)
        .map_or(Py::None, |row| Py::Str(page_cursor(&row.at, row.seq)));

    let mut answer = vec![
        (
            "key".to_owned(),
            Py::Str(match topic {
                None => format!("conversation:{cid}"),
                Some(topic) => format!("topic:{cid}:{topic}"),
            }),
        ),
        ("conversation".to_owned(), Py::str(cid)),
        (
            "shape".to_owned(),
            Py::str(if topic.is_none() { shape } else { "posts" }),
        ),
    ];
    if let Some(topic) = topic {
        answer.push(("topic".to_owned(), Py::str(topic)));
    }
    for (key, value) in [
        ("items", Py::List(items)),
        ("total", Py::int(total)),
        ("older", Py::int(older)),
        ("newer", Py::int(newer)),
        ("before", before.clone()),
        ("after", after),
        ("limit", Py::int(limit)),
    ] {
        answer.push((key.to_owned(), value));
    }
    Ok(Collected {
        answer: Py::Dict(answer),
        ids: rows.into_iter().map(|row| row.id).collect(),
        before,
        total,
    })
}

/// `GET /fluid/api/collections/conversation`.
#[derive(Clone, Copy, Debug, Default)]
pub struct ConversationCollection;

impl ReadOp for ConversationCollection {
    type Args = ConversationArgs;
    type Row = PyRow;

    const NAME: &'static str = "collections/conversation";
    const BUDGET: Budget = Budget {
        statements: 1 + COLLECTED_STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<ConversationArgs>,
    ) -> Result<ReadAnswer<PyRow>, OpError> {
        let as_of = scope.position();
        let limit = request.limit.unwrap_or(reads::PAGE);
        let got = collected(scope, &request.args, limit)?;
        Ok(whole(as_of, got.answer))
    }
}

/// An answer already in Python's shape. `ReadOp::Row` asks for `Serialize`; nothing sends this as it
/// is, because an adapter wants `json.dumps`'s bytes and not serde's.
pub struct PyRow(pub Py);

impl serde::Serialize for PyRow {
    fn serialize<S: serde::Serializer>(&self, to: S) -> Result<S::Ok, S::Error> {
        to.serialize_str(&self.0.dumps())
    }
}

fn whole(as_of: mentis_record::Position, answer: Py) -> ReadAnswer<PyRow> {
    ReadAnswer {
        rows: vec![PyRow(answer)],
        as_of,
        more: None,
        not_searched: Vec::new(),
    }
}

/// `GET /fluid/api/collections/thread`.
#[derive(Clone, Copy, Debug, Default)]
pub struct ThreadCollection;

#[derive(Clone, Debug, Default)]
pub struct ThreadArgs {
    pub root: String,
    pub before: Option<String>,
    pub after: Option<String>,
    pub start: Option<String>,
}

impl ReadOp for ThreadCollection {
    type Args = ThreadArgs;
    type Row = PyRow;

    const NAME: &'static str = "collections/thread";
    /// The position, the root, a cursor by id, the closure, and the root's home.
    const BUDGET: Budget = Budget { statements: 5 };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<ThreadArgs>,
    ) -> Result<ReadAnswer<PyRow>, OpError> {
        let as_of = scope.position();
        let args = &request.args;
        let root = args.root.as_str();
        let limit = request.limit.unwrap_or(reads::PAGE) as usize;
        let mut is_post = false;
        scope.query(KIND_OF, &[Param::Text(root)], &mut |row| {
            is_post = text(row, 0)?.as_deref() == Some("entry")
                && text(row, 1)?.as_deref() == Some(CONTRIBUTION)
                && matches!(row.value(2)?, Value::Null);
            Ok(Flow::Stop)
        })?;
        if !is_post {
            let shown = repr(root).ok_or_else(|| python_says("an id to show in other words"))?;
            return Err(bad_request(format!("not a post: {shown}")));
        }
        let (b, a) = page_window(
            scope,
            args.before.as_deref(),
            args.after.as_deref(),
            args.start.as_deref(),
        )?;
        let rows = closures(scope, &[root])?.remove(root).unwrap_or_default();
        let key = |row: &reads::Reply| (as_f64(&row.at), row.seq);
        let less = |x: (f64, i64), y: (f64, i64)| x.0 < y.0 || (x.0 == y.0 && x.1 < y.1);

        // Indexes into `rows`, which is in `(recorded_at, seq)` order.
        let (first, count) = if let Some(b) = b {
            let under = rows
                .iter()
                .filter(|row| less(key(row), (b.at, b.seq)))
                .count();
            let shown = under.min(limit);
            (under - shown, shown)
        } else if let Some(a) = a {
            let from = rows
                .iter()
                .position(|row| less((a.at, a.seq), key(row)))
                .unwrap_or(rows.len());
            let shown = (rows.len() - from).min(limit);
            (from, shown)
        } else {
            let shown = rows.len().min(limit);
            (rows.len() - shown, shown)
        };
        let chosen = &rows[first..first + count];
        let older = if !chosen.is_empty() {
            first
        } else if a.is_none() {
            0
        } else {
            rows.len()
        };
        let newer = if !chosen.is_empty() {
            rows.len() - first - chosen.len()
        } else if b.is_none() {
            0
        } else {
            rows.len()
        };
        let root_home = homes_of(scope, &[root])?;
        let answer = dict([
            ("key", Py::Str(format!("thread:{root}"))),
            ("root", Py::str(root)),
            (
                "root_home",
                Py::opt_str(root_home.get(root).map(String::as_str)),
            ),
            (
                "items",
                Py::List(
                    chosen
                        .iter()
                        .map(|row| {
                            dict([
                                ("id", Py::str(row.id.as_str())),
                                ("parent", Py::opt_str(row.parent.as_deref())),
                                ("depth", Py::int(row.depth)),
                                ("home", Py::opt_str(row.home.as_deref())),
                            ])
                        })
                        .collect(),
                ),
            ),
            ("total", Py::int(rows.len())),
            ("older", Py::int(older)),
            ("newer", Py::int(newer)),
            (
                "by_home",
                by_home(rows.iter().map(|row| row.home.as_deref())),
            ),
            (
                "before",
                chosen
                    .first()
                    .filter(|_| older != 0)
                    .map_or(Py::None, |row| Py::Str(page_cursor(&row.at, row.seq))),
            ),
            (
                "after",
                chosen
                    .last()
                    .filter(|_| newer != 0)
                    .map_or(Py::None, |row| Py::Str(page_cursor(&row.at, row.seq))),
            ),
            ("limit", Py::int(limit)),
        ]);
        Ok(whole(as_of, answer))
    }
}

/// `Id` is what the rules take; a window reads strings.
pub(crate) fn ids_of(ids: &[&str]) -> Vec<Id> {
    ids.iter().map(|id| Id((*id).to_owned())).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_page_text_says_what_python_s_does_in_each_direction() {
        assert!(PAGE_NEWEST.contains("FROM units  ORDER BY recorded_at DESC, seq DESC LIMIT ?8"));
        assert!(PAGE_BEFORE.contains(
            "FROM units WHERE (recorded_at, seq) < (?9, ?10) ORDER BY recorded_at DESC, seq DESC"
        ));
        assert!(PAGE_AFTER.contains(
            "FROM units WHERE (recorded_at, seq) > (?9, ?10) ORDER BY recorded_at ASC, seq ASC"
        ));
    }

    #[test]
    fn pyjson_is_how_a_cursor_writes_a_time() {
        assert_eq!(
            page_cursor(&crate::pyjson::loads("1793578173.25").unwrap(), 12),
            "1793578173.25_12"
        );
    }
}
