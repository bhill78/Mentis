//! R4.2's owner-side durable views.

use std::time::Instant;

use mentis_ops::pyjson::{Py, dict};
use mentis_ops::views::{
    ConversationFields, ConversationFieldsArgs, DecisionsView, DecisionsViewArgs, IntakeView,
    IntakeViewArgs, Personas, ThreadView, ThreadViewArgs, TurnView, TurnViewArgs, TurnsView,
    TurnsViewArgs,
};
use mentis_ops::{OpError, ReadClass, ReadRequest, RecordError, python};
use mentis_record::READ_SCOPE_LIMIT;

use super::query::{Query, from_error};
use super::window::ids_named;
use super::{Ask, Context, Door, Reply, Route};

pub const PERSONAS: Route = Route {
    name: "personas",
    door: Door::Api,
    answer: personas,
};
pub const CONVERSATION_FIELDS: Route = Route {
    name: "conversation-fields",
    door: Door::Api,
    answer: conversation_fields,
};
pub const TURN_VIEW: Route = Route {
    name: "turn-view",
    door: Door::Api,
    answer: turn_view,
};
pub const INTAKE: Route = Route {
    name: "intake",
    door: Door::Api,
    answer: intake,
};
pub const TURNS: Route = Route {
    name: "turns",
    door: Door::Api,
    answer: turns,
};
pub const THREAD_VIEW: Route = Route {
    name: "thread-view",
    door: Door::Api,
    answer: thread_view,
};
pub const DECISIONS: Route = Route {
    name: "decisions",
    door: Door::FluidGet,
    answer: decisions,
};

fn request<A>(args: A) -> ReadRequest<A> {
    ReadRequest {
        args,
        cursor: None,
        limit: None,
        deadline: Instant::now() + READ_SCOPE_LIMIT,
    }
}

/// A read that can't finish in its time, or at all just now, is one Python can still answer: no
/// route here is left worse off than forwarding.
fn failed(error: OpError) -> Reply {
    match error {
        OpError::Busy { .. } | OpError::Record(RecordError::ScopeExpired) => Reply::NotOwned,
        other => from_error(other),
    }
}

/// A path segment read as itself. Python unquotes and may route anything else differently.
fn plain_id(segment: &str) -> bool {
    !segment.is_empty()
        && segment
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn turn_view(context: &Context, ask: &Ask) -> Reply {
    if Query::parse(&ask.query).is_none() {
        return Reply::NotOwned;
    }
    let Some(id) = ask.path.strip_prefix("/api/turns/") else {
        return Reply::NotOwned;
    };
    if !plain_id(id) {
        return Reply::NotOwned;
    }
    let Some(overlay) = context.snapshots.overlay() else {
        return Reply::NotOwned;
    };
    let asked = request(TurnViewArgs {
        turn: id.to_owned(),
        overlay,
    });
    match mentis_ops::run(&TurnView, &*context.record, ReadClass::Foreground, &asked) {
        Ok(mut read) => answer(read.rows.pop().expect("turn view answers one row").0),
        Err(OpError::NotFound { .. }) => Reply::NotOwned,
        Err(error) => failed(error),
    }
}

fn intake(context: &Context, ask: &Ask) -> Reply {
    if ask.path != "/api/intake" || Query::parse(&ask.query).is_none() {
        return Reply::NotOwned;
    }
    let Some(overlay) = context.snapshots.overlay() else {
        return Reply::NotOwned;
    };
    let asked = request(IntakeViewArgs { overlay });
    match mentis_ops::run(&IntakeView, &*context.record, ReadClass::Foreground, &asked) {
        Ok(mut read) => answer(read.rows.pop().expect("intake answers one row").0),
        Err(error) => failed(error),
    }
}

/// `_turns_read`'s refusal. `/api/turns` is not Fluid's door, so its kind is `_BadRequest`.
fn refused(words: &str) -> Reply {
    Reply::Answer {
        status: 400,
        content_type: "application/json",
        body: dict([("error", Py::str(words)), ("kind", Py::str("_BadRequest"))])
            .dumps()
            .into_bytes(),
    }
}

/// `_turns_read`'s ids: every `ids=` sent, joined. Its words are its own, so this isn't `_ids`.
fn turn_ids(query: &Query) -> Result<Vec<String>, Reply> {
    let raw = query.all("ids").join(",");
    let mut ids: Vec<String> = Vec::new();
    for id in raw.split(',') {
        let id = python::strip(id);
        if !id.is_empty() && !ids.iter().any(|seen| seen == id) {
            ids.push(id.to_owned());
        }
    }
    if ids.is_empty() {
        return Err(refused("name the Turns to read: /api/turns?ids=<id>,<id>"));
    }
    if ids.len() > 64 {
        return Err(refused(&format!(
            "{} Turns asked for in one read; at most 64 -- ask again for the rest",
            ids.len()
        )));
    }
    if let Some(id) = ids.iter().find(|id| id.contains('/')) {
        return Err(match python::repr(id) {
            Some(shown) => refused(&format!("not a Turn id: {shown}")),
            None => Reply::NotOwned,
        });
    }
    Ok(ids)
}

fn turns(context: &Context, ask: &Ask) -> Reply {
    if ask.path != "/api/turns" {
        return Reply::NotOwned;
    }
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let ids = match turn_ids(&query) {
        Ok(v) => v,
        Err(r) => return r,
    };
    let Some(overlay) = context.snapshots.overlay() else {
        return Reply::NotOwned;
    };
    let asked = request(TurnsViewArgs {
        turns: ids,
        overlay,
    });
    match mentis_ops::run(&TurnsView, &*context.record, ReadClass::Foreground, &asked) {
        Ok(mut read) => answer(read.rows.pop().unwrap().0),
        Err(error) => failed(error),
    }
}

fn thread_view(context: &Context, ask: &Ask) -> Reply {
    if Query::parse(&ask.query).is_none() {
        return Reply::NotOwned;
    }
    let Some(rest) = ask.path.strip_prefix("/api/conversations/") else {
        return Reply::NotOwned;
    };
    let Some((conversation, root)) = rest.split_once("/thread/") else {
        return Reply::NotOwned;
    };
    if !plain_id(conversation) || !plain_id(root) {
        return Reply::NotOwned;
    }
    let Some(overlay) = context.snapshots.overlay() else {
        return Reply::NotOwned;
    };
    let asked = request(ThreadViewArgs {
        conversation: conversation.into(),
        root: root.into(),
        overlay,
    });
    match mentis_ops::run(&ThreadView, &*context.record, ReadClass::Foreground, &asked) {
        Ok(mut read) => answer(read.rows.pop().unwrap().0),
        Err(error) => failed(error),
    }
}

fn decisions(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let (post, ids) = if query.first("ids").is_some() {
        match ids_named(query.first("ids"), "ids") {
            Ok(ids) => (None, ids),
            Err(reply) => return reply,
        }
    } else if let Some(post) = query.first("post") {
        (Some(post.to_owned()), Vec::new())
    } else {
        return super::query::bad_request("name the post: ?post=<id>, or ?ids=");
    };
    let Some(overlay) = context.snapshots.overlay() else {
        return Reply::NotOwned;
    };
    let asked = request(DecisionsViewArgs { post, ids, overlay });
    match mentis_ops::run(
        &DecisionsView,
        &*context.record,
        ReadClass::Foreground,
        &asked,
    ) {
        Ok(mut read) => {
            let mut row = read.rows.pop().unwrap().0;
            row.set(
                "cursor",
                mentis_ops::window::reads::change_cursor(read.as_of),
            );
            answer(row)
        }
        // `raise NotFound`, which `handle_get` words without the id.
        Err(OpError::NotFound { .. }) => Reply::Answer {
            status: 404,
            content_type: "application/json",
            body: dict([
                ("error", Py::str("no such Fluid surface")),
                ("path", Py::str(&ask.path)),
            ])
            .dumps()
            .into_bytes(),
        },
        Err(error) => failed(error),
    }
}

fn answer(row: Py) -> Reply {
    Reply::Answer {
        status: 200,
        content_type: "application/json",
        body: row.dumps().into_bytes(),
    }
}

fn personas(context: &Context, ask: &Ask) -> Reply {
    if ask.path != "/api/personas" || Query::parse(&ask.query).is_none() {
        return Reply::NotOwned;
    }
    match mentis_ops::run(
        &Personas,
        &*context.record,
        ReadClass::Foreground,
        &request(()),
    ) {
        Ok(mut read) => answer(read.rows.pop().expect("personas answers one row").0),
        Err(error) => failed(error),
    }
}

fn conversation_fields(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let Some(raw) = query.first("fields") else {
        return Reply::NotOwned;
    };
    let Some(rest) = ask.path.strip_prefix("/api/conversations/") else {
        return Reply::NotOwned;
    };
    if !plain_id(rest) {
        return Reply::NotOwned;
    }
    let fields: Vec<String> = raw
        .split(',')
        .map(python::strip)
        .filter(|x| !x.is_empty())
        .map(str::to_owned)
        .collect();
    if fields.is_empty() {
        return answer(dict([
            (
                "error",
                Py::str("name the fields: ?fields=name,about,participants,topics"),
            ),
            ("fields", Py::str(raw)),
        ]));
    }
    if let Some(unknown) = fields
        .iter()
        .find(|field| !matches!(field.as_str(), "name" | "about" | "participants" | "topics"))
    {
        let Some(shown) = python::repr(unknown) else {
            return Reply::NotOwned;
        };
        return answer(dict([
            (
                "error",
                Py::str(format!(
                    "no such field: {shown}; ask for any of name, about, participants, topics"
                )),
            ),
            ("fields", Py::str(raw)),
        ]));
    }
    let asked = request(ConversationFieldsArgs {
        conversation: rest.to_owned(),
        fields,
    });
    match mentis_ops::run(
        &ConversationFields,
        &*context.record,
        ReadClass::Foreground,
        &asked,
    ) {
        Ok(mut read) => answer(read.rows.pop().expect("fields answers one row").0),
        Err(OpError::NotFound { .. }) => answer(dict([
            ("error", Py::str(format!("not a conversation: '{rest}'"))),
            ("conversation", Py::str(rest)),
        ])),
        Err(error) => failed(error),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn running_out_of_time_forwards_and_nothing_else_does() {
        for gave_up in [
            OpError::Record(RecordError::ScopeExpired),
            OpError::Busy {
                why: "turns-view ran past its deadline".into(),
            },
        ] {
            assert_eq!(failed(gave_up), Reply::NotOwned);
        }
        assert!(matches!(
            failed(OpError::Record(RecordError::Sqlite {
                detail: "disk".into()
            })),
            Reply::Answer { status: 500, .. }
        ));
    }

    #[test]
    fn only_a_segment_python_reads_as_itself_is_read_here() {
        assert!(plain_id("ent-0123abc_d"));
        for odd in ["", "ent%2D1", "a b", "a;b", "caf\u{e9}", "a/b", "a.b"] {
            assert!(!plain_id(odd), "{odd:?}");
        }
    }
}
