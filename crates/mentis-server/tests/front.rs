//! The front on real sockets, with a stand-in where Python goes. What these show is the front's
//! own behaviour. Whether its answers are Python's is `tests/front/test_front_contract.py`, on
//! `PAIR`. No test name here may hold the substring row K filters on (`R1-acceptance.md`, K).

use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use mentis_record::{ReadClass, ReadScope, RecordError, RecordReader};
use mentis_server::front::{self, Config, Running};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::Semaphore;

const SECRET: &str = "the-boot-secret";
const OK: &[u8] = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok";

struct NoRecord;

impl RecordReader for NoRecord {
    fn read_scope(&self, _class: ReadClass) -> Result<Box<dyn ReadScope>, RecordError> {
        Err(RecordError::Sqlite {
            detail: "not in these tests".into(),
        })
    }

    fn corpus_id(&self) -> &str {
        ""
    }
}

/// What the stand-in does with a request, once it has read its head.
#[derive(Clone)]
enum Script {
    /// Send this and close.
    Answer(&'static [u8]),
    /// Read the declared body, then answer.
    ReadBodyThenAnswer(&'static [u8]),
    /// Close without a word.
    Vanish,
    /// Send the first part, wait for a permit, send the second, close.
    Parts(&'static [u8], Arc<Semaphore>, &'static [u8]),
    /// Wait for a permit, then answer and close.
    AnswerWhenAllowed(Arc<Semaphore>, &'static [u8]),
    /// Send the first part and hang up, however much was promised.
    CutOff(&'static [u8]),
}

struct StandIn {
    address: SocketAddr,
    seen: Arc<Mutex<Vec<Vec<u8>>>>,
    bodies: Arc<Mutex<Vec<usize>>>,
}

fn declared_length(head: &[u8]) -> usize {
    let text = String::from_utf8_lossy(head).to_ascii_lowercase();
    text.lines()
        .find_map(|line| line.strip_prefix("content-length:"))
        .and_then(|value| value.trim().parse().ok())
        .unwrap_or(0)
}

async fn stand_in(script: Script) -> StandIn {
    let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    let address = listener.local_addr().unwrap();
    let seen = Arc::new(Mutex::new(Vec::new()));
    let bodies = Arc::new(Mutex::new(Vec::new()));
    let (seen_by_it, bodies_by_it) = (seen.clone(), bodies.clone());
    tokio::spawn(async move {
        loop {
            let Ok((mut stream, _)) = listener.accept().await else {
                return;
            };
            let (seen, bodies, script) = (seen_by_it.clone(), bodies_by_it.clone(), script.clone());
            tokio::spawn(async move {
                let mut buffer = Vec::new();
                let mut chunk = [0; 65536];
                let end = loop {
                    if let Some(end) = buffer.windows(4).position(|w| w == b"\r\n\r\n") {
                        break end + 4;
                    }
                    match stream.read(&mut chunk).await {
                        Ok(0) | Err(_) => return,
                        Ok(got) => buffer.extend_from_slice(&chunk[..got]),
                    }
                };
                seen.lock().unwrap().push(buffer[..end].to_vec());
                match script {
                    Script::Answer(bytes) => {
                        let _ = stream.write_all(bytes).await;
                    }
                    Script::ReadBodyThenAnswer(bytes) => {
                        let want = declared_length(&buffer[..end]);
                        let mut got = buffer.len() - end;
                        while got < want {
                            match stream.read(&mut chunk).await {
                                Ok(0) | Err(_) => {
                                    bodies.lock().unwrap().push(got);
                                    return;
                                }
                                Ok(more) => got += more,
                            }
                        }
                        bodies.lock().unwrap().push(got);
                        let _ = stream.write_all(bytes).await;
                    }
                    Script::Vanish => {}
                    Script::Parts(first, gate, second) => {
                        let _ = stream.write_all(first).await;
                        let _ = gate.acquire().await.unwrap();
                        let _ = stream.write_all(second).await;
                    }
                    Script::AnswerWhenAllowed(gate, bytes) => {
                        let _ = gate.acquire().await.unwrap();
                        let _ = stream.write_all(bytes).await;
                    }
                    Script::CutOff(bytes) => {
                        let _ = stream.write_all(bytes).await;
                    }
                }
            });
        }
    });
    StandIn {
        address,
        seen,
        bodies,
    }
}

/// A port nothing is listening on.
async fn nobody() -> SocketAddr {
    let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    listener.local_addr().unwrap()
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("mentis-front-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(dir.join("dist/assets")).unwrap();
    std::fs::write(dir.join("dist/index.html"), "<index>").unwrap();
    std::fs::write(dir.join("dist/assets/app-1.js"), "js").unwrap();
    dir
}

fn config(scratch: &Path, upstream: SocketAddr, table: Option<PathBuf>) -> Config {
    Config {
        brain: scratch.to_path_buf(),
        host: "127.0.0.1".into(),
        port: 0,
        upstream,
        dist: scratch.join("dist"),
        route_table: table,
        secret: SECRET.into(),
        drain_limit: Duration::from_secs(5),
    }
}

struct Up {
    address: SocketAddr,
    serving: tokio::task::JoinHandle<()>,
}

async fn up_with(config: Config) -> Up {
    let running: Running = match front::start_with(config, Arc::new(NoRecord)).await {
        Ok(running) => running,
        Err(front::Refused(why)) => panic!("{why}"),
    };
    let address = running.address;
    Up {
        address,
        serving: tokio::spawn(running.serve()),
    }
}

async fn up(name: &str, upstream: SocketAddr) -> Up {
    up_with(config(&scratch(name), upstream, None)).await
}

/// Send these bytes on a new connection and read until it ends.
async fn exchange(address: SocketAddr, request: &[u8]) -> Vec<u8> {
    let mut stream = TcpStream::connect(address).await.unwrap();
    stream.write_all(request).await.unwrap();
    let mut got = Vec::new();
    let _ = stream.read_to_end(&mut got).await;
    got
}

fn text(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).into_owned()
}

fn status(bytes: &[u8]) -> String {
    text(bytes).lines().next().unwrap_or("").to_owned()
}

const GET_CLOSE: &[u8] = b"GET /api/x HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n";

#[tokio::test(flavor = "multi_thread")]
async fn a_forwarded_request_arrives_byte_for_byte_with_the_real_peer() {
    let python = stand_in(Script::Answer(OK)).await;
    let front = up("bytes", python.address).await;
    let got = exchange(
        front.address,
        b"GET /a%20b/../c?x=%41 HTTP/1.1\r\nHOST:  LocalHost:9 \r\nX-Mentis-Peer: 9.9.9.9\r\nx-mentis-boot-secret: forged\r\nA: 1\r\nConnection: close\r\n\r\n",
    )
    .await;
    assert_eq!(got, OK);
    assert_eq!(
        text(&python.seen.lock().unwrap()[0]),
        format!(
            "GET /a%20b/../c?x=%41 HTTP/1.1\r\nHOST:  LocalHost:9 \r\nA: 1\r\nConnection: close\r\nX-Mentis-Peer: 127.0.0.1\r\nX-Mentis-Boot-Secret: {SECRET}\r\n\r\n"
        )
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn an_answer_goes_back_as_python_sent_it_repeated_headers_and_all() {
    const ODD: &[u8] = b"HTTP/1.1 404 Not Found\r\nSet-Cookie: b=1\r\nsEt-cOOkie: a=2\r\nX-Spacing:   three  \r\nConnection: close\r\nContent-Length: 4\r\n\r\nbody";
    let python = stand_in(Script::Answer(ODD)).await;
    let front = up("answer", python.address).await;
    assert_eq!(exchange(front.address, GET_CLOSE).await, ODD);
}

#[tokio::test(flavor = "multi_thread")]
async fn first_bytes_arrive_before_python_has_finished_writing() {
    let gate = Arc::new(Semaphore::new(0));
    let python = stand_in(Script::Parts(
        b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nfirst",
        gate.clone(),
        b"secnd",
    ))
    .await;
    let front = up("stream", python.address).await;
    let mut stream = TcpStream::connect(front.address).await.unwrap();
    stream.write_all(GET_CLOSE).await.unwrap();
    let mut got = Vec::new();
    let mut chunk = [0; 1024];
    while !text(&got).ends_with("first") {
        let more = tokio::time::timeout(Duration::from_secs(5), stream.read(&mut chunk))
            .await
            .expect("the first part came before the second was allowed")
            .unwrap();
        assert!(more > 0);
        got.extend_from_slice(&chunk[..more]);
    }
    gate.add_permits(1);
    stream.read_to_end(&mut got).await.unwrap();
    assert!(text(&got).ends_with("firstsecnd"));
}

#[tokio::test(flavor = "multi_thread")]
async fn nothing_listening_is_the_503_that_says_nothing_was_done() {
    let front = up("gone", nobody().await).await;
    let got = text(&exchange(front.address, GET_CLOSE).await);
    assert!(
        got.starts_with("HTTP/1.1 503 Service Unavailable\r\n"),
        "{got}"
    );
    assert!(got.contains("Connection: close\r\n"), "{got}");
    assert!(
        got.ends_with("{\"error\": \"Python is not answering behind this front, so this request did not reach it and nothing was done.\"}"),
        "{got}"
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn python_going_with_the_request_in_hand_is_the_503_that_says_unknown() {
    let python = stand_in(Script::Vanish).await;
    let front = up("in-hand", python.address).await;
    let got = text(&exchange(front.address, GET_CLOSE).await);
    assert!(got.starts_with("HTTP/1.1 503 "), "{got}");
    assert!(
        got.ends_with("{\"error\": \"Python stopped with this request in hand, so the result is unknown. It may still have done it: check the record before repeating it.\"}"),
        "{got}"
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn a_head_python_never_finished_is_still_that_503_and_no_part_of_it_is_passed_on() {
    let python = stand_in(Script::CutOff(b"HTTP/1.1 200 OK\r\nContent-Le")).await;
    let front = up("half-head", python.address).await;
    let got = text(&exchange(front.address, GET_CLOSE).await);
    assert!(got.starts_with("HTTP/1.1 503 "), "{got}");
}

#[tokio::test(flavor = "multi_thread")]
async fn python_going_mid_answer_ends_the_connection_short_and_adds_nothing() {
    const SHORT: &[u8] = b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\npartial";
    let python = stand_in(Script::CutOff(SHORT)).await;
    let front = up("short", python.address).await;
    assert_eq!(exchange(front.address, GET_CLOSE).await, SHORT);
}

#[tokio::test(flavor = "multi_thread")]
async fn requests_on_one_connection_each_get_their_own_connection_to_python() {
    let python = stand_in(Script::Answer(OK)).await;
    let front = up("kept", python.address).await;
    let mut stream = TcpStream::connect(front.address).await.unwrap();
    let one = b"GET /one HTTP/1.1\r\nHost: localhost\r\n\r\n";
    let two = b"GET /two HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n";
    stream.write_all(one).await.unwrap();
    let mut chunk = [0; 1024];
    let mut first = Vec::new();
    while first.len() < OK.len() {
        let more = stream.read(&mut chunk).await.unwrap();
        first.extend_from_slice(&chunk[..more]);
    }
    assert_eq!(first, OK);
    // And pipelined bytes are the next request, not lost.
    stream.write_all(two).await.unwrap();
    let mut second = Vec::new();
    stream.read_to_end(&mut second).await.unwrap();
    assert_eq!(second, OK);
    let seen = python.seen.lock().unwrap();
    assert_eq!(seen.len(), 2);
    assert!(text(&seen[0]).starts_with("GET /one "));
    assert!(text(&seen[1]).starts_with("GET /two "));
}

#[tokio::test(flavor = "multi_thread")]
async fn a_body_arriving_with_its_head_and_after_it_all_reach_python() {
    let python = stand_in(Script::ReadBodyThenAnswer(OK)).await;
    let front = up("body", python.address).await;
    let mut stream = TcpStream::connect(front.address).await.unwrap();
    stream
        .write_all(b"POST /x HTTP/1.1\r\nHost: a\r\nConnection: close\r\nContent-Length: 200000\r\n\r\nstart")
        .await
        .unwrap();
    let rest = vec![b'x'; 200_000 - 5];
    stream.write_all(&rest).await.unwrap();
    let mut got = Vec::new();
    stream.read_to_end(&mut got).await.unwrap();
    assert_eq!(got, OK);
    assert_eq!(python.bodies.lock().unwrap()[0], 200_000);
}

#[tokio::test(flavor = "multi_thread")]
async fn a_client_leaving_mid_body_ends_python_s_connection_too() {
    let python = stand_in(Script::ReadBodyThenAnswer(OK)).await;
    let front = up("left", python.address).await;
    let mut stream = TcpStream::connect(front.address).await.unwrap();
    stream
        .write_all(b"POST /x HTTP/1.1\r\nHost: a\r\nContent-Length: 1000\r\n\r\nsome")
        .await
        .unwrap();
    while python.seen.lock().unwrap().is_empty() {
        tokio::time::sleep(Duration::from_millis(5)).await;
    }
    drop(stream);
    let waited = Instant::now();
    while python.bodies.lock().unwrap().is_empty() {
        assert!(
            waited.elapsed() < Duration::from_secs(5),
            "Python was left hanging"
        );
        tokio::time::sleep(Duration::from_millis(5)).await;
    }
    assert!(python.bodies.lock().unwrap()[0] < 1000);
}

#[tokio::test(flavor = "multi_thread")]
async fn expect_continue_is_relayed_as_python_sends_it() {
    const WITH: &[u8] =
        b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok";
    let python = stand_in(Script::Answer(WITH)).await;
    let front = up("continue", python.address).await;
    assert_eq!(
        exchange(
            front.address,
            b"GET /x HTTP/1.1\r\nHost: a\r\nExpect: 100-continue\r\n\r\n"
        )
        .await,
        WITH
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn a_refused_framing_is_answered_here_and_python_hears_nothing_of_it_or_what_follows() {
    let python = stand_in(Script::Answer(OK)).await;
    let front = up("framing", python.address).await;
    const NEXT: &str = "GET /smuggled HTTP/1.1\r\nHost: localhost\r\n\r\n";
    for (request, says) in [
        (
            "POST /x HTTP/1.1\r\nHost: localhost\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
            "HTTP/1.1 501 Not Implemented",
        ),
        (
            "POST /x HTTP/1.1\r\nHost: evil.example\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
            "HTTP/1.1 421 Misdirected Request",
        ),
        (
            "POST /x HTTP/1.1\r\nHost: localhost\r\nTransfer-Encoding : chunked\r\n\r\n",
            "HTTP/1.1 400 a header line is not `Name: value`",
        ),
        (
            "POST /x HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n",
            "HTTP/1.1 400 more than one Content-Length",
        ),
        (
            "POST /x HTTP/1.1\r\nHost: localhost\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n",
            "HTTP/1.1 400 more than one Content-Length",
        ),
        (
            "POST /x HTTP/1.1\r\nHost: localhost\r\nContent-Length: +1\r\n\r\n",
            "HTTP/1.1 400 Content-Length must be digits only",
        ),
        (
            "HEAD /x HTTP/1.1\r\nHost: localhost\r\n\r\n",
            "HTTP/1.1 501 Unsupported method ('HEAD')",
        ),
        (
            "PUT /x HTTP/1.1\r\nHost: localhost\r\nContent-Length: 1\r\n\r\nx",
            "HTTP/1.1 501 Unsupported method ('PUT')",
        ),
    ] {
        let got = exchange(front.address, format!("{request}{NEXT}").as_bytes()).await;
        assert_eq!(status(&got), says, "{request}");
    }
    assert!(python.seen.lock().unwrap().is_empty());
}

#[tokio::test(flavor = "multi_thread")]
async fn a_get_framed_by_transfer_encoding_goes_on_as_a_head_and_its_body_does_not() {
    let python = stand_in(Script::Answer(
        b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 2\r\n\r\nok",
    ))
    .await;
    let front = up("get-te", python.address).await;
    let got = exchange(
        front.address,
        b"GET /x HTTP/1.1\r\nHost: localhost\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\nGET /smuggled HTTP/1.1\r\n\r\n",
    )
    .await;
    assert!(status(&got).contains("200"));
    let seen = python.seen.lock().unwrap();
    assert_eq!(seen.len(), 1);
    assert!(!text(&seen[0]).contains("hello"));
}

#[tokio::test(flavor = "multi_thread")]
async fn what_the_front_cannot_read_python_answers() {
    let python = stand_in(Script::Answer(b"as python says")).await;
    let front = up("odd", python.address).await;
    for line in [
        "GET /x\r\nHost: a",
        "GET /x HTTP/x\r\nHost: a",
        "G'T /x HTTP/1.1",
    ] {
        let got = exchange(front.address, format!("{line}\r\n\r\n").as_bytes()).await;
        assert_eq!(got, b"as python says", "{line}");
    }
    assert_eq!(python.seen.lock().unwrap().len(), 3);
}

#[tokio::test(flavor = "multi_thread")]
async fn a_blank_first_line_ends_the_connection_without_a_word() {
    let python = stand_in(Script::Answer(OK)).await;
    let front = up("blank", python.address).await;
    assert_eq!(exchange(front.address, b"\r\n").await, b"");
    assert!(python.seen.lock().unwrap().is_empty());
}

fn stop_request(secret: &str) -> Vec<u8> {
    format!(
        "POST /private/stop HTTP/1.1\r\nHost: localhost\r\nX-Mentis-Boot-Secret: {secret}\r\nContent-Length: 0\r\n\r\n"
    )
    .into_bytes()
}

#[tokio::test(flavor = "multi_thread")]
async fn private_is_the_front_s_own_and_is_never_forwarded() {
    let python = stand_in(Script::Answer(OK)).await;
    let front = up("private", python.address).await;
    for target in [
        "/private/live",
        "/private/anything",
        "//private/live",
        "///private/live",
        "http://localhost/private/live",
    ] {
        let got = text(
            &exchange(
                front.address,
                format!("GET {target} HTTP/1.1\r\nHost: localhost\r\nX-Mentis-Client: 1\r\n\r\n")
                    .as_bytes(),
            )
            .await,
        );
        assert!(
            got.starts_with("HTTP/1.1 404 Not Found\r\n"),
            "{target}: {got}"
        );
        assert!(
            got.ends_with("{\"error\": \"no such semantic surface\"}"),
            "{got}"
        );
    }
    let wrong = exchange(front.address, &stop_request("wrong")).await;
    assert!(status(&wrong).contains("404"));
    let get = exchange(
        front.address,
        format!("GET /private/stop HTTP/1.1\r\nHost: localhost\r\nX-Mentis-Boot-Secret: {SECRET}\r\n\r\n").as_bytes(),
    )
    .await;
    assert!(status(&get).contains("404"));
    assert!(python.seen.lock().unwrap().is_empty());
    assert!(!front.serving.is_finished());
}

#[tokio::test(flavor = "multi_thread")]
async fn a_planned_stop_refuses_new_connections_at_once_and_finishes_what_is_in_hand() {
    let gate = Arc::new(Semaphore::new(0));
    let python = stand_in(Script::AnswerWhenAllowed(gate.clone(), OK)).await;
    let front = up("drain", python.address).await;

    let mut held = TcpStream::connect(front.address).await.unwrap();
    held.write_all(GET_CLOSE).await.unwrap();
    while python.seen.lock().unwrap().is_empty() {
        tokio::time::sleep(Duration::from_millis(5)).await;
    }
    // One kept open and idle, which a stop ends rather than waits for.
    let mut idle = TcpStream::connect(front.address).await.unwrap();
    tokio::time::sleep(Duration::from_millis(20)).await;

    let answered = exchange(front.address, &stop_request(SECRET)).await;
    assert!(status(&answered).contains("200"), "{}", text(&answered));
    assert!(TcpStream::connect(front.address).await.is_err());

    let mut nothing = Vec::new();
    tokio::time::timeout(Duration::from_secs(2), idle.read_to_end(&mut nothing))
        .await
        .expect("an idle connection ends with the stop")
        .ok();
    assert!(nothing.is_empty());

    assert!(!front.serving.is_finished());
    gate.add_permits(1);
    let mut got = Vec::new();
    held.read_to_end(&mut got).await.unwrap();
    assert_eq!(got, OK);
    tokio::time::timeout(Duration::from_secs(2), front.serving)
        .await
        .expect("nothing in hand, so it ended")
        .unwrap();
}

#[tokio::test(flavor = "multi_thread")]
async fn a_call_past_the_limit_does_not_hold_up_the_stop() {
    let gate = Arc::new(Semaphore::new(0));
    let python = stand_in(Script::AnswerWhenAllowed(gate, OK)).await;
    let mut settings = config(&scratch("limit"), python.address, None);
    settings.drain_limit = Duration::from_millis(300);
    let front = up_with(settings).await;
    let mut held = TcpStream::connect(front.address).await.unwrap();
    held.write_all(GET_CLOSE).await.unwrap();
    while python.seen.lock().unwrap().is_empty() {
        tokio::time::sleep(Duration::from_millis(5)).await;
    }
    let began = Instant::now();
    exchange(front.address, &stop_request(SECRET)).await;
    tokio::time::timeout(Duration::from_secs(3), front.serving)
        .await
        .expect("the limit ended it")
        .unwrap();
    assert!(began.elapsed() >= Duration::from_millis(250));
}

const STATIC_TABLE: &str = r#"{"format":1,"routes":[
    {"id":"api","method":"GET","path":"/api/*","owner":"python"},
    {"id":"fluid","method":"GET","path":"/fluid/api/*","owner":"python"},
    {"id":"static","method":"GET","path":"*","owner":"rust"}]}"#;
const STATIC_BACK: &str = r#"{"format":1,"routes":[
    {"id":"static","method":"GET","path":"*","owner":"python"}]}"#;

async fn static_front(name: &str, upstream: SocketAddr) -> (Up, PathBuf) {
    let dir = scratch(name);
    let table = dir.join("routes.json");
    std::fs::write(&table, STATIC_TABLE).unwrap();
    let front = up_with(config(&dir, upstream, Some(table.clone()))).await;
    (front, table)
}

#[tokio::test(flavor = "multi_thread")]
async fn an_owned_route_answers_with_python_gone_and_a_forwarded_one_does_not() {
    let (front, _) = static_front("owned", nobody().await).await;
    let got = text(
        &exchange(
            front.address,
            b"GET /assets/app-1.js HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n",
        )
        .await,
    );
    assert!(
        got.starts_with("HTTP/1.1 200 OK\r\nServer: BaseHTTP/0.6 Python/3.12.10\r\nDate: "),
        "{got}"
    );
    assert!(got.ends_with("\r\nContent-Type: text/javascript\r\nContent-Length: 2\r\nCache-Control: no-store\r\n\r\njs"), "{got}");
    let forwarded = exchange(
        front.address,
        b"GET /api/anything HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n",
    )
    .await;
    assert!(status(&forwarded).contains("503"));
}

#[tokio::test(flavor = "multi_thread")]
async fn a_door_s_host_check_runs_before_its_handler_and_a_second_request_is_refused_too() {
    let (front, _) = static_front("host", nobody().await).await;
    let got = text(
        &exchange(
            front.address,
            b"GET / HTTP/1.1\r\nHost: evil.example\r\n\r\n",
        )
        .await,
    );
    assert!(
        got.starts_with("HTTP/1.1 421 Misdirected Request\r\n"),
        "{got}"
    );
    assert!(got.contains("\"Host 'evil.example' is not one"), "{got}");
    let none = text(&exchange(front.address, b"GET / HTTP/1.1\r\n\r\n").await);
    assert!(none.contains("\"Host None is not one"), "{none}");
}

#[tokio::test(flavor = "multi_thread")]
async fn an_odd_spelling_of_an_owned_path_is_python_s_to_read() {
    let python = stand_in(Script::Answer(OK)).await;
    let (front, _) = static_front("spelling", python.address).await;
    for target in [
        "//index.html",
        "/%69ndex.html",
        "/index.html;x",
        "/../index.html",
    ] {
        let got = exchange(
            front.address,
            format!("GET {target} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                .as_bytes(),
        )
        .await;
        assert_eq!(got, OK, "{target}");
    }
    assert_eq!(python.seen.lock().unwrap().len(), 4);
}

#[tokio::test(flavor = "multi_thread")]
async fn multipart_never_reaches_a_handler() {
    let python = stand_in(Script::Answer(OK)).await;
    let (front, _) = static_front("multipart", python.address).await;
    let got = exchange(
        front.address,
        b"GET / HTTP/1.1\r\nHost: localhost\r\nContent-Type: multipart/form-data\r\nConnection: close\r\n\r\n",
    )
    .await;
    assert_eq!(got, OK);
}

#[tokio::test(flavor = "multi_thread")]
async fn a_route_goes_back_to_python_within_two_seconds_with_no_restart() {
    let python = stand_in(Script::Answer(OK)).await;
    let (front, table) = static_front("rollback", python.address).await;
    let index = b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n";
    assert!(text(&exchange(front.address, index).await).ends_with("<index>"));

    std::fs::write(&table, STATIC_BACK).unwrap();
    let written = Instant::now();
    while exchange(front.address, index).await != OK {
        assert!(written.elapsed() < Duration::from_secs(2), "not yet at 2 s");
        tokio::time::sleep(Duration::from_millis(25)).await;
    }

    std::fs::write(&table, "{ half a file").unwrap();
    tokio::time::sleep(Duration::from_millis(1200)).await;
    assert_eq!(
        exchange(front.address, index).await,
        OK,
        "a bad file changes nothing"
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn a_bad_table_or_a_taken_port_refuses_to_start() {
    let dir = scratch("refuse");
    let table = dir.join("routes.json");
    std::fs::write(
        &table,
        r#"{"format":1,"routes":[{"id":"nope","method":"GET","path":"/x","owner":"rust"}]}"#,
    )
    .unwrap();
    let refused = |result: Result<Running, front::Refused>| match result {
        Ok(_) => panic!("it started"),
        Err(front::Refused(why)) => why,
    };
    let why = refused(
        front::start_with(
            config(&dir, nobody().await, Some(table)),
            Arc::new(NoRecord),
        )
        .await,
    );
    assert!(why.contains("nope"), "{why}");

    let taken = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    let mut settings = config(&dir, nobody().await, None);
    settings.port = taken.local_addr().unwrap().port();
    let why = refused(front::start_with(settings, Arc::new(NoRecord)).await);
    assert!(why.contains("cannot listen"), "{why}");
}
