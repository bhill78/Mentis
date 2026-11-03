//! `POST /api/worker`, for the reads Rust owns. `docs/rust/R3-mirror.md`, section 5, in Python's order.
//!
//! **Every case that isn't "answer" sends the request on byte for byte,** and what is checked here is
//! never carried into Python: it checks a forwarded request again in full. Rust never refuses for a
//! mirror reason and never serves one. The two 403s here are the words Python would give for a grant
//! the mirror holds.

use std::time::{SystemTime, UNIX_EPOCH};

use mentis_ops::rules::permitted as rules;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use tokio::io::AsyncReadExt;
use tokio::net::TcpStream;

use super::answers::{self, Written};
use super::checks;
use super::grants::{BODY_LOOK, Granted, Serve};
use super::head::Head;
use super::held::{BrainFile, ProcessWatch};
use super::probe;
use super::tail::{self, OnFiles, Refused, SEND_BOUND, Tailed};
use super::{Shared, say};
use crate::object_worker_reads;
use crate::worker_reads::{self, MOVED, Read};

/// What was decided about one request.
pub(super) enum Door {
    /// To Python, for this reason. Any body read is still in the buffer.
    Forward(&'static str),
    /// The whole answer has been handed to the socket.
    Answered { closes: bool },
    /// The client went while being answered.
    ClientGone,
    /// Past `SEND_BOUND`. The caller closes the socket, then drops this.
    Aborted(Box<AbortedHold>),
}

/// What an abort still holds until the socket has been closed.
pub(super) struct AbortedHold {
    pub hold: Option<tail::Held>,
    pub id: u64,
}

/// The framing a body has to have for this door to read it. Otherwise it isn't read at all.
fn body_length(head: &Head, target: &str) -> Option<usize> {
    if target.contains('?')
        || head.get("Expect").is_some()
        || head.get("Transfer-Encoding").is_some()
        || head.refusal.is_some()
        || !head.has_value("Content-Length")
    {
        return None;
    }
    let length = head.content_length();
    (length > 0 && length <= BODY_LOOK).then_some(length as usize)
}

/// Reads to the end of a declared body. Nothing is taken out of `buffer`.
pub(super) async fn read_body(client: &mut TcpStream, buffer: &mut Vec<u8>, length: usize) -> bool {
    let mut chunk = [0; 16 * 1024];
    while buffer.len() < length {
        match client.read(&mut chunk).await {
            Ok(0) | Err(_) => return false,
            Ok(got) => buffer.extend_from_slice(&chunk[..got]),
        }
    }
    true
}

/// A read this door might answer.
struct Asked {
    /// What the mirror knows the grant by: the token's SHA-256.
    key: String,
    op: String,
    args: Map<String, Value>,
    /// The `corpus` the request names, if it names one.
    corpus: Option<String>,
}

/// What a request asks, or why this isn't a read this door answers. Order is Python's, up to the
/// mirror. `serde_json` accepts strictly less than `json.loads`, and what it refuses forwards.
fn asked(head: &Head, shared: &Shared, body: &[u8]) -> Result<Asked, &'static str> {
    if !checks::host_allowed(head.get("Host"), &shared.allowed_hosts) {
        return Err("host");
    }
    let presented = head.get(checks::GRANT_HEADER).unwrap_or("");
    if presented.is_empty() {
        return Err("no grant");
    }
    let content_type = head.get("Content-Type").unwrap_or("");
    let content_type = content_type.split(';').next().unwrap_or("");
    if !content_type
        .trim_matches(|c: char| c.is_ascii_whitespace())
        .eq_ignore_ascii_case("application/json")
    {
        return Err("content type");
    }
    let Ok(Value::Object(mut payload)) = serde_json::from_slice::<Value>(body) else {
        return Err("json");
    };
    let op = match payload.get("op") {
        Some(Value::String(op))
            if MOVED.contains(&op.as_str())
                || object_worker_reads::MOVED.contains(&op.as_str()) =>
        {
            op.clone()
        }
        _ => return Err("op"),
    };
    let args = match payload.remove("args") {
        None => Map::new(),
        Some(Value::Object(args)) => args,
        Some(_) => return Err("args"),
    };
    let corpus = match payload.remove("corpus") {
        None | Some(Value::Null) => None,
        Some(Value::String(corpus)) if corpus.is_empty() => None,
        Some(Value::String(corpus)) => Some(corpus),
        Some(_) => return Err("corpus"),
    };
    Ok(Asked {
        key: hex(Sha256::digest(presented.as_bytes()).as_slice()),
        op,
        args,
        corpus,
    })
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// `Forward` unless this is a read the mirror answers for, then its whole answer through the tail.
pub(super) async fn answer(
    client: &mut TcpStream,
    head: &Head,
    target: &str,
    buffer: &mut Vec<u8>,
    still_unread: &mut bool,
    shared: &Shared,
    client_closes: bool,
) -> Door {
    let Some(length) = body_length(head, target) else {
        return Door::Forward("framing");
    };
    if !read_body(client, buffer, length).await {
        return Door::Forward("body not whole");
    }
    let Asked {
        key,
        op,
        args,
        corpus,
    } = match asked(head, shared, &buffer[..length]) {
        Ok(asked) => asked,
        Err(why) => return Door::Forward(why),
    };
    let granted = match shared.mirror.serve(&key) {
        Serve::Grant(granted) => granted,
        Serve::Forward(why) => return Door::Forward(why),
    };
    // Python resolves the path and words the refusal. Exactly the pull's says the same as it would.
    if corpus.is_some_and(|corpus| corpus != granted.corpus) {
        return Door::Forward("corpus");
    }
    if granted.grant.scope == rules::TRANSIENT_SCOPE {
        return Door::Forward("transient scope");
    }
    if !rules::repr_is_simple(&granted.grant.scope) || !rules::repr_is_simple(&op) {
        return Door::Forward("repr");
    }
    let (status, body) = if granted.grant.corpus != granted.corpus {
        (403, rules::refused_body(rules::OTHER_CORPUS_WORDS))
    } else {
        let allowed = rules::permitted(
            Some(&granted.grant.scope),
            granted.grant.operations.as_deref(),
        );
        if allowed.contains(&op.as_str()) && object_worker_reads::MOVED.contains(&op.as_str()) {
            let record = shared.context.record.clone();
            let window = shared.context.window.clone();
            let read = tokio::task::spawn_blocking(move || {
                object_worker_reads::read(&op, &args, &*record, &window)
            })
            .await;
            match read {
                Ok(Read::Body(body)) => (200, String::from_utf8_lossy(&body).into_owned()),
                Ok(Read::NotOwned) => return Door::Forward("not owned"),
                Err(panicked) => {
                    say(&format!("worker read panicked: {panicked}"));
                    return Door::Forward("not owned");
                }
            }
        } else if allowed.contains(&op.as_str()) {
            let record = shared.context.record.clone();
            let at = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_or(0.0, |since| since.as_secs_f64());
            let read =
                tokio::task::spawn_blocking(move || worker_reads::read(&op, &args, &*record, at))
                    .await;
            match read {
                Ok(Read::Body(body)) => (200, String::from_utf8_lossy(&body).into_owned()),
                Ok(Read::NotOwned) => return Door::Forward("not owned"),
                Err(panicked) => {
                    say(&format!("worker read panicked: {panicked}"));
                    return Door::Forward("not owned");
                }
            }
        } else {
            let words = rules::not_permitted_words(&op, Some(&granted.grant.scope), &allowed);
            (403, rules::refused_body(&words))
        }
    };
    let answered = answers::send_json(status, &body, false, client_closes);
    through_the_tail(
        client,
        buffer,
        length,
        still_unread,
        shared,
        &granted,
        answered,
    )
    .await
}

async fn through_the_tail(
    client: &mut TcpStream,
    buffer: &mut Vec<u8>,
    length: usize,
    still_unread: &mut bool,
    shared: &Shared,
    granted: &Granted<ProcessWatch, BrainFile>,
    answered: Written,
) -> Door {
    let barrier = OnFiles {
        brain: shared.mirror.brain(),
        boot: &granted.boot,
        owner: &granted.owner,
        watch: &*granted.watch,
    };
    let ended = tail::answer(
        &mut *client,
        &answered.bytes,
        &barrier,
        probe::send_bound(SEND_BOUND),
    )
    .await;
    match ended {
        // Past the first accepted byte nothing forwards, so only these leave the buffer as it was.
        Tailed::Forward(Refused::Discard(why)) => {
            shared.mirror.discard_boot(&granted.boot);
            Door::Forward(why)
        }
        Tailed::Forward(Refused::Forward(why)) => Door::Forward(why),
        Tailed::Sent => {
            buffer.drain(..length);
            *still_unread = false;
            Door::Answered {
                closes: answered.closes,
            }
        }
        Tailed::ClientGone => {
            buffer.drain(..length);
            *still_unread = false;
            Door::ClientGone
        }
        Tailed::Aborted { hold, id } => Door::Aborted(Box::new(AbortedHold { hold, id })),
    }
}

/// `POST /private/grants`'s answer, the front's own. A malformed push discards, **and only then**
/// answers 400, so Python takes it as a failed push and fences.
pub(super) async fn push(
    client: &mut TcpStream,
    head: &Head,
    buffer: &mut Vec<u8>,
    still_unread: &mut bool,
    shared: &Shared,
) -> Written {
    let refused = |shared: &Shared| {
        shared.mirror.pushed(None);
        answers::send_json(400, "{\"error\": \"a malformed push\"}", false, true)
    };
    let declared = head.content_length_if_framed();
    if head.has_value("Transfer-Encoding") || declared == 0 || declared > BODY_LOOK {
        return refused(shared);
    }
    let length = declared as usize;
    if !read_body(client, buffer, length).await {
        return refused(shared);
    }
    let body: Vec<u8> = buffer.drain(..length).collect();
    *still_unread = false;
    if shared.mirror.pushed(super::grants::parse_push(&body)) {
        answers::send_json(200, "{\"ok\": true}", false, true)
    } else {
        refused(shared)
    }
}
