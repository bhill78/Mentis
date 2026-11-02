//! The door's last step, for every answer it gives from the mirror, 403s included. `docs/rust/
//! R3-mirror.md`, section 4, "The tail".
//!
//! **The owner's two rulings are what this holds to.** Claim completion is the point of ownership,
//! and a complete success goes first. So the last check and the last byte handed to the socket sit
//! inside locks a replacement must get past. Either the whole answer has been accepted before it can
//! own the Brain, or the connection is aborted first, and the client never sees a whole answer.
//!
//! Up to the first accepted byte nothing awaits with anything held, and nothing depends on a client.
//! After it the tail awaits only the client's socket, only until the deadline. A cancelled task or a
//! panic drops the locks with their handles. A read isn't run under it, because a read that finishes
//! before a passing check is ordered before the claim, as the check is. **Every forward releases
//! first:** a forward waits on Python, and that Python could be the one waiting on this lock.

use std::io;
use std::path::Path;
use std::time::Duration;

use tokio::net::TcpStream;
use tokio::time::Instant;

use super::grants::{CLAIM, SERVE_LOCK};
use super::held::{BrainFile, Ended, Tried};
use super::probe;

/// How long a tail that has had bytes accepted may hold its locks for the rest, then aborts the
/// connection. **Provisional** (`R3-mirror.md`, Timings). Safety assumes nothing of it: it limits how
/// long a stalled client can hold up a start, and sets which slow clients get aborted. Only
/// `brainlock.CLAIM_WAIT` being longer is part of the design.
pub const SEND_BOUND: Duration = Duration::from_secs(5);

/// A client's socket, as the tail uses it.
#[allow(async_fn_in_trait, reason = "only ever used with concrete types, here")]
pub trait Socket {
    async fn writable(&mut self) -> io::Result<()>;
    fn try_write(&mut self, bytes: &[u8]) -> io::Result<usize>;
    /// So the close that follows resets the connection, dropping what the kernel holds.
    fn abort(&mut self) -> io::Result<()>;
}

impl Socket for &mut TcpStream {
    async fn writable(&mut self) -> io::Result<()> {
        TcpStream::writable(self).await
    }

    fn try_write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        TcpStream::try_write(self, bytes)
    }

    #[allow(
        deprecated,
        reason = "tokio 1.48's name for SO_LINGER; the pin is exact"
    )]
    fn abort(&mut self) -> io::Result<()> {
        self.set_linger(Some(Duration::ZERO))
    }
}

/// Why a check didn't pass. The read forwards either way.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Refused {
    /// The mirror is the old boot's: close the watch and the owner handle, discard, pull.
    Discard(&'static str),
    /// Busy, or no clear answer from a file. No change to the state.
    Forward(&'static str),
}

/// The checks, and what stays held once they have passed.
pub trait Barrier {
    type Hold;
    fn check(&self) -> Result<Self::Hold, Refused>;
}

/// How a tail ended.
#[derive(Debug)]
pub enum Tailed<H> {
    /// Every byte accepted, and released.
    Sent,
    /// Nothing accepted, and released. Goes to Python with its bytes in hand.
    Forward(Refused),
    /// A failed write: the client has gone, and it has released.
    ClientGone,
    /// Past the deadline, with bytes not accepted. The caller closes the socket, **then** drops this.
    Aborted { hold: Option<H>, id: u64 },
}

/// The whole of it. Generic so each line can be tested with the checks and the write as inputs.
pub async fn answer<S: Socket, B: Barrier>(
    mut socket: S,
    bytes: &[u8],
    barrier: &B,
    send_bound: Duration,
) -> Tailed<B::Hold> {
    let id = probe::begin();
    loop {
        // Holding nothing: a client not draining waits here.
        if socket.writable().await.is_err() {
            return Tailed::ClientGone;
        }
        let hold = match barrier.check() {
            Ok(hold) => hold,
            Err(refused) => {
                probe::trace(id, "forward");
                return Tailed::Forward(refused);
            }
        };
        let mut hold = Some(hold);
        probe::trace(id, "checked");
        if cfg!(feature = "mutant-release-before-write") {
            hold = None;
            probe::trace(id, "released");
        }
        probe::stop("checked");
        let first = probe::limited(bytes);
        let mut sent = match socket.try_write(first) {
            Ok(0) => return Tailed::ClientGone,
            Ok(sent) => sent,
            // Nothing accepted: release, and start this block again.
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                probe::trace(id, "would-block");
                if hold.take().is_some() {
                    probe::trace(id, "released");
                }
                continue;
            }
            Err(_) => return Tailed::ClientGone,
        };
        probe::trace(id, "first-byte");
        // From the first accepted byte: whole, or aborted.
        let deadline = Instant::now() + send_bound;
        if cfg!(feature = "mutant-release-after-first-write") {
            hold = None;
            probe::trace(id, "released");
        }
        while sent < bytes.len() {
            probe::stop("mid-send");
            if Instant::now() >= deadline {
                return abort(&mut socket, hold, id);
            }
            match tokio::time::timeout_at(deadline, socket.writable()).await {
                Err(_) => return abort(&mut socket, hold, id),
                Ok(Err(_)) => return Tailed::ClientGone,
                Ok(Ok(())) => {}
            }
            if Instant::now() >= deadline {
                return abort(&mut socket, hold, id);
            }
            match socket.try_write(probe::limited(&bytes[sent..])) {
                Ok(0) => return Tailed::ClientGone,
                Ok(more) => sent += more,
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {}
                Err(_) => return Tailed::ClientGone,
            }
        }
        probe::trace(id, "last-byte");
        if hold.take().is_some() {
            probe::trace(id, "released");
        }
        return Tailed::Sent;
    }
}

fn abort<S: Socket, H>(socket: &mut S, hold: Option<H>, id: u64) -> Tailed<H> {
    // If SO_LINGER can't be set the close is ordinary: what was accepted still goes, and what wasn't
    // never will, so the client still can't get the whole answer.
    let _ = socket.abort();
    probe::trace(id, "abort");
    Tailed::Aborted { hold, id }
}

/// The real checks, on Python's files.
pub struct OnFiles<'a, W> {
    pub brain: &'a Path,
    pub boot: &'a str,
    pub owner: &'a BrainFile,
    pub watch: &'a W,
}

/// The two shared locks. Dropped, they go with their handles.
#[derive(Debug)]
pub struct Held {
    claim: BrainFile,
    serve: Option<BrainFile>,
}

impl Drop for Held {
    fn drop(&mut self) {
        self.claim.unlock();
        if let Some(serve) = &self.serve {
            serve.unlock();
        }
    }
}

impl<W: Ended> Barrier for OnFiles<'_, W> {
    type Hold = Held;

    fn check(&self) -> Result<Held, Refused> {
        let claim = BrainFile::open(&self.brain.join(CLAIM))
            .map_err(|_| Refused::Forward("claim unreadable"))?;
        match claim.try_shared() {
            Tried::Taken => {}
            Tried::Busy => return Err(Refused::Forward("claim busy")),
            Tried::Failed => return Err(Refused::Forward("claim unreadable")),
        }
        let mut held = Held { claim, serve: None };
        if !cfg!(feature = "mutant-no-serve-check") {
            let serve = BrainFile::open(&self.brain.join(SERVE_LOCK))
                .map_err(|_| Refused::Forward("serve lock unreadable"))?;
            match serve.try_shared() {
                Tried::Taken => held.serve = Some(serve),
                Tried::Busy => return Err(Refused::Discard("serve lock held exclusive")),
                Tried::Failed => return Err(Refused::Forward("serve lock unreadable")),
            }
        }
        match held.claim.says(self.boot) {
            Ok(true) => {}
            Ok(false) => return Err(Refused::Discard("another claim")),
            Err(_) => return Err(Refused::Forward("claim unreadable")),
        }
        match self.owner.try_shared() {
            Tried::Busy => {}
            Tried::Taken => {
                self.owner.unlock();
                return Err(Refused::Discard("owner lock released"));
            }
            Tried::Failed => return Err(Refused::Forward("owner lock unreadable")),
        }
        if self.watch.ended() {
            return Err(Refused::Discard("watch ended"));
        }
        Ok(held)
    }
}

#[cfg(test)]
mod tests {
    use std::cell::RefCell;
    use std::collections::VecDeque;
    use std::rc::Rc;

    use super::*;

    const BOUND: Duration = Duration::from_millis(30);

    /// What happened, in order.
    type Log = Rc<RefCell<Vec<String>>>;

    /// One scripted answer to a `try_write`.
    enum Takes {
        Up(usize),
        Blocks,
        Fails,
    }

    struct Scripted {
        log: Log,
        writes: VecDeque<Takes>,
        /// A `writable` after this many never comes.
        ready: usize,
    }

    impl Socket for Scripted {
        async fn writable(&mut self) -> io::Result<()> {
            if self.ready == 0 {
                std::future::pending::<()>().await;
            }
            self.ready -= 1;
            self.log.borrow_mut().push("writable".into());
            Ok(())
        }

        fn try_write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            assert!(
                !self.log.borrow().iter().any(|line| line == "abort"),
                "written after the abort"
            );
            match self
                .writes
                .pop_front()
                .expect("no more writes were scripted")
            {
                Takes::Up(most) => {
                    let took = most.min(bytes.len());
                    self.log.borrow_mut().push(format!("write {took}"));
                    Ok(took)
                }
                Takes::Blocks => {
                    self.log.borrow_mut().push("blocks".into());
                    Err(io::ErrorKind::WouldBlock.into())
                }
                Takes::Fails => {
                    self.log.borrow_mut().push("fails".into());
                    Err(io::ErrorKind::ConnectionReset.into())
                }
            }
        }

        fn abort(&mut self) -> io::Result<()> {
            self.log.borrow_mut().push("abort".into());
            Ok(())
        }
    }

    struct Hold(Log);

    impl Drop for Hold {
        fn drop(&mut self) {
            self.0.borrow_mut().push("release".into());
        }
    }

    struct Checks {
        log: Log,
        refusal: Option<Refused>,
    }

    impl Barrier for Checks {
        type Hold = Hold;
        fn check(&self) -> Result<Hold, Refused> {
            self.log.borrow_mut().push("check".into());
            match self.refusal {
                Some(refused) => Err(refused),
                None => Ok(Hold(self.log.clone())),
            }
        }
    }

    fn scripted(writes: Vec<Takes>, ready: usize) -> (Scripted, Checks, Log) {
        let log = Log::default();
        (
            Scripted {
                log: log.clone(),
                writes: writes.into(),
                ready,
            },
            Checks {
                log: log.clone(),
                refusal: None,
            },
            log,
        )
    }

    fn run<H>(future: impl Future<Output = Tailed<H>>) -> Tailed<H> {
        tokio::runtime::Builder::new_current_thread()
            .enable_time()
            .build()
            .unwrap()
            .block_on(future)
    }

    fn said(log: &Log) -> Vec<String> {
        log.borrow().clone()
    }

    /// An answer whose status line is 15 bytes, headers to 60, and body to 100.
    const ANSWER: [u8; 100] = [b'x'; 100];

    #[test]
    fn a_refused_check_forwards_having_written_nothing() {
        for refused in [Refused::Discard("x"), Refused::Forward("y")] {
            let (socket, mut checks, log) = scripted(vec![], 1);
            checks.refusal = Some(refused);
            let ended = run(answer(socket, &ANSWER, &checks, BOUND));
            assert!(matches!(ended, Tailed::Forward(said) if said == refused));
            assert_eq!(said(&log), ["writable", "check"]);
        }
    }

    #[test]
    fn a_whole_write_releases_after_it() {
        let (socket, checks, log) = scripted(vec![Takes::Up(100)], 1);
        let ended = run(answer(socket, &ANSWER, &checks, BOUND));
        assert!(matches!(ended, Tailed::Sent));
        assert_eq!(said(&log), ["writable", "check", "write 100", "release"]);
    }

    #[test]
    fn a_blocked_write_with_nothing_accepted_releases_and_starts_again() {
        let (socket, checks, log) = scripted(vec![Takes::Blocks, Takes::Up(100)], 2);
        let ended = run(answer(socket, &ANSWER, &checks, BOUND));
        assert!(matches!(ended, Tailed::Sent));
        assert_eq!(
            said(&log),
            [
                "writable",
                "check",
                "blocks",
                "release",
                "writable",
                "check",
                "write 100",
                "release"
            ]
        );
    }

    #[test]
    fn nothing_is_released_until_the_last_byte_wherever_the_first_write_stops() {
        // In the status line, in the headers, in the body.
        for first in [7, 40, 80] {
            let (socket, checks, log) =
                scripted(vec![Takes::Up(first), Takes::Blocks, Takes::Up(100)], 3);
            let ended = run(answer(socket, &ANSWER, &checks, BOUND));
            assert!(matches!(ended, Tailed::Sent));
            let log = said(&log);
            assert_eq!(log.last().map(String::as_str), Some("release"));
            assert_eq!(log.iter().filter(|line| *line == "release").count(), 1);
            assert_eq!(log[log.len() - 2], format!("write {}", 100 - first));
        }
    }

    #[test]
    fn past_the_deadline_it_aborts_and_the_caller_releases_after_the_close() {
        for first in [7, 40, 80] {
            let (socket, checks, log) = scripted(vec![Takes::Up(first)], 1);
            let ended = run(answer(socket, &ANSWER, &checks, BOUND));
            let Tailed::Aborted { hold, .. } = ended else {
                panic!("it wasn't aborted");
            };
            assert_eq!(
                said(&log),
                ["writable", "check", &format!("write {first}"), "abort"]
            );
            drop(hold);
            assert_eq!(said(&log).last().map(String::as_str), Some("release"));
        }
    }

    #[test]
    fn nothing_is_written_at_or_past_the_deadline() {
        // Ready only after the deadline has passed.
        struct Late(Scripted);
        impl Socket for Late {
            async fn writable(&mut self) -> io::Result<()> {
                if self.0.ready == 2 {
                    return self.0.writable().await;
                }
                tokio::time::sleep(BOUND + Duration::from_millis(20)).await;
                self.0.writable().await
            }
            fn try_write(&mut self, bytes: &[u8]) -> io::Result<usize> {
                self.0.try_write(bytes)
            }
            fn abort(&mut self) -> io::Result<()> {
                self.0.abort()
            }
        }
        let (socket, checks, log) = scripted(vec![Takes::Up(7)], 2);
        let ended = run(answer(Late(socket), &ANSWER, &checks, BOUND));
        assert!(matches!(ended, Tailed::Aborted { hold: Some(_), .. }));
        assert_eq!(
            said(&log).iter().filter(|l| l.starts_with("write")).count(),
            1
        );
    }

    #[test]
    fn a_client_gone_part_way_releases() {
        let (socket, checks, log) = scripted(vec![Takes::Up(7), Takes::Fails], 2);
        let ended = run(answer(socket, &ANSWER, &checks, BOUND));
        assert!(matches!(ended, Tailed::ClientGone));
        assert_eq!(said(&log).last().map(String::as_str), Some("release"));
    }

    #[test]
    fn a_dropped_tail_releases() {
        let (socket, checks, log) = scripted(vec![Takes::Up(7)], 1);
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_time()
            .build()
            .unwrap();
        runtime.block_on(async {
            let mut going = Box::pin(answer(socket, &ANSWER, &checks, BOUND));
            // Far enough to have sent the first part and be waiting on the socket.
            assert!(
                tokio::time::timeout(Duration::from_millis(1), &mut going)
                    .await
                    .is_err()
            );
            assert!(!said(&log).contains(&"release".to_owned()));
            drop(going);
            assert_eq!(said(&log).last().map(String::as_str), Some("release"));
        });
    }

    #[test]
    fn nothing_is_held_across_the_wait_for_a_client_not_draining() {
        let (socket, checks, log) = scripted(vec![], 0);
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_time()
            .build()
            .unwrap();
        runtime.block_on(async {
            let waited = tokio::time::timeout(
                Duration::from_millis(60),
                answer(socket, &ANSWER, &checks, BOUND),
            )
            .await;
            assert!(waited.is_err());
            assert!(said(&log).is_empty(), "no check, so no lock");
        });
    }
}
