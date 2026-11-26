//! Reads a route of the front's own couldn't answer, on their way to Python: shared when the same
//! read is already on its way, and only so many at a time. `contracts/route-table.md`, "Forwarded
//! reads".
//!
//! **Why.** A route the front owns forwards when it can't answer for itself, most often because the
//! live snapshot is stale (`contracts/live-snapshot.md`). That happens when Python is slow, so every
//! client polling a view sends Python its heaviest reads exactly when it has least to spare. Here
//! identical reads in flight share one request to Python and its answer, and at most
//! [`MOST_FORWARDED_READS`] distinct ones go to Python at once.
//!
//! **What is never shared.** Only a `GET` with no body, no `Expect` and no worker grant, whose
//! answer is framed by its length, is shared, and only with requests whose target and headers (the
//! credentials among them) and peer are the same. A request joins a read already in flight only if
//! no other request, a write or anything else that isn't a `GET` or `HEAD`, was in hand at any time
//! since that read was sent: so a read made after a write has been answered never gets an answer
//! asked for before it. Nothing is kept once it has been answered: this is not a cache.

use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::{Semaphore, watch};
use tokio::task::AbortHandle;

use super::answers::PythonGone;
use super::checks::GRANT_HEADER;
use super::forward::{answer_head_end, read_answer_head};
use super::head::{Head, Line};

/// The most forwarded reads of the front's own routes in Python's hands at once. Python answers
/// them on a thread each, under one interpreter lock, so more at once finishes none sooner.
pub const MOST_FORWARDED_READS: usize = 4;
/// How long a read waits for one of those places before it is told Mentis is busy.
pub const WAIT_FOR_A_PLACE: Duration = Duration::from_secs(3);
/// What the busy answer's `Retry-After` says, in seconds.
pub const RETRY_AFTER_S: u64 = 2;
/// The largest answer shared. A larger one is passed on to each of its requests on its own.
pub const MOST_SHARED_ANSWER: usize = 32 * 1024 * 1024;
const MOST_HEAD: usize = 1 << 20;

/// Headers that say nothing Python answers by, left out of what makes two reads the same.
const NOT_ANSWERED_BY: &[&str] = &[
    "connection",
    "keep-alive",
    "priority",
    "referer",
    "cache-control",
    "pragma",
    "dnt",
];

/// What a shared read came to.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Landed {
    /// Python's whole answer, as it sent it, and whether it said `Connection: close`.
    Answer {
        bytes: Arc<Vec<u8>>,
        says_close: bool,
    },
    /// No place came within [`WAIT_FOR_A_PLACE`]: nothing was sent to Python.
    Busy,
    /// Python couldn't be reached, or stopped before its answer was whole.
    Gone(PythonGone),
    /// An answer this can't share: each request asks for its own.
    NotShared,
}

/// What makes two reads the same, or `None` for a read that is never shared.
pub fn key(head: &Head, target: &str, peer: &str) -> Option<String> {
    let unshareable = [
        "Content-Length",
        "Transfer-Encoding",
        "Expect",
        GRANT_HEADER,
    ];
    if unshareable.iter().any(|name| head.get(name).is_some()) {
        return None;
    }
    let version = match &head.line {
        Line::Plain { http_1_1, .. } => *http_1_1,
        _ => return None,
    };
    let mut key = format!("GET {target} {version}\n{peer}\n");
    for header in &head.headers {
        let name = header.name.to_ascii_lowercase();
        if NOT_ANSWERED_BY.contains(&name.as_str())
            || name.starts_with("sec-fetch-")
            || name.starts_with("sec-ch-")
        {
            continue;
        }
        key.push_str(&name);
        key.push(':');
        key.push_str(&header.value);
        key.push('\n');
    }
    Some(key)
}

struct Flight {
    key: String,
    /// [`Inner::requests_seen`] when it was sent.
    seen_at: u64,
    landed: watch::Receiver<Option<Landed>>,
    waiting: usize,
    task: AbortHandle,
}

#[derive(Default)]
struct Inner {
    /// Every flight not yet landed, by its id.
    flying: HashMap<u64, Flight>,
    /// The one a read with this key may join, if any.
    latest: HashMap<String, u64>,
    next_id: u64,
    /// Requests other than reads in hand now.
    others_in_hand: usize,
    /// Moves when a request other than a read begins and when it ends.
    requests_seen: u64,
}

/// For the front's whole life.
pub struct Flights {
    upstream: SocketAddr,
    places: Arc<Semaphore>,
    inner: Mutex<Inner>,
}

/// Held while a request other than a `GET` or `HEAD` is in hand. See the module's words.
pub struct OtherInHand<'a>(&'a Flights);

impl Drop for OtherInHand<'_> {
    fn drop(&mut self) {
        let mut inner = self.0.locked();
        inner.others_in_hand -= 1;
        inner.requests_seen += 1;
    }
}

/// One request's share of a flight. Its leaving, with others still waiting, leaves the flight to
/// them; the last to leave before it lands ends it, and with it the request to Python.
struct Waiting<'a> {
    flights: &'a Flights,
    id: u64,
}

impl Drop for Waiting<'_> {
    fn drop(&mut self) {
        let mut inner = self.flights.locked();
        let Some(flight) = inner.flying.get_mut(&self.id) else {
            return;
        };
        flight.waiting -= 1;
        if flight.waiting == 0 {
            inner.land(self.id).task.abort();
        }
    }
}

impl Inner {
    /// Forgets a flight, landed or let go. It must be flying.
    fn land(&mut self, id: u64) -> Flight {
        let flight = self
            .flying
            .remove(&id)
            .expect("only a flying one is landed");
        if self.latest.get(&flight.key) == Some(&id) {
            self.latest.remove(&flight.key);
        }
        flight
    }
}

impl Flights {
    pub fn new(upstream: SocketAddr) -> Self {
        Self::with_places(upstream, MOST_FORWARDED_READS)
    }

    pub fn with_places(upstream: SocketAddr, places: usize) -> Self {
        Self {
            upstream,
            places: Arc::new(Semaphore::new(places)),
            inner: Mutex::new(Inner::default()),
        }
    }

    fn locked(&self) -> std::sync::MutexGuard<'_, Inner> {
        self.inner.lock().expect("no panic is held across this")
    }

    /// A request other than a read begins: held until it has been answered.
    pub fn other_in_hand(&self) -> OtherInHand<'_> {
        let mut inner = self.locked();
        inner.others_in_hand += 1;
        inner.requests_seen += 1;
        OtherInHand(self)
    }

    /// How many shared reads are in flight now. For tests and reports.
    pub fn in_flight(&self) -> usize {
        self.locked().flying.len()
    }

    /// The answer to `request` (the bytes Python is sent), shared with any identical read already
    /// in flight that this may join. `None` if `client` left first: its share is let go, and the
    /// request to Python ends with the last one waiting for it.
    pub async fn read(
        self: &Arc<Self>,
        key: String,
        request: Vec<u8>,
        client: &TcpStream,
    ) -> Option<Landed> {
        let (mut landed, waiting) = {
            let mut inner = self.locked();
            let can_join = inner.others_in_hand == 0;
            let seen = inner.requests_seen;
            let latest = inner.latest.get(&key).copied();
            let joined = match latest.and_then(|id| Some((id, inner.flying.get_mut(&id)?))) {
                Some((id, flight)) if can_join && flight.seen_at == seen => {
                    flight.waiting += 1;
                    Some((flight.landed.clone(), id))
                }
                _ => None,
            };
            match joined {
                Some((landed, id)) => (landed, Waiting { flights: self, id }),
                None => {
                    inner.next_id += 1;
                    let id = inner.next_id;
                    let (send, landed) = watch::channel(None);
                    let flights = self.clone();
                    // Held until it is in the table, so it can't land before it is there.
                    let task = tokio::spawn(async move {
                        let came = fly(&flights.places, flights.upstream, &request).await;
                        let mut inner = flights.locked();
                        let _ = send.send(Some(came));
                        if inner.flying.contains_key(&id) {
                            inner.land(id);
                        }
                    });
                    // One it replaces as the one to join flies on for those already waiting.
                    inner.latest.insert(key.clone(), id);
                    inner.flying.insert(
                        id,
                        Flight {
                            key,
                            seen_at: seen,
                            landed: landed.clone(),
                            waiting: 1,
                            task: task.abort_handle(),
                        },
                    );
                    (landed, Waiting { flights: self, id })
                }
            }
        };
        let came = tokio::select! {
            biased;
            came = landed.wait_for(Option::is_some) => came.ok().and_then(|came| came.clone()),
            () = client_left(client) => None,
        };
        drop(waiting);
        came
    }
}

/// Returns once the client has ended its connection, looking without reading. Bytes arriving mean
/// it's still there (a next request sent ahead), and it isn't looked at again.
pub async fn client_left(client: &TcpStream) {
    let mut byte = [0; 1];
    match client.peek(&mut byte).await {
        Ok(got) if got > 0 => std::future::pending().await,
        _ => {}
    }
}

/// One request to Python, once a place is free, read whole.
async fn fly(places: &Semaphore, upstream: SocketAddr, request: &[u8]) -> Landed {
    let Ok(Ok(_place)) = tokio::time::timeout(WAIT_FOR_A_PLACE, places.acquire()).await else {
        return Landed::Busy;
    };
    let Ok(mut python) = TcpStream::connect(upstream).await else {
        return Landed::Gone(PythonGone::Unreached);
    };
    let _ = python.set_nodelay(true);
    if python.write_all(request).await.is_err() {
        return Landed::Gone(PythonGone::Reached);
    }
    let mut got = Vec::with_capacity(16 * 1024);
    let mut chunk = vec![0; 64 * 1024];
    let head_end = loop {
        if let Some(end) = answer_head_end(&got) {
            break end;
        }
        if got.len() > MOST_HEAD {
            return Landed::NotShared;
        }
        match python.read(&mut chunk).await {
            Ok(0) | Err(_) => return Landed::Gone(PythonGone::Reached),
            Ok(more) => got.extend_from_slice(&chunk[..more]),
        }
    };
    let Some(answer) = read_answer_head(&got[..head_end]) else {
        return Landed::NotShared;
    };
    let no_body = answer.status == 204 || answer.status == 304;
    let length = match (answer.other_framing, no_body, answer.content_length) {
        (false, true, _) => 0,
        (false, false, Some(length)) => length,
        _ => return Landed::NotShared,
    };
    if (100..200).contains(&answer.status) {
        return Landed::NotShared;
    }
    let Ok(length) = usize::try_from(length) else {
        return Landed::NotShared;
    };
    if length > MOST_SHARED_ANSWER {
        return Landed::NotShared;
    }
    let whole = head_end + length;
    while got.len() < whole {
        match python.read(&mut chunk).await {
            Ok(0) | Err(_) => return Landed::Gone(PythonGone::Reached),
            Ok(more) => got.extend_from_slice(&chunk[..more]),
        }
    }
    got.truncate(whole);
    Landed::Answer {
        bytes: Arc::new(got),
        says_close: answer.says_close,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::front::head::parse;

    fn key_of(raw: &[u8]) -> Option<String> {
        let head = parse(raw.to_vec());
        key(&head, "/api/turns?c=1", "127.0.0.1")
    }

    #[test]
    fn only_a_plain_read_with_nothing_that_changes_its_answer_left_out_is_shared() {
        let plain = key_of(
            b"GET /api/turns?c=1 HTTP/1.1\r\nHost: h\r\nX-Mentis-Client: 1\r\nCookie: a=1\r\n\r\n",
        );
        let other_hints = key_of(
            b"GET /api/turns?c=1 HTTP/1.1\r\nHost: h\r\nConnection: keep-alive\r\nX-Mentis-Client: 1\r\nSec-Fetch-Mode: cors\r\nCookie: a=1\r\nReferer: x\r\n\r\n",
        );
        assert!(plain.is_some());
        assert_eq!(plain, other_hints);
        let other_cookie = key_of(
            b"GET /api/turns?c=1 HTTP/1.1\r\nHost: h\r\nX-Mentis-Client: 1\r\nCookie: a=2\r\n\r\n",
        );
        assert_ne!(plain, other_cookie, "credentials are part of the read");
        for never in [
            &b"GET / HTTP/1.1\r\nHost: h\r\nX-Mentis-Worker: g\r\n\r\n"[..],
            b"GET / HTTP/1.1\r\nHost: h\r\nContent-Length: 0\r\n\r\n",
            b"GET / HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n",
            b"GET / HTTP/1.1\r\nHost: h\r\nExpect: 100-continue\r\n\r\n",
        ] {
            assert_eq!(key_of(never), None);
        }
        let head = parse(b"GET / HTTP/1.1\r\nHost: h\r\n\r\n".to_vec());
        assert_ne!(
            key(&head, "/a", "127.0.0.1"),
            key(&head, "/a", "10.0.0.2"),
            "the peer too"
        );
        assert_ne!(
            key(&head, "/a?x=1", "p"),
            key(&head, "/a?x=2", "p"),
            "the query too"
        );
    }
}
