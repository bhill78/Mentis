//! `POST /fluid/api/magnets/<id>/activate`: the front's half of a Magnet's manual activation. Contract:
//! `docs/magnets/M1-contract.md`, "Manual activation", whose fixtures are
//! `tests/fixtures/magnet-conformance/activation/`.
//!
//! **Rust owns the door, the read and the artifact's bytes, and never writes the Brain.** Everything the
//! body means, the definition, every semantic refusal and every record write are Python's, over the two
//! `/private/magnets/<id>/activate/*` paths. Each is one connection, as `forward.rs` says why, and nothing
//! here retries or queues: the next request simply tries again.
//!
//! **What may have happened decides the answer.** Before the first byte of a commit nothing can have been
//! written, so anything going wrong says so plainly. From that byte on, a whole and well-formed answer is
//! the only thing that says what happened, and anything else is `OutcomeUnknown`.

use std::net::SocketAddr;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use mentis_ops::magnet::{MagnetDefinition, NotADefinition};
use mentis_ops::pyjson::{self, Py, dict};
use mentis_ops::{OpError, RecordError};
use sha2::{Digest, Sha256};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::net::tcp::ReadHalf;

use super::answers::{self, Written};
use super::connection::until_it_leaves;
use super::door::read_body;
use super::forward::{answer_head_end, read_answer_head};
use super::head::Head;
use super::{Shared, say};
use crate::handlers::magnet::activation_page;
use crate::launch::SECRET_HEADER;

/// Its name in a route table and in [`crate::HANDLERS`].
pub const HANDLER: &str = "magnet-activate";
/// `request.identity.route`.
pub const IDENTITY_ROUTE: &str = "fluid-magnet-activate";
/// Wire bytes of the public body.
pub const PUBLIC_BODY_MOST: u64 = 65_536;
/// Exact bytes of a definition.
pub const DEFINITION_MOST: usize = 262_144;
/// Wire bytes of a private answer's body.
pub const PRIVATE_ANSWER_MOST: u64 = 1_048_576;
/// Exact bytes of an artifact.
pub const ARTIFACT_MOST: usize = 26_214_400;
/// A preflight, connecting through its whole answer.
pub const PREFLIGHT_WITHIN: Duration = Duration::from_secs(2);
/// A commit, from its first byte through its whole answer. Its connection has this much again.
pub const COMMIT_WITHIN: Duration = Duration::from_secs(5);
/// The private protocol's version.
const PROTOCOL: &str = "1";
/// The longest head of a private answer read before calling it no answer of this protocol's.
const ANSWER_HEAD_MOST: usize = 64 * 1024;
/// How long the last check gives a client's leaving to be seen, and all a commit waits for it.
const LAST_LOOK: Duration = Duration::from_millis(1);
const ARTIFACT_HEADER: &str = "X-Mentis-Artifact-SHA256";

/// How a request this door took ended.
pub(super) enum Ended {
    Answered(Written),
    ClientGone,
}

/// The Magnet's segment of an activation's path, raw: a malformed one is Python's to refuse. A `#` is the
/// one thing in a segment that Python's `urlparse` would read as something else, so it isn't this route.
pub fn segment(path: &str) -> Option<&str> {
    let segment = path
        .strip_prefix("/fluid/api/magnets/")?
        .strip_suffix("/activate")?;
    (!segment.is_empty() && !segment.contains(['/', '#'])).then_some(segment)
}

/// Rows 6 and 7 of the door, once its first five have passed: a body of the wrong type, then one over the
/// limit, by the number its length spells. Nothing has been read of it.
pub(super) fn body_refused(head: &Head) -> Option<Written> {
    let length = head.content_length();
    if length == 0 {
        return None;
    }
    let content_type = head.get("Content-Type").unwrap_or("");
    let content_type = content_type.split(';').next().unwrap_or("");
    let is_json = content_type
        .trim_matches(|c: char| c.is_ascii_whitespace())
        .eq_ignore_ascii_case("application/json");
    if !is_json {
        return Some(answers::send_json(
            415,
            &answers::json_object(&[
                ("error", "a JSON route takes Content-Type: application/json"),
                ("kind", "PermissionError"),
            ]),
            false,
            true,
        ));
    }
    (length > PUBLIC_BODY_MOST).then(|| {
        let body = public_body_too_large();
        answers::send_json(413, &body.dumps(), false, true)
    })
}

/// One of Rust's refusals: its status and its whole body. `refusals.json` has them, and the magnet in
/// each is the raw segment asked about.
pub type Said = (u16, Py);

fn reason(code: &str, words: &str, retryable: bool) -> Py {
    dict([
        ("code", Py::str(code)),
        ("message", Py::str(words)),
        ("retryable", Py::Bool(retryable)),
    ])
}

/// The neighbouring shape of a refusal about what runs, with `kind` where it has one.
fn refusal(magnet: &str, kind: Option<&str>, code: &str, words: &str, retryable: bool) -> Py {
    let mut body = dict([("error", Py::str(words))]);
    if let Some(kind) = kind {
        body.set("kind", Py::str(kind));
    }
    body.set("refused", Py::Bool(true));
    body.set("magnet", Py::str(magnet));
    body.set("reason", reason(code, words, retryable));
    body
}

pub fn public_body_too_large() -> Py {
    dict([
        (
            "error",
            Py::str(
                "this request's body is over the 65,536 bytes an activation takes, so nothing was \
                 read or recorded",
            ),
        ),
        ("kind", Py::str("ContentTooLarge")),
        ("limit", Py::int(PUBLIC_BODY_MOST)),
    ])
}

pub fn busy(magnet: &str) -> Said {
    let words = "another activation holds the one place, so nothing was recorded. Ask again";
    (503, refusal(magnet, Some("Busy"), "busy", words, true))
}

pub fn preflight_interrupted(magnet: &str) -> Said {
    let words =
        "this activation could not be prepared in time, so nothing was read or recorded. Ask again";
    let code = "preflight-interrupted";
    (503, refusal(magnet, Some("Busy"), code, words, true))
}

pub fn sources_busy(magnet: &str) -> Said {
    let words = "no source produced a useful result and at least one was busy, so nothing was \
                 recorded. Ask again";
    (
        503,
        refusal(magnet, Some("Busy"), "sources-busy", words, true),
    )
}

pub fn no_readable_source(magnet: &str) -> Said {
    let words = "no source produced a useful result: none could be read, or what could be read gave \
                 no results. Nothing was recorded";
    (
        422,
        refusal(magnet, None, "no-readable-source", words, false),
    )
}

pub fn artifact_too_large(magnet: &str) -> Said {
    let words =
        "this activation's page is over the 25 MiB an artifact may be, so nothing was recorded";
    let code = "artifact-too-large";
    (
        413,
        refusal(magnet, Some("ContentTooLarge"), code, words, false),
    )
}

pub fn internal_protocol_error(magnet: &str) -> Said {
    let words = "this server's two halves disagree about this activation, and nothing was written. It \
                 is a defect to report, not a configuration to change";
    let body = dict([
        ("error", Py::str(words)),
        ("kind", Py::str("InternalProtocolError")),
        ("magnet", Py::str(magnet)),
        ("reason", reason("internal-protocol-error", words, false)),
    ]);
    (502, body)
}

pub fn outcome_unknown(magnet: &str, op: &str) -> Said {
    let words = "this activation may or may not have been recorded. Retry with the same operation key \
                 to find out; a new key may record a second activation";
    let body = dict([
        ("error", Py::str(words)),
        ("kind", Py::str("OutcomeUnknown")),
        ("magnet", Py::str(magnet)),
        ("op", Py::str(op)),
        ("reason", reason("outcome-unknown", words, true)),
    ]);
    (503, body)
}

/// What one exchange with Python's private port came to, before anybody reads what it said.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Exchange {
    /// A whole answer, however it is spelt inside.
    Whole { status: u16, body: Vec<u8> },
    /// Whole enough to say it is no answer of this protocol's: over 1 MiB, or not framed by a length.
    NoAnswer,
    /// Timeout, reset, disconnect, a truncated answer, or no connection at all.
    Interrupted,
}

/// What a `ready` holds, which goes on to the read and into the artifact as it came.
#[derive(Clone, Debug)]
pub struct Ready {
    pub author: String,
    pub op: String,
    pub sha256: String,
    pub raw: String,
    pub value: Py,
    /// The one operation's `name`, and `options` as the definition says them.
    pub name: Py,
    pub options: Py,
    /// `MagnetDefinition::parse` of `raw`, and nothing else's reading of it.
    pub magnet: MagnetDefinition,
}

/// What a preflight decides.
#[derive(Debug)]
pub enum Preflight {
    Ready(Box<Ready>),
    /// A public answer, as Python said it or as `said` makes it.
    Says(Said),
}

/// What a commit decides. `OutcomeUnknown` is one of these: there's no other way for it to end.
pub type Commit = Said;

pub fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// Standard base64 with padding.
pub fn base64(bytes: &[u8]) -> String {
    const LETTERS: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for three in bytes.chunks(3) {
        let at = |i: usize| three.get(i).copied().unwrap_or(0);
        let word = u32::from(at(0)) << 16 | u32::from(at(1)) << 8 | u32::from(at(2));
        for place in 0..4 {
            if place <= three.len() {
                let index = (word >> (18 - 6 * place)) & 63;
                out.push(char::from(LETTERS[index as usize]));
            } else {
                out.push('=');
            }
        }
    }
    out
}

/// A preflight's bytes: the exact public body, whatever it holds.
pub fn preflight_body(magnet: &str, public_body: &[u8]) -> String {
    dict([
        ("protocol", Py::int(PROTOCOL)),
        ("magnet", Py::str(magnet)),
        ("public_body_base64", Py::Str(base64(public_body))),
    ])
    .dumps()
}

fn has_exactly(value: &Py, names: &[&str]) -> bool {
    match value {
        Py::Dict(items) => {
            items.len() == names.len() && names.iter().all(|name| value.get(name).is_some())
        }
        _ => false,
    }
}

fn identity_of(magnet: &str) -> Py {
    dict([
        ("route", Py::str(IDENTITY_ROUTE)),
        ("magnet", Py::str(magnet)),
    ])
}

fn int_is(value: Option<&Py>, want: &str) -> bool {
    matches!(value, Some(Py::Int(digits)) if digits == want)
}

fn status_of(value: Option<&Py>) -> Option<u16> {
    match value {
        Some(Py::Int(digits)) => digits.parse().ok(),
        _ => None,
    }
}

fn is_identity(value: Option<&Py>) -> bool {
    matches!(value, Some(Py::None | Py::Str(_)))
}

/// An answer, as far as `protocol`, `magnet` and being an object go. `None` is no answer.
fn read_answer(body: &[u8], asked: &str) -> Option<Py> {
    let answer = pyjson::loads(std::str::from_utf8(body).ok()?)?;
    let fits = answer.is_dict()
        && int_is(answer.get("protocol"), PROTOCOL)
        && answer.get("magnet").and_then(Py::as_str) == Some(asked);
    fits.then_some(answer)
}

/// `refused`, `internal-protocol-error`, `committed` and `replay`, in the same envelope: which fields
/// their state has, the state against its status and body, and the body's shape. The public answer.
fn enveloped(answer: &Py, state: &str, asked: &str, refused_statuses: &[u16]) -> Option<Said> {
    const ENVELOPE: &[&str] = &[
        "protocol", "state", "magnet", "author", "op", "status", "body",
    ];
    if !has_exactly(answer, ENVELOPE)
        || !is_identity(answer.get("author"))
        || !is_identity(answer.get("op"))
    {
        return None;
    }
    let status = status_of(answer.get("status"))?;
    let body = answer.get("body").filter(|body| body.is_dict())?;
    let error_is_text = match body.get("error") {
        None => true,
        Some(error) => error.as_str().is_some(),
    };
    if !error_is_text {
        return None;
    }
    let said = match state {
        "refused" => refused_statuses.contains(&status) && body.get("error").is_some(),
        "internal-protocol-error" => status == 502 && body.get("error").is_some(),
        "committed" | "replay" => {
            let (want_status, want_replayed) = if state == "committed" {
                (201, false)
            } else {
                (200, true)
            };
            status == want_status
                && body.get("replayed") == Some(&Py::Bool(want_replayed))
                && body.get("magnet").and_then(Py::as_str) == Some(asked)
                && body.get("cursor").and_then(Py::as_str).is_some()
                && answer.get("author").and_then(Py::as_str).is_some()
                && answer.get("op").and_then(Py::as_str).is_some()
        }
        _ => false,
    };
    said.then(|| (status, body.clone()))
}

/// A `ready`, if that's what this is. Its definition is parsed from `raw`: refusing what Python approved
/// is a disagreement between implementations, not configuration.
fn ready_of(answer: &Py, asked: &str) -> Option<Ready> {
    if !has_exactly(
        answer,
        &["protocol", "state", "magnet", "request", "definition"],
    ) {
        return None;
    }
    let request = answer.get("request")?;
    if !has_exactly(request, &["author", "op", "identity"])
        || request.get("identity") != Some(&identity_of(asked))
    {
        return None;
    }
    let definition = answer.get("definition")?;
    if !has_exactly(definition, &["sha256", "raw", "value"]) {
        return None;
    }
    let raw = definition.get("raw")?.as_str()?;
    let sha256 = definition.get("sha256")?.as_str()?;
    if raw.len() > DEFINITION_MOST || sha256_hex(raw.as_bytes()) != sha256 {
        return None;
    }
    let value = definition.get("value").filter(|value| value.is_dict())?;
    let magnet = match MagnetDefinition::parse(asked, raw) {
        Ok(magnet) => magnet,
        Err(NotADefinition::Malformed(_) | NotADefinition::LaterSchema(_)) => return None,
    };
    // What Python approved is one `extract`, and the artifact has to say so from the checked value.
    let operations = value.get("processing")?.get("operations")?.as_list()?;
    let [operation] = operations else {
        return None;
    };
    if operation.get("op").and_then(Py::as_str) != Some("extract") {
        return None;
    }
    let options = operation
        .get("options")
        .cloned()
        .unwrap_or_else(|| Py::Dict(Vec::new()));
    Some(Ready {
        author: request.get("author")?.as_str()?.to_owned(),
        op: request.get("op")?.as_str()?.to_owned(),
        sha256: sha256.to_owned(),
        raw: raw.to_owned(),
        value: value.clone(),
        name: operation.get("name").cloned().unwrap_or(Py::None),
        options,
        magnet,
    })
}

/// A preflight's statuses that say something. `answers.json`'s `refused_statuses`.
const PREFLIGHT_REFUSES: &[u16] = &[400, 404, 409, 422, 503];
const COMMIT_REFUSES: &[u16] = &[413, 422, 503];

/// What Rust makes of a preflight. It has nothing to compare an identity with: it doesn't read the body.
pub fn preflight_decides(asked: &str, exchange: &Exchange) -> Preflight {
    let disagree = || Preflight::Says(internal_protocol_error(asked));
    let body = match exchange {
        Exchange::Interrupted => return Preflight::Says(preflight_interrupted(asked)),
        Exchange::NoAnswer => return disagree(),
        Exchange::Whole { status: 200, body } => body,
        Exchange::Whole { .. } => return disagree(),
    };
    let Some(answer) = read_answer(body, asked) else {
        return disagree();
    };
    match answer.get("state").and_then(Py::as_str) {
        Some("ready") => ready_of(&answer, asked)
            .map_or_else(disagree, |ready| Preflight::Ready(Box::new(ready))),
        Some(state @ ("refused" | "internal-protocol-error" | "replay")) => {
            enveloped(&answer, state, asked, PREFLIGHT_REFUSES)
                .map_or_else(disagree, Preflight::Says)
        }
        _ => disagree(),
    }
}

/// What Rust makes of a commit, holding the `ready` it came from. Everything but a whole, well-formed
/// answer for this request is `OutcomeUnknown`: only that says what happened.
pub fn commit_decides(asked: &str, held: &Ready, exchange: &Exchange) -> Commit {
    let unknown = || outcome_unknown(asked, &held.op);
    let Exchange::Whole { status: 200, body } = exchange else {
        return unknown();
    };
    let Some(answer) = read_answer(body, asked) else {
        return unknown();
    };
    let state = answer.get("state").and_then(Py::as_str);
    let Some(state @ ("refused" | "internal-protocol-error" | "committed" | "replay")) = state
    else {
        return unknown();
    };
    let Some(said) = enveloped(&answer, state, asked, COMMIT_REFUSES) else {
        return unknown();
    };
    let names_another = |field: &str, held: &str| {
        answer
            .get(field)
            .and_then(Py::as_str)
            .is_some_and(|named| named != held)
    };
    if names_another("author", &held.author) || names_another("op", &held.op) {
        return unknown();
    }
    said
}

/// What a page comes to, by its sources alone.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PageSays {
    Complete,
    Partial,
    SourcesBusy,
    NoReadableSource,
}

/// The useful-source rule. A source is useful only if it contributes a result.
pub fn page_says(page: &Py) -> PageSays {
    let sources = page.get("sources").and_then(Py::as_list).unwrap_or(&[]);
    fn says(source: &Py) -> &str {
        source.get("status").and_then(Py::as_str).unwrap_or("")
    }
    let useful = sources.iter().any(|source| {
        source
            .get("results")
            .and_then(Py::as_list)
            .is_some_and(|results| !results.is_empty())
    });
    if !useful {
        return if sources.iter().any(|source| says(source) == "busy") {
            PageSays::SourcesBusy
        } else {
            PageSays::NoReadableSource
        };
    }
    let kept = page.get("kept").and_then(Py::as_list).unwrap_or(&[]);
    if kept.is_empty() && sources.iter().all(|source| says(source) == "ok") {
        PageSays::Complete
    } else {
        PageSays::Partial
    }
}

/// An artifact's exact bytes: `json.dumps(artifact)`'s default form, members in the contract's order.
pub fn artifact(asked: &str, ready: &Ready, page: Py) -> String {
    dict([
        ("format", Py::str("mentis.magnet-extract")),
        ("version", Py::int(1)),
        ("mode", Py::str("m1-page")),
        ("magnet", Py::str(asked)),
        (
            "request",
            dict([
                ("author", Py::str(ready.author.as_str())),
                ("op", Py::str(ready.op.as_str())),
                ("identity", identity_of(asked)),
            ]),
        ),
        (
            "definition",
            dict([
                ("sha256", Py::str(ready.sha256.as_str())),
                ("raw", Py::str(ready.raw.as_str())),
                ("value", ready.value.clone()),
            ]),
        ),
        (
            "operation",
            dict([
                ("index", Py::int(0)),
                ("op", Py::str("extract")),
                ("mode", Py::str("m1-page")),
                ("name", ready.name.clone()),
                ("options", ready.options.clone()),
            ]),
        ),
        ("page", page),
    ])
    .dumps()
}

/// A private request's head. Its text is Latin-1, as the segment came: Python decodes a request line so.
fn private_head(
    upstream: SocketAddr,
    secret: &str,
    path: &str,
    extra: &str,
    length: usize,
) -> Vec<u8> {
    format!(
        "POST {path} HTTP/1.1\r\nHost: {upstream}\r\n{SECRET_HEADER}: {secret}\r\nContent-Type: \
         application/json\r\n{extra}Content-Length: {length}\r\nConnection: close\r\n\r\n"
    )
    .chars()
    .map(|c| u8::try_from(u32::from(c)).unwrap_or(b'?'))
    .collect()
}

/// Up to the end of one answer, keeping at most what the bounds allow.
async fn read_whole(python: &mut ReadHalf<'_>) -> Exchange {
    let mut held = Vec::with_capacity(4096);
    let mut chunk = [0; 16 * 1024];
    let head_end = loop {
        if let Some(end) = answer_head_end(&held) {
            break end;
        }
        if held.len() > ANSWER_HEAD_MOST {
            return Exchange::NoAnswer;
        }
        match python.read(&mut chunk).await {
            Ok(0) | Err(_) => return Exchange::Interrupted,
            Ok(got) => held.extend_from_slice(&chunk[..got]),
        }
    };
    let Some(head) = read_answer_head(&held[..head_end]) else {
        return Exchange::NoAnswer;
    };
    let length = match head.content_length {
        Some(length)
            if !head.other_framing
                && length <= PRIVATE_ANSWER_MOST
                && !(100..200).contains(&head.status) =>
        {
            length as usize
        }
        _ => return Exchange::NoAnswer,
    };
    while held.len() < head_end + length {
        match python.read(&mut chunk).await {
            Ok(0) | Err(_) => return Exchange::Interrupted,
            Ok(got) => held.extend_from_slice(&chunk[..got]),
        }
    }
    Exchange::Whole {
        status: head.status,
        body: held[head_end..head_end + length].to_vec(),
    }
}

/// Sends and reads at once: Python may answer before it has read everything, and a whole answer then
/// decides however far the sending got. Not being able to send only means an answer may still come.
async fn send_and_read(python: &mut TcpStream, head: &[u8], body: &[u8]) -> Exchange {
    let _ = python.set_nodelay(true);
    let (mut from_python, mut to_python) = python.split();
    let sending = async {
        let _ = to_python.write_all(head).await;
        let _ = to_python.write_all(body).await;
    };
    let reading = read_whole(&mut from_python);
    tokio::pin!(sending, reading);
    let mut sent = false;
    loop {
        tokio::select! {
            answer = &mut reading => return answer,
            () = &mut sending, if !sent => sent = true,
        }
    }
}

async fn preflight(upstream: SocketAddr, secret: &str, magnet: &str, body: &[u8]) -> Exchange {
    let path = format!("/private/magnets/{magnet}/activate/preflight");
    let wire = preflight_body(magnet, body);
    let head = private_head(upstream, secret, &path, "", wire.len());
    let exchange = async {
        let Ok(mut python) = TcpStream::connect(upstream).await else {
            return Exchange::Interrupted;
        };
        send_and_read(&mut python, &head, wire.as_bytes()).await
    };
    tokio::time::timeout(PREFLIGHT_WITHIN, exchange)
        .await
        .unwrap_or(Exchange::Interrupted)
}

/// Whether the client has gone: the end of its stream, or its socket failing. Bytes sent ahead mean it
/// is still there, and stay for the next request.
pub async fn has_left(client: &TcpStream) -> bool {
    let mut byte = [0; 1];
    match tokio::time::timeout(LAST_LOOK, client.peek(&mut byte)).await {
        Ok(Ok(got)) => got == 0,
        Ok(Err(_)) => true,
        Err(_) => false,
    }
}

/// What a whole page comes to: the artifact to commit and its digest, or the refusal that needs no
/// commit. A refusal writes nothing.
pub fn materialized(asked: &str, ready: &Ready, page: Py) -> Result<(String, String), Said> {
    match page_says(&page) {
        PageSays::SourcesBusy => return Err(sources_busy(asked)),
        PageSays::NoReadableSource => return Err(no_readable_source(asked)),
        PageSays::Complete | PageSays::Partial => {}
    }
    let bytes = artifact(asked, ready, page);
    if bytes.len() > ARTIFACT_MOST {
        return Err(artifact_too_large(asked));
    }
    let sha256 = sha256_hex(bytes.as_bytes());
    Ok((bytes, sha256))
}

/// The read and the artifact, off the connection's thread: both can take a moment.
fn read_and_serialize(
    context: &crate::handlers::Context,
    asked: &str,
    ready: &Ready,
    gone: &Arc<AtomicBool>,
) -> Result<(String, String), Said> {
    match activation_page(context, ready.magnet.clone(), gone) {
        Ok(page) => materialized(asked, ready, page),
        // No place in the class, or its time gone: every source is busy, and asking again may find one.
        Err(OpError::Busy { .. } | OpError::Record(RecordError::ScopeExpired)) => {
            Err(sources_busy(asked))
        }
        // Nothing of it could be read, and nothing says that asking again would help.
        Err(error) => {
            say(&format!("activating {asked}: {error}"));
            Err(no_readable_source(asked))
        }
    }
}

/// Past the door, with a body it hasn't read yet. The Magnet's place is taken only once preflight says
/// there's something to do, so a replay never waits on it, and two preflights may both be done.
pub(super) async fn activate(
    client: &mut TcpStream,
    head: &Head,
    magnet: &str,
    buffer: &mut Vec<u8>,
    still_unread: &mut bool,
    shared: &Shared,
    client_closes: bool,
) -> Ended {
    let length = head.content_length() as usize;
    if !read_body(client, buffer, length).await {
        return Ended::ClientGone;
    }
    let public_body: Vec<u8> = buffer.drain(..length).collect();
    *still_unread = false;

    let answered = |(status, body): Said| {
        Ended::Answered(answers::send_json(
            status,
            &body.dumps(),
            false,
            client_closes,
        ))
    };
    let (upstream, secret) = (shared.upstream, shared.secret.as_str());
    let exchange = preflight(upstream, secret, magnet, &public_body).await;
    let ready = match preflight_decides(magnet, &exchange) {
        Preflight::Says(said) => return answered(said),
        Preflight::Ready(ready) => Arc::new(*ready),
    };
    let Ok(_place) = shared.activating.try_acquire() else {
        return answered(busy(magnet));
    };

    let gone = Arc::new(AtomicBool::new(false));
    let task = {
        let (context, asked, ready, gone) = (
            shared.context.clone(),
            magnet.to_owned(),
            ready.clone(),
            gone.clone(),
        );
        tokio::task::spawn_blocking(move || read_and_serialize(&context, &asked, &ready, &gone))
    };
    let read = until_it_leaves(client, task, &gone).await;
    if gone.load(Ordering::Relaxed) {
        return Ended::ClientGone;
    }
    let (bytes, sha256) = match read {
        Ok(Ok(artifact)) => artifact,
        Ok(Err(said)) => return answered(said),
        // Nothing was sent: a defect here, and nothing was written.
        Err(panicked) => {
            say(&format!("activating {magnet} panicked: {panicked}"));
            return answered(internal_protocol_error(magnet));
        }
    };

    let unknown = || answered(outcome_unknown(magnet, &ready.op));
    let connecting = tokio::time::timeout(COMMIT_WITHIN, TcpStream::connect(upstream));
    let Ok(Ok(mut python)) = connecting.await else {
        return unknown();
    };
    // The last point a client leaving means nothing is written: `until_it_leaves` stopped looking.
    if has_left(client).await {
        return Ended::ClientGone;
    }
    let path = format!("/private/magnets/{magnet}/activate/commit");
    let extra = format!("{ARTIFACT_HEADER}: {sha256}\r\n");
    let commit_head = private_head(upstream, secret, &path, &extra, bytes.len());
    let sending = send_and_read(&mut python, &commit_head, bytes.as_bytes());
    let exchange = tokio::time::timeout(COMMIT_WITHIN, sending)
        .await
        .unwrap_or(Exchange::Interrupted);
    answered(commit_decides(magnet, &ready, &exchange))
}

#[cfg(test)]
mod tests {
    use tokio::net::TcpListener;

    use super::*;

    async fn pair() -> (TcpStream, TcpStream) {
        let listening = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let at = listening.local_addr().unwrap();
        let (accepted, there) = tokio::join!(listening.accept(), TcpStream::connect(at));
        (accepted.unwrap().0, there.unwrap())
    }

    #[test]
    fn base64_is_the_standard_one_with_padding() {
        for (bytes, text) in [
            (&b""[..], ""),
            (b"f", "Zg=="),
            (b"fo", "Zm8="),
            (b"foo", "Zm9v"),
            (b"foob", "Zm9vYg=="),
            (b"\xff\xfe\xfd", "//79"),
        ] {
            assert_eq!(base64(bytes), text);
        }
    }

    #[test]
    fn only_one_spelling_of_the_path_is_this_route() {
        for (path, segment_) in [
            ("/fluid/api/magnets/mag-a/activate", Some("mag-a")),
            ("/fluid/api/magnets/mag-bad!/activate", Some("mag-bad!")),
            ("/fluid/api/magnets/mag-a%2fb/activate", Some("mag-a%2fb")),
            ("/fluid/api/magnets/mag-a;b/activate", Some("mag-a;b")),
            ("/fluid/api/magnets/mag-a#b/activate", None),
            ("/fluid/api/magnets//activate", None),
            ("/fluid/api/magnets/a/b/activate", None),
            ("/fluid/api/magnets/mag-a/activate/", None),
            ("/fluid/api/magnets/mag-a/read", None),
        ] {
            assert_eq!(segment(path), segment_, "{path}");
        }
    }

    #[tokio::test]
    async fn a_client_that_has_gone_is_seen_and_one_still_there_is_not_taken_for_it() {
        let (here, mut there) = pair().await;
        assert!(!has_left(&here).await);
        there.write_all(b"GET").await.unwrap();
        tokio::time::sleep(Duration::from_millis(50)).await;
        assert!(!has_left(&here).await, "bytes sent ahead");
        let mut seen = [0; 3];
        here.peek(&mut seen).await.unwrap();
        assert_eq!(&seen, b"GET");

        let (here, there) = pair().await;
        drop(there);
        tokio::time::sleep(Duration::from_millis(50)).await;
        assert!(has_left(&here).await);
    }
}
