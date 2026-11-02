//! `history` with no `set`: `Surface.history`, `worker.py:1744`. `participant` is the actor asked
//! about, a filter, and has nothing to do with who is calling.
//!
//! Python has no continuation here, so `more` stays `None` and no cursor meaning is promised. The
//! deleted marking's sentence is the door's: the row holds `deleted` and `deleted_material`.

use std::collections::HashMap;

use mentis_record::{Flow, Id, Param, ReadScope, Value};
use mentis_rules::{STATEMENTS, Seen, Versioned};
use serde::Serialize;

use crate::acts::{Act, COLUMNS, text};
use crate::stored::{Stored, python_says};
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest, act_columns};

/// Whether `about` and `detail` are JSON, which `json.loads` raises on for every row it is handed,
/// returned or not.
macro_rules! act_rows {
    ($where:literal) => {
        concat!(
            "SELECT ",
            act_columns!(),
            ", json_valid(about) AND json_valid(detail) FROM operational ",
            $where,
            "ORDER BY seq DESC"
        )
    };
}

const ALL: &str = act_rows!("");
const IN_CONVERSATION: &str = act_rows!("WHERE conversation = ?1 ");
const ON_TURN: &str = act_rows!("WHERE turn = ?1 ");
const IN_CONVERSATION_ON_TURN: &str = act_rows!("WHERE conversation = ?1 AND turn = ?2 ");

/// `producing_act`: the first `produced` link to each artifact whose act exists.
const PRODUCING: &str = concat!(
    "SELECT l.link_to, ",
    "o.id, o.act, o.at, o.actor, o.conversation, o.turn, o.execution, o.runtime, o.because, ",
    "o.caused_by, o.about, o.detail ",
    "FROM entry l JOIN operational o ON o.id = l.link_from ",
    "WHERE l.link_relation = 'produced' AND l.link_to IN (SELECT value FROM json_each(?1)) ",
    "ORDER BY l.seq"
);

/// `_result_turns`, for every execution at once: each result with what its run was started by.
const RESULTS: &str = "SELECT r.execution, r.turn, s.caused_by, s.id FROM operational r \
     LEFT JOIN operational s ON s.id = r.caused_by \
     WHERE r.act = 'result-returned' AND r.execution IN (SELECT value FROM json_each(?1)) \
     ORDER BY r.seq";

/// `artifacts.RETURNED`, `artifacts.SUBMITTED`.
const RETURNED: &str = "artifact-returned";
const SUBMITTED: &str = "artifact-submitted";

/// `PAGE`, when no limit was given.
const DEFAULT_LIMIT: u32 = 40;

/// History.
#[derive(Clone, Copy, Debug, Default)]
pub struct History;

impl History {
    /// The most one read returns. Python has no cap and a budget needs one, so above this Python
    /// answers.
    pub const MOST: u32 = 1000;
}

/// Filters, all optional.
#[derive(Clone, Debug, Default)]
pub struct HistoryArgs {
    pub conversation: Option<String>,
    pub turn: Option<String>,
    pub participant: Option<String>,
}

/// What a deleted Turn or Conversation an artifact came in on says about it.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct DeletedMark {
    pub what: String,
    #[serde(rename = "ref")]
    pub reference: String,
    pub when: f64,
    pub by: Option<String>,
}

/// One act, as recorded.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ActRow {
    pub id: String,
    pub act: Option<String>,
    pub at: f64,
    pub actor: Option<String>,
    pub actor_alias: Option<String>,
    pub conversation: Option<String>,
    pub turn: Option<String>,
    pub execution: Option<String>,
    pub runtime: Option<String>,
    pub because: Option<String>,
    pub caused_by: Option<String>,
    pub about: Stored,
    pub detail: Stored,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub deleted: Option<DeletedMark>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub deleted_material: Option<String>,
}

/// The answer's one row: `matched` is every act the filters kept, beside the page returned.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct HistoryPage {
    pub acts: Vec<ActRow>,
    pub matched: u64,
    pub not_returned: u64,
}

/// `if conversation:`: an empty filter is no filter.
fn given(filter: &Option<String>) -> Option<&str> {
    filter.as_deref().filter(|value| !value.is_empty())
}

impl ReadOp for History {
    type Args = HistoryArgs;
    type Row = HistoryPage;

    const NAME: &'static str = "history";
    /// The position, the acts, the actors' aliases, and for acts about an artifact what produced
    /// it, the results of those runs, and how the Conversation and Turns concerned now read.
    const BUDGET: Budget = Budget {
        statements: 4 + 2 * STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<HistoryArgs>,
    ) -> Result<ReadAnswer<HistoryPage>, OpError> {
        let as_of = scope.position();
        let limit = request.limit.unwrap_or(DEFAULT_LIMIT);
        if limit > History::MOST {
            return Err(python_says("a limit over what one read returns here"));
        }
        let limit = limit as usize;
        let args = &request.args;
        let participant = given(&args.participant);
        let (statement, params): (&'static str, Vec<Param<'_>>) =
            match (given(&args.conversation), given(&args.turn)) {
                (None, None) => (ALL, Vec::new()),
                (Some(conversation), None) => (IN_CONVERSATION, vec![Param::Text(conversation)]),
                (None, Some(turn)) => (ON_TURN, vec![Param::Text(turn)]),
                (Some(conversation), Some(turn)) => (
                    IN_CONVERSATION_ON_TURN,
                    vec![Param::Text(conversation), Param::Text(turn)],
                ),
            };

        let mut acts: Vec<Act> = Vec::new();
        let mut matched = 0u64;
        let mut unreadable = false;
        scope.query(statement, &params, &mut |row| {
            unreadable |= !matches!(row.value(COLUMNS)?, Value::Integer(1));
            if let Some(wanted) = participant
                && text(row, 3)?.as_deref() != Some(wanted)
            {
                return Ok(Flow::Continue);
            }
            matched += 1;
            if acts.len() < limit {
                acts.push(Act::read(row, 0)?);
            }
            Ok(Flow::Continue)
        })?;
        if unreadable {
            return Err(python_says("an act this can't read"));
        }

        let mut actors: Vec<Id> = acts
            .iter()
            .filter_map(|a| a.actor.clone().filter(|actor| !actor.is_empty()))
            .map(Id)
            .collect();
        actors.sort();
        actors.dedup();
        let seen = mentis_rules::reads(scope, &actors, Versioned::Participants)?;

        // The artifacts each row is about, in its order, the first marked being the one it says.
        let mut about: Vec<Vec<String>> = Vec::with_capacity(acts.len());
        let mut artifacts: Vec<String> = Vec::new();
        for act in &acts {
            let mut here = Vec::new();
            for item in act.about_items()? {
                if let Some(text) = item.string()?
                    && text.starts_with("adm-")
                {
                    artifacts.push(text.clone());
                    here.push(text);
                }
            }
            about.push(here);
        }
        let marks = deleted_marks(scope, &artifacts)?;

        let mut rows = Vec::with_capacity(acts.len());
        for (act, artifacts) in acts.iter().zip(about) {
            let actor_alias = match act.actor.as_deref().filter(|actor| !actor.is_empty()) {
                None => None,
                Some(actor) => {
                    let id = Id(actor.to_owned());
                    Some(
                        mentis_rules::alias_of(seen.get(&id), &id)
                            .ok_or_else(|| python_says("an actor this can't read"))?,
                    )
                }
            };
            let mark = artifacts
                .iter()
                .find_map(|artifact| marks.get(artifact).map(|mark| (artifact, mark)));
            rows.push(ActRow {
                id: act.id.clone(),
                act: act.act.clone(),
                at: act.at,
                actor: act.actor.clone(),
                actor_alias,
                conversation: act.conversation.clone(),
                turn: act.turn.clone(),
                execution: act.execution.clone(),
                runtime: act.runtime.clone(),
                because: act.because.clone(),
                caused_by: act.caused_by.clone(),
                about: act.about()?.clone(),
                detail: act.detail()?.clone(),
                deleted: mark.map(|(_, mark)| mark.clone()),
                deleted_material: mark.map(|(artifact, _)| artifact.clone()),
            });
        }
        let not_returned = matched.saturating_sub(rows.len() as u64);
        Ok(ReadAnswer {
            rows: vec![HistoryPage {
                acts: rows,
                matched,
                not_returned,
            }],
            as_of,
            more: None,
            not_searched: Vec::new(),
        })
    }
}

/// `_deletion`: the record of an entry that now reads as deleted.
fn deletion(seen: &HashMap<Id, Seen>, reference: &str) -> Result<Option<DeletedMark>, OpError> {
    let Some(entry) = seen.get(&Id(reference.to_owned())) else {
        return Ok(None);
    };
    if entry.reading.python_says {
        return Err(python_says("an entry this can't read"));
    }
    let Some(deleted) = &entry.reading.deleted else {
        return Ok(None);
    };
    let what = match entry.kind.as_deref() {
        Some("contribution") => "turn".to_owned(),
        Some(kind) => kind.to_owned(),
        None => "entry".to_owned(),
    };
    Ok(Some(DeletedMark {
        what,
        reference: reference.to_owned(),
        when: deleted.at,
        by: deleted.by.as_ref().map(|by| by.0.clone()),
    }))
}

/// `artifacts.deleted_from` of each artifact, those it marks only. Two statements and one read of
/// what they name, or nothing for no artifacts.
fn deleted_marks(
    scope: &mut dyn ReadScope,
    artifacts: &[String],
) -> Result<HashMap<String, DeletedMark>, OpError> {
    let mut marks = HashMap::new();
    if artifacts.is_empty() {
        return Ok(marks);
    }
    let asked = mentis_rules::id_list(artifacts.iter().map(String::as_str));
    let mut made: HashMap<String, Act> = HashMap::new();
    scope.query(PRODUCING, &[Param::Text(&asked)], &mut |row| {
        if let Some(artifact) = text(row, 0)? {
            let act = Act::read(row, 1)?;
            made.entry(artifact).or_insert(act);
        }
        Ok(Flow::Continue)
    })?;
    made.retain(|_, act| act.is(RETURNED) || act.is(SUBMITTED));
    if made.is_empty() {
        return Ok(marks);
    }

    let mut executions: Vec<&str> = made
        .values()
        .filter(|act| act.is(RETURNED))
        .filter_map(|act| act.execution.as_deref())
        .filter(|execution| !execution.is_empty())
        .collect();
    executions.sort_unstable();
    executions.dedup();
    let mut results: HashMap<String, Vec<(String, Option<String>)>> = HashMap::new();
    if !executions.is_empty() {
        let asked = mentis_rules::id_list(executions.iter().copied());
        scope.query(RESULTS, &[Param::Text(&asked)], &mut |row| {
            // A result whose start the record doesn't hold counts for nothing.
            if let (Some(execution), Some(turn), Some(_)) =
                (text(row, 0)?, text(row, 1)?, text(row, 3)?)
                && !turn.is_empty()
            {
                results
                    .entry(execution)
                    .or_default()
                    .push((turn, text(row, 2)?));
            }
            Ok(Flow::Continue)
        })?;
    }

    // Every Turn that carried it, in `deleted_from`'s order.
    let mut carriers: HashMap<&str, Vec<String>> = HashMap::new();
    let mut named: Vec<Id> = Vec::new();
    for (artifact, act) in &made {
        let mut here = Vec::new();
        here.extend(act.turn.clone());
        if act.is(RETURNED)
            && let Some(execution) = act.execution.as_deref()
        {
            for (turn, started_by) in results.get(execution).map_or(&[][..], Vec::as_slice) {
                if *started_by == act.caused_by {
                    here.push(turn.clone());
                }
            }
        }
        here.retain(|turn| !turn.is_empty());
        let mut unique = Vec::with_capacity(here.len());
        for turn in here {
            if !unique.contains(&turn) {
                unique.push(turn);
            }
        }
        named.extend(unique.iter().cloned().map(Id));
        if let Some(conversation) = act.conversation.as_deref().filter(|c| !c.is_empty()) {
            named.push(Id(conversation.to_owned()));
        }
        carriers.insert(artifact, unique);
    }
    named.sort();
    named.dedup();
    let seen = mentis_rules::reads(scope, &named, Versioned::All)?;

    for (artifact, act) in &made {
        if let Some(conversation) = act.conversation.as_deref().filter(|c| !c.is_empty())
            && let Some(gone) = deletion(&seen, conversation)?
        {
            marks.insert(artifact.clone(), gone);
            continue;
        }
        let turns = &carriers[artifact.as_str()];
        if turns.is_empty() {
            continue;
        }
        let mut any_live = false;
        for turn in turns {
            let Some(entry) = seen.get(&Id(turn.clone())) else {
                continue;
            };
            if entry.reading.python_says {
                return Err(python_says("a Turn this can't read"));
            }
            any_live |= entry.reading.deleted.is_none();
        }
        if !any_live && let Some(gone) = deletion(&seen, &turns[0])? {
            marks.insert(artifact.clone(), gone);
        }
    }
    Ok(marks)
}
