//! R5.1's routes: `/api/references`, `/fluid/api/search`, `/fluid/api/object-refs` and
//! `/fluid/api/document`, each only mapping a request onto `mentis_ops`, in the order Python asks its
//! questions.
//!
//! **`/api/references` forwards on any failed read,** as the agent door does, because the two share one
//! answer. The Fluid routes say what R2's say (`query::from_error`).

use mentis_ops::find::{FindAsk, find};
use mentis_ops::object_reads::{Document, RefsAsk, document, object_refs};
use mentis_ops::post_search::{self, SearchAsk};
use mentis_ops::pyjson::Py;
use mentis_ops::python::{self, PythonInt};
use mentis_ops::window::Unresolved;
use mentis_ops::window::reads::{PAGE, PAGE_MAX};
use mentis_record::ReadClass;
use serde_json::{Map, Value};

use super::query::{Query, bad_request, from_error, limit};
use super::{Ask, Context, Door, Reply, Route};
use crate::worker_reads::{self, Read};

pub const REFERENCES: Route = Route {
    name: "references",
    door: Door::Api,
    answer: references,
};
pub const SEARCH: Route = Route {
    name: "post-search",
    door: Door::FluidGet,
    answer: search,
};
pub const OBJECT_REFS: Route = Route {
    name: "object-refs",
    door: Door::FluidGet,
    answer: refs,
};
pub const DOCUMENT: Route = Route {
    name: "document",
    door: Door::Document,
    answer: words,
};

const JSON: &str = "application/json";
/// `int(one("limit", 12))`, `/api/references`.
const REFERENCES_LIMIT: usize = 12;

fn sent(status: u16, value: &Py) -> Reply {
    Reply::Answer {
        status,
        content_type: JSON,
        body: value.dumps().into_bytes(),
    }
}

/// `GET /api/references`: `resolve` for `ref=`, and `find` for anything else.
fn references(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    if let Some(reference) = query.first("ref") {
        let mut args = Map::new();
        args.insert("ref".to_owned(), Value::String(reference.to_owned()));
        return match worker_reads::read("resolve", &args, &*context.record, 0.0) {
            Read::Body(body) => Reply::Answer {
                status: 200,
                content_type: JSON,
                body,
            },
            Read::NotOwned => Reply::NotOwned,
        };
    }
    let most = match query.first("limit") {
        None => REFERENCES_LIMIT,
        Some(raw) => match python::int(raw) {
            PythonInt::Value(n) if n >= 1 => usize::try_from(n).unwrap_or(usize::MAX),
            // Python slices with what's left, or says its own `ValueError`.
            _ => return Reply::NotOwned,
        },
    };
    let asked = FindAsk {
        q: query.first("q").unwrap_or("").to_owned(),
        limit: most,
        here: query.first("conversation").map(str::to_owned),
    };
    match find(&*context.record, ReadClass::Foreground, &asked) {
        Ok(value) => sent(200, &value),
        Err(_) => Reply::NotOwned,
    }
}

/// `route`'s `rest == "search"`.
fn search(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let Some(conversation) = query.first("conversation") else {
        return bad_request("name the conversation: ?conversation=<id>");
    };
    let most = match limit(query.first("limit"), PAGE, PAGE_MAX) {
        Ok(most) => most,
        Err(reply) => return reply,
    };
    let asked = SearchAsk {
        conversation: conversation.to_owned(),
        q: query.first("q").map(str::to_owned),
        before: query.first("before").map(str::to_owned),
        limit: most,
    };
    match post_search::conversation(&*context.record, ReadClass::Foreground, &asked) {
        Ok((value, _)) => sent(200, &value),
        Err(error) => from_error(error),
    }
}

/// `route`'s `rest == "object-refs"`.
fn refs(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let asked = if let Some(post) = query.first("post") {
        RefsAsk::Post(post.to_owned())
    } else if let (Some(reference), Some(key)) = (query.first("ref"), query.first("key")) {
        RefsAsk::Part {
            reference: reference.to_owned(),
            key: key.to_owned(),
            exact: query.first("exact").map(str::to_owned),
        }
    } else {
        return bad_request(
            "name the post: ?post=<id>, or one reference: ?ref=<post>&key=<key>[&exact=<address>]",
        );
    };
    match object_refs(
        &context.window,
        &*context.record,
        ReadClass::Foreground,
        &asked,
    ) {
        Ok(value) => sent(200, &value),
        Err(error) => from_error(error),
    }
}

/// `route`'s `rest == "document"`, whose every answer carries the artifact routes' protections: the
/// door says so ([`Door::Document`]).
fn words(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let Some(reference) = query.first("ref") else {
        return bad_request("name the document: ?ref=<artifact ref>");
    };
    match document(
        &context.window,
        &*context.record,
        ReadClass::Foreground,
        reference,
    ) {
        Ok(Document::Words(value)) => sent(200, &value),
        Ok(Document::Unresolved(Unresolved(value))) => sent(404, &value),
        Err(error) => from_error(error),
    }
}
