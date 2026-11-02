//! The front's client of `GET /private/live`, what the pulse's second half comes from. Contract:
//! `docs/rust/contracts/live-snapshot.md`; the type, timings and state rule are in [`crate::live`].
//!
//! It only ever asks because a pulse was asked for recently, one poll at a time, with no retry but
//! the next tick. Nothing here is used for authority or a write decision.

use std::net::SocketAddr;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::Notify;
use tokio::task::JoinHandle;

use super::say;
use crate::launch::SECRET_HEADER;
use crate::live::{
    LIVE_PATH, LiveMark, LiveSnapshot, Liveness, POLL_EVERY, POLL_TIMEOUT, POLL_WHILE_ASKED_WITHIN,
    PollAnswer, discards, freshness,
};

/// More than any snapshot holds. Past it, the poll counts as unreadable.
const MOST_ANSWER: usize = 64 * 1024 * 1024;

/// A poll that has not come to anything yet, kept for the next tick. See [`Snapshots::poll`].
#[derive(Debug)]
enum InHand {
    Connecting(JoinHandle<std::io::Result<TcpStream>>),
    /// Sent, and what has come back so far.
    Waiting(TcpStream, Vec<u8>),
}

/// How reading an answer ended.
enum Read {
    Whole(Vec<u8>),
    /// Not all of it yet: the stream and what came are still good.
    NotYet(TcpStream, Vec<u8>),
    Gone,
    Unreadable,
}

/// What one poll came to: the table in `contracts/live-snapshot.md`, "What a poll does".
#[derive(Clone, Debug, PartialEq)]
pub enum Polled {
    /// A body that is the envelope of a schema this build reads.
    Good(Box<LiveSnapshot>),
    /// A schema this build doesn't read.
    UnknownSchema,
    /// A timeout, a non-200 or an unreadable body. Age keeps growing.
    Nothing,
    /// Connection refused, or reset before an answer.
    Gone,
}

/// What a pulse is told, at one moment.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Seen {
    pub state: Liveness,
    /// The hash held, whatever the state.
    pub hash: Option<String>,
    pub age: Option<Duration>,
}

impl Seen {
    pub fn mark(&self) -> Option<LiveMark> {
        LiveMark::of(self.state, self.age)
    }
}

#[derive(Clone, Debug)]
struct Held {
    snapshot: LiveSnapshot,
    /// When the poll that got this answer was sent. Its age is judged from here.
    sent: Instant,
}

/// What is known, with no clock of its own, so every rule can be tested at exact moments.
#[derive(Debug, Default)]
pub struct State {
    held: Option<Held>,
    /// A poll was refused or reset, and no good answer has come since.
    gone: bool,
    /// When a pulse last asked.
    asked: Option<Instant>,
    /// When polling last turned on. `None` while it is off.
    polling_since: Option<Instant>,
    /// When polling last turned on, on or off now: the bound on unavailable counts from it.
    last_turned_on: Option<Instant>,
    said: Option<Liveness>,
    polls_timed_out: u64,
}

impl State {
    /// A pulse asks. Whether that turned polling on, and what it is told.
    fn asked_at(&mut self, now: Instant) -> (bool, Seen) {
        self.asked = Some(now);
        let turned_on = self.polling_since.is_none();
        if turned_on {
            self.polling_since = Some(now);
            self.last_turned_on = Some(now);
        }
        (turned_on, self.seen(now))
    }

    pub fn seen(&self, now: Instant) -> Seen {
        let Some(held) = &self.held else {
            return Seen {
                state: Liveness::Unavailable,
                hash: None,
                age: None,
            };
        };
        let age = now.saturating_duration_since(held.sent);
        let state = if self.gone {
            Liveness::Unavailable
        } else {
            let polling_for = self
                .last_turned_on
                .map_or(Duration::ZERO, |on| now.saturating_duration_since(on));
            freshness(age, polling_for)
        };
        Seen {
            state,
            hash: Some(held.snapshot.live_hash.clone()),
            age: Some(age),
        }
    }

    /// What a poll sent at `sent` came to.
    pub fn apply(&mut self, polled: Polled, sent: Instant) {
        match polled {
            Polled::Good(answer) => {
                self.gone = false;
                match &self.held {
                    Some(held) if discards(&held.snapshot, &answer) => self.held = None,
                    _ => {
                        self.held = Some(Held {
                            snapshot: *answer,
                            sent,
                        });
                    }
                }
            }
            Polled::UnknownSchema => {
                self.gone = false;
                self.held = None;
            }
            Polled::Nothing => {}
            Polled::Gone => self.gone = true,
        }
    }

    /// Whether polling goes on. Off once no pulse has asked within the window.
    fn keep_polling(&mut self, now: Instant) -> bool {
        let wanted = self
            .asked
            .is_some_and(|asked| now.saturating_duration_since(asked) <= POLL_WHILE_ASKED_WITHIN);
        if !wanted {
            self.polling_since = None;
        }
        wanted
    }
}

/// The client, for the front's whole life.
#[derive(Debug)]
pub struct Snapshots {
    upstream: SocketAddr,
    secret: String,
    state: Mutex<State>,
    wake: Notify,
}

impl Snapshots {
    pub fn new(upstream: SocketAddr, secret: String) -> Self {
        Self {
            upstream,
            secret,
            state: Mutex::new(State::default()),
            wake: Notify::new(),
        }
    }

    /// A pulse asks. It is told what is held now and never waits for a poll: on the first pulse
    /// after polling was off, polling starts and this answer is already decided.
    pub fn asked(&self) -> Seen {
        let now = Instant::now();
        let (turned_on, seen, line) = {
            let mut state = self.state.lock().expect("no panic is held across this");
            let (turned_on, seen) = state.asked_at(now);
            let line = (state.said != Some(seen.state)).then(|| {
                state.said = Some(seen.state);
                let taken_at = state.held.as_ref().map(|held| held.snapshot.taken_at);
                format!(
                    "snapshot {:?}: age {:?}, taken_at {taken_at:?}, polls timed out {}",
                    seen.state, seen.age, state.polls_timed_out
                )
            });
            (turned_on, seen, line)
        };
        if let Some(line) = line {
            say(&line);
        }
        if turned_on {
            self.wake.notify_one();
        }
        seen
    }

    /// Polls while pulses ask. Started once, by the front, and never returns.
    pub async fn poll_while_asked(&self) {
        loop {
            self.wake.notified().await;
            let mut in_hand = None;
            loop {
                let tick = Instant::now();
                {
                    let mut state = self.state.lock().expect("no panic is held across this");
                    if !state.keep_polling(tick) {
                        break;
                    }
                }
                let polled = self.poll(&mut in_hand).await;
                {
                    let mut state = self.state.lock().expect("no panic is held across this");
                    if polled == Polled::Nothing {
                        state.polls_timed_out += 1;
                    }
                    state.apply(polled, tick);
                }
                tokio::time::sleep_until((tick + POLL_EVERY).into()).await;
            }
        }
    }

    /// One poll, within [`POLL_TIMEOUT`].
    ///
    /// **A poll that comes to nothing stays in hand, and the next tick looks at it rather than
    /// starting another,** so it really is one at a time:
    ///
    /// - **A connection still being made.** Windows retries a refused loopback connection for about
    ///   2 s, far past the timeout, so a poll that gave up on it could never see the refusal that
    ///   says Python is gone.
    /// - **A request sent and unanswered.** A suspended Python's port goes on accepting into its
    ///   backlog, and it can't accept any of them. A new connection each tick would fill that
    ///   backlog in seconds, and then be refused, and a suspended Python would read as a gone one.
    ///   Held open, this also hears a kill as soon as it happens.
    ///
    /// An answer that comes on a later tick is late, so it is discarded, and this tick asks again.
    async fn poll(&self, in_hand: &mut Option<InHand>) -> Polled {
        let deadline = tokio::time::Instant::now() + POLL_TIMEOUT;
        let connecting = match in_hand.take() {
            Some(InHand::Waiting(stream, got)) => match read_to_end(stream, got, deadline).await {
                Read::NotYet(stream, got) => {
                    *in_hand = Some(InHand::Waiting(stream, got));
                    return Polled::Nothing;
                }
                Read::Gone => return Polled::Gone,
                Read::Whole(_) | Read::Unreadable => None,
            },
            Some(InHand::Connecting(task)) => Some(task),
            None => None,
        };
        let upstream = self.upstream;
        let mut task = connecting.unwrap_or_else(|| tokio::spawn(TcpStream::connect(upstream)));
        let mut stream = match tokio::time::timeout_at(deadline, &mut task).await {
            Err(_) => {
                *in_hand = Some(InHand::Connecting(task));
                return Polled::Nothing;
            }
            Ok(Err(_)) => return Polled::Nothing,
            Ok(Ok(Err(error))) if is_gone(&error) => return Polled::Gone,
            Ok(Ok(Err(_))) => return Polled::Nothing,
            Ok(Ok(Ok(stream))) => stream,
        };
        let _ = stream.set_nodelay(true);
        let request = format!(
            "GET {LIVE_PATH} HTTP/1.1\r\nHost: {}\r\n{SECRET_HEADER}: {}\r\nConnection: close\r\n\r\n",
            self.upstream, self.secret
        );
        match tokio::time::timeout_at(deadline, stream.write_all(request.as_bytes())).await {
            Err(_) => return Polled::Nothing,
            Ok(Err(error)) if is_gone(&error) => return Polled::Gone,
            Ok(Err(_)) => return Polled::Nothing,
            Ok(Ok(())) => {}
        }
        match read_to_end(stream, Vec::new(), deadline).await {
            Read::Whole(answer) => read_answer(&answer),
            Read::NotYet(stream, got) => {
                *in_hand = Some(InHand::Waiting(stream, got));
                Polled::Nothing
            }
            Read::Gone => Polled::Gone,
            Read::Unreadable => Polled::Nothing,
        }
    }
}

/// Whether this is all of an answer framed by `Content-Length`, as Python's are. Ending the
/// connection is not to be counted on, though the request asks for it: `door_recorder` keeps it open.
fn is_whole(got: &[u8]) -> bool {
    let Some(end) = got.windows(4).position(|window| window == b"\r\n\r\n") else {
        return false;
    };
    let declared = got[..end].split(|byte| *byte == b'\n').find_map(|line| {
        let line = std::str::from_utf8(line).ok()?;
        let (name, value) = line.split_once(':')?;
        name.eq_ignore_ascii_case("content-length")
            .then(|| value.trim().parse::<usize>().ok())?
    });
    declared.is_some_and(|declared| got.len() >= end + 4 + declared)
}

/// Reads until the answer ends or the deadline passes.
async fn read_to_end(
    mut stream: TcpStream,
    mut got: Vec<u8>,
    deadline: tokio::time::Instant,
) -> Read {
    let mut chunk = [0; 16 * 1024];
    loop {
        let read = tokio::time::timeout_at(deadline, stream.read(&mut chunk)).await;
        match read {
            Err(_) => return Read::NotYet(stream, got),
            Ok(Ok(0)) if got.is_empty() => return Read::Gone,
            Ok(Ok(0)) => return Read::Whole(got),
            Ok(Ok(count)) => {
                got.extend_from_slice(&chunk[..count]);
                if is_whole(&got) {
                    return Read::Whole(got);
                }
                if got.len() > MOST_ANSWER {
                    return Read::Unreadable;
                }
            }
            Ok(Err(error)) if got.is_empty() && is_gone(&error) => return Read::Gone,
            Ok(Err(_)) => return Read::Unreadable,
        }
    }
}

fn is_gone(error: &std::io::Error) -> bool {
    use std::io::ErrorKind::{ConnectionAborted, ConnectionRefused, ConnectionReset};
    matches!(
        error.kind(),
        ConnectionRefused | ConnectionReset | ConnectionAborted
    )
}

/// A whole answer, read to its end.
fn read_answer(answer: &[u8]) -> Polled {
    let Some(end) = answer.windows(4).position(|window| window == b"\r\n\r\n") else {
        return Polled::Nothing;
    };
    let is_ok = answer[..end]
        .split(|byte| *byte == b'\r')
        .next()
        .is_some_and(|line| {
            line.starts_with(b"HTTP/1.1 200 ") || line.starts_with(b"HTTP/1.0 200 ")
        });
    if !is_ok {
        return Polled::Nothing;
    }
    match PollAnswer::read(&answer[end + 4..]) {
        PollAnswer::Snapshot(snapshot) => Polled::Good(Box::new(snapshot)),
        PollAnswer::UnknownSchema(_) => Polled::UnknownSchema,
        PollAnswer::Unreadable => Polled::Nothing,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::live::{LiveFields, UNAVAILABLE_AFTER};

    fn snapshot(boot: &str, generation: u64, hash: &str) -> Polled {
        Polled::Good(Box::new(LiveSnapshot {
            schema: 1,
            boot_id: boot.into(),
            generation,
            live_hash: hash.into(),
            taken_at: 1.0,
            fields: LiveFields {
                live_now: Vec::new(),
                run_marks: Vec::new(),
            },
        }))
    }

    const fn ms(n: u64) -> Duration {
        Duration::from_millis(n)
    }

    /// Polling on from `start`, with one good answer sent then.
    fn fresh_at(start: Instant) -> State {
        let mut state = State::default();
        state.asked_at(start);
        state.apply(snapshot("b", 1, "h1"), start);
        state
    }

    #[test]
    fn nothing_held_is_unavailable_with_no_age() {
        let now = Instant::now();
        let mut state = State::default();
        let (turned_on, seen) = state.asked_at(now);
        assert!(turned_on);
        assert_eq!(
            seen,
            Seen {
                state: Liveness::Unavailable,
                hash: None,
                age: None
            }
        );
        let mark = seen.mark().unwrap();
        assert_eq!(mark.state, Liveness::Unavailable);
        assert_eq!(mark.age_ms, None);
    }

    #[test]
    fn age_counts_from_the_poll_s_send_time_and_a_failed_poll_changes_nothing() {
        let start = Instant::now();
        let mut state = fresh_at(start);
        assert_eq!(state.seen(start + ms(2000)).state, Liveness::Fresh);
        state.apply(Polled::Nothing, start + ms(500));
        let seen = state.seen(start + ms(2001));
        assert_eq!(seen.state, Liveness::Stale);
        assert_eq!(seen.hash.as_deref(), Some("h1"));
        assert_eq!(seen.age, Some(ms(2001)));
        assert_eq!(seen.mark().unwrap().age_ms, Some(2001));
        // Answered late: the age is the send's.
        state.apply(snapshot("b", 1, "h1"), start + ms(1900));
        assert_eq!(state.seen(start + ms(2001)).state, Liveness::Fresh);
    }

    #[test]
    fn a_stalled_python_goes_stale_then_unavailable() {
        let start = Instant::now();
        let state = fresh_at(start);
        assert_eq!(state.seen(start + UNAVAILABLE_AFTER).state, Liveness::Stale);
        assert_eq!(
            state.seen(start + UNAVAILABLE_AFTER + ms(1)).state,
            Liveness::Unavailable
        );
    }

    #[test]
    fn a_refused_poll_is_unavailable_at_once_until_a_good_answer() {
        let start = Instant::now();
        let mut state = fresh_at(start);
        state.apply(Polled::Gone, start + ms(100));
        let seen = state.seen(start + ms(100));
        assert_eq!(seen.state, Liveness::Unavailable);
        assert_eq!(seen.age, Some(ms(100)));
        // A timeout says nothing about that.
        state.apply(Polled::Nothing, start + ms(600));
        assert_eq!(state.seen(start + ms(600)).state, Liveness::Unavailable);
        state.apply(snapshot("b", 2, "h2"), start + ms(1100));
        let seen = state.seen(start + ms(1100));
        assert_eq!(seen.state, Liveness::Fresh);
        assert_eq!(seen.hash.as_deref(), Some("h2"));
    }

    #[test]
    fn a_new_boot_or_a_lower_generation_passes_through_unavailable() {
        let start = Instant::now();
        for discarding in [snapshot("other", 9, "new"), snapshot("b", 0, "new")] {
            let mut state = fresh_at(start);
            state.apply(discarding.clone(), start + ms(500));
            assert_eq!(
                state.seen(start + ms(500)),
                Seen {
                    state: Liveness::Unavailable,
                    hash: None,
                    age: None
                }
            );
            state.apply(discarding, start + ms(1000));
            let seen = state.seen(start + ms(1000));
            assert_eq!(seen.state, Liveness::Fresh);
            assert_eq!(seen.hash.as_deref(), Some("new"));
        }
    }

    #[test]
    fn a_refused_poll_then_a_new_boot_is_one_change_of_hash() {
        let start = Instant::now();
        let mut state = fresh_at(start);
        state.apply(Polled::Gone, start + ms(100));
        state.apply(snapshot("other", 1, "new"), start + ms(600));
        assert_eq!(state.seen(start + ms(600)).state, Liveness::Unavailable);
        state.apply(snapshot("other", 1, "new"), start + ms(1100));
        assert_eq!(state.seen(start + ms(1100)).state, Liveness::Fresh);
    }

    #[test]
    fn an_unknown_schema_discards_and_the_next_known_one_is_taken() {
        let start = Instant::now();
        let mut state = fresh_at(start);
        state.apply(Polled::UnknownSchema, start + ms(500));
        assert_eq!(state.seen(start + ms(500)).state, Liveness::Unavailable);
        assert_eq!(state.seen(start + ms(500)).hash, None);
        state.apply(snapshot("b", 1, "h1"), start + ms(1000));
        assert_eq!(state.seen(start + ms(1000)).state, Liveness::Fresh);
    }

    #[test]
    fn polling_stops_without_pulses_and_a_resume_is_stale_with_its_full_bound() {
        let start = Instant::now();
        let mut state = fresh_at(start);
        assert!(state.keep_polling(start + POLL_WHILE_ASKED_WITHIN));
        assert!(!state.keep_polling(start + POLL_WHILE_ASKED_WITHIN + ms(1)));

        let resume = start + Duration::from_secs(60);
        let (turned_on, seen) = state.asked_at(resume);
        assert!(turned_on);
        assert_eq!(seen.state, Liveness::Stale);
        assert_eq!(seen.age, Some(Duration::from_secs(60)));
        assert_eq!(seen.hash.as_deref(), Some("h1"));
        // Still on: the next pulse doesn't turn it on again.
        assert!(!state.asked_at(resume + ms(1)).0);
        assert_eq!(
            state.seen(resume + UNAVAILABLE_AFTER).state,
            Liveness::Stale
        );
        assert_eq!(
            state.seen(resume + UNAVAILABLE_AFTER + ms(1)).state,
            Liveness::Unavailable
        );
    }

    #[test]
    fn an_answer_is_whole_by_its_length_and_otherwise_by_its_end() {
        let head = b"HTTP/1.1 200 OK\r\nContent-Type: x\r\ncontent-LENGTH: 3\r\n\r\n";
        assert!(!is_whole(b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n"));
        assert!(!is_whole(head));
        assert!(!is_whole(&[&head[..], b"ab"].concat()));
        assert!(is_whole(&[&head[..], b"abc"].concat()));
        assert!(!is_whole(b"HTTP/1.1 200 OK\r\n\r\nabc"));
    }

    #[test]
    fn an_answer_is_read_only_from_a_200() {
        let body = br#"{"schema": 1, "boot_id": "b", "generation": 1, "live_hash": "h", "taken_at": 1.0, "fields": {"live_now": [], "run_marks": []}}"#;
        let with = |head: &str| [head.as_bytes(), b"\r\n\r\n", body].concat();
        assert!(matches!(
            read_answer(&with("HTTP/1.1 200 OK\r\nContent-Type: application/json")),
            Polled::Good(_)
        ));
        assert_eq!(
            read_answer(&with("HTTP/1.1 403 Forbidden")),
            Polled::Nothing
        );
        assert_eq!(read_answer(b"HTTP/1.1 200 OK\r\n"), Polled::Nothing);
        assert_eq!(
            read_answer(b"HTTP/1.1 200 OK\r\n\r\n<index>"),
            Polled::Nothing
        );
        assert_eq!(
            read_answer(b"HTTP/1.1 200 OK\r\n\r\n{\"schema\": 2}"),
            Polled::UnknownSchema
        );
    }
}
