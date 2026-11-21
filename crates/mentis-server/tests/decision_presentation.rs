#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::path::PathBuf;
use std::sync::OnceLock;

use mentis_record::{Brain, BrainOpener};
use mentis_server::worker_reads::{Read, read};
use serde_json::Value;

fn fixture() -> &'static Value {
    static FIXTURE: OnceLock<Value> = OnceLock::new();
    FIXTURE.get_or_init(|| {
        let root = PathBuf::from(env!("CARGO_TARGET_TMPDIR"))
            .join(format!("decision-front-{}", std::process::id()));
        assert!(!root.exists());
        let done = support::python()
            .arg(
                support::repo_root()
                    .join("crates/mentis-ops/tests/support/decision_presentation_side.py"),
            )
            .arg(root)
            .output()
            .unwrap();
        assert!(
            done.status.success(),
            "{}",
            String::from_utf8_lossy(&done.stderr)
        );
        serde_json::from_slice(&done.stdout).unwrap()
    })
}

#[test]
fn worker_form_and_turn_reads_preserve_question_identity_metadata_and_answers() {
    let mut native = 0;
    let mut forwarded = 0;
    for case in fixture()["scenarios"].as_array().unwrap() {
        let reader = Brain::open(std::path::Path::new(case["brain"].as_str().unwrap())).unwrap();
        for expected in case["worker_answers"].as_array().unwrap() {
            match read(
                "resolve",
                expected["args"].as_object().unwrap(),
                &reader,
                0.0,
            ) {
                Read::Body(bytes) => {
                    assert_eq!(case["native"], true, "an unclassified record must forward");
                    assert_eq!(
                        serde_json::from_slice::<Value>(&bytes).unwrap(),
                        expected["answer"],
                        "{} {}",
                        case["name"],
                        expected["args"]
                    );
                    native += 1;
                }
                Read::NotOwned => {
                    assert_eq!(
                        case["native"], false,
                        "unexpected forward {} {}",
                        case["name"], expected["args"]
                    );
                    forwarded += 1;
                }
            }
        }
    }
    assert!(
        native >= 12 && forwarded == 4,
        "{native} native, {forwarded} forwarded"
    );
    eprintln!("worker presentation seam: {native} native, {forwarded} forwarded");
}

#[tokio::test]
async fn grouped_list_and_inspection_keep_the_python_fallback() {
    use mentis_server::front::{self, Config};
    use std::sync::Arc;
    use std::time::Duration;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::{TcpListener, TcpStream};

    let root = PathBuf::from(fixture()["scenarios"][0]["brain"].as_str().unwrap());
    let reader = Brain::open(&root).unwrap();
    let upstream = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    let address = upstream.local_addr().unwrap();
    let upstream_task = tokio::spawn(async move {
        let mut requests = Vec::new();
        while requests.len() < 2 {
            let (mut stream, _) = upstream.accept().await.unwrap();
            let mut got = vec![];
            loop {
                let mut buf = [0u8; 8192];
                let n = stream.read(&mut buf).await.unwrap();
                if n == 0 {
                    break;
                }
                got.extend_from_slice(&buf[..n]);
                if got.windows(4).any(|w| w == b"\r\n\r\n") {
                    break;
                }
            }
            let text = String::from_utf8(got).unwrap();
            if !text.starts_with("GET /private/") {
                requests.push(text);
            }
            stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 17\r\nConnection: close\r\n\r\n{\"from\":\"python\"}").await.unwrap();
        }
        requests
    });
    let running = front::start_with(
        Config {
            brain: root.clone(),
            host: "127.0.0.1".into(),
            port: 0,
            upstream: address,
            dist: root.join("no-ui"),
            route_table: None,
            secret: "presentation-fixture".into(),
            drain_limit: Duration::from_secs(1),
        },
        Arc::new(reader),
    )
    .await
    .unwrap();
    let address = running.address;
    let server = tokio::spawn(running.serve());
    for path in [
        "/fluid/api/needs-you/items",
        "/fluid/api/needs-you/about?ids=opr-unknown",
    ] {
        let mut stream = TcpStream::connect(address).await.unwrap();
        stream
            .write_all(
                format!("GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                    .as_bytes(),
            )
            .await
            .unwrap();
        let mut answer = vec![];
        tokio::time::timeout(Duration::from_secs(10), stream.read_to_end(&mut answer))
            .await
            .unwrap()
            .unwrap();
        assert!(
            answer.ends_with(b"{\"from\":\"python\"}"),
            "{}",
            String::from_utf8_lossy(&answer)
        );
    }
    let requests = tokio::time::timeout(Duration::from_secs(10), upstream_task)
        .await
        .unwrap()
        .unwrap();
    assert!(requests[0].starts_with("GET /fluid/api/needs-you/items "));
    assert!(requests[1].starts_with("GET /fluid/api/needs-you/about?ids=opr-unknown "));
    server.abort();
    assert!(server.await.unwrap_err().is_cancelled());
}
