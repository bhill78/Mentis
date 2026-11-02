//! `GET /api/pulse` (`web/__init__.py:2564-2600`). The durable half is read here and is never held
//! up by Python; the live half is whatever the snapshot client holds when the pulse asks.
//!
//! The one listed difference from Python's answer is `live`, on an answer that isn't fresh
//! (`contracts/live-snapshot.md`).

use std::time::Instant;

use mentis_ops::moved::Moved;
use mentis_ops::pulse::{Pulse, PulseArgs};
use mentis_ops::{ReadClass, ReadRequest};
use mentis_record::READ_SCOPE_LIMIT;

use super::query::{Query, from_error};
use super::{Ask, Context, Door, Reply, Route};
use crate::front::answers::json_string;
use crate::front::snapshot::Seen;
use crate::live::{Liveness, pulse_token};

pub const ROUTE: Route = Route {
    name: "pulse",
    door: Door::Api,
    answer,
};

fn answer(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let request = ReadRequest {
        args: PulseArgs {
            since: query.first("since").map(str::to_owned),
        },
        cursor: None,
        limit: None,
        deadline: Instant::now() + READ_SCOPE_LIMIT,
    };
    // Asked before the read, so a pulse that turned polling on is told what was held then.
    let seen = context.snapshots.asked();
    match mentis_ops::run(&Pulse, &*context.record, ReadClass::Foreground, &request) {
        Err(error) => from_error(error),
        Ok(mut read) => {
            let row = read.rows.pop().expect("a pulse answers one row");
            Reply::Answer {
                status: 200,
                content_type: "application/json",
                body: shaped(&row.durable.to_string(), row.moved.as_ref(), &seen).into_bytes(),
            }
        }
    }
}

fn shaped(durable: &str, moved: Option<&Option<Moved>>, seen: &Seen) -> String {
    let token = pulse_token(durable, seen.state, seen.hash.as_deref());
    let mut out = format!("{{\"token\": {}", json_string(&token));
    if let Some(moved) = moved {
        out.push_str(", \"moved\": ");
        match moved {
            None => out.push_str("null"),
            Some(moved) => out.push_str(&moved_json(moved)),
        }
    }
    if let Some(mark) = seen.mark() {
        out.push_str(", \"live\": {\"state\": ");
        out.push_str(match mark.state {
            Liveness::Fresh => "\"fresh\"",
            Liveness::Stale => "\"stale\"",
            Liveness::Unavailable => "\"unavailable\"",
        });
        out.push_str(", \"age_ms\": ");
        match mark.age_ms {
            Some(age) => out.push_str(&age.to_string()),
            None => out.push_str("null"),
        }
        out.push('}');
    }
    out.push('}');
    out
}

fn moved_json(moved: &Moved) -> String {
    let list = |items: &[String]| {
        let shown: Vec<String> = items.iter().map(|item| json_string(item)).collect();
        format!("[{}]", shown.join(", "))
    };
    format!(
        "{{\"conversations\": {}, \"executions\": {}, \"governed\": {}, \"people\": {}, \"loose\": {}}}",
        list(&moved.conversations),
        list(&moved.executions),
        moved.governed,
        moved.people,
        moved.loose
    )
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use super::*;

    fn fresh() -> Seen {
        Seen {
            state: Liveness::Fresh,
            hash: Some("abc".into()),
            age: Some(Duration::from_millis(100)),
        }
    }

    #[test]
    fn a_fresh_pulse_has_python_s_shape() {
        assert_eq!(shaped("1.2.3", None, &fresh()), r#"{"token": "1.2.3/abc"}"#);
        assert_eq!(
            shaped("1.2.3", Some(&None), &fresh()),
            r#"{"token": "1.2.3/abc", "moved": null}"#
        );
        let moved = Moved {
            conversations: vec!["ent-a".into(), "ent-b".into()],
            executions: vec!["run".into()],
            governed: true,
            people: false,
            loose: false,
        };
        assert_eq!(
            shaped("1.2.3", Some(&Some(moved)), &fresh()),
            r#"{"token": "1.2.3/abc", "moved": {"conversations": ["ent-a", "ent-b"], "executions": ["run"], "governed": true, "people": false, "loose": false}}"#
        );
    }

    #[test]
    fn what_isn_t_fresh_says_so_beside_the_token() {
        let stale = Seen {
            state: Liveness::Stale,
            hash: Some("abc".into()),
            age: Some(Duration::from_millis(2500)),
        };
        assert_eq!(
            shaped("1.2.3", None, &stale),
            r#"{"token": "1.2.3/abc", "live": {"state": "stale", "age_ms": 2500}}"#
        );
        let held_but_gone = Seen {
            state: Liveness::Unavailable,
            hash: Some("abc".into()),
            age: Some(Duration::from_millis(12000)),
        };
        assert_eq!(
            shaped("1.2.3", None, &held_but_gone),
            r#"{"token": "1.2.3/unavailable", "live": {"state": "unavailable", "age_ms": 12000}}"#
        );
        let nothing_held = Seen {
            state: Liveness::Unavailable,
            hash: None,
            age: None,
        };
        assert_eq!(
            shaped("1.2.3", None, &nothing_held),
            r#"{"token": "1.2.3/unavailable", "live": {"state": "unavailable", "age_ms": null}}"#
        );
    }
}
