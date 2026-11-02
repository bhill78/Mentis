//! Passing a request to Python and its answer back, as bytes.
//!
//! **One connection to Python per request, never kept.** A kept connection that Python has dropped
//! can't be told from Python dying with the request in hand, and the two 503s say opposite things.
//! A refused connection is the one proof that nothing was sent.
//!
//! Both directions run at once with a bounded buffer: an export ZIP or a 200 MB upload is never
//! held, and Python may answer before it has read everything it was sent.

use std::net::SocketAddr;
use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::net::tcp::{ReadHalf, WriteHalf};

use super::answers::{PythonGone, Written, python_gone};
use super::head::{Head, Line, latin1};
use crate::launch::{PEER_HEADER, SECRET_HEADER};

/// A declared body at or past this isn't one anybody is sending. Python has to allocate it to read
/// it, so a route that reads one raises and Python closes without a word, which is its answer and
/// isn't Python going. Where that starts depends on the machine's memory, so the front can't know it
/// (2^38 where it was measured), and this is low enough for any machine a Brain runs on. Short of
/// that, Python closing with a body still to come stays the 503: it may be dying with it in hand.
const BEYOND_ANY_BODY: u64 = 1 << 32;

/// Bytes moved at a time, each way, per request. What a streamed body costs in memory.
const CHUNK: usize = 64 * 1024;
/// The longest answer head the front reads before giving up on framing it.
const MAX_ANSWER_HEAD: usize = 1 << 20;

/// The request as Python gets it: every byte as sent, less any inbound peer or secret header, plus
/// the real ones if [`Head::may_carry_proof`] says so. `peer` is the IP alone, as
/// `self.client_address[0]` is.
pub fn for_python(head: &Head, peer: &str, secret: &str) -> Vec<u8> {
    let mut out = Vec::with_capacity(head.raw.len() + secret.len() + 64);
    let mut at = 0;
    for header in &head.headers {
        if header.name.eq_ignore_ascii_case(PEER_HEADER)
            || header.name.eq_ignore_ascii_case(SECRET_HEADER)
        {
            out.extend_from_slice(&head.raw[at..header.raw.start]);
            at = header.raw.end;
        }
    }
    out.extend_from_slice(&head.raw[at..head.add_at]);
    // A head cut off by the client's end may have no line ending to stand on.
    if !matches!(out.last(), Some(b'\n' | b'\r')) {
        out.extend_from_slice(b"\r\n");
    }
    if head.may_carry_proof() {
        out.extend_from_slice(format!("{PEER_HEADER}: {peer}\r\n").as_bytes());
        out.extend_from_slice(format!("{SECRET_HEADER}: {secret}\r\n").as_bytes());
    }
    if head.add_at == head.raw.len() {
        out.extend_from_slice(b"\r\n");
    } else {
        out.extend_from_slice(&head.raw[head.add_at..]);
    }
    out
}

/// How a forwarded request ended, for the connection it came on.
#[derive(Debug, PartialEq, Eq)]
pub enum Forwarded {
    /// Answered whole, and the client's connection can take another request.
    KeepOpen,
    /// Answered, or as much as could be, and the connection ends.
    Close,
}

/// A body to carry: how much of it is still to come, and what was already read with the head.
pub struct Body<'a> {
    pub already: &'a [u8],
    pub remaining: u64,
}

enum Pumped {
    Done,
    ClientGone,
    PythonStoppedReading,
}

/// How much of a refused body the front reads and drops before answering, as `DISCARD_MAX`.
pub const DISCARD_MAX: u64 = 64 * 1024;
/// How long it reads for, as `_discard_small_body`.
pub const DISCARD_FOR: Duration = Duration::from_secs(2);

/// `_discard_small_body`: on Windows, closing a socket with unread bytes in it sends RST, and the
/// client can lose the answer it was just sent. So a small unread body is read and thrown away.
/// `in_hand` is what was already read of it.
pub async fn discard_small_body(client: &mut TcpStream, in_hand: u64, length: u64) {
    if !(1..=DISCARD_MAX).contains(&length) {
        return;
    }
    let mut left = length.saturating_sub(in_hand);
    let mut buffer = [0; 4096];
    let reading = async {
        while left > 0 {
            match client.read(&mut buffer).await {
                Ok(0) | Err(_) => return,
                Ok(got) => left = left.saturating_sub(got as u64),
            }
        }
    };
    let _ = tokio::time::timeout(DISCARD_FOR, reading).await;
}

/// Forward one request and relay its answer. `Err` is the 503 to give, with nothing yet sent.
pub async fn forward(
    client: &mut TcpStream,
    upstream: SocketAddr,
    request: &[u8],
    head: &Head,
    body: Body<'_>,
    client_closes: bool,
) -> Result<Forwarded, Written> {
    let declared = body.already.len() as u64 + body.remaining;
    let in_hand = body.already.len() as u64;
    let Ok(mut python) = TcpStream::connect(upstream).await else {
        discard_small_body(client, in_hand, declared).await;
        return Err(python_gone(PythonGone::Unreached));
    };
    let _ = python.set_nodelay(true);
    if python.write_all(request).await.is_err() {
        discard_small_body(client, in_hand, declared).await;
        return Err(python_gone(PythonGone::Reached));
    }
    if !matches!(head.line, Line::Plain { .. }) {
        // Python ends every one of these, and with its reading side closed it can't wait for more.
        let _ = python.shutdown().await;
        let (_, mut to_client) = client.split();
        let (mut from_python, _) = python.split();
        return Ok(relay_until_python_ends(&mut from_python, &mut to_client, &[]).await);
    }

    let mut still_unread = body.remaining;
    let relayed = {
        let (mut from_client, mut to_client) = client.split();
        let (mut from_python, mut to_python) = python.split();
        let pump = pump_body(
            &mut from_client,
            &mut to_python,
            body.already,
            &mut still_unread,
        );
        let relay = relay_answer(&mut from_python, &mut to_client, client_closes);
        tokio::pin!(pump, relay);
        let mut pumping = true;
        loop {
            tokio::select! {
                relayed = &mut relay => {
                    // An answer that came before the whole body did leaves bytes on the connection
                    // that aren't a next request. Python closes then too.
                    break relayed.map(|ended| if pumping { Forwarded::Close } else { ended });
                }
                pumped = &mut pump, if pumping => match pumped {
                    Pumped::Done | Pumped::PythonStoppedReading => pumping = false,
                    // Dropping the connection to Python tells it what the client's end told this.
                    Pumped::ClientGone => break Ok(Forwarded::Close),
                },
            }
        }
    };
    if relayed.is_err() {
        if (still_unread > 0 && declared >= BEYOND_ANY_BODY)
            || head.python_cannot_parse_its_target()
        {
            return Ok(Forwarded::Close);
        }
        discard_small_body(client, declared - still_unread, declared).await;
    }
    relayed
}

async fn pump_body(
    client: &mut ReadHalf<'_>,
    python: &mut WriteHalf<'_>,
    already: &[u8],
    remaining: &mut u64,
) -> Pumped {
    if !already.is_empty() && python.write_all(already).await.is_err() {
        return Pumped::PythonStoppedReading;
    }
    let mut buffer = vec![0; CHUNK];
    while *remaining > 0 {
        let want = usize::try_from(*remaining).unwrap_or(CHUNK).min(CHUNK);
        match client.read(&mut buffer[..want]).await {
            Ok(0) | Err(_) => return Pumped::ClientGone,
            Ok(got) => {
                *remaining -= got as u64;
                if python.write_all(&buffer[..got]).await.is_err() {
                    return Pumped::PythonStoppedReading;
                }
            }
        }
    }
    Pumped::Done
}

/// What an answer's head says about how it ends.
#[derive(Debug, PartialEq, Eq)]
struct AnswerHead {
    status: u16,
    content_length: Option<u64>,
    says_close: bool,
    /// Framed some way the front doesn't read, so it ends when Python ends it.
    other_framing: bool,
}

/// The end of a head in `buffer`, past its blank line.
fn answer_head_end(buffer: &[u8]) -> Option<usize> {
    let mut at = 0;
    while let Some(line) = buffer[at..].iter().position(|&b| b == b'\n') {
        let line_end = at + line + 1;
        if matches!(&buffer[at..line_end], b"\r\n" | b"\n") {
            return Some(line_end);
        }
        at = line_end;
    }
    None
}

/// Read an answer's head. `None` for something that isn't one: HTTP/0.9, say. It is passed on as
/// it is, whatever it is.
fn read_answer_head(head: &[u8]) -> Option<AnswerHead> {
    let text = latin1(head);
    let mut lines = text.split('\n').map(|line| line.trim_end_matches('\r'));
    let status_line = lines.next()?;
    let mut words = status_line.split(' ');
    if !words.next()?.starts_with("HTTP/1.") {
        return None;
    }
    let status = words.next()?.parse().ok()?;
    let mut answer = AnswerHead {
        status,
        content_length: None,
        says_close: false,
        other_framing: false,
    };
    for line in lines {
        let Some((name, value)) = line.split_once(':') else {
            continue;
        };
        let value = value.trim();
        if name.eq_ignore_ascii_case("Content-Length") {
            match value.parse() {
                Ok(length) if answer.content_length.is_none() => {
                    answer.content_length = Some(length);
                }
                _ => answer.other_framing = true,
            }
        } else if name.eq_ignore_ascii_case("Connection") {
            answer.says_close |= value.eq_ignore_ascii_case("close");
        } else if name.eq_ignore_ascii_case("Transfer-Encoding") {
            answer.other_framing = true;
        }
    }
    Some(answer)
}

async fn relay_answer(
    python: &mut ReadHalf<'_>,
    client: &mut WriteHalf<'_>,
    client_closes: bool,
) -> Result<Forwarded, Written> {
    let mut held = Vec::with_capacity(4096);
    let mut buffer = vec![0; CHUNK];
    loop {
        // Nothing has been given to the client from this answer until its head is whole.
        let head_end = loop {
            if let Some(end) = answer_head_end(&held) {
                break end;
            }
            if held.len() > MAX_ANSWER_HEAD {
                return Ok(relay_until_python_ends(python, client, &held).await);
            }
            match python.read(&mut buffer).await {
                Ok(0) | Err(_) => return Err(python_gone(PythonGone::Reached)),
                Ok(got) => {
                    held.extend_from_slice(&buffer[..got]);
                    // Not the start of an answer's head at all: passed on, and Python ends it.
                    if held.len() >= 7 && !held.starts_with(b"HTTP/1.") {
                        return Ok(relay_until_python_ends(python, client, &held).await);
                    }
                }
            }
        };
        let Some(answer) = read_answer_head(&held[..head_end]) else {
            return Ok(relay_until_python_ends(python, client, &held).await);
        };
        if (100..200).contains(&answer.status) {
            // `Expect: 100-continue`: passed on as it came, and the answer is still to come.
            if client.write_all(&held[..head_end]).await.is_err() {
                return Ok(Forwarded::Close);
            }
            held.drain(..head_end);
            continue;
        }

        let no_body = answer.status == 204 || answer.status == 304;
        let length = match (answer.other_framing, no_body, answer.content_length) {
            (true, _, _) => None,
            (false, true, _) => Some(0),
            (false, false, length) => length,
        };
        let Some(length) = length else {
            return Ok(relay_until_python_ends(python, client, &held).await);
        };

        let already = (held.len() - head_end) as u64;
        let send_now = usize::try_from(length.min(already)).unwrap_or(usize::MAX);
        if client
            .write_all(&held[..head_end + send_now])
            .await
            .is_err()
        {
            return Ok(Forwarded::Close);
        }
        let mut remaining = length - send_now as u64;
        while remaining > 0 {
            let want = usize::try_from(remaining).unwrap_or(CHUNK).min(CHUNK);
            match python.read(&mut buffer[..want]).await {
                // Python stopped mid-answer. The client's connection has to end short, so it
                // knows: its head is gone, and what it has can't be made whole.
                Ok(0) | Err(_) => return Ok(Forwarded::Close),
                Ok(got) => {
                    if client.write_all(&buffer[..got]).await.is_err() {
                        return Ok(Forwarded::Close);
                    }
                    remaining -= got as u64;
                }
            }
        }
        return Ok(if answer.says_close || client_closes {
            Forwarded::Close
        } else {
            Forwarded::KeepOpen
        });
    }
}

/// Everything from here is passed on until Python ends it, which ends the client's too.
async fn relay_until_python_ends(
    python: &mut ReadHalf<'_>,
    client: &mut WriteHalf<'_>,
    held: &[u8],
) -> Forwarded {
    if client.write_all(held).await.is_err() {
        return Forwarded::Close;
    }
    let mut buffer = vec![0; CHUNK];
    loop {
        match python.read(&mut buffer).await {
            Ok(0) | Err(_) => return Forwarded::Close,
            Ok(got) => {
                if client.write_all(&buffer[..got]).await.is_err() {
                    return Forwarded::Close;
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::front::head::parse;

    fn sent(raw: &[u8]) -> String {
        latin1(&for_python(&parse(raw.to_vec()), "100.64.0.9", "s3"))
    }

    #[test]
    fn every_byte_goes_on_and_the_real_peer_is_added() {
        assert_eq!(
            sent(b"GET /a%20b?x=1 HTTP/1.1\r\nHoSt:  LocalHost:1 \r\nA: 1\r\n\r\n"),
            "GET /a%20b?x=1 HTTP/1.1\r\nHoSt:  LocalHost:1 \r\nA: 1\r\nX-Mentis-Peer: 100.64.0.9\r\nX-Mentis-Boot-Secret: s3\r\n\r\n"
        );
    }

    #[test]
    fn an_inbound_peer_or_secret_never_reaches_python_however_it_is_spelt() {
        let got = sent(
            b"GET / HTTP/1.1\r\nx-mentis-peer: 1.1.1.1\r\nA: 1\r\nX-MENTIS-BOOT-SECRET: forged\r\n folded\r\nX-Mentis-Peer: 2.2.2.2\r\nB: 2\r\n\r\n",
        );
        assert_eq!(
            got,
            "GET / HTTP/1.1\r\nA: 1\r\nB: 2\r\nX-Mentis-Peer: 100.64.0.9\r\nX-Mentis-Boot-Secret: s3\r\n\r\n"
        );
    }

    #[test]
    fn one_behind_a_bare_cr_is_stripped_too() {
        let got = sent(b"GET / HTTP/1.1\r\nA: 1\rX-Mentis-Peer: forged\r\nB: 2\r\n\r\n");
        assert!(!got.contains("forged"), "{got}");
        assert!(got.contains("A: 1\rB: 2\r\n"), "{got}");
    }

    #[test]
    fn a_head_cut_off_by_the_client_still_ends_for_python() {
        assert_eq!(
            sent(b"GET / HTTP/1.1\r\nA: 1"),
            "GET / HTTP/1.1\r\nA: 1\r\nX-Mentis-Peer: 100.64.0.9\r\nX-Mentis-Boot-Secret: s3\r\n\r\n"
        );
    }

    #[test]
    fn no_proof_goes_with_what_python_would_read_as_private() {
        for raw in [
            &b"GET /private/x\r\nHost: a\r\n\r\n"[..],
            b"GET //private/x\r\nHost: a\r\n\r\n",
            b"GET http://[/private/x HTTP/1.1\r\nHost: a\r\n\r\n",
            b"G'T /private/x HTTP/1.1\r\nHost: a\r\n\r\n",
        ] {
            let got = sent(raw);
            assert!(!got.contains("s3") && !got.contains("100.64.0.9"), "{got}");
        }
    }

    #[test]
    fn a_forged_proof_goes_whether_or_not_a_real_one_comes() {
        assert_eq!(
            sent(b"G'T /x HTTP/1.1\r\nX-Mentis-Boot-Secret: forged\r\nA: 1\r\n\r\n"),
            "G'T /x HTTP/1.1\r\nA: 1\r\n\r\n"
        );
    }

    #[test]
    fn what_an_answer_s_head_says_about_its_end() {
        let read = |text: &[u8]| read_answer_head(text).unwrap();
        let plain = read(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\n");
        assert_eq!(plain.content_length, Some(5));
        assert!(!plain.says_close && !plain.other_framing);
        assert!(read(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n").says_close);
        assert!(read(b"HTTP/1.1 200 OK\r\nContent-Length: x\r\n\r\n").other_framing);
        assert!(read(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n").other_framing);
        assert!(
            read(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nContent-Length: 6\r\n\r\n")
                .other_framing
        );
        assert_eq!(read_answer_head(b"{\"not\": \"http\"}\n\n"), None);
    }
}
