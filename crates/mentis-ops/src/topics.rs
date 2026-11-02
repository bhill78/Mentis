//! `GET /fluid/api/topics`'s read: `topics`, `fluid/read.py:545`. A name lookup, never a search: no
//! Turn and no source text is read.

use std::collections::HashMap;

use mentis_record::{Flow, Id, Param, ReadScope, Value};
use mentis_rules::body::{self, Field};
use serde::Serialize;

use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest, python};

/// The Topics' links to their Conversations, through the link-from index, as `corpus.links(relation,
/// frm_any=tids)` reads them.
const HOMES: &str = "SELECT l.link_from, l.link_to FROM entry l \
     WHERE l.link_relation = 'topic-of' AND l.link_from IN \
       (SELECT id FROM entry WHERE def_name = 'topic' AND family = 'entry' \
        AND link_relation IS NULL) \
     ORDER BY l.seq";

/// Topics.
#[derive(Clone, Copy, Debug, Default)]
pub struct Topics;

/// What a person typed after `#`, as sent. The op's limit is [`ReadRequest::limit`].
#[derive(Clone, Debug, Default)]
pub struct TopicsArgs {
    pub q: Option<String>,
}

/// A Topic that matched.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct TopicRow {
    #[serde(rename = "ref")]
    pub reference: String,
    pub name: String,
    pub conversation: String,
    pub conversation_name: Option<String>,
}

/// The one row of an answer: `matched` counts every hit beside the page returned, so it belongs to
/// no one Topic.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct TopicsPage {
    pub topics: Vec<TopicRow>,
    pub matched: u64,
}

/// Python would have to say what this is. Nothing was answered.
fn python_says(what: &str) -> OpError {
    OpError::NotOwned { why: what.into() }
}

impl ReadOp for Topics {
    type Args = TopicsArgs;
    type Row = TopicsPage;

    const NAME: &'static str = "topics";
    /// The position, the Topics' homes, and one [`mentis_rules::now_reads`] of the Topics and
    /// their Conversations together.
    const BUDGET: Budget = Budget {
        statements: 2 + mentis_rules::STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<TopicsArgs>,
    ) -> Result<ReadAnswer<TopicsPage>, OpError> {
        let as_of = scope.position();
        let asked = request.args.q.as_deref().unwrap_or("");
        let want = python::lower(python::strip(asked))
            .ok_or_else(|| python_says("a question in letters newer than Python's table"))?;
        let want = want.trim_start_matches('#');
        let limit = usize::try_from(request.limit.unwrap_or(100)).unwrap_or(usize::MAX);

        // `dict`: a Topic with two homes keeps the last.
        let mut home: HashMap<String, String> = HashMap::new();
        scope.query(HOMES, &[] as &[Param<'_>], &mut |row| {
            if let (Value::Text(from), Value::Text(to)) = (row.value(0)?, row.value(1)?)
                && let (Ok(from), Ok(to)) = (std::str::from_utf8(from), std::str::from_utf8(to))
            {
                home.insert(from.to_owned(), to.to_owned());
            }
            Ok(Flow::Continue)
        })?;
        if home.is_empty() {
            return Ok(answer(as_of, Vec::new(), 0));
        }

        let mut ids: Vec<Id> = home.keys().cloned().map(Id).collect();
        ids.extend(home.values().cloned().map(Id));
        ids.sort();
        ids.dedup();
        let readings = mentis_rules::now_reads(scope, &ids).map_err(OpError::from)?;

        let mut hits: Vec<(u8, String, String, String)> = Vec::new();
        for topic in home.keys() {
            let Some(reading) = readings.get(&Id(topic.clone())) else {
                continue;
            };
            if reading.deleted.is_some() {
                continue;
            }
            let name = match body::fields(&reading.body_json, &["name"]).as_deref() {
                Some([Field::Text(name)]) => name.clone(),
                Some([Field::Nothing]) => continue,
                _ => return Err(python_says("a Topic whose name is not text")),
            };
            let low = python::lower(&name)
                .ok_or_else(|| python_says("a name in letters newer than Python's table"))?;
            if !want.is_empty() && !low.contains(want) {
                continue;
            }
            let rank = if low.starts_with(want) {
                0
            } else if python::words(&low).any(|word| word.starts_with(want)) {
                1
            } else {
                2
            };
            hits.push((rank, low, topic.clone(), name));
        }
        hits.sort();

        let matched = hits.len() as u64;
        let mut rows = Vec::new();
        for (_, _, reference, name) in hits.into_iter().take(limit) {
            let conversation = home[&reference].clone();
            let conversation_name = match readings.get(&Id(conversation.clone())) {
                None => None,
                Some(reading) => match body::fields(&reading.body_json, &["name"]).as_deref() {
                    Some([Field::Text(name)]) => Some(name.clone()),
                    Some([Field::Nothing]) => conversation_name_when_blank(&reading.body_json)?,
                    _ => return Err(python_says("a Conversation whose name is not text")),
                },
            };
            rows.push(TopicRow {
                reference,
                name,
                conversation,
                conversation_name,
            });
        }
        Ok(answer(as_of, rows, matched))
    }
}

/// `.get("name")` with no `or`, unlike a Topic's: a name `""` stays `""`, and one absent is `None`.
/// A false value that is neither is Python's to show.
fn conversation_name_when_blank(body_json: &str) -> Result<Option<String>, OpError> {
    let found: serde_json::Value = serde_json::from_str(body_json)
        .map_err(|_| python_says("a Conversation whose body can't be read here"))?;
    match found.get("name") {
        None | Some(serde_json::Value::Null) => Ok(None),
        Some(serde_json::Value::String(name)) => Ok(Some(name.clone())),
        Some(_) => Err(python_says("a Conversation whose name is not text")),
    }
}

fn answer(
    as_of: mentis_record::Position,
    topics: Vec<TopicRow>,
    matched: u64,
) -> ReadAnswer<TopicsPage> {
    ReadAnswer {
        rows: vec![TopicsPage { topics, matched }],
        as_of,
        more: None,
        not_searched: Vec::new(),
    }
}
