//! What the window's reads share: `fluid/read.py`'s "shared readings", each one statement for any
//! number of ids. Each reads through the indexes Python's do, and only the columns its caller uses.

use std::collections::{HashMap, HashSet};

use mentis_record::{Flow, Id, Param, Position, ReadScope, RecordError, Row, Value};
use mentis_rules::{NameRead, id_list};

use super::python_says;
use crate::OpError;
use crate::pyjson::Py;

/// `conversation/__init__.py`'s relations and kinds, as `fluid/read.py` imports them.
pub const IN_CONVERSATION: &str = "in-conversation";
pub const LINKED_INTO: &str = "linked-into";
pub const REPLIES_TO: &str = "replies-to";
pub const TOPIC_OF: &str = "topic-of";
pub const ABOUT_TOPIC: &str = "about-topic";
pub const CONTRIBUTION: &str = "contribution";
pub const CONVERSATION: &str = "conversation";
/// `read.RETURNING_ACTS`.
pub const RETURNING_ACTS: [&str; 2] = ["result-returned", "result-recovered"];

/// `read.BATCH`, `read.PAGE`, `read.PAGE_MAX`.
pub const BATCH: usize = 64;
pub const PAGE: u32 = 30;
pub const PAGE_MAX: u32 = 200;

const LINKS_FROM: &str = "SELECT id, link_from, link_to, attributed_to, recorded_at FROM entry \
     WHERE link_relation IS NOT NULL AND link_relation = ?1 \
       AND link_from IN (SELECT value FROM json_each(?2)) ORDER BY seq";
const LINKS_TO: &str = "SELECT id, link_from, link_to, attributed_to, recorded_at FROM entry \
     WHERE link_relation IS NOT NULL AND link_relation = ?1 \
       AND link_to IN (SELECT value FROM json_each(?2)) ORDER BY seq";

/// A row of `corpus.heads`, as far as the window asks of one: what it is, without its body.
const HEADS: &str = "SELECT id, seq, family, def_name, link_relation, recorded_at, attributed_to \
     FROM entry WHERE id IN (SELECT value FROM json_each(?1))";

/// `numbers_of`: one statement for every home at once. Python's is one per distinct home, and a post's
/// rank is the same: among the nodes linked to its home, `DISTINCT`, by `(recorded_at, seq)`.
const NUMBERS: &str = "WITH pairs AS ( \
       SELECT json_extract(value, '$[0]') AS post, json_extract(value, '$[1]') AS home \
       FROM json_each(?1)), \
     homes AS (SELECT DISTINCT home FROM pairs), \
     members AS ( \
       SELECT DISTINCT h.home AS home, e.id AS id, e.seq AS seq, e.recorded_at AS recorded_at \
       FROM homes h JOIN entry l ON l.link_to = h.home AND l.link_relation = 'in-conversation' \
       JOIN entry e ON e.id = l.link_from \
       WHERE e.family = 'entry' AND e.def_name = 'contribution' AND e.link_relation IS NULL), \
     numbered AS ( \
       SELECT home, id, ROW_NUMBER() OVER (PARTITION BY home ORDER BY recorded_at, seq) AS n \
       FROM members) \
     SELECT n.id, n.n FROM numbered n JOIN pairs p ON p.post = n.id AND p.home = n.home";

/// `_closures`, for many roots in one statement: `reply_closure`'s recursion with the root carried
/// along. A node is under its FIRST `replies-to` link, once, at its shallowest depth. Python's walks a
/// level at a time for its two statements a level; this reads the same tree in one.
const CLOSURES: &str = "WITH RECURSIVE t(root, id, parent, depth) AS ( \
       SELECT value, value, NULL, 0 FROM json_each(?1) \
       UNION \
       SELECT t.root, l.link_from, l.link_to, t.depth + 1 \
       FROM t JOIN entry l ON l.link_to = t.id \
       WHERE l.link_relation = 'replies-to' AND t.depth < 500 \
         AND l.seq = (SELECT MIN(x.seq) FROM entry x WHERE x.link_from = l.link_from \
                      AND x.link_relation = 'replies-to')) \
     SELECT t.root, t.id, e.seq, e.recorded_at, t.parent, MIN(t.depth), \
            (SELECT h.link_to FROM entry h WHERE h.link_from = t.id \
               AND h.link_relation = 'in-conversation' ORDER BY h.seq LIMIT 1) \
     FROM t JOIN entry e ON e.id = t.id \
     WHERE t.depth > 0 AND t.id != t.root \
     GROUP BY t.root, t.id \
     ORDER BY e.recorded_at, e.seq";

/// Whichever text a column holds. Anything else in these columns isn't something a Brain writes, and
/// Python reads it some way of its own, so it's a failed read here and never a guess.
pub fn text(row: &dyn Row, column: usize) -> Result<Option<String>, RecordError> {
    match row.value(column)? {
        Value::Null => Ok(None),
        Value::Text(bytes) => match std::str::from_utf8(bytes) {
            Ok(text) => Ok(Some(text.to_owned())),
            Err(_) => Err(RecordError::Sqlite {
                detail: format!("column {column} is not UTF-8"),
            }),
        },
        _ => Err(RecordError::Sqlite {
            detail: format!("column {column} is not text"),
        }),
    }
}

/// `recorded_at`, a seconds count, as Python's `sqlite3` hands it: a `float`, or an `int` if stored so.
pub fn number(row: &dyn Row, column: usize) -> Result<Py, RecordError> {
    Ok(match row.value(column)? {
        Value::Real(value) => Py::Float(value),
        Value::Integer(value) => Py::int(value),
        _ => Py::None,
    })
}

/// A moment or a position as a number to compare.
pub fn as_f64(value: &Py) -> f64 {
    match value {
        Py::Float(value) => *value,
        Py::Int(digits) => digits.parse().unwrap_or(0.0),
        _ => 0.0,
    }
}

/// `read.change_cursor`.
pub fn change_cursor(at: Position) -> Py {
    Py::Str(format!(
        "f1.{}.{}.{}",
        at.entry, at.operational, at.delivery
    ))
}

/// `read._page_cursor`: `f"{at!r}_{seq}"`.
pub fn page_cursor(at: &Py, seq: i64) -> String {
    format!("{}_{seq}", at.dumps())
}

/// A link, as far as these reads need one.
#[derive(Clone, Debug)]
pub struct Link {
    pub id: String,
    pub from: String,
    pub to: String,
    pub attributed_to: Option<String>,
    pub recorded_at: Py,
}

fn links(
    scope: &mut dyn ReadScope,
    sql: &'static str,
    relation: &str,
    ids: &[&str],
) -> Result<Vec<Link>, RecordError> {
    let mut out = Vec::new();
    if ids.is_empty() {
        return Ok(out);
    }
    let list = id_list(ids.iter().copied());
    scope.query(
        sql,
        &[Param::Text(relation), Param::Text(&list)],
        &mut |row| {
            out.push(Link {
                id: text(row, 0)?.unwrap_or_default(),
                from: text(row, 1)?.unwrap_or_default(),
                to: text(row, 2)?.unwrap_or_default(),
                attributed_to: text(row, 3)?,
                recorded_at: number(row, 4)?,
            });
            Ok(Flow::Continue)
        },
    )?;
    Ok(out)
}

/// `corpus.links(relation=, frm_any=)`. One statement, in append order.
pub fn links_from(
    scope: &mut dyn ReadScope,
    relation: &str,
    ids: &[&str],
) -> Result<Vec<Link>, RecordError> {
    links(scope, LINKS_FROM, relation, ids)
}

/// `corpus.links(relation=, to_any=)`. One statement, in append order.
pub fn links_to(
    scope: &mut dyn ReadScope,
    relation: &str,
    ids: &[&str],
) -> Result<Vec<Link>, RecordError> {
    links(scope, LINKS_TO, relation, ids)
}

/// `_first`: from -> the first link's `to`.
pub fn first_to(links: &[Link]) -> HashMap<String, String> {
    let mut out = HashMap::with_capacity(links.len());
    for link in links {
        out.entry(link.from.clone())
            .or_insert_with(|| link.to.clone());
    }
    out
}

/// `homes_of`. One statement.
pub fn homes_of(
    scope: &mut dyn ReadScope,
    ids: &[&str],
) -> Result<HashMap<String, String>, RecordError> {
    Ok(first_to(&links_from(scope, IN_CONVERSATION, ids)?))
}

/// `_in_force`, its links in the order given. Two statements for the set.
pub fn in_force(scope: &mut dyn ReadScope, links: Vec<Link>) -> Result<Vec<Link>, RecordError> {
    let ids: Vec<&str> = links.iter().map(|link| link.id.as_str()).collect();
    let ended: HashSet<String> = mentis_rules::ended(scope, &ids)?;
    Ok(links
        .into_iter()
        .filter(|link| !ended.contains(&link.id))
        .collect())
}

/// `numbers_of`: post -> its home number. One statement.
pub fn numbers_of(
    scope: &mut dyn ReadScope,
    homes: &HashMap<String, String>,
) -> Result<HashMap<String, i64>, RecordError> {
    let mut out = HashMap::with_capacity(homes.len());
    if homes.is_empty() {
        return Ok(out);
    }
    let pairs: Vec<[&str; 2]> = homes
        .iter()
        .map(|(post, home)| [post.as_str(), home.as_str()])
        .collect();
    let list = serde_json::to_string(&pairs).expect("a list of pairs of strings is always JSON");
    scope.query(NUMBERS, &[Param::Text(&list)], &mut |row| {
        if let (Some(post), Some(n)) = (text(row, 0)?, row.value(1)?.integer()) {
            out.insert(post, n);
        }
        Ok(Flow::Continue)
    })?;
    Ok(out)
}

/// `_names`: id -> the name a person reads. An id the record doesn't hold is absent. A name that isn't
/// text is Python's to show. At most [`mentis_rules::STATEMENTS`].
pub fn names_of(scope: &mut dyn ReadScope, ids: &[&str]) -> Result<HashMap<String, String>, OpError> {
    let mut seen = HashSet::new();
    let asked: Vec<Id> = ids
        .iter()
        .filter(|id| !id.is_empty() && seen.insert(**id))
        .map(|id| Id((*id).to_owned()))
        .collect();
    let mut out = HashMap::with_capacity(asked.len());
    for (id, read) in mentis_rules::name_reads(scope, &asked)? {
        let shown = match read {
            NameRead::Named(name) => name,
            NameRead::Unnamed => id.0.clone(),
            NameRead::NotPlain => return Err(python_says("a name that isn't text")),
        };
        out.insert(id.0, shown);
    }
    Ok(out)
}

/// What a row is, without its body.
#[derive(Clone, Debug)]
pub struct Head {
    pub seq: i64,
    pub family: String,
    pub kind: Option<String>,
    pub is_link: bool,
    pub recorded_at: Py,
    pub attributed_to: Option<String>,
}

impl Head {
    /// `read._is_post`.
    pub fn is_post(&self) -> bool {
        self.family == "entry" && !self.is_link && self.kind.as_deref() == Some(CONTRIBUTION)
    }
}

/// `corpus.heads`. One statement.
pub fn heads(scope: &mut dyn ReadScope, ids: &[&str]) -> Result<HashMap<String, Head>, RecordError> {
    let mut out = HashMap::with_capacity(ids.len());
    let wanted: Vec<&str> = ids.iter().copied().filter(|id| !id.is_empty()).collect();
    if wanted.is_empty() {
        return Ok(out);
    }
    let list = id_list(wanted);
    scope.query(HEADS, &[Param::Text(&list)], &mut |row| {
        out.insert(
            text(row, 0)?.unwrap_or_default(),
            Head {
                seq: row.value(1)?.integer().unwrap_or_default(),
                family: text(row, 2)?.unwrap_or_default(),
                kind: text(row, 3)?,
                is_link: !matches!(row.value(4)?, Value::Null),
                recorded_at: number(row, 5)?,
                attributed_to: text(row, 6)?,
            },
        );
        Ok(Flow::Continue)
    })?;
    Ok(out)
}

/// One reply under a root, as `_closures` lists it.
#[derive(Clone, Debug)]
pub struct Reply {
    pub id: String,
    pub seq: i64,
    pub at: Py,
    pub parent: Option<String>,
    pub depth: i64,
    pub home: Option<String>,
}

/// `_closures`: root -> its thread, in `(recorded_at, seq)` order. One statement.
pub fn closures(
    scope: &mut dyn ReadScope,
    roots: &[&str],
) -> Result<HashMap<String, Vec<Reply>>, RecordError> {
    let mut out: HashMap<String, Vec<Reply>> =
        roots.iter().map(|root| ((*root).to_owned(), Vec::new())).collect();
    if roots.is_empty() {
        return Ok(out);
    }
    let list = id_list(roots.iter().copied());
    scope.query(CLOSURES, &[Param::Text(&list)], &mut |row| {
        let root = text(row, 0)?.unwrap_or_default();
        out.entry(root).or_default().push(Reply {
            id: text(row, 1)?.unwrap_or_default(),
            seq: row.value(2)?.integer().unwrap_or_default(),
            at: number(row, 3)?,
            parent: text(row, 4)?,
            depth: row.value(5)?.integer().unwrap_or_default(),
            home: text(row, 6)?,
        });
        Ok(Flow::Continue)
    })?;
    Ok(out)
}

/// `{h: count}`, first met first. A reply with no home counts under `null`, as `json.dumps` writes
/// `None` as a key.
pub fn by_home<'a>(homes: impl Iterator<Item = Option<&'a str>>) -> Py {
    let mut counts: Vec<(String, u64)> = Vec::new();
    for home in homes {
        let key = home.unwrap_or("null");
        match counts.iter_mut().find(|(have, _)| have == key) {
            Some(found) => found.1 += 1,
            None => counts.push((key.to_owned(), 1)),
        }
    }
    Py::Dict(
        counts
            .into_iter()
            .map(|(key, count)| (key, Py::int(count)))
            .collect(),
    )
}
