//! A post's objects: `fluid/objects.py`'s readings, over `mentis_extract`. **Nothing here parses
//! Markdown:** keys and kinds are the UI's, from the bundle it built. Python's module stays, whole, until
//! R7, for post checking and its other callers (`docs/rust/routes.md`).
//!
//! Cached by version, never by a live address, under the same key as Python's: the version, what the
//! run returned, and the bundle's path and digest. So an entry can't outlive what it was read from.

use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use std::sync::{Arc, PoisonError};

use mentis_extract::{Bundle, MAX_CHARS};
use mentis_record::{Flow, Id, Param, ReadScope};
use mentis_rules::{Entry, Line, id_list, lines_of};
use sha2::{Digest, Sha256};

use super::collections::{self, ConversationArgs};
use super::reads::{self, BATCH, CONTRIBUTION, Reply, closures, homes_of, names_of, numbers_of, text};
use super::{
    CACHE_BYTES, CACHE_MAX, Finished, FileVersion, Key, KINDS_MAX, Prepared, Unresolved, Window,
    bad_request, python_says, unresolved,
};
use crate::pyjson::{self, Py, dict, repr};
use crate::python;
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest};

/// `artifacts.STORE`, `held.LOCATOR`, `held.PURGED`.
const STORE: [&str; 2] = ["artifacts", "sha256"];
const LOCATOR: &str = "sha256:";
const PURGED: &str = "purged";
/// `objects.LOOK_BACK`, `objects.THREAD_MAX`.
const LOOK_BACK: usize = 20;
const THREAD_MAX: usize = reads::PAGE_MAX as usize;

const RETURNED: &str = "SELECT turn, detail FROM operational \
     WHERE turn IN (SELECT value FROM json_each(?1)) \
       AND act IN ('result-returned', 'result-recovered') ORDER BY seq";

const BODIES: &str = "SELECT id, family, body FROM entry \
     WHERE id IN (SELECT value FROM json_each(?1))";

/// What [`prepare`] reads: the admissions, and which were purged.
pub const DESCRIBE_STATEMENTS: u32 = 2;

fn poison_is_nothing<T>(lock: &std::sync::Mutex<T>) -> std::sync::MutexGuard<'_, T> {
    lock.lock().unwrap_or_else(PoisonError::into_inner)
}

/// One extraction, kept: `{"extracted": True, "objects", "renderer"}`.
#[derive(Debug, PartialEq)]
pub struct Extracted {
    pub objects: Vec<Py>,
    pub renderer: Py,
}

/// One version of one post to read.
#[derive(Clone, Debug)]
pub struct Wanted {
    root: String,
    version: Entry,
    returned: Vec<String>,
    key: Key,
}

impl Wanted {
    pub fn new(
        root: &str,
        version: Entry,
        returned: Vec<String>,
        bundle: &Bundle,
        window: &Window,
    ) -> Wanted {
        let key = Key {
            version: version.id.clone(),
            returned: returned.clone(),
            bundle: format!("{}:{}", window.bundle_text(), bundle.digest),
        };
        Wanted {
            root: root.to_owned(),
            version,
            returned,
            key,
        }
    }
}

/// What stands behind references, as read: enough for `describe` with no further statement.
#[derive(Debug, Default)]
pub struct Described {
    asked: HashSet<String>,
    rows: HashMap<String, (String, Py)>,
    purged_by: HashMap<String, Vec<String>>,
}

/// What a finishing step needs and can't read any more, all taken before the scope was let go.
#[derive(Debug, Default)]
pub struct PreparedInputs {
    pinned: HashMap<Key, Arc<Extracted>>,
    kinds: HashMap<Key, Option<Vec<String>>>,
    described: Described,
}

/// `(version.get("body") or {}).get("parts") or []`.
fn parts_of(version: &Entry) -> Result<Vec<Py>, OpError> {
    let body = pyjson::loads(&version.body_json)
        .ok_or_else(|| python_says("a body this can't read"))?;
    if !body.truthy() {
        return Ok(Vec::new());
    }
    if !body.is_dict() {
        return Err(python_says("a body that isn't an object"));
    }
    match body.get("parts") {
        Some(parts) if parts.truthy() => match parts {
            Py::List(parts) => Ok(parts.clone()),
            _ => Err(python_says("parts that aren't a list")),
        },
        _ => Ok(Vec::new()),
    }
}

/// Whether `annotate_part` asks what stands behind this part's `ref`.
fn annotated_ref(part: &Py) -> Option<&str> {
    if !part.is_dict() || part.get("type").and_then(Py::as_str) == Some("text") {
        return None;
    }
    if matches!(
        part.get("type").and_then(Py::as_str),
        Some("acquired" | "object")
    ) {
        return None;
    }
    part.get("ref").and_then(Py::as_str).filter(|r| !r.is_empty())
}

/// All of `wanted` that isn't kept already, and what stands behind what they name. `for_kinds` reads
/// the kinds kept apart first. `ref_of_key`: for a kept extraction, a ref its object of this key will
/// ask about after the scope has gone.
fn prepare_inputs(
    window: &Window,
    scope: &mut dyn ReadScope,
    wanted: &[&Wanted],
    for_kinds: bool,
    ref_of_key: Option<&str>,
) -> Result<PreparedInputs, OpError> {
    let mut prepared = PreparedInputs::default();
    let mut refs: Vec<String> = Vec::new();
    for want in wanted {
        if for_kinds {
            let known = poison_is_nothing(&window.kinds).get(&want.key);
            if let Some(kinds) = known {
                prepared.kinds.insert(want.key.clone(), kinds);
                continue;
            }
        }
        let held = poison_is_nothing(&window.extractions).get(&want.key);
        if let Some(extracted) = held {
            if let Some(key) = ref_of_key {
                refs.extend(
                    extracted
                        .objects
                        .iter()
                        .filter(|o| o.get("key").and_then(Py::as_str) == Some(key))
                        .filter_map(|o| o.get("ref").and_then(Py::as_str))
                        .map(str::to_owned),
                );
            }
            prepared.pinned.insert(want.key.clone(), extracted);
            continue;
        }
        for part in parts_of(&want.version)? {
            if let Some(found) = annotated_ref(&part) {
                refs.push(found.to_owned());
            }
        }
        refs.extend(want.returned.iter().cloned());
    }
    refs.sort();
    refs.dedup();
    if refs.is_empty() {
        return Ok(prepared);
    }
    let list = id_list(refs.iter().map(String::as_str));
    let described = &mut prepared.described;
    let (rows, unreadable) = {
        let mut rows = HashMap::with_capacity(refs.len());
        let mut unreadable = false;
        scope.query(BODIES, &[Param::Text(&list)], &mut |row| {
            let Some(body) = text(row, 2)?.as_deref().and_then(pyjson::loads) else {
                unreadable = true;
                return Ok(Flow::Stop);
            };
            rows.insert(
                text(row, 0)?.unwrap_or_default(),
                (text(row, 1)?.unwrap_or_default(), body),
            );
            Ok(Flow::Continue)
        })?;
        (rows, unreadable)
    };
    if unreadable {
        return Err(python_says("an admission this can't read"));
    }
    described.rows = rows;
    let named: Vec<&str> = refs.iter().map(String::as_str).collect();
    for link in reads::links_to(scope, PURGED, &named)? {
        described
            .purged_by
            .entry(link.to)
            .or_default()
            .push(link.from);
    }
    described.asked = refs.iter().cloned().collect();
    Ok(prepared)
}

/// For `posts?ids=&thread=1`: a version's kinds may be all that's kept of it.
pub fn prepare_kinds(
    window: &Window,
    scope: &mut dyn ReadScope,
    wanted: &[&Wanted],
) -> Result<PreparedInputs, OpError> {
    prepare_inputs(window, scope, wanted, true, None)
}

/// `_returned_of`: post -> what its run returned with it, in the acts' order.
pub fn returned_of(
    scope: &mut dyn ReadScope,
    ids: &[&str],
) -> Result<HashMap<String, Vec<String>>, OpError> {
    let mut out: HashMap<String, Vec<String>> =
        ids.iter().map(|id| ((*id).to_owned(), Vec::new())).collect();
    if ids.is_empty() {
        return Ok(out);
    }
    let list = id_list(ids.iter().copied());
    let mut unreadable = false;
    scope.query(RETURNED, &[Param::Text(&list)], &mut |row| {
        let Some(detail) = text(row, 1)?.as_deref().and_then(pyjson::loads) else {
            unreadable = true;
            return Ok(Flow::Stop);
        };
        let refs = if !detail.truthy() {
            None
        } else if detail.is_dict() {
            detail.get("returned_artifacts").filter(|refs| refs.truthy())
        } else {
            unreadable = true;
            return Ok(Flow::Stop);
        };
        let Some(refs) = refs else {
            return Ok(Flow::Continue);
        };
        let Some(refs) = refs.as_list() else {
            unreadable = true;
            return Ok(Flow::Stop);
        };
        let turn = text(row, 0)?.unwrap_or_default();
        for found in refs {
            let Some(found) = found.as_str() else {
                unreadable = true;
                return Ok(Flow::Stop);
            };
            out.entry(turn.clone()).or_default().push(found.to_owned());
        }
        Ok(Flow::Continue)
    })?;
    if unreadable {
        return Err(python_says("what a run returned, in a shape this can't read"));
    }
    Ok(out)
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Verify {
    /// `verify="cached"`: hashed once per file version.
    Cached,
    /// `verify=False`: only whether the file is there.
    Exists,
}

impl Window {
    fn held_path(&self, digest: &str) -> PathBuf {
        let mut path = self.root.clone();
        path.extend(STORE);
        path.push(&digest[..2]);
        path.push(digest);
        path
    }

    /// `_state_cached`.
    fn state_cached(&self, digest: &str) -> Result<&'static str, OpError> {
        if !is_digest(digest) {
            return Ok("missing");
        }
        let path = self.held_path(digest);
        let meta = match std::fs::metadata(&path) {
            Ok(meta) => meta,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok("missing"),
            Err(_) => return Err(python_says("a held file this can't ask about")),
        };
        let modified_ns = meta
            .modified()
            .ok()
            .and_then(|at| at.duration_since(std::time::UNIX_EPOCH).ok())
            .map_or(0, |at| at.as_nanos());
        let version = FileVersion {
            digest: digest.to_owned(),
            size: meta.len(),
            modified_ns,
        };
        if let Some(known) = poison_is_nothing(&self.verified).get(&version) {
            return Ok(*known);
        }
        let state = if !meta.is_file() {
            "missing"
        } else {
            let data = std::fs::read(&path)
                .map_err(|_| python_says("a held file this can't read yet"))?;
            let mut got = String::with_capacity(64);
            for byte in Sha256::digest(&data).iter() {
                got.push_str(&format!("{byte:02x}"));
            }
            if got == digest { "present" } else { "corrupt" }
        };
        poison_is_nothing(&self.verified).insert(version, state);
        Ok(state)
    }

    /// `describe`, with `public` already applied.
    fn describe(&self, described: &Described, ask: &str, verify: Verify) -> Result<Py, OpError> {
        let reference = Py::str(ask);
        if !described.asked.contains(ask) {
            return Err(python_says("a reference nothing read ahead of it"));
        }
        let Some((family, body)) = described.rows.get(ask) else {
            return Ok(dict([("ref", reference), ("state", Py::str("unknown"))]));
        };
        if family != "admission" {
            return Ok(dict([
                ("ref", reference),
                ("state", Py::str("not-an-artifact")),
            ]));
        }
        if !body.is_dict() {
            return Err(python_says("an admission's body that isn't an object"));
        }
        let field = |name: &str| body.get(name).cloned().unwrap_or(Py::None);
        if body.get("content").and_then(Py::as_str) != Some("held") {
            return Ok(dict([
                ("ref", reference),
                ("state", Py::str("not-held")),
                ("content", field("content")),
                ("locator", field("locator")),
            ]));
        }
        let envelope = body.get("envelope").filter(|env| env.truthy());
        if envelope.is_some_and(|env| !env.is_dict()) {
            return Err(python_says("an envelope that isn't an object"));
        }
        let of_envelope = |name: &str| {
            envelope
                .and_then(|env| env.get(name))
                .cloned()
                .unwrap_or(Py::None)
        };
        let digest = body
            .get("locator")
            .and_then(Py::as_str)
            .and_then(|locator| locator.strip_prefix(LOCATOR))
            .filter(|digest| is_digest(digest))
            .unwrap_or("");
        let mut out = dict([
            ("ref", reference),
            ("digest", Py::str(digest)),
            ("size", of_envelope("size")),
            ("claimed_media_type", field("payload_type")),
            ("name", of_envelope("claimed_name")),
            ("door", of_envelope("door")),
            ("source", field("source")),
            ("url", Py::Str(format!("/api/artifacts/{ask}"))),
        ]);
        if let Some(purges) = described.purged_by.get(ask) {
            out.set("state", Py::str("purged"));
            out.set(
                "purged_by",
                Py::List(purges.iter().map(|from| Py::str(from.as_str())).collect()),
            );
            let remain = is_digest(digest) && self.held_path(digest).is_file();
            out.set("bytes_remain", Py::Bool(remain));
            return Ok(out);
        }
        let state = match verify {
            Verify::Cached => self.state_cached(digest)?,
            Verify::Exists => {
                if !is_digest(digest) {
                    return Err(python_says("a held locator that names no digest"));
                }
                if self.held_path(digest).is_file() {
                    "present"
                } else {
                    "missing"
                }
            }
        };
        out.set(
            "state",
            Py::str(match state {
                "present" => "held",
                "missing" => "held-but-missing",
                _ => "held-but-corrupt",
            }),
        );
        Ok(out)
    }

    /// `input_of`: what the bundle is given for one version.
    fn input_of(&self, described: &Described, want: &Wanted) -> Result<Py, OpError> {
        let mut parts = Vec::new();
        for part in parts_of(&want.version)? {
            parts.push(match annotated_ref(&part) {
                None => part,
                Some(found) => {
                    let found = found.to_owned();
                    let about = self.describe(described, &found, Verify::Cached)?;
                    if matches!(
                        about.get("state").and_then(Py::as_str),
                        Some("unknown" | "not-an-artifact")
                    ) {
                        part
                    } else {
                        let mut part = part;
                        part.set("artifact", about);
                        part
                    }
                }
            });
        }
        let mut returned_with = Vec::with_capacity(want.returned.len());
        for found in &want.returned {
            returned_with.push(self.describe(described, found, Verify::Cached)?);
        }
        Ok(dict([
            ("id", Py::str(want.root.as_str())),
            ("parts", Py::List(parts)),
            ("returned_with", Py::List(returned_with)),
        ]))
    }
}

/// `held.is_digest`.
fn is_digest(text: &str) -> bool {
    text.len() == 64 && text.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

/// What `extract` answers.
enum Outcome {
    Read { extracted: Arc<Extracted>, cached: bool },
    /// Over the limit, in its own words. Engine failures aren't here: they're Python's to say.
    NotRead { why_not: String, input: Py },
}

/// `sum(len(p.get("text") or "") for p in parts if isinstance(p, dict))`.
fn text_size(input: &Py) -> Result<usize, OpError> {
    let mut size = 0;
    for part in input.get("parts").and_then(Py::as_list).unwrap_or(&[]) {
        if !part.is_dict() {
            continue;
        }
        match part.get("text") {
            None => {}
            Some(found) if !found.truthy() => {}
            Some(Py::Str(words)) => size += words.chars().count(),
            Some(Py::List(items)) => size += items.len(),
            Some(Py::Dict(items)) => size += items.len(),
            Some(_) => return Err(python_says("a part's text that has no length")),
        }
    }
    Ok(size)
}

/// `extract`.
fn fetch(
    window: &Window,
    bundle: &Bundle,
    want: &Wanted,
    prepared: &PreparedInputs,
) -> Result<Outcome, OpError> {
    if let Some(extracted) = prepared.pinned.get(&want.key) {
        return Ok(Outcome::Read {
            extracted: Arc::clone(extracted),
            cached: true,
        });
    }
    let held = poison_is_nothing(&window.extractions).get(&want.key);
    if let Some(extracted) = held {
        return Ok(Outcome::Read {
            extracted,
            cached: true,
        });
    }
    let input = window.input_of(&prepared.described, want)?;
    let size = text_size(&input)?;
    if size > MAX_CHARS {
        return Ok(Outcome::NotRead {
            why_not: format!(
                "the post's text is {size} characters; extraction reads at most {MAX_CHARS}"
            ),
            input,
        });
    }
    // No lock, and no scope. Two asking for one version at once each read it, and the second keeps
    // what they both found.
    let text = window
        .engines
        .extract(bundle, &input.dumps())
        .map_err(|why| python_says(&why.to_string()))?;
    let got = pyjson::loads(&text).ok_or_else(|| python_says("the bundle's answer doesn't read"))?;
    let objects = match got.get("objects") {
        Some(Py::List(objects)) if got.is_dict() => objects.clone(),
        _ => return Err(python_says("the bundle returned a malformed extraction")),
    };
    let renderer = dict([
        ("bundle", Py::Str(window.bundle_text())),
        ("sha256", Py::str(&bundle.digest[..16])),
    ]);
    let extracted = Arc::new(Extracted { objects, renderer });
    let kept = dict([
        ("extracted", Py::Bool(true)),
        ("objects", Py::List(extracted.objects.clone())),
        ("renderer", extracted.renderer.clone()),
    ]);
    poison_is_nothing(&window.extractions).put(
        want.key.clone(),
        Arc::clone(&extracted),
        kept.dumps().len(),
        CACHE_MAX,
        CACHE_BYTES,
    );
    Ok(Outcome::Read {
        extracted,
        cached: false,
    })
}

fn plain<'a>(o: &'a Py, name: &str) -> Result<Option<&'a str>, OpError> {
    match o.get(name) {
        None | Some(Py::None) => Ok(None),
        Some(Py::Str(words)) => Ok(Some(words)),
        Some(found) if !found.truthy() => Ok(None),
        Some(_) => Err(python_says("a field the chip's rule reads that isn't text")),
    }
}

/// `is_text`.
fn is_text(media_type: &str, name: &str) -> bool {
    const TEXT: [&str; 45] = [
        ".md", ".markdown", ".txt", ".py", ".json", ".jsonl", ".ts", ".tsx", ".js", ".jsx", ".mjs",
        ".cjs", ".css", ".scss", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".sh",
        ".ps1", ".bat", ".sql", ".csv", ".tsv", ".log", ".rs", ".go", ".java", ".kt", ".c", ".h",
        ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".diff", ".patch", ".env", ".gitignore",
        ".dockerfile",
    ];
    const TEXT_TYPES: [&str; 10] = [
        "application/json",
        "application/xml",
        "application/javascript",
        "application/x-python",
        "application/x-sh",
        "application/yaml",
        "application/x-yaml",
        "application/toml",
        "application/sql",
        "application/x-ndjson",
    ];
    let mt = media_type.split(';').next().unwrap_or("");
    let mt = python::strip(mt);
    (mt.starts_with("text/") && mt != "text/html")
        || TEXT_TYPES.contains(&mt)
        || mt.ends_with("+json")
        || mt.ends_with("+xml")
        || TEXT.iter().any(|ending| name.ends_with(ending))
}

/// `chip_kind`: how the chip names one object This post draws, or nothing for one it doesn't.
fn chip_kind(o: &Py) -> Result<Option<String>, OpError> {
    if !o.is_dict() {
        return Err(python_says("an object that isn't an object"));
    }
    if let Some(is) = o.get("is").filter(|is| is.is_dict())
        && let Some(chip) = is.get("chip")
    {
        return match chip {
            Py::Str(chip) if !chip.is_empty() => Ok(Some(chip.clone())),
            found if !found.truthy() => Ok(None),
            _ => Err(python_says("a chip that isn't text")),
        };
    }
    let kind = o.get("kind").and_then(Py::as_str);
    if !matches!(o.get("parent"), None | Some(Py::None)) || kind == Some("post-text") {
        return Ok(None);
    }
    let lower = |text: &str| {
        python::lower(text).ok_or_else(|| python_says("a name in letters newer than Python's table"))
    };
    if kind == Some("block") {
        let t = lower(plain(o, "type")?.unwrap_or("block"))?;
        return Ok(Some(match t.as_str() {
            "pad" => "note".to_owned(),
            "ref" => "reference".to_owned(),
            "markdown" => "doc".to_owned(),
            _ => t,
        }));
    }
    let mt = lower(plain(o, "media_type")?.unwrap_or(""))?;
    let name = lower(plain(o, "title")?.unwrap_or(""))?;
    let image = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]
        .iter()
        .any(|ending| name.ends_with(ending));
    if kind == Some("figure") || mt.starts_with("image/") || image {
        return Ok(Some("image".to_owned()));
    }
    if is_text(&mt, &name) {
        return Ok(Some("doc".to_owned()));
    }
    Ok(Some("file".to_owned()))
}

/// `_kinds_of_version`: the chip kinds of one version's objects, or `None` if it isn't read. A refusal
/// is remembered too, under the same bound.
pub fn kinds_of(
    window: &Window,
    bundle: &Bundle,
    want: &Wanted,
    prepared: &PreparedInputs,
) -> Result<Option<Vec<String>>, OpError> {
    if let Some(kinds) = prepared.kinds.get(&want.key) {
        return Ok(kinds.clone());
    }
    let known = poison_is_nothing(&window.kinds).get(&want.key);
    if let Some(kinds) = known {
        return Ok(kinds);
    }
    let kinds = match fetch(window, bundle, want, prepared)? {
        Outcome::NotRead { .. } => None,
        Outcome::Read { extracted, .. } => {
            let mut kinds = Vec::with_capacity(extracted.objects.len());
            for o in &extracted.objects {
                kinds.extend(chip_kind(o)?);
            }
            Some(kinds)
        }
    };
    poison_is_nothing(&window.kinds).put(
        want.key.clone(),
        kinds.clone(),
        0,
        KINDS_MAX,
        usize::MAX,
    );
    Ok(kinds)
}

/// `str(part)`, `_part_token`.
fn part_token(part: Option<&Py>) -> Result<String, OpError> {
    match part {
        None | Some(Py::None) => Ok("-".to_owned()),
        Some(Py::Int(digits)) => Ok(digits.clone()),
        Some(Py::Str(words)) => Ok(words.clone()),
        Some(_) => Err(python_says("an object's part that isn't a number")),
    }
}

fn key_of(o: &Py) -> Result<&str, OpError> {
    o.get("key")
        .and_then(Py::as_str)
        .ok_or_else(|| python_says("an object whose key isn't text"))
}

/// `_listing`: an object as listed, what it is and where, never its content.
fn listing(o: &Py, root: &str, version: &str) -> Result<Py, OpError> {
    if !o.is_dict() {
        return Err(python_says("an object that isn't an object"));
    }
    let key = key_of(o)?;
    let mut out = Py::Dict(
        [
            "key", "part", "kind", "type", "title", "name", "identity", "stable", "parent", "page",
            "line", "end", "formats",
        ]
        .iter()
        .map(|name| ((*name).to_owned(), o.get(name).cloned().unwrap_or(Py::None)))
        .collect(),
    );
    let on = |name: &str| o.get(name).filter(|found| found.truthy());
    if let Some(found) = on("duplicate") {
        out.set("duplicate", found.clone());
    }
    out.set(
        "declared",
        Py::Bool(o.get("identity").and_then(Py::as_str) == Some("declared")),
    );
    out.set(
        "address",
        dict([
            (
                "exact",
                Py::Str(format!(
                    "exact:{version}:{}:{key}",
                    part_token(o.get("part"))?
                )),
            ),
            ("live", Py::Str(format!("live:{root}:{key}"))),
        ]),
    );
    if let Some(found) = on("block") {
        out.set("block", found.clone());
    }
    if let Some(found) = on("ref") {
        let Some(reference) = found.as_str() else {
            return Err(python_says("an object's ref that isn't text"));
        };
        out.set("ref", found.clone());
        out.set(
            "artifact",
            dict([
                ("ref", found.clone()),
                ("url", Py::Str(format!("/api/artifacts/{reference}"))),
            ]),
        );
    }
    if let Some(found) = on("media_type") {
        out.set("media_type", found.clone());
    }
    if let Some(found) = on("link") {
        out.set("link", found.clone());
    }
    if let Some(found) = on("is") {
        out.set("is", found.clone());
    }
    Ok(out)
}

/// `_where`.
#[derive(Clone, Debug)]
struct Whereabouts {
    home: Option<String>,
    home_name: Option<String>,
    number: Option<i64>,
}

impl Whereabouts {
    fn fields(&self) -> [(&'static str, Py); 3] {
        [
            ("home", Py::opt_str(self.home.as_deref())),
            ("home_name", Py::opt_str(self.home_name.as_deref())),
            ("number", self.number.map_or(Py::None, Py::int)),
        ]
    }
}

fn where_of(scope: &mut dyn ReadScope, root: &str) -> Result<Whereabouts, OpError> {
    let homes = homes_of(scope, &[root])?;
    let home = homes.get(root).cloned();
    let number = numbers_of(scope, &homes)?.get(root).copied();
    let home_name = match &home {
        None => None,
        Some(home) => names_of(scope, &[home.as_str()])?.get(home).cloned(),
    };
    Ok(Whereabouts {
        home,
        home_name,
        number,
    })
}

/// `_root_of`: a post, or a version of one, with its root; or what's known of something else.
struct RootOf {
    root: Option<String>,
    held: bool,
}

fn root_of(scope: &mut dyn ReadScope, id: &str) -> Result<RootOf, OpError> {
    let heads = reads::heads(scope, &[id])?;
    let Some(head) = heads.get(id) else {
        return Ok(RootOf {
            root: None,
            held: false,
        });
    };
    if !head.is_post() {
        return Ok(RootOf {
            root: None,
            held: true,
        });
    }
    let asked = [Id(id.to_owned())];
    let root = lines_of(scope, &asked)?
        .remove(&asked[0])
        .map_or_else(|| id.to_owned(), |line| line.root);
    let found = homes_of(scope, &[root.as_str()])?.contains_key(&root);
    Ok(RootOf {
        root: found.then_some(root),
        held: true,
    })
}

/// One post's listing, read and ready: `_listed`, as far as it has no need of the engine.
struct Listing {
    root: String,
    ids: Vec<String>,
    current: String,
    whereabouts: Whereabouts,
    deleted: bool,
    /// The version asked for, then the current one if that's another.
    wanted: Vec<Wanted>,
}

fn plan_listing(
    window: &Window,
    bundle: &Bundle,
    root: &str,
    line: &Line,
    whereabouts: Whereabouts,
    returned: Vec<String>,
    version: Option<&str>,
) -> Result<Listing, Unresolved> {
    let ids: Vec<String> = line.versions.iter().map(|v| v.id.clone()).collect();
    let current = ids.last().cloned().unwrap_or_else(|| root.to_owned());
    let deleted = line.deletion.is_some();
    let mut wanted = Vec::new();
    if !deleted {
        if let Some(version) = version
            && !ids.iter().any(|id| id == version)
        {
            return Err(unresolved(
                &format!("post={root}&version={version}"),
                &format!("{version} is not a version of the post {root}"),
                vec![
                    ("post", Py::str(root)),
                    (
                        "versions",
                        Py::List(ids.iter().map(|id| Py::str(id.as_str())).collect()),
                    ),
                ],
            ));
        }
        let asked = version.unwrap_or(&current);
        let at = |id: &str| line.versions.iter().find(|v| v.id == id).cloned();
        if let Some(entry) = at(asked) {
            wanted.push(Wanted::new(root, entry, returned.clone(), bundle, window));
        }
        if asked != current
            && let Some(entry) = at(&current)
        {
            wanted.push(Wanted::new(root, entry, returned, bundle, window));
        }
    }
    Ok(Listing {
        root: root.to_owned(),
        ids,
        current,
        whereabouts,
        deleted,
        wanted,
    })
}

impl Listing {
    fn finish(
        &self,
        window: &Window,
        bundle: &Bundle,
        prepared: &PreparedInputs,
    ) -> Result<Py, OpError> {
        let [home, home_name, number] = self.whereabouts.fields();
        let mut out = dict([
            ("post", Py::str(self.root.as_str())),
            ("current_version", Py::str(self.current.as_str())),
            (
                "versions",
                Py::List(self.ids.iter().map(|id| Py::str(id.as_str())).collect()),
            ),
            home,
            home_name,
            number,
        ]);
        if self.deleted {
            out.set("version", Py::None);
            out.set("deleted", Py::Bool(true));
            out.set("objects", Py::List(Vec::new()));
            out.set("extracted", Py::None);
            out.set(
                "why",
                Py::str("the post was deleted; its objects are not served"),
            );
            return Ok(out);
        }
        let want = self
            .wanted
            .first()
            .ok_or_else(|| python_says("a line with no versions"))?;
        let version = want.version.id.as_str();
        let is_current = version == self.current;
        let got = fetch(window, bundle, want, prepared)?;
        out.set("version", Py::str(version));
        out.set("current", Py::Bool(is_current));
        out.set("deleted", Py::Bool(false));
        let (extracted, cached) = match got {
            Outcome::NotRead { why_not, input } => {
                out.set("extracted", Py::Bool(false));
                out.set("why_not", Py::Str(why_not));
                out.set("input", input);
                return Ok(out);
            }
            Outcome::Read { extracted, cached } => (extracted, cached),
        };
        let mut objects = Vec::with_capacity(extracted.objects.len());
        for o in &extracted.objects {
            objects.push(listing(o, &self.root, version)?);
        }
        if !is_current && let Some(now) = self.wanted.get(1) {
            if let Outcome::Read {
                extracted: now, ..
            } = fetch(window, bundle, now, prepared)?
            {
                let mut keys = HashSet::with_capacity(now.objects.len());
                for o in &now.objects {
                    keys.insert(key_of(o)?.to_owned());
                }
                for o in &mut objects {
                    let resolves = o.get("key").and_then(Py::as_str).is_some_and(|k| keys.contains(k));
                    o.set("live_resolves", Py::Bool(resolves));
                }
            }
        }
        out.set("extracted", Py::Bool(true));
        out.set("cached", Py::Bool(cached));
        out.set("renderer", extracted.renderer.clone());
        out.set("objects", Py::List(objects));
        Ok(out)
    }
}

/// `_many`'s reading of each post.
enum Many {
    Error { post: String, why: &'static str },
    Listed(Box<Listing>),
}

fn plan_many(
    window: &Window,
    scope: &mut dyn ReadScope,
    bundle: &Bundle,
    ids: &[&str],
) -> Result<Vec<Many>, OpError> {
    let mut seen = HashSet::with_capacity(ids.len());
    let ids: Vec<&str> = ids.iter().copied().filter(|id| seen.insert(*id)).collect();
    let asked = collections::ids_of(&ids);
    let lines = lines_of(scope, &asked)?;
    let posts: Vec<&str> = ids
        .iter()
        .copied()
        .filter(|id| {
            lines
                .get(&Id((*id).to_owned()))
                .and_then(|line| line.versions.first())
                .is_some_and(|first| {
                    first.family == "entry"
                        && !first.is_link
                        && first.kind.as_deref() == Some(CONTRIBUTION)
                })
        })
        .collect();
    let homes = homes_of(scope, &posts)?;
    let numbers = numbers_of(scope, &homes)?;
    let homed: Vec<&str> = homes.values().map(String::as_str).collect();
    let names = names_of(scope, &homed)?;
    let with_home: Vec<&str> = homes.keys().map(String::as_str).collect();
    let returned = returned_of(scope, &with_home)?;
    let mut out = Vec::with_capacity(ids.len());
    for id in &ids {
        let line = lines.get(&Id((*id).to_owned()));
        let Some(home) = homes.get(*id) else {
            out.push(Many::Error {
                post: (*id).to_owned(),
                why: if line.is_some() {
                    "not a post"
                } else {
                    "the record holds no such entry"
                },
            });
            continue;
        };
        let line = line.ok_or_else(|| python_says("a homed post with no line"))?;
        let whereabouts = Whereabouts {
            home: Some(home.clone()),
            home_name: names.get(home).cloned(),
            number: numbers.get(*id).copied(),
        };
        let listing = plan_listing(
            window,
            bundle,
            id,
            line,
            whereabouts,
            returned.get(*id).cloned().unwrap_or_default(),
            None,
        )
        .map_err(|_| python_says("a version asked of no version"))?;
        out.push(Many::Listed(Box::new(listing)));
    }
    Ok(out)
}

fn finish_many(
    many: &[Many],
    window: &Window,
    bundle: &Bundle,
    prepared: &PreparedInputs,
) -> Result<Vec<Py>, OpError> {
    let mut out = Vec::with_capacity(many.len());
    for item in many {
        out.push(match item {
            Many::Error { post, why } => dict([
                ("post", Py::str(post.as_str())),
                ("error", Py::str(*why)),
            ]),
            Many::Listed(listing) => listing.finish(window, bundle, prepared)?,
        });
    }
    Ok(out)
}

fn wanted_of(many: &[Many]) -> Vec<&Wanted> {
    many.iter()
        .filter_map(|item| match item {
            Many::Listed(listing) => Some(listing.wanted.iter()),
            Many::Error { .. } => None,
        })
        .flatten()
        .collect()
}

/// `parse_address`.
enum Address {
    Exact {
        version: String,
        part: Option<i128>,
        key: String,
    },
    Live {
        root: String,
        key: String,
    },
}

fn parse_address(address: &str) -> Result<Address, OpError> {
    if address.starts_with("exact:") {
        let bits: Vec<&str> = address.splitn(4, ':').collect();
        if let [_, version, part, key] = bits.as_slice()
            && !version.is_empty()
            && !key.is_empty()
        {
            if *part == "-" {
                return Ok(Address::Exact {
                    version: (*version).to_owned(),
                    part: None,
                    key: (*key).to_owned(),
                });
            }
            if !part.is_ascii() {
                return Err(python_says("a part in other digits"));
            }
            if !part.is_empty() && part.bytes().all(|b| b.is_ascii_digit()) {
                let Ok(part) = part.parse::<i128>() else {
                    return Err(python_says("a part past what an object can have"));
                };
                return Ok(Address::Exact {
                    version: (*version).to_owned(),
                    part: Some(part),
                    key: (*key).to_owned(),
                });
            }
        }
    } else if address.starts_with("live:") {
        let bits: Vec<&str> = address.splitn(3, ':').collect();
        if let [_, root, key] = bits.as_slice()
            && !root.is_empty()
            && !key.is_empty()
        {
            return Ok(Address::Live {
                root: (*root).to_owned(),
                key: (*key).to_owned(),
            });
        }
    }
    let shown = repr(address).ok_or_else(|| python_says("an address to show in other words"))?;
    Err(bad_request(format!(
        "not an object address: {shown} -- an address is \
         exact:<version>:<part>:<key> or live:<root>:<key>"
    )))
}

/// What a request asks of `/fluid/api/objects` and `/fluid/api/objects/<address>`.
#[derive(Clone, Debug)]
pub enum ObjectsAsk {
    Conversation {
        id: String,
        before: Option<String>,
        limit: u32,
    },
    Posts {
        ids: Vec<String>,
    },
    Thread {
        root: String,
    },
    Post {
        root: String,
        version: Option<String>,
    },
    One {
        address: String,
        format: String,
    },
}

pub struct ObjectsArgs {
    pub bundle: Bundle,
    pub ask: ObjectsAsk,
}

/// `one_object`, read and ready.
pub struct OnePlan {
    address: String,
    form: &'static str,
    key: String,
    part: Option<i128>,
    is_exact: bool,
    format: String,
    root: String,
    version: String,
    ids: Vec<String>,
    whereabouts: Whereabouts,
    want: Wanted,
    /// Newest first, the versions before the current one, for `last_version`.
    older: Vec<Wanted>,
}

enum Plan {
    Conversation {
        collected: collections::Collected,
        roots: usize,
        limit: u32,
        conversation: String,
        parent_of: HashMap<String, String>,
        many: Vec<Many>,
    },
    Posts {
        many: Vec<Many>,
    },
    Thread {
        root: String,
        replies: usize,
        omitted: usize,
        many: Vec<Many>,
    },
    Post(Box<Listing>),
    One(Box<OnePlan>),
    Unresolved(Unresolved),
}

pub struct ObjectsPlan {
    plan: Plan,
    bundle: Bundle,
    prepared: PreparedInputs,
    at: Py,
}

/// The op.
pub struct Objects<'w> {
    pub window: &'w Window,
}

impl ReadOp for Objects<'_> {
    type Args = ObjectsArgs;
    type Row = Prepared<ObjectsPlan>;

    const NAME: &'static str = "objects";
    /// The position; then the worst of `objects?conversation=`, its page, closures and many posts, and
    /// `objects/<address>`, with its two lines. Either way what stands behind the references.
    const BUDGET: Budget = Budget {
        statements: 1
            + collections::COLLECTED_STATEMENTS
            + 1
            + mentis_rules::STATEMENTS
            + 1
            + 1
            + mentis_rules::STATEMENTS
            + 1
            + DESCRIBE_STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<ObjectsArgs>,
    ) -> Result<ReadAnswer<Prepared<ObjectsPlan>>, OpError> {
        let as_of = scope.position();
        let window = self.window;
        let bundle = &request.args.bundle;
        let (plan, prepared) = match &request.args.ask {
            ObjectsAsk::Conversation { id, before, limit } => {
                let args = ConversationArgs {
                    id: id.clone(),
                    before: before.clone(),
                    ..ConversationArgs::default()
                };
                let collected = collections::collected(scope, &args, *limit)?;
                let roots: Vec<&str> = collected.ids.iter().map(String::as_str).collect();
                let threads = closures(scope, &roots)?;
                let mut ids: Vec<&str> = Vec::with_capacity(roots.len());
                let mut parent_of: HashMap<String, String> = HashMap::new();
                for root in &roots {
                    ids.push(root);
                    for reply in threads.get(*root).map_or(&[][..], Vec::as_slice) {
                        ids.push(&reply.id);
                        if let Some(parent) = &reply.parent {
                            parent_of.insert(reply.id.clone(), parent.clone());
                        }
                    }
                }
                let many = plan_many(window, scope, bundle, &ids)?;
                let prepared =
                    prepare_inputs(window, scope, &wanted_of(&many), false, None)?;
                let count = roots.len();
                (
                    Plan::Conversation {
                        conversation: id.clone(),
                        roots: count,
                        limit: *limit,
                        parent_of,
                        many,
                        collected,
                    },
                    prepared,
                )
            }
            ObjectsAsk::Posts { ids } => {
                let ids: Vec<&str> = ids.iter().map(String::as_str).collect();
                let many = plan_many(window, scope, bundle, &ids)?;
                let prepared =
                    prepare_inputs(window, scope, &wanted_of(&many), false, None)?;
                (Plan::Posts { many }, prepared)
            }
            ObjectsAsk::Thread { root } => {
                let found = root_of(scope, root)?;
                let Some(found) = found.root else {
                    let shown =
                        repr(root).ok_or_else(|| python_says("an id to show in other words"))?;
                    return Err(bad_request(format!("not a post: {shown}")));
                };
                if found != *root {
                    return Err(bad_request(format!(
                        "{root} is a version of the post {found}: ask with thread={found}"
                    )));
                }
                let rows = closures(scope, &[root.as_str()])?
                    .remove(root.as_str())
                    .unwrap_or_default();
                let from = rows.len().saturating_sub(THREAD_MAX);
                let kept: &[Reply] = &rows[from..];
                let mut ids: Vec<&str> = vec![root.as_str()];
                ids.extend(kept.iter().map(|row| row.id.as_str()));
                let many = plan_many(window, scope, bundle, &ids)?;
                let prepared =
                    prepare_inputs(window, scope, &wanted_of(&many), false, None)?;
                (
                    Plan::Thread {
                        root: root.clone(),
                        replies: rows.len(),
                        omitted: from,
                        many,
                    },
                    prepared,
                )
            }
            ObjectsAsk::Post { root, version } => {
                let found = root_of(scope, root)?;
                let Some(found) = found.root else {
                    let shown =
                        repr(root).ok_or_else(|| python_says("an id to show in other words"))?;
                    return Err(bad_request(format!("not a post: {shown}")));
                };
                if found != *root {
                    return Err(bad_request(format!(
                        "{root} is a version of the post {found}: ask with \
                         post={found}&version={root}"
                    )));
                }
                let asked = [Id(root.clone())];
                let line = lines_of(scope, &asked)?
                    .remove(&asked[0])
                    .ok_or_else(|| python_says("a post with no line"))?;
                let whereabouts = where_of(scope, root)?;
                let returned = returned_of(scope, &[root.as_str()])?
                    .remove(root.as_str())
                    .unwrap_or_default();
                match plan_listing(
                    window,
                    bundle,
                    root,
                    &line,
                    whereabouts,
                    returned,
                    version.as_deref(),
                ) {
                    Err(unresolved) => (Plan::Unresolved(unresolved), PreparedInputs::default()),
                    Ok(listing) => {
                        let wanted: Vec<&Wanted> = listing.wanted.iter().collect();
                        let prepared = prepare_inputs(window, scope, &wanted, false, None)?;
                        (Plan::Post(Box::new(listing)), prepared)
                    }
                }
            }
            ObjectsAsk::One { address, format } => read_one(window, scope, bundle, address, format)?,
        };
        Ok(ReadAnswer {
            rows: vec![Prepared(ObjectsPlan {
                plan,
                bundle: bundle.clone(),
                prepared,
                at: reads::change_cursor(as_of),
            })],
            as_of,
            more: None,
            not_searched: Vec::new(),
        })
    }
}

fn read_one(
    window: &Window,
    scope: &mut dyn ReadScope,
    bundle: &Bundle,
    address: &str,
    format: &str,
) -> Result<(Plan, PreparedInputs), OpError> {
    let a = parse_address(address)?;
    if !matches!(format, "json" | "md" | "csv") {
        return Err(bad_request("format is json, md or csv".to_owned()));
    }
    let nothing = |unresolved: Unresolved| (Plan::Unresolved(unresolved), PreparedInputs::default());
    let (root, line, version, key, part, is_exact) = match &a {
        Address::Exact { version, part, key } => {
            let found = root_of(scope, version)?;
            let Some(root) = found.root else {
                let why = if found.held {
                    format!("{version} is not a version of any post")
                } else {
                    format!("the record holds no entry {version}")
                };
                return Ok(nothing(unresolved(address, &why, Vec::new())));
            };
            let asked = [Id(root.clone())];
            let line = lines_of(scope, &asked)?
                .remove(&asked[0])
                .ok_or_else(|| python_says("a post with no line"))?;
            if !line.versions.iter().any(|v| v.id == *version) {
                let why = format!("{version} is not a version of the post {root}");
                return Ok(nothing(unresolved(
                    address,
                    &why,
                    vec![("post", Py::str(root.as_str()))],
                )));
            }
            (root, line, version.clone(), key.as_str(), *part, true)
        }
        Address::Live { root: asked_root, key } => {
            let found = root_of(scope, asked_root)?;
            let root = match found.root {
                Some(root) if root == *asked_root => root,
                other => {
                    let why = match other {
                        Some(root) => format!(
                            "{asked_root} is a version, not a post: a live address names the post ({root})"
                        ),
                        None if found.held => format!("{asked_root} is not a post"),
                        None => format!("the record holds no entry {asked_root}"),
                    };
                    return Ok(nothing(unresolved(address, &why, Vec::new())));
                }
            };
            let asked = [Id(root.clone())];
            let line = lines_of(scope, &asked)?
                .remove(&asked[0])
                .ok_or_else(|| python_says("a post with no line"))?;
            let version = line
                .versions
                .last()
                .map_or_else(|| root.clone(), |v| v.id.clone());
            (root, line, version, key.as_str(), None, false)
        }
    };
    if line.deletion.is_some() {
        return Ok(nothing(unresolved(
            address,
            "the post was deleted; its objects are not served",
            vec![("post", Py::str(root.as_str())), ("deleted", Py::Bool(true))],
        )));
    }
    let whereabouts = where_of(scope, &root)?;
    let returned = returned_of(scope, &[root.as_str()])?
        .remove(root.as_str())
        .unwrap_or_default();
    let ids: Vec<String> = line.versions.iter().map(|v| v.id.clone()).collect();
    let entry = line
        .versions
        .iter()
        .find(|v| v.id == version)
        .cloned()
        .ok_or_else(|| python_says("a version that isn't in its line"))?;
    let want = Wanted::new(&root, entry, returned.clone(), bundle, window);
    // `line["versions"][-LOOK_BACK - 1:-1]`, newest first.
    let last = line.versions.len().saturating_sub(1);
    let first = last.saturating_sub(LOOK_BACK);
    let older: Vec<Wanted> = line.versions[first..last]
        .iter()
        .rev()
        .map(|v| Wanted::new(&root, v.clone(), returned.clone(), bundle, window))
        .collect();
    let mut wanted: Vec<&Wanted> = vec![&want];
    if !is_exact {
        wanted.extend(older.iter());
    }
    let prepared = prepare_inputs(window, scope, &wanted, false, Some(key))?;
    let plan = OnePlan {
        address: address.to_owned(),
        form: if is_exact { "exact" } else { "live" },
        key: key.to_owned(),
        part,
        is_exact,
        format: format.to_owned(),
        root,
        version,
        ids,
        whereabouts,
        want,
        older,
    };
    Ok((Plan::One(Box::new(plan)), prepared))
}

impl OnePlan {
    fn finish(
        &self,
        window: &Window,
        bundle: &Bundle,
        prepared: &PreparedInputs,
    ) -> Result<Finished, OpError> {
        let address = self.address.as_str();
        let version = self.version.as_str();
        let root = self.root.as_str();
        let current = self.ids.last().map_or(root, String::as_str);
        let [home, home_name, number] = self.whereabouts.fields();
        let mut out = dict([
            ("address", Py::str(address)),
            ("form", Py::str(self.form)),
            ("post", Py::str(root)),
            ("version", Py::str(version)),
            ("current", Py::Bool(version == current)),
            ("current_version", Py::str(current)),
            home,
            home_name,
            number,
        ]);
        let (extracted, cached) = match fetch(window, bundle, &self.want, prepared)? {
            Outcome::NotRead { why_not, input } => {
                out.set("extracted", Py::Bool(false));
                out.set("why_not", Py::Str(why_not));
                out.set("input", input);
                out.set("resolves", Py::None);
                return Ok(Finished::Answer(out));
            }
            Outcome::Read { extracted, cached } => (extracted, cached),
        };
        let key = self.key.as_str();
        let mut found = None;
        for o in &extracted.objects {
            if !o.is_dict() {
                return Err(python_says("an object that isn't an object"));
            }
            if key_of(o)? == key {
                found = Some(o);
                break;
            }
        }
        let shown_key = || repr(key).ok_or_else(|| python_says("a key to show in other words"));
        let Some(o) = found else {
            if self.is_exact {
                return Ok(unresolved(
                    address,
                    &format!("version {version} of {root} has no object {}", shown_key()?),
                    vec![("post", Py::str(root)), ("version", Py::str(version))],
                )
                .into());
            }
            let mut last_version = Py::None;
            for older in &self.older {
                if let Outcome::Read { extracted, .. } = fetch(window, bundle, older, prepared)? {
                    let mut has = false;
                    for o in &extracted.objects {
                        if key_of(o)? == key {
                            has = true;
                            break;
                        }
                    }
                    if has {
                        last_version = Py::str(older.version.id.as_str());
                        break;
                    }
                }
            }
            return Ok(unresolved(
                address,
                &format!(
                    "no longer resolves: the current version {version} of {root} has no object {}",
                    shown_key()?
                ),
                vec![
                    ("post", Py::str(root)),
                    ("version", Py::str(version)),
                    ("last_version", last_version),
                ],
            )
            .into());
        };
        if self.is_exact {
            let held = match o.get("part") {
                None | Some(Py::None) => None,
                Some(Py::Int(digits)) => Some(
                    digits
                        .parse::<i128>()
                        .map_err(|_| python_says("a part past what this holds"))?,
                ),
                Some(_) => return Err(python_says("a part that isn't a number")),
            };
            if held != self.part {
                let token = |part: Option<i128>| part.map_or("-".to_owned(), |p| p.to_string());
                return Ok(unresolved(
                    address,
                    &format!(
                        "the object {} is in part {} of {version}, not part {}",
                        shown_key()?,
                        token(held),
                        token(self.part)
                    ),
                    vec![("post", Py::str(root)), ("version", Py::str(version))],
                )
                .into());
            }
        }
        let format = self.format.as_str();
        let content = if format == "json" {
            o.get("json").cloned().unwrap_or(Py::None)
        } else {
            let formats = o.get("formats").filter(|found| found.truthy());
            let forms: Vec<&str> = match formats {
                None => Vec::new(),
                Some(Py::List(forms)) => {
                    let mut names = Vec::with_capacity(forms.len());
                    for form in forms {
                        names.push(
                            form.as_str()
                                .ok_or_else(|| python_says("a format that isn't text"))?,
                        );
                    }
                    names
                }
                Some(_) => return Err(python_says("formats that aren't a list")),
            };
            if !forms.contains(&format) {
                return Err(bad_request(format!(
                    "{address} has no {format} form; it has: {}",
                    forms.join(", ")
                )));
            }
            o.get(format).cloned().unwrap_or(Py::None)
        };
        let mut listed = listing(o, root, version)?;
        let kind = o
            .get("kind")
            .ok_or_else(|| python_says("an object with no kind"))?;
        if let Some(reference) = o.get("ref").filter(|found| found.truthy())
            && matches!(kind.as_str(), Some("media" | "figure"))
        {
            let reference = reference
                .as_str()
                .ok_or_else(|| python_says("an object's ref that isn't text"))?;
            let about = window.describe(&prepared.described, reference, Verify::Exists)?;
            if let Some(Py::Dict(artifact)) = listed.get("artifact") {
                let mut artifact = Py::Dict(artifact.clone());
                artifact.set(
                    "state",
                    about.get("state").cloned().unwrap_or(Py::None),
                );
                listed.set("artifact", artifact);
            }
        }
        out.set("extracted", Py::Bool(true));
        out.set("resolves", Py::Bool(true));
        out.set("cached", Py::Bool(cached));
        out.set("object", listed);
        out.set("format", Py::str(format));
        out.set("content", content);
        Ok(Finished::Answer(out))
    }
}

/// `_object_summary`.
fn summary(listing: &Py, obj: &Py, parent_numbers: &HashMap<String, Py>) -> Result<Py, OpError> {
    let or = |names: &[&str], is: Option<&Py>| -> Py {
        for name in names {
            let found = match *name {
                "is.chip" => is.and_then(|is| is.get("chip")),
                "is.word" => is.and_then(|is| is.get("word")),
                other => obj.get(other),
            };
            if let Some(found) = found.filter(|found| found.truthy()) {
                return found.clone();
            }
        }
        // `a or b or c`: the last, whatever it is.
        names
            .last()
            .and_then(|name| obj.get(name))
            .cloned()
            .unwrap_or(Py::None)
    };
    let is = obj.get("is").filter(|is| is.truthy());
    if is.is_some_and(|is| !is.is_dict()) {
        return Err(python_says("an object's `is` that isn't an object"));
    }
    let post = listing
        .get("post")
        .and_then(Py::as_str)
        .ok_or_else(|| python_says("a listing with no post"))?;
    let address = obj
        .get("address")
        .ok_or_else(|| python_says("a listing with no address"))?;
    let of_listing = |name: &str| listing.get(name).cloned().unwrap_or(Py::None);
    Ok(dict([
        ("address", address.get("live").cloned().unwrap_or(Py::None)),
        ("exact", address.get("exact").cloned().unwrap_or(Py::None)),
        ("kind", or(&["is.chip", "is.word", "type", "kind"], is)),
        ("title", or(&["title", "name", "type"], is)),
        ("post", Py::str(post)),
        ("number", of_listing("number")),
        (
            "reply_to_number",
            parent_numbers.get(post).cloned().unwrap_or(Py::None),
        ),
        ("home", of_listing("home")),
        ("preview", obj.clone()),
    ]))
}

impl ObjectsPlan {
    /// What's left: hashing what's held, and extracting what isn't kept. No scope is held.
    pub fn finish(self, window: &Window) -> Result<Finished, OpError> {
        let ObjectsPlan {
            plan,
            bundle,
            prepared,
            at,
        } = self;
        let mut answer = match plan {
            Plan::Unresolved(unresolved) => return Ok(unresolved.into()),
            Plan::Conversation {
                collected,
                roots,
                limit,
                conversation,
                parent_of,
                many,
            } => {
                let listings = finish_many(&many, window, &bundle, &prepared)?;
                let ok = || listings.iter().filter(|x| x.get("error").is_none_or(|e| !e.truthy()));
                let numbers: HashMap<&str, &Py> = ok()
                    .filter_map(|x| {
                        Some((
                            x.get("post")?.as_str()?,
                            x.get("number").unwrap_or(&NOTHING),
                        ))
                    })
                    .collect();
                let parent_numbers: HashMap<String, Py> = parent_of
                    .iter()
                    .map(|(reply, parent)| {
                        (
                            reply.clone(),
                            numbers
                                .get(parent.as_str())
                                .map_or(Py::None, |n| (*n).clone()),
                        )
                    })
                    .collect();
                let mut summaries = Vec::new();
                for listing in ok() {
                    for obj in listing.get("objects").and_then(Py::as_list).unwrap_or(&[]) {
                        let top = matches!(obj.get("parent"), None | Some(Py::None));
                        if top && obj.get("kind").and_then(Py::as_str) != Some("post-text") {
                            summaries.push(summary(listing, obj, &parent_numbers)?);
                        }
                    }
                }
                let posts: Vec<Py> = ok()
                    .map(|x| x.get("post").cloned().unwrap_or(Py::None))
                    .collect();
                dict([
                    ("conversation", Py::Str(conversation)),
                    ("objects", Py::List(summaries)),
                    ("posts", Py::List(posts)),
                    ("before", collected.before.clone()),
                    ("roots", Py::int(roots)),
                    ("total_roots", Py::int(collected.total)),
                    ("limit", Py::int(limit)),
                ])
            }
            Plan::Posts { many } => dict([
                (
                    "posts",
                    Py::List(finish_many(&many, window, &bundle, &prepared)?),
                ),
                ("limit", Py::int(BATCH)),
            ]),
            Plan::Thread {
                root,
                replies,
                omitted,
                many,
            } => dict([
                ("root", Py::Str(root)),
                ("replies", Py::int(replies)),
                ("omitted", Py::int(omitted)),
                (
                    "posts",
                    Py::List(finish_many(&many, window, &bundle, &prepared)?),
                ),
            ]),
            Plan::Post(listing) => listing.finish(window, &bundle, &prepared)?,
            Plan::One(one) => match one.finish(window, &bundle, &prepared)? {
                Finished::Answer(answer) => answer,
                other => return Ok(other),
            },
        };
        answer.set("cursor", at);
        Ok(Finished::Answer(answer))
    }
}

static NOTHING: Py = Py::None;

#[cfg(test)]
mod tests {
    use super::*;

    fn object(text: &str) -> Py {
        pyjson::loads(text).unwrap()
    }

    #[test]
    fn a_chip_is_the_registry_s_word_when_there_is_one() {
        assert_eq!(
            chip_kind(&object(r#"{"is": {"chip": "chart"}, "kind": "block"}"#)).unwrap(),
            Some("chart".to_owned())
        );
        assert_eq!(
            chip_kind(&object(r#"{"is": {"chip": null}, "kind": "block"}"#)).unwrap(),
            None
        );
    }

    #[test]
    fn with_no_registry_the_rule_written_out_gives_the_same_words() {
        for (given, kind) in [
            (r#"{"kind": "block", "type": "pad"}"#, Some("note")),
            (r#"{"kind": "block", "type": "Chart"}"#, Some("chart")),
            (r#"{"kind": "block"}"#, Some("block")),
            (r#"{"kind": "post-text"}"#, None),
            (r#"{"kind": "block", "parent": "x"}"#, None),
            (r#"{"kind": "figure"}"#, Some("image")),
            (r#"{"kind": "media", "media_type": "image/png"}"#, Some("image")),
            (r#"{"kind": "media", "title": "a.PNG"}"#, Some("image")),
            (r#"{"kind": "media", "media_type": "text/plain"}"#, Some("doc")),
            (r#"{"kind": "media", "media_type": "text/html"}"#, Some("file")),
            (r#"{"kind": "media", "media_type": "application/ld+json"}"#, Some("doc")),
            (r#"{"kind": "media", "title": "x.rs"}"#, Some("doc")),
            (r#"{"kind": "media", "title": "x.bin"}"#, Some("file")),
        ] {
            assert_eq!(
                chip_kind(&object(given)).unwrap().as_deref(),
                kind,
                "{given}"
            );
        }
    }

    #[test]
    fn an_address_is_exactly_one_of_two_forms() {
        assert!(matches!(
            parse_address("exact:ent-1:2:a:b").unwrap(),
            Address::Exact { part: Some(2), key, .. } if key == "a:b"
        ));
        assert!(matches!(
            parse_address("exact:ent-1:-:k").unwrap(),
            Address::Exact { part: None, .. }
        ));
        assert!(matches!(
            parse_address("live:ent-1:a:b").unwrap(),
            Address::Live { key, .. } if key == "a:b"
        ));
        for bad in ["", "x", "exact:", "exact:a:b:c", "exact:a:1:", "live:a", "live::k"] {
            let got = parse_address(bad);
            assert!(
                matches!(got, Err(OpError::BadRequest { .. })),
                "{bad:?}"
            );
        }
        assert_eq!(
            parse_address("x").err().unwrap(),
            OpError::BadRequest {
                why: "not an object address: 'x' -- an address is exact:<version>:<part>:<key> or live:<root>:<key>".to_owned()
            }
        );
    }

    #[test]
    fn a_listing_says_what_and_where_and_never_the_content() {
        let o = object(
            r#"{"key": "k", "part": 1, "kind": "media", "ref": "adm-1", "json": {"secret": 1},
                "identity": "declared", "media_type": "image/png"}"#,
        );
        let listed = listing(&o, "ent-r", "ent-v").unwrap().dumps();
        assert!(!listed.contains("secret"));
        assert!(listed.contains(r#""exact": "exact:ent-v:1:k""#), "{listed}");
        assert!(listed.contains(r#""live": "live:ent-r:k""#), "{listed}");
        assert!(listed.contains(r#""declared": true"#), "{listed}");
        assert!(
            listed.contains(r#""artifact": {"ref": "adm-1", "url": "/api/artifacts/adm-1"}"#),
            "{listed}"
        );
    }

    #[test]
    fn a_long_post_is_measured_in_python_s_characters() {
        let input = object(r#"{"parts": [{"text": "é😀"}, "skip", {"text": null}, {"text": [1, 2]}]}"#);
        assert_eq!(text_size(&input).unwrap(), 4);
    }
}
