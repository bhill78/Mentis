//! `owner_decisions`: `Conversations.owner_decisions`, `conversation/__init__.py:6319`, under
//! `Surface.owner_decisions`, `worker.py:2106`. Facts only. A non-Conversation is `NotFound`, and
//! the words that refuse it, naming `orient`, are the door's.
//!
//! **A failed read forwards.** `contracts/ops.md` makes a failed read `Record`, but Python answers
//! empty lists when its first read fails, so that route's Python wins (its own last rule) and Python
//! is asked.

use std::collections::{HashMap, HashSet};

use mentis_record::{Flow, Param, ReadScope};
use serde::Serialize;

use crate::acts::{Act, text};
use crate::stored::{Object, python_says};
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest, act_columns, python};

const IS_CONVERSATION: &str = "SELECT family, def_name FROM entry WHERE id = ?1";

/// `detail_is={"expects": "decision"}`, newest first.
const ASKED: &str = concat!(
    "SELECT ",
    act_columns!(),
    " FROM operational WHERE conversation = ?1 AND act = 'expectation-recorded' \
     AND json_extract(detail, '$.expects') = 'decision' ORDER BY seq DESC"
);

/// `operational_under`.
const UNDER: &str = concat!(
    "SELECT ",
    act_columns!(),
    " FROM operational WHERE caused_by IN (SELECT value FROM json_each(?1)) ORDER BY seq"
);

/// `ORIENTATION_DECISIONS`, and `PAGE`, the most this ever gives of each.
const DEFAULT_MOST: u32 = 5;
const MOST: u32 = 40;

/// Owner decisions.
#[derive(Clone, Copy, Debug, Default)]
pub struct OwnerDecisions;

/// A Conversation. `most` is [`ReadRequest::limit`].
#[derive(Clone, Debug, Default)]
pub struct OwnerDecisionsArgs {
    pub conversation: String,
}

/// One decision question.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct DecisionRow {
    pub expectation: String,
    pub post: Option<String>,
    pub question: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub answer: Option<String>,
}

/// The answer's one row: the counts are of every question, beside lists cut to `most`.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct DecisionsPage {
    pub conversation: String,
    pub open: Vec<DecisionRow>,
    pub answered: Vec<DecisionRow>,
    pub open_count: u64,
    pub answered_count: u64,
}

impl ReadOp for OwnerDecisions {
    type Args = OwnerDecisionsArgs;
    type Row = DecisionsPage;

    const NAME: &'static str = "owner_decisions";
    /// The position, whether it is a Conversation, the questions, and what they caused.
    const BUDGET: Budget = Budget { statements: 4 };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<OwnerDecisionsArgs>,
    ) -> Result<ReadAnswer<DecisionsPage>, OpError> {
        let as_of = scope.position();
        let conversation = python::strip(&request.args.conversation).to_owned();
        let most = request.limit.unwrap_or(DEFAULT_MOST).min(MOST) as usize;
        let forwarded = |failed: OpError| match failed {
            OpError::Record(error) => python_says(&error.to_string()),
            other => other,
        };

        let mut is_conversation = false;
        scope
            .query(IS_CONVERSATION, &[Param::Text(&conversation)], &mut |row| {
                is_conversation = text(row, 0)?.as_deref() == Some("entry")
                    && text(row, 1)?.as_deref() == Some("conversation");
                Ok(Flow::Stop)
            })
            .map_err(|error| forwarded(error.into()))?;
        if !is_conversation {
            return Err(OpError::NotFound { what: conversation });
        }

        let mut asked = Vec::new();
        scope
            .query(ASKED, &[Param::Text(&conversation)], &mut |row| {
                asked.push(Act::read(row, 0)?);
                Ok(Flow::Continue)
            })
            .map_err(|error| forwarded(error.into()))?;

        let mut answered: HashMap<String, Act> = HashMap::new();
        let mut closed: HashSet<String> = HashSet::new();
        if !asked.is_empty() {
            let parents = mentis_rules::id_list(asked.iter().map(|a| a.id.as_str()));
            scope
                .query(UNDER, &[Param::Text(&parents)], &mut |row| {
                    let act = Act::read(row, 0)?;
                    let Some(cause) = act.caused_by.clone() else {
                        return Ok(Flow::Continue);
                    };
                    if act.is("decision-answered") {
                        answered.entry(cause).or_insert(act);
                    } else if act.is("expectation-met") {
                        closed.insert(cause);
                    }
                    Ok(Flow::Continue)
                })
                .map_err(|error| forwarded(error.into()))?;
        }

        let mut open = Vec::new();
        let mut settled = Vec::new();
        for a in &asked {
            let words = question_words(a)?;
            let mut row = DecisionRow {
                expectation: a.id.clone(),
                post: a.turn.clone(),
                question: if words.is_empty() {
                    "(no question words)".to_owned()
                } else {
                    words
                },
                answer: None,
            };
            if let Some(got) = answered.get(&a.id) {
                row.answer = Some(answer_words(got)?);
                settled.push(row);
            } else if !closed.contains(&a.id) {
                open.push(row);
            }
        }
        let (open_count, answered_count) = (open.len() as u64, settled.len() as u64);
        open.truncate(most);
        settled.truncate(most);
        Ok(ReadAnswer {
            rows: vec![DecisionsPage {
                conversation,
                open,
                answered: settled,
                open_count,
                answered_count,
            }],
            as_of,
            more: None,
            not_searched: Vec::new(),
        })
    }
}

/// `first_line(d.get("question") or a.get("because") or "", 140)`, and `""` for what isn't text.
fn question_words(act: &Act) -> Result<String, OpError> {
    let detail = act.detail_object()?;
    let said = match detail.get("question") {
        Some(question) if question.truthy() != Some(false) => question
            .truthy()
            .ok_or_else(|| python_says("a question this can't read"))
            .and_then(|_| question.string())?,
        _ => act.because.clone(),
    };
    Ok(python::first_line(said.as_deref().unwrap_or(""), 140))
}

/// The option's label, or where to read the owner's own words.
fn answer_words(got: &Act) -> Result<String, OpError> {
    let detail: Object = got.detail_object()?;
    if let Some(label) = detail.get("label")
        && let Some(label) = label.string()?
        && !label.is_empty()
    {
        return Ok(python::first_line(&label, 100));
    }
    if detail.is_truthy("reply")? {
        let reply = detail
            .text("reply")?
            .ok_or_else(|| python_says("a reply that isn't text"))?;
        return Ok(format!("in their own words, reply {reply}"));
    }
    Ok("answered".to_owned())
}
