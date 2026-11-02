//! The front: owns the public port, answers what the route table gives it, and forwards everything
//! else to Python on its private port, unchanged. `docs/rust/contracts/route-table.md` and
//! `launcher.md` are what it keeps to.
//!
//! **It watches nothing and restarts nothing.** If Python is gone a forwarded request is told so
//! and an owned one is still answered. Nothing here retries: the next request simply tries again.

pub mod answers;
pub mod brain;
pub mod checks;
mod connection;
pub mod forward;
pub mod head;
pub mod latency;

use std::io::Write as _;
use std::net::{Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

use mentis_record::RecordReader;
use tokio::net::TcpListener;
use tokio::sync::{Notify, watch};

use crate::HANDLERS;
use crate::handlers::Context;
use crate::launch::DRAIN_LIMIT;
use crate::route_table::{LiveRouteTable, REREAD_EVERY, Reread};
use checks::AllowedHosts;
use latency::Latency;

/// What the front is started with, by `contracts/launcher.md`'s step 4.
pub struct Config {
    pub brain: PathBuf,
    pub host: String,
    pub port: u16,
    /// Python's private port, or for J6 and J7 the harness's recorder. Always loopback.
    pub upstream: SocketAddr,
    pub dist: PathBuf,
    pub route_table: Option<PathBuf>,
    /// From `MENTIS_BOOT_SECRET`, never a command line.
    pub secret: String,
    /// [`DRAIN_LIMIT`], but for tests that need a stop to end within them.
    pub drain_limit: Duration,
}

/// The words for a command line that isn't one.
pub const USAGE: &str = "mentis-server <brain> --host <host> --port <port> --upstream http://127.0.0.1:<port> --dist <Fluid's dist> [--route-table <file>], with MENTIS_BOOT_SECRET in the environment";

impl Config {
    /// Arguments after the program's name, and `MENTIS_BOOT_SECRET`'s value.
    pub fn from_args(args: &[String], secret: Option<String>) -> Result<Config, String> {
        let mut brain = None;
        let mut host = None;
        let mut port = None;
        let mut upstream = None;
        let mut dist = None;
        let mut route_table = None;
        let mut args = args.iter();
        while let Some(arg) = args.next() {
            let mut value = || {
                args.next()
                    .ok_or_else(|| format!("{arg} needs a value. {USAGE}"))
            };
            match arg.as_str() {
                "--host" => host = Some(value()?.clone()),
                "--port" => {
                    let text = value()?;
                    port = Some(
                        text.parse::<u16>()
                            .map_err(|_| format!("--port {text} is not a port"))?,
                    );
                }
                "--upstream" => upstream = Some(parse_upstream(value()?)?),
                "--dist" => dist = Some(PathBuf::from(value()?)),
                "--route-table" => route_table = Some(PathBuf::from(value()?)),
                other if other.starts_with("--") => {
                    return Err(format!("{other} is not an argument. {USAGE}"));
                }
                other if brain.is_none() => brain = Some(PathBuf::from(other)),
                other => return Err(format!("{other} is one Brain too many. {USAGE}")),
            }
        }
        let needs = |what: &str| format!("{what} is needed. {USAGE}");
        let secret = secret
            .filter(|secret| !secret.is_empty())
            .ok_or_else(|| needs("MENTIS_BOOT_SECRET"))?;
        Ok(Config {
            brain: brain.ok_or_else(|| needs("A Brain"))?,
            host: host.unwrap_or_else(|| Ipv4Addr::LOCALHOST.to_string()),
            port: port.ok_or_else(|| needs("--port"))?,
            upstream: upstream.ok_or_else(|| needs("--upstream"))?,
            dist: dist.ok_or_else(|| needs("--dist"))?,
            route_table,
            secret,
            drain_limit: DRAIN_LIMIT,
        })
    }
}

/// `http://127.0.0.1:<port>`, and nothing else: the secret goes to it with every request.
fn parse_upstream(url: &str) -> Result<SocketAddr, String> {
    let refused = || format!("--upstream {url} is not http://127.0.0.1:<port>");
    let port = url.strip_prefix("http://127.0.0.1:").ok_or_else(refused)?;
    let port: u16 = port.parse().map_err(|_| refused())?;
    Ok(SocketAddr::from((Ipv4Addr::LOCALHOST, port)))
}

/// One line in the front's log: its stderr, which the launcher appends to `front.log`.
pub fn say(line: &str) {
    let _ = writeln!(std::io::stderr(), "{line}");
}

/// `hmac.compare_digest` for the secret: its time doesn't say how much of a guess was right.
pub fn secrets_match(presented: &str, secret: &str) -> bool {
    presented.len() == secret.len()
        && presented
            .bytes()
            .zip(secret.bytes())
            .fold(0, |differ, (a, b)| differ | (a ^ b))
            == 0
}

/// Returns once this is true. The channels here are owned by [`Shared`], so they outlive this.
async fn turned_on(flag: &mut watch::Receiver<bool>) {
    while !*flag.borrow_and_update() {
        if flag.changed().await.is_err() {
            return;
        }
    }
}

/// What every connection shares.
pub struct Shared {
    table: LiveRouteTable,
    context: Arc<Context>,
    upstream: SocketAddr,
    secret: String,
    allowed_hosts: AllowedHosts,
    latency: Latency,
    stop_requested: watch::Sender<bool>,
    listener_gone: watch::Sender<bool>,
    in_flight: AtomicUsize,
    quiet: Notify,
}

/// Held while a request is in hand, so a stop can wait for it.
struct InFlight<'a>(&'a Shared);

impl Drop for InFlight<'_> {
    fn drop(&mut self) {
        if self.0.in_flight.fetch_sub(1, Ordering::SeqCst) == 1 {
            self.0.quiet.notify_waiters();
        }
    }
}

impl Shared {
    fn begin(&self) -> InFlight<'_> {
        self.in_flight.fetch_add(1, Ordering::SeqCst);
        InFlight(self)
    }

    /// Stop taking connections, returning once a new one is refused by the operating system.
    async fn stop_accepting(&self) {
        self.stop_requested.send_replace(true);
        turned_on(&mut self.listener_gone.subscribe()).await;
    }

    async fn drained(&self, limit: Duration) -> bool {
        let wait = async {
            loop {
                let quiet = self.quiet.notified();
                if self.in_flight.load(Ordering::SeqCst) == 0 {
                    return;
                }
                quiet.await;
            }
        };
        tokio::time::timeout(limit, wait).await.is_ok()
    }
}

/// A front that refused to start, in words. Exit 3.
#[derive(Debug, PartialEq, Eq)]
pub struct Refused(pub String);

/// A front bound and answering.
pub struct Running {
    pub address: SocketAddr,
    pub shared: Arc<Shared>,
    listener: TcpListener,
    drain_limit: Duration,
}

impl Running {
    /// Serve until a planned stop has finished, up to the drain limit. Anything still running past
    /// it is cut when the process ends.
    pub async fn serve(self) {
        let Running {
            shared,
            listener,
            drain_limit,
            ..
        } = self;
        let log = spawn_latency_log(shared.clone());
        spawn_reread(shared.clone());

        let mut stopping = shared.stop_requested.subscribe();
        loop {
            tokio::select! {
                () = turned_on(&mut stopping) => break,
                accepted = listener.accept() => match accepted {
                    Ok((client, peer)) => {
                        tokio::spawn(connection::serve(client, peer, shared.clone()));
                    }
                    Err(error) => {
                        say(&format!("accepting a connection failed: {error}"));
                        tokio::time::sleep(Duration::from_millis(50)).await;
                    }
                },
            }
        }
        // Closing the socket is what refuses the next connection.
        drop(listener);
        shared.listener_gone.send_replace(true);
        say("stopping: not accepting, finishing what is in hand");
        if !shared.drained(drain_limit).await {
            say("stopping: the drain limit passed with calls still in hand; they are cut");
        }
        log.abort();
        for line in shared.latency.lines_if_changed() {
            say(&line);
        }
        say("stopped");
    }
}

/// Open the Brain, then [`start_with`].
pub async fn start(config: Config) -> Result<Running, Refused> {
    let record =
        brain::open::<brain::Opener>(&config.brain).map_err(|why| Refused(why.to_string()))?;
    start_with(config, record).await
}

/// Bind and get ready, or refuse. Nothing has been served when this returns an error.
pub async fn start_with(config: Config, record: Arc<dyn RecordReader>) -> Result<Running, Refused> {
    let table = LiveRouteTable::start(config.route_table.as_deref(), HANDLERS)
        .map_err(|why| Refused(why.to_string()))?;
    let listener = TcpListener::bind((config.host.as_str(), config.port))
        .await
        .map_err(|error| {
            Refused(format!(
                "cannot listen on {}:{}: {error}",
                config.host, config.port
            ))
        })?;
    let address = listener
        .local_addr()
        .map_err(|error| Refused(format!("cannot read the bound address: {error}")))?;
    let (stop_requested, _) = watch::channel(false);
    let (listener_gone, _) = watch::channel(false);
    let shared = Arc::new(Shared {
        table,
        context: Arc::new(Context {
            dist: config.dist,
            record,
        }),
        upstream: config.upstream,
        secret: config.secret,
        allowed_hosts: AllowedHosts::from_env(),
        latency: Latency::default(),
        stop_requested,
        listener_gone,
        in_flight: AtomicUsize::new(0),
        quiet: Notify::new(),
    });
    if let (Some(file), Some(digest)) = (&config.route_table, shared.table.started_on()) {
        say(&format!("route table {}: {digest}", file.display()));
    }
    say(&format!(
        "answering on {address}, forwarding to {}",
        shared.upstream
    ));
    Ok(Running {
        address,
        shared,
        listener,
        drain_limit: config.drain_limit,
    })
}

fn spawn_latency_log(shared: Arc<Shared>) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let mut every = tokio::time::interval(latency::LOG_EVERY);
        every.tick().await;
        loop {
            every.tick().await;
            for line in shared.latency.lines_if_changed() {
                say(&line);
            }
        }
    })
}

/// The table's file, looked at each [`REREAD_EVERY`] on a blocking thread, for the process's life.
/// A front on the table in the binary has nothing to look at and starts none of this.
fn spawn_reread(shared: Arc<Shared>) {
    let Some(file) = shared.table.file().map(PathBuf::from) else {
        return;
    };
    std::thread::spawn(move || {
        loop {
            std::thread::sleep(REREAD_EVERY);
            match shared.table.reread() {
                Reread::Unchanged => {}
                Reread::Taken { digest } => {
                    say(&format!("route table {}: {digest}", file.display()));
                }
                Reread::Refused(why) => {
                    say(&format!(
                        "route table {} refused, the last good one stays: {why}",
                        file.display()
                    ));
                }
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(words: &[&str]) -> Vec<String> {
        words.iter().map(|word| (*word).to_owned()).collect()
    }

    const WHOLE: &[&str] = &[
        r"C:\b",
        "--host",
        "127.0.0.1",
        "--port",
        "8861",
        "--upstream",
        "http://127.0.0.1:18861",
        "--dist",
        r"C:\d",
    ];

    #[test]
    fn step_four_s_command_is_understood() {
        let config = Config::from_args(&args(WHOLE), Some("s".into())).unwrap_or_else(|why| {
            panic!("{why}");
        });
        assert_eq!(config.port, 8861);
        assert_eq!(config.upstream.port(), 18861);
        assert!(config.upstream.ip().is_loopback());
        assert_eq!(config.drain_limit, DRAIN_LIMIT);
        assert!(config.route_table.is_none());
    }

    fn refused(words: &[&str], secret: Option<&str>) -> String {
        match Config::from_args(&args(words), secret.map(str::to_owned)) {
            Ok(_) => panic!("{words:?} was taken"),
            Err(why) => why,
        }
    }

    #[test]
    fn a_command_line_that_is_not_one_is_refused_in_words() {
        assert!(refused(WHOLE, None).contains("MENTIS_BOOT_SECRET"));
        assert!(refused(WHOLE, Some("")).contains("MENTIS_BOOT_SECRET"));
        assert!(refused(&["--host"], Some("s")).contains("--host needs a value"));
        assert!(refused(&["--what", "x"], Some("s")).contains("not an argument"));
        assert!(refused(&[r"C:\b", r"C:\c"], Some("s")).contains("one Brain too many"));
        assert!(refused(&["--port", "x"], Some("s")).contains("not a port"));
    }

    #[test]
    fn the_secret_only_ever_goes_to_a_loopback_upstream() {
        for url in [
            "http://evil.example:1",
            "http://localhost:1",
            "https://127.0.0.1:1",
            "http://127.0.0.1",
            "http://127.0.0.1:1/x",
            "http://127.0.0.1:99999",
        ] {
            assert!(parse_upstream(url).is_err(), "{url}");
        }
    }

    #[test]
    fn secrets_compare_whole() {
        assert!(secrets_match("abc", "abc"));
        assert!(!secrets_match("abd", "abc"));
        assert!(!secrets_match("ab", "abc"));
        assert!(!secrets_match("", "abc"));
    }
}
