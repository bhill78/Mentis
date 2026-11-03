//! `GET /fluid/api/search`: `fluid/search.py`, literal post search within one Conversation, newest
//! first. Its candidates are the Conversation collection's. **Its cost grows with the Conversation,**
//! which is the point of [`SearchCost`]: a search that matches late reads every post it passes.
//!
//! **A page to a scope.** One page's statements are fixed, and the scope goes between pages, so a long
//! Conversation doesn't pin the WAL for its whole walk.
//!
//! **ASCII needles only,** because `re.IGNORECASE` is Python's own relation: a needle with anything
//! else in it forwards. An ASCII letter's relation is small and is checked against `re` itself for every
//! code point (`tests/post_search.rs`): the case pair, and `K` (U+212A), `ſ` (U+017F), `İ` (U+0130)
//! and `ı` (U+0131). The text searched can hold anything.

use std::time::{Duration, Instant};

use mentis_record::{Id, READ_SCOPE_LIMIT, ReadClass, ReadScope, RecordReader};

use crate::pyjson::{self, Py, dict};
use crate::window::collections::{self, PageKey};
use crate::window::python_says;
use crate::window::reads::PAGE_MAX;
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest, python};

/// `search.QUERY_MAX`, `search.SNIPPET`.
pub const QUERY_MAX: usize = 500;
pub const SNIPPET: usize = 240;

/// `read.PAGE_MAX`.
const WALK_PAGE: usize = PAGE_MAX as usize;

/// `_REFERENCE_PARTS`, `conversation/versions.py:149`.
const REFERENCE_PARTS: [&str; 5] = ["topic", "turn", "conversation", "acquired", "object"];

/// What one character is, under `re.IGNORECASE`, for what an ASCII needle can match: two characters
/// match when these are equal.
fn folded(c: char) -> char {
    match c {
        'A'..='Z' => c.to_ascii_lowercase(),
        '\u{212a}' => 'k',
        '\u{17f}' => 's',
        '\u{130}' | '\u{131}' => 'i',
        _ => c,
    }
}

/// Whether `re.compile(re.escape(needle), re.IGNORECASE)` matches `c`, for a needle in ASCII.
pub fn matches_needle(needle: char, c: char) -> bool {
    folded(needle) == folded(c)
}

/// `pattern.search(text, from)`: where the needle first starts, and where it ends.
fn search(text: &[char], needle: &[char]) -> Option<(usize, usize)> {
    if needle.is_empty() || text.len() < needle.len() {
        return None;
    }
    (0..=text.len() - needle.len())
        .find(|at| {
            needle
                .iter()
                .zip(&text[*at..])
                .all(|(want, got)| folded(*want) == folded(*got))
        })
        .map(|at| (at, at + needle.len()))
}

/// `_snippet`: a compact excerpt around what matched, without breaking words.
fn snippet(text: &str, matched: &[char]) -> String {
    let clean: Vec<char> = {
        let mut clean = String::with_capacity(text.len());
        for (at, word) in python::words(text).enumerate() {
            if at > 0 {
                clean.push(' ');
            }
            clean.push_str(word);
        }
        clean.chars().collect()
    };
    let whole = |chars: &[char]| chars.iter().collect::<String>();
    let Some((start_of, end_of)) = search(&clean, matched).filter(|_| clean.len() > SNIPPET) else {
        return whole(&clean);
    };
    // A match longer than an excerpt makes `room` negative, and its floor moves both ends inward.
    let length = clean.len() as i64;
    let (found_start, found_end) = (start_of as i64, end_of as i64);
    let room = SNIPPET as i64 - (found_end - found_start);
    let half = room.div_euclid(2);
    let mut start = (found_start - half).max(0);
    let mut end = length.min(found_end + room - half);
    if start > 0 {
        let cut = clean
            .get(start as usize..)
            .and_then(|rest| rest.iter().position(|c| *c == ' '))
            .map(|at| at as i64 + start);
        if let Some(cut) = cut.filter(|cut| *cut < found_start) {
            start = cut + 1;
        }
    }
    if end < length {
        let cut = (found_end < end)
            .then(|| clean[end_of..end as usize].iter().rposition(|c| *c == ' '))
            .flatten()
            .map(|at| at as i64 + found_end);
        if let Some(cut) = cut.filter(|cut| *cut > found_end) {
            end = cut;
        }
    }
    let (start, end, length) = (start as usize, end.max(0) as usize, length as usize);
    let mut out = String::new();
    if start > 0 {
        out.push_str("...");
    }
    out.push_str(&whole(&clean[start.min(end)..end]));
    if end < length {
        out.push_str("...");
    }
    out
}

/// `flow_text`: what the author typed, as one string. What Python raises on is Python's to say.
pub fn flow_text(body: &Py) -> Result<String, OpError> {
    if !body.truthy() {
        return Ok(String::new());
    }
    if !body.is_dict() {
        return Err(python_says("a body that isn't an object"));
    }
    let parts = match body.get("parts") {
        None | Some(Py::None) => return Ok(String::new()),
        Some(found) if !found.truthy() => return Ok(String::new()),
        Some(Py::List(parts)) => parts,
        Some(_) => return Err(python_says("parts that aren't a list")),
    };
    let mut out = String::new();
    for part in parts {
        if !part.is_dict() {
            return Err(python_says("a part that isn't an object"));
        }
        let kind = part.get("type").and_then(Py::as_str);
        if kind != Some("text") && !kind.is_some_and(|kind| REFERENCE_PARTS.contains(&kind)) {
            continue;
        }
        match part.get("text") {
            None => {}
            Some(found) if !found.truthy() => {}
            Some(Py::Str(words)) => out.push_str(words),
            Some(_) => return Err(python_says("a part's text that isn't text")),
        }
    }
    Ok(out)
}

/// What a search asks.
#[derive(Clone, Debug)]
pub struct SearchAsk {
    pub conversation: String,
    /// `one("q")`, as sent.
    pub q: Option<String>,
    pub before: Option<String>,
    pub limit: u32,
}

/// What a search cost, for what the package reports. Never a reason to behave differently.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct SearchCost {
    /// Pages walked, each one scope and a fixed number of statements.
    pub pages: u32,
    /// Posts whose text was read.
    pub posts: u64,
    pub statements: u32,
    pub took: Duration,
}

/// The one row of a [`PostPage`]: every post in it, newest first, with its words.
struct Passage {
    id: String,
    at: Py,
    number: Option<i64>,
    text: String,
}

struct PageOfPosts {
    passages: Vec<Passage>,
    /// How many the page held, read or not, and where the next starts.
    held: usize,
    next: Option<PageKey>,
}

/// What a walk starts from: the first scope's reading of what's visible, and where to page from.
struct Start {
    also: Vec<String>,
    before: Option<PageKey>,
}

struct BeginSearch;

impl ReadOp for BeginSearch {
    type Args = (String, Option<String>);
    type Row = crate::window::Prepared<Start>;

    const NAME: &'static str = "post-search-start";
    /// The kind, the inclusions and which are in force, and a cursor by id.
    const BUDGET: Budget = Budget { statements: 5 };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let (conversation, before) = &request.args;
        let also = collections::conversation_scope(scope, conversation)?;
        let before = collections::page_key_of(scope, before.as_deref())?;
        Ok(ReadAnswer {
            rows: vec![crate::window::Prepared(Start { also, before })],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

struct PostPage;

impl ReadOp for PostPage {
    type Args = (String, Vec<String>, Option<PageKey>);
    type Row = crate::window::Prepared<PageOfPosts>;

    const NAME: &'static str = "post-search-page";
    /// `members_page`, and how the page's posts now read.
    const BUDGET: Budget = Budget {
        statements: 1 + mentis_rules::CHANGED_STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let (conversation, also, before) = &request.args;
        let also: Vec<&str> = also.iter().map(String::as_str).collect();
        let rows = collections::posts_page(scope, conversation, &also, *before, PAGE_MAX)?;
        let ids: Vec<Id> = rows.iter().map(|row| Id(row.id.clone())).collect();
        let mut readings = mentis_rules::now_reads_walking_only_what_changed(scope, &ids)?;
        let held = rows.len();
        let next = rows.first().map(|row| row.key);
        let mut passages = Vec::with_capacity(held);
        for row in rows.into_iter().rev() {
            let Some(reading) = readings.remove(&Id(row.id.clone())) else {
                continue;
            };
            if reading.python_says {
                return Err(python_says("a post Python has to read"));
            }
            let body = pyjson::loads(&reading.body_json)
                .ok_or_else(|| python_says("a body this can't read"))?;
            passages.push(Passage {
                text: flow_text(&body)?,
                id: row.id,
                at: row.at,
                number: row.number,
            });
        }
        Ok(ReadAnswer {
            rows: vec![crate::window::Prepared(PageOfPosts {
                passages,
                held,
                next,
            })],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

fn asked<A>(args: A) -> ReadRequest<A> {
    ReadRequest {
        args,
        cursor: None,
        limit: None,
        deadline: Instant::now() + READ_SCOPE_LIMIT,
    }
}

/// `search.conversation`: `{"hits": [...], "more": ...}`, and what it cost.
pub fn conversation(
    record: &dyn RecordReader,
    class: ReadClass,
    ask: &SearchAsk,
) -> Result<(Py, SearchCost), OpError> {
    let started = Instant::now();
    let needle = python::strip(ask.q.as_deref().unwrap_or(""));
    if needle.is_empty() {
        return Err(OpError::BadRequest {
            why: "name what to search for: ?q=<text>".to_owned(),
        });
    }
    let length = needle.chars().count();
    if length > QUERY_MAX {
        return Err(OpError::BadRequest {
            why: format!("search text is at most {QUERY_MAX} characters, not {length}"),
        });
    }
    if !needle.is_ascii() {
        return Err(python_says("a needle whose case only `re` can say"));
    }
    let needle: Vec<char> = needle.chars().collect();
    let limit = usize::try_from(ask.limit).unwrap_or(usize::MAX);

    let mut cost = SearchCost::default();
    let Start { also, mut before } = {
        let args = (ask.conversation.clone(), ask.before.clone());
        let mut got = crate::run(&BeginSearch, record, class, &asked(args))?;
        got.rows.pop().ok_or_else(|| python_says("no start"))?.0
    };
    cost.statements += BeginSearch::BUDGET.statements;

    let mut hits: Vec<Py> = Vec::new();
    while hits.len() <= limit {
        let args = (ask.conversation.clone(), also.clone(), before);
        let mut got = crate::run(&PostPage, record, class, &asked(args))?;
        let page = got.rows.pop().ok_or_else(|| python_says("no page"))?.0;
        cost.pages += 1;
        cost.statements += PostPage::BUDGET.statements;
        if page.held == 0 {
            break;
        }
        for passage in page.passages {
            cost.posts += 1;
            let text: Vec<char> = passage.text.chars().collect();
            let Some((start, end)) = search(&text, &needle) else {
                continue;
            };
            hits.push(dict([
                ("post", Py::Str(passage.id)),
                ("number", passage.number.map_or(Py::None, Py::int)),
                (
                    "snippet",
                    Py::Str(snippet(&passage.text, &text[start..end])),
                ),
                ("at", passage.at),
            ]));
            if hits.len() > limit {
                break;
            }
        }
        if hits.len() > limit || page.held < WALK_PAGE {
            break;
        }
        before = page.next;
    }
    let more = hits.len() > limit;
    hits.truncate(limit);
    cost.took = started.elapsed();
    Ok((
        dict([("hits", Py::List(hits)), ("more", Py::Bool(more))]),
        cost,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chars(text: &str) -> Vec<char> {
        text.chars().collect()
    }

    #[test]
    fn a_needle_finds_the_first_place_it_folds_to() {
        assert_eq!(search(&chars("a Kelvin"), &chars("KELV")), Some((2, 6)));
        assert_eq!(search(&chars("\u{212a}elvin"), &chars("kel")), Some((0, 3)));
        assert_eq!(search(&chars("\u{17f}o"), &chars("SO")), Some((0, 2)));
        assert_eq!(search(&chars("\u{130}\u{131}"), &chars("ii")), Some((0, 2)));
        assert_eq!(search(&chars("abc"), &chars("abcd")), None);
        assert_eq!(search(&chars("abc"), &chars("x")), None);
    }

    #[test]
    fn a_short_text_is_all_its_words_and_a_long_one_is_cut_at_words() {
        assert_eq!(snippet("  a\n b\u{a0}c ", &chars("b")), "a b c");
        let long = format!("{} needle {}", "before ".repeat(60), "after ".repeat(60));
        let got = snippet(&long, &chars("needle"));
        assert!(got.starts_with("...before"), "{got}");
        assert!(got.ends_with("after..."), "{got}");
        assert!(got.contains("needle"));
        assert!(got.chars().count() <= SNIPPET + 6);
    }

    #[test]
    fn a_match_only_the_original_held_gives_the_whole_text() {
        // Two spaces match in the post, and the excerpt's words have one.
        let long = format!("x  y {}", "word ".repeat(100));
        let clean: Vec<&str> = python::words(&long).collect();
        assert_eq!(snippet(&long, &chars("x  y")), clean.join(" "));
    }

    #[test]
    fn a_match_past_an_excerpt_is_cut_inward_as_python_s_floor_cuts_it() {
        let matched = "m".repeat(250);
        let text = format!("aaa {matched} bbb");
        // `room` is -10: 5 in from each end of what matched, and nothing to cut at.
        assert_eq!(
            snippet(&text, &chars(&matched)),
            format!("...{}...", "m".repeat(240))
        );
    }

    #[test]
    fn flow_text_is_the_words_and_the_references_characters() {
        let body = pyjson::loads(
            r#"{"parts": [{"type": "text", "text": "a "},
                {"type": "topic", "ref": "t", "text": "b "},
                {"type": "media", "ref": "m", "text": "no"},
                {"type": "object", "ref": "o", "text": null},
                {"type": "text"}]}"#,
        )
        .unwrap();
        assert_eq!(flow_text(&body).unwrap(), "a b ");
        for bad in [r#"{"parts": [1]}"#, r#"{"parts": 3}"#, r#"[1]"#] {
            assert!(flow_text(&pyjson::loads(bad).unwrap()).is_err(), "{bad}");
        }
    }
}
