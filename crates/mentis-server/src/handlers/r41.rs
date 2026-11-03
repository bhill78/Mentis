//! R4.1's remaining durable Fluid reads.  Query parsing lives here; the record work is shared
//! through `mentis-ops` and every cursor is minted from that operation's own read position.

use std::time::Instant;

use mentis_ops::annotations::{Anchors, AnchorsArgs};
use mentis_ops::changes::{Changes, ChangesArgs};
use mentis_ops::needs_you::{NeedsYou, NeedsYouArgs, NeedsYouMode};
use mentis_ops::response_sets::{ResponseRead, ResponseSets};
use mentis_ops::window::collections::PyRow;
use mentis_ops::window::reads::change_cursor;
use mentis_ops::{ReadClass, ReadRequest};
use mentis_record::READ_SCOPE_LIMIT;

use super::query::{Query, bad_request, from_error, limit};
use super::window::ids_named;
use super::{Ask, Context, Door, Reply, Route};

pub const HOME_NEEDS_YOU: Route = Route {
    name: "home-needs-you",
    door: Door::FluidGet,
    answer: home_needs_you,
};
pub const NEEDS_YOU_ITEMS: Route = Route {
    name: "needs-you-items",
    door: Door::FluidGet,
    answer: needs_you_items,
};
pub const NEEDS_YOU: Route = Route {
    name: "needs-you",
    door: Door::FluidGet,
    answer: needs_you,
};
pub const POST_ANCHORS: Route = Route {
    name: "post-anchors",
    door: Door::FluidGet,
    answer: post_anchors,
};
pub const ANCHORS: Route = Route {
    name: "anchors",
    door: Door::FluidGet,
    answer: anchors,
};
pub const CHANGES: Route = Route {
    name: "changes",
    door: Door::FluidGet,
    answer: changes,
};
pub const RESPONSE_SETS: Route = Route {
    name: "response-sets",
    door: Door::FluidGet,
    answer: response_sets,
};
pub const RESPONSE_SET: Route = Route {
    name: "response-set",
    door: Door::FluidGet,
    answer: response_set,
};
pub const RESPONSE_HISTORY: Route = Route {
    name: "response-set-history",
    door: Door::FluidGet,
    answer: response_history,
};
pub const RESPONSE_ACCOUNTING: Route = Route {
    name: "response-set-accounting",
    door: Door::FluidGet,
    answer: response_accounting,
};

fn request<A>(args: A, limit: Option<u32>) -> ReadRequest<A> {
    ReadRequest {
        args,
        cursor: None,
        limit,
        deadline: Instant::now() + READ_SCOPE_LIMIT,
    }
}

fn run<A, O>(context: &Context, op: &O, args: A, limit: Option<u32>, cursor: bool) -> Reply
where
    O: mentis_ops::ReadOp<Args = A, Row = PyRow>,
{
    match mentis_ops::run(
        op,
        &*context.record,
        ReadClass::Foreground,
        &request(args, limit),
    ) {
        Ok(mut read) => {
            let PyRow(mut value) = read.rows.pop().expect("one R4.1 answer");
            if cursor {
                value.set("cursor", change_cursor(read.as_of));
            }
            Reply::Answer {
                status: 200,
                content_type: "application/json",
                body: value.dumps().into_bytes(),
            }
        }
        Err(
            mentis_ops::OpError::Busy { .. }
            | mentis_ops::OpError::Record(mentis_record::RecordError::ScopeExpired),
        ) => Reply::NotOwned,
        Err(error) => from_error(error),
    }
}

fn home_needs_you(context: &Context, ask: &Ask) -> Reply {
    let Some(q) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let lim = match limit(q.first("limit"), 30, 200) {
        Ok(v) => v,
        Err(r) => return r,
    };
    match mentis_ops::run(
        &NeedsYou,
        &*context.record,
        ReadClass::Foreground,
        &request(
            NeedsYouArgs {
                mode: NeedsYouMode::Page {
                    before: q.first("before").map(str::to_owned),
                },
            },
            Some(lim),
        ),
    ) {
        Ok(mut read) => {
            let PyRow(mut value) = read.rows.pop().expect("one needs-you page");
            value.set("cursor", change_cursor(read.as_of));
            Reply::Answer {
                status: 200,
                content_type: "application/json",
                body: value.dumps().into_bytes(),
            }
        }
        Err(
            mentis_ops::OpError::Busy { .. }
            | mentis_ops::OpError::Record(mentis_record::RecordError::ScopeExpired),
        ) => Reply::NotOwned,
        Err(error) => from_error(error),
    }
}

fn needs_you_items(context: &Context, ask: &Ask) -> Reply {
    if Query::parse(&ask.query).is_none() {
        return Reply::NotOwned;
    }
    run(
        context,
        &NeedsYou,
        NeedsYouArgs {
            mode: NeedsYouMode::Items,
        },
        None,
        true,
    )
}

fn needs_you(context: &Context, ask: &Ask) -> Reply {
    let Some(q) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    if q.first("ids").is_some() {
        let ids = match ids_named(q.first("ids"), "ids") {
            Ok(v) => v,
            Err(r) => return r,
        };
        return run(
            context,
            &NeedsYou,
            NeedsYouArgs {
                mode: NeedsYouMode::Asks { ids },
            },
            None,
            false,
        );
    }
    let Some(post) = q.first("post") else {
        return bad_request("name the post: ?post=<id>, or ?ids=");
    };
    run(
        context,
        &NeedsYou,
        NeedsYouArgs {
            mode: NeedsYouMode::On {
                post: post.to_owned(),
            },
        },
        None,
        true,
    )
}

fn post_segment<'a>(ask: &'a Ask, suffix: &str) -> Option<&'a str> {
    ask.path
        .strip_prefix("/fluid/api/posts/")?
        .strip_suffix(suffix)
}

fn post_anchors(context: &Context, ask: &Ask) -> Reply {
    let Some(post) = post_segment(ask, "/anchors") else {
        return Reply::NotOwned;
    };
    match mentis_ops::run(
        &Anchors,
        &*context.record,
        ReadClass::Foreground,
        &request(
            AnchorsArgs {
                posts: vec![post.to_owned()],
            },
            None,
        ),
    ) {
        Ok(mut read) => {
            let PyRow(value) = read.rows.pop().expect("one anchors read");
            if value
                .get("missing")
                .and_then(mentis_ops::pyjson::Py::as_list)
                .is_some_and(|v| !v.is_empty())
            {
                return Reply::NotOwned;
            }
            let anchors = value
                .get("posts")
                .and_then(|v| v.get(post))
                .cloned()
                .unwrap_or_else(|| mentis_ops::pyjson::Py::List(vec![]));
            let out = mentis_ops::pyjson::dict([
                ("post", mentis_ops::pyjson::Py::str(post)),
                ("anchors", anchors),
                ("cursor", change_cursor(read.as_of)),
            ]);
            Reply::Answer {
                status: 200,
                content_type: "application/json",
                body: out.dumps().into_bytes(),
            }
        }
        Err(
            mentis_ops::OpError::Busy { .. }
            | mentis_ops::OpError::Record(mentis_record::RecordError::ScopeExpired),
        ) => Reply::NotOwned,
        Err(error) => from_error(error),
    }
}

fn anchors(context: &Context, ask: &Ask) -> Reply {
    let Some(q) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let posts = match ids_named(q.first("posts"), "posts") {
        Ok(v) => v,
        Err(r) => return r,
    };
    run(context, &Anchors, AnchorsArgs { posts }, None, true)
}

fn changes(context: &Context, ask: &Ask) -> Reply {
    let Some(q) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    run(
        context,
        &Changes,
        ChangesArgs {
            since: q.first("since").map(str::to_owned),
            threads: q.first("threads") == Some("1"),
        },
        None,
        false,
    )
}

fn sid<'a>(ask: &'a Ask, tail: &str) -> Option<&'a str> {
    ask.path
        .strip_prefix("/fluid/api/response-sets/")?
        .strip_suffix(tail)
}

/// A post's sets embed each set's state, which takes the form's own check: Python's, as a set's state
/// is, until the render engine's write-side callers move (`mentis_ops::response_sets`).
fn response_sets(_context: &Context, _ask: &Ask) -> Reply {
    Reply::NotOwned
}

fn response_set(_context: &Context, _ask: &Ask) -> Reply {
    Reply::NotOwned
}

fn response_history(context: &Context, ask: &Ask) -> Reply {
    let Some(set) = sid(ask, "/history") else {
        return Reply::NotOwned;
    };
    let Some(q) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let mode = if q.first("words") == Some("1") {
        ResponseRead::WordsHistory {
            set: set.to_owned(),
            by: q.first("by").map(str::to_owned),
        }
    } else if let Some(field) = q.first("field") {
        ResponseRead::FieldHistory {
            set: set.to_owned(),
            field: field.to_owned(),
        }
    } else {
        return bad_request("name the field: ?field=<id>, or ?words=1 for the own words");
    };
    run(context, &ResponseSets, mode, None, true)
}

fn response_accounting(context: &Context, ask: &Ask) -> Reply {
    let Some(set) = sid(ask, "/accounting") else {
        return Reply::NotOwned;
    };
    run(
        context,
        &ResponseSets,
        ResponseRead::Accounting {
            set: set.to_owned(),
        },
        None,
        true,
    )
}
