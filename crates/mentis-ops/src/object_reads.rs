//! What a post's object references name now, and a document's words: `conversation/objectref.py`'s
//! `resolve` and `resolve_post`, and `fluid/objects.py`'s `document_text`. Python's stay for their write
//! side and for `for_request` until R7 (`docs/rust/routes.md`).
//!
//! **Each object read is the window's own** ([`Objects`]): one op to an address, each with its own scope,
//! and no scope held while an engine runs or a file is read. So nothing here parses Markdown, and no
//! second answer can be given to what an object is.

use std::time::Instant;

use mentis_record::{Id, Position, READ_SCOPE_LIMIT, ReadClass, ReadScope, RecordReader};
use sha2::{Digest, Sha256};

use crate::pyjson::{self, Py, dict, repr};
use crate::window::objects::{self, Objects, ObjectsArgs, ObjectsAsk};
use crate::window::reads::{BATCH, change_cursor, heads};
use crate::window::{Finished, Prepared, Unresolved, Window, bad_request, python_says, unresolved};
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest};

/// `fluid/objects.py`'s `DOC_MAX`: the client's limit, in bytes.
pub const DOC_MAX: usize = 256 * 1024;

/// `objectref.PART`.
const PART: &str = "object";

fn asked<A>(args: A) -> ReadRequest<A> {
    ReadRequest {
        args,
        cursor: None,
        limit: None,
        deadline: Instant::now() + READ_SCOPE_LIMIT,
    }
}

// -- object references ----------------------------------------------------------------------------

/// What `/fluid/api/object-refs` asks.
#[derive(Clone, Debug)]
pub enum RefsAsk {
    Post(String),
    Part {
        reference: String,
        key: String,
        exact: Option<String>,
    },
}

struct PostParts {
    deleted: bool,
    parts: Vec<(usize, Py)>,
    at: Position,
}

struct ReadPostParts;

impl ReadOp for ReadPostParts {
    type Args = String;
    type Row = Prepared<PostParts>;

    const NAME: &'static str = "object-ref-parts";
    /// The head, and how the post now reads.
    const BUDGET: Budget = Budget {
        statements: 1 + mentis_rules::CHANGED_STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<String>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let post = request.args.as_str();
        let at = scope.position();
        let is_post = heads(scope, &[post])?
            .get(post)
            .is_some_and(|head| head.is_post());
        if !is_post {
            let shown = repr(post).ok_or_else(|| python_says("an id to show in other words"))?;
            return Err(bad_request(format!("not a post: {shown}")));
        }
        let id = Id(post.to_owned());
        let reading =
            mentis_rules::now_reads_walking_only_what_changed(scope, std::slice::from_ref(&id))?
                .remove(&id)
                .ok_or_else(|| python_says("a post that went between two reads"))?;
        if reading.python_says {
            return Err(python_says("a post Python has to read"));
        }
        let body = pyjson::loads(&reading.body_json)
            .ok_or_else(|| python_says("a body this can't read"))?;
        Ok(ReadAnswer {
            rows: vec![Prepared(PostParts {
                deleted: reading.deleted.is_some(),
                parts: object_parts(&body)?,
                at,
            })],
            as_of: at,
            more: None,
            not_searched: Vec::new(),
        })
    }
}

/// `(now.get("body") or {}).get("parts") or []`, its object parts with where each is.
fn object_parts(body: &Py) -> Result<Vec<(usize, Py)>, OpError> {
    if !body.truthy() {
        return Ok(Vec::new());
    }
    if !body.is_dict() {
        return Err(python_says("a body that isn't an object"));
    }
    let parts = match body.get("parts") {
        None => return Ok(Vec::new()),
        Some(found) if !found.truthy() => return Ok(Vec::new()),
        Some(Py::List(parts)) => parts,
        Some(_) => return Err(python_says("parts that aren't a list")),
    };
    Ok(parts
        .iter()
        .enumerate()
        .filter(|(_, part)| part.is_dict() && part.get("type").and_then(Py::as_str) == Some(PART))
        .map(|(at, part)| (at, part.clone()))
        .collect())
}

/// `f"{value}"` of a reference's field, for what's plainly the same here. A value that's true and not
/// text forwards: it would have to read as an address.
fn shown_field(value: Option<&Py>) -> Result<String, OpError> {
    match value {
        None | Some(Py::None) => Ok("None".to_owned()),
        Some(Py::Str(words)) => Ok(words.clone()),
        Some(_) => Err(python_says("a reference field that isn't text")),
    }
}

/// How one address went.
enum Reached {
    Read(Py),
    Unresolved(Py),
    Bad(String),
}

/// `one_object(corpus, address)`.
fn one_object(
    window: &Window,
    record: &dyn RecordReader,
    class: ReadClass,
    bundle: &mentis_extract::Bundle,
    address: &str,
) -> Result<Reached, OpError> {
    let op = Objects { window };
    let request = asked(ObjectsArgs {
        bundle: bundle.clone(),
        ask: ObjectsAsk::One {
            address: address.to_owned(),
            format: "json".to_owned(),
        },
    });
    let mut read = match crate::run(&op, record, class, &request) {
        Ok(read) => read,
        Err(OpError::BadRequest { why }) => return Ok(Reached::Bad(why)),
        Err(other) => return Err(other),
    };
    let Prepared(plan) = read
        .rows
        .pop()
        .ok_or_else(|| python_says("objects answered nothing"))?;
    match plan.finish(window) {
        Ok(Finished::Answer(value)) => Ok(Reached::Read(value)),
        Ok(Finished::Unresolved(Unresolved(value))) => Ok(Reached::Unresolved(value)),
        Err(OpError::BadRequest { why }) => Ok(Reached::Bad(why)),
        Err(other) => Err(other),
    }
}

fn field(value: &Py, name: &str) -> Py {
    value.get(name).cloned().unwrap_or(Py::None)
}

/// `objectref.resolve`: what one part names now. Never a substitute.
fn resolve_part(
    window: &Window,
    record: &dyn RecordReader,
    class: ReadClass,
    bundle: &mut Option<mentis_extract::Bundle>,
    part: &Py,
) -> Result<Py, OpError> {
    let live = format!(
        "live:{}:{}",
        shown_field(part.get("ref"))?,
        shown_field(part.get("key"))?
    );
    let mut out = dict([
        ("ref", field(part, "ref")),
        ("key", field(part, "key")),
        ("exact", field(part, "exact")),
        ("live", Py::str(live.as_str())),
        ("text", field(part, "text")),
        ("about", field(part, "about")),
    ]);
    let names_it = |name: &str| part.get(name).is_some_and(Py::truthy);
    if !names_it("ref") || !names_it("key") {
        out.set("resolves", Py::Bool(false));
        out.set("why", Py::str("the reference names no post and key"));
        return Ok(out);
    }
    if bundle.is_none() {
        *bundle = Some(window.bundle()?);
    }
    let bundle = bundle
        .as_ref()
        .ok_or_else(|| python_says("no bundle to read with"))?;
    match one_object(window, record, class, bundle, &live)? {
        Reached::Unresolved(payload) => {
            out.set("resolves", Py::Bool(false));
            out.set("why", field(&payload, "why"));
            if payload.get("deleted").is_some_and(Py::truthy) {
                out.set("deleted", Py::Bool(true));
            }
        }
        Reached::Bad(why) => {
            out.set("resolves", Py::Bool(false));
            out.set("why", Py::Str(why));
        }
        Reached::Read(got) => {
            if got.get("extracted").is_some_and(Py::truthy) {
                out.set("resolves", Py::Bool(true));
                out.set("object", field(&got, "object"));
                for name in ["version", "current_version", "home", "home_name", "number"] {
                    out.set(name, field(&got, name));
                }
            } else {
                out.set("resolves", Py::None);
                out.set("why_not", field(&got, "why_not"));
            }
        }
    }
    if let Some(exact) = part.get("exact").and_then(Py::as_str)
        && !exact.is_empty()
    {
        match one_object(window, record, class, bundle, exact)? {
            Reached::Read(pinned) => out.set(
                "exact_resolves",
                if pinned.get("extracted").is_some_and(Py::truthy) {
                    Py::Bool(true)
                } else {
                    Py::None
                },
            ),
            Reached::Unresolved(payload) => {
                out.set("exact_resolves", Py::Bool(false));
                out.set("exact_why", field(&payload, "why"));
            }
            Reached::Bad(why) => {
                out.set("exact_resolves", Py::Bool(false));
                out.set("exact_why", Py::Str(why));
            }
        }
    }
    Ok(out)
}

struct ReadPosition;

impl ReadOp for ReadPosition {
    type Args = ();
    type Row = Prepared<Position>;

    const NAME: &'static str = "position";
    const BUDGET: Budget = Budget { statements: 1 };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        _request: &ReadRequest<()>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let at = scope.position();
        Ok(ReadAnswer {
            rows: vec![Prepared(at)],
            as_of: at,
            more: None,
            not_searched: Vec::new(),
        })
    }
}

/// `GET /fluid/api/object-refs`: `{**answer, "cursor": at}`, the cursor from before anything was read. A
/// post naming more references than a batch forwards: this holds no one read's limit over Python's.
pub fn object_refs(
    window: &Window,
    record: &dyn RecordReader,
    class: ReadClass,
    ask: &RefsAsk,
) -> Result<Py, OpError> {
    let mut bundle = None;
    match ask {
        RefsAsk::Post(post) => {
            let mut read = crate::run(&ReadPostParts, record, class, &asked(post.clone()))?;
            let Prepared(found) = read
                .rows
                .pop()
                .ok_or_else(|| python_says("no post's parts"))?;
            if found.parts.len() > BATCH {
                return Err(python_says("more references than one read takes"));
            }
            let mut references = Vec::with_capacity(found.parts.len());
            for (at, part) in &found.parts {
                let resolved = resolve_part(window, record, class, &mut bundle, part)?;
                let mut row = dict([("part", Py::int(*at))]);
                if let Py::Dict(fields) = resolved {
                    for (name, value) in fields {
                        row.set(&name, value);
                    }
                }
                references.push(row);
            }
            Ok(dict([
                ("post", Py::str(post.as_str())),
                ("deleted", Py::Bool(found.deleted)),
                ("references", Py::List(references)),
                ("cursor", change_cursor(found.at)),
            ]))
        }
        RefsAsk::Part {
            reference,
            key,
            exact,
        } => {
            let mut read = crate::run(&ReadPosition, record, class, &asked(()))?;
            let Prepared(at) = read.rows.pop().ok_or_else(|| python_says("no position"))?;
            let part = dict([
                ("type", Py::str(PART)),
                ("ref", Py::str(reference.as_str())),
                ("key", Py::str(key.as_str())),
                ("exact", Py::opt_str(exact.as_deref())),
            ]);
            let mut out = resolve_part(window, record, class, &mut bundle, &part)?;
            out.set("cursor", change_cursor(at));
            Ok(out)
        }
    }
}

// -- a document's words ---------------------------------------------------------------------------

struct Describe<'w> {
    window: &'w Window,
}

impl ReadOp for Describe<'_> {
    type Args = String;
    type Row = Prepared<Py>;

    const NAME: &'static str = "document-describe";
    /// The admission, and which purges name it.
    const BUDGET: Budget = Budget {
        statements: objects::DESCRIBE_STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<String>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let about = objects::described_without_hashing(self.window, scope, &request.args)?;
        Ok(ReadAnswer {
            rows: vec![Prepared(about)],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

/// `head[:len(head) - k].decode("utf-8")` for k up to 3: a character the cut split is left out. Failing
/// that it's decoded with replacement, as a whole file under the limit is.
fn words_of(data: &[u8], limit: usize) -> String {
    let head = &data[..data.len().min(limit)];
    if data.len() > limit {
        for less in 0..4 {
            if let Some(kept) = head.len().checked_sub(less)
                && let Ok(text) = std::str::from_utf8(&head[..kept])
            {
                return text.to_owned();
            }
        }
    }
    String::from_utf8_lossy(head).into_owned()
}

/// What `document_text` answers.
#[derive(Debug)]
pub enum Document {
    Words(Py),
    /// There are no bytes to read, and this says why.
    Unresolved(Unresolved),
}

/// `GET /fluid/api/document?ref=`: `document_text`, from bytes verified against their name. The scope
/// goes before the file is opened.
pub fn document(
    window: &Window,
    record: &dyn RecordReader,
    class: ReadClass,
    reference: &str,
) -> Result<Document, OpError> {
    let op = Describe { window };
    let mut read = crate::run(&op, record, class, &asked(reference.to_owned()))?;
    let Prepared(about) = read
        .rows
        .pop()
        .ok_or_else(|| python_says("no description"))?;
    let mut state = about
        .get("state")
        .and_then(Py::as_str)
        .ok_or_else(|| python_says("a description with no state"))?
        .to_owned();
    let mut data = None;
    if state == "held" {
        let digest = about
            .get("digest")
            .and_then(Py::as_str)
            .ok_or_else(|| python_says("held with no digest"))?;
        let bytes = std::fs::read(window.held_path(digest))
            .map_err(|_| python_says("a held file this can't read"))?;
        let got: String = Sha256::digest(&bytes)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect();
        if got == digest {
            data = Some(bytes);
        } else {
            state = "held-but-corrupt".to_owned();
        }
    }
    let Some(data) = data else {
        return Ok(Document::Unresolved(unresolved(
            &format!("document={reference}"),
            &format!("no bytes to read: the artifact is {state}"),
            vec![("state", Py::str(state.as_str()))],
        )));
    };
    Ok(Document::Words(dict([
        ("ref", Py::str(reference)),
        ("size", Py::int(data.len())),
        ("cut", Py::Bool(data.len() > DOC_MAX)),
        ("text", Py::Str(words_of(&data, DOC_MAX))),
    ])))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_cut_leaves_out_a_character_it_split() {
        let data = "ab\u{1f600}".as_bytes();
        assert_eq!(words_of(data, 100), "ab\u{1f600}");
        assert_eq!(words_of(data, 6), "ab\u{1f600}");
        assert_eq!(words_of(data, 5), "ab");
        assert_eq!(words_of(data, 3), "ab");
    }

    #[test]
    fn bytes_that_are_not_utf_8_are_replaced_as_a_lossy_decode_replaces_them() {
        assert_eq!(words_of(b"a\xffb", 100), "a\u{fffd}b");
        // Past three bytes of leaving out, the cut gives up and replaces too.
        assert_eq!(words_of(b"\xff\xff\xff\xff\xff\xff", 5).chars().count(), 5);
    }

    #[test]
    fn only_a_part_of_the_object_type_is_named() {
        let body =
            pyjson::loads(r#"{"parts": [{"type": "text"}, 3, {"type": "object", "ref": "a"}]}"#)
                .unwrap();
        let got = object_parts(&body).unwrap();
        assert_eq!(got.len(), 1);
        assert_eq!(got[0].0, 2);
        assert!(object_parts(&pyjson::loads(r#"{"parts": 3}"#).unwrap()).is_err());
        assert!(object_parts(&Py::None).unwrap().is_empty());
    }
}
