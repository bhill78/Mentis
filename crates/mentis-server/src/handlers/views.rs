//! R4.2's owner-side durable views.

use std::time::Instant;

use mentis_ops::views::{
    ConversationFields, ConversationFieldsArgs, DecisionsView, DecisionsViewArgs, IntakeView,
    IntakeViewArgs, Personas, ThreadView, ThreadViewArgs, TurnView, TurnViewArgs, TurnsView,
    TurnsViewArgs,
};
use mentis_ops::{ReadClass, ReadRequest};
use mentis_record::READ_SCOPE_LIMIT;

use super::query::{Query, from_error};
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

fn turn_view(context: &Context, ask: &Ask) -> Reply {
    if Query::parse(&ask.query).is_none() {
        return Reply::NotOwned;
    }
    let Some(id) = ask.path.strip_prefix("/api/turns/") else {
        return Reply::NotOwned;
    };
    if id.is_empty() || id.contains('/') {
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
        Err(mentis_ops::OpError::NotFound { .. }) => Reply::NotOwned,
        Err(error) => from_error(error),
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
        Err(error) => from_error(error),
    }
}

fn ids(raw: Option<&str>) -> Result<Vec<String>, Reply> {
    let mut ids = Vec::new();
    for id in raw
        .unwrap_or("")
        .split(',')
        .map(str::trim)
        .filter(|x| !x.is_empty())
    {
        if !ids.iter().any(|x| x == id) {
            ids.push(id.to_owned())
        }
    }
    if ids.is_empty() {
        return Err(super::query::bad_request(
            "name the Turns to read: /api/turns?ids=<id>,<id>",
        ));
    }
    if ids.len() > 64 {
        return Err(super::query::bad_request(&format!(
            "{} Turns asked for in one read; at most 64 -- ask again for the rest",
            ids.len()
        )));
    }
    if let Some(id) = ids.iter().find(|id| id.contains('/')) {
        return Err(super::query::bad_request(&format!("not a Turn id: {id:?}")));
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
    let ids = match ids(query.first("ids")) {
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
        Err(error) => from_error(error),
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
    if conversation.is_empty() || root.is_empty() || root.contains('/') {
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
        Err(mentis_ops::OpError::BadRequest { why }) => answer(mentis_ops::pyjson::dict([
            ("error", mentis_ops::pyjson::Py::str(why)),
            ("thread", mentis_ops::pyjson::Py::str(root)),
        ])),
        Err(error) => from_error(error),
    }
}

fn decisions(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let Some(overlay) = context.snapshots.overlay() else {
        return Reply::NotOwned;
    };
    let (post, ids) = if let Some(raw) = query.first("ids") {
        let mut got = Vec::new();
        for id in raw.split(',').map(str::trim).filter(|x| !x.is_empty()) {
            if !got.iter().any(|x| x == id) {
                got.push(id.to_owned())
            }
        }
        (None, got)
    } else if let Some(post) = query.first("post") {
        (Some(post.to_owned()), Vec::new())
    } else {
        return super::query::bad_request("name the post: ?post=<id>, or ?ids=");
    };
    let asked = request(DecisionsViewArgs {
        post,
        ids,
        overlay,
        owner: None,
    });
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
        Err(error) => from_error(error),
    }
}

fn answer(row: mentis_ops::pyjson::Py) -> Reply {
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
        Err(error) => from_error(error),
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
    if rest.is_empty() || rest.contains('/') {
        return Reply::NotOwned;
    }
    let fields: Vec<String> = raw
        .split(',')
        .map(str::trim)
        .filter(|x| !x.is_empty())
        .map(str::to_owned)
        .collect();
    if fields.is_empty() {
        return answer(mentis_ops::pyjson::dict([
            (
                "error",
                mentis_ops::pyjson::Py::str(
                    "name the fields: ?fields=name,about,participants,topics",
                ),
            ),
            ("fields", mentis_ops::pyjson::Py::str(raw)),
        ]));
    }
    if let Some(unknown) = fields
        .iter()
        .find(|field| !matches!(field.as_str(), "name" | "about" | "participants" | "topics"))
    {
        return answer(mentis_ops::pyjson::dict([
            (
                "error",
                mentis_ops::pyjson::Py::str(format!(
                    "no such field: {unknown:?}; ask for any of name, about, participants, topics"
                )),
            ),
            ("fields", mentis_ops::pyjson::Py::str(raw)),
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
        Err(mentis_ops::OpError::NotFound { .. }) => answer(mentis_ops::pyjson::dict([
            (
                "error",
                mentis_ops::pyjson::Py::str(format!("not a conversation: {rest:?}")),
            ),
            ("conversation", mentis_ops::pyjson::Py::str(rest)),
        ])),
        Err(error) => from_error(error),
    }
}
