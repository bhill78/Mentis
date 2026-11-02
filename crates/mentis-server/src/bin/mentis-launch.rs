//! Starts Python and the front as siblings, says they answer, and exits. Contract:
//! `docs/rust/contracts/launcher.md`.
//!
//! **Nothing here restarts anything,** and after step 5 of the order it touches nothing. A start
//! that fails stops what this invocation started, which isn't recovery: nothing had been handed
//! over. One killed before it could do that leaves `launch.starting.json`, which says what it had
//! started, and `recover` stops that when somebody asks. `--attached` stays only as both processes'
//! parent, for tests and the bench.

use std::env;
use std::ffi::OsStr;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::net::{TcpListener, TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitCode, Stdio};
use std::time::{Duration, Instant};

use mentis_server::launch::{
    DRAIN_LIMIT, EXIT_REFUSED, LaunchState, SECRET_BYTES, SECRET_ENV, SECRET_HEADER, STATE_FORMAT,
    STOP_PATH, Started, StartedWith, default_private_port,
};
use serde::{Deserialize, Serialize};

/// As the bench's own limit: a large Brain's start is slow.
const PYTHON_LIMIT: Duration = Duration::from_secs(240);
const FRONT_LIMIT: Duration = Duration::from_secs(30);
const WAIT_STEP: Duration = Duration::from_millis(100);
const ASK_TIMEOUT: Duration = Duration::from_secs(5);
/// How long `stop` waits past the front's own limit, for it to exit having drained.
const EXIT_MARGIN: Duration = Duration::from_secs(5);
const LOG_TAIL_LINES: usize = 20;
/// The port `stop`, with neither `--port` nor `--run-dir`, means, as the contract's command does.
const DEFAULT_PUBLIC_PORT: u16 = 8760;
const FLUID_DIST_ENV: &str = "MENTIS_FLUID_DIST";
const USAGE: &str = "\
mentis-launch <brain> --port <port> [--host <host>] [--private-port <port>]
    --workspace <dir> [--writable-root <dir>]... [--mars <command>]
    --python <python.exe> --code <dir holding mentis/>
    [--front <mentis-server.exe>] [--dist <Fluid's dist>] [--route-table <file>]
    [--run-dir <dir>] [--attached] [--upstream <loopback url>] [--only front|python]
mentis-launch stop [--run-dir <dir>] [--port <port>] --front
mentis-launch recover [--run-dir <dir>] [--port <port>]";

/// Why this invocation changed nothing lasting. Exit 3, these words on stderr.
#[derive(Debug, PartialEq, Eq)]
struct Refused(String);

impl From<String> for Refused {
    fn from(words: String) -> Self {
        Self(words)
    }
}

fn refuse<T>(words: impl Into<String>) -> Result<T, Refused> {
    Err(Refused(words.into()))
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Only {
    Front,
    Python,
}

/// The command line, as given.
#[derive(Debug, Default, PartialEq, Eq)]
struct Given {
    brain: Option<String>,
    port: Option<u16>,
    host: Option<String>,
    private_port: Option<u16>,
    workspace: Option<String>,
    writable_roots: Vec<String>,
    mars: Option<String>,
    python: Option<String>,
    code: Option<String>,
    front: Option<String>,
    dist: Option<String>,
    route_table: Option<String>,
    run_dir: Option<String>,
    attached: bool,
    upstream: Option<String>,
    only: Option<Only>,
}

#[derive(Debug, PartialEq, Eq)]
enum Asked {
    Launch(Box<Given>),
    StopFront { run_dir: Option<String>, port: u16 },
    Recover { run_dir: Option<String>, port: u16 },
}

fn port_of(flag: &str, text: &str) -> Result<u16, Refused> {
    match text.parse::<u16>() {
        Ok(port) if port > 0 => Ok(port),
        _ => refuse(format!("{flag} is a port from 1 to 65535, not {text:?}")),
    }
}

/// `stop` and `recover`, which name a run directory the same way.
fn parse_stop(verb: &str, args: &[String]) -> Result<Asked, Refused> {
    let (mut run_dir, mut port, mut front) = (None, DEFAULT_PUBLIC_PORT, false);
    let mut rest = args.iter();
    while let Some(flag) = rest.next() {
        match flag.as_str() {
            "--front" if verb == "stop" => front = true,
            "--run-dir" | "--port" => {
                let Some(value) = rest.next() else {
                    return refuse(format!("{flag} needs a value"));
                };
                if flag == "--port" {
                    port = port_of(flag, value)?;
                } else {
                    run_dir = Some(value.clone());
                }
            }
            other => return refuse(format!("{verb} doesn't take {other:?}\n{USAGE}")),
        }
    }
    if verb == "recover" {
        return Ok(Asked::Recover { run_dir, port });
    }
    if !front {
        return refuse(
            "stop stops only the front, and says so with --front. Python is stopped by taskkill \
             of its tree, which ends live runs and is the owner's decision each time",
        );
    }
    Ok(Asked::StopFront { run_dir, port })
}

fn parse(args: &[String]) -> Result<Asked, Refused> {
    if let Some(verb @ ("stop" | "recover")) = args.first().map(String::as_str) {
        return parse_stop(verb, &args[1..]);
    }
    let mut given = Given::default();
    let mut rest = args.iter();
    while let Some(arg) = rest.next() {
        let flag = arg.as_str();
        if !flag.starts_with("--") {
            if given.brain.is_some() {
                return refuse(format!("one Brain, not also {flag:?}\n{USAGE}"));
            }
            given.brain = Some(arg.clone());
            continue;
        }
        if flag == "--attached" {
            given.attached = true;
            continue;
        }
        let Some(value) = rest.next() else {
            return refuse(format!("{flag} needs a value\n{USAGE}"));
        };
        let value = value.clone();
        match flag {
            "--port" => given.port = Some(port_of(flag, &value)?),
            "--private-port" => given.private_port = Some(port_of(flag, &value)?),
            "--host" => given.host = Some(value),
            "--workspace" => given.workspace = Some(value),
            "--writable-root" => given.writable_roots.push(value),
            "--mars" => given.mars = Some(value),
            "--python" => given.python = Some(value),
            "--code" => given.code = Some(value),
            "--front" => given.front = Some(value),
            "--dist" => given.dist = Some(value),
            "--route-table" => given.route_table = Some(value),
            "--run-dir" => given.run_dir = Some(value),
            "--upstream" => given.upstream = Some(check_upstream(&value)?),
            "--only" => {
                given.only = Some(match value.as_str() {
                    "front" => Only::Front,
                    "python" => Only::Python,
                    other => return refuse(format!("--only is front or python, not {other:?}")),
                });
            }
            other => return refuse(format!("no such option {other:?}\n{USAGE}")),
        }
    }
    check_absolute(&given)?;
    Ok(Asked::Launch(Box::new(given)))
}

/// `--upstream` is for the harness's recorder, on this machine, and nothing else.
fn check_upstream(url: &str) -> Result<String, Refused> {
    let port = url.strip_prefix("http://127.0.0.1:").unwrap_or("");
    match port.parse::<u16>() {
        Ok(number) if number > 0 && number.to_string() == port => Ok(url.to_owned()),
        _ => refuse(format!(
            "--upstream is only http://127.0.0.1:<port>, not {url:?}"
        )),
    }
}

/// Nothing is found through `PATH`, because the bench strips `PATH`, and nothing is relative to
/// wherever this happened to be started.
fn check_absolute(given: &Given) -> Result<(), Refused> {
    let named = [
        ("<brain>", &given.brain),
        ("--workspace", &given.workspace),
        ("--python", &given.python),
        ("--code", &given.code),
        ("--front", &given.front),
        ("--dist", &given.dist),
        ("--route-table", &given.route_table),
        ("--run-dir", &given.run_dir),
    ];
    for (what, path) in named {
        if let Some(path) = path
            && !Path::new(path).is_absolute()
        {
            return refuse(format!("{what} must be an absolute path, not {path:?}"));
        }
    }
    for root in &given.writable_roots {
        if !Path::new(root).is_absolute() {
            return refuse(format!(
                "--writable-root must be an absolute path, not {root:?}"
            ));
        }
    }
    Ok(())
}

/// The journal's first line. See the contract's "A launcher killed part way".
#[derive(Debug, Serialize, Deserialize)]
struct JournalHead {
    format: u32,
    launcher: Mark,
}

/// What was started and hasn't been handed over yet, as the journal says it, from before the first
/// process to the moment `launch.json` says it. A line a kill cut short says nothing.
#[derive(Clone, Debug, PartialEq, Eq)]
struct Unfinished {
    launcher: Option<Mark>,
    started: Vec<Mark>,
}

/// One process, by what identifies it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
struct Mark {
    pid: u32,
    start_time: u64,
}

const STARTING_FILE: &str = "launch.starting.json";
const STATE_FILE: &str = "launch.json";

fn run_dir_for_port(port: u16) -> Result<PathBuf, Refused> {
    let Some(local) = env::var_os("LOCALAPPDATA") else {
        return refuse("no --run-dir, and no LOCALAPPDATA to put it under");
    };
    Ok(Path::new(&local)
        .join("Mentis")
        .join("run")
        .join(port.to_string()))
}

/// Canonical as far as the path exists, so a directory yet to be made can be compared.
fn resolved(path: &Path) -> PathBuf {
    let mut tail = Vec::new();
    let mut at = path;
    loop {
        if let Ok(found) = at.canonicalize() {
            return tail
                .iter()
                .rev()
                .fold(found, |so_far, part| so_far.join(part));
        }
        match (at.parent(), at.file_name()) {
            (Some(parent), Some(name)) => {
                tail.push(name.to_owned());
                at = parent;
            }
            _ => return path.to_owned(),
        }
    }
}

fn require_file(what: &str, path: &str) -> Result<(), Refused> {
    if Path::new(path).is_file() {
        Ok(())
    } else {
        refuse(format!("{what} {path:?} isn't a file"))
    }
}

fn required(what: &str, value: Option<String>) -> Result<String, Refused> {
    value.ok_or_else(|| Refused(format!("{what} is required\n{USAGE}")))
}

fn default_front() -> Result<String, Refused> {
    let me = env::current_exe().map_err(|e| Refused(format!("where this binary is: {e}")))?;
    let beside = me.with_file_name(format!("mentis-server{}", env::consts::EXE_SUFFIX));
    Ok(beside.to_string_lossy().into_owned())
}

fn default_dist(code: Option<&str>) -> Result<String, Refused> {
    if let Some(dist) = env::var_os(FLUID_DIST_ENV) {
        return Ok(dist.to_string_lossy().into_owned());
    }
    match code {
        Some(code) => Ok(Path::new(code)
            .join("apps")
            .join("fluid-web")
            .join("dist")
            .to_string_lossy()
            .into_owned()),
        None => refuse(format!("--dist, {FLUID_DIST_ENV} or --code is required")),
    }
}

/// `--host` as something to connect to. An address that means every interface answers on loopback.
fn reachable_host(host: &str) -> &str {
    match host {
        "0.0.0.0" | "::" | "[::]" => "127.0.0.1",
        other => other,
    }
}

fn url_host(host: &str) -> String {
    if host.contains(':') && !host.starts_with('[') {
        format!("[{host}]")
    } else {
        host.to_owned()
    }
}

fn answers_at(host: &str, port: u16) -> String {
    format!("http://{}:{port}", url_host(host))
}

/// Step 1. Binding is the only true answer to "is it in use". Nothing is written.
fn look(what: &str, host: &str, port: u16) -> Result<(), Refused> {
    let host_for_bind = host.trim_start_matches('[').trim_end_matches(']');
    match TcpListener::bind((host_for_bind, port)) {
        Ok(listener) => {
            drop(listener);
            Ok(())
        }
        Err(e) => refuse(format!(
            "{what} port {port} on {host} is in use or can't be bound ({e}): stop whatever \
             serves it first. This doesn't pick another"
        )),
    }
}

fn new_secret() -> Result<String, Refused> {
    let mut bytes = [0u8; SECRET_BYTES];
    platform::random(&mut bytes).map_err(|e| Refused(format!("no random bytes: {e}")))?;
    Ok(urlsafe_base64(&bytes))
}

/// As `secrets.token_urlsafe`: URL-safe base64 with no padding.
fn urlsafe_base64(bytes: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let at = |i: usize| chunk.get(i).copied().unwrap_or(0);
        let group = (u32::from(at(0)) << 16) | (u32::from(at(1)) << 8) | u32::from(at(2));
        for position in 0..=chunk.len() {
            let index = (group >> (18 - 6 * position)) & 0x3f;
            out.push(char::from(ALPHABET[index as usize]));
        }
    }
    out
}

/// The `launch.starting.json` of this invocation, for as long as nothing has been handed over.
/// Lines appended to one file held open, because on Windows renaming over a file made a moment ago
/// can be refused while something else, such as a scanner, has it open.
struct Journal {
    path: PathBuf,
    file: File,
}

impl Journal {
    /// Before anything is started, and only if no other invocation holds this run directory.
    fn begin(run_dir: &Path) -> Result<Self, Refused> {
        let me = std::process::id();
        let start_time = platform::start_time_of(me)
            .ok_or_else(|| Refused("can't say when this launcher started".to_owned()))?;
        let path = run_dir.join(STARTING_FILE);
        let file = OpenOptions::new()
            .append(true)
            .create_new(true)
            .open(&path)
            .map_err(|e| Refused(format!("can't make {}: {e}", path.display())))?;
        let mut journal = Self { path, file };
        platform::keep_to_user(&journal.path).map_err(|e| {
            journal.remove();
            Refused(format!("can't keep {STARTING_FILE} to this user: {e}"))
        })?;
        let head = JournalHead {
            format: STATE_FORMAT,
            launcher: Mark {
                pid: me,
                start_time,
            },
        };
        if let Err(refused) = journal.write_line(&head) {
            journal.remove();
            return Err(refused);
        }
        Ok(journal)
    }

    /// Written before the process is let run.
    fn note(&mut self, mark: Mark) -> Result<(), Refused> {
        self.write_line(&mark)
    }

    fn write_line<T: Serialize>(&mut self, value: &T) -> Result<(), Refused> {
        let line = serde_json::to_string(value)
            .map_err(|e| Refused(format!("can't say what was started: {e}")))?;
        writeln!(self.file, "{line}")
            .and_then(|()| self.file.sync_all())
            .map_err(|e| Refused(format!("can't write {}: {e}", self.path.display())))
    }

    fn remove(&self) {
        let _ = fs::remove_file(&self.path);
    }

    /// Nothing is left for anybody to recover. One this can't remove is cleared by whoever reads it
    /// next, since its launcher will have gone and what it names is gone or published.
    fn end(self) {
        self.remove();
    }
}

/// A process being started, with where its log stood so a refusal can quote only its own words.
struct Starting {
    child: Child,
    who: &'static str,
    log: PathBuf,
    log_from: u64,
    start_time: u64,
}

impl Starting {
    /// What this invocation started goes with it, its children too.
    fn stop(&mut self) {
        platform::stop_tree(self.child.id());
        let _ = self.child.kill();
        let _ = self.child.wait();
    }

    fn pid(&self) -> u32 {
        self.child.id()
    }

    fn own_log_tail(&self) -> String {
        let Ok(mut file) = File::open(&self.log) else {
            return String::new();
        };
        let mut text = Vec::new();
        if file.seek(SeekFrom::Start(self.log_from)).is_err()
            || file.read_to_end(&mut text).is_err()
        {
            return String::new();
        }
        let text = String::from_utf8_lossy(&text);
        let lines: Vec<&str> = text.lines().collect();
        lines[lines.len().saturating_sub(LOG_TAIL_LINES)..].join("\n")
    }
}

/// `env` is added to what the launcher itself has, which both processes inherit. Noted in the
/// journal before it runs a line, so a kill landing here leaves a process that is either on record
/// or held suspended, with no port and no lock.
#[allow(clippy::too_many_arguments)]
fn start(
    journal: &mut Journal,
    who: &'static str,
    program: &str,
    args: &[String],
    cwd: Option<&str>,
    extra_env: &[(&str, &str)],
    log: &Path,
    attached: bool,
) -> Result<Starting, Refused> {
    let open_log = || {
        OpenOptions::new()
            .create(true)
            .append(true)
            .open(log)
            .map_err(|e| Refused(format!("can't open {}: {e}", log.display())))
    };
    let out = open_log()?;
    let log_from = out.metadata().map(|m| m.len()).unwrap_or(0);
    let err = out
        .try_clone()
        .map_err(|e| Refused(format!("can't share {}: {e}", log.display())))?;
    let mut command = Command::new(program);
    command
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::from(out))
        .stderr(Stdio::from(err));
    if let Some(cwd) = cwd {
        command.current_dir(cwd);
    }
    for (name, value) in extra_env {
        command.env(name, OsStr::new(value));
    }
    platform::outlive_the_launcher(&mut command, attached);
    let mut child = command
        .spawn()
        .map_err(|e| Refused(format!("can't start {who}, {program:?}: {e}")))?;
    let noted = platform::start_time_of_child(&child)
        .ok_or_else(|| Refused(format!("can't say when {who} started")))
        .and_then(|start_time| {
            journal.note(Mark {
                pid: child.id(),
                start_time,
            })?;
            platform::let_run(&child).map_err(|e| Refused(format!("can't let {who} run: {e}")))?;
            Ok(start_time)
        });
    let start_time = match noted {
        Ok(start_time) => start_time,
        Err(refused) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(refused);
        }
    };
    Ok(Starting {
        child,
        who,
        log: log.to_owned(),
        log_from,
        start_time,
    })
}

/// One small request, by hand, so nothing else is needed. The status, or why there wasn't one.
fn ask_status(
    host: &str,
    port: u16,
    method: &str,
    path: &str,
    headers: &[(&str, &str)],
    answer_within: Duration,
) -> io::Result<u16> {
    let target = reachable_host(host)
        .trim_start_matches('[')
        .trim_end_matches(']');
    let address = (target, port)
        .to_socket_addrs()?
        .next()
        .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "no address"))?;
    let mut stream = TcpStream::connect_timeout(&address, ASK_TIMEOUT)?;
    stream.set_read_timeout(Some(answer_within))?;
    stream.set_write_timeout(Some(ASK_TIMEOUT))?;
    let mut request = format!(
        "{method} {path} HTTP/1.1\r\nHost: {}:{port}\r\nX-Mentis-Client: 1\r\nConnection: close\r\n",
        url_host(host)
    );
    for (name, value) in headers {
        request.push_str(&format!("{name}: {value}\r\n"));
    }
    if method == "POST" {
        request.push_str("Content-Length: 0\r\n");
    }
    request.push_str("\r\n");
    stream.write_all(request.as_bytes())?;
    let mut head = Vec::new();
    let mut buffer = [0u8; 256];
    while !head.contains(&b'\n') {
        let got = stream.read(&mut buffer)?;
        if got == 0 {
            break;
        }
        head.extend_from_slice(&buffer[..got]);
    }
    let line = String::from_utf8_lossy(&head);
    line.split_whitespace()
        .nth(1)
        .and_then(|status| status.parse().ok())
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "no HTTP status"))
}

/// Waits for `GET /api/server` to say 200 at this address. A process that exits has refused.
fn wait_for_answer(
    starting: &mut Starting,
    host: &str,
    port: u16,
    limit: Duration,
) -> Result<(), Refused> {
    let began = Instant::now();
    loop {
        if let Some(status) = starting
            .child
            .try_wait()
            .map_err(|e| Refused(format!("can't watch {}: {e}", starting.who)))?
        {
            return refuse(format!(
                "{} exited, {status}, before answering:\n{}",
                starting.who,
                starting.own_log_tail()
            ));
        }
        let last = match ask_status(host, port, "GET", "/api/server", &[], ASK_TIMEOUT) {
            Ok(200) => return Ok(()),
            Ok(status) => format!("answered {status}"),
            Err(e) => e.to_string(),
        };
        if began.elapsed() > limit {
            return refuse(format!(
                "{} didn't answer on port {port} within {} s ({last}):\n{}",
                starting.who,
                limit.as_secs(),
                starting.own_log_tail()
            ));
        }
        std::thread::sleep(WAIT_STEP);
    }
}

/// Atomically, and readable by this user alone before anything goes in.
fn write_private(path: &Path, text: &str) -> Result<(), Refused> {
    let temporary = path.with_extension(format!("{}.tmp", std::process::id()));
    let result = (|| -> io::Result<()> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)?;
        platform::keep_to_user(&temporary)?;
        file.write_all(text.as_bytes())?;
        file.sync_all()?;
        drop(file);
        fs::rename(&temporary, path)
    })();
    result.map_err(|e| {
        let _ = fs::remove_file(&temporary);
        Refused(format!(
            "can't write {} for this user alone: {e}",
            path.display()
        ))
    })
}

fn json_of<T: Serialize>(value: &T) -> Result<String, Refused> {
    serde_json::to_string_pretty(value)
        .map_err(|e| Refused(format!("can't say what was started: {e}")))
}

fn read_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T, Refused> {
    let text = fs::read_to_string(path)
        .map_err(|e| Refused(format!("can't read {}: {e}", path.display())))?;
    serde_json::from_str(&text)
        .map_err(|e| Refused(format!("{} is not as it should be: {e}", path.display())))
}

fn read_state(run_dir: &Path) -> Result<LaunchState, Refused> {
    settle_unfinished(run_dir)?;
    let state: LaunchState = read_json(&run_dir.join(STATE_FILE))?;
    if state.format != STATE_FORMAT {
        return refuse(format!(
            "{STATE_FILE} says format {}, and this build reads {STATE_FORMAT}",
            state.format
        ));
    }
    Ok(state)
}

/// Whether this is still the process that was recorded.
fn is_still(pid: u32, start_time: u64) -> bool {
    platform::start_time_of(pid) == Some(start_time)
}

fn read_unfinished(run_dir: &Path) -> Result<Option<Unfinished>, Refused> {
    let path = run_dir.join(STARTING_FILE);
    if !path.exists() {
        return Ok(None);
    }
    let text = fs::read_to_string(&path)
        .map_err(|e| Refused(format!("can't read {}: {e}", path.display())))?;
    let mut lines = text.lines();
    let head: Option<JournalHead> = lines
        .next()
        .and_then(|line| serde_json::from_str(line).ok());
    if let Some(head) = &head
        && head.format != STATE_FORMAT
    {
        return refuse(format!(
            "{STARTING_FILE} says format {}, and this build reads {STATE_FORMAT}",
            head.format
        ));
    }
    Ok(Some(Unfinished {
        launcher: head.map(|head| head.launcher),
        started: lines
            .filter_map(|line| serde_json::from_str(line).ok())
            .collect(),
    }))
}

/// Everything in the journal is in a `launch.json` too: the start finished, and was killed only
/// between saying so and tidying up.
fn was_published(run_dir: &Path, unfinished: &Unfinished) -> bool {
    let Ok(state) = read_json::<LaunchState>(&run_dir.join(STATE_FILE)) else {
        return false;
    };
    let said = [&state.front, &state.python].map(|s| Mark {
        pid: s.pid,
        start_time: s.start_time,
    });
    !unfinished.started.is_empty() && unfinished.started.iter().all(|mark| said.contains(mark))
}

fn still_alive(unfinished: &Unfinished) -> Vec<Mark> {
    let marks = unfinished.started.iter();
    marks
        .filter(|mark| is_still(mark.pid, mark.start_time))
        .copied()
        .collect()
}

fn pids_of(marks: &[Mark]) -> String {
    let pids: Vec<String> = marks.iter().map(|mark| mark.pid.to_string()).collect();
    pids.join(", ")
}

fn still_starting(run_dir: &Path, unfinished: &Unfinished) -> Option<Refused> {
    let launcher = unfinished.launcher?;
    is_still(launcher.pid, launcher.start_time).then(|| {
        Refused(format!(
            "another launcher, pid {}, is still starting in {}",
            launcher.pid,
            run_dir.display()
        ))
    })
}

/// Clears a journal that says nothing is left, and refuses to go past one that says something is.
fn settle_unfinished(run_dir: &Path) -> Result<(), Refused> {
    let Some(unfinished) = read_unfinished(run_dir)? else {
        return Ok(());
    };
    if let Some(refused) = still_starting(run_dir, &unfinished) {
        return Err(refused);
    }
    let alive = still_alive(&unfinished);
    if alive.is_empty() || was_published(run_dir, &unfinished) {
        let _ = fs::remove_file(run_dir.join(STARTING_FILE));
        return Ok(());
    }
    refuse(format!(
        "a launcher was killed before it finished here, and left pid {} running with nothing \
         else on record. `mentis-launch recover --run-dir {}` stops {}, and ends any run on it",
        pids_of(&alive),
        run_dir.display(),
        if alive.len() == 1 { "it" } else { "them" }
    ))
}

/// `mentis-launch recover`: stops what a killed launcher left, so a start can be made again. A
/// person's act, as stopping Python is: it never happens by itself, and it restarts nothing.
fn recover(run_dir: Option<String>, port: u16) -> Result<(), Refused> {
    let run_dir = match run_dir {
        Some(run_dir) => PathBuf::from(run_dir),
        None => run_dir_for_port(port)?,
    };
    let Some(unfinished) = read_unfinished(&run_dir)? else {
        println!("nothing to recover in {}", run_dir.display());
        return Ok(());
    };
    if let Some(refused) = still_starting(&run_dir, &unfinished) {
        return Err(refused);
    }
    let path = run_dir.join(STARTING_FILE);
    if was_published(&run_dir, &unfinished) {
        let _ = fs::remove_file(&path);
        println!(
            "nothing to recover: {STATE_FILE} already says what was started, and it stays running"
        );
        return Ok(());
    }
    let alive = still_alive(&unfinished);
    for mark in &alive {
        platform::stop_tree(mark.pid);
    }
    let left: Vec<Mark> = alive
        .iter()
        .filter(|mark| !platform::wait_for_exit(mark.pid, EXIT_MARGIN))
        .copied()
        .collect();
    if !left.is_empty() {
        return refuse(format!(
            "pid {} didn't exit, so {} stays",
            pids_of(&left),
            path.display()
        ));
    }
    fs::remove_file(&path).map_err(|e| Refused(format!("can't remove {}: {e}", path.display())))?;
    if alive.is_empty() {
        println!("nothing was left running. A start can be made");
    } else {
        println!("stopped pid {}. A start can be made", pids_of(&alive));
    }
    Ok(())
}

fn write_state(run_dir: &Path, state: &LaunchState) -> Result<(), Refused> {
    write_private(&run_dir.join(STATE_FILE), &json_of(state)?)
}

fn python_args(
    brain: &str,
    private_port: u16,
    answers: &str,
    remembered: &StartedWith,
) -> Vec<String> {
    let mut args: Vec<String> = [
        "-m",
        "mentis.web",
        brain,
        "--host",
        "127.0.0.1",
        "--port",
        &private_port.to_string(),
        "--answers-at",
        answers,
        "--workspace",
        &remembered.workspace,
    ]
    .map(str::to_owned)
    .into();
    for root in &remembered.writable_roots {
        args.extend(["--writable-root".to_owned(), root.clone()]);
    }
    if let Some(mars) = &remembered.mars {
        args.extend(["--mars".to_owned(), mars.clone()]);
    }
    args
}

fn front_args(
    brain: &str,
    host: &str,
    port: u16,
    upstream: &str,
    remembered: &StartedWith,
) -> Vec<String> {
    let mut args: Vec<String> = [
        brain,
        "--host",
        host,
        "--port",
        &port.to_string(),
        "--upstream",
        upstream,
        "--dist",
        &remembered.dist,
    ]
    .map(str::to_owned)
    .into();
    if let Some(table) = &remembered.route_table {
        args.extend(["--route-table".to_owned(), table.clone()]);
    }
    args
}

#[allow(clippy::too_many_arguments)]
fn start_python(
    journal: &mut Journal,
    run_dir: &Path,
    brain: &str,
    private_port: u16,
    answers: &str,
    secret: &str,
    remembered: &StartedWith,
    attached: bool,
) -> Result<Starting, Refused> {
    let mut python = start(
        journal,
        "Python",
        &remembered.python,
        &python_args(brain, private_port, answers, remembered),
        Some(&remembered.code),
        // One build for both sides: Python's post checking reads Fluid's, as the front serves it.
        &[(SECRET_ENV, secret), (FLUID_DIST_ENV, &remembered.dist)],
        &run_dir.join("python.log"),
        attached,
    )?;
    if let Err(refused) = wait_for_answer(&mut python, "127.0.0.1", private_port, PYTHON_LIMIT) {
        python.stop();
        return Err(refused);
    }
    Ok(python)
}

#[allow(clippy::too_many_arguments)]
fn start_front(
    journal: &mut Journal,
    run_dir: &Path,
    front: &str,
    brain: &str,
    host: &str,
    port: u16,
    upstream: &str,
    secret: &str,
    remembered: &StartedWith,
    attached: bool,
) -> Result<Starting, Refused> {
    let mut started = start(
        journal,
        "the front",
        front,
        &front_args(brain, host, port, upstream, remembered),
        None,
        &[(SECRET_ENV, secret)],
        &run_dir.join("front.log"),
        attached,
    )?;
    if let Err(refused) = wait_for_answer(&mut started, host, port, FRONT_LIMIT) {
        started.stop();
        return Err(refused);
    }
    Ok(started)
}

fn started_record(starting: &Starting, executable: &str) -> Started {
    Started {
        pid: starting.pid(),
        start_time: starting.start_time,
        executable: executable.to_owned(),
        log: starting.log.to_string_lossy().into_owned(),
    }
}

fn say_so(host: &str, port: u16, attached: bool) -> ! {
    let mut out = io::stdout();
    let _ = writeln!(out, "Mentis on {}", answers_at(host, port));
    let _ = out.flush();
    if attached {
        // Their parent, until killed, and nothing else: not a watcher.
        loop {
            std::thread::park();
        }
    }
    std::process::exit(0)
}

fn launch_both(given: Given) -> Result<(), Refused> {
    let brain = required("<brain>", given.brain)?;
    let port = given
        .port
        .ok_or_else(|| Refused(format!("--port is required\n{USAGE}")))?;
    let host = given.host.unwrap_or_else(|| "127.0.0.1".to_owned());
    let Some(private_port) = given.private_port.or_else(|| default_private_port(port)) else {
        return refuse(format!(
            "public port {port} has no default private port: name one with --private-port"
        ));
    };
    if private_port == port {
        return refuse(format!("the public and private ports are both {port}"));
    }
    let python = required("--python", given.python)?;
    let code = required("--code", given.code)?;
    let workspace = required("--workspace", given.workspace)?;
    let front = match given.front {
        Some(front) => front,
        None => default_front()?,
    };
    let dist = match given.dist {
        Some(dist) => dist,
        None => default_dist(Some(&code))?,
    };
    require_file("--python", &python)?;
    require_file("--front", &front)?;
    if !Path::new(&code).join("mentis").is_dir() {
        return refuse(format!("--code {code:?} doesn't hold mentis/"));
    }
    if let Some(table) = &given.route_table {
        require_file("--route-table", table)?;
    }
    let run_dir = match given.run_dir {
        Some(run_dir) => PathBuf::from(run_dir),
        None => run_dir_for_port(port)?,
    };
    if resolved(&run_dir).starts_with(resolved(Path::new(&brain))) {
        return refuse(format!(
            "the run directory {} is in the Brain, which it must never be",
            run_dir.display()
        ));
    }

    settle_unfinished(&run_dir)?;
    look("the public", &host, port)?;
    look("the private", "127.0.0.1", private_port)?;

    fs::create_dir_all(&run_dir)
        .map_err(|e| Refused(format!("can't make {}: {e}", run_dir.display())))?;
    let secret = new_secret()?;
    let answers = answers_at(&host, port);
    let remembered = StartedWith {
        python: python.clone(),
        code,
        workspace,
        writable_roots: given.writable_roots,
        mars: given.mars,
        dist,
        route_table: given.route_table,
    };

    let mut journal = Journal::begin(&run_dir)?;
    let mut python_started = match start_python(
        &mut journal,
        &run_dir,
        &brain,
        private_port,
        &answers,
        &secret,
        &remembered,
        given.attached,
    ) {
        Ok(started) => started,
        Err(refused) => {
            journal.end();
            return Err(refused);
        }
    };
    let upstream = given
        .upstream
        .unwrap_or_else(|| format!("http://127.0.0.1:{private_port}"));
    let mut front_started = match start_front(
        &mut journal,
        &run_dir,
        &front,
        &brain,
        &host,
        port,
        &upstream,
        &secret,
        &remembered,
        given.attached,
    ) {
        Ok(started) => started,
        Err(refused) => {
            python_started.stop();
            journal.end();
            return Err(refused);
        }
    };

    let state = LaunchState {
        format: STATE_FORMAT,
        brain,
        public_host: host.clone(),
        public_port: port,
        private_port,
        answers_at: answers,
        secret,
        front: started_record(&front_started, &front),
        python: started_record(&python_started, &python),
        started_with: remembered,
    };
    if let Err(refused) = write_state(&run_dir, &state) {
        front_started.stop();
        python_started.stop();
        journal.end();
        return Err(refused);
    }
    journal.end();
    say_so(&host, port, given.attached)
}

/// Refuses what contradicts the state file, so `--only` can't quietly mean another server.
fn check_against(given: &Given, state: &LaunchState) -> Result<(), Refused> {
    if let Some(brain) = &given.brain
        && resolved(Path::new(brain)) != resolved(Path::new(&state.brain))
    {
        return refuse(format!(
            "{brain:?} isn't the Brain {STATE_FILE} names, {:?}",
            state.brain
        ));
    }
    if given.port.is_some_and(|port| port != state.public_port) {
        return refuse(format!(
            "{STATE_FILE} says public port {}",
            state.public_port
        ));
    }
    if given
        .private_port
        .is_some_and(|port| port != state.private_port)
    {
        return refuse(format!(
            "{STATE_FILE} says private port {}",
            state.private_port
        ));
    }
    if given
        .host
        .as_ref()
        .is_some_and(|host| *host != state.public_host)
    {
        return refuse(format!("{STATE_FILE} says host {}", state.public_host));
    }
    Ok(())
}

fn launch_one(given: Given, only: Only) -> Result<(), Refused> {
    let run_dir = match (&given.run_dir, given.port) {
        (Some(run_dir), _) => PathBuf::from(run_dir),
        (None, Some(port)) => run_dir_for_port(port)?,
        (None, None) => return refuse(format!("--only needs --run-dir or --port\n{USAGE}")),
    };
    let mut state = read_state(&run_dir)?;
    check_against(&given, &state)?;
    let before = state.started_with.clone();
    let remembered = StartedWith {
        python: given.python.unwrap_or(before.python),
        code: given.code.unwrap_or(before.code),
        workspace: given.workspace.unwrap_or(before.workspace),
        writable_roots: if given.writable_roots.is_empty() {
            before.writable_roots
        } else {
            given.writable_roots
        },
        mars: given.mars.or(before.mars),
        dist: given.dist.unwrap_or(before.dist),
        route_table: given.route_table.or(before.route_table),
    };

    let front = match (only, given.front) {
        (Only::Front, None) => default_front()?,
        (_, front) => front.unwrap_or_default(),
    };
    match only {
        Only::Python => {
            require_file("--python", &remembered.python)?;
            look("the private", "127.0.0.1", state.private_port)?;
        }
        Only::Front => {
            require_file("--front", &front)?;
            if let Some(table) = &remembered.route_table {
                require_file("--route-table", table)?;
            }
            look("the public", &state.public_host, state.public_port)?;
        }
    }

    let mut journal = Journal::begin(&run_dir)?;
    let result = match only {
        Only::Python => start_python(
            &mut journal,
            &run_dir,
            &state.brain,
            state.private_port,
            &state.answers_at,
            &state.secret,
            &remembered,
            given.attached,
        ),
        Only::Front => start_front(
            &mut journal,
            &run_dir,
            &front,
            &state.brain,
            &state.public_host,
            state.public_port,
            &given
                .upstream
                .unwrap_or_else(|| format!("http://127.0.0.1:{}", state.private_port)),
            &state.secret,
            &remembered,
            given.attached,
        ),
    };
    let mut started = match result {
        Ok(started) => started,
        Err(refused) => {
            journal.end();
            return Err(refused);
        }
    };
    match only {
        Only::Python => state.python = started_record(&started, &remembered.python),
        Only::Front => state.front = started_record(&started, &front),
    }
    state.started_with = remembered;
    if let Err(refused) = write_state(&run_dir, &state) {
        started.stop();
        journal.end();
        return Err(refused);
    }
    journal.end();
    say_so(&state.public_host, state.public_port, given.attached)
}

fn stop_front(run_dir: Option<String>, port: u16) -> Result<(), Refused> {
    let run_dir = match run_dir {
        Some(run_dir) => PathBuf::from(run_dir),
        None => run_dir_for_port(port)?,
    };
    let state = read_state(&run_dir)?;
    let began = Instant::now();
    let status = ask_status(
        &state.public_host,
        state.public_port,
        "POST",
        STOP_PATH,
        &[(SECRET_HEADER, &state.secret)],
        DRAIN_LIMIT + EXIT_MARGIN,
    )
    .map_err(|e| {
        Refused(format!(
            "no front took the stop on port {}: {e}",
            state.public_port
        ))
    })?;
    if !(200..300).contains(&status) {
        return refuse(format!(
            "the front on port {} answered the stop with {status}, so it hasn't stopped",
            state.public_port
        ));
    }
    let limit = (DRAIN_LIMIT + EXIT_MARGIN).saturating_sub(began.elapsed());
    if is_still(state.front.pid, state.front.start_time)
        && !platform::wait_for_exit(state.front.pid, limit)
    {
        return refuse(format!(
            "the front, pid {}, took the stop and hasn't exited within {} s",
            state.front.pid,
            (DRAIN_LIMIT + EXIT_MARGIN).as_secs()
        ));
    }
    println!(
        "front stopped, pid {}, in {:.1} s",
        state.front.pid,
        began.elapsed().as_secs_f64()
    );
    Ok(())
}

fn run(args: &[String]) -> Result<(), Refused> {
    match parse(args)? {
        Asked::StopFront { run_dir, port } => stop_front(run_dir, port),
        Asked::Recover { run_dir, port } => recover(run_dir, port),
        Asked::Launch(given) => match given.only {
            Some(only) => launch_one(*given, only),
            None => launch_both(*given),
        },
    }
}

fn main() -> ExitCode {
    platform::keep_own_output_to_self();
    let mut args = Vec::new();
    for arg in env::args_os().skip(1) {
        match arg.into_string() {
            Ok(arg) => args.push(arg),
            Err(arg) => {
                eprintln!("mentis-launch refused: {arg:?} isn't Unicode");
                return ExitCode::from(EXIT_REFUSED as u8);
            }
        }
    }
    match run(&args) {
        Ok(()) => ExitCode::SUCCESS,
        Err(Refused(words)) => {
            eprintln!("mentis-launch refused: {words}");
            ExitCode::from(EXIT_REFUSED as u8)
        }
    }
}

#[cfg(windows)]
mod platform {
    use std::io;
    use std::os::windows::ffi::OsStrExt;
    use std::os::windows::io::AsRawHandle;
    use std::os::windows::process::CommandExt;
    use std::path::Path;
    use std::process::{Child, Command, Stdio};
    use std::ptr;
    use std::time::Duration;

    use windows_sys::Win32::Foundation::{
        CloseHandle, ERROR_SUCCESS, FILETIME, HANDLE, HANDLE_FLAG_INHERIT, LocalFree, STILL_ACTIVE,
        SetHandleInformation, WAIT_OBJECT_0,
    };
    use windows_sys::Win32::Security::Authorization::{
        EXPLICIT_ACCESS_W, NO_MULTIPLE_TRUSTEE, SE_FILE_OBJECT, SET_ACCESS, SetEntriesInAclW,
        SetNamedSecurityInfoW, TRUSTEE_IS_SID, TRUSTEE_IS_USER, TRUSTEE_W,
    };
    use windows_sys::Win32::Security::Cryptography::{
        BCRYPT_USE_SYSTEM_PREFERRED_RNG, BCryptGenRandom,
    };
    use windows_sys::Win32::Security::{
        ACL, DACL_SECURITY_INFORMATION, GetTokenInformation, NO_INHERITANCE,
        PROTECTED_DACL_SECURITY_INFORMATION, TOKEN_QUERY, TOKEN_USER, TokenUser,
    };
    use windows_sys::Win32::Storage::FileSystem::FILE_ALL_ACCESS;
    use windows_sys::Win32::System::Console::{
        GetStdHandle, STD_ERROR_HANDLE, STD_INPUT_HANDLE, STD_OUTPUT_HANDLE,
    };
    use windows_sys::Win32::System::Threading::{
        CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW, CREATE_SUSPENDED, GetCurrentProcess,
        GetExitCodeProcess, GetProcessTimes, OpenProcess, OpenProcessToken,
        PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_SYNCHRONIZE, WaitForSingleObject,
    };

    #[link(name = "ntdll")]
    unsafe extern "system" {
        fn NtResumeProcess(process: HANDLE) -> i32;
    }

    /// What started this may be reading these until they close. Both processes outlive this one,
    /// so if they inherited them, that reader would wait for as long as the server runs.
    pub fn keep_own_output_to_self() {
        for which in [STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE] {
            // SAFETY: a handle of this process, or an invalid one, which only makes this fail.
            unsafe { SetHandleInformation(GetStdHandle(which), HANDLE_FLAG_INHERIT, 0) };
        }
    }

    pub fn random(bytes: &mut [u8]) -> io::Result<()> {
        // SAFETY: the buffer and its length are this slice's own.
        let status = unsafe {
            BCryptGenRandom(
                ptr::null_mut(),
                bytes.as_mut_ptr(),
                bytes.len() as u32,
                BCRYPT_USE_SYSTEM_PREFERRED_RNG,
            )
        };
        if status == 0 {
            Ok(())
        } else {
            Err(io::Error::other(format!("BCryptGenRandom: {status:#x}")))
        }
    }

    /// No window and no share of the launcher's console, or anything MARS later starts would open
    /// one. Under `--attached` it stays in the launcher's group, as a test's tree expects. Held
    /// before its first instruction until `let_run`, however it is started.
    pub fn outlive_the_launcher(command: &mut Command, attached: bool) {
        let group = if attached {
            0
        } else {
            CREATE_NEW_PROCESS_GROUP
        };
        command.creation_flags(CREATE_NO_WINDOW | CREATE_SUSPENDED | group);
    }

    pub fn let_run(child: &Child) -> io::Result<()> {
        // SAFETY: the child's own handle, open for as long as `child` is.
        match unsafe { NtResumeProcess(child.as_raw_handle().cast()) } {
            0 => Ok(()),
            status => Err(io::Error::other(format!("NtResumeProcess: {status:#x}"))),
        }
    }

    fn creation_time(process: HANDLE) -> Option<u64> {
        let zero = FILETIME {
            dwLowDateTime: 0,
            dwHighDateTime: 0,
        };
        let (mut created, mut exited, mut kernel, mut user) = (zero, zero, zero, zero);
        // SAFETY: an open handle, and four FILETIMEs of this frame.
        let got =
            unsafe { GetProcessTimes(process, &mut created, &mut exited, &mut kernel, &mut user) };
        (got != 0)
            .then(|| (u64::from(created.dwHighDateTime) << 32) | u64::from(created.dwLowDateTime))
    }

    pub fn start_time_of_child(child: &Child) -> Option<u64> {
        creation_time(child.as_raw_handle().cast())
    }

    /// `None` when no process has this pid any more, one that has exited included.
    pub fn start_time_of(pid: u32) -> Option<u64> {
        // SAFETY: asks only to read its times, and the handle is closed below.
        let process = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid) };
        if process.is_null() {
            return None;
        }
        let mut code = 0u32;
        // SAFETY: a handle opened above, and a local to write to.
        let read = unsafe { GetExitCodeProcess(process, &mut code) };
        let running = read != 0 && code == STILL_ACTIVE as u32;
        let time = if running {
            creation_time(process)
        } else {
            None
        };
        // SAFETY: as above, and closed once.
        unsafe { CloseHandle(process) };
        time
    }

    pub fn stop_tree(pid: u32) {
        let system = std::env::var_os("SystemRoot").unwrap_or_else(|| r"C:\Windows".into());
        let taskkill = Path::new(&system).join("System32").join("taskkill.exe");
        let _ = Command::new(taskkill)
            .args(["/T", "/F", "/PID", &pid.to_string()])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }

    pub fn wait_for_exit(pid: u32, limit: Duration) -> bool {
        // SAFETY: asks only to wait on it, and the handle is closed below.
        let process = unsafe { OpenProcess(PROCESS_SYNCHRONIZE, 0, pid) };
        if process.is_null() {
            return true; // already gone
        }
        let millis = u32::try_from(limit.as_millis()).unwrap_or(u32::MAX);
        // SAFETY: a handle opened above, not yet closed.
        let waited = unsafe { WaitForSingleObject(process, millis) };
        // SAFETY: as above, and closed once.
        unsafe { CloseHandle(process) };
        waited == WAIT_OBJECT_0
    }

    /// As `mentis/readonly.py`'s `keep_to_user`: the DACL replaced by one entry, full control for
    /// this user by SID, protected from inheritance.
    pub fn keep_to_user(path: &Path) -> io::Result<()> {
        let wide: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
        let mut token: HANDLE = ptr::null_mut();
        // SAFETY: the pseudo-handle needs no closing, and `token` is written on success.
        if unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) } == 0 {
            return Err(io::Error::last_os_error());
        }
        let mut needed = 0u32;
        // SAFETY: asking the size with no buffer, which is documented to fail and say it.
        unsafe { GetTokenInformation(token, TokenUser, ptr::null_mut(), 0, &mut needed) };
        // In u64s, so the buffer is aligned for the TOKEN_USER written into it.
        let mut buffer = vec![0u64; (needed as usize).div_ceil(8)];
        // SAFETY: `buffer` holds at least `needed` bytes.
        let got = unsafe {
            GetTokenInformation(
                token,
                TokenUser,
                buffer.as_mut_ptr().cast(),
                needed,
                &mut needed,
            )
        };
        let token_error = io::Error::last_os_error();
        // SAFETY: opened above and closed once.
        unsafe { CloseHandle(token) };
        if got == 0 {
            return Err(token_error);
        }
        // SAFETY: GetTokenInformation filled this as a TOKEN_USER, and `buffer` outlives its use.
        let sid = unsafe { (*buffer.as_ptr().cast::<TOKEN_USER>()).User.Sid };
        let entry = EXPLICIT_ACCESS_W {
            grfAccessPermissions: FILE_ALL_ACCESS,
            grfAccessMode: SET_ACCESS,
            grfInheritance: NO_INHERITANCE,
            Trustee: TRUSTEE_W {
                pMultipleTrustee: ptr::null_mut(),
                MultipleTrusteeOperation: NO_MULTIPLE_TRUSTEE,
                TrusteeForm: TRUSTEE_IS_SID,
                TrusteeType: TRUSTEE_IS_USER,
                ptstrName: sid.cast(),
            },
        };
        let mut acl: *mut ACL = ptr::null_mut();
        // SAFETY: one entry, no old ACL, and `acl` is freed below.
        let made = unsafe { SetEntriesInAclW(1, &entry, ptr::null(), &mut acl) };
        if made != ERROR_SUCCESS {
            return Err(io::Error::from_raw_os_error(made as i32));
        }
        // SAFETY: `wide` is NUL-terminated, and `acl` is what SetEntriesInAclW made.
        let set = unsafe {
            SetNamedSecurityInfoW(
                wide.as_ptr(),
                SE_FILE_OBJECT,
                DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                ptr::null_mut(),
                ptr::null_mut(),
                acl,
                ptr::null(),
            )
        };
        // SAFETY: allocated by SetEntriesInAclW, freed once.
        unsafe { LocalFree(acl.cast()) };
        if set == ERROR_SUCCESS {
            Ok(())
        } else {
            Err(io::Error::from_raw_os_error(set as i32))
        }
    }
}

#[cfg(unix)]
mod platform {
    use std::fs::{self, File, Permissions};
    use std::io::{self, Read};
    use std::os::unix::fs::PermissionsExt;
    use std::os::unix::process::CommandExt;
    use std::path::Path;
    use std::process::{Child, Command};
    use std::time::{Duration, Instant};

    /// A child's stdio is replaced before it runs, so nothing of this one's reaches it.
    pub fn keep_own_output_to_self() {}

    pub fn random(bytes: &mut [u8]) -> io::Result<()> {
        File::open("/dev/urandom")?.read_exact(bytes)
    }

    /// Its own session, so it survives whatever started the launcher. Under `--attached` it stays
    /// in the launcher's, as a test's tree expects.
    pub fn outlive_the_launcher(command: &mut Command, attached: bool) {
        if !attached {
            // SAFETY: `setsid` is async-signal-safe, and nothing else runs between fork and exec.
            unsafe {
                command.pre_exec(|| {
                    if libc::setsid() == -1 {
                        return Err(io::Error::last_os_error());
                    }
                    Ok(())
                });
            }
        }
    }

    /// Nothing holds it: the journal is written just after it starts, so a kill exactly there
    /// leaves it unrecorded. Windows is the gate, and POSIX is a Linux check.
    pub fn let_run(_child: &Child) -> io::Result<()> {
        Ok(())
    }

    pub fn start_time_of_child(child: &Child) -> Option<u64> {
        start_time_of(child.id())
    }

    /// Field 22 of `/proc/<pid>/stat`, counted from after the command's closing bracket. A zombie
    /// has exited, and says so in field 3.
    pub fn start_time_of(pid: u32) -> Option<u64> {
        let stat = fs::read_to_string(format!("/proc/{pid}/stat")).ok()?;
        let mut fields = stat.rsplit_once(')')?.1.split_whitespace();
        if fields.next()? == "Z" {
            return None;
        }
        fields.nth(18)?.parse().ok()
    }

    pub fn stop_tree(pid: u32) {
        // SAFETY: a signal to the session's group, which this process leads when detached.
        unsafe { libc::kill(-(pid as libc::pid_t), libc::SIGKILL) };
        // SAFETY: as above, for one that doesn't lead a group.
        unsafe { libc::kill(pid as libc::pid_t, libc::SIGKILL) };
    }

    pub fn wait_for_exit(pid: u32, limit: Duration) -> bool {
        let began = Instant::now();
        // SAFETY: signal 0 delivers nothing and only asks whether it exists.
        while unsafe { libc::kill(pid as libc::pid_t, 0) } == 0 {
            if began.elapsed() > limit {
                return false;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        true
    }

    pub fn keep_to_user(path: &Path) -> io::Result<()> {
        fs::set_permissions(path, Permissions::from_mode(0o600))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(text: &str) -> Vec<String> {
        text.split_whitespace().map(str::to_owned).collect()
    }

    fn refused(text: &str) -> String {
        match parse(&args(text)) {
            Err(Refused(words)) => words,
            Ok(asked) => panic!("{text:?} was taken: {asked:?}"),
        }
    }

    #[cfg(windows)]
    const ROOT: &str = r"C:\r";
    #[cfg(unix)]
    const ROOT: &str = "/r";

    #[test]
    fn upstream_is_only_this_machines_port() {
        assert!(check_upstream("http://127.0.0.1:8873").is_ok());
        for bad in [
            "http://localhost:8873",
            "https://127.0.0.1:8873",
            "http://127.0.0.1",
            "http://127.0.0.1:",
            "http://127.0.0.1:0",
            "http://127.0.0.1:99999",
            "http://127.0.0.1:8873/",
            "http://127.0.0.1:8873/x",
            "http://127.0.0.1:08873",
            "http://10.0.0.1:8873",
        ] {
            assert!(check_upstream(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn paths_must_be_absolute() {
        for (flag, words) in [
            ("--python", "--python must be an absolute path"),
            ("--front", "--front must be an absolute path"),
            ("--code", "--code must be an absolute path"),
            ("--workspace", "--workspace must be an absolute path"),
            (
                "--writable-root",
                "--writable-root must be an absolute path",
            ),
        ] {
            let said = refused(&format!("{ROOT}/brain --port 8871 {flag} relative"));
            assert!(said.contains(words), "{said}");
        }
        assert!(refused("brain --port 8871").contains("<brain> must be an absolute path"));
    }

    #[test]
    fn stop_says_front_and_means_only_the_front() {
        assert!(refused("stop").contains("--front"));
        assert!(refused("stop --python").contains("doesn't take"));
        assert_eq!(
            parse(&args("stop --front --run-dir x")),
            Ok(Asked::StopFront {
                run_dir: Some("x".into()),
                port: DEFAULT_PUBLIC_PORT
            })
        );
        assert_eq!(
            parse(&args("stop --front --port 8871")),
            Ok(Asked::StopFront {
                run_dir: None,
                port: 8871
            })
        );
    }

    #[test]
    fn recover_names_a_run_directory_and_nothing_else() {
        assert_eq!(
            parse(&args("recover --run-dir x")),
            Ok(Asked::Recover {
                run_dir: Some("x".into()),
                port: DEFAULT_PUBLIC_PORT
            })
        );
        assert!(refused("recover --front").contains("recover doesn't take"));
    }

    #[test]
    fn a_process_is_known_by_its_pid_and_when_it_started() {
        let me = std::process::id();
        let when = platform::start_time_of(me).expect("this process has a start time");
        assert!(is_still(me, when));
        assert!(!is_still(me, when + 1), "the same pid, another process");
    }

    #[test]
    fn only_is_one_side_and_options_are_known() {
        assert!(refused("--only both").contains("front or python"));
        assert!(refused("--nonsense 1").contains("no such option"));
        assert!(refused("--port").contains("needs a value"));
        assert!(refused("--port 0").contains("a port from 1"));
        assert!(refused(&format!("{ROOT}/a {ROOT}/b")).contains("one Brain"));
    }

    #[test]
    fn a_secret_is_as_token_urlsafe_says() {
        // RFC 4648's vectors, in its URL-safe alphabet with no padding.
        for (bytes, text) in [
            (&b""[..], ""),
            (b"f", "Zg"),
            (b"fo", "Zm8"),
            (b"foo", "Zm9v"),
            (b"foob", "Zm9vYg"),
            (&[0xfb, 0xff, 0xfe], "-__-"),
        ] {
            assert_eq!(urlsafe_base64(bytes), text);
        }
        let one = new_secret().unwrap();
        assert_eq!(one.len(), 43);
        assert_ne!(one, new_secret().unwrap());
    }

    #[test]
    fn step_three_and_four_commands_are_the_contracts() {
        let remembered = StartedWith {
            python: "py".into(),
            code: "code".into(),
            workspace: "ws".into(),
            writable_roots: vec!["w1".into()],
            mars: Some("mars stdio".into()),
            dist: "dist".into(),
            route_table: Some("table".into()),
        };
        assert_eq!(
            python_args("b", 18871, "http://127.0.0.1:8871", &remembered).join(" "),
            "-m mentis.web b --host 127.0.0.1 --port 18871 --answers-at \
             http://127.0.0.1:8871 --workspace ws --writable-root w1 --mars mars stdio"
        );
        assert_eq!(
            front_args("b", "h", 8871, "http://127.0.0.1:18871", &remembered).join(" "),
            "b --host h --port 8871 --upstream http://127.0.0.1:18871 --dist dist \
             --route-table table"
        );
    }

    #[test]
    fn a_run_directory_yet_to_be_made_is_compared_where_it_will_be() {
        let top = env::temp_dir().canonicalize().unwrap();
        assert_eq!(
            resolved(&top.join("no").join("such")),
            top.join("no").join("such")
        );
    }

    #[test]
    fn hosts_for_urls_and_for_connecting() {
        assert_eq!(answers_at("127.0.0.1", 8871), "http://127.0.0.1:8871");
        assert_eq!(answers_at("::1", 8871), "http://[::1]:8871");
        assert_eq!(reachable_host("0.0.0.0"), "127.0.0.1");
        assert_eq!(reachable_host("10.0.0.5"), "10.0.0.5");
    }
}
