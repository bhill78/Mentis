//! The front's copy of the grant table. `docs/rust/R3-mirror.md`, sections 2 to 4.
//!
//! [`State`] is pure, with no clock of its own, as `snapshot.rs`'s is, so every rule can be tested at
//! exact moments. [`Mirror`] is the client: one location and pull at a time, a poll while grants are
//! held, and nothing retried on a timer.
//!
//! **Fail closed means forward, never refuse and never serve.** Python holds the table, so
//! forwarding is always the right answer, and it costs only speed.

use std::collections::HashMap;
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::Deserialize;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::Notify;

use super::held::{BrainFile, Ended, ProcessWatch};
use crate::launch::SECRET_HEADER;

pub const SCHEMA: u64 = 1;
pub const GRANTS_PATH: &str = "/private/grants";
const POSITION_PATH: &str = "/private/grants/position";

/// How long a confirmation from Python, measured from when it was *sent*, says the mirror is current.
pub const LEASE: Duration = Duration::from_secs(3);
pub const POSITION_EVERY: Duration = Duration::from_millis(500);
pub const POSITION_TIMEOUT: Duration = Duration::from_millis(250);
pub const PULL_TIMEOUT: Duration = Duration::from_millis(500);
/// Past it, a push or request body isn't read at all.
pub const BODY_LOOK: u64 = 1024 * 1024;
const MOST_ANSWER: usize = 64 * 1024 * 1024;

pub const CLAIM: &str = ".mentis.claim";
pub const SERVE_LOCK: &str = ".mentis.serve.lock";
pub const OWNER_LOCK: &str = ".mentis.owner.lock";

/// What the mirror holds of a grant, and all the door needs: `R3-mirror.md`, section 2.
#[derive(Clone, Debug, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Grant {
    pub corpus: String,
    pub scope: String,
    pub operations: Option<Vec<String>>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Push {
    pub boot_id: String,
    pub generation: u64,
    pub key: String,
    /// `None` is a `drop`.
    pub grant: Option<Grant>,
}

/// A push's body, or `None` if it is malformed. Then the table is discarded before anything answers.
pub fn parse_push(body: &[u8]) -> Option<Push> {
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Wire {
        schema: u64,
        boot_id: String,
        generation: u64,
        key: String,
        grant: Option<Grant>,
    }
    if body.len() as u64 > BODY_LOOK {
        return None;
    }
    // `grant` absent would read as null: a field missing is malformed.
    let value: serde_json::Value = serde_json::from_slice(body).ok()?;
    if !value.as_object()?.contains_key("grant") {
        return None;
    }
    let wire: Wire = serde_json::from_value(value).ok()?;
    let is_hex = |text: &str, length: usize| {
        text.len() == length
            && text
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    };
    (wire.schema == SCHEMA && is_hex(&wire.key, 64)).then_some(Push {
        boot_id: wire.boot_id,
        generation: wire.generation,
        key: wire.key,
        grant: wire.grant,
    })
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Position {
    pub boot_id: String,
    pub generation: u64,
    pub down: bool,
    pub pid: u32,
}

/// What a position or a pull's body came to.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Said<T> {
    Good(T),
    UnknownSchema,
    Unreadable,
}

pub fn parse_position(body: &[u8]) -> Said<Position> {
    #[derive(Deserialize)]
    struct Wire {
        boot_id: String,
        generation: u64,
        down: bool,
        pid: u32,
    }
    parse_said(body, |wire: Wire| Position {
        boot_id: wire.boot_id,
        generation: wire.generation,
        down: wire.down,
        pid: wire.pid,
    })
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Pull {
    pub boot_id: String,
    pub generation: u64,
    pub corpus: String,
    pub grants: HashMap<String, Grant>,
}

pub fn parse_pull(body: &[u8]) -> Said<Pull> {
    #[derive(Deserialize)]
    struct Wire {
        boot_id: String,
        generation: u64,
        corpus: String,
        grants: HashMap<String, Grant>,
    }
    parse_said(body, |wire: Wire| Pull {
        boot_id: wire.boot_id,
        generation: wire.generation,
        corpus: wire.corpus,
        grants: wire.grants,
    })
}

fn parse_said<W: serde::de::DeserializeOwned, T>(body: &[u8], made: impl Fn(W) -> T) -> Said<T> {
    let Ok(value) = serde_json::from_slice::<serde_json::Value>(body) else {
        return Said::Unreadable;
    };
    match value.get("schema").and_then(serde_json::Value::as_u64) {
        Some(SCHEMA) => {}
        Some(_) => return Said::UnknownSchema,
        None => return Said::Unreadable,
    }
    serde_json::from_value(value).map_or(Said::Unreadable, |wire| Said::Good(made(wire)))
}

/// A table being answered from.
pub struct Held<W, O> {
    boot: String,
    pid: u32,
    watch: Arc<W>,
    owner: Arc<O>,
    generation: u64,
    corpus: String,
    table: HashMap<String, Grant>,
    confirmed_sent: Instant,
    behind: bool,
}

enum Phase<W, O> {
    /// Nothing to serve from.
    Empty,
    /// Asking position who Python is. Pushes that arrive meanwhile wait.
    Locating { pending: Vec<Push> },
    /// One pull at a time, after the watch is open.
    Pulling {
        boot: String,
        pid: u32,
        watch: Arc<W>,
        sent: Instant,
        pending: Vec<Push>,
    },
    Held(Held<W, O>),
}

/// What the door may do with a read.
pub enum Serve<W, O> {
    /// The mirror says nothing about this: forward. Names why, for the count of forwards per reason.
    Forward(&'static str),
    Grant(Granted<W, O>),
}

/// A grant the mirror answers for, and everything the tail checks it against.
pub struct Granted<W, O> {
    pub grant: Grant,
    pub boot: String,
    pub corpus: String,
    pub watch: Arc<W>,
    pub owner: Arc<O>,
}

pub struct State<W, O> {
    phase: Phase<W, O>,
    /// A trigger has happened and no location has begun for it.
    wanted: bool,
}

impl<W: Ended, O> Default for State<W, O> {
    fn default() -> Self {
        Self {
            phase: Phase::Empty,
            wanted: false,
        }
    }
}

impl<W: Ended, O> State<W, O> {
    /// A trigger: front start, or a presented grant while not `Held`. Starts at `Locating`.
    pub fn trigger(&mut self) {
        self.wanted = true;
    }

    /// Whether a location should begin now, which it then has.
    pub fn begin(&mut self) -> bool {
        if !std::mem::take(&mut self.wanted) {
            return false;
        }
        let pending = match std::mem::replace(&mut self.phase, Phase::Empty) {
            Phase::Locating { pending } | Phase::Pulling { pending, .. } => pending,
            Phase::Empty | Phase::Held(_) => Vec::new(),
        };
        self.phase = Phase::Locating { pending };
        true
    }

    /// A position or pull was refused, failed or timed out. `pending` goes with it, because any
    /// later pull includes those changes. Tried again at the next trigger, not on a timer.
    pub fn failed(&mut self) {
        self.phase = Phase::Empty;
    }

    /// Close the watch and the owner handle, and pull. The event table's "discard".
    pub fn discard(&mut self) {
        self.phase = Phase::Empty;
        self.wanted = true;
    }

    /// The answer to a position while `Locating`. Whether to send the pull now: the watch is open
    /// before it goes, which is what makes it the right process's (`R3-mirror.md`, the boot check).
    pub fn located(
        &mut self,
        said: Said<Position>,
        open_watch: impl FnOnce(u32) -> Option<W>,
        now: Instant,
    ) -> bool {
        let Phase::Locating { pending } = std::mem::replace(&mut self.phase, Phase::Empty) else {
            return false;
        };
        let Said::Good(position) = said else {
            return false;
        };
        let Some(watch) = open_watch(position.pid) else {
            return false;
        };
        self.phase = Phase::Pulling {
            boot: position.boot_id,
            pid: position.pid,
            watch: Arc::new(watch),
            sent: now,
            pending,
        };
        true
    }

    /// The answer to the pull. `adopt` reads the claim and opens the owner lock's file, and nothing
    /// is served for a boot that doesn't own this Brain.
    pub fn pulled(&mut self, said: Said<Pull>, adopt: impl FnOnce(&str) -> Option<O>) {
        let Phase::Pulling {
            boot,
            pid,
            watch,
            sent,
            pending,
        } = std::mem::replace(&mut self.phase, Phase::Empty)
        else {
            return;
        };
        let pull = match said {
            Said::Good(pull) => pull,
            Said::UnknownSchema | Said::Unreadable => return,
        };
        if pull.boot_id != boot {
            // It may be on the wrong process. The discard is a trigger.
            self.discard();
            return;
        }
        let Some(owner) = adopt(&boot) else {
            return;
        };
        let mut held = Held {
            boot,
            pid,
            watch,
            owner: Arc::new(owner),
            generation: pull.generation,
            corpus: pull.corpus,
            table: pull.grants,
            confirmed_sent: sent,
            behind: false,
        };
        for push in pending {
            if push.boot_id != held.boot || push.generation <= held.generation {
                continue;
            }
            if push.generation != held.generation + 1 {
                self.discard();
                return;
            }
            held.apply(push);
        }
        self.phase = Phase::Held(held);
    }

    /// A well-formed push. Always acked: the ack means applied, or that nothing will be served until
    /// a table including it. **It never touches `confirmed_sent`:** a late arrival would extend the
    /// lease past a later change's fence.
    pub fn pushed(&mut self, push: Push) {
        match &mut self.phase {
            Phase::Held(held) => {
                if push.boot_id == held.boot {
                    if push.generation <= held.generation {
                        return;
                    }
                    if push.generation == held.generation + 1 {
                        held.apply(push);
                        return;
                    }
                }
                self.phase = Phase::Locating {
                    pending: vec![push],
                };
                self.wanted = true;
            }
            Phase::Empty => {
                self.phase = Phase::Locating {
                    pending: vec![push],
                };
                self.wanted = true;
            }
            Phase::Locating { pending } | Phase::Pulling { pending, .. } => pending.push(push),
        }
    }

    /// A poll's answer, sent at `sent`. Lease credit only for a position saying what is held.
    pub fn positioned(&mut self, said: Said<Position>, sent: Instant) {
        let Phase::Held(held) = &mut self.phase else {
            return;
        };
        match said {
            Said::Unreadable => {}
            Said::UnknownSchema => self.discard(),
            Said::Good(position) => {
                if position.boot_id != held.boot || position.pid != held.pid {
                    self.discard();
                } else if position.generation > held.generation || position.down {
                    held.behind = true;
                    self.wanted = true;
                } else if position.generation == held.generation {
                    held.confirmed_sent = sent;
                    held.behind = false;
                }
                // Below what is held: the poll raced a push it hasn't seen. No credit, and a real
                // regression never earns any again, so it ends in forwarding.
            }
        }
    }

    /// The tail found another claim, the owner lock released, or the serve lock taken exclusive, for
    /// this boot. A boot since replaced isn't touched.
    pub fn discard_boot(&mut self, boot: &str) {
        if matches!(&self.phase, Phase::Held(held) if held.boot == boot) {
            self.discard();
        }
    }

    /// Whether polling goes on: `Held`, with at least one grant.
    pub fn polling(&self) -> bool {
        matches!(&self.phase, Phase::Held(held) if !held.table.is_empty())
    }

    /// Whether a location should begin.
    pub fn is_wanted(&self) -> bool {
        self.wanted
    }

    /// Whether this grant can be answered for, **the watch's check last of all**.
    pub fn serve(&mut self, key: &str, now: Instant) -> Serve<W, O> {
        let held = match &self.phase {
            Phase::Held(held) => held,
            Phase::Empty => {
                self.wanted = true;
                return Serve::Forward("not held");
            }
            Phase::Locating { .. } | Phase::Pulling { .. } => return Serve::Forward("not held"),
        };
        if held.behind {
            return Serve::Forward("behind");
        }
        if now.saturating_duration_since(held.confirmed_sent) > LEASE {
            return Serve::Forward("lease");
        }
        let Some(grant) = held.table.get(key) else {
            return Serve::Forward("unknown token");
        };
        let granted = Granted {
            grant: grant.clone(),
            boot: held.boot.clone(),
            corpus: held.corpus.clone(),
            watch: held.watch.clone(),
            owner: held.owner.clone(),
        };
        if held.watch.ended() {
            self.discard();
            return Serve::Forward("watch ended");
        }
        Serve::Grant(granted)
    }

    #[cfg(test)]
    fn generation(&self) -> Option<u64> {
        match &self.phase {
            Phase::Held(held) => Some(held.generation),
            _ => None,
        }
    }
}

impl<W, O> Held<W, O> {
    fn apply(&mut self, push: Push) {
        self.generation = push.generation;
        match push.grant {
            Some(grant) => self.table.insert(push.key, grant),
            None => self.table.remove(&push.key),
        };
    }
}

/// The client, for the front's whole life.
pub struct Mirror {
    upstream: SocketAddr,
    secret: String,
    brain: PathBuf,
    state: Mutex<State<ProcessWatch, BrainFile>>,
    wake: Notify,
}

/// What adoption needs from the files.
fn adopt(brain: &Path, boot: &str) -> Option<BrainFile> {
    let claim = BrainFile::open(&brain.join(CLAIM)).ok()?;
    claim.says(boot).ok()?.then_some(())?;
    BrainFile::open(&brain.join(OWNER_LOCK)).ok()
}

impl Mirror {
    pub fn new(upstream: SocketAddr, secret: String, brain: PathBuf) -> Self {
        let mut state = State::default();
        state.trigger();
        Self {
            upstream,
            secret,
            brain,
            state: Mutex::new(state),
            wake: Notify::new(),
        }
    }

    fn locked(&self) -> std::sync::MutexGuard<'_, State<ProcessWatch, BrainFile>> {
        self.state.lock().expect("no panic is held across this")
    }

    pub fn brain(&self) -> &Path {
        &self.brain
    }

    /// Whether this token can be answered for now. Wakes the client if it wants a location.
    pub fn serve(&self, key: &str) -> Serve<ProcessWatch, BrainFile> {
        let mut state = self.locked();
        let served = state.serve(key, Instant::now());
        let wanted = state.is_wanted();
        drop(state);
        if wanted {
            self.wake.notify_one();
        }
        served
    }

    pub fn discard_boot(&self, boot: &str) {
        self.locked().discard_boot(boot);
        self.wake.notify_one();
    }

    /// A push from Python. `None` is malformed: discarded before this returns, so before any answer.
    pub fn pushed(&self, push: Option<Push>) -> bool {
        let good = push.is_some();
        {
            let mut state = self.locked();
            match push {
                Some(push) => state.pushed(push),
                None => state.discard(),
            }
        }
        self.wake.notify_one();
        good
    }

    /// Started once, by the front, and never returns.
    pub async fn run(&self) {
        let mut connection: Option<TcpStream> = None;
        loop {
            if self.locked().begin() {
                connection = None;
                self.locate_and_pull().await;
                continue;
            }
            if self.locked().polling() {
                let sent = Instant::now();
                self.poll(&mut connection, sent).await;
                let next = sent + POSITION_EVERY;
                self.idle(&mut connection, next).await;
            } else {
                connection = None;
                self.wake.notified().await;
            }
        }
    }

    async fn locate_and_pull(&self) {
        let Ok(mut stream) = connect(self.upstream, POSITION_TIMEOUT).await else {
            self.locked().failed();
            return;
        };
        let said = match self.ask(&mut stream, POSITION_PATH, POSITION_TIMEOUT).await {
            Asked::Answer(200, body) => parse_position(&body),
            _ => {
                self.locked().failed();
                return;
            }
        };
        let located = self
            .locked()
            .located(said, ProcessWatch::open, Instant::now());
        if !located {
            return;
        }
        match self.ask(&mut stream, GRANTS_PATH, PULL_TIMEOUT).await {
            Asked::Answer(200, body) => {
                let said = parse_pull(&body);
                let brain = self.brain.clone();
                self.locked().pulled(said, |boot| adopt(&brain, boot));
            }
            _ => self.locked().failed(),
        }
    }

    /// One position, on the connection in hand or a new one. A poll not whole in time loses the
    /// connection and earns nothing; a connection that ends says Python is gone.
    async fn poll(&self, connection: &mut Option<TcpStream>, sent: Instant) {
        if connection.is_none() {
            match connect(self.upstream, POSITION_TIMEOUT).await {
                Ok(stream) => *connection = Some(stream),
                // A refused connect on Windows lands here, since it takes longer than the timeout.
                Err(()) => return,
            }
        }
        let stream = connection.as_mut().expect("just made");
        match self.ask(stream, POSITION_PATH, POSITION_TIMEOUT).await {
            Asked::Answer(200, body) => self.locked().positioned(parse_position(&body), sent),
            // The lease keeps running out.
            Asked::Answer(..) | Asked::Late => *connection = None,
            Asked::Gone => {
                *connection = None;
                self.locked().discard();
            }
        }
    }

    /// Until the next poll is due or something wakes this, with the connection in hand watched: its
    /// end is a discard. **Nothing relies on this:** it saves the next read a check.
    async fn idle(&self, connection: &mut Option<TcpStream>, next: Instant) {
        let sleep = tokio::time::sleep_until(next.into());
        tokio::pin!(sleep);
        loop {
            let ended = async {
                match connection.as_mut() {
                    Some(stream) => {
                        let mut one = [0; 1];
                        matches!(stream.peek(&mut one).await, Ok(0) | Err(_))
                    }
                    None => std::future::pending().await,
                }
            };
            tokio::select! {
                () = &mut sleep => return,
                () = self.wake.notified() => {
                    if self.locked().is_wanted() {
                        return;
                    }
                }
                true = ended => {
                    *connection = None;
                    self.locked().discard();
                    return;
                }
            }
        }
    }

    async fn ask(&self, stream: &mut TcpStream, path: &str, limit: Duration) -> Asked {
        let request = format!(
            "GET {path} HTTP/1.1\r\nHost: {}\r\n{SECRET_HEADER}: {}\r\n\r\n",
            self.upstream, self.secret
        );
        match tokio::time::timeout(limit, exchange(stream, request.as_bytes())).await {
            Ok(asked) => asked,
            Err(_) => Asked::Late,
        }
    }
}

enum Asked {
    Answer(u16, Vec<u8>),
    /// Not whole in time, or unreadable: dropped, so no late answer can count.
    Late,
    /// The connection ended.
    Gone,
}

async fn connect(upstream: SocketAddr, limit: Duration) -> Result<TcpStream, ()> {
    match tokio::time::timeout(limit, TcpStream::connect(upstream)).await {
        Ok(Ok(stream)) => {
            let _ = stream.set_nodelay(true);
            Ok(stream)
        }
        _ => Err(()),
    }
}

async fn exchange(stream: &mut TcpStream, request: &[u8]) -> Asked {
    if stream.write_all(request).await.is_err() {
        return Asked::Gone;
    }
    let mut got = Vec::new();
    let mut chunk = [0; 16 * 1024];
    let (head_end, length) = loop {
        if let Some(end) = got.windows(4).position(|w| w == b"\r\n\r\n") {
            let head = String::from_utf8_lossy(&got[..end]).to_ascii_lowercase();
            let Some(length) = head
                .lines()
                .find_map(|line| line.strip_prefix("content-length:"))
                .and_then(|value| value.trim().parse::<usize>().ok())
            else {
                return Asked::Late;
            };
            if length > MOST_ANSWER {
                return Asked::Late;
            }
            break (end + 4, length);
        }
        match stream.read(&mut chunk).await {
            Ok(0) | Err(_) => return Asked::Gone,
            Ok(more) => got.extend_from_slice(&chunk[..more]),
        }
    };
    while got.len() < head_end + length {
        match stream.read(&mut chunk).await {
            Ok(0) | Err(_) => return Asked::Gone,
            Ok(more) => got.extend_from_slice(&chunk[..more]),
        }
    }
    let Some(status) = std::str::from_utf8(&got[..head_end])
        .ok()
        .and_then(|head| head.split(' ').nth(1))
        .and_then(|code| code.parse().ok())
    else {
        return Asked::Late;
    };
    Asked::Answer(status, got[head_end..head_end + length].to_vec())
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicBool, Ordering};

    use super::*;

    #[derive(Default)]
    struct Watch(AtomicBool);

    impl Ended for Watch {
        fn ended(&self) -> bool {
            self.0.load(Ordering::SeqCst)
        }
    }

    type S = State<Watch, ()>;

    const BOOT: &str = "b";
    const KEY: &str = "k1";

    fn grant() -> Grant {
        Grant {
            corpus: "C:\\b".into(),
            scope: "worker".into(),
            operations: None,
        }
    }

    fn position(generation: u64, down: bool) -> Said<Position> {
        Said::Good(Position {
            boot_id: BOOT.into(),
            generation,
            down,
            pid: 7,
        })
    }

    fn pull(generation: u64, grants: &[&str]) -> Said<Pull> {
        Said::Good(Pull {
            boot_id: BOOT.into(),
            generation,
            corpus: "C:\\b".into(),
            grants: grants
                .iter()
                .map(|key| ((*key).to_owned(), grant()))
                .collect(),
        })
    }

    fn push(generation: u64, key: &str, grant_it: bool) -> Push {
        Push {
            boot_id: BOOT.into(),
            generation,
            key: key.into(),
            grant: grant_it.then(grant),
        }
    }

    /// A state `Held` on boot `b`, at `generation`, with `KEY`, confirmed at `at`.
    fn held(at: Instant, generation: u64) -> (S, Arc<Watch>) {
        let mut state = S::default();
        state.trigger();
        assert!(state.begin());
        assert!(state.located(position(generation, false), |_| Some(Watch::default()), at));
        state.pulled(pull(generation, &[KEY]), |_| Some(()));
        let Phase::Held(inner) = &state.phase else {
            panic!("not held");
        };
        let watch = inner.watch.clone();
        (state, watch)
    }

    fn served(state: &mut S, now: Instant) -> Result<(), &'static str> {
        match state.serve(KEY, now) {
            Serve::Grant(_) => Ok(()),
            Serve::Forward(why) => Err(why),
        }
    }

    #[test]
    fn nothing_is_served_until_a_table_is_held() {
        let now = Instant::now();
        let mut state = S::default();
        assert_eq!(served(&mut state, now), Err("not held"));
        assert!(state.is_wanted(), "a presented grant while not held is a trigger");
        assert!(state.begin());
        assert_eq!(served(&mut state, now), Err("not held"));
    }

    #[test]
    fn no_watch_means_nothing_is_held() {
        let mut state = S::default();
        state.trigger();
        state.begin();
        assert!(!state.located(position(0, false), |_| None, Instant::now()));
        assert!(matches!(state.phase, Phase::Empty));
    }

    #[test]
    fn an_unknown_schema_at_location_is_nothing() {
        let mut state = S::default();
        state.trigger();
        state.begin();
        assert!(!state.located(Said::UnknownSchema, |_| Some(Watch::default()), Instant::now()));
        assert!(matches!(state.phase, Phase::Empty));
    }

    #[test]
    fn the_lease_counts_from_when_the_confirmation_was_sent() {
        let start = Instant::now();
        let (mut state, _) = held(start, 3);
        assert_eq!(served(&mut state, start + LEASE), Ok(()));
        assert_eq!(
            served(&mut state, start + LEASE + Duration::from_millis(1)),
            Err("lease")
        );
        let later = start + Duration::from_secs(2);
        state.positioned(position(3, false), later);
        assert_eq!(served(&mut state, later + LEASE), Ok(()));
    }

    #[test]
    fn a_push_never_renews_the_lease() {
        let start = Instant::now();
        let (mut state, _) = held(start, 3);
        state.pushed(push(4, "k2", true));
        assert_eq!(state.generation(), Some(4));
        assert_eq!(
            served(&mut state, start + LEASE + Duration::from_millis(1)),
            Err("lease")
        );
    }

    #[test]
    fn a_drop_takes_the_grant_at_once() {
        let start = Instant::now();
        let (mut state, _) = held(start, 3);
        state.pushed(push(4, KEY, false));
        assert_eq!(served(&mut state, start), Err("unknown token"));
    }

    #[test]
    fn a_push_already_included_changes_nothing() {
        let start = Instant::now();
        let (mut state, _) = held(start, 3);
        state.pushed(push(3, KEY, false));
        assert_eq!(state.generation(), Some(3));
        assert_eq!(served(&mut state, start), Ok(()));
    }

    #[test]
    fn a_gap_or_another_boot_discards_and_pulls() {
        let start = Instant::now();
        let (mut state, _) = held(start, 3);
        state.pushed(push(5, KEY, true));
        assert!(state.is_wanted());
        assert_eq!(served(&mut state, start), Err("not held"));

        let (mut state, _) = held(start, 3);
        state.pushed(Push {
            boot_id: "another".into(),
            ..push(4, KEY, true)
        });
        assert!(state.is_wanted());
        assert_eq!(served(&mut state, start), Err("not held"));
    }

    #[test]
    fn a_push_during_a_pull_waits_and_is_replayed_on_adoption() {
        let start = Instant::now();
        let mut state = S::default();
        state.trigger();
        state.begin();
        state.pushed(push(4, KEY, false));
        assert!(state.located(position(3, false), |_| Some(Watch::default()), start));
        state.pushed(push(5, "k2", true));
        state.pulled(pull(3, &[KEY]), |_| Some(()));
        assert_eq!(state.generation(), Some(5));
        assert_eq!(served(&mut state, start), Err("unknown token"));
        assert!(matches!(state.serve("k2", start), Serve::Grant(_)));
    }

    #[test]
    fn a_pending_push_below_the_pull_is_already_included() {
        let start = Instant::now();
        let mut state = S::default();
        state.trigger();
        state.begin();
        state.pushed(push(2, KEY, false));
        assert!(state.located(position(3, false), |_| Some(Watch::default()), start));
        state.pulled(pull(3, &[KEY]), |_| Some(()));
        assert_eq!(served(&mut state, start), Ok(()));
    }

    #[test]
    fn a_gap_in_what_waited_pulls_again() {
        let start = Instant::now();
        let mut state = S::default();
        state.trigger();
        state.begin();
        assert!(state.located(position(3, false), |_| Some(Watch::default()), start));
        state.pushed(push(5, KEY, false));
        state.pulled(pull(3, &[KEY]), |_| Some(()));
        assert!(state.is_wanted());
        assert_eq!(served(&mut state, start), Err("not held"));
    }

    #[test]
    fn a_pull_from_another_boot_closes_the_watch_and_discards() {
        let start = Instant::now();
        let mut state = S::default();
        state.trigger();
        state.begin();
        assert!(state.located(position(3, false), |_| Some(Watch::default()), start));
        let Phase::Pulling { watch, .. } = &state.phase else {
            panic!("not pulling");
        };
        let watch = watch.clone();
        state.pulled(
            Said::Good(Pull {
                boot_id: "another".into(),
                generation: 3,
                corpus: String::new(),
                grants: HashMap::new(),
            }),
            |_| panic!("not adopted"),
        );
        assert_eq!(Arc::strong_count(&watch), 1, "the state's copy has gone");
        assert!(state.is_wanted());
    }

    #[test]
    fn a_boot_that_does_not_own_the_brain_is_never_held() {
        let start = Instant::now();
        let mut state = S::default();
        state.trigger();
        state.begin();
        assert!(state.located(position(3, false), |_| Some(Watch::default()), start));
        state.pulled(pull(3, &[KEY]), |_| None);
        assert!(matches!(state.phase, Phase::Empty));
        assert!(!state.is_wanted(), "tried again at the next trigger");
    }

    #[test]
    fn a_position_at_what_is_held_clears_behind_and_one_past_it_sets_it() {
        let start = Instant::now();
        let (mut state, _) = held(start, 3);
        state.positioned(position(4, false), start);
        assert_eq!(served(&mut state, start), Err("behind"));
        assert!(state.is_wanted());
        state.positioned(position(3, false), start);
        assert_eq!(served(&mut state, start), Ok(()));
        state.positioned(position(3, true), start);
        assert_eq!(served(&mut state, start), Err("behind"));
    }

    #[test]
    fn a_position_below_what_is_held_earns_nothing() {
        let start = Instant::now();
        let (mut state, _) = held(start, 3);
        state.positioned(position(2, false), start + Duration::from_secs(2));
        assert_eq!(
            served(&mut state, start + LEASE + Duration::from_millis(1)),
            Err("lease")
        );
        assert_eq!(state.generation(), Some(3));
    }

    #[test]
    fn a_position_from_another_boot_or_pid_or_schema_discards() {
        for said in [
            Said::Good(Position {
                boot_id: "another".into(),
                generation: 3,
                down: false,
                pid: 7,
            }),
            Said::Good(Position {
                boot_id: BOOT.into(),
                generation: 3,
                down: false,
                pid: 8,
            }),
            Said::UnknownSchema,
        ] {
            let start = Instant::now();
            let (mut state, _) = held(start, 3);
            state.positioned(said, start);
            assert_eq!(served(&mut state, start), Err("not held"));
            assert!(state.is_wanted());
        }
    }

    #[test]
    fn an_unreadable_position_changes_nothing_and_the_lease_runs_on() {
        let start = Instant::now();
        let (mut state, _) = held(start, 3);
        state.positioned(Said::Unreadable, start + Duration::from_secs(2));
        assert_eq!(served(&mut state, start), Ok(()));
        assert_eq!(
            served(&mut state, start + LEASE + Duration::from_millis(1)),
            Err("lease")
        );
    }

    #[test]
    fn an_ended_watch_forwards_with_no_monitor_event_and_no_push() {
        let start = Instant::now();
        let (mut state, watch) = held(start, 3);
        watch.0.store(true, Ordering::SeqCst);
        assert_eq!(served(&mut state, start), Err("watch ended"));
        assert!(matches!(state.phase, Phase::Empty));
        assert!(state.is_wanted());
        assert_eq!(Arc::strong_count(&watch), 1);
    }

    #[test]
    fn a_tail_s_discard_is_for_its_own_boot() {
        let start = Instant::now();
        let (mut state, _) = held(start, 3);
        state.discard_boot("another");
        assert_eq!(served(&mut state, start), Ok(()));
        state.discard_boot(BOOT);
        assert_eq!(served(&mut state, start), Err("not held"));
    }

    #[test]
    fn no_grants_no_polling() {
        let start = Instant::now();
        let (mut state, _) = held(start, 3);
        assert!(state.polling());
        state.pushed(push(4, KEY, false));
        assert!(!state.polling());
        assert!(!S::default().polling());
    }

    #[test]
    fn a_failure_drops_what_was_pending_and_waits_for_a_trigger() {
        let mut state = S::default();
        state.trigger();
        state.begin();
        state.pushed(push(1, KEY, true));
        state.failed();
        assert!(matches!(state.phase, Phase::Empty));
        assert!(!state.is_wanted());
    }

    #[test]
    fn every_malformed_push_is_refused() {
        let key = "a".repeat(64);
        let whole = format!(
            r#"{{"schema":1,"boot_id":"b","generation":1,"key":"{key}","grant":{{"corpus":"c","scope":"s","operations":null}}}}"#
        );
        assert!(parse_push(whole.as_bytes()).is_some());
        let drop_it = format!(r#"{{"schema":1,"boot_id":"b","generation":1,"key":"{key}","grant":null}}"#);
        assert!(parse_push(drop_it.as_bytes()).unwrap().grant.is_none());
        for bad in [
            "not json".to_owned(),
            "[]".to_owned(),
            whole.replace(r#""schema":1"#, r#""schema":2"#),
            whole.replace(r#""boot_id":"b","#, ""),
            whole.replace(r#""generation":1"#, r#""generation":"1""#),
            whole.replace(&key, &"A".repeat(64)),
            whole.replace(&key, &"a".repeat(63)),
            format!(r#"{{"schema":1,"boot_id":"b","generation":1,"key":"{key}"}}"#),
            whole.replace(r#""scope":"s""#, r#""scope":null"#),
            whole.replace(r#""operations":null"#, r#""operations":"x""#),
            whole.replace(r#""operations":null"#, r#""operations":[1]"#),
            whole.replace(r#"{"corpus":"c","scope":"s","operations":null}"#, "3"),
        ] {
            assert!(parse_push(bad.as_bytes()).is_none(), "{bad}");
        }
        let long = format!(" {}", " ".repeat(BODY_LOOK as usize));
        assert!(parse_push(long.as_bytes()).is_none());
    }
}
