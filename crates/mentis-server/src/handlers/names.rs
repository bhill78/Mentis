//! `GET /fluid/api/names?ids=` (`fluid/__init__.py:157`, `fluid/read.py:598`): what a notification
//! says of somewhere else.

use std::collections::HashMap;
use std::time::Instant;

use mentis_ops::names::{NameRow, Names, NamesArgs};
use mentis_ops::python;
use mentis_ops::{Id, ReadClass, ReadRequest};
use mentis_record::READ_SCOPE_LIMIT;

use super::query::{Query, bad_request, from_error};
use super::{Ask, Context, Door, Reply, Route};
use crate::front::answers::json_string;

pub const ROUTE: Route = Route {
    name: "names",
    door: Door::FluidGet,
    answer,
};

/// `_read.BATCH`.
const BATCH: usize = 64;

/// `_ids`: `Err` with the reply it comes to. An id holding `/` gets its 400 from Python, whose
/// words hold the id's `repr`.
fn ids_from(raw: Option<&str>) -> Result<Vec<String>, Reply> {
    let mut ids: Vec<String> = Vec::new();
    for id in raw.unwrap_or("").split(',') {
        let id = python::strip(id);
        if !id.is_empty() && !ids.iter().any(|seen| seen == id) {
            ids.push(id.to_owned());
        }
    }
    if ids.is_empty() {
        return Err(bad_request("name what to read: ?ids=<id>,<id>"));
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

fn answer(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let ids = match ids_from(query.first("ids")) {
        Ok(ids) => ids,
        Err(reply) => return reply,
    };
    let request = ReadRequest {
        args: NamesArgs {
            ids: ids.iter().cloned().map(Id).collect(),
        },
        cursor: None,
        limit: None,
        deadline: Instant::now() + READ_SCOPE_LIMIT,
    };
    match mentis_ops::run(&Names, &*context.record, ReadClass::Foreground, &request) {
        Err(error) => from_error(error),
        Ok(read) => Reply::Answer {
            status: 200,
            content_type: "application/json",
            body: shaped(&ids, &read.rows).into_bytes(),
        },
    }
}

/// `{i: got.get(i) for i in ids}`, in the order asked: held with no name shows its own id, and an
/// id the record doesn't hold is null.
fn shaped(ids: &[String], rows: &[NameRow]) -> String {
    let held: HashMap<&str, &NameRow> = rows.iter().map(|row| (row.id.as_str(), row)).collect();
    let shown: Vec<String> = ids
        .iter()
        .map(|id| {
            let value = match held.get(id.as_str()) {
                None => "null".to_owned(),
                Some(row) => json_string(row.name.as_deref().unwrap_or(id)),
            };
            format!("{}: {value}", json_string(id))
        })
        .collect();
    format!(
        "{{\"names\": {{{}}}, \"limit\": {BATCH}}}",
        shown.join(", ")
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
    fn ids_are_as_ids_reads_them() {
        assert_eq!(
            ids_from(Some(" a, b ,a,,b")),
            Ok(vec!["a".to_owned(), "b".to_owned()])
        );
        assert_eq!(
            says(ids_from(None)),
            r#"{"error": "name what to read: ?ids=<id>,<id>", "kind": "BadRequest"}"#
        );
        assert_eq!(says(ids_from(Some(" , "))), says(ids_from(None)));
        let too_many: Vec<String> = (0..65).map(|n| format!("i{n}")).collect();
        assert_eq!(
            says(ids_from(Some(&too_many.join(",")))),
            r#"{"error": "65 asked for in one read; at most 64 -- ask again for the rest", "kind": "BadRequest"}"#
        );
        let all: Vec<String> = (0..64).map(|n| format!("i{n}")).collect();
        assert_eq!(ids_from(Some(&all.join(","))), Ok(all));
        assert_eq!(ids_from(Some("a/b")), Err(Reply::NotOwned));
    }

    #[test]
    fn it_has_python_s_shape_in_the_order_asked() {
        let rows = [
            NameRow {
                id: "b".into(),
                name: Some("B".into()),
            },
            NameRow {
                id: "c".into(),
                name: None,
            },
        ];
        let ids = ["c".to_owned(), "a".to_owned(), "b".to_owned()];
        assert_eq!(
            shaped(&ids, &rows),
            r#"{"names": {"c": "c", "a": null, "b": "B"}, "limit": 64}"#
        );
    }
}
