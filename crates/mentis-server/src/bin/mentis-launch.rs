//! Starts Python and the front as siblings, says they answer, and exits. Contract:
//! `docs/rust/contracts/launcher.md`.
//!
//! **Nothing here restarts anything,** and after step 5 of the order it touches nothing. A start
//! that fails stops what this invocation started, which isn't recovery: nothing had been handed
//! over. `--attached` stays only as both processes' parent, for tests and the bench.

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
    STOP_PATH, Started, default_private_port,
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
mentis-launch stop [--run-dir <dir>] [--port <port>] --front";

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
}

fn port_of(flag: &str, text: &str) -> Result<u16, Refused> {
    match text.parse::<u16>() {
        Ok(port) if port > 0 => Ok(port),
        _ => refuse(format!("{flag} is a port from 1 to 65535, not {text:?}")),
    }
}

fn parse_stop(args: &[String]) -> Result<Asked, Refused> {
    let (mut run_dir, mut port, mut front) = (None, DEFAULT_PUBLIC_PORT, false);
    let mut rest = args.iter();
    while let Some(flag) = rest.next() {
        match flag.as_str() {
            "--front" => front = true,
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
            other => return refuse(format!("stop doesn't take {other:?}\n{USAGE}")),
        }
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
    if args.first().map(String::as_str) == Some("stop") {
        return parse_stop(&args[1..]);
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

/// How both processes were started, beside `launch.json`, so a later `--only` or a script needs
/// only the run directory. `--upstream` is deliberately not here: it isn't remembered.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
struct Remembered {
    format: u32,
    python: String,
    code: String,
    workspace: String,
    writable_roots: Vec<String>,
    mars: Option<String>,
    dist: String,
    route_table: Option<String>,
}

const REMEMBERED_FILE: &str = "launch-args.json";
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

/// A process being started, with where its log stood so a refusal can quote only its own words.
struct Starting {
    child: Child,
    who: &'static str,
    log: PathBuf,
    log_from: u64,
}

impl Starting {
    /// What this invocation started goes with it, its children too.
    fn stop(&mut self) {
        platform::stop_tree(&mut self.child);
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

/// `env` is added to what the launcher itself has, which both processes inherit.
fn start(
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
    let child = command
        .spawn()
        .map_err(|e| Refused(format!("can't start {who}, {program:?}: {e}")))?;
    Ok(Starting {
        child,
        who,
        log: log.to_owned(),
        log_from,
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

fn read_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T, Refused> {
    let text = fs::read_to_string(path)
        .map_err(|e| Refused(format!("can't read {}: {e}", path.display())))?;
    serde_json::from_str(&text)
        .map_err(|e| Refused(format!("{} is not as it should be: {e}", path.display())))
}

fn read_state(run_dir: &Path) -> Result<LaunchState, Refused> {
    let state: LaunchState = read_json(&run_dir.join(STATE_FILE))?;
    if state.format != STATE_FORMAT {
        return refuse(format!(
            "{STATE_FILE} says format {}, and this build reads {STATE_FORMAT}",
            state.format
        ));
    }
    Ok(state)
}

fn read_remembered(run_dir: &Path) -> Result<Option<Remembered>, Refused> {
    let path = run_dir.join(REMEMBERED_FILE);
    if !path.exists() {
        return Ok(None);
    }
    let remembered: Remembered = read_json(&path)?;
    if remembered.format != STATE_FORMAT {
        return refuse(format!(
            "{REMEMBERED_FILE} says format {}, and this build reads {STATE_FORMAT}",
            remembered.format
        ));
    }
    Ok(Some(remembered))
}

fn write_both(run_dir: &Path, remembered: &Remembered, state: &LaunchState) -> Result<(), Refused> {
    let text = |value: Result<String, serde_json::Error>| {
        value.map_err(|e| Refused(format!("can't say what was started: {e}")))
    };
    write_private(
        &run_dir.join(REMEMBERED_FILE),
        &text(serde_json::to_string_pretty(remembered))?,
    )?;
    write_private(
        &run_dir.join(STATE_FILE),
        &text(serde_json::to_string_pretty(state))?,
    )
}

fn python_args(
    brain: &str,
    private_port: u16,
    answers: &str,
    remembered: &Remembered,
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
    remembered: &Remembered,
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

fn start_python(
    run_dir: &Path,
    brain: &str,
    private_port: u16,
    answers: &str,
    secret: &str,
    remembered: &Remembered,
    attached: bool,
) -> Result<Starting, Refused> {
    let mut python = start(
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
    run_dir: &Path,
    front: &str,
    brain: &str,
    host: &str,
    port: u16,
    upstream: &str,
    secret: &str,
    remembered: &Remembered,
    attached: bool,
) -> Result<Starting, Refused> {
    let mut started = start(
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

    look("the public", &host, port)?;
    look("the private", "127.0.0.1", private_port)?;

    fs::create_dir_all(&run_dir)
        .map_err(|e| Refused(format!("can't make {}: {e}", run_dir.display())))?;
    let secret = new_secret()?;
    let answers = answers_at(&host, port);
    let remembered = Remembered {
        format: STATE_FORMAT,
        python: python.clone(),
        code,
        workspace,
        writable_roots: given.writable_roots,
        mars: given.mars,
        dist,
        route_table: given.route_table,
    };

    let mut python_started = start_python(
        &run_dir,
        &brain,
        private_port,
        &answers,
        &secret,
        &remembered,
        given.attached,
    )?;
    let upstream = given
        .upstream
        .unwrap_or_else(|| format!("http://127.0.0.1:{private_port}"));
    let mut front_started = match start_front(
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
    };
    if let Err(refused) = write_both(&run_dir, &remembered, &state) {
        front_started.stop();
        python_started.stop();
        return Err(refused);
    }
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
    let before = read_remembered(&run_dir)?;
    let python = given
        .python
        .or_else(|| before.as_ref().map(|r| r.python.clone()))
        .unwrap_or_else(|| state.python.executable.clone());
    let code = given
        .code
        .or_else(|| before.as_ref().map(|r| r.code.clone()));
    let dist = match given
        .dist
        .or_else(|| before.as_ref().map(|r| r.dist.clone()))
    {
        Some(dist) => dist,
        None => default_dist(code.as_deref())?,
    };
    let remembered = Remembered {
        format: STATE_FORMAT,
        python,
        code: code.unwrap_or_default(),
        workspace: given
            .workspace
            .or_else(|| before.as_ref().map(|r| r.workspace.clone()))
            .unwrap_or_default(),
        writable_roots: if given.writable_roots.is_empty() {
            before
                .as_ref()
                .map(|r| r.writable_roots.clone())
                .unwrap_or_default()
        } else {
            given.writable_roots
        },
        mars: given
            .mars
            .or_else(|| before.as_ref().and_then(|r| r.mars.clone())),
        dist,
        route_table: given
            .route_table
            .or_else(|| before.as_ref().and_then(|r| r.route_table.clone())),
    };

    match only {
        Only::Python => {
            if remembered.code.is_empty() || remembered.workspace.is_empty() {
                return refuse(format!(
                    "--only python needs --code and --workspace, or {REMEMBERED_FILE}"
                ));
            }
            require_file("--python", &remembered.python)?;
            look("the private", "127.0.0.1", state.private_port)?;
            let mut started = start_python(
                &run_dir,
                &state.brain.clone(),
                state.private_port,
                &state.answers_at.clone(),
                &state.secret.clone(),
                &remembered,
                given.attached,
            )?;
            state.python = started_record(&started, &remembered.python);
            if let Err(refused) = write_both(&run_dir, &remembered, &state) {
                started.stop();
                return Err(refused);
            }
        }
        Only::Front => {
            let front = match given.front {
                Some(front) => front,
                None => default_front()?,
            };
            require_file("--front", &front)?;
            if let Some(table) = &remembered.route_table {
                require_file("--route-table", table)?;
            }
            look("the public", &state.public_host, state.public_port)?;
            let upstream = given
                .upstream
                .unwrap_or_else(|| format!("http://127.0.0.1:{}", state.private_port));
            let mut started = start_front(
                &run_dir,
                &front,
                &state.brain.clone(),
                &state.public_host.clone(),
                state.public_port,
                &upstream,
                &state.secret.clone(),
                &remembered,
                given.attached,
            )?;
            state.front = started_record(&started, &front);
            if let Err(refused) = write_both(&run_dir, &remembered, &state) {
                started.stop();
                return Err(refused);
            }
        }
    }
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
    if !platform::wait_for_exit(state.front.pid, limit) {
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
    use std::os::windows::process::CommandExt;
    use std::path::Path;
    use std::process::{Child, Command, Stdio};
    use std::ptr;
    use std::time::Duration;

    use windows_sys::Win32::Foundation::{
        CloseHandle, ERROR_SUCCESS, HANDLE, HANDLE_FLAG_INHERIT, LocalFree, SetHandleInformation,
        WAIT_OBJECT_0,
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
        CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW, GetCurrentProcess, OpenProcess,
        OpenProcessToken, PROCESS_SYNCHRONIZE, WaitForSingleObject,
    };

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
    /// one. Under `--attached` it stays in the launcher's group, as a test's tree expects.
    pub fn outlive_the_launcher(command: &mut Command, attached: bool) {
        let group = if attached {
            0
        } else {
            CREATE_NEW_PROCESS_GROUP
        };
        command.creation_flags(CREATE_NO_WINDOW | group);
    }

    pub fn stop_tree(child: &mut Child) {
        let system = std::env::var_os("SystemRoot").unwrap_or_else(|| r"C:\Windows".into());
        let taskkill = Path::new(&system).join("System32").join("taskkill.exe");
        let _ = Command::new(taskkill)
            .args(["/T", "/F", "/PID", &child.id().to_string()])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .creation_flags(CREATE_NO_WINDOW)
            .status();
        let _ = child.kill();
        let _ = child.wait();
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

    pub fn stop_tree(child: &mut Child) {
        // SAFETY: a signal to the session's group, which this child leads when detached.
        unsafe { libc::kill(-(child.id() as libc::pid_t), libc::SIGKILL) };
        let _ = child.kill();
        let _ = child.wait();
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
        let remembered = Remembered {
            format: STATE_FORMAT,
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
