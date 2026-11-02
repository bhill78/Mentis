//! One client connection: its requests, one at a time, each answered or forwarded.
//!
//! The order of what is decided is Python's. The head's refusals, then `/private/` (the front's
//! own, and decided before the table), then a method nothing answers, then `do_POST`'s refusal of
//! `Transfer-Encoding`, and only then the table.

use std::net::SocketAddr;
use std::sync::Arc;
use std::time::{Duration, Instant};

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::watch;

use super::answers::{self, Written};
use super::checks;
use super::forward::{self, Body, Forwarded};
use super::head::{self, Head, HeadEnd, Line, Refusal};
use super::latency::unnamed_route;
use super::{Shared, secrets_match};
use crate::handlers::{self, Ask, Reply};
use crate::launch::{PRIVATE_PREFIX, SECRET_HEADER, STOP_PATH};
use crate::route_table::Decision;

/// `send_response_only(CONTINUE)`.
const CONTINUE: &[u8] = b"HTTP/1.1 100 Continue\r\n\r\n";

/// How much of the client's bytes the front reads at a time while looking for a head.
const READ_AHEAD: usize = 16 * 1024;

enum Next {
    Another,
    End,
}

/// Serve a connection until it ends or the front stops. A stopping front finishes what it has
/// forwarded, and takes no new request even on a connection kept open from before.
pub async fn serve(mut client: TcpStream, peer: SocketAddr, shared: Arc<Shared>) {
    let _ = client.set_nodelay(true);
    let mut stopping = shared.stop_requested.subscribe();
    let mut buffer = Vec::new();
    let mut at_eof = false;
    loop {
        let Some(found) = read_head(&mut client, &mut buffer, &mut at_eof, &mut stopping).await
        else {
            return;
        };
        let _in_flight = shared.begin();
        let next = match found {
            HeadEnd::RequestLineTooLong => {
                let answer = answers::refusal(&Refusal::RequestLineTooLong, false);
                let _ = client.write_all(&answer.bytes).await;
                shared.latency.record("refused", Duration::ZERO);
                Next::End
            }
            HeadEnd::At(end) => {
                let raw: Vec<u8> = buffer.drain(..end).collect();
                let started = Instant::now();
                let (next, route) =
                    request(&mut client, peer, head::parse(raw), &mut buffer, &shared).await;
                shared.latency.record(&route, started.elapsed());
                next
            }
        };
        match next {
            Next::Another => {}
            Next::End => {
                let _ = client.shutdown().await;
                return;
            }
        }
    }
}

/// Up to the end of a head, or `None` when the connection is over: the client has ended it, or the
/// front is stopping with no request in hand.
async fn read_head(
    client: &mut TcpStream,
    buffer: &mut Vec<u8>,
    at_eof: &mut bool,
    stopping: &mut watch::Receiver<bool>,
) -> Option<HeadEnd> {
    loop {
        if *stopping.borrow() {
            return None;
        }
        if let Some(found) = head::head_end(buffer, *at_eof) {
            return Some(found);
        }
        if *at_eof {
            return None;
        }
        let mut chunk = [0; READ_AHEAD];
        tokio::select! {
            _ = stopping.changed() => {}
            read = client.read(&mut chunk) => match read {
                Ok(0) => {
                    *at_eof = true;
                    if buffer.is_empty() {
                        return None;
                    }
                }
                Ok(got) => buffer.extend_from_slice(&chunk[..got]),
                Err(_) => return None,
            },
        }
    }
}

/// One request. Returns what the connection does next and the name its time is filed under.
async fn request(
    client: &mut TcpStream,
    peer: SocketAddr,
    head: Head,
    buffer: &mut Vec<u8>,
    shared: &Shared,
) -> (Next, String) {
    if matches!(head.line, Line::Empty) {
        return (Next::End, "refused".into());
    }
    let Line::Plain { method, target, .. } = &head.line else {
        let next = send_on(client, peer, &head, buffer, shared, true).await;
        return (next, "forwarded:other".into());
    };
    let (method, target) = (method.clone(), target.clone());
    let path = target.split('?').next().unwrap_or(&target).to_owned();
    let declared = head.content_length_if_framed();
    let client_closes = head.client_asked_to_close();

    if let Some(refusal) = &head.refusal {
        // Line limits stop Python before it has looked at `Expect`, and the rest come after.
        let limit = matches!(
            refusal,
            Refusal::HeaderLineTooLong | Refusal::TooManyHeaders
        );
        if !limit && head.expects_continue() {
            let _ = client.write_all(CONTINUE).await;
        }
        let answer = answers::refusal(refusal, method == "HEAD");
        return (give(client, answer).await, "refused".into());
    }

    let body_unread = head.body_goes_unread(&method);

    if under_private(&target) {
        let answer = private(&head, &method, &path, peer, body_unread, shared).await;
        let has_te = head.has_value("Transfer-Encoding");
        if head.expects_continue() {
            let _ = client.write_all(CONTINUE).await;
        }
        if answer.closes && !has_te {
            discard(client, buffer, declared).await;
        }
        return (give(client, answer).await, "private".into());
    }

    if !matches!(method.as_str(), "GET" | "POST" | "OPTIONS") {
        if head.expects_continue() {
            let _ = client.write_all(CONTINUE).await;
        }
        discard(client, buffer, declared).await;
        let answer = answers::unsupported_method(&method);
        return (give(client, answer).await, "refused".into());
    }

    if method == "POST" && head.has_value("Transfer-Encoding") {
        if head.expects_continue() {
            let _ = client.write_all(CONTINUE).await;
        }
        let host = head.get("Host");
        let answer = if checks::host_allowed(host, &shared.allowed_hosts) {
            answers::transfer_encoding_refused()
        } else {
            answers::refused_host(host, true)
        };
        return (give(client, answer).await, "refused".into());
    }

    // The table decides on the path as sent, and a target Python would have to read for itself
    // (`//x`, an absolute URL) is Python's to read. Multipart and the like are Python's whatever
    // the table says. Only a GET is ever answered here: nothing here reads a request's body.
    let table = shared.table.current();
    let decision = if path.starts_with('/') && !path.starts_with("//") && !head.only_python_can_say
    {
        table.decide(&method, &path)
    } else {
        Decision::Python { rule: None }
    };
    let filed = match &decision {
        _ if path == "/api/worker" => unnamed_route(&path).to_owned(),
        Decision::Rust { handler } => (*handler).to_owned(),
        Decision::Python { rule: Some(rule) } => (*rule).to_owned(),
        Decision::Python { rule: None } => unnamed_route(&path).to_owned(),
    };
    if let Decision::Rust { handler } = decision
        && method == "GET"
        && let Some(route) = handlers::find(handler)
    {
        if let Some(answer) = door_refuses(route.door, &head, &method, &path, body_unread, shared) {
            if head.expects_continue() {
                let _ = client.write_all(CONTINUE).await;
            }
            if !head.has_value("Transfer-Encoding") {
                discard(client, buffer, declared).await;
            }
            return (give(client, answer).await, filed);
        }
        let ask = Ask {
            method,
            path: path.clone(),
            query: target
                .split_once('?')
                .map_or(String::new(), |(_, query)| query.to_owned()),
            headers: head
                .headers
                .iter()
                .map(|header| (header.name.clone(), header.value.clone()))
                .collect(),
        };
        let context = shared.context.clone();
        let answer = route.answer;
        let replied = tokio::task::spawn_blocking(move || answer(&context, &ask))
            .await
            .unwrap_or_else(|panicked| {
                super::say(&format!("handler {handler} panicked: {panicked}"));
                Reply::NotOwned
            });
        if let Reply::Answer {
            status,
            content_type,
            body,
        } = replied
        {
            if head.expects_continue() {
                let _ = client.write_all(CONTINUE).await;
            }
            let answer = answers::send(status, content_type, &body, body_unread, client_closes);
            if answer.closes && !head.has_value("Transfer-Encoding") {
                discard(client, buffer, declared).await;
            }
            return (give(client, answer).await, filed);
        }
        let next = send_on(client, peer, &head, buffer, shared, client_closes).await;
        return (next, format!("{filed}:forwarded"));
    }
    let next = send_on(client, peer, &head, buffer, shared, client_closes).await;
    (next, filed)
}

/// Whether Python would read this target as being under `/private/`.
///
/// The prefix check on the path as sent isn't enough. Python turns `//x` into `/x`
/// (`parse_request`), and `urlparse` finds the path in `http://host/x`. So `//private/live`
/// forwarded with the secret the front adds would reach Python's private route, carrying the proof
/// that it came from the front, for anyone who asked.
fn under_private(target: &str) -> bool {
    if target.starts_with('/') {
        let collapsed = format!("/{}", target.trim_start_matches('/'));
        return collapsed.starts_with(PRIVATE_PREFIX);
    }
    // An absolute URL, or anything with leading junk `urlsplit` would strip.
    target.contains(PRIVATE_PREFIX)
}

async fn private(
    head: &Head,
    method: &str,
    path: &str,
    peer: SocketAddr,
    body_unread: bool,
    shared: &Shared,
) -> Written {
    let from_this_machine = peer.ip().to_canonical().is_loopback();
    let presented = head.get(SECRET_HEADER).unwrap_or("");
    if method == "POST"
        && path == STOP_PATH
        && from_this_machine
        && secrets_match(presented, &shared.secret)
    {
        shared.stop_accepting().await;
        return answers::send_json(200, "{\"stopping\": true}", true, true);
    }
    answers::no_such_surface(body_unread)
}

/// The refusals of the door a route replaced, in its order.
fn door_refuses(
    door: handlers::Door,
    head: &Head,
    method: &str,
    path: &str,
    body_unread: bool,
    shared: &Shared,
) -> Option<Written> {
    let host = head.get("Host");
    if !checks::host_allowed(host, &shared.allowed_hosts) {
        return Some(answers::refused_host(host, body_unread));
    }
    if door.checks_client()
        && checks::client_missing(
            method,
            path,
            head.get(checks::CLIENT_HEADER),
            head.get(checks::GRANT_HEADER),
        )
    {
        return Some(answers::missing_client(body_unread));
    }
    if let Some(wording) = door.grant_wording()
        && head.has_value(checks::GRANT_HEADER)
    {
        return Some(answers::grant_refused(wording, path, body_unread));
    }
    None
}

/// Forward to Python. A request framed by `Transfer-Encoding` goes on as a head alone: nothing
/// here decodes it and nor does Python, so its body isn't a body, and the connection ends with
/// this answer so that those bytes can't be read as the next request.
async fn send_on(
    client: &mut TcpStream,
    peer: SocketAddr,
    head: &Head,
    buffer: &mut Vec<u8>,
    shared: &Shared,
    client_closes: bool,
) -> Next {
    let request = forward::for_python(head, &peer.ip().to_canonical().to_string(), &shared.secret);
    let framed_by_length =
        matches!(head.line, Line::Plain { .. }) && !head.has_value("Transfer-Encoding");
    let declared = if framed_by_length {
        head.content_length_if_framed()
    } else {
        0
    };
    let in_hand = usize::try_from(declared)
        .unwrap_or(usize::MAX)
        .min(buffer.len());
    let body = Body {
        already: &buffer[..in_hand],
        remaining: declared - in_hand as u64,
    };
    let result = forward::forward(
        client,
        shared.upstream,
        &request,
        head,
        body,
        client_closes || !framed_by_length,
    )
    .await;
    buffer.drain(..in_hand);
    match result {
        Ok(Forwarded::KeepOpen) => Next::Another,
        Ok(Forwarded::Close) => Next::End,
        Err(answer) => give(client, answer).await,
    }
}

async fn discard(client: &mut TcpStream, buffer: &mut Vec<u8>, declared: u64) {
    let in_hand = usize::try_from(declared)
        .unwrap_or(usize::MAX)
        .min(buffer.len());
    buffer.drain(..in_hand);
    forward::discard_small_body(client, in_hand as u64, declared).await;
}

async fn give(client: &mut TcpStream, answer: Written) -> Next {
    if client.write_all(&answer.bytes).await.is_err() || answer.closes {
        Next::End
    } else {
        Next::Another
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_way_python_would_read_a_target_as_private_is_the_front_s() {
        for target in [
            "/private/live",
            "/private/",
            "/private/stop?x=1",
            "//private/live",
            "///private/live",
            "http://host/private/live",
            "HTTP://host/private/live",
            "http:/private/live",
            "\u{1}/private/live",
        ] {
            assert!(under_private(target), "{target}");
        }
        for target in [
            "/private",
            "/privateer/x",
            "/fluid/private/x",
            "/api/pulse",
            "/%70rivate/live",
            "*",
        ] {
            assert!(!under_private(target), "{target}");
        }
    }
}
