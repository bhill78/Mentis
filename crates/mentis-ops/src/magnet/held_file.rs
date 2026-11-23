//! Exact retained filesystem observations. SQL under the caller's scope; bounded streaming
//! verification after releasing it. Never consult bindings or open a source folder.
use std::io::Read;

use mentis_record::{Flow, Param, ReadScope};
use sha2::{Digest, Sha256};
use serde_json::Value as Json;

use crate::{OpError, pyjson::{self, Py, dict}, window::Window};

pub(super) struct HeldFile {
    reference: String,
    digest: String,
    collection: String,
    path: String,
    at: Py,
}

fn unavailable(why: &str) -> OpError {
    OpError::NotFound { what: format!("held file unavailable: {why}") }
}

pub(super) fn prepare(scope: &mut dyn ReadScope, source: &Py) -> Result<HeldFile, OpError> {
    let collection = source.get("collection").and_then(Py::as_str).unwrap_or("");
    let path = source.get("path").and_then(Py::as_str).unwrap_or("");
    if collection.is_empty() || path.is_empty() || path.trim() != path
        || path.contains(['\\', ':', '*', '?', '[', ']', '\0'])
        || path.split('/').any(|p| matches!(p, "" | "." | "..")) {
        return Err(unavailable("Choose one held file; collection-wide file reads are unavailable."));
    }
    let source_id = format!("filesystem:{collection}");
    let mut found = None;
    scope.query(
        "SELECT id, body FROM entry WHERE family='admission' \
         AND json_extract(body,'$.source')=?1 \
         AND json_extract(body,'$.envelope.bulk_source.object')=?2 \
         AND EXISTS (SELECT 1 FROM operational WHERE act='source-collection-declared' \
         AND json_extract(detail,'$.collection')=?3 AND json_extract(detail,'$.connector')='filesystem') \
         ORDER BY seq DESC LIMIT 1",
        &[Param::Text(&source_id), Param::Text(path), Param::Text(collection)],
        &mut |row| {
            if let (Some(id), Some(body)) = (row.value(0)?.text(), row.value(1)?.text()) {
                found = Some((id.to_owned(), body.to_owned()));
            }
            Ok(Flow::Stop)
        },
    )?;
    let (reference, raw) = found.ok_or_else(|| unavailable("path has never been acquired in this filesystem collection"))?;
    let body: Json = serde_json::from_str(&raw).map_err(|_| unavailable("invalid observation"))?;
    let o = &body["envelope"]["bulk_source"];
    if o["state"] != "present" || body["content"] != "held" {
        return Err(unavailable("latest observation is absent or not held"));
    }
    if o["connector"] != "filesystem" || o["collection"] != collection || o["object"] != path {
        return Err(unavailable("observation provenance disagrees"));
    }
    if o["encoding"]["text"] != true {
        return Err(unavailable("observation is not text"));
    }
    let digest = body["locator"].as_str().and_then(|s| s.strip_prefix("sha256:"))
        .filter(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
        .ok_or_else(|| unavailable("invalid digest locator"))?.to_owned();
    let mut purged = false;
    scope.query("SELECT 1 FROM entry WHERE link_relation='purged' AND link_to=?1 LIMIT 1",
        &[Param::Text(&reference)], &mut |_| { purged = true; Ok(Flow::Stop) })?;
    if purged { return Err(unavailable("observation was purged")); }
    let at = body["admitted_at"].as_f64().filter(|n| n.is_finite())
        .ok_or_else(|| unavailable("missing acquisition time"))?;
    Ok(HeldFile { reference, digest, collection: collection.to_owned(), path: path.to_owned(),
        at: pyjson::loads(&at.to_string()).expect("finite time") })
}

impl HeldFile {
    pub(super) fn finish(self, window: &Window, stop: &dyn Fn() -> bool) -> Result<(Py, bool), OpError> {
        let mut file = std::fs::File::open(window.held_path(&self.digest))
            .map_err(|_| unavailable("retained bytes missing or unreadable"))?;
        let mut hash = Sha256::new();
        let mut size = 0usize;
        let mut prefix = Vec::with_capacity(65536);
        let mut carry = Vec::new();
        let mut chunk = [0u8; 16384];
        loop {
            if stop() { return Err(OpError::Busy { why: "held file read deadline ended".into() }); }
            let n = file.read(&mut chunk).map_err(|_| unavailable("retained bytes unreadable"))?;
            if n == 0 { break; }
            size += n;
            if size > 25 * 1024 * 1024 { return Err(unavailable("retained bytes exceed held limit")); }
            hash.update(&chunk[..n]);
            let take = n.min(65536 - prefix.len());
            prefix.extend_from_slice(&chunk[..take]);
            carry.extend_from_slice(&chunk[..n]);
            if carry.contains(&0) { return Err(unavailable("text contains NUL")); }
            match std::str::from_utf8(&carry) {
                Ok(_) => carry.clear(),
                Err(e) if e.error_len().is_none() => { carry.drain(..e.valid_up_to()); }
                Err(_) => return Err(unavailable("invalid UTF-8")),
            }
        }
        if !carry.is_empty() { return Err(unavailable("invalid UTF-8")); }
        if format!("{:x}", hash.finalize()) != self.digest { return Err(unavailable("corrupt digest")); }
        let end = match std::str::from_utf8(&prefix) {
            Ok(_) => prefix.len(), Err(e) => e.valid_up_to(),
        };
        let shortened = end < size;
        let text = std::str::from_utf8(&prefix[..end]).expect("validated UTF-8");
        let value = dict([
            ("ref", Py::str(&self.reference)), ("digest", Py::str(&self.digest)),
            ("collection", Py::str(&self.collection)), ("path", Py::str(&self.path)),
            ("text", Py::str(text)), ("offset", Py::int(0)), ("end", Py::int(end)),
            ("size", Py::int(size)), ("acquired_at", self.at.clone()),
            ("shortened", Py::Bool(shortened)), ("omitted_bytes", Py::int(size-end)),
            ("next_offset", if shortened { Py::int(end) } else { Py::None }),
            ("citation", Py::str(format!("{}@{}[0:{end}]", self.reference, &self.digest[..12]))),
        ]);
        Ok((dict([
            ("kind", Py::str("file")), ("id", Py::str(&self.reference)),
            ("version", Py::str(&self.reference)), ("conversation", Py::None),
            ("author", Py::None), ("at", self.at), ("via", Py::str("held-source")), ("value", value),
        ]), shortened))
    }
}
