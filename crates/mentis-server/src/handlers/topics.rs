//! `GET /fluid/api/topics` (`fluid/__init__.py:161`, `fluid/read.py:545`): the composer's `#`.

use std::time::Instant;

use mentis_ops::topics::{Topics, TopicsArgs, TopicsPage};
use mentis_ops::{ReadClass, ReadRequest};
use mentis_record::READ_SCOPE_LIMIT;

use super::query::{Query, from_error, limit};
use super::{Ask, Context, Door, Reply, Route};
use crate::front::answers::json_string;

pub const ROUTE: Route = Route {
    name: "topics",
    door: Door::FluidGet,
    answer,
};

/// `_read.LIST`, `_read.LIST_MAX`.
const LIST: u32 = 100;
const LIST_MAX: u32 = 500;

fn answer(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let limit = match limit(query.first("limit"), LIST, LIST_MAX) {
        Ok(limit) => limit,
        Err(reply) => return reply,
    };
    let request = ReadRequest {
        args: TopicsArgs {
            q: query.first("q").map(str::to_owned),
        },
        cursor: None,
        limit: Some(limit),
        deadline: Instant::now() + READ_SCOPE_LIMIT,
    };
    match mentis_ops::run(&Topics, &*context.record, ReadClass::Foreground, &request) {
        Err(error) => from_error(error),
        Ok(mut read) => {
            let page = read.rows.pop().expect("topics answers one page");
            Reply::Answer {
                status: 200,
                content_type: "application/json",
                body: shaped(&page, limit).into_bytes(),
            }
        }
    }
}

fn shaped(page: &TopicsPage, limit: u32) -> String {
    let rows: Vec<String> = page
        .topics
        .iter()
        .map(|topic| {
            format!(
                "{{\"ref\": {}, \"name\": {}, \"conversation\": {}, \"conversation_name\": {}}}",
                json_string(&topic.reference),
                json_string(&topic.name),
                json_string(&topic.conversation),
                topic
                    .conversation_name
                    .as_deref()
                    .map_or_else(|| "null".to_owned(), json_string),
            )
        })
        .collect();
    format!(
        "{{\"topics\": [{}], \"matched\": {}, \"limit\": {limit}}}",
        rows.join(", "),
        page.matched
    )
}

#[cfg(test)]
mod tests {
    use mentis_ops::topics::TopicRow;

    use super::*;

    #[test]
    fn it_has_python_s_shape() {
        let empty = TopicsPage {
            topics: Vec::new(),
            matched: 0,
        };
        assert_eq!(
            shaped(&empty, 100),
            r#"{"topics": [], "matched": 0, "limit": 100}"#
        );
        let page = TopicsPage {
            topics: vec![
                TopicRow {
                    reference: "ent-1".into(),
                    name: "Caf\u{e9}".into(),
                    conversation: "ent-2".into(),
                    conversation_name: Some("Home".into()),
                },
                TopicRow {
                    reference: "ent-3".into(),
                    name: "x".into(),
                    conversation: "ent-4".into(),
                    conversation_name: None,
                },
            ],
            matched: 5,
        };
        assert_eq!(
            shaped(&page, 2),
            "{\"topics\": [{\"ref\": \"ent-1\", \"name\": \"Caf\\u00e9\", \"conversation\": \"ent-2\", \"conversation_name\": \"Home\"}, {\"ref\": \"ent-3\", \"name\": \"x\", \"conversation\": \"ent-4\", \"conversation_name\": null}], \"matched\": 5, \"limit\": 2}"
        );
    }
}
