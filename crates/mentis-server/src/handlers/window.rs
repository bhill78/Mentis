//! The post window's routes (R2): `fluid/__init__.py`'s `route`, as far as `posts`,
//! `collections/conversation`, `collections/thread`, `objects` and `objects/<address>`. Each only maps a
//! request onto an op in `mentis_ops::window`, in the order Python asks its questions, so the first
//! thing wrong with a request is the thing it's told.

use std::time::Instant;

use mentis_ops::pyjson::Py;
use mentis_ops::python;
use mentis_ops::window::collections::{
    ConversationArgs, ConversationCollection, PyRow, ThreadArgs, ThreadCollection,
};
use mentis_ops::window::objects::{Objects, ObjectsArgs, ObjectsAsk};
use mentis_ops::window::posts::{Posts, PostsArgs};
use mentis_ops::window::reads::{BATCH, PAGE, PAGE_MAX, change_cursor};
use mentis_ops::window::{Finished, Prepared};
use mentis_ops::{OpError, ReadAnswer, ReadClass, ReadRequest};
use mentis_record::READ_SCOPE_LIMIT;

use super::query::{Query, bad_request, from_error, limit};
use super::{Ask, Context, Door, Reply, Route};

pub const POSTS: Route = Route {
    name: "posts",
    door: Door::FluidGet,
    answer: posts,
};
pub const CONVERSATION: Route = Route {
    name: "conversation-collection",
    door: Door::FluidGet,
    answer: conversation,
};
pub const THREAD: Route = Route {
    name: "thread-collection",
    door: Door::FluidGet,
    answer: thread,
};
pub const OBJECTS: Route = Route {
    name: "objects",
    door: Door::FluidGet,
    answer: objects,
};
pub const OBJECT: Route = Route {
    name: "object",
    door: Door::FluidGet,
    answer: object,
};

const JSON: &str = "application/json";

fn request<A>(args: A, limit: Option<u32>) -> ReadRequest<A> {
    ReadRequest {
        args,
        cursor: None,
        limit,
        deadline: Instant::now() + READ_SCOPE_LIMIT,
    }
}

fn sent(status: u16, value: &Py) -> Reply {
    Reply::Answer {
        status,
        content_type: JSON,
        body: value.dumps().into_bytes(),
    }
}

fn finished(done: Result<Finished, OpError>) -> Reply {
    match done {
        Ok(Finished::Answer(value)) => sent(200, &value),
        Ok(Finished::Unresolved(unresolved)) => sent(404, &unresolved.0),
        Err(error) => from_error(error),
    }
}

/// `_ids(raw, name)`. An id holding `/` gets its 400 from Python, whose words hold the id's `repr`.
fn ids_named(raw: Option<&str>, name: &str) -> Result<Vec<String>, Reply> {
    let mut ids: Vec<String> = Vec::new();
    for id in raw.unwrap_or("").split(',') {
        let id = python::strip(id);
        if !id.is_empty() && !ids.iter().any(|seen| seen == id) {
            ids.push(id.to_owned());
        }
    }
    if ids.is_empty() {
        return Err(bad_request(&format!(
            "name what to read: ?{name}=<id>,<id>"
        )));
    }
    if ids.len() > BATCH {
        return Err(bad_request(&format!(
            "{} asked for in one read; at most {BATCH} -- ask again for the rest",
            ids.len()
        )));
    }
    if ids.iter().any(|id| id.contains('/')) {
        return Err(Reply::NotOwned);
    }
    Ok(ids)
}

fn posts(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let ids = match ids_named(query.first("ids"), "ids") {
        Ok(ids) => ids,
        Err(reply) => return reply,
    };
    let window = &*context.window;
    let thread = if query.first("thread") == Some("1") {
        match window.bundle() {
            Ok(bundle) => Some(bundle),
            Err(error) => return from_error(error),
        }
    } else {
        None
    };
    let asked = request(PostsArgs { ids, thread }, None);
    let op = Posts { window };
    match mentis_ops::run(&op, &*context.record, ReadClass::Foreground, &asked) {
        Err(error) => from_error(error),
        Ok(mut read) => {
            let Prepared(plan) = read.rows.pop().expect("posts answers one plan");
            // The scope has gone, so nothing is pinned while the engines run.
            finished(plan.finish(window))
        }
    }
}

/// `{**out, "cursor": at}`.
fn with_cursor(mut read: ReadAnswer<PyRow>) -> Reply {
    let PyRow(mut value) = read.rows.pop().expect("a collection answers one page");
    value.set("cursor", change_cursor(read.as_of));
    sent(200, &value)
}

fn conversation(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let Some(id) = query.first("id") else {
        return bad_request("name the conversation: ?id=<id>");
    };
    let limit = match limit(query.first("limit"), PAGE, PAGE_MAX) {
        Ok(limit) => limit,
        Err(reply) => return reply,
    };
    let owned = |name: &str| query.first(name).map(str::to_owned);
    let args = ConversationArgs {
        id: id.to_owned(),
        before: owned("before"),
        after: owned("after"),
        start: owned("from"),
        shape: owned("shape"),
        topic: owned("topic"),
    };
    let asked = request(args, Some(limit));
    match mentis_ops::run(
        &ConversationCollection,
        &*context.record,
        ReadClass::Foreground,
        &asked,
    ) {
        Err(error) => from_error(error),
        Ok(read) => with_cursor(read),
    }
}

fn thread(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let Some(root) = query.first("root") else {
        return bad_request("name the post: ?root=<id>");
    };
    let limit = match limit(query.first("limit"), PAGE, PAGE_MAX) {
        Ok(limit) => limit,
        Err(reply) => return reply,
    };
    let owned = |name: &str| query.first(name).map(str::to_owned);
    let args = ThreadArgs {
        root: root.to_owned(),
        before: owned("before"),
        after: owned("after"),
        start: owned("from"),
    };
    let asked = request(args, Some(limit));
    match mentis_ops::run(
        &ThreadCollection,
        &*context.record,
        ReadClass::Foreground,
        &asked,
    ) {
        Err(error) => from_error(error),
        Ok(read) => with_cursor(read),
    }
}

fn run_objects(context: &Context, ask: ObjectsAsk) -> Reply {
    let window = &*context.window;
    let bundle = match window.bundle() {
        Ok(bundle) => bundle,
        Err(error) => return from_error(error),
    };
    let asked = request(ObjectsArgs { bundle, ask }, None);
    let op = Objects { window };
    match mentis_ops::run(&op, &*context.record, ReadClass::Foreground, &asked) {
        Err(error) => from_error(error),
        Ok(mut read) => {
            let Prepared(plan) = read.rows.pop().expect("objects answers one plan");
            finished(plan.finish(window))
        }
    }
}

/// `handle_get` and `route`: `objects?conversation=`, `posts=`, `thread=` or `post=`, first asked first.
fn objects(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    if let Some(id) = query.first("conversation") {
        let limit = match limit(query.first("limit"), PAGE, PAGE_MAX) {
            Ok(limit) => limit,
            Err(reply) => return reply,
        };
        return run_objects(
            context,
            ObjectsAsk::Conversation {
                id: id.to_owned(),
                before: query.first("before").map(str::to_owned),
                limit,
            },
        );
    }
    if query.first("posts").is_some() || Query::sent_blank(&ask.query, "posts") {
        let ids = match ids_named(query.first("posts"), "posts") {
            Ok(ids) => ids,
            Err(reply) => return reply,
        };
        return run_objects(context, ObjectsAsk::Posts { ids });
    }
    if query.first("thread").is_some() || Query::sent_blank(&ask.query, "thread") {
        let Some(root) = query.first("thread") else {
            return bad_request("name the post: ?thread=<root id>");
        };
        return run_objects(
            context,
            ObjectsAsk::Thread {
                root: root.to_owned(),
            },
        );
    }
    let Some(root) = query.first("post") else {
        return bad_request("name the post: ?post=<root id>");
    };
    run_objects(
        context,
        ObjectsAsk::Post {
            root: root.to_owned(),
            version: query.first("version").map(str::to_owned),
        },
    )
}

/// `urllib.parse.unquote`, or `None` where something would have been replaced, or where `urlparse` would
/// have read the path differently: `;` starts its params and `#` its fragment.
fn unquoted(raw: &str) -> Option<String> {
    let bytes = raw.as_bytes();
    if !bytes.iter().all(|byte| matches!(byte, 0x21..=0x7e)) || raw.contains(['#', ';']) {
        return None;
    }
    let mut out = Vec::with_capacity(bytes.len());
    let mut at = 0;
    while at < bytes.len() {
        let escape = (bytes[at] == b'%' && at + 2 < bytes.len())
            .then(|| Some(hex(bytes[at + 1])? * 16 + hex(bytes[at + 2])?))
            .flatten();
        match escape {
            Some(value) => {
                out.push(value);
                at += 3;
            }
            None => {
                out.push(bytes[at]);
                at += 1;
            }
        }
    }
    String::from_utf8(out).ok()
}

fn hex(byte: u8) -> Option<u8> {
    char::from(byte)
        .to_digit(16)
        .and_then(|digit| u8::try_from(digit).ok())
}

/// `GET /fluid/api/objects/<address>?format=`: one percent-encoded segment, which is all the table
/// gives this.
fn object(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let Some(segment) = ask.path.strip_prefix("/fluid/api/objects/") else {
        return Reply::NotOwned;
    };
    let Some(address) = unquoted(segment) else {
        return Reply::NotOwned;
    };
    run_objects(
        context,
        ObjectsAsk::One {
            address,
            format: query.first("format").unwrap_or("json").to_owned(),
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn says(reply: Result<Vec<String>, Reply>) -> String {
        match reply {
            Err(Reply::Answer {
                status: 400, body, ..
            }) => String::from_utf8(body).unwrap(),
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn ids_name_themselves_by_what_was_asked() {
        assert_eq!(
            says(ids_named(None, "posts")),
            r#"{"error": "name what to read: ?posts=<id>,<id>", "kind": "BadRequest"}"#
        );
        assert_eq!(
            ids_named(Some(" a, b ,a"), "ids"),
            Ok(vec!["a".to_owned(), "b".to_owned()])
        );
        assert_eq!(ids_named(Some("a/b"), "ids"), Err(Reply::NotOwned));
    }

    #[test]
    fn a_segment_is_unquoted_as_python_does_or_left_to_python() {
        assert_eq!(
            unquoted("live:ent-1:a%20b%2Fc"),
            Some("live:ent-1:a b/c".into())
        );
        assert_eq!(unquoted("a+b"), Some("a+b".into()));
        assert_eq!(unquoted("%zz%4"), Some("%zz%4".into()));
        assert_eq!(unquoted("caf%C3%A9"), Some("caf\u{e9}".into()));
        for odd in ["a%ff", "a;b", "a#b", "a b", "caf\u{e9}"] {
            assert_eq!(unquoted(odd), None, "{odd:?}");
        }
    }
}
