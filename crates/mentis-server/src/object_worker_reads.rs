//! R5.1's reads at the agent door: `find` and `check_rendering`, as `_result` answers them. **Equal bytes
//! or forward,** as `worker_reads`' are. They are apart from those because they need the window's
//! engines, and because each is only an argument check over `mentis_ops`.
//!
//! **Every failed read forwards,** `Busy` and `Record` included, and so does whatever Python coerces.

use mentis_ops::find::{FindAsk, find};
use mentis_ops::pyjson::Py;
use mentis_ops::render_report::check_rendering;
use mentis_ops::window::Window;
use mentis_ops::{OpError, ReadClass};
use mentis_record::RecordReader;
use serde_json::{Map, Value};

use crate::worker_reads::Read;

/// What this door may answer beside `worker_reads::MOVED`.
pub const MOVED: [&str; 2] = ["find", "check_rendering"];

/// `worker.PAGE`: `int(args.get("limit") or PAGE)`.
const PAGE: usize = 40;

fn forward(what: &str) -> OpError {
    OpError::NotOwned { why: what.into() }
}

fn find_args(args: &Map<String, Value>) -> Result<FindAsk, OpError> {
    let q = match args.get("q") {
        None | Some(Value::Null) => String::new(),
        Some(Value::String(q)) => q.clone(),
        Some(_) => return Err(forward("a question that isn't text")),
    };
    let limit = match args.get("limit") {
        None | Some(Value::Null) => PAGE,
        Some(Value::Number(n)) => match n.as_u64() {
            Some(0) => PAGE,
            Some(n) => usize::try_from(n).map_err(|_| forward("a limit past a page"))?,
            None => return Err(forward("a limit `int` would have to read")),
        },
        Some(_) => return Err(forward("a limit `int` would have to read")),
    };
    Ok(FindAsk {
        q,
        limit,
        here: None,
    })
}

fn answered(
    op: &str,
    args: &Map<String, Value>,
    record: &dyn RecordReader,
    window: &Window,
) -> Result<Py, OpError> {
    match op {
        "find" => find(record, ReadClass::Agent, &find_args(args)?),
        "check_rendering" => check_rendering(args, window, record, ReadClass::Agent),
        _ => Err(forward("not one of these")),
    }
}

/// One of [`MOVED`], as the agent door asks it. Blocking.
pub fn read(
    op: &str,
    args: &Map<String, Value>,
    record: &dyn RecordReader,
    window: &Window,
) -> Read {
    match answered(op, args, record, window) {
        Ok(value) => Read::Body(value.dumps().into_bytes()),
        Err(_) => Read::NotOwned,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn map(value: Value) -> Map<String, Value> {
        value.as_object().unwrap().clone()
    }

    #[test]
    fn find_s_arguments_are_what_python_doesn_t_have_to_coerce() {
        let got = find_args(&map(serde_json::json!({"q": "word", "limit": 3}))).unwrap();
        assert_eq!((got.q.as_str(), got.limit), ("word", 3));
        let got = find_args(&map(serde_json::json!({"limit": 0}))).unwrap();
        assert_eq!((got.q.as_str(), got.limit), ("", PAGE));
        for odd in [
            serde_json::json!({"q": 1}),
            serde_json::json!({"limit": "3"}),
            serde_json::json!({"limit": 1.5}),
            serde_json::json!({"limit": -1}),
            serde_json::json!({"limit": true}),
        ] {
            assert!(find_args(&map(odd.clone())).is_err(), "{odd}");
        }
    }
}
