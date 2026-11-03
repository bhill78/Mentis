//! R4.1 durable Fluid list adapters.

use std::time::Instant;

use mentis_ops::lists::{ConversationMode, Conversations as ConversationsOp, ConversationsArgs};
use mentis_ops::lists::{
    Latest as LatestOp, LatestArgs, Participants as ParticipantsOp, ParticipantsArgs,
    Selection as SelectionOp, SelectionArgs, Stream as StreamOp, StreamArgs,
};
use mentis_ops::window::collections::PyRow;
use mentis_ops::window::reads::change_cursor;
use mentis_ops::{ReadClass, ReadRequest};
use mentis_record::READ_SCOPE_LIMIT;

use super::query::{Query, from_error, limit};
use super::window::ids_named;
use super::{Ask, Context, Door, Reply, Route};

pub const STREAM: Route = Route {
    name: "stream-collection",
    door: Door::FluidGet,
    answer: stream,
};
pub const SELECTION: Route = Route {
    name: "selection-collection",
    door: Door::FluidGet,
    answer: selection,
};
pub const PARTICIPANTS: Route = Route {
    name: "fluid-participants",
    door: Door::FluidGet,
    answer: participants,
};
pub const LATEST: Route = Route {
    name: "latest",
    door: Door::FluidGet,
    answer: latest,
};
pub const FLUID_CONVERSATIONS: Route = Route {
    name: "fluid-conversations",
    door: Door::FluidGet,
    answer: fluid_conversations,
};
pub const API_CONVERSATIONS: Route = Route {
    name: "api-conversations",
    door: Door::Api,
    answer: api_conversations,
};
pub const API_PARTICIPANTS: Route = Route {
    name: "api-participants",
    door: Door::Api,
    answer: api_participants,
};

fn request<A>(args: A, limit: Option<u32>) -> ReadRequest<A> {
    ReadRequest {
        args,
        cursor: None,
        limit,
        deadline: Instant::now() + READ_SCOPE_LIMIT,
    }
}

fn answer(mut read: mentis_ops::ReadAnswer<PyRow>, cursor: bool) -> Reply {
    let PyRow(mut value) = read.rows.pop().expect("one list answer");
    if cursor {
        value.set("cursor", change_cursor(read.as_of));
    }
    Reply::Answer {
        status: 200,
        content_type: "application/json",
        body: value.dumps().into_bytes(),
    }
}

fn stream(context: &Context, ask: &Ask) -> Reply {
    let Some(q) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let limit = match limit(q.first("limit"), 50, 200) {
        Ok(v) => v,
        Err(r) => return r,
    };
    let args = StreamArgs {
        before: q.first("before").map(str::to_owned),
        after: q.first("after").map(str::to_owned),
        start: q.first("from").map(str::to_owned),
    };
    match mentis_ops::run(
        &StreamOp,
        &*context.record,
        ReadClass::Foreground,
        &request(args, Some(limit)),
    ) {
        Ok(read) => answer(read, true),
        Err(error) => from_error(error),
    }
}

fn selection(context: &Context, ask: &Ask) -> Reply {
    let Some(q) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let ids = match ids_named(q.first("ids"), "ids") {
        Ok(v) => v,
        Err(r) => return r,
    };
    match mentis_ops::run(
        &SelectionOp,
        &*context.record,
        ReadClass::Foreground,
        &request(SelectionArgs { ids }, None),
    ) {
        Ok(read) => answer(read, true),
        Err(error) => from_error(error),
    }
}

fn participants(context: &Context, ask: &Ask) -> Reply {
    let Some(q) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let limit = match limit(q.first("limit"), 100, 500) {
        Ok(v) => v,
        Err(r) => return r,
    };
    let args = ParticipantsArgs {
        q: q.first("q").map(str::to_owned),
        runtimes: q.first("runtimes") == Some("1"),
        api: false,
    };
    match mentis_ops::run(
        &ParticipantsOp,
        &*context.record,
        ReadClass::Foreground,
        &request(args, Some(limit)),
    ) {
        Ok(read) => answer(read, false),
        Err(error) => from_error(error),
    }
}

fn latest(context: &Context, ask: &Ask) -> Reply {
    let Some(q) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let limit = match limit(q.first("limit"), 10, 50) {
        Ok(v) => v,
        Err(r) => return r,
    };
    let agent_work = matches!(q.first("agent_work"), Some("1" | "true" | "yes"));
    let args = LatestArgs {
        conversation: q
            .first("conversation")
            .filter(|v| !v.is_empty())
            .map(str::to_owned),
        agent_work,
    };
    match mentis_ops::run(
        &LatestOp,
        &*context.record,
        ReadClass::Foreground,
        &request(args, Some(limit)),
    ) {
        Ok(read) => answer(read, true),
        Err(error) => from_error(error),
    }
}

fn conversations(context: &Context, mode: ConversationMode, limit: Option<u32>) -> Reply {
    let Some(overlay) = context.snapshots.overlay() else {
        return Reply::NotOwned;
    };
    let activity = matches!(&mode, ConversationMode::Activity { .. });
    match mentis_ops::run(
        &ConversationsOp,
        &*context.record,
        ReadClass::Foreground,
        &request(ConversationsArgs { mode, overlay }, limit),
    ) {
        Ok(mut read) if activity => {
            let at = read.as_of;
            let PyRow(mut value) = read.rows.pop().expect("one conversation list");
            value.set("key", mentis_ops::pyjson::Py::str("conversations"));
            value.set("cursor", change_cursor(at));
            Reply::Answer {
                status: 200,
                content_type: "application/json",
                body: value.dumps().into_bytes(),
            }
        }
        Ok(read) => answer(read, false),
        Err(
            mentis_ops::OpError::Busy { .. }
            | mentis_ops::OpError::Record(mentis_record::RecordError::ScopeExpired),
        ) => Reply::NotOwned,
        Err(error) => from_error(error),
    }
}

fn api_conversations(context: &Context, _ask: &Ask) -> Reply {
    conversations(context, ConversationMode::Api, None)
}

fn fluid_conversations(context: &Context, ask: &Ask) -> Reply {
    let Some(q) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    if q.first("ids").is_some() {
        let ids = match ids_named(q.first("ids"), "ids") {
            Ok(v) => v,
            Err(r) => return r,
        };
        return conversations(context, ConversationMode::Ids(ids), None);
    }
    if q.first("activity").is_some() {
        let limit = match limit(q.first("limit"), 100, 500) {
            Ok(v) => v,
            Err(r) => return r,
        };
        return conversations(
            context,
            ConversationMode::Activity {
                after: q.first("cursor").map(str::to_owned),
                q: q.first("q").map(str::to_owned),
            },
            Some(limit),
        );
    }
    super::query::bad_request("ask for ?ids=<id>,<id> or ?activity=1")
}

fn api_participants(context: &Context, ask: &Ask) -> Reply {
    let Some(q) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let lim = match q.first("limit") {
        Some(v) => match v.parse::<u32>() {
            Ok(n) => Some(n),
            Err(_) => return Reply::NotOwned,
        },
        None => None,
    };
    let args = ParticipantsArgs {
        q: q.first("q").map(str::to_owned),
        runtimes: true,
        api: true,
    };
    match mentis_ops::run(
        &ParticipantsOp,
        &*context.record,
        ReadClass::Foreground,
        &request(args, lim),
    ) {
        Ok(read) => answer(read, false),
        Err(error) => from_error(error),
    }
}
