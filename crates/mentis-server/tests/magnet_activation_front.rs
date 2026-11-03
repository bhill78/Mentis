//! A Magnet's manual activation through a real front (`docs/magnets/M1-contract.md`, "Manual activation"),
//! with a stand-in on Python's private port saying what each row of
//! `tests/fixtures/magnet-conformance/activation/` says. Python's own half isn't here: what it does with
//! what it is sent is the integrated package's to show.

#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};

use mentis_ops::magnet::MagnetDefinition;
use mentis_ops::pyjson::{self, Py, dict};
use mentis_record::{
    Brain, BrainOpener, Flow, ReadClass, ReadScope, RecordError, RecordReader, Value,
};
use mentis_server::front::activate::{
    self, ARTIFACT_MOST, Exchange, PageSays, Preflight, Ready, Said,
};
use mentis_server::front::{self, Config, Running};
use serde_json::Value as Json;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::Semaphore;

const SECRET: &str = "the-boot-secret";
const MAGNET: &str = "mag-a1c7e2f09b3d4e68";
const AUTHOR: &str = "ent-b20d8e47f196";
const OP: &str = "activate-0001";
const BODY: &str = r#"{"author": "ent-b20d8e47f196", "op": "activate-0001"}"#;

fn dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/magnet-conformance/activation")
}

fn fixture(name: &str) -> Json {
    serde_json::from_str(&std::fs::read_to_string(dir().join(name)).unwrap()).unwrap()
}

fn answer_rows() -> Vec<Json> {
    fixture("answers.json")["rows"].as_array().unwrap().clone()
}

/// `tests/test_magnet_activation_contract.py`'s `wire_of`.
fn wire_of(row: &Json, rows: &[Json]) -> Option<Vec<u8>> {
    if let Some(text) = row["wire_text"].as_str() {
        return Some(text.as_bytes().to_vec());
    }
    let (made, of) = if row["wire_pad"].is_object() {
        ("pad", &row["wire_pad"])
    } else if row["wire_cut"].is_object() {
        ("cut", &row["wire_cut"])
    } else {
        return None;
    };
    let source = rows
        .iter()
        .find(|r| r["phase"] == row["phase"] && r["id"] == of["of"])
        .unwrap();
    let text = source["wire_text"].as_str().unwrap().as_bytes();
    if made == "cut" {
        return Some(text[..of["keep"].as_u64().unwrap() as usize].to_vec());
    }
    let total = of["total"].as_u64().unwrap() as usize;
    let mut padded = text[..text.len() - 1].to_vec();
    padded.resize(total - 1, b' ');
    padded.push(b'}');
    Some(padded)
}

/// The exchange a row stands for, as `read_whole` would hand it over.
fn exchange_of(row: &Json, rows: &[Json]) -> Exchange {
    if row["event"].is_string() {
        return Exchange::Interrupted;
    }
    let body = wire_of(row, rows).unwrap();
    if body.len() as u64 > activate::PRIVATE_ANSWER_MOST {
        return Exchange::NoAnswer;
    }
    let status = row["http_status"].as_u64().unwrap_or(200) as u16;
    Exchange::Whole { status, body }
}

/// A refusal's bytes. Rust's name the raw segment it was asked about, and `refusals.json` has one Magnet.
fn refusal_about(refusal: &Json, row: &Json) -> String {
    let bytes = refusal["bytes"].as_str().unwrap();
    let asked = row["asked"].as_str().unwrap_or(MAGNET);
    if refusal["said_by"] == "python" {
        return bytes.to_owned();
    }
    bytes.replace(MAGNET, asked)
}

/// Holds the row's answer to what the row says it decides.
fn says_what_it_decides(said: &Said, row: &Json, rows: &[Json]) {
    let refusals = fixture("refusals.json");
    let id = row["id"].as_str().unwrap();
    let decides = row["decides"].as_str().unwrap();
    let (status, bytes) = (said.0, said.1.dumps());
    if let Some(refusal) = refusals.get(decides) {
        assert_eq!(status, refusal["status"], "{id}");
        assert_eq!(bytes, refusal_about(refusal, row), "{id}");
        return;
    }
    let wire = wire_of(row, rows).unwrap();
    let answer: Json = serde_json::from_slice(&wire).unwrap();
    assert_eq!(decides, answer["state"], "{id}");
    assert_eq!(status, answer["status"], "{id}");
    let read = pyjson::loads(std::str::from_utf8(&wire).unwrap()).unwrap();
    assert_eq!(bytes, read.get("body").unwrap().dumps(), "{id}");
}

fn held() -> Ready {
    let rows = answer_rows();
    let row = rows.iter().find(|r| r["id"] == "ready").unwrap();
    match activate::preflight_decides(MAGNET, &exchange_of(row, &rows)) {
        Preflight::Ready(ready) => *ready,
        Preflight::Says(said) => panic!("{}", said.1.dumps()),
    }
}

#[test]
fn every_private_answer_decides_what_its_row_says() {
    let rows = answer_rows();
    let mut counted = 0;
    for row in &rows {
        let id = row["id"].as_str().unwrap();
        let exchange = exchange_of(row, &rows);
        if row["phase"] == "preflight" {
            let asked = row["asked"].as_str().unwrap_or(MAGNET);
            match activate::preflight_decides(asked, &exchange) {
                Preflight::Ready(ready) => {
                    assert!(row["decides"].is_null(), "{id}");
                    assert_eq!(row["next"], "retrieve", "{id}");
                    assert_eq!((ready.author.as_str(), ready.op.as_str()), (AUTHOR, OP));
                }
                Preflight::Says(said) => {
                    assert_eq!(row["next"], "none", "{id}");
                    says_what_it_decides(&said, row, &rows);
                }
            }
        } else {
            let said = activate::commit_decides(MAGNET, &held(), &exchange);
            says_what_it_decides(&said, row, &rows);
        }
        counted += 1;
    }
    assert!(counted >= 100, "{counted} rows");
}

#[test]
fn every_refusal_rust_says_is_the_fixture_s_bytes() {
    let refusals = fixture("refusals.json");
    for (name, said) in [
        ("busy", activate::busy(MAGNET)),
        (
            "preflight-interrupted",
            activate::preflight_interrupted(MAGNET),
        ),
        ("sources-busy", activate::sources_busy(MAGNET)),
        ("no-readable-source", activate::no_readable_source(MAGNET)),
        ("artifact-too-large", activate::artifact_too_large(MAGNET)),
        (
            "internal-protocol-error",
            activate::internal_protocol_error(MAGNET),
        ),
        ("outcome-unknown", activate::outcome_unknown(MAGNET, OP)),
        (
            "public-body-too-large",
            (413, activate::public_body_too_large()),
        ),
    ] {
        assert_eq!(said.0, refusals[name]["status"], "{name}");
        assert_eq!(
            said.1.dumps(),
            refusals[name]["bytes"].as_str().unwrap(),
            "{name}"
        );
    }
}

#[test]
fn a_preflight_is_the_fixture_s_bytes() {
    let requests = fixture("private_requests.json");
    assert_eq!(
        activate::preflight_body(MAGNET, BODY.as_bytes()),
        requests["preflight"]["wire_text"].as_str().unwrap()
    );
    for row in requests["preflight_malformed_magnet"].as_array().unwrap() {
        let wire = row["wire_text"].as_str().unwrap();
        let sent: Json = serde_json::from_str(wire).unwrap();
        let body = if sent["public_body_base64"] == "ew==" {
            &b"{"[..]
        } else {
            BODY.as_bytes()
        };
        assert_eq!(
            activate::preflight_body(row["segment"].as_str().unwrap(), body),
            wire
        );
    }
}

/// The `ready` that would have led to this artifact, as Python would send it.
fn ready_for(artifact: &Py) -> Ready {
    let answer = dict([
        ("protocol", Py::int(1)),
        ("state", Py::str("ready")),
        ("magnet", artifact.get("magnet").unwrap().clone()),
        ("request", artifact.get("request").unwrap().clone()),
        ("definition", artifact.get("definition").unwrap().clone()),
    ]);
    let exchange = Exchange::Whole {
        status: 200,
        body: answer.dumps().into_bytes(),
    };
    let asked = artifact.get("magnet").unwrap().as_str().unwrap();
    match activate::preflight_decides(asked, &exchange) {
        Preflight::Ready(ready) => *ready,
        Preflight::Says(said) => panic!("{}", said.1.dumps()),
    }
}

#[test]
fn an_artifact_is_the_fixture_s_bytes_and_digest() {
    let all = fixture("artifacts.json");
    let mut seen = 0;
    for (name, info) in all["artifacts"].as_object().unwrap() {
        let bytes = std::fs::read(dir().join(info["file"].as_str().unwrap())).unwrap();
        let text = String::from_utf8(bytes).unwrap();
        let read = pyjson::loads(&text).unwrap();
        let ready = ready_for(&read);
        let asked = read.get("magnet").unwrap().as_str().unwrap();
        let page = read.get("page").unwrap().clone();
        let (made, sha256) = activate::materialized(asked, &ready, page).unwrap();
        assert_eq!(made, text, "{name}");
        assert_eq!(sha256, info["sha256"].as_str().unwrap(), "{name}");
        seen += 1;
    }
    assert!(seen >= 3);
}

#[test]
fn a_page_comes_to_what_the_useful_source_rule_says() {
    for row in fixture("useful_sources.json").as_array().unwrap() {
        let sources = row["sources"].as_array().unwrap().iter().map(|source| {
            let results = (0..source["results"].as_u64().unwrap())
                .map(|_| dict([("kind", Py::str("post"))]))
                .collect();
            dict([
                ("status", Py::str(source["status"].as_str().unwrap())),
                ("results", Py::List(results)),
            ])
        });
        let kept = (0..row["kept"].as_u64().unwrap())
            .map(|_| dict([("facet", Py::str("criteria"))]))
            .collect();
        let page = dict([
            ("sources", Py::List(sources.collect())),
            ("kept", Py::List(kept)),
        ]);
        let want = match row["decides"].as_str().unwrap() {
            "complete" => PageSays::Complete,
            "partial" => PageSays::Partial,
            "sources-busy" => PageSays::SourcesBusy,
            "no-readable-source" => PageSays::NoReadableSource,
            other => panic!("{other}"),
        };
        assert_eq!(activate::page_says(&page), want, "{}", row["id"]);
    }
}

fn one_result() -> Py {
    dict([(
        "sources",
        Py::List(vec![dict([
            ("status", Py::str("ok")),
            ("results", Py::List(vec![dict([("id", Py::str("ent-1"))])])),
        ])]),
    )])
}

#[test]
fn an_artifact_over_the_bound_is_the_413_and_at_it_is_not() {
    let ready = held();
    let (made, _) = activate::materialized(MAGNET, &ready, one_result()).unwrap();
    let fill = |extra: usize| {
        let mut page = one_result();
        page.set("fill", Py::Str("x".repeat(extra)));
        page
    };
    // What the fill adds besides itself: its name, and a string's quotes.
    let over = made.len() + ", \"fill\": \"\"".len();
    let at_most = activate::materialized(MAGNET, &ready, fill(ARTIFACT_MOST - over)).unwrap();
    assert_eq!(at_most.0.len(), ARTIFACT_MOST);
    let refused = activate::materialized(MAGNET, &ready, fill(ARTIFACT_MOST - over + 1));
    let (status, body) = refused.unwrap_err();
    assert_eq!(status, 413);
    assert_eq!(
        body.dumps(),
        fixture("refusals.json")["artifact-too-large"]["bytes"]
            .as_str()
            .unwrap()
    );
}

// ---- Through a real front -------------------------------------------------------------------------

/// What the stand-in does with what it heard.
#[derive(Clone)]
enum Says {
    /// Reads the body, answers 200 with these bytes, closes.
    Answer(Vec<u8>),
    /// Reads the body, then these whole bytes as an HTTP answer of this status.
    Status(u16, Vec<u8>),
    /// Answers from the head alone, half-closes, and reads on, as `_linger`.
    Early(Vec<u8>),
    /// Reads the body, promises the whole of `.1`, sends `.0` of it, closes.
    Truncated(usize, Vec<u8>),
    /// Reads the body and closes.
    Disconnect,
    /// Reads the body and resets.
    Reset,
    /// Never answers.
    Hang,
    /// Waits for a permit first.
    Gated(Arc<Semaphore>, Box<Says>),
    /// Forwarded: answers this whole, whatever it was.
    Whole(&'static [u8]),
}

#[derive(Clone, Debug)]
struct Heard {
    path: String,
    head: String,
    body: Vec<u8>,
}

impl Heard {
    fn is_commit(&self) -> bool {
        self.path.ends_with("/activate/commit")
    }

    fn is_preflight(&self) -> bool {
        self.path.ends_with("/activate/preflight")
    }

    fn says(&self, name: &str) -> Option<String> {
        self.head.lines().find_map(|line| {
            let (header, value) = line.split_once(": ")?;
            header
                .eq_ignore_ascii_case(name)
                .then(|| value.trim().to_owned())
        })
    }
}

type Script = Arc<Mutex<Box<dyn FnMut(&Heard) -> Says + Send>>>;

fn scripted(script: impl FnMut(&Heard) -> Says + Send + 'static) -> Script {
    Arc::new(Mutex::new(Box::new(script)))
}

struct Python {
    address: SocketAddr,
    heard: Arc<Mutex<Vec<Heard>>>,
    script: Script,
}

impl Python {
    fn heard(&self) -> Vec<Heard> {
        self.heard.lock().unwrap().clone()
    }

    fn commits(&self) -> Vec<Heard> {
        self.heard().into_iter().filter(Heard::is_commit).collect()
    }

    fn says(&self, script: impl FnMut(&Heard) -> Says + Send + 'static) {
        *self.script.lock().unwrap() = Box::new(script);
    }

    async fn until_it_has_heard(&self, count: usize) {
        let until = Instant::now() + Duration::from_secs(10);
        while self.heard().len() < count {
            assert!(Instant::now() < until, "heard only {:?}", self.heard());
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    }
}

fn whole(status: u16, body: &[u8]) -> Vec<u8> {
    let mut answer = format!(
        "HTTP/1.1 {status} Whatever\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n",
        body.len()
    )
    .into_bytes();
    answer.extend_from_slice(body);
    answer
}

fn declared(head: &str) -> usize {
    head.lines()
        .find_map(|line| {
            let (name, value) = line.split_once(':')?;
            name.eq_ignore_ascii_case("content-length")
                .then(|| value.trim().parse().ok())
                .flatten()
        })
        .unwrap_or(0)
}

async fn act(says: Says, stream: &mut TcpStream) {
    let mut says = says;
    if let Says::Gated(gate, then) = says {
        let permit = gate.acquire().await.unwrap();
        drop(permit);
        says = *then;
    }
    match says {
        Says::Answer(bytes) => {
            let _ = stream.write_all(&whole(200, &bytes)).await;
        }
        Says::Status(status, bytes) => {
            let _ = stream.write_all(&whole(status, &bytes)).await;
        }
        Says::Early(bytes) => {
            let _ = stream.write_all(&whole(200, &bytes)).await;
            let _ = stream.shutdown().await;
            let mut chunk = [0; 65536];
            while matches!(stream.read(&mut chunk).await, Ok(more) if more > 0) {}
        }
        Says::Truncated(keep, bytes) => {
            let answer = whole(200, &bytes);
            let cut = answer.len() - bytes.len() + keep;
            let _ = stream.write_all(&answer[..cut]).await;
        }
        Says::Disconnect => {}
        Says::Reset => {
            let _ = stream.set_linger(Some(Duration::ZERO));
        }
        Says::Hang => tokio::time::sleep(Duration::from_secs(30)).await,
        Says::Whole(bytes) => {
            let _ = stream.write_all(bytes).await;
        }
        Says::Gated(..) => unreachable!("one gate at a time"),
    }
}

async fn python(script: Script) -> Python {
    let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    let address = listener.local_addr().unwrap();
    let heard: Arc<Mutex<Vec<Heard>>> = Arc::default();
    let (heard_by_it, script_of_it) = (heard.clone(), script.clone());
    tokio::spawn(async move {
        loop {
            let Ok((mut stream, _)) = listener.accept().await else {
                return;
            };
            let (heard, script) = (heard_by_it.clone(), script_of_it.clone());
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
                // The mirror's own questions: nothing this test is about.
                if buffer.starts_with(b"GET /private/") {
                    let _ = stream
                        .write_all(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                        .await;
                    return;
                }
                let head: String = buffer[..end].iter().map(|&b| char::from(b)).collect();
                let path = head.split(' ').nth(1).unwrap_or("").to_owned();
                let mut heard_one = Heard {
                    path,
                    head,
                    body: buffer[end..].to_vec(),
                };
                let says = script.lock().unwrap()(&heard_one);
                if !matches!(says, Says::Early(_)) {
                    while heard_one.body.len() < declared(&heard_one.head) {
                        match stream.read(&mut chunk).await {
                            Ok(0) | Err(_) => break,
                            Ok(got) => heard_one.body.extend_from_slice(&chunk[..got]),
                        }
                    }
                }
                heard.lock().unwrap().push(heard_one);
                act(says, &mut stream).await;
            });
        }
    });
    Python {
        address,
        heard,
        script,
    }
}

struct NoRecord(RecordError);

impl RecordReader for NoRecord {
    fn read_scope(&self, _class: ReadClass) -> Result<Box<dyn ReadScope>, RecordError> {
        Err(self.0.clone())
    }

    fn corpus_id(&self) -> &str {
        ""
    }
}

fn no_record() -> Arc<dyn RecordReader> {
    Arc::new(NoRecord(RecordError::Sqlite {
        detail: "not in these tests".into(),
    }))
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("magnet-activate-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(dir.join("dist")).unwrap();
    dir
}

async fn front_on(
    brain: &Path,
    upstream: SocketAddr,
    table: Option<PathBuf>,
    record: Arc<dyn RecordReader>,
) -> SocketAddr {
    let config = Config {
        brain: brain.to_path_buf(),
        host: "127.0.0.1".into(),
        port: 0,
        upstream,
        dist: brain.join("dist"),
        route_table: table,
        secret: SECRET.into(),
        drain_limit: Duration::from_secs(5),
    };
    let running: Running = match front::start_with(config, record).await {
        Ok(running) => running,
        Err(front::Refused(why)) => panic!("{why}"),
    };
    let address = running.address;
    tokio::spawn(running.serve());
    address
}

/// A front on the table in the binary, with no record to read.
async fn bare_front(name: &str, upstream: SocketAddr) -> SocketAddr {
    front_on(&scratch(name), upstream, None, no_record()).await
}

fn world() -> &'static PathBuf {
    static WORLD: OnceLock<PathBuf> = OnceLock::new();
    WORLD.get_or_init(|| support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "activation"))
}

/// A Conversation in the world with posts, the one with the most.
fn a_conversation() -> String {
    const BIGGEST: &str = "SELECT l.link_to FROM entry l WHERE l.link_relation = 'in-conversation' \
         GROUP BY l.link_to ORDER BY COUNT(*) DESC LIMIT 1";
    let reader = Brain::open(world()).unwrap();
    let mut scope = reader.read_scope(ReadClass::Connector).unwrap();
    let mut found = None;
    scope
        .query(BIGGEST, &[], &mut |row| {
            if let Value::Text(text) = row.value(0)? {
                found = Some(String::from_utf8(text.to_vec()).unwrap());
            }
            Ok(Flow::Stop)
        })
        .unwrap();
    found.unwrap()
}

async fn world_front(upstream: SocketAddr) -> SocketAddr {
    let reader = Brain::open(world()).unwrap();
    front_on(world(), upstream, None, Arc::new(reader)).await
}

/// The exact text of a definition Python would approve, reading these sources.
fn definition_text(sources: &str) -> String {
    format!(
        "{{\n \"id\": \"{MAGNET}\", \"sources\": [{sources}], \"selection\": {{\"informationTypes\": [\"post\"]}},\n \
         \"collection\": {{\"mode\": \"one-time\"}}, \"synthesis\": {{\"mode\": \"manual\"}},\n \
         \"notifications\": {{\"newItems\": false, \"changes\": false, \"failures\": false}},\n \
         \"presentation\": {{\"renderer\": \"disc\"}}, \"activation\": {{\"mode\": \"manual\"}},\n \
         \"processing\": {{\"operations\": [{{\"op\": \"extract\", \"name\": \"th\u{e9} page\"}}]}},\n \
         \"schema_version\": 1\n}}"
    )
}

fn conversation_source(id: &str) -> String {
    format!(r#"{{"kind": "conversation", "conversation": "{id}"}}"#)
}

/// `ready` for that text. As Python sends it: not ASCII-escaped.
fn ready_wire(raw: &str) -> Vec<u8> {
    let mut value = pyjson::loads(raw).unwrap();
    if let Py::Dict(items) = &mut value {
        items.retain(|(key, _)| key != "schema_version");
    }
    let answer = dict([
        ("protocol", Py::int(1)),
        ("state", Py::str("ready")),
        ("magnet", Py::str(MAGNET)),
        (
            "request",
            dict([
                ("author", Py::str(AUTHOR)),
                ("op", Py::str(OP)),
                (
                    "identity",
                    dict([
                        ("route", Py::str(activate::IDENTITY_ROUTE)),
                        ("magnet", Py::str(MAGNET)),
                    ]),
                ),
            ]),
        ),
        (
            "definition",
            dict([
                ("sha256", Py::Str(activate::sha256_hex(raw.as_bytes()))),
                ("raw", Py::str(raw)),
                ("value", value),
            ]),
        ),
    ]);
    answer.dumps().into_bytes()
}

fn row_wire(id: &str, phase: &str) -> Vec<u8> {
    answer_rows()
        .iter()
        .find(|r| r["id"] == id && r["phase"] == phase)
        .and_then(|r| r["wire_text"].as_str().map(|t| t.as_bytes().to_vec()))
        .unwrap()
}

fn committed() -> Vec<u8> {
    row_wire("committed", "commit")
}

fn activation(path: &str, body: &str, extra: &str) -> Vec<u8> {
    format!(
        "POST {path} HTTP/1.1\r\nHost: localhost\r\nX-Mentis-Client: 1\r\nContent-Type: application/json\r\n\
         Content-Length: {}\r\nConnection: close\r\n{extra}\r\n{body}",
        body.len()
    )
    .into_bytes()
}

fn activating() -> Vec<u8> {
    activation(&format!("/fluid/api/magnets/{MAGNET}/activate"), BODY, "")
}

async fn exchange(address: SocketAddr, request: &[u8]) -> Vec<u8> {
    let mut stream = TcpStream::connect(address).await.unwrap();
    stream.write_all(request).await.unwrap();
    let mut got = Vec::new();
    let _ = stream.read_to_end(&mut got).await;
    got
}

fn status_of(answer: &[u8]) -> u16 {
    let text = String::from_utf8_lossy(answer);
    text.split(' ').nth(1).unwrap_or("0").parse().unwrap_or(0)
}

fn body_of(answer: &[u8]) -> String {
    let at = answer
        .windows(4)
        .position(|w| w == b"\r\n\r\n")
        .unwrap_or_else(|| panic!("{}", String::from_utf8_lossy(answer)));
    String::from_utf8_lossy(&answer[at + 4..]).into_owned()
}

fn refusal_bytes(name: &str) -> String {
    fixture("refusals.json")[name]["bytes"]
        .as_str()
        .unwrap()
        .to_owned()
}

fn door_body(row: &Json) -> Vec<u8> {
    if let Some(fill) = row["body_fill"].as_object() {
        let mut body = fill["text"].as_str().unwrap().as_bytes().to_vec();
        let byte = fill["byte"].as_str().unwrap().as_bytes()[0];
        body.resize(fill["total"].as_u64().unwrap() as usize, byte);
        return body;
    }
    row["body_text"].as_str().unwrap_or("").as_bytes().to_vec()
}

#[tokio::test(flavor = "multi_thread")]
async fn every_row_of_the_door_answers_in_its_bytes_and_only_what_should_reaches_preflight() {
    let answers = answer_rows();
    let author_missing = answers
        .iter()
        .find(|r| r["id"] == "refused-author-malformed-null-identity")
        .and_then(|r| r["wire_text"].as_str())
        .unwrap()
        .as_bytes()
        .to_vec();
    let busy = row_wire("refused-busy", "preflight");
    let empty_body = activate::preflight_body(MAGNET, b"");
    let stand_in = python(scripted(move |heard| {
        if heard.body == empty_body.as_bytes() {
            Says::Answer(author_missing.clone())
        } else {
            Says::Answer(busy.clone())
        }
    }))
    .await;
    let front = bare_front("door", stand_in.address).await;
    let door = fixture("door.json");
    let target = door["target"].as_str().unwrap();
    let rows = door["rows"].as_array().unwrap();
    assert!(rows.len() >= 66, "{}", rows.len());
    for row in rows {
        let id = row["id"].as_str().unwrap();
        let mut request = format!("POST {target} HTTP/1.1\r\n");
        let headers = row["headers"].as_array().unwrap();
        if !headers
            .iter()
            .any(|h| h[0].as_str().unwrap().trim().eq_ignore_ascii_case("host"))
        {
            request.push_str("Host: 127.0.0.1:8760\r\n");
        }
        for header in headers {
            request.push_str(&format!(
                "{}: {}\r\n",
                header[0].as_str().unwrap(),
                header[1].as_str().unwrap()
            ));
        }
        request.push_str("\r\n");
        let body = door_body(row);
        let mut wire: Vec<u8> = request
            .chars()
            .flat_map(|c| {
                let mut utf8 = [0; 4];
                c.encode_utf8(&mut utf8).as_bytes().to_vec()
            })
            .collect();
        wire.extend_from_slice(&body);

        let before = stand_in.heard().len();
        let answer = exchange(front, &wire).await;
        let heard = &stand_in.heard()[before..];
        let got = String::from_utf8_lossy(&answer).into_owned();
        if let Some(expect) = row["expect"].as_object() {
            let status_line = got.lines().next().unwrap_or("");
            assert_eq!(
                status_line,
                format!(
                    "HTTP/1.1 {} {}",
                    expect["status"],
                    expect["reason_phrase"].as_str().unwrap()
                ),
                "{id}"
            );
            assert!(
                got.contains(&format!(
                    "Content-Type: {}\r\n",
                    expect["content_type"].as_str().unwrap()
                )),
                "{id}: {got}"
            );
            assert_eq!(expect["closes"], true, "{id}");
            assert!(got.contains("Connection: close\r\n"), "{id}: {got}");
            assert_eq!(body_of(&answer), expect["body"].as_str().unwrap(), "{id}");
        }
        if row["reaches"] == "preflight" || row["stage"] == "body" {
            assert_eq!(heard.len(), 1, "{id}: {heard:?}");
            assert!(heard[0].is_preflight(), "{id}");
            assert_eq!(
                heard[0].path,
                format!("/private/magnets/{MAGNET}/activate/preflight")
            );
            assert_eq!(
                heard[0].says("X-Mentis-Boot-Secret").as_deref(),
                Some(SECRET)
            );
            let sent = String::from_utf8(heard[0].body.clone()).unwrap();
            assert_eq!(sent, activate::preflight_body(MAGNET, &body), "{id}");
        } else {
            assert!(heard.is_empty(), "{id}: {heard:?}");
        }
    }
    assert!(stand_in.commits().is_empty());
}

fn request_for(row: &Json) -> Vec<u8> {
    let asked = row["asked"].as_str().unwrap_or(MAGNET);
    activation(&format!("/fluid/api/magnets/{asked}/activate"), BODY, "")
}

fn says_for(row: &Json, rows: &[Json]) -> Says {
    match row["event"].as_str() {
        Some("timeout") => Says::Hang,
        Some("reset") => Says::Reset,
        Some("disconnect") => Says::Disconnect,
        Some("truncated") => {
            let of = &row["wire_cut"];
            let source = rows
                .iter()
                .find(|r| r["phase"] == row["phase"] && r["id"] == of["of"])
                .unwrap();
            Says::Truncated(
                of["keep"].as_u64().unwrap() as usize,
                source["wire_text"].as_str().unwrap().as_bytes().to_vec(),
            )
        }
        _ => {
            let status = row["http_status"].as_u64().unwrap_or(200) as u16;
            Says::Status(status, wire_of(row, rows).unwrap())
        }
    }
}

#[tokio::test(flavor = "multi_thread")]
async fn every_preflight_answer_on_the_wire_decides_what_its_row_says_and_reads_nothing_else() {
    let rows = answer_rows();
    let stand_in = python(scripted(|_| Says::Disconnect)).await;
    let front = bare_front("preflight-rows", stand_in.address).await;
    let refusals = fixture("refusals.json");
    for row in rows.iter().filter(|r| r["phase"] == "preflight") {
        let id = row["id"].as_str().unwrap();
        if row["event"] == "cannot-connect" {
            continue;
        }
        let says = says_for(row, &rows);
        stand_in.says(move |_| says.clone());
        let answer = exchange(front, &request_for(row)).await;
        match row["decides"].as_str() {
            // It went on to the read. This front has no record, so that comes to the 422.
            None => assert_eq!(
                body_of(&answer),
                refusal_bytes("no-readable-source"),
                "{id}"
            ),
            Some(decides) => {
                if let Some(refusal) = refusals.get(decides) {
                    assert_eq!(status_of(&answer), refusal["status"], "{id}");
                    assert_eq!(body_of(&answer), refusal_about(refusal, row), "{id}");
                } else {
                    let wire = wire_of(row, &rows).unwrap();
                    let read = pyjson::loads(std::str::from_utf8(&wire).unwrap()).unwrap();
                    assert_eq!(status_of(&answer), 200, "{id}");
                    assert_eq!(body_of(&answer), read.get("body").unwrap().dumps(), "{id}");
                }
            }
        }
        assert!(stand_in.commits().is_empty(), "{id}");
    }
}

#[tokio::test(flavor = "multi_thread")]
async fn no_connection_for_a_preflight_is_busy_and_nothing_follows() {
    let nobody = {
        let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        listener.local_addr().unwrap()
    };
    let front = bare_front("no-python", nobody).await;
    let answer = exchange(front, &activating()).await;
    assert_eq!(status_of(&answer), 503);
    assert_eq!(body_of(&answer), refusal_bytes("preflight-interrupted"));
}

#[tokio::test(flavor = "multi_thread")]
async fn a_read_that_fails_whole_writes_nothing_and_says_why() {
    let raw = definition_text(&conversation_source("ent-any"));
    let wire = ready_wire(&raw);
    let stand_in = python(scripted(move |_| Says::Answer(wire.clone()))).await;
    let full: Arc<dyn RecordReader> = Arc::new(NoRecord(RecordError::Busy {
        class: "background",
    }));
    let front = front_on(&scratch("class-full"), stand_in.address, None, full).await;
    let answer = exchange(front, &activating()).await;
    assert_eq!(status_of(&answer), 503);
    assert_eq!(body_of(&answer), refusal_bytes("sources-busy"));
    assert!(stand_in.commits().is_empty());

    let front = bare_front("no-record", stand_in.address).await;
    let answer = exchange(front, &activating()).await;
    assert_eq!(status_of(&answer), 422);
    assert_eq!(body_of(&answer), refusal_bytes("no-readable-source"));
    assert!(stand_in.commits().is_empty());
}

#[tokio::test(flavor = "multi_thread")]
async fn every_commit_answer_on_the_wire_decides_what_its_row_says() {
    let rows = answer_rows();
    let raw = definition_text(&conversation_source(&a_conversation()));
    let stand_in = python(scripted(|_| Says::Disconnect)).await;
    let front = world_front(stand_in.address).await;
    let refusals = fixture("refusals.json");
    let mut commits = 0;
    for row in rows.iter().filter(|r| r["phase"] == "commit") {
        let id = row["id"].as_str().unwrap();
        if row["event"] == "cannot-connect" {
            continue;
        }
        let ready = ready_wire(&raw);
        let says = says_for(row, &rows);
        stand_in.says(move |heard| {
            if heard.is_preflight() {
                Says::Answer(ready.clone())
            } else {
                says.clone()
            }
        });
        let started = Instant::now();
        let answer = exchange(front, &activating()).await;
        commits += 1;
        assert_eq!(stand_in.commits().len(), commits, "{id}");
        let decides = row["decides"].as_str().unwrap();
        if let Some(refusal) = refusals.get(decides) {
            assert_eq!(status_of(&answer), refusal["status"], "{id}");
            assert_eq!(body_of(&answer), refusal["bytes"].as_str().unwrap(), "{id}");
        } else {
            let source = if row["wire_pad"].is_object() {
                wire_of(row, &rows).unwrap()
            } else {
                row["wire_text"].as_str().unwrap().as_bytes().to_vec()
            };
            let read = pyjson::loads(std::str::from_utf8(&source).unwrap()).unwrap();
            let status = read.get("status").unwrap().dumps();
            assert_eq!(status_of(&answer).to_string(), status, "{id}");
            assert_eq!(body_of(&answer), read.get("body").unwrap().dumps(), "{id}");
        }
        if row["event"] == "timeout" {
            assert!(started.elapsed() < Duration::from_secs(8), "{id}");
        }
    }
    assert!(commits >= 40, "{commits}");
}

#[tokio::test(flavor = "multi_thread")]
async fn no_connection_for_a_commit_is_outcome_unknown() {
    // Answers the first preflight on a listener that then goes, so a commit has nowhere to go.
    let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    let address = listener.local_addr().unwrap();
    let raw = definition_text(&conversation_source(&a_conversation()));
    let ready = ready_wire(&raw);
    tokio::spawn(async move {
        loop {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut chunk = [0; 65536];
            let mut buffer = Vec::new();
            while !buffer.windows(4).any(|w| w == b"\r\n\r\n") {
                let got = stream.read(&mut chunk).await.unwrap_or(0);
                if got == 0 {
                    break;
                }
                buffer.extend_from_slice(&chunk[..got]);
            }
            if buffer.starts_with(b"POST") {
                let text = String::from_utf8_lossy(&buffer).into_owned();
                let end = text.find("\r\n\r\n").unwrap() + 4;
                let mut got = buffer.len() - end;
                while got < declared(&text) {
                    got += stream.read(&mut chunk).await.unwrap_or(1);
                }
                let _ = stream.write_all(&whole(200, &ready)).await;
                let _ = stream.shutdown().await;
                return;
            }
            let _ = stream
                .write_all(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                .await;
        }
    });
    let front = world_front(address).await;
    let answer = exchange(front, &activating()).await;
    assert_eq!(status_of(&answer), 503);
    assert_eq!(body_of(&answer), refusal_bytes("outcome-unknown"));
}

#[tokio::test(flavor = "multi_thread")]
async fn a_commit_sends_the_exact_artifact_and_a_read_of_the_same_page_says_the_same() {
    let conversation = a_conversation();
    let raw = definition_text(&conversation_source(&conversation));
    let (ready, done) = (ready_wire(&raw), committed());
    let stand_in = python(scripted(move |heard| {
        if heard.is_preflight() {
            Says::Answer(ready.clone())
        } else {
            Says::Answer(done.clone())
        }
    }))
    .await;
    let front = world_front(stand_in.address).await;
    let answer = exchange(front, &activating()).await;
    assert_eq!(
        status_of(&answer),
        201,
        "{}",
        String::from_utf8_lossy(&answer)
    );
    assert!(String::from_utf8_lossy(&answer).starts_with("HTTP/1.1 201 Created\r\n"));
    let row_body = pyjson::loads(std::str::from_utf8(&committed()).unwrap()).unwrap();
    assert_eq!(body_of(&answer), row_body.get("body").unwrap().dumps());

    let commits = stand_in.commits();
    let [commit] = &commits[..] else {
        panic!("{commits:?}")
    };
    assert_eq!(
        commit.path,
        format!("/private/magnets/{MAGNET}/activate/commit")
    );
    assert_eq!(commit.says("X-Mentis-Boot-Secret").as_deref(), Some(SECRET));
    assert_eq!(
        commit.says("Content-Type").as_deref(),
        Some("application/json")
    );
    assert_eq!(
        commit.says("X-Mentis-Artifact-SHA256"),
        Some(activate::sha256_hex(&commit.body))
    );
    assert_eq!(
        commit.says("Content-Length"),
        Some(commit.body.len().to_string())
    );
    let text = std::str::from_utf8(&commit.body).unwrap();
    assert!(text.is_ascii(), "json.dumps's default form");
    let artifact = pyjson::loads(text).unwrap();
    assert_eq!(artifact.dumps(), text, "one serialization");
    assert_eq!(
        artifact
            .get("definition")
            .unwrap()
            .get("raw")
            .unwrap()
            .as_str(),
        Some(raw.as_str())
    );
    let operation = artifact.get("operation").unwrap();
    assert_eq!(
        operation.get("name").unwrap().as_str(),
        Some("th\u{e9} page")
    );
    assert_eq!(operation.get("options").unwrap().dumps(), "{}");
    let page = artifact.get("page").unwrap();
    assert_eq!(activate::page_says(page), PageSays::Complete);
    assert!(MagnetDefinition::parse(MAGNET, &raw).is_ok());

    // The route that says it for anybody, on this same definition, from this same record: one read.
    let folder = world().join("presentation").join("magnets");
    std::fs::create_dir_all(&folder).unwrap();
    std::fs::write(folder.join(format!("{MAGNET}.json")), &raw).unwrap();
    let read = format!(
        "GET /fluid/api/magnets/{MAGNET}/read?mode=page HTTP/1.1\r\nHost: localhost\r\n\
         X-Mentis-Client: 1\r\nConnection: close\r\n\r\n"
    );
    let got = exchange(front, read.as_bytes()).await;
    std::fs::remove_file(folder.join(format!("{MAGNET}.json"))).unwrap();
    assert_eq!(status_of(&got), 200);
    assert_eq!(body_of(&got), page.dumps());
}

#[tokio::test(flavor = "multi_thread")]
async fn a_source_with_no_useful_result_commits_nothing() {
    let raw = definition_text(&conversation_source("ent-000000000000"));
    let wire = ready_wire(&raw);
    let stand_in = python(scripted(move |_| Says::Answer(wire.clone()))).await;
    let front = world_front(stand_in.address).await;
    let answer = exchange(front, &activating()).await;
    assert_eq!(status_of(&answer), 422);
    assert_eq!(body_of(&answer), refusal_bytes("no-readable-source"));
    assert!(stand_in.commits().is_empty());
}

#[tokio::test(flavor = "multi_thread")]
async fn a_whole_answer_before_the_whole_artifact_was_read_decides() {
    let raw = definition_text(&conversation_source(&a_conversation()));
    let ready = ready_wire(&raw);
    let early = row_wire("early-busy-null-identity", "commit");
    let stand_in = python(scripted(move |heard| {
        if heard.is_preflight() {
            Says::Answer(ready.clone())
        } else {
            Says::Early(early.clone())
        }
    }))
    .await;
    let front = world_front(stand_in.address).await;
    let answer = exchange(front, &activating()).await;
    assert_eq!(status_of(&answer), 503);
    assert_eq!(body_of(&answer), refusal_bytes("busy"));
}

#[tokio::test(flavor = "multi_thread")]
async fn one_place_not_queued_held_through_the_commit_s_answer_and_given_back() {
    let raw = definition_text(&conversation_source(&a_conversation()));
    let (ready, done) = (ready_wire(&raw), committed());
    let gate = Arc::new(Semaphore::new(0));
    let first_gate = gate.clone();
    let mut commits = 0;
    let stand_in = python(scripted(move |heard| {
        if heard.is_preflight() {
            return Says::Answer(ready.clone());
        }
        commits += 1;
        if commits == 1 {
            Says::Gated(first_gate.clone(), Box::new(Says::Answer(done.clone())))
        } else {
            Says::Answer(done.clone())
        }
    }))
    .await;
    let front = world_front(stand_in.address).await;

    let holding = tokio::spawn(async move { exchange(front, &activating()).await });
    // Its preflight and its commit: the place is taken and the commit hasn't been answered.
    stand_in.until_it_has_heard(2).await;
    assert!(!holding.is_finished());
    let started = Instant::now();
    let overlapping = exchange(front, &activating()).await;
    assert!(
        started.elapsed() < Duration::from_secs(1),
        "it doesn't wait"
    );
    assert_eq!(status_of(&overlapping), 503);
    assert_eq!(body_of(&overlapping), refusal_bytes("busy"));
    assert_eq!(
        stand_in.commits().len(),
        1,
        "it read nothing and sent nothing"
    );

    gate.add_permits(1);
    assert_eq!(status_of(&holding.await.unwrap()), 201);
    assert_eq!(
        status_of(&exchange(front, &activating()).await),
        201,
        "it went back"
    );
    assert_eq!(stand_in.commits().len(), 2);
}

#[tokio::test(flavor = "multi_thread")]
async fn two_preflights_may_both_be_done_and_their_commits_each_go_alone() {
    let raw = definition_text(&conversation_source(&a_conversation()));
    let (ready, done) = (ready_wire(&raw), committed());
    let replay = row_wire("replay", "commit");
    let gate = Arc::new(Semaphore::new(0));
    let second_gate = gate.clone();
    let (mut preflights, mut commits) = (0, 0);
    let stand_in = python(scripted(move |heard| {
        if heard.is_preflight() {
            preflights += 1;
            let says = Says::Answer(ready.clone());
            return if preflights == 1 {
                Says::Gated(second_gate.clone(), Box::new(says))
            } else {
                says
            };
        }
        commits += 1;
        Says::Answer(if commits == 1 {
            done.clone()
        } else {
            replay.clone()
        })
    }))
    .await;
    let front = world_front(stand_in.address).await;

    // The first has asked and hasn't been told. The second goes through it, whole.
    let waiting = tokio::spawn(async move { exchange(front, &activating()).await });
    stand_in.until_it_has_heard(1).await;
    let through = exchange(front, &activating()).await;
    assert_eq!(status_of(&through), 201);
    gate.add_permits(1);
    assert_eq!(status_of(&waiting.await.unwrap()), 200);
    assert_eq!(stand_in.commits().len(), 2);
}

#[tokio::test(flavor = "multi_thread")]
async fn a_replay_at_preflight_reads_nothing_and_commits_nothing() {
    let replay = row_wire("replay", "preflight");
    let stand_in = python(scripted(move |_| Says::Answer(replay.clone()))).await;
    let front = bare_front("replay", stand_in.address).await;
    let answer = exchange(front, &activating()).await;
    assert_eq!(status_of(&answer), 200);
    assert!(body_of(&answer).contains("\"replayed\": true"));
    assert_eq!(stand_in.heard().len(), 1);
}

#[tokio::test(flavor = "multi_thread")]
async fn a_client_gone_before_the_last_check_means_no_commit_and_the_place_goes_back() {
    let raw = definition_text(&conversation_source(&a_conversation()));
    let (ready, done) = (ready_wire(&raw), committed());
    let gate = Arc::new(Semaphore::new(0));
    let first_gate = gate.clone();
    let mut preflights = 0;
    let stand_in = python(scripted(move |heard| {
        if heard.is_commit() {
            return Says::Answer(done.clone());
        }
        preflights += 1;
        let says = Says::Answer(ready.clone());
        if preflights == 1 {
            Says::Gated(first_gate.clone(), Box::new(says))
        } else {
            says
        }
    }))
    .await;
    let front = world_front(stand_in.address).await;

    let mut leaving = TcpStream::connect(front).await.unwrap();
    leaving.write_all(&activating()).await.unwrap();
    stand_in.until_it_has_heard(1).await;
    drop(leaving);
    tokio::time::sleep(Duration::from_millis(100)).await;
    gate.add_permits(1);
    tokio::time::sleep(Duration::from_millis(500)).await;
    assert!(stand_in.commits().is_empty(), "{:?}", stand_in.heard());

    assert_eq!(status_of(&exchange(front, &activating()).await), 201);
    assert_eq!(stand_in.commits().len(), 1);
}

#[tokio::test(flavor = "multi_thread")]
async fn the_private_paths_on_the_public_port_are_decided_here_whatever_they_carry() {
    let stand_in = python(scripted(|_| {
        Says::Whole(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
    }))
    .await;
    let front = bare_front("shield", stand_in.address).await;
    let forged = format!(
        "{{\"format\": \"mentis.magnet-extract\", \"magnet\": \"{MAGNET}\", \"page\": {{}}}}"
    );
    let surface = fixture("door.json")["private"]["public_port"].clone();
    for target in surface["targets"].as_array().unwrap() {
        let target = target.as_str().unwrap();
        for secret in ["", &format!("X-Mentis-Boot-Secret: {SECRET}\r\n")] {
            let extra = format!(
                "{secret}X-Mentis-Artifact-SHA256: {}\r\n",
                activate::sha256_hex(forged.as_bytes())
            );
            let answer = exchange(front, &activation(target, &forged, &extra)).await;
            assert_eq!(status_of(&answer), surface["status"], "{target}");
            assert_eq!(
                body_of(&answer),
                surface["body"].as_str().unwrap(),
                "{target}"
            );
        }
    }
    assert!(stand_in.heard().is_empty(), "{:?}", stand_in.heard());
}

#[tokio::test(flavor = "multi_thread")]
async fn what_isn_t_the_exact_route_goes_to_python_whole_and_starts_nothing() {
    let stand_in = python(scripted(|_| {
        Says::Whole(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
    }))
    .await;
    let front = bare_front("odd", stand_in.address).await;
    for target in [
        format!("/fluid/api/magnets/{MAGNET}/activate/"),
        format!("/fluid/api/magnets/{MAGNET}#x/activate"),
        format!("/fluid/api/magnets/{MAGNET}/activate#x"),
        format!("/fluid/api/magnets/{MAGNET}/activate;x"),
        format!("//fluid/api/magnets/{MAGNET}/activate"),
    ] {
        let before = stand_in.heard().len();
        let answer = exchange(front, &activation(&target, BODY, "")).await;
        assert_eq!(status_of(&answer), 200, "{target}");
        stand_in.until_it_has_heard(before + 1).await;
        let heard = &stand_in.heard()[before];
        assert_eq!(heard.path, target);
        assert_eq!(heard.body, BODY.as_bytes(), "{target}");
    }
    let mut multipart = activating();
    let at = multipart
        .windows(16)
        .position(|w| w == b"application/json")
        .unwrap();
    multipart.splice(at..at + 16, b"multipart/mixed".iter().copied());
    let before = stand_in.heard().len();
    assert_eq!(status_of(&exchange(front, &multipart).await), 200);
    assert_eq!(
        stand_in.heard()[before].path,
        format!("/fluid/api/magnets/{MAGNET}/activate")
    );
    assert!(stand_in.commits().is_empty());
}

#[tokio::test(flavor = "multi_thread")]
async fn the_rule_rolled_back_sends_the_exact_path_to_python_byte_for_byte() {
    let stand_in = python(scripted(|_| {
        Says::Whole(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
    }))
    .await;
    let scratch = scratch("rollback");
    let table = scratch.join("routes.json");
    let rules = mentis_server::route_table::DEFAULT_TABLE.replace(
        r#""path": "/fluid/api/magnets/{}/activate", "owner": "rust""#,
        r#""path": "/fluid/api/magnets/{}/activate", "owner": "python""#,
    );
    assert_ne!(rules, mentis_server::route_table::DEFAULT_TABLE);
    std::fs::write(&table, rules).unwrap();
    let front = front_on(&scratch, stand_in.address, Some(table), no_record()).await;
    let target = format!("/fluid/api/magnets/{MAGNET}/activate");
    assert_eq!(status_of(&exchange(front, &activating()).await), 200);
    let heard = stand_in.heard();
    assert_eq!(heard.len(), 1);
    assert_eq!(heard[0].path, target);
    assert_eq!(heard[0].body, BODY.as_bytes());
}

#[tokio::test(flavor = "multi_thread")]
async fn a_forged_secret_on_the_public_request_goes_nowhere_and_the_real_one_goes_to_preflight() {
    let replay = row_wire("replay", "preflight");
    let stand_in = python(scripted(move |_| Says::Answer(replay.clone()))).await;
    let front = bare_front("forged", stand_in.address).await;
    let request = activation(
        &format!("/fluid/api/magnets/{MAGNET}/activate"),
        BODY,
        "X-Mentis-Boot-Secret: forged\r\nX-Mentis-Peer: 1.1.1.1\r\n",
    );
    assert_eq!(status_of(&exchange(front, &request).await), 200);
    let heard = stand_in.heard();
    assert_eq!(
        heard[0].says("X-Mentis-Boot-Secret").as_deref(),
        Some(SECRET)
    );
    assert!(!heard[0].head.contains("forged") && !heard[0].head.contains("1.1.1.1"));
}

#[tokio::test(flavor = "multi_thread")]
async fn expect_continue_is_answered_before_the_door_as_python_answers_it() {
    let replay = row_wire("replay", "preflight");
    let stand_in = python(scripted(move |_| Says::Answer(replay.clone()))).await;
    let front = bare_front("continue", stand_in.address).await;
    let request = activation(
        &format!("/fluid/api/magnets/{MAGNET}/activate"),
        BODY,
        "Expect: 100-continue\r\n",
    );
    let answer = exchange(front, &request).await;
    let text = String::from_utf8_lossy(&answer);
    assert!(
        text.starts_with("HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 200 OK\r\n"),
        "{text}"
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn a_success_stays_open_for_the_next_request_on_the_connection() {
    let replay = row_wire("replay", "preflight");
    let stand_in = python(scripted(move |_| Says::Answer(replay.clone()))).await;
    let front = bare_front("keep-alive", stand_in.address).await;
    let mut stream = TcpStream::connect(front).await.unwrap();
    let one = String::from_utf8(activating())
        .unwrap()
        .replace("Connection: close\r\n", "");
    let mut buffer = [0; 8192];
    for _ in 0..2 {
        stream.write_all(one.as_bytes()).await.unwrap();
        let got = stream.read(&mut buffer).await.unwrap();
        assert_eq!(status_of(&buffer[..got]), 200);
    }
    assert_eq!(stand_in.heard().len(), 2);
}
