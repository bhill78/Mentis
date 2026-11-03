//! The front's client of `GET /private/live`, what the pulse's second half comes from. Contract:
//! `docs/rust/contracts/live-snapshot.md`; the type, timings and state rule are in [`crate::live`].
//!
//! It only ever asks because a pulse was asked for recently, one poll at a time, with no retry but
//! the next tick. Nothing here is used for authority or a write decision.

use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use mentis_ops::overlay::Overlay;
use mentis_record::{Position, ReadClass, RecordReader};
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

/// How long a poll waits for its durable position before asking without one. A read of the record
/// can block for up to `BUSY_TIMEOUT`, and neither the pulse's hash nor hearing Python go may wait
/// for that: a poll with no marker is still fresh, and forwards what its overlay would change.
pub const SAMPLE_WITHIN: Duration = Duration::from_millis(50);

/// Where the record stands now, or `None` if that can't be said. Blocking.
pub type Sampler = Arc<dyn Fn() -> Option<Position> + Send + Sync>;

/// A poll that has not come to anything yet, kept for the next tick. See [`Snapshots::poll`].
#[derive(Debug)]
enum InHand {
    Connecting(JoinHandle<std::io::Result<TcpStream>>),
    /// Open, with nothing sent on it. Where the next poll asks.
    Connected(TcpStream),
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
    /// A body that is the envelope of a schema this build reads, with where the record stood before
    /// this poll asked. A late answer is discarded, so the two can't be from different polls.
    Good(Box<LiveSnapshot>, Option<Position>),
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
    /// Where the record stood just before it was sent. See [`Overlay`].
    marker: Option<Position>,
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

    /// What a read that shows live state has to work with: nothing unless what is held is fresh, so
    /// a read with no overlay forwards, and saying Python is gone is the forward's. Asking doesn't
    /// turn polling on: only a pulse does that, and without one this goes stale, and forwards.
    pub fn overlay(&self, now: Instant) -> Option<Overlay> {
        let held = self.held.as_ref()?;
        (self.seen(now).state == Liveness::Fresh).then(|| {
            let fields = &held.snapshot.fields;
            Overlay::new(
                fields.active_executions.clone(),
                fields.run_observations.clone(),
                held.marker,
            )
        })
    }

    /// What a poll sent at `sent` came to.
    pub fn apply(&mut self, polled: Polled, sent: Instant) {
        match polled {
            Polled::Good(answer, marker) => {
                self.gone = false;
                match &self.held {
                    Some(held) if discards(&held.snapshot, &answer) => self.held = None,
                    _ => {
                        self.held = Some(Held {
                            snapshot: *answer,
                            sent,
                            marker,
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
pub struct Snapshots {
    upstream: SocketAddr,
    secret: String,
    sampler: Option<Sampler>,
    state: Mutex<State>,
    wake: Notify,
}

impl std::fmt::Debug for Snapshots {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Snapshots")
            .field("upstream", &self.upstream)
            .field("state", &self.state)
            .finish_non_exhaustive()
    }
}

impl Snapshots {
    /// With no record to sample: every poll has no marker, so any overlay that changes an answer
    /// forwards.
    pub fn new(upstream: SocketAddr, secret: String) -> Self {
        Self::with_sampler(upstream, secret, None)
    }

    /// Each poll marked with where `record` stands just before it asks.
    pub fn sampling(upstream: SocketAddr, secret: String, record: Arc<dyn RecordReader>) -> Self {
        let sampler: Sampler = Arc::new(move || {
            let scope = record.read_scope(ReadClass::Foreground).ok()?;
            Some(scope.position())
        });
        Self::with_sampler(upstream, secret, Some(sampler))
    }

    pub fn with_sampler(upstream: SocketAddr, secret: String, sampler: Option<Sampler>) -> Self {
        Self {
            upstream,
            secret,
            sampler,
            state: Mutex::new(State::default()),
            wake: Notify::new(),
        }
    }

    /// See [`State::overlay`].
    pub fn overlay(&self) -> Option<Overlay> {
        self.state
            .lock()
            .expect("no panic is held across this")
            .overlay(Instant::now())
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
            let mut sampling = None;
            loop {
                let tick = Instant::now();
                {
                    let mut state = self.state.lock().expect("no panic is held across this");
                    if !state.keep_polling(tick) {
                        break;
                    }
                }
                let polled = self.poll(&mut in_hand, &mut sampling).await;
                {
                    let mut state = self.state.lock().expect("no panic is held across this");
                    if polled == Polled::Nothing {
                        state.polls_timed_out += 1;
                    }
                    state.apply(polled, tick);
                }
                let next = (tick + POLL_EVERY).into();
                if self.listen_until(next, &mut in_hand).await {
                    let mut state = self.state.lock().expect("no panic is held across this");
                    state.apply(Polled::Gone, Instant::now());
                }
                tokio::time::sleep_until(next).await;
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
    ///
    /// An answer that comes on a later tick is late, so it is discarded, and this tick asks again.
    async fn poll(
        &self,
        in_hand: &mut Option<InHand>,
        sampling: &mut Option<JoinHandle<Option<Position>>>,
    ) -> Polled {
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
            Some(InHand::Connected(stream)) => {
                return self.ask(stream, in_hand, sampling, deadline).await;
            }
            None => None,
        };
        let upstream = self.upstream;
        let mut task = connecting.unwrap_or_else(|| tokio::spawn(TcpStream::connect(upstream)));
        let stream = match tokio::time::timeout_at(deadline, &mut task).await {
            Err(_) => {
                *in_hand = Some(InHand::Connecting(task));
                return Polled::Nothing;
            }
            Ok(Err(_)) => return Polled::Nothing,
            Ok(Ok(Err(error))) if is_gone(&error) => return Polled::Gone,
            Ok(Ok(Err(_))) => return Polled::Nothing,
            Ok(Ok(Ok(stream))) => stream,
        };
        self.ask(stream, in_hand, sampling, deadline).await
    }

    /// Where the record stands, for a poll about to ask on `stream`, within [`SAMPLE_WITHIN`].
    ///
    /// **It goes on listening while it waits,** because `listen_until` isn't running now and a kill
    /// has to be heard as it happens. A sample that isn't back in time stays in `sampling`, so
    /// there is only ever one, and the next poll waits for that one instead of starting another:
    /// taken earlier, it is still from before that poll asks, which is all a marker has to be.
    async fn sampled(
        &self,
        stream: &mut TcpStream,
        sampling: &mut Option<JoinHandle<Option<Position>>>,
    ) -> Result<Option<Position>, Polled> {
        let Some(sampler) = &self.sampler else {
            return Ok(None);
        };
        let mut task = sampling.take().unwrap_or_else(|| {
            let sampler = sampler.clone();
            tokio::task::spawn_blocking(move || sampler())
        });
        let mut nothing_is_expected = [0; 1];
        tokio::select! {
            done = &mut task => Ok(done.ok().flatten()),
            () = tokio::time::sleep(SAMPLE_WITHIN) => {
                *sampling = Some(task);
                Ok(None)
            }
            read = stream.read(&mut nothing_is_expected) => {
                *sampling = Some(task);
                Err(match read {
                    Ok(0) => Polled::Gone,
                    Err(error) if is_gone(&error) => Polled::Gone,
                    // Something said unasked. This connection isn't used again.
                    Ok(_) | Err(_) => Polled::Nothing,
                })
            }
        }
    }

    /// Asks on this connection, and reads what comes back until the deadline.
    async fn ask(
        &self,
        mut stream: TcpStream,
        in_hand: &mut Option<InHand>,
        sampling: &mut Option<JoinHandle<Option<Position>>>,
        deadline: tokio::time::Instant,
    ) -> Polled {
        let _ = stream.set_nodelay(true);
        let marker = match self.sampled(&mut stream, sampling).await {
            Ok(marker) => marker,
            Err(heard) => return heard,
        };
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
            Read::Whole(answer) => read_answer(&answer, marker),
            Read::NotYet(stream, got) => {
                *in_hand = Some(InHand::Waiting(stream, got));
                Polled::Nothing
            }
            Read::Gone => Polled::Gone,
            Read::Unreadable => Polled::Nothing,
        }
    }

    /// Between polls, until `until`, listens to what is in hand, and says whether that heard Python
    /// go. **A connection is always in hand here, so a kill is heard as it happens,** rather than by
    /// the next poll's new connection, which Windows would keep pending for about 2.5 s before
    /// saying it was refused. With nothing sent on it, it isn't a poll, and nothing else is ever
    /// open beside it, so a suspended Python's backlog holds only this one.
    async fn listen_until(
        &self,
        until: tokio::time::Instant,
        in_hand: &mut Option<InHand>,
    ) -> bool {
        loop {
            match in_hand.take() {
                None => {
                    let connecting = tokio::spawn(TcpStream::connect(self.upstream));
                    *in_hand = Some(InHand::Connecting(connecting));
                }
                Some(InHand::Connecting(mut task)) => {
                    match tokio::time::timeout_at(until, &mut task).await {
                        Err(_) => {
                            *in_hand = Some(InHand::Connecting(task));
                            return false;
                        }
                        Ok(Ok(Ok(stream))) => *in_hand = Some(InHand::Connected(stream)),
                        Ok(Ok(Err(error))) => return is_gone(&error),
                        Ok(Err(_)) => return false,
                    }
                }
                Some(InHand::Connected(mut stream)) => {
                    let mut nothing_is_expected = [0; 1];
                    let read = stream.read(&mut nothing_is_expected);
                    match tokio::time::timeout_at(until, read).await {
                        Err(_) => {
                            *in_hand = Some(InHand::Connected(stream));
                            return false;
                        }
                        Ok(Ok(0)) => return true,
                        Ok(Err(error)) => return is_gone(&error),
                        // Something said unasked. This connection isn't used again.
                        Ok(Ok(_)) => return false,
                    }
                }
                Some(InHand::Waiting(stream, got)) => {
                    match read_to_end(stream, got, until).await {
                        Read::NotYet(stream, got) => {
                            *in_hand = Some(InHand::Waiting(stream, got));
                            return false;
                        }
                        Read::Gone => return true,
                        // Late, so discarded, and the next poll needs a connection.
                        Read::Whole(_) | Read::Unreadable => {}
                    }
                }
            }
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

/// A whole answer, read to its end, to the poll marked `marker`.
fn read_answer(answer: &[u8], marker: Option<Position>) -> Polled {
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
        PollAnswer::Snapshot(snapshot) => Polled::Good(Box::new(snapshot), marker),
        PollAnswer::UnknownSchema(_) => Polled::UnknownSchema,
        PollAnswer::Unreadable => Polled::Nothing,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::live::{LiveFields, UNAVAILABLE_AFTER};

    fn snapshot(boot: &str, generation: u64, hash: &str) -> Polled {
        Polled::Good(
            Box::new(LiveSnapshot {
                schema: 1,
                boot_id: boot.into(),
                generation,
                live_hash: hash.into(),
                taken_at: 1.0,
                fields: LiveFields::default(),
            }),
            None,
        )
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

    const AT: Position = Position {
        entry: 1,
        operational: 2,
        delivery: 3,
    };

    fn marked(marker: Option<Position>) -> Polled {
        let Polled::Good(answer, _) = snapshot("b", 1, "h1") else {
            unreachable!()
        };
        Polled::Good(answer, marker)
    }

    #[test]
    fn an_overlay_is_had_only_while_fresh_and_carries_its_poll_s_marker() {
        let start = Instant::now();
        let mut state = State::default();
        assert!(state.overlay(start).is_none(), "nothing held");
        state.asked_at(start);
        state.apply(marked(Some(AT)), start);
        let overlay = state.overlay(start + ms(2000)).expect("fresh");
        assert!(overlay.coherent_with(AT));
        assert!(state.overlay(start + ms(2001)).is_none(), "stale");
        state.apply(Polled::Gone, start + ms(100));
        assert!(state.overlay(start + ms(100)).is_none(), "gone");
    }

    #[test]
    fn a_new_poll_s_marker_replaces_the_last_and_a_failed_poll_keeps_it() {
        let start = Instant::now();
        let later = Position { entry: 9, ..AT };
        let mut state = State::default();
        state.asked_at(start);
        state.apply(marked(Some(AT)), start);
        state.apply(Polled::Nothing, start + ms(500));
        assert!(!state.overlay(start + ms(500)).unwrap().coherent_with(later));
        state.apply(marked(Some(later)), start + ms(1000));
        assert!(
            state
                .overlay(start + ms(1000))
                .unwrap()
                .coherent_with(later)
        );
        state.apply(marked(None), start + ms(1500));
        assert!(!state.overlay(start + ms(1500)).unwrap().coherent_with(AT));
    }

    /// A connected pair: what a poll asks on, and Python's end of it.
    async fn connected() -> (TcpStream, TcpStream, SocketAddr) {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let (ours, theirs) = tokio::join!(TcpStream::connect(address), listener.accept());
        (ours.unwrap(), theirs.unwrap().0, address)
    }

    /// A sampler that doesn't come back until the sender goes.
    fn held_sampler() -> (Sampler, std::sync::mpsc::Sender<()>) {
        let (release, held) = std::sync::mpsc::channel::<()>();
        let held = Mutex::new(held);
        let sampler: Sampler = Arc::new(move || {
            let _ = held.lock().unwrap().recv();
            Some(AT)
        });
        (sampler, release)
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn a_kill_during_a_sample_is_heard_at_once() {
        let (mut ours, theirs, address) = connected().await;
        let (sampler, release) = held_sampler();
        let snapshots = Snapshots::with_sampler(address, "s".into(), Some(sampler));
        let mut sampling = None;
        drop(theirs);
        let started = Instant::now();
        let heard = snapshots.sampled(&mut ours, &mut sampling).await;
        assert_eq!(heard, Err(Polled::Gone));
        assert!(started.elapsed() < SAMPLE_WITHIN, "{:?}", started.elapsed());
        drop(release);
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn a_slow_sample_leaves_this_poll_no_marker_and_the_next_gets_that_one() {
        let (mut ours, _theirs, address) = connected().await;
        let (sampler, release) = held_sampler();
        let snapshots = Snapshots::with_sampler(address, "s".into(), Some(sampler));
        let mut sampling = None;
        let started = Instant::now();
        assert_eq!(snapshots.sampled(&mut ours, &mut sampling).await, Ok(None));
        assert!(started.elapsed() < POLL_TIMEOUT, "{:?}", started.elapsed());
        assert!(sampling.is_some(), "one sample, kept");
        drop(release);
        assert_eq!(
            snapshots.sampled(&mut ours, &mut sampling).await,
            Ok(Some(AT))
        );
        assert!(sampling.is_none());
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn a_failed_sample_is_no_marker_and_no_sampler_is_none() {
        let (mut ours, _theirs, address) = connected().await;
        let failing: Sampler = Arc::new(|| None);
        let snapshots = Snapshots::with_sampler(address, "s".into(), Some(failing));
        let mut sampling = None;
        assert_eq!(snapshots.sampled(&mut ours, &mut sampling).await, Ok(None));
        let snapshots = Snapshots::new(address, "s".into());
        assert_eq!(snapshots.sampled(&mut ours, &mut sampling).await, Ok(None));
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
            read_answer(
                &with("HTTP/1.1 200 OK\r\nContent-Type: application/json"),
                None
            ),
            Polled::Good(..)
        ));
        assert_eq!(
            read_answer(&with("HTTP/1.1 403 Forbidden"), None),
            Polled::Nothing
        );
        assert_eq!(read_answer(b"HTTP/1.1 200 OK\r\n", None), Polled::Nothing);
        assert_eq!(
            read_answer(b"HTTP/1.1 200 OK\r\n\r\n<index>", None),
            Polled::Nothing
        );
        assert_eq!(
            read_answer(b"HTTP/1.1 200 OK\r\n\r\n{\"schema\": 2}", None),
            Polled::UnknownSchema
        );
    }
}
