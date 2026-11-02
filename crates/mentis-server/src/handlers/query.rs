//! A route's query, as `urllib.parse.parse_qs(urlparse(path).query)` reads it, and what every owned
//! read says when it can't answer (`contracts/ops.md`, "What `OpError` becomes").
//!
//! **Only what can't be got wrong.** A fragment, a byte outside printable ASCII, or a percent escape
//! that isn't UTF-8 makes Python say: `Query::parse` is `None`, and the route answers nothing.

use mentis_ops::OpError;
use mentis_ops::python::{self, PythonInt};
use mentis_record::RecordError;

use super::Reply;
use crate::front::answers::{json_object, python_repr};

const JSON: &str = "application/json";

/// Names and values, in the order sent, blanks left out as `parse_qs` leaves them.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Query(Vec<(String, String)>);

impl Query {
    pub fn parse(raw: &str) -> Option<Query> {
        if !raw.bytes().all(|byte| matches!(byte, 0x21..=0x7e)) || raw.contains('#') {
            return None;
        }
        let mut fields = Vec::new();
        for field in raw.split('&') {
            // `name` alone, or `name=`, is left out by `keep_blank_values=False`.
            let Some((name, value)) = field.split_once('=') else {
                continue;
            };
            if value.is_empty() {
                continue;
            }
            fields.push((decoded(name)?, decoded(value)?));
        }
        Some(Query(fields))
    }

    /// Whether `parse_qs(raw, keep_blank_values=True)` would hold this name with a blank value: how
    /// `objects?posts=` asked empty is told from not asking. Called only of what [`Query::parse`] took.
    pub fn sent_blank(raw: &str, name: &str) -> bool {
        raw.split('&').any(|field| {
            let (sent, value) = field.split_once('=').unwrap_or((field, ""));
            !field.is_empty() && value.is_empty() && decoded(sent).as_deref() == Some(name)
        })
    }

    /// `query.get(name)[0]`: the first one sent.
    pub fn first(&self, name: &str) -> Option<&str> {
        self.0
            .iter()
            .find(|(field, _)| field == name)
            .map(|(_, value)| value.as_str())
    }
}

/// `unquote_plus` with `errors="replace"`, or `None` where something would have been replaced.
fn decoded(raw: &str) -> Option<String> {
    let bytes = raw.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut at = 0;
    while at < bytes.len() {
        let escape = (bytes[at] == b'%' && at + 2 < bytes.len())
            .then(|| Some(hex(bytes[at + 1])? * 16 + hex(bytes[at + 2])?))
            .flatten();
        match (bytes[at], escape) {
            (_, Some(value)) => {
                out.push(value);
                at += 3;
            }
            (b'+', None) => {
                out.push(b' ');
                at += 1;
            }
            (byte, None) => {
                out.push(byte);
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

/// `_limit` (`fluid/read.py:117`): the number, or the 400 it gets, or `Err(NotOwned)` if Python
/// has to read it.
pub fn limit(raw: Option<&str>, default: u32, most: u32) -> Result<u32, Reply> {
    let Some(raw) = raw else {
        return Ok(default);
    };
    match python::int(raw) {
        PythonInt::Unsure => Err(Reply::NotOwned),
        PythonInt::NotInt => Err(bad_request(&format!(
            "limit is a number, not {}",
            python_repr(raw)
        ))),
        PythonInt::Value(n) if n < 1 => Err(bad_request("limit is at least 1")),
        PythonInt::Value(n) => Ok(u32::try_from(n.min(i128::from(most))).unwrap_or(most)),
    }
}

/// `_read.BadRequest` at Fluid's door.
pub fn bad_request(why: &str) -> Reply {
    Reply::Answer {
        status: 400,
        content_type: JSON,
        body: json_object(&[("error", why), ("kind", "BadRequest")]).into_bytes(),
    }
}

/// What an op's failure becomes, by `contracts/ops.md`'s table. The route's bad requests are the
/// route's, and a read's own failure has no Python answer to match: Python reads differently.
pub fn from_error(error: OpError) -> Reply {
    let answer = |status, words: &str, kind| Reply::Answer {
        status,
        content_type: JSON,
        body: json_object(&[("error", words), ("kind", kind)]).into_bytes(),
    };
    match error {
        OpError::NotOwned { .. } => Reply::NotOwned,
        OpError::BadRequest { why } => bad_request(&why),
        OpError::Busy { why } => answer(503, &why, "Busy"),
        OpError::Record(RecordError::ScopeExpired) => {
            answer(503, &RecordError::ScopeExpired.to_string(), "ScopeExpired")
        }
        OpError::Record(other) => answer(500, &other.to_string(), "RecordError"),
        OpError::NotFound { what } => answer(404, &what, "NotFound"),
        other => answer(500, &other.to_string(), "RecordError"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parsed(raw: &str) -> Vec<(String, String)> {
        Query::parse(raw).unwrap().0
    }

    fn pair(name: &str, value: &str) -> (String, String) {
        (name.to_owned(), value.to_owned())
    }

    #[test]
    fn as_parse_qs_reads_it() {
        assert_eq!(parsed(""), []);
        assert_eq!(parsed("a"), []);
        assert_eq!(parsed("a=&b="), []);
        assert_eq!(parsed("a=1&&b=2"), [pair("a", "1"), pair("b", "2")]);
        assert_eq!(parsed("a=x=y"), [pair("a", "x=y")]);
        assert_eq!(parsed("a=b+c%20d"), [pair("a", "b c d")]);
        assert_eq!(parsed("%61=1"), [pair("a", "1")]);
        assert_eq!(parsed("a=%zz%4"), [pair("a", "%zz%4")]);
        assert_eq!(parsed("a=%c3%a9"), [pair("a", "\u{e9}")]);
        assert_eq!(Query::parse("a=1&a=2").unwrap().first("a"), Some("1"));
    }

    #[test]
    fn a_blank_is_told_from_not_asking() {
        for raw in ["posts=", "posts", "a=1&posts=", "%70osts="] {
            assert!(Query::sent_blank(raw, "posts"), "{raw}");
        }
        for raw in ["", "posts=1", "a=", "post="] {
            assert!(!Query::sent_blank(raw, "posts"), "{raw}");
        }
    }

    #[test]
    fn what_python_would_have_to_read_for_itself_is_python_s() {
        for raw in ["a=1#f", "a=%ff", "a=\u{e9}", "a=b c", "a=\t"] {
            assert_eq!(Query::parse(raw), None, "{raw:?}");
        }
    }

    fn limited(raw: Option<&str>) -> Result<u32, Reply> {
        limit(raw, 100, 500)
    }

    fn says(reply: Result<u32, Reply>) -> String {
        match reply {
            Err(Reply::Answer {
                status: 400, body, ..
            }) => String::from_utf8(body).unwrap(),
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn a_limit_is_as_limit_reads_it() {
        assert_eq!(limited(None), Ok(100));
        assert_eq!(limited(Some("7")), Ok(7));
        assert_eq!(limited(Some(" 7")), Ok(7));
        assert_eq!(limited(Some("9999")), Ok(500));
        assert_eq!(
            says(limited(Some("0"))),
            r#"{"error": "limit is at least 1", "kind": "BadRequest"}"#
        );
        assert_eq!(
            says(limited(Some("x'y"))),
            r#"{"error": "limit is a number, not \"x'y\"", "kind": "BadRequest"}"#
        );
        assert_eq!(limited(Some("\u{663}")), Err(Reply::NotOwned));
    }
}
