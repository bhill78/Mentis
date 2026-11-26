//! Exact retained observations of one held object. SQL under the caller's scope; bounded streaming
//! verification after releasing it. Never consult bindings or open a source folder.
//!
//! [`choice`] is the one rule that decides what a `file` source names -- one object, every object
//! under a prefix, or the whole collection -- and it is the same rule Python's
//! `mentis.magnet.activation.runnable_files` keeps. The prefix and whole-collection forms are read by
//! the sibling [`super::collection_files`]; this module reads the exact one, and lends that reader its
//! bounded byte verification ([`verified_bytes`]) and its row shape ([`row`]) so one shape serves both.
use std::io::Read;

use mentis_record::{Flow, Param, ReadScope};
use serde_json::Value as Json;
use sha2::{Digest, Sha256};

use crate::{
    OpError,
    pyjson::{self, Py, dict},
    window::Window,
};

/// Bytes of one row's text. The existing cap, unchanged: a row carries at most this much, ending on a
/// UTF-8 character boundary, and says what it left out.
pub(super) const ROW_BYTES_MOST: usize = 65_536;
/// What may be retained at all for one object, whatever a row takes of it.
pub(super) const HELD_BYTES_MOST: usize = 25 * 1024 * 1024;

pub(super) struct HeldFile {
    reference: String,
    digest: String,
    collection: String,
    path: String,
    at: Py,
}

/// What a `file` source's `collection` and `path` name.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) enum Choice {
    /// No `path`: every object the collection holds now.
    Whole,
    /// A `path` ending in `/`: every object under it. The prefix keeps its trailing `/`.
    Prefix(String),
    /// A `path` naming one object exactly.
    Exact(String),
}

/// The words a source gets when its `collection`/`path` name nothing this can read. Python says the
/// same thing at activation (`mentis.magnet.activation.FILE_CHOICE`).
pub(super) const CHOICE_REFUSED: &str =
    "Choose a path, a prefix ending in `/`, or the whole collection.";

/// `(collection, what it names)`, or nothing. ONE RULE, kept with Python's `runnable_files`: a
/// component is never empty, `.` or `..`, and a path carries no separator, wildcard, drive letter or
/// NUL. A trailing `/` is the one empty component there may be, and it means a prefix.
pub(super) fn choice(source: &Py) -> Option<(String, Choice)> {
    let collection = source.get("collection").and_then(Py::as_str).unwrap_or("");
    if collection.is_empty() {
        return None;
    }
    let said = match source.get("path") {
        None | Some(Py::None) => return Some((collection.to_owned(), Choice::Whole)),
        Some(path) => path.as_str()?,
    };
    if said.is_empty()
        || said.trim() != said
        || said.contains(['\\', ':', '*', '?', '[', ']', '\0'])
    {
        return None;
    }
    let (parts, prefix) = match said.strip_suffix('/') {
        Some(head) => (head, true),
        None => (said, false),
    };
    if parts.split('/').any(|p| matches!(p, "" | "." | "..")) {
        return None;
    }
    Some((
        collection.to_owned(),
        if prefix {
            Choice::Prefix(said.to_owned())
        } else {
            Choice::Exact(said.to_owned())
        },
    ))
}

pub(super) fn unavailable(why: &str) -> OpError {
    OpError::NotFound {
        what: format!("held file unavailable: {why}"),
    }
}

pub(super) fn prepare(scope: &mut dyn ReadScope, source: &Py) -> Result<HeldFile, OpError> {
    let Some((collection, Choice::Exact(path))) = choice(source) else {
        return Err(unavailable(CHOICE_REFUSED));
    };
    let (collection, path) = (collection.as_str(), path.as_str());
    // WHICH CONNECTOR IS NOT THIS READER'S TO DECIDE. The declaration says it, and this reads what
    // that connector actually admitted. Nothing here names a connector, so a connector that becomes
    // available reads with no change here (`super::collection_files`).
    let connector = super::collection_files::declared_connector(scope, collection)?;
    let source_id = format!("{connector}:{collection}");
    let mut found = None;
    scope.query(
        "SELECT id, body FROM entry WHERE family='admission' \
         AND json_extract(body,'$.source')=?1 \
         AND json_extract(body,'$.envelope.bulk_source.object')=?2 \
         ORDER BY seq DESC LIMIT 1",
        &[Param::Text(&source_id), Param::Text(path)],
        &mut |row| {
            if let (Some(id), Some(body)) = (row.value(0)?.text(), row.value(1)?.text()) {
                found = Some((id.to_owned(), body.to_owned()));
            }
            Ok(Flow::Stop)
        },
    )?;
    let (reference, raw) =
        found.ok_or_else(|| unavailable("path has never been acquired in this collection"))?;
    let body: Json = serde_json::from_str(&raw).map_err(|_| unavailable("invalid observation"))?;
    let o = &body["envelope"]["bulk_source"];
    if o["state"] != "present" || body["content"] != "held" {
        return Err(unavailable("latest observation is absent or not held"));
    }
    if o["connector"] != connector.as_str() || o["collection"] != collection || o["object"] != path {
        return Err(unavailable("observation provenance disagrees"));
    }
    if o["encoding"]["text"] != true {
        return Err(unavailable("observation is not text"));
    }
    let digest = digest_of(&body).ok_or_else(|| unavailable("invalid digest locator"))?;
    if purged(scope, &reference)? {
        return Err(unavailable("observation was purged"));
    }
    let at = body["admitted_at"]
        .as_f64()
        .filter(|n| n.is_finite())
        .ok_or_else(|| unavailable("missing acquisition time"))?;
    Ok(HeldFile {
        reference,
        digest,
        collection: collection.to_owned(),
        path: path.to_owned(),
        at: pyjson::loads(&at.to_string()).expect("finite time"),
    })
}

/// The `sha256:` locator of an observation, where it is one.
pub(super) fn digest_of(body: &Json) -> Option<String> {
    body["locator"]
        .as_str()
        .and_then(|s| s.strip_prefix("sha256:"))
        .filter(|s| {
            s.len() == 64
                && s.bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        })
        .map(str::to_owned)
}

/// Whether this exact Admission's bytes were purged. A purge is reported, never read past.
pub(super) fn purged(scope: &mut dyn ReadScope, reference: &str) -> Result<bool, OpError> {
    let mut purged = false;
    scope.query(
        "SELECT 1 FROM entry WHERE link_relation='purged' AND link_to=?1 LIMIT 1",
        &[Param::Text(reference)],
        &mut |_| {
            purged = true;
            Ok(Flow::Stop)
        },
    )?;
    Ok(purged)
}

/// One object's retained text, verified whole against its digest and cut to [`ROW_BYTES_MOST`] on a
/// character boundary: `(text, end, size)`. The whole file is hashed however much of it a row takes,
/// so a row is never served from bytes the record did not commit to.
pub(super) fn verified_bytes(
    window: &Window,
    digest: &str,
    stop: &dyn Fn() -> bool,
) -> Result<(String, usize, usize), OpError> {
    let mut file = std::fs::File::open(window.held_path(digest))
        .map_err(|_| unavailable("retained bytes missing or unreadable"))?;
    let mut hash = Sha256::new();
    let mut size = 0usize;
    let mut prefix = Vec::with_capacity(ROW_BYTES_MOST);
    let mut carry = Vec::new();
    let mut chunk = [0u8; 16384];
    loop {
        if stop() {
            return Err(OpError::Busy {
                why: "held file read deadline ended".into(),
            });
        }
        let n = file
            .read(&mut chunk)
            .map_err(|_| unavailable("retained bytes unreadable"))?;
        if n == 0 {
            break;
        }
        size += n;
        if size > HELD_BYTES_MOST {
            return Err(unavailable("retained bytes exceed held limit"));
        }
        hash.update(&chunk[..n]);
        let take = n.min(ROW_BYTES_MOST - prefix.len());
        prefix.extend_from_slice(&chunk[..take]);
        carry.extend_from_slice(&chunk[..n]);
        if carry.contains(&0) {
            return Err(unavailable("text contains NUL"));
        }
        match std::str::from_utf8(&carry) {
            Ok(_) => carry.clear(),
            Err(e) if e.error_len().is_none() => {
                carry.drain(..e.valid_up_to());
            }
            Err(_) => return Err(unavailable("invalid UTF-8")),
        }
    }
    if !carry.is_empty() {
        return Err(unavailable("invalid UTF-8"));
    }
    let got: String = hash.finalize().iter().map(|b| format!("{b:02x}")).collect();
    if got != digest {
        return Err(unavailable("corrupt digest"));
    }
    let end = match std::str::from_utf8(&prefix) {
        Ok(_) => prefix.len(),
        Err(e) => e.valid_up_to(),
    };
    let text = std::str::from_utf8(&prefix[..end])
        .expect("validated UTF-8")
        .to_owned();
    Ok((text, end, size))
}

/// ONE ROW SHAPE, whatever named the object: an exact `path`, a prefix, or the whole collection. Python
/// pins these exact fields (`mentis.magnet.activation._verified_file`), so both readers build them here.
pub(super) fn row(
    reference: &str,
    digest: &str,
    collection: &str,
    path: &str,
    at: Py,
    (text, end, size): (String, usize, usize),
) -> (Py, bool) {
    let shortened = end < size;
    let value = dict([
        ("ref", Py::str(reference)),
        ("digest", Py::str(digest)),
        ("collection", Py::str(collection)),
        ("path", Py::str(path)),
        ("text", Py::Str(text)),
        ("offset", Py::int(0)),
        ("end", Py::int(end)),
        ("size", Py::int(size)),
        ("acquired_at", at.clone()),
        ("shortened", Py::Bool(shortened)),
        ("omitted_bytes", Py::int(size - end)),
        (
            "next_offset",
            if shortened { Py::int(end) } else { Py::None },
        ),
        (
            "citation",
            Py::str(format!("{reference}@{}[0:{end}]", &digest[..12])),
        ),
    ]);
    (
        dict([
            ("kind", Py::str("file")),
            ("id", Py::str(reference)),
            ("version", Py::str(reference)),
            ("conversation", Py::None),
            ("author", Py::None),
            ("at", at),
            ("via", Py::str("held-source")),
            ("value", value),
        ]),
        shortened,
    )
}

impl HeldFile {
    pub(super) fn finish(
        self,
        window: &Window,
        stop: &dyn Fn() -> bool,
    ) -> Result<(Py, bool), OpError> {
        let bytes = verified_bytes(window, &self.digest, stop)?;
        Ok(row(
            &self.reference,
            &self.digest,
            &self.collection,
            &self.path,
            self.at,
            bytes,
        ))
    }
}
