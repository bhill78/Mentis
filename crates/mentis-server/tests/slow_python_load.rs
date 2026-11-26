//! A measurement, not a check: the front in front of a Python that does one thing at a time, under
//! twenty polling clients. Ignored by default; run it with
//! `cargo test -p mentis-server --test slow_python_load -- --ignored --nocapture`.
//! It prints one JSON line: Python's requests by path, how many of its answers nobody was waiting
//! for any more, and the clients' latencies. It uses only what the front has had since R4, so the
//! same file runs against an older front for a before-and-after.

use std::collections::BTreeMap;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use mentis_record::{ReadClass, ReadScope, RecordError, RecordReader};
use mentis_server::front::{self, Config, Running};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};

const SECRET: &str = "the-boot-secret";
const CLIENTS: usize = 20;
/// How many distinct views the clients poll between them; `MENTIS_LOAD_VIEWS` changes it.
fn views() -> usize {
    std::env::var("MENTIS_LOAD_VIEWS")
        .ok()
        .and_then(|views| views.parse().ok())
        .unwrap_or(5)
}
const HEAVY: Duration = Duration::from_secs(2);
const LIGHT: Duration = Duration::from_millis(20);
const RUN: Duration = Duration::from_secs(30);

struct NoRecord;

impl RecordReader for NoRecord {
    fn read_scope(&self, _class: ReadClass) -> Result<Box<dyn ReadScope>, RecordError> {
        Err(RecordError::Sqlite {
            detail: "not in this measurement".into(),
        })
    }

    fn corpus_id(&self) -> &str {
        ""
    }
}

#[derive(Default)]
struct Seen {
    by_path: BTreeMap<String, usize>,
    unwanted: usize,
}

/// Python, with its interpreter lock: any number of connections, one request worked on at a time.
async fn python() -> (SocketAddr, Arc<Mutex<Seen>>) {
    let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    let address = listener.local_addr().unwrap();
    let seen = Arc::new(Mutex::new(Seen::default()));
    let gil = Arc::new(tokio::sync::Mutex::new(()));
    let it = seen.clone();
    tokio::spawn(async move {
        let mut generation = 0u64;
        loop {
            let Ok((mut stream, _)) = listener.accept().await else {
                return;
            };
            let (seen, gil) = (it.clone(), gil.clone());
            generation += 1;
            tokio::spawn(async move {
                let mut got = Vec::new();
                let mut chunk = [0; 8192];
                loop {
                    let Some(end) = got.windows(4).position(|w| w == b"\r\n\r\n") else {
                        match stream.read(&mut chunk).await {
                            Ok(0) | Err(_) => return,
                            Ok(n) => got.extend_from_slice(&chunk[..n]),
                        }
                        continue;
                    };
                    let head = String::from_utf8_lossy(&got[..end]).into_owned();
                    got.drain(..end + 4);
                    let target = head.split(' ').nth(1).unwrap_or("").to_owned();
                    let path = target.split('?').next().unwrap_or("").to_owned();
                    let family = if path.starts_with("/api/turns/") {
                        "/api/turns/{}".to_owned()
                    } else {
                        path.clone()
                    };
                    *seen.lock().unwrap().by_path.entry(family).or_default() += 1;
                    let (status, body) = {
                        let _held = gil.lock().await;
                        if path == "/private/live" {
                            tokio::time::sleep(LIGHT).await;
                            (
                                200,
                                format!(
                                    r#"{{"schema":1,"boot_id":"b","generation":{generation},"live_hash":"h","taken_at":1.0,"fields":{{"live_now":[],"run_marks":[]}}}}"#
                                ),
                            )
                        } else if path.starts_with("/private/") {
                            tokio::time::sleep(LIGHT).await;
                            (404, "{}".to_owned())
                        } else {
                            tokio::time::sleep(HEAVY).await;
                            (200, format!(r#"{{"for": "{target}"}}"#))
                        }
                    };
                    // Whether whoever asked is still there to be answered.
                    let mut one = [0; 1];
                    if let Ok(Ok(0) | Err(_)) =
                        tokio::time::timeout(Duration::from_millis(1), stream.peek(&mut one)).await
                    {
                        seen.lock().unwrap().unwanted += 1;
                        return;
                    }
                    let answer = format!(
                        "HTTP/1.1 {status} X\r\nContent-Length: {}\r\n\r\n{body}",
                        body.len()
                    );
                    if stream.write_all(answer.as_bytes()).await.is_err() {
                        seen.lock().unwrap().unwanted += 1;
                        return;
                    }
                }
            });
        }
    });
    (address, seen)
}

async fn front(upstream: SocketAddr) -> SocketAddr {
    let scratch: PathBuf = std::env::temp_dir().join(format!("mentis-load-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&scratch);
    std::fs::create_dir_all(scratch.join("dist")).unwrap();
    std::fs::write(scratch.join("dist/index.html"), "<index>").unwrap();
    let config = Config {
        brain: scratch.clone(),
        host: "127.0.0.1".into(),
        port: 0,
        upstream,
        dist: scratch.join("dist"),
        route_table: None,
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

/// One request on its own connection: its status and how long it took, or `None` past 120 s.
async fn ask(front: SocketAddr, target: &str) -> Option<(u16, Duration)> {
    let began = Instant::now();
    let request = format!(
        "GET {target} HTTP/1.1\r\nHost: localhost\r\nX-Mentis-Client: 1\r\nConnection: close\r\n\r\n"
    );
    let asked = async {
        let mut stream = TcpStream::connect(front).await.ok()?;
        stream.write_all(request.as_bytes()).await.ok()?;
        let mut got = Vec::new();
        let _ = stream.read_to_end(&mut got).await;
        let line = String::from_utf8_lossy(&got).lines().next()?.to_owned();
        line.split(' ').nth(1)?.parse().ok()
    };
    let status = tokio::time::timeout(Duration::from_secs(120), asked)
        .await
        .ok()??;
    Some((status, began.elapsed()))
}

fn percentile(sorted: &[Duration], percent: usize) -> f64 {
    if sorted.is_empty() {
        return 0.0;
    }
    let at = (sorted.len() * percent).div_ceil(100).max(1) - 1;
    sorted[at].as_secs_f64() * 1000.0
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
#[ignore = "a measurement: about a minute"]
async fn twenty_clients_polling_through_a_slow_python() {
    let (upstream, seen) = python().await;
    let front = front(upstream).await;
    let until = Instant::now() + RUN;
    let results = Arc::new(Mutex::new(Vec::<(u16, Duration)>::new()));
    let mut tasks = Vec::new();
    for client in 0..CLIENTS {
        let results = results.clone();
        tasks.push(tokio::spawn(async move {
            let target = format!("/api/turns/t-{}", client % views());
            while Instant::now() < until {
                if let Some(result) = ask(front, &target).await {
                    results.lock().unwrap().push(result);
                }
                tokio::time::sleep(Duration::from_millis(500)).await;
            }
        }));
    }
    // A Fluid tab's pulse, which is what keeps the live snapshot polled.
    let pulses = tokio::spawn(async move {
        while Instant::now() < until {
            let _ = ask(front, "/api/pulse").await;
            tokio::time::sleep(Duration::from_secs(1)).await;
        }
    });
    for task in tasks {
        let _ = task.await;
    }
    let _ = pulses.await;
    // What Python still has in hand finishes.
    tokio::time::sleep(Duration::from_secs(3)).await;

    let results = results.lock().unwrap().clone();
    let mut statuses: BTreeMap<u16, usize> = BTreeMap::new();
    for (status, _) in &results {
        *statuses.entry(*status).or_default() += 1;
    }
    let mut took: Vec<Duration> = results.iter().map(|(_, took)| *took).collect();
    took.sort();
    let seen = seen.lock().unwrap();
    let report = serde_json::json!({
        "clients": CLIENTS,
        "distinct_views": views(),
        "python_ms_per_read": HEAVY.as_millis() as u64,
        "run_s": RUN.as_secs(),
        "client_requests": results.len(),
        "client_statuses": statuses,
        "client_p50_ms": percentile(&took, 50),
        "client_p95_ms": percentile(&took, 95),
        "python_requests": seen.by_path,
        "python_answers_nobody_wanted": seen.unwanted,
    });
    println!("LOAD {report}");
}
