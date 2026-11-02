//! `resolve`: `Surface.resolve`, `worker.py:1126`. What an identity is and what the record says about
//! it. Kind by kind, and **a kind that isn't here forwards,** which is always correct and only slower.
//!
//! [`OpError::NotOwned`], so Python answers:
//!
//! - **Held files.** An artifact and an acquired observation ask whether a file exists and read its
//!   first bytes, which no statement says. Those wait for the op's own `held` field, not built here
//!   (`docs/rust/R3-seams.md`, section 4).
//! - **The render engine.** A Turn with a fillable block or a response set, and a response set. Those
//!   wait for R2's `extract`, and there will be no second extraction.
//! - **Anchors.** An Anchor, a Turn holding an anchor part, and a Conversation opened from one. They
//!   are read by selector, grapheme and every reactor's own line, and this release keeps them.
//!
//! Every sentence that tells a reader what to do next (`note`, `standing`) is the door's: this says
//! `stands`, `superseded_by` and `knowing`, and the door words them. So is `known`: an unknown
//! reference is [`OpError::NotFound`].

use std::collections::HashMap;

use mentis_record::{Flow, Id, Param, ReadScope};
use mentis_rules::{
    IncomingLinks, ROOTS_STATEMENTS, Reading, STANDING_STATEMENTS, STATEMENTS, Seen, Versioned,
};
use serde::Serialize;

use crate::acts::{real, text};
use crate::forms::{self, Form};
use crate::stored::{Object, Stored, python_says};
use crate::turn_line::{parts_of, turn_line};
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest, python};

const HEAD: &str = "SELECT family, def_name, attributed_to, written_by, recorded_at, link_from, \
     link_to, link_relation FROM entry WHERE id = ?1";

/// The links every kind here reads, of this one id.
const NEAR: &str = "SELECT id, link_relation, link_from, link_to FROM entry \
     WHERE (link_from = ?1 AND link_relation IN \
              ('in-conversation', 'participates-in', 'topic-of', 'opened-from')) \
        OR (link_to = ?1 AND link_relation IN ('participates-in', 'about-topic')) \
     ORDER BY seq";

/// `sets_on`, of the Turn's root.
const HAS_SETS: &str = "SELECT 1 FROM entry l JOIN entry e ON e.id = l.link_from \
     WHERE l.link_relation = 'responds-to' AND l.link_to = ?1 AND e.def_name = 'response-set' \
     LIMIT 1";

/// `Conversations.contributions`: each Turn's time, and whether it was ever superseded, which is
/// all that sends it through `presented`, which raises on some.
const TURNS: &str = "SELECT e.id, e.recorded_at, json_valid(e.body), EXISTS (SELECT 1 FROM entry s \
       WHERE s.link_to = e.id AND s.link_relation = (SELECT json_extract(d.body, '$.relation') \
         FROM entry d WHERE d.family = 'definition' \
           AND json_extract(d.body, '$.substrate_role') = 'supersedes' ORDER BY d.seq LIMIT 1)) \
     FROM entry e \
     WHERE e.id IN (SELECT l.link_from FROM entry l \
                    WHERE l.link_relation = 'in-conversation' AND l.link_to = ?1) \
       AND e.family = 'entry' AND e.def_name = 'contribution' ORDER BY e.seq";

/// `current_definition(kind)`'s `knowing`, by version.
const KNOWING: &str = "SELECT def_version, json_extract(body, '$.knowing') FROM entry \
     WHERE family = 'definition' AND def_name = ?1 ORDER BY seq";

const HELD: &str = "SELECT id FROM entry WHERE id IN (SELECT value FROM json_each(?1))";

/// Resolve.
#[derive(Clone, Copy, Debug, Default)]
pub struct Resolve;

/// A reference. Absent or not a string, it never reaches the op.
#[derive(Clone, Debug, Default)]
pub struct ResolveArgs {
    pub reference: String,
}

/// `presented`'s `revision`.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct RevisionFacts {
    pub versions: u32,
    pub current: String,
    pub edited_at: f64,
    pub edited_by: Option<String>,
}

/// `presented`'s `deleted`.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct DeletedFacts {
    pub record: String,
    pub at: f64,
    pub by: Option<String>,
    pub because: Option<String>,
}

/// Somebody, with the alias they are shown by.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Named {
    pub participant: Stored,
    pub alias: Option<String>,
}

/// A structured reference in a Turn.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Reference {
    #[serde(rename = "type")]
    pub part_type: Stored,
    #[serde(rename = "ref")]
    pub reference: Stored,
    pub text: Stored,
}

/// What each moved kind adds to the common fields.
#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(untagged)]
pub enum Shape {
    Turn {
        conversation: Option<String>,
        number: Option<u64>,
        said: String,
        author: Option<String>,
        author_alias: Option<String>,
        addressed_to: Vec<Named>,
        references: Vec<Reference>,
        #[serde(skip_serializing_if = "Vec::is_empty")]
        decision_forms: Vec<Form>,
    },
    Conversation {
        name: Stored,
        about: Stored,
        turns: u64,
        participants: Vec<Named>,
    },
    Participant {
        alias: Option<String>,
        about: Stored,
        conversations: Vec<String>,
    },
    Topic {
        name: Stored,
        about: Stored,
        conversation: Option<String>,
        turns: u64,
    },
    Reaction {
        token: Stored,
        about: Stored,
    },
    Other {
        body: Stored,
    },
}

/// What a Link joins.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct LinkFacts {
    pub relation: Option<String>,
    pub links_from: Option<String>,
    pub links_to: Option<String>,
    pub links_from_alias: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub links_from_kind: Option<Option<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub links_from_name: Option<Stored>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub links_to_kind: Option<Option<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub links_to_name: Option<Stored>,
}

/// What the record says about one reference.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Resolved {
    #[serde(rename = "ref")]
    pub reference: String,
    pub kind: Option<String>,
    pub recorded_at: f64,
    pub attributed_to: Option<String>,
    pub written_by: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub revision: Option<RevisionFacts>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub deleted: Option<DeletedFacts>,
    pub stands: bool,
    pub established_by: Vec<String>,
    pub superseded_by: Vec<String>,
    pub what: String,
    #[serde(flatten)]
    pub shape: Shape,
    #[serde(flatten, skip_serializing_if = "Option::is_none")]
    pub link: Option<LinkFacts>,
    /// `"that"` or `"how"` where the Kind's current definition says so, the facts the door's
    /// `standing` sentence is chosen by. `None` is neither, and gets no sentence.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub knowing: Option<String>,
}

struct Head {
    family: Option<String>,
    kind: Option<String>,
    attributed_to: Option<String>,
    written_by: Option<String>,
    recorded_at: f64,
    from: Option<String>,
    to: Option<String>,
    relation: Option<String>,
}

struct Near {
    id: String,
    relation: String,
    from: Option<String>,
    to: Option<String>,
}

impl ReadOp for Resolve {
    type Args = ResolveArgs;
    type Row = Resolved;

    const NAME: &'static str = "resolve";
    /// The position, the entry, how it reads, its standing, the links near it, and its Kind's
    /// `knowing`; for a Turn its root, its sets, its Conversation's Turns and how the superseded
    /// ones read, the aliases and the forms; for a Topic the filings' standing and which are held;
    /// and for a Link how each end reads.
    const BUDGET: Budget = Budget {
        statements: 4
            + 2 * STATEMENTS
            + STANDING_STATEMENTS
            + ROOTS_STATEMENTS
            + 2
            + STATEMENTS
            + forms::ON_TURN_STATEMENTS
            + STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<ResolveArgs>,
    ) -> Result<ReadAnswer<Resolved>, OpError> {
        let as_of = scope.position();
        let row = read_one(scope, &request.args.reference)?;
        Ok(ReadAnswer {
            rows: vec![row],
            as_of,
            more: None,
            not_searched: Vec::new(),
        })
    }
}

/// Python would say this one.
fn forward(what: &str) -> OpError {
    python_says(what)
}

fn read_one(scope: &mut dyn ReadScope, reference: &str) -> Result<Resolved, OpError> {
    let id = Id(reference.to_owned());
    let mut head = None;
    scope.query(HEAD, &[Param::Text(reference)], &mut |row| {
        head = Some(Head {
            family: text(row, 0)?,
            kind: text(row, 1)?,
            attributed_to: text(row, 2)?,
            written_by: text(row, 3)?,
            recorded_at: real(row, 4)?,
            from: text(row, 5)?,
            to: text(row, 6)?,
            relation: text(row, 7)?,
        });
        Ok(Flow::Stop)
    })?;
    let Some(head) = head else {
        return Err(OpError::NotFound {
            what: reference.to_owned(),
        });
    };
    let kind = head.kind.as_deref();

    // Kinds this release keeps with Python, before anything else is read for them.
    match kind {
        Some("response-set") => return Err(forward("a response set: the render engine")),
        Some("anchor") => return Err(forward("an Anchor")),
        _ => {}
    }

    let mut readings = mentis_rules::now_reads(scope, std::slice::from_ref(&id))?;
    let reading = readings
        .remove(&id)
        .ok_or_else(|| forward("an entry that went between two reads"))?;
    if reading.python_says {
        return Err(forward("an entry Python can't read"));
    }

    let standing = mentis_rules::standing_many(scope, std::slice::from_ref(&id), None)?
        .remove(&id)
        .ok_or_else(|| forward("no standing"))?;

    let mut near: Vec<Near> = Vec::new();
    scope.query(NEAR, &[Param::Text(reference)], &mut |row| {
        near.push(Near {
            id: text(row, 0)?.unwrap_or_default(),
            relation: text(row, 1)?.unwrap_or_default(),
            from: text(row, 2)?,
            to: text(row, 3)?,
        });
        Ok(Flow::Continue)
    })?;

    let (what, shape) = match kind {
        Some("contribution") => (
            "a Turn".to_owned(),
            a_turn(scope, &id, &reading, &head, &near)?,
        ),
        Some("conversation") => (
            "a Conversation".to_owned(),
            a_conversation(scope, &id, &reading, &near)?,
        ),
        Some("participant") => {
            let body = Object::exactly(&reading.body_json)?;
            let seen =
                mentis_rules::reads(scope, std::slice::from_ref(&id), Versioned::Participants)?;
            let mut conversations: Vec<String> = near
                .iter()
                .filter(|l| l.relation == "participates-in" && l.from.as_deref() == Some(reference))
                .filter_map(|l| l.to.clone())
                .collect();
            conversations.sort();
            conversations.dedup();
            (
                "a Participant".to_owned(),
                Shape::Participant {
                    alias: Some(alias(&seen, &id)?),
                    about: body.get_or_null("about"),
                    conversations,
                },
            )
        }
        Some("topic") => (
            "a Topic".to_owned(),
            a_topic(scope, reference, &reading, &near)?,
        ),
        Some("reaction") => {
            let body = Object::exactly(&reading.body_json)?;
            (
                "a Reaction".to_owned(),
                Shape::Reaction {
                    token: body.get_or_null("token"),
                    about: body.get_or_null("about"),
                },
            )
        }
        _ => {
            if head.family.as_deref() == Some("admission") {
                let body = Object::exactly(&reading.body_json)?;
                let envelope = Object::or_empty(body.get_or_null("envelope").text())?;
                if envelope.is_truthy("bulk_source")? {
                    return Err(forward("an acquired observation: held files"));
                }
                if body.says("content", "held")? {
                    return Err(forward("a held artifact: held files"));
                }
            }
            let shown = match kind {
                None => "None".to_owned(),
                Some(kind) => {
                    python::repr(kind).ok_or_else(|| forward("a Kind Python has to show itself"))?
                }
            };
            let body = Stored::parse(&reading.body_json)
                .ok_or_else(|| forward("a body this can't read"))?;
            (format!("an entry of kind {shown}"), Shape::Other { body })
        }
    };

    let mut what = what;
    let link = match &head.relation {
        None => None,
        Some(relation) => {
            what = "a Link".to_owned();
            Some(a_link(scope, relation, &head)?)
        }
    };

    Ok(Resolved {
        reference: reference.to_owned(),
        kind: head.kind.clone(),
        recorded_at: head.recorded_at,
        attributed_to: head.attributed_to.clone(),
        written_by: head.written_by.clone(),
        revision: reading.revision.as_ref().map(|r| RevisionFacts {
            versions: r.versions,
            current: r.current.0.clone(),
            edited_at: r.edited_at,
            edited_by: r.edited_by.as_ref().map(|by| by.0.clone()),
        }),
        deleted: reading.deleted.as_ref().map(|d| DeletedFacts {
            record: d.record.0.clone(),
            at: d.at,
            by: d.by.as_ref().map(|by| by.0.clone()),
            because: d.because.clone(),
        }),
        stands: standing.stands,
        established_by: standing
            .established_by
            .iter()
            .map(|i| i.0.clone())
            .collect(),
        superseded_by: standing.superseded_by.iter().map(|i| i.0.clone()).collect(),
        what,
        shape,
        link,
        knowing: match kind {
            Some(kind) => knowing_of(scope, kind)?,
            None => None,
        },
    })
}

/// `Conversations.alias`, or Python where it raises.
fn alias(seen: &HashMap<Id, Seen>, id: &Id) -> Result<String, OpError> {
    mentis_rules::alias_of(seen.get(id), id).ok_or_else(|| forward("somebody Python can't read"))
}

/// `knowing_of`, the first of the newest version, and only the two ladders.
fn knowing_of(scope: &mut dyn ReadScope, kind: &str) -> Result<Option<String>, OpError> {
    let mut best: Option<(i64, Option<String>)> = None;
    scope.query(KNOWING, &[Param::Text(kind)], &mut |row| {
        let version = match row.value(0)? {
            mentis_record::Value::Integer(version) => version,
            _ => i64::MIN,
        };
        if best.as_ref().is_none_or(|(held, _)| version > *held) {
            // A value that isn't text is on neither ladder, whatever it is.
            let said = match row.value(1)? {
                mentis_record::Value::Text(_) => text(row, 1)?,
                _ => None,
            };
            best = Some((version, said));
        }
        Ok(Flow::Continue)
    })?;
    Ok(best
        .and_then(|(_, said)| said)
        .filter(|said| said == "that" || said == "how"))
}

/// `_FILL_FENCE`, as "might this post hold one". It takes more than the expression does, since it
/// doesn't ask where the word ends, and what it takes goes to Python, which is always correct.
fn might_hold_a_block(words: &str) -> bool {
    words.split('\n').any(|line| {
        let line = line.trim_start_matches([' ', '\t']);
        let rest = line.trim_start_matches('`');
        let rest = if line.len() - rest.len() >= 3 {
            rest
        } else {
            let tilde = line.trim_start_matches('~');
            if line.len() - tilde.len() >= 3 {
                tilde
            } else {
                return false;
            }
        };
        let rest = rest.trim_start_matches([' ', '\t']);
        ["form", "checklist", "table", "pad", "panel"]
            .iter()
            .any(|word| rest.starts_with(word))
    })
}

/// The Turns of a Conversation, with each one's number. Raises where `contributions` would.
fn numbered_turns(scope: &mut dyn ReadScope, conversation: &str) -> Result<Vec<String>, OpError> {
    let mut turns: Vec<(String, f64)> = Vec::new();
    let mut superseded: Vec<Id> = Vec::new();
    let mut unreadable = false;
    scope.query(TURNS, &[Param::Text(conversation)], &mut |row| {
        let id = text(row, 0)?.unwrap_or_default();
        if !matches!(row.value(2)?, mentis_record::Value::Integer(1)) {
            unreadable = true;
        }
        if matches!(row.value(3)?, mentis_record::Value::Integer(1)) {
            superseded.push(Id(id.clone()));
        }
        turns.push((id, real(row, 1)?));
        Ok(Flow::Continue)
    })?;
    if unreadable {
        return Err(forward("a Turn this can't read"));
    }
    let read = mentis_rules::now_reads(scope, &superseded)?;
    if read.values().any(|reading| reading.python_says) {
        return Err(forward("a Turn Python can't read"));
    }
    turns.sort_by(|a, b| a.1.total_cmp(&b.1));
    Ok(turns.into_iter().map(|(id, _)| id).collect())
}

fn a_turn(
    scope: &mut dyn ReadScope,
    id: &Id,
    reading: &Reading,
    head: &Head,
    near: &[Near],
) -> Result<Shape, OpError> {
    let body = Object::exactly(&reading.body_json)?;
    let parts = parts_of(&body)?;
    for part in &parts {
        if part.says("type", "anchor")? {
            return Err(forward("a Turn holding an anchor part"));
        }
    }

    let root = mentis_rules::roots(scope, std::slice::from_ref(id))?
        .remove(id)
        .ok_or_else(|| forward("no root"))?;
    let mut has_sets = false;
    scope.query(HAS_SETS, &[Param::Text(&root.0)], &mut |_| {
        has_sets = true;
        Ok(Flow::Stop)
    })?;
    if has_sets {
        return Err(forward("a Turn with a response set: the render engine"));
    }
    if reading.deleted.is_none() {
        for part in &parts {
            if part.says("type", "text")? {
                let words = match part.get("text") {
                    None => None,
                    Some(words) if words.truthy() == Some(false) => None,
                    Some(words) => match words.string()? {
                        Some(words) => Some(words),
                        None => return Err(forward("words that aren't text")),
                    },
                };
                if words.is_some_and(|words| might_hold_a_block(&words)) {
                    return Err(forward("a Turn with a fillable block: the render engine"));
                }
            }
        }
    }

    let conversation = near
        .iter()
        .find(|l| l.relation == "in-conversation" && l.from.as_deref() == Some(id.0.as_str()))
        .and_then(|l| l.to.clone());
    let number = match &conversation {
        None => None,
        Some(conversation) => numbered_turns(scope, conversation)?
            .iter()
            .position(|turn| *turn == id.0)
            .map(|at| at as u64 + 1),
    };

    let said = turn_line(reading)?;
    let mut references = Vec::new();
    for part in &parts {
        if part.is_truthy("ref")? {
            references.push(Reference {
                part_type: part
                    .get("type")
                    .cloned()
                    .ok_or_else(|| forward("a reference with no type"))?,
                reference: part.get_or_null("ref"),
                text: part.get_or_null("text"),
            });
        }
    }
    let addressed: Vec<Stored> = match body.get("addressed_to") {
        None => Vec::new(),
        Some(addressed) => addressed.items_or_none()?,
    };
    let mut who: Vec<Id> = Vec::new();
    who.extend(head.attributed_to.clone().map(Id));
    let mut addressed_ids = Vec::with_capacity(addressed.len());
    for participant in &addressed {
        let named = participant
            .string()?
            .ok_or_else(|| forward("somebody addressed who isn't a reference"))?;
        addressed_ids.push(Id(named));
    }
    who.extend(addressed_ids.iter().cloned());
    who.sort();
    who.dedup();
    let seen = mentis_rules::reads(scope, &who, Versioned::Participants)?;
    let mut addressed_to = Vec::with_capacity(addressed.len());
    for (participant, named) in addressed.iter().zip(&addressed_ids) {
        addressed_to.push(Named {
            participant: participant.clone(),
            alias: Some(alias(&seen, named)?),
        });
    }
    let author_alias = match &head.attributed_to {
        None => None,
        Some(author) => Some(alias(&seen, &Id(author.clone()))?),
    };

    let decision_forms = forms::on_turn(scope, &root.0)?;
    Ok(Shape::Turn {
        conversation,
        number,
        said,
        author: head.attributed_to.clone(),
        author_alias,
        addressed_to,
        references,
        decision_forms,
    })
}

fn a_conversation(
    scope: &mut dyn ReadScope,
    id: &Id,
    reading: &Reading,
    near: &[Near],
) -> Result<Shape, OpError> {
    let body = Object::exactly(&reading.body_json)?;
    if near
        .iter()
        .any(|l| l.relation == "opened-from" && l.from.as_deref() == Some(id.0.as_str()))
    {
        return Err(forward("a Conversation opened from an Anchor"));
    }
    let turns = numbered_turns(scope, &id.0)?.len() as u64;
    let mut people: Vec<Id> = near
        .iter()
        .filter(|l| l.relation == "participates-in" && l.to.as_deref() == Some(id.0.as_str()))
        .filter_map(|l| l.from.clone())
        .map(Id)
        .collect();
    people.sort();
    people.dedup();
    let seen = mentis_rules::reads(scope, &people, Versioned::Participants)?;
    let mut participants = Vec::with_capacity(people.len());
    for person in &people {
        participants.push(Named {
            participant: Stored::of(&person.0),
            alias: Some(alias(&seen, person)?),
        });
    }
    Ok(Shape::Conversation {
        name: body.get_or_null("name"),
        about: body.get_or_null("about"),
        turns,
        participants,
    })
}

fn a_topic(
    scope: &mut dyn ReadScope,
    reference: &str,
    reading: &Reading,
    near: &[Near],
) -> Result<Shape, OpError> {
    let body = Object::exactly(&reading.body_json)?;
    let conversation = near
        .iter()
        .find(|l| l.relation == "topic-of" && l.from.as_deref() == Some(reference))
        .and_then(|l| l.to.clone());
    // `topic_contributions`: the filings nothing has ended, and which of those Turns are held.
    let filings: Vec<&Near> = near
        .iter()
        .filter(|l| l.relation == "about-topic" && l.to.as_deref() == Some(reference))
        .collect();
    let ids: Vec<Id> = filings.iter().map(|l| Id(l.id.clone())).collect();
    let links = IncomingLinks::load(scope, &ids)?;
    let filed: Vec<&str> = filings
        .iter()
        .filter(|l| {
            links
                .standing(&Id(l.id.clone()), None)
                .superseded_by
                .is_empty()
        })
        .filter_map(|l| l.from.as_deref())
        .collect();
    let mut turns = 0;
    if !filed.is_empty() {
        let asked = mentis_rules::id_list(filed.iter().copied());
        scope.query(HELD, &[Param::Text(&asked)], &mut |_| {
            turns += 1;
            Ok(Flow::Continue)
        })?;
    }
    Ok(Shape::Topic {
        name: body.get_or_null("name"),
        about: body.get_or_null("about"),
        conversation,
        turns,
    })
}

/// A Link's ends, as `resolve`'s last part reads them.
fn a_link(scope: &mut dyn ReadScope, relation: &str, head: &Head) -> Result<LinkFacts, OpError> {
    let mut ends: Vec<Id> = Vec::new();
    ends.extend(head.from.clone().map(Id));
    ends.extend(head.to.clone().map(Id));
    let seen = mentis_rules::reads(scope, &ends, Versioned::All)?;
    let mut facts = LinkFacts {
        relation: Some(relation.to_owned()),
        links_from: head.from.clone(),
        links_to: head.to.clone(),
        links_from_alias: None,
        links_from_kind: None,
        links_from_name: None,
        links_to_kind: None,
        links_to_name: None,
    };
    let read = |end: &Option<String>| -> Result<Option<(Option<String>, Option<Stored>)>, OpError> {
        let Some(one) = end.as_ref().and_then(|end| seen.get(&Id(end.clone()))) else {
            return Ok(None);
        };
        if one.reading.python_says {
            return Err(forward("a Link's end Python can't read"));
        }
        let body = Object::or_empty(&one.reading.body_json)?;
        let name = body.is_truthy("name")?.then(|| body.get_or_null("name"));
        Ok(Some((one.kind.clone(), name)))
    };
    if let Some((kind, name)) = read(&head.from)? {
        if kind.as_deref() == Some("participant")
            && let Some(from) = &head.from
        {
            let from = Id(from.clone());
            facts.links_from_alias = Some(alias(&seen, &from)?);
        }
        facts.links_from_kind = Some(kind);
        facts.links_from_name = name;
    }
    if let Some((kind, name)) = read(&head.to)? {
        facts.links_to_kind = Some(kind);
        facts.links_to_name = name;
    }
    Ok(facts)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_fence_that_might_hold_a_block_is_python_s_to_look_at() {
        for yes in [
            "```form",
            "  ~~~~ table x",
            "a\n```` checklist",
            "```panel version=1",
            "```formal",
        ] {
            assert!(might_hold_a_block(yes), "{yes:?}");
        }
        for no in ["``form", "text ```form", "```python", "~~form"] {
            assert!(!might_hold_a_block(no), "{no:?}");
        }
    }
}
