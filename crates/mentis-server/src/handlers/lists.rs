//! R4.1 durable Fluid list adapters.

use mentis_ops::ReadClass;
use mentis_ops::lists::{ConversationMode, Conversations as ConversationsOp, ConversationsArgs};
use mentis_ops::lists::{
    Latest as LatestOp, LatestArgs, Participants as ParticipantsOp, ParticipantsArgs,
    Selection as SelectionOp, SelectionArgs, Stream as StreamOp, StreamArgs,
};
use mentis_ops::window::collections::PyRow;

use super::query::{Query, limit};
use super::r41::{reply, request, run};
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
    run(context, &StreamOp, args, Some(limit), true)
}

fn selection(context: &Context, ask: &Ask) -> Reply {
    let Some(q) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let ids = match ids_named(q.first("ids"), "ids") {
        Ok(v) => v,
        Err(r) => return r,
    };
    run(context, &SelectionOp, SelectionArgs { ids }, None, true)
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
    let op = ParticipantsOp { window: None };
    run(context, &op, args, Some(limit), false)
}

fn latest(context: &Context, ask: &Ask) -> Reply {
    let Some(q) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let limit = match limit(q.first("limit"), 10, 50) {
        Ok(v) => v,
        Err(r) => return r,
    };
    let args = LatestArgs {
        conversation: q.first("conversation").map(str::to_owned),
        agent_work: matches!(q.first("agent_work"), Some("1" | "true" | "yes")),
    };
    run(context, &LatestOp, args, Some(limit), true)
}

fn conversations(context: &Context, mode: ConversationMode, limit: Option<u32>) -> Reply {
    let Some(overlay) = context.snapshots.overlay() else {
        return Reply::NotOwned;
    };
    let activity = matches!(&mode, ConversationMode::Activity { .. });
    let args = ConversationsArgs { mode, overlay };
    if !activity {
        return run(context, &ConversationsOp, args, limit, false);
    }
    let read = mentis_ops::run(
        &ConversationsOp,
        &*context.record,
        ReadClass::Foreground,
        &request(args, limit),
    );
    reply(
        read.map(|mut read| {
            for PyRow(value) in &mut read.rows {
                value.set("key", mentis_ops::pyjson::Py::str("conversations"));
            }
            read
        }),
        true,
    )
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
    let op = ParticipantsOp {
        window: Some(&*context.window),
    };
    run(context, &op, args, lim, false)
}
