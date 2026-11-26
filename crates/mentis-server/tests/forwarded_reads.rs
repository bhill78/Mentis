//! Forwarded reads of the front's own routes, through the real front, with a slow stand-in where
//! Python goes: identical reads share one request, distinct ones go a few at a time, a write in hand
//! stops sharing, and a client leaving ends Python's request unless others still wait for it.
//! `contracts/route-table.md`, "Forwarded reads".

use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use mentis_record::{ReadClass, ReadScope, RecordError, RecordReader};
use mentis_server::front::flights::{MOST_FORWARDED_READS, RETRY_AFTER_S};
use mentis_server::front::{self, Config, Running};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};

const SECRET: &str = "the-boot-secret";

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

/// What Python saw of one request: its target, how it ended and when.
type Ended = (String, &'static str, Instant);

/// A Python that answers each `/api/` request `delay` after its head, one at a time per
/// connection, and counts them. Anything else (the mirror's location) is a quick 404.
#[derive(Clone)]
struct Slow {
    address: SocketAddr,
    asked: Arc<AtomicUsize>,
    now: Arc<AtomicUsize>,
    most: Arc<AtomicUsize>,
    /// How each `/api/` request ended: answered, or its connection ended first.
    ended: Arc<Mutex<Vec<Ended>>>,
}

async fn slow(delay: Duration) -> Slow {
    let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    let python = Slow {
        address: listener.local_addr().unwrap(),
        asked: Arc::default(),
        now: Arc::default(),
        most: Arc::default(),
        ended: Arc::default(),
    };
    let it = python.clone();
    tokio::spawn(async move {
        loop {
            let Ok((mut stream, _)) = listener.accept().await else {
                return;
            };
            let it = it.clone();
            tokio::spawn(async move {
                let mut got = Vec::new();
                let mut chunk = [0; 4096];
                let end = loop {
                    if let Some(end) = got.windows(4).position(|w| w == b"\r\n\r\n") {
                        break end;
                    }
                    match stream.read(&mut chunk).await {
                        Ok(0) | Err(_) => return,
                        Ok(n) => got.extend_from_slice(&chunk[..n]),
                    }
                };
                let head = String::from_utf8_lossy(&got[..end]).into_owned();
                let line = head.lines().next().unwrap_or("").to_owned();
                let target = line.split(' ').nth(1).unwrap_or("").to_owned();
                if !target.starts_with("/api/") {
                    let _ = stream
                        .write_all(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                        .await;
                    return;
                }
                it.asked.fetch_add(1, Ordering::SeqCst);
                let at_once = it.now.fetch_add(1, Ordering::SeqCst) + 1;
                it.most.fetch_max(at_once, Ordering::SeqCst);
                // Python can't hear a client go while it works; this stand-in can, to show when the
                // front let its request go.
                let mut one = [0; 1];
                let how = tokio::select! {
                    () = tokio::time::sleep(delay) => "answered",
                    read = stream.read(&mut one) => match read {
                        Ok(0) | Err(_) => "dropped",
                        Ok(_) => "answered",
                    },
                };
                it.now.fetch_sub(1, Ordering::SeqCst);
                it.ended
                    .lock()
                    .unwrap()
                    .push((target.clone(), how, Instant::now()));
                if how == "answered" {
                    let body = format!("{{\"for\": \"{target}\"}}");
                    let answer = format!(
                        "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
                        body.len()
                    );
                    let _ = stream.write_all(answer.as_bytes()).await;
                }
            });
        }
    });
    python
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("mentis-flights-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(dir.join("dist/assets")).unwrap();
    std::fs::write(dir.join("dist/index.html"), "<index>").unwrap();
    dir
}

/// A front on the table in the binary, which owns `/api/turns/{}`. With no live snapshot held, that
/// route can't answer for itself, so every such read forwards: as when Python is slow.
async fn front(name: &str, upstream: SocketAddr, routes: Option<&str>) -> SocketAddr {
    let scratch = scratch(name);
    let route_table = routes.map(|routes| {
        let file = scratch.join("routes.json");
        std::fs::write(&file, routes).unwrap();
        file
    });
    let config = Config {
        brain: scratch.clone(),
        host: "127.0.0.1".into(),
        port: 0,
        upstream,
        dist: scratch.join("dist"),
        route_table,
        secret: SECRET.into(),
        drain_limit: Duration::from_secs(5),
    };
    let running: Running = match front::start_with(config, Arc::new(NoRecord)).await {
        Ok(running) => running,
        Err(front::Refused(why)) => panic!("{why}"),
    };
    let address = running.address;
    tokio::spawn(running.serve());
    address
}

fn read_of(target: &str) -> String {
    format!(
        "GET {target} HTTP/1.1\r\nHost: localhost\r\nX-Mentis-Client: 1\r\nConnection: close\r\n\r\n"
    )
}

async fn exchange(address: SocketAddr, request: String) -> String {
    let mut stream = TcpStream::connect(address).await.unwrap();
    stream.write_all(request.as_bytes()).await.unwrap();
    let mut got = Vec::new();
    let _ = stream.read_to_end(&mut got).await;
    String::from_utf8_lossy(&got).into_owned()
}

#[tokio::test(flavor = "multi_thread")]
async fn identical_reads_in_flight_share_one_request_to_python() {
    let python = slow(Duration::from_millis(500)).await;
    let front = front("same", python.address, None).await;
    let asks = (0..20).map(|_| tokio::spawn(exchange(front, read_of("/api/turns/t-1"))));
    for answer in futures_join(asks).await {
        assert!(answer.starts_with("HTTP/1.1 200 OK\r\n"), "{answer}");
        assert!(answer.ends_with(r#"{"for": "/api/turns/t-1"}"#), "{answer}");
    }
    assert_eq!(python.asked.load(Ordering::SeqCst), 1);
}

#[tokio::test(flavor = "multi_thread")]
async fn distinct_reads_go_to_python_a_few_at_a_time() {
    let python = slow(Duration::from_millis(300)).await;
    let front = front("distinct", python.address, None).await;
    let asks =
        (0..16).map(|at| tokio::spawn(exchange(front, read_of(&format!("/api/turns/t-{at}")))));
    for answer in futures_join(asks).await {
        assert!(answer.starts_with("HTTP/1.1 200 OK\r\n"), "{answer}");
    }
    assert_eq!(python.asked.load(Ordering::SeqCst), 16);
    assert_eq!(python.most.load(Ordering::SeqCst), MOST_FORWARDED_READS);
}

#[tokio::test(flavor = "multi_thread")]
async fn a_read_with_no_place_in_time_is_told_mentis_is_busy_and_nothing_is_sent() {
    let python = slow(Duration::from_millis(2000)).await;
    let front = front("busy", python.address, None).await;
    let asks =
        (0..12).map(|at| tokio::spawn(exchange(front, read_of(&format!("/api/turns/b-{at}")))));
    let answers = futures_join(asks).await;
    let busy: Vec<_> = answers
        .iter()
        .filter(|answer| answer.starts_with("HTTP/1.1 503 "))
        .collect();
    assert_eq!(busy.len(), 4, "{answers:?}");
    for answer in &busy {
        assert!(
            answer.contains(&format!("Retry-After: {RETRY_AFTER_S}\r\n")),
            "{answer}"
        );
        assert!(answer.contains(r#""kind": "Busy""#), "{answer}");
    }
    assert_eq!(python.asked.load(Ordering::SeqCst), 8);
}

#[tokio::test(flavor = "multi_thread")]
async fn a_read_after_a_write_was_in_hand_is_not_given_an_answer_asked_for_before_it() {
    let python = slow(Duration::from_millis(600)).await;
    let front = front("write", python.address, None).await;
    let first = tokio::spawn(exchange(front, read_of("/api/turns/w")));
    tokio::time::sleep(Duration::from_millis(100)).await;
    let post = "POST /api/something HTTP/1.1\r\nHost: localhost\r\nX-Mentis-Client: 1\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
    let write = tokio::spawn(exchange(front, post.to_owned()));
    tokio::time::sleep(Duration::from_millis(100)).await;
    // The write is in hand: this read goes on its own.
    let during = tokio::spawn(exchange(front, read_of("/api/turns/w")));
    let written = write.await.unwrap();
    assert!(written.starts_with("HTTP/1.1 200 "), "{written}");
    // The write has been answered: this read doesn't join one sent before it.
    let after = exchange(front, read_of("/api/turns/w")).await;
    for answer in [first.await.unwrap(), during.await.unwrap(), after] {
        assert!(answer.starts_with("HTTP/1.1 200 "), "{answer}");
    }
    // Three reads and the write, each its own request.
    assert_eq!(python.asked.load(Ordering::SeqCst), 4);
}

async fn leave_after(front: SocketAddr, request: String, after: Duration) {
    let mut stream = TcpStream::connect(front).await.unwrap();
    stream.write_all(request.as_bytes()).await.unwrap();
    tokio::time::sleep(after).await;
    drop(stream);
}

fn dropped(python: &Slow) -> Vec<Instant> {
    python
        .ended
        .lock()
        .unwrap()
        .iter()
        .filter(|(_, how, _)| *how == "dropped")
        .map(|(_, _, at)| *at)
        .collect()
}

#[tokio::test(flavor = "multi_thread")]
async fn a_client_leaving_a_plain_forward_ends_its_request_to_python_at_once() {
    let python = slow(Duration::from_secs(5)).await;
    // A table that owns nothing: a plain forward.
    let front = front(
        "plain-leave",
        python.address,
        Some(r#"{"format":1,"routes":[]}"#),
    )
    .await;
    let left = Instant::now() + Duration::from_millis(200);
    leave_after(front, read_of("/api/x"), Duration::from_millis(200)).await;
    tokio::time::sleep(Duration::from_millis(500)).await;
    let dropped = dropped(&python);
    assert_eq!(dropped.len(), 1, "Python's request wasn't let go");
    assert!(dropped[0].saturating_duration_since(left) < Duration::from_millis(300));
}

#[tokio::test(flavor = "multi_thread")]
async fn one_client_leaving_a_shared_read_leaves_it_to_the_others_and_the_last_ends_it() {
    let python = slow(Duration::from_millis(1200)).await;
    let front = front("shared-leave", python.address, None).await;
    let staying = tokio::spawn(exchange(front, read_of("/api/turns/s")));
    tokio::time::sleep(Duration::from_millis(100)).await;
    leave_after(front, read_of("/api/turns/s"), Duration::from_millis(200)).await;
    let answer = staying.await.unwrap();
    assert!(answer.ends_with(r#"{"for": "/api/turns/s"}"#), "{answer}");
    assert_eq!(python.asked.load(Ordering::SeqCst), 1);
    assert!(dropped(&python).is_empty());

    // Every one gone: the request to Python goes too.
    let left = Instant::now() + Duration::from_millis(200);
    let a = tokio::spawn(leave_after(
        front,
        read_of("/api/turns/g"),
        Duration::from_millis(200),
    ));
    let b = tokio::spawn(leave_after(
        front,
        read_of("/api/turns/g"),
        Duration::from_millis(200),
    ));
    let _ = (a.await, b.await);
    tokio::time::sleep(Duration::from_millis(500)).await;
    assert_eq!(python.asked.load(Ordering::SeqCst), 2);
    let dropped = dropped(&python);
    assert_eq!(dropped.len(), 1);
    assert!(dropped[0].saturating_duration_since(left) < Duration::from_millis(300));
}

async fn futures_join<T: Send + 'static>(
    tasks: impl Iterator<Item = tokio::task::JoinHandle<T>>,
) -> Vec<T> {
    let mut out = Vec::new();
    for task in tasks.collect::<Vec<_>>() {
        out.push(task.await.unwrap());
    }
    out
}
