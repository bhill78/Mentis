//! `magnet_read`: its budget, a source failing alone, its cursor, a summary that walks nothing, and
//! what saturating it does to everyone else. Fixtures as `window.rs`'s. No speed is asserted: a run says
//! what it saw, and only that nobody else was starved fails.

#[path = "../../mentis-rules/tests/support/mod.rs"]
mod support;

use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, MutexGuard, OnceLock};
use std::time::{Duration, Instant};

use mentis_extract::Bundle;
use mentis_ops::history::{History, HistoryArgs};
use mentis_ops::magnet::{
    JOINS, JOINS_MOST, LINKS_MOST, MagnetArgs, MagnetDefinition, MagnetMode, MagnetPlan,
    MagnetRead, MagnetSource, NEWEST, NEWEST_ROWS, NotADefinition, PARTICIPANTS_MOST, SUMMARY_ONE,
    UNCACHED_MOST,
};
use mentis_ops::pyjson::Py;
use mentis_ops::window::collections::{ConversationArgs, ConversationCollection};
use mentis_ops::window::objects::{Objects, ObjectsArgs, ObjectsAsk};
use mentis_ops::window::{Prepared, Window};
use mentis_ops::{Cursor, OpError, ReadClass, ReadOp, ReadRequest};
use mentis_record::{
    Brain, BrainOpener, Flow, Param, Position, ReadScope, Reader, RecordError, RecordReader, Row,
    Value,
};

fn world() -> &'static PathBuf {
    static WORLD: OnceLock<PathBuf> = OnceLock::new();
    WORLD.get_or_init(|| match std::env::var("MENTIS_RULES_BRAIN") {
        Ok(brain) => PathBuf::from(brain),
        Err(_) => support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "magnet"),
    })
}

/// Extraction's places are the process's, as they are in a front, so what counts them runs alone.
fn alone() -> MutexGuard<'static, ()> {
    static ONE: Mutex<()> = Mutex::new(());
    ONE.lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
}

fn reader() -> Reader {
    Brain::open(world()).unwrap()
}

fn column(reader: &dyn RecordReader, sql: &'static str) -> Vec<String> {
    let mut scope = reader.read_scope(ReadClass::Connector).unwrap();
    let mut out = Vec::new();
    scope
        .query(sql, &[], &mut |row| {
            if let Value::Text(text) = row.value(0)? {
                out.push(String::from_utf8(text.to_vec()).unwrap());
            }
            Ok(Flow::Continue)
        })
        .unwrap();
    out
}

/// Conversations, those with the most posts first.
const BIGGEST: &str = "SELECT l.link_to FROM entry l WHERE l.link_relation = 'in-conversation' \
     GROUP BY l.link_to ORDER BY COUNT(*) DESC";

fn conversations(reader: &dyn RecordReader) -> Vec<String> {
    column(reader, BIGGEST)
}

fn definition(sources: &[String]) -> MagnetDefinition {
    let listed: Vec<String> = sources
        .iter()
        .map(|s| {
            if s.starts_with('{') {
                s.clone()
            } else {
                format!(r#"{{"kind":"conversation","conversation":"{s}"}}"#)
            }
        })
        .collect();
    let text = format!(
        r#"{{"id":"mag-t","sources":[{}],"selection":{{}}}}"#,
        listed.join(",")
    );
    MagnetDefinition::parse("mag-t", &text).unwrap()
}

/// A bundle no extraction has been kept for, whose extraction takes `spin` iterations, with an object
/// for each post, so a page is cold every time it's asked with a new `salt`.
fn cold_bundle(salt: usize, spin: u32) -> Bundle {
    Bundle::of_source(
        &format!("cold-{salt}.js"),
        &format!(
            "var MentisRenderCheck = {{extractPost: function () {{ \
             var n = 0; for (var i = 0; i < {spin}; i++) n += i; \
             return {{objects: [{{key: 'k', type: 'file', kind: 'block', \
               is: {{family: 'file', word: 'file'}}, title: 'f', \
               address: {{live: 'live:x:k', exact: 'exact:x:-:k'}}}}]}} }}}}; /* {salt} */"
        ),
    )
}

fn asked(
    magnet: MagnetDefinition,
    mode: MagnetMode,
    bundle: Result<Bundle, String>,
    cursor: Option<String>,
    limit: Option<u32>,
    within: Duration,
) -> ReadRequest<MagnetArgs> {
    ReadRequest {
        args: MagnetArgs {
            magnet,
            mode,
            bundle,
            gone: Arc::default(),
        },
        cursor: cursor.map(Cursor),
        limit,
        deadline: Instant::now() + within,
    }
}

fn page(types: &[&str], source: Option<&str>) -> MagnetMode {
    MagnetMode::Page {
        source: source.map(str::to_owned),
        types: Some(types.iter().map(|t| (*t).to_owned()).collect()),
    }
}

const NO_BUNDLE: fn() -> Result<Bundle, String> = || Err("no bundle in this test".to_owned());
const WITHIN: Duration = Duration::from_secs(5);

fn finished(plan: MagnetPlan, window: &Window) -> Py {
    plan.finish(window, &|| false)
}

fn read(
    window: &Window,
    reader: &dyn RecordReader,
    request: &ReadRequest<MagnetArgs>,
) -> Result<Py, OpError> {
    let op = MagnetRead { window };
    let mut got = mentis_ops::run(&op, reader, ReadClass::Background, request)?;
    let Prepared(plan) = got.rows.pop().unwrap();
    Ok(finished(plan, window))
}

fn sources_of(answer: &Py) -> Vec<Py> {
    answer.get("sources").unwrap().as_list().unwrap().to_vec()
}

fn status(source: &Py) -> &str {
    source.get("status").and_then(Py::as_str).unwrap()
}

fn results(source: &Py) -> Vec<Py> {
    source.get("results").unwrap().as_list().unwrap().to_vec()
}

/// What each statement was, for after the op has given the scope back.
struct Watched<'a> {
    inner: Box<dyn ReadScope>,
    seen: &'a mut Vec<&'static str>,
}

impl ReadScope for Watched<'_> {
    fn position(&self) -> Position {
        self.inner.position()
    }

    fn query(
        &mut self,
        sql: &'static str,
        params: &[Param<'_>],
        each: &mut dyn FnMut(&dyn Row) -> Result<Flow, RecordError>,
    ) -> Result<(), RecordError> {
        self.seen.push(sql);
        self.inner.query(sql, params, each)
    }

    fn statements(&self) -> u32 {
        self.inner.statements()
    }
}

fn statements_of(
    window: &Window,
    reader: &dyn RecordReader,
    request: &ReadRequest<MagnetArgs>,
) -> Vec<&'static str> {
    let mut seen = Vec::new();
    let inner = reader.read_scope(ReadClass::Background).unwrap();
    let mut scope = Watched {
        inner,
        seen: &mut seen,
    };
    MagnetRead { window }
        .read(&mut scope, request)
        .ok()
        .unwrap();
    seen
}

#[test]
fn a_summary_walks_nothing_and_its_cost_does_not_grow_with_a_conversation() {
    let reader = reader();
    let window = Window::new(world(), "no-dist".as_ref());
    let ids = conversations(&reader);
    assert!(ids.len() >= 2, "{ids:?}");
    let largest = definition(&ids[..1]);
    let smallest = definition(&ids[ids.len() - 1..]);
    let ask = |d: MagnetDefinition| asked(d, MagnetMode::Summary, NO_BUNDLE(), None, None, WITHIN);
    let big = statements_of(&window, &reader, &ask(largest.clone()));
    let small = statements_of(&window, &reader, &ask(smallest));
    // What varies is how many versions a Conversation's own name has, never how many posts it holds.
    for spent in [&big, &small] {
        assert!(spent.len() as u32 <= SUMMARY_ONE, "{spent:#?}");
        for sql in spent.iter() {
            // Not the closures, not what runs returned, not a page and not a post's number.
            for walks in ["t(root", "operational", "ROW_NUMBER", "json_extract(value"] {
                assert!(!sql.contains(walks), "a summary read {walks}: {sql}");
            }
        }
    }
    let answer = read(&window, &reader, &ask(largest)).unwrap();
    let got = &sources_of(&answer)[0];
    assert_eq!(status(got), "ok");
    let summary = got.get("summary").unwrap();
    assert!(summary.get("title").and_then(Py::as_str).is_some());
    assert!(summary.get("activity").unwrap().truthy());
    assert!(results(got).is_empty(), "a summary lists nothing");
    // The bigger conversation has a post count that isn't its first page's.
    assert_eq!(summary.get("posts").unwrap().dumps(), {
        let c = ConversationCollection;
        let request = ReadRequest {
            args: ConversationArgs {
                id: ids[0].clone(),
                shape: Some("posts".into()),
                ..ConversationArgs::default()
            },
            cursor: None,
            limit: Some(1),
            deadline: Instant::now() + WITHIN,
        };
        let mut page = mentis_ops::run(&c, &reader, ReadClass::Foreground, &request).unwrap();
        let row = page.rows.pop().unwrap();
        serde_json::to_value(&row)
            .ok()
            .and_then(|v| v.get("total").map(ToString::to_string))
            .unwrap_or_else(|| row.0.get("total").unwrap().dumps())
    });
}

#[test]
fn twenty_sources_stay_within_the_budget_and_a_summary_costs_each_the_same() {
    let reader = reader();
    let window = Window::new(world(), "no-dist".as_ref());
    let ids = conversations(&reader);
    // Twenty different sources: every conversation there is, and then ones that aren't.
    let different: Vec<String> = ids
        .iter()
        .cloned()
        .chain((0..20).map(|i| format!("ent-00000000{i:04}")))
        .take(20)
        .collect();
    // Twenty that all hold posts, which a seed can't say with so few conversations, as a source is
    // named once: the costs are the conversation's, so these are told apart by key here.
    let mut holding = definition(&ids[..1]);
    holding.sources = ids
        .iter()
        .cycle()
        .take(20)
        .enumerate()
        .map(|(i, id)| MagnetSource {
            key: format!("conversation:{id}#{i}"),
            conversation: Some(id.clone()),
            ..holding.sources[0].clone()
        })
        .collect();
    for d in [definition(&different), holding] {
        let summary = asked(
            d.clone(),
            MagnetMode::Summary,
            NO_BUNDLE(),
            None,
            None,
            WITHIN,
        );
        let spent = statements_of(&window, &reader, &summary);
        assert!(
            spent.len() as u32 <= MagnetRead::BUDGET.statements,
            "{}",
            spent.len()
        );
        let pages = asked(
            d,
            page(&["post", "file"], None),
            Ok(cold_bundle(0, 1)),
            None,
            None,
            WITHIN,
        );
        let spent = statements_of(&window, &reader, &pages);
        assert!(
            spent.len() as u32 <= MagnetRead::BUDGET.statements,
            "{}",
            spent.len()
        );
    }
}

#[test]
fn objects_are_read_only_for_the_types_asked() {
    let reader = reader();
    let window = Window::new(world(), "no-dist".as_ref());
    let ids = conversations(&reader);
    let posts_only = asked(
        definition(&ids[..1]),
        page(&["post"], None),
        Err("no objects were asked for".to_owned()),
        None,
        None,
        WITHIN,
    );
    let sql = statements_of(&window, &reader, &posts_only);
    assert!(!sql.iter().any(|s| s.contains("t(root")), "{sql:#?}");
    let answer = read(&window, &reader, &posts_only).unwrap();
    let got = &sources_of(&answer)[0];
    assert_eq!(status(got), "ok", "{}", answer.dumps());
    let first = &results(got)[0];
    for key in ["id", "version", "conversation", "author", "at"] {
        assert!(first.get(key).is_some(), "{key} in {}", first.dumps());
    }
    assert_eq!(
        first.get("conversation").and_then(Py::as_str),
        Some(ids[0].as_str())
    );
}

#[test]
fn the_cursor_walks_one_source_with_no_post_twice_and_is_that_source_s_alone() {
    let reader = reader();
    let window = Window::new(world(), "no-dist".as_ref());
    let ids = conversations(&reader);
    let key = format!("conversation:{}", ids[0]);
    let d = definition(&ids[..1]);
    let mut seen = HashSet::new();
    let mut cursor: Option<String> = None;
    let mut pages = 0;
    loop {
        let request = asked(
            d.clone(),
            page(&["post"], Some(&key)),
            NO_BUNDLE(),
            cursor.clone(),
            Some(1),
            WITHIN,
        );
        let answer = read(&window, &reader, &request).unwrap();
        let got = &sources_of(&answer)[0];
        assert_eq!(status(got), "ok");
        let rows = results(got);
        assert!(rows.len() <= 1, "a page is bounded");
        for row in &rows {
            assert!(
                seen.insert(row.get("id").unwrap().dumps()),
                "twice: {}",
                row.dumps()
            );
        }
        pages += 1;
        match got.get("next").and_then(Py::as_str) {
            Some(next) => cursor = Some(next.to_owned()),
            None => break,
        }
        assert!(pages < 500, "a cursor that never ends");
    }
    assert!(pages > 1, "the fixture has more than one page: {pages}");
    let wrong = asked(
        d.clone(),
        page(&["post"], None),
        NO_BUNDLE(),
        Some("x".into()),
        None,
        WITHIN,
    );
    assert!(matches!(
        read(&window, &reader, &wrong),
        Err(OpError::BadRequest { .. })
    ));
    let odd = asked(
        d.clone(),
        page(&["post"], Some(&key)),
        NO_BUNDLE(),
        Some("x".into()),
        None,
        WITHIN,
    );
    assert!(matches!(
        read(&window, &reader, &odd),
        Err(OpError::BadRequest { .. })
    ));
    let other = asked(
        d,
        page(&["post"], Some("web::x")),
        NO_BUNDLE(),
        None,
        None,
        WITHIN,
    );
    assert!(matches!(
        read(&window, &reader, &other),
        Err(OpError::BadRequest { .. })
    ));
}

#[test]
fn dates_apply_to_a_source_and_are_said_on_it() {
    let reader = reader();
    let window = Window::new(world(), "no-dist".as_ref());
    let ids = conversations(&reader);
    let dated = |dates: &str| {
        let text = format!(
            r#"{{"id":"mag-t","sources":[{{"kind":"conversation","conversation":"{}"}}],"selection":{{"dates":{dates}}}}}"#,
            ids[0]
        );
        let d = MagnetDefinition::parse("mag-t", &text).unwrap();
        let request = asked(d, page(&["post"], None), NO_BUNDLE(), None, None, WITHIN);
        sources_of(&read(&window, &reader, &request).unwrap())[0].clone()
    };
    let all = dated("{}");
    assert!(!results(&all).is_empty());
    let future = dated(r#"{"after":"2999-01-01"}"#);
    assert!(results(&future).is_empty());
    assert_eq!(
        future.get("next"),
        Some(&Py::None),
        "nothing older can match"
    );
    assert_eq!(
        future
            .get("dates")
            .unwrap()
            .get("after")
            .unwrap()
            .get("applied"),
        Some(&Py::Bool(true))
    );
    let past = dated(r#"{"before":"1999-01-01"}"#);
    assert!(results(&past).is_empty());
    let odd = dated(r#"{"before":"someday"}"#);
    assert_eq!(
        results(&odd).len(),
        results(&all).len(),
        "said, not guessed at"
    );
    assert_eq!(
        odd.get("dates")
            .unwrap()
            .get("before")
            .unwrap()
            .get("applied"),
        Some(&Py::Bool(false))
    );
}

/// A reader whose scopes fail statements naming one id, or take `slow` over each row of them.
struct Trouble {
    inner: Reader,
    fails: Option<String>,
    slow: Option<(String, Duration)>,
    /// Scopes it has handed out, so a test can see places taken without taking one.
    opened: AtomicUsize,
}

struct TroubleScope {
    inner: Box<dyn ReadScope>,
    fails: Option<String>,
    slow: Option<(String, Duration)>,
}

fn names(params: &[Param<'_>], id: &str) -> bool {
    params
        .iter()
        .any(|p| matches!(p, Param::Text(text) if text.contains(id)))
}

impl ReadScope for TroubleScope {
    fn position(&self) -> Position {
        self.inner.position()
    }

    fn query(
        &mut self,
        sql: &'static str,
        params: &[Param<'_>],
        each: &mut dyn FnMut(&dyn Row) -> Result<Flow, RecordError>,
    ) -> Result<(), RecordError> {
        if self.fails.as_deref().is_some_and(|id| names(params, id)) {
            return Err(RecordError::Sqlite {
                detail: "this source fails".into(),
            });
        }
        let pause = self
            .slow
            .as_ref()
            .filter(|(id, _)| names(params, id))
            .map(|(_, pause)| *pause);
        self.inner.query(sql, params, &mut |row| {
            if let Some(pause) = pause {
                std::thread::sleep(pause);
            }
            each(row)
        })
    }

    fn statements(&self) -> u32 {
        self.inner.statements()
    }
}

impl RecordReader for Trouble {
    fn read_scope(&self, class: ReadClass) -> Result<Box<dyn ReadScope>, RecordError> {
        let inner = self.inner.read_scope(class)?;
        self.opened.fetch_add(1, Ordering::SeqCst);
        Ok(Box::new(TroubleScope {
            inner,
            fails: self.fails.clone(),
            slow: self.slow.clone(),
        }))
    }

    fn corpus_id(&self) -> &str {
        self.inner.corpus_id()
    }
}

#[test]
fn one_failing_source_never_fails_the_others() {
    let inner = reader();
    let ids = conversations(&inner);
    let (bad, good) = (ids[0].clone(), ids[1].clone());
    let reader = Trouble {
        inner,
        fails: Some(bad.clone()),
        slow: None,
        opened: AtomicUsize::new(0),
    };
    let window = Window::new(world(), "no-dist".as_ref());
    let d = definition(&[
        bad,
        good.clone(),
        "ent-not-there".to_owned(),
        r#"{"kind":"web","domain":"example.com"}"#.to_owned(),
        r#"{"kind":"agent-results"}"#.to_owned(),
        r#"{"kind":"database","collection":"c"}"#.to_owned(),
    ]);
    let request = asked(d, page(&["post"], None), NO_BUNDLE(), None, None, WITHIN);
    let answer = read(&window, &reader, &request).unwrap();
    let got = sources_of(&answer);
    assert_eq!(
        got.iter().map(status).collect::<Vec<_>>(),
        [
            "unavailable",
            "ok",
            "unavailable",
            "unavailable",
            "unavailable",
            "unavailable"
        ],
        "{}",
        answer.dumps()
    );
    assert!(!results(&got[1]).is_empty());
    for source in [&got[0], &got[2], &got[3], &got[4], &got[5]] {
        assert!(
            source
                .get("reason")
                .and_then(Py::as_str)
                .is_some_and(|r| !r.is_empty())
        );
    }
    assert_eq!(
        got[1]
            .get("source")
            .unwrap()
            .get("conversation")
            .and_then(Py::as_str),
        Some(good.as_str())
    );
}

#[test]
fn a_slow_source_runs_out_of_its_share_and_the_next_one_still_answers() {
    let inner = reader();
    let ids = conversations(&inner);
    let (slow, quick) = (ids[0].clone(), ids[1].clone());
    let reader = Trouble {
        inner,
        fails: None,
        slow: Some((slow.clone(), Duration::from_millis(200))),
        opened: AtomicUsize::new(0),
    };
    let window = Window::new(world(), "no-dist".as_ref());
    let d = definition(&[slow, quick]);
    let request = asked(
        d,
        page(&["post"], None),
        NO_BUNDLE(),
        None,
        None,
        Duration::from_millis(1600),
    );
    let answer = read(&window, &reader, &request).unwrap();
    let got = sources_of(&answer);
    assert_eq!(status(&got[0]), "busy", "{}", answer.dumps());
    assert_eq!(status(&got[1]), "ok", "{}", answer.dumps());
    assert!(!results(&got[1]).is_empty());
}

#[test]
fn page_mode_starts_a_stated_few_readings_and_asking_again_gets_further() {
    let _alone = alone();
    let reader = reader();
    let window = Window::new(world(), "no-dist".as_ref());
    let ids = conversations(&reader);
    let d = definition(&ids[..1]);
    let bundle = cold_bundle(1, 1);
    let ask = || {
        asked(
            d.clone(),
            page(&["file"], None),
            Ok(bundle.clone()),
            None,
            None,
            WITHIN,
        )
    };
    let first = read(&window, &reader, &ask()).unwrap();
    let got = &sources_of(&first)[0];
    assert_eq!(status(got), "partial", "{}", first.dumps());
    assert!(results(got).len() <= UNCACHED_MOST, "{}", first.dumps());
    assert!(
        got.get("reason")
            .and_then(Py::as_str)
            .unwrap()
            .contains("ask again")
    );
    let mut read_so_far = results(got).len();
    let mut rounds = 0;
    loop {
        let again = read(&window, &reader, &ask()).unwrap();
        let got = &sources_of(&again)[0];
        assert!(results(got).len() >= read_so_far, "kept readings stay read");
        read_so_far = results(got).len();
        if status(got) == "ok" {
            break;
        }
        rounds += 1;
        assert!(rounds < 200, "it never finished: {}", again.dumps());
    }
    let row = &results(&sources_of(&read(&window, &reader, &ask()).unwrap())[0])[0];
    for key in ["id", "version", "conversation", "author", "at", "value"] {
        assert!(row.get(key).is_some(), "{key} in {}", row.dumps());
    }
    assert_eq!(row.get("kind").and_then(Py::as_str), Some("file"));
}

#[test]
fn a_stopped_finish_starts_no_more_readings_and_the_posts_still_answer() {
    let _alone = alone();
    let reader = reader();
    let window = Window::new(world(), "no-dist".as_ref());
    let ids = conversations(&reader);
    let request = asked(
        definition(&ids[..1]),
        page(&["post", "file"], None),
        Ok(cold_bundle(2, 1)),
        None,
        None,
        WITHIN,
    );
    let op = MagnetRead { window: &window };
    let mut got = mentis_ops::run(&op, &reader, ReadClass::Background, &request).unwrap();
    let Prepared(plan) = got.rows.pop().unwrap();
    let answer = plan.finish(&window, &|| true);
    let source = &sources_of(&answer)[0];
    assert_eq!(status(source), "partial", "{}", answer.dumps());
    let rows = results(source);
    assert!(
        !rows.is_empty()
            && rows
                .iter()
                .all(|r| r.get("kind").and_then(Py::as_str) == Some("post"))
    );
}

#[test]
fn a_definition_from_a_later_schema_is_refused_not_read() {
    let text = r#"{"id":"mag-t","schema_version":99,"sources":[{"kind":"conversation","conversation":"c"}],"selection":{}}"#;
    assert!(matches!(
        MagnetDefinition::parse("mag-t", text),
        Err(NotADefinition::LaterSchema(_))
    ));
}

// -- the class's places, and everyone else ---------------------------------------------------------

#[test]
fn the_client_leaving_ends_the_work_and_frees_the_place() {
    let inner = reader();
    let ids = conversations(&inner);
    let reader = Arc::new(Trouble {
        inner,
        fails: None,
        slow: Some((ids[0].clone(), Duration::from_millis(50))),
        opened: AtomicUsize::new(0),
    });
    let window = Arc::new(Window::new(world(), "no-dist".as_ref()));
    let gone = Arc::new(AtomicBool::new(false));
    let holding: Vec<_> = (0..2)
        .map(|_| {
            let (reader, window, gone) = (reader.clone(), window.clone(), gone.clone());
            let d = definition(&ids[..1]);
            std::thread::spawn(move || {
                let request = ReadRequest {
                    args: MagnetArgs {
                        magnet: d,
                        mode: page(&["post"], None),
                        bundle: NO_BUNDLE(),
                        gone,
                    },
                    cursor: None,
                    limit: None,
                    deadline: Instant::now() + Duration::from_secs(60),
                };
                let op = MagnetRead { window: &window };
                let started = Instant::now();
                let got =
                    mentis_ops::run(&op, &*reader, ReadClass::Background, &request).map(|_| ());
                (got, started.elapsed())
            })
        })
        .collect();
    // Both places are taken, and a third read is told so at once.
    let full = Instant::now() + Duration::from_secs(3);
    while reader.opened.load(Ordering::SeqCst) < 2 {
        assert!(Instant::now() < full, "the reads never took the places");
        std::thread::sleep(Duration::from_millis(1));
    }
    let late = asked(
        definition(&ids[..1]),
        MagnetMode::Summary,
        NO_BUNDLE(),
        None,
        None,
        WITHIN,
    );
    let op = MagnetRead { window: &window };
    assert!(matches!(
        mentis_ops::run(&op, &*reader, ReadClass::Background, &late),
        Err(OpError::Busy { .. })
    ));
    gone.store(true, Ordering::Relaxed);
    for thread in holding {
        let (got, took) = thread.join().unwrap();
        assert!(matches!(got, Err(OpError::Busy { .. })), "{got:?}");
        assert!(took < Duration::from_secs(30), "{took:?}");
    }
    assert!(
        reader.inner.read_scope(ReadClass::Background).is_ok(),
        "the place went back"
    );
}

#[test]
fn a_deadline_frees_the_place_too() {
    let inner = reader();
    let ids = conversations(&inner);
    let reader = Trouble {
        inner,
        fails: None,
        slow: Some((ids[0].clone(), Duration::from_millis(50))),
        opened: AtomicUsize::new(0),
    };
    let window = Window::new(world(), "no-dist".as_ref());
    let request = asked(
        definition(&ids[..1]),
        page(&["post"], None),
        NO_BUNDLE(),
        None,
        None,
        Duration::from_millis(100),
    );
    let answer = read(&window, &reader, &request).unwrap();
    assert_eq!(
        status(&sources_of(&answer)[0]),
        "busy",
        "{}",
        answer.dumps()
    );
    drop(reader.inner.read_scope(ReadClass::Background).unwrap());
    drop(reader.inner.read_scope(ReadClass::Background).unwrap());
}

fn foreground_read(reader: &dyn RecordReader, id: &str) -> Result<(), OpError> {
    let request = ReadRequest {
        args: ConversationArgs {
            id: id.to_owned(),
            ..ConversationArgs::default()
        },
        cursor: None,
        limit: Some(30),
        deadline: Instant::now() + Duration::from_secs(10),
    };
    mentis_ops::run(
        &ConversationCollection,
        reader,
        ReadClass::Foreground,
        &request,
    )
    .map(|_| ())
}

/// A window's own object read, cold, through the same engines a Magnet's readings queue on.
fn foreground_objects(
    reader: &dyn RecordReader,
    window: &Window,
    id: &str,
    salt: usize,
) -> Result<(), OpError> {
    let request = ReadRequest {
        args: ObjectsArgs {
            bundle: cold_bundle(salt, 1),
            ask: ObjectsAsk::Conversation {
                id: id.to_owned(),
                before: None,
                limit: 2,
            },
        },
        cursor: None,
        limit: None,
        deadline: Instant::now() + Duration::from_secs(10),
    };
    let mut got = mentis_ops::run(&Objects { window }, reader, ReadClass::Foreground, &request)?;
    let Prepared(plan) = got.rows.pop().unwrap();
    plan.finish(window).map(|_| ())
}

fn agent_read(reader: &dyn RecordReader, id: &str) -> Result<(), OpError> {
    let request = ReadRequest {
        args: HistoryArgs {
            conversation: Some(id.to_owned()),
            turn: None,
            participant: None,
        },
        cursor: None,
        limit: Some(40),
        deadline: Instant::now() + Duration::from_secs(10),
    };
    mentis_ops::run(&History, reader, ReadClass::Agent, &request).map(|_| ())
}

struct Rounds {
    took: Vec<Duration>,
    failed: Vec<String>,
}

impl Rounds {
    fn middle(&self) -> Duration {
        let mut took = self.took.clone();
        took.sort();
        took.get(took.len() / 2).copied().unwrap_or_default()
    }
}

fn rounds(mut one: impl FnMut(usize) -> Result<(), OpError>, salt: &AtomicUsize) -> Rounds {
    let mut out = Rounds {
        took: Vec::new(),
        failed: Vec::new(),
    };
    for _ in 0..30 {
        let at = Instant::now();
        let n = salt.fetch_add(1, Ordering::Relaxed);
        match one(n) {
            Ok(()) => out.took.push(at.elapsed()),
            Err(error) => out.failed.push(error.to_string()),
        }
    }
    out
}

#[test]
fn saturating_magnet_reads_starve_neither_foreground_nor_agent_reads() {
    let _alone = alone();
    let reader = Arc::new(reader());
    let window = Arc::new(Window::new(world(), "no-dist".as_ref()));
    let ids = conversations(&*reader);
    let salt = Arc::new(AtomicUsize::new(1000));

    let measure = |who: &str| {
        let f = rounds(|_| foreground_read(&*reader, &ids[0]), &salt);
        let o = rounds(|n| foreground_objects(&*reader, &window, &ids[1], n), &salt);
        let a = rounds(|_| agent_read(&*reader, &ids[0]), &salt);
        println!(
            "{who}: foreground {:?}, objects {:?}, agent {:?} (middle of {} each)",
            f.middle(),
            o.middle(),
            a.middle(),
            f.took.len()
        );
        (f, o, a)
    };
    let (base_f, base_o, base_a) = measure("without Magnets");
    assert!(base_f.failed.is_empty() && base_o.failed.is_empty() && base_a.failed.is_empty());

    // Far more Magnet readers than the class has places, each asking a cold page that must extract.
    let stop = Arc::new(AtomicBool::new(false));
    let busy = Arc::new(AtomicUsize::new(0));
    let answered = Arc::new(AtomicUsize::new(0));
    let load: Vec<_> = (0..12)
        .map(|n| {
            let (reader, window, stop) = (reader.clone(), window.clone(), stop.clone());
            let (busy, answered, salt) = (busy.clone(), answered.clone(), salt.clone());
            let d = definition(&ids[n % ids.len()..=n % ids.len()]);
            std::thread::spawn(move || {
                while !stop.load(Ordering::Relaxed) {
                    let s = salt.fetch_add(1, Ordering::Relaxed);
                    let request = asked(
                        d.clone(),
                        page(&["post", "file"], None),
                        Ok(cold_bundle(s, 2000)),
                        None,
                        None,
                        Duration::from_secs(2),
                    );
                    match read(&window, &*reader, &request) {
                        Ok(_) => answered.fetch_add(1, Ordering::Relaxed),
                        Err(OpError::Busy { .. }) => busy.fetch_add(1, Ordering::Relaxed),
                        Err(other) => panic!("{other}"),
                    };
                }
            })
        })
        .collect();
    let saturated = Instant::now() + Duration::from_secs(10);
    while busy.load(Ordering::Relaxed) == 0 {
        assert!(Instant::now() < saturated, "the class was never saturated");
        std::thread::yield_now();
    }
    let (f, o, a) = measure("beside Magnets");
    stop.store(true, Ordering::Relaxed);
    for thread in load {
        thread.join().unwrap();
    }
    println!(
        "Magnets: {} answered, {} told Busy",
        answered.load(Ordering::Relaxed),
        busy.load(Ordering::Relaxed)
    );
    assert!(f.failed.is_empty(), "foreground starved: {:?}", f.failed);
    assert!(
        o.failed.is_empty(),
        "the window's objects starved: {:?}",
        o.failed
    );
    assert!(a.failed.is_empty(), "agents starved: {:?}", a.failed);
    assert_eq!(f.took.len(), base_f.took.len());
    assert_eq!(o.took.len(), base_o.took.len());
    assert_eq!(a.took.len(), base_a.took.len());
    assert!(
        answered.load(Ordering::Relaxed) > 0,
        "Magnets got turns too"
    );
    // The class is free again, whatever the load left.
    drop(reader.read_scope(ReadClass::Background).unwrap());
}

// -- the shapes Python, Rust and the client share: tests/fixtures/magnet-conformance -----------------

fn conformance(name: &str) -> serde_json::Value {
    let path = support::repo_root()
        .join("tests/fixtures/magnet-conformance")
        .join(name);
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

/// A shape in a fixture held against an answer: the same keys, and each value of the same type, without
/// comparing the values. Null beside a value is the same shape: it is what `preview` is with no words.
fn same_shape(path: &str, fixture: &serde_json::Value, answer: &serde_json::Value) {
    use serde_json::Value as J;
    match (fixture, answer) {
        (J::Object(want), J::Object(got)) => {
            let mut wants: Vec<&String> = want.keys().collect();
            let mut gots: Vec<&String> = got.keys().collect();
            wants.sort();
            gots.sort();
            assert_eq!(wants, gots, "{path}");
            for (key, value) in want {
                same_shape(&format!("{path}.{key}"), value, &got[key]);
            }
        }
        (J::Array(want), J::Array(got)) => {
            if let Some(first) = want.first() {
                for (at, item) in got.iter().enumerate() {
                    same_shape(&format!("{path}[{at}]"), first, item);
                }
            }
        }
        (J::Null, _) | (_, J::Null) => {}
        (J::Number(_), J::Number(_)) | (J::String(_), J::String(_)) | (J::Bool(_), J::Bool(_)) => {}
        _ => panic!("{path}: the fixture has {fixture}, the answer {answer}"),
    }
}

fn as_json(value: &Py) -> serde_json::Value {
    serde_json::from_str(&value.dumps()).unwrap()
}

/// The fields of one source the fixture holds as this package's. What else a source says is not
/// compared here: `ent-77c6f16c712a` is that wider gap.
fn summary_fields(source: &serde_json::Value) -> serde_json::Value {
    let mut out = serde_json::Map::new();
    for field in ["participants", "participants_more", "latest", "absent"] {
        if let Some(value) = source.get(field) {
            out.insert(field.to_owned(), value.clone());
        }
    }
    serde_json::Value::Object(out)
}

/// A BRAIN-SEED to grow, on its own: nothing else's answers change with it. Python's commands write it.
const GROW: &str = r#"
import sys
import mentis.api as api
corpus = api.open_corpus(sys.argv[1])
cv = api.brain(corpus).conversations
owner = cv.resolve_participant("@r1-owner")
where = next(c["id"] for c in corpus.entries_of_kind("conversation")
             if c["body"].get("name") == "R1 known conversation")
if sys.argv[2] == "people":
    for n in range(int(sys.argv[3])):
        cv.join(cv.resolve_participant(f"@r1-extra-{n:02}"), where)
elif sys.argv[2] == "rejoins":
    for n in range(int(sys.argv[3])):
        cv.join(owner, where)
elif sys.argv[2] == "links":
    for n in range(int(sys.argv[3])):
        corpus.write(body={"reason": "not a post"}, attributed_to=owner,
                     link={"from": owner, "to": where, "relation": "in-conversation"})
elif sys.argv[2] == "older":
    import mentis.spine.seam as seam
    was = seam._now
    seam._now = lambda: was() - 86400
    cv.say(where, owner, [{"type": "text", "text": "written with the clock stepped back"}])
elif sys.argv[2] == "tied":
    import mentis.spine.seam as seam
    at = seam._now()
    seam._now = lambda: at
    for n in range(int(sys.argv[3])):
        print(cv.say(where, owner, [{"type": "text", "text": f"tied {n}"}]))
elif sys.argv[2] == "import-order":
    import copy, uuid
    entries = corpus.all_entries()
    post_template = next(e for e in entries
                         if e.get("family") == "entry"
                         if (e.get("definition") or {}).get("name") == "contribution"
                         and not e.get("link"))
    link_template = next(e for e in entries
                         if (e.get("link") or {}).get("relation") == "in-conversation")
    at = max(float(e["recorded_at"]) for e in entries) + 1
    def post(text):
        row = copy.deepcopy(post_template)
        row.update(id="ent-" + uuid.uuid4().hex[:12], recorded_at=at,
                   attributed_to=owner,
                   body={"parts": [{"type": "text", "text": text}],
                         "addressed_to": []}, origin=None)
        return row
    def link(post, reason):
        row = copy.deepcopy(link_template)
        row.update(id="ent-" + uuid.uuid4().hex[:12], recorded_at=at,
                   attributed_to=owner, body={"reason": reason}, origin=None)
        row["link"] = dict(row["link"], **{"from": post, "to": where})
        return row
    a, b = post("imported A"), post("imported B")
    link_b, relink_a = link(b["id"], "said here"), link(a["id"], "linked again")
    corpus._store.append_imported([link_b, a, b, relink_a], [])
    print(a["id"])
    print(b["id"])
elif sys.argv[2].startswith("relink:"):
    for n in range(int(sys.argv[3])):
        corpus.write(body={"reason": "linked again"}, attributed_to=owner,
                     link={"from": sys.argv[2][len("relink:"):], "to": where,
                           "relation": "in-conversation"})
elif sys.argv[2] == "alone":
    where = cv.open_conversation(f"alone {sys.argv[3]}", attributed_to=owner)
    post = cv.say(where, owner, [{"type": "text", "text": "the only post"}])
    for n in range(int(sys.argv[3])):
        corpus.write(body={"reason": "linked again"}, attributed_to=owner,
                     link={"from": post, "to": where, "relation": "in-conversation"})
    print(post)
else:
    for n in range(int(sys.argv[3])):
        last = cv.say(where, owner, [{"type": "text", "text": f"grown {n} " + "x" * 400}])
    print(last)
print(where)
"#;

fn grow(brain: &std::path::Path, what: &str, count: u32) -> Vec<String> {
    let done = support::python()
        .args(["-c", GROW])
        .arg(brain)
        .arg(what)
        .arg(count.to_string())
        .output()
        .unwrap();
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    String::from_utf8(done.stdout)
        .unwrap()
        .lines()
        .map(str::to_owned)
        .collect()
}

/// Statements and the rows they gave.
struct Counted<'a> {
    inner: Box<dyn ReadScope>,
    seen: &'a mut Vec<(&'static str, usize)>,
}

impl ReadScope for Counted<'_> {
    fn position(&self) -> Position {
        self.inner.position()
    }

    fn query(
        &mut self,
        sql: &'static str,
        params: &[Param<'_>],
        each: &mut dyn FnMut(&dyn Row) -> Result<Flow, RecordError>,
    ) -> Result<(), RecordError> {
        let mut rows = 0;
        let got = self.inner.query(sql, params, &mut |row| {
            rows += 1;
            each(row)
        });
        self.seen.push((sql, rows));
        got
    }

    fn statements(&self) -> u32 {
        self.inner.statements()
    }
}

fn spent_on(window: &Window, brain: &std::path::Path, id: &str) -> Vec<(&'static str, usize)> {
    let reader = Brain::open(brain).unwrap();
    let request = asked(
        definition(&[id.to_owned()]),
        MagnetMode::Summary,
        NO_BUNDLE(),
        None,
        None,
        WITHIN,
    );
    let mut seen = Vec::new();
    let inner = reader.read_scope(ReadClass::Background).unwrap();
    let mut scope = Counted {
        inner,
        seen: &mut seen,
    };
    MagnetRead { window }
        .read(&mut scope, &request)
        .ok()
        .unwrap();
    seen
}

fn summary_on(window: &Window, brain: &std::path::Path, id: &str) -> Py {
    let reader = Brain::open(brain).unwrap();
    let request = asked(
        definition(&[id.to_owned()]),
        MagnetMode::Summary,
        NO_BUNDLE(),
        None,
        None,
        WITHIN,
    );
    sources_of(&read(window, &reader, &request).unwrap())[0].clone()
}

/// What `sql` costs SQLite up to its `rows`th row, in the times its progress handler is called, which
/// is every branch of its program: a scan or a sorter's every row is one. `mentis-ops` can't reach
/// `rusqlite`, and a row or a statement counted through a scope can't see this. Python's SQLite runs it.
const METER: &str = r#"
import pathlib, sqlite3, sys
brain, rows, sql, *params = sys.argv[1:]
db = sqlite3.connect(pathlib.Path(brain, "corpus.db").resolve().as_uri() + "?mode=ro", uri=True)
ticks = [0]
def tick():
    ticks[0] += 1
db.set_progress_handler(tick, 1)
db.execute(sql, [int(p) if p.isdigit() else p for p in params]).fetchmany(int(rows))
db.set_progress_handler(None, 1)
print(ticks[0])
"#;

fn ticks(brain: &std::path::Path, rows: usize, sql: &str, params: &[&str]) -> u64 {
    let done = support::python()
        .args(["-c", METER])
        .arg(brain)
        .arg(rows.to_string())
        .arg(sql)
        .args(params)
        .output()
        .unwrap();
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    String::from_utf8(done.stdout)
        .unwrap()
        .trim()
        .parse()
        .unwrap()
}

/// The same work in the forms that were read first, which grow, so a flat meter means something.
const SORTS_POSTS: &str = "SELECT e.id FROM entry l JOIN entry e ON e.id = l.link_from \
     WHERE l.link_relation = ? AND l.link_to = ? \
     AND e.def_name = 'contribution' AND e.family = 'entry' AND e.link_relation IS NULL \
     ORDER BY e.recorded_at DESC, e.seq DESC LIMIT 1";
const SORTS_PEOPLE: &str = "SELECT DISTINCT link_from FROM entry \
     WHERE link_to = ? AND link_relation = ? ORDER BY link_from LIMIT 13";

/// How the real engine, the one `Scope` runs, says it will run these.
fn plan_of(reader: &dyn RecordReader, sql: &'static str, params: &[Param<'_>]) -> Vec<String> {
    let mut scope = reader.read_scope(ReadClass::Connector).unwrap();
    let mut steps = Vec::new();
    scope
        .query(sql, params, &mut |row| {
            if let Value::Text(text) = row.value(3)? {
                steps.push(String::from_utf8(text.to_vec()).unwrap());
            }
            Ok(Flow::Continue)
        })
        .unwrap();
    steps
}

#[test]
fn neither_field_sorts_or_scans_in_the_engine_that_reads_them() {
    let reader = reader();
    let id = conversations(&reader).remove(0);
    let explain = |sql: &str| -> &'static str {
        Box::leak(format!("EXPLAIN QUERY PLAN {sql}").into_boxed_str())
    };
    let newest = plan_of(
        &reader,
        explain(NEWEST),
        &[
            Param::Text("in-conversation"),
            Param::Text(&id),
            Param::Integer(NEWEST_ROWS as i64),
        ],
    );
    let joins = plan_of(
        &reader,
        explain(JOINS),
        &[
            Param::Text(&id),
            Param::Text("participates-in"),
            Param::Integer(JOINS_MOST as i64),
        ],
    );
    for plan in [&newest, &joins] {
        assert!(
            plan[0].contains("idx_entry_link_to") && plan[0].contains("link_relation=?"),
            "{plan:#?}"
        );
        assert!(!plan.iter().any(|s| s.contains("TEMP B-TREE")), "{plan:#?}");
    }
    // Each post's own row is one seek, and nothing else is read.
    assert_eq!(newest.len(), 2, "{newest:#?}");
    assert!(newest[1].contains("e USING INDEX"), "{newest:#?}");
    assert_eq!(joins.len(), 1, "{joins:#?}");
}

#[test]
fn what_the_bound_doesn_t_settle_is_absent_with_its_reason() {
    let reason_of = |got: &serde_json::Value, field: &str| -> String {
        let all = got["absent"].as_array().unwrap();
        assert_eq!(all.len(), 1, "{got}");
        assert_eq!(all[0]["field"], field);
        all[0]["reason"].as_str().unwrap().to_owned()
    };
    let source = |window: &Window, brain: &std::path::Path, id: &str| {
        let got = as_json(&summary_on(window, brain, id));
        assert_eq!(got["status"], "ok", "{got}");
        assert!(got["summary"]["posts"].as_u64().unwrap() > 0, "{got}");
        got
    };

    // When the whole bounded set is read, a last link to an older post doesn't hide the newest.
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "magnet-bound-time");
    let window = Window::new(&brain, "no-dist".as_ref());
    let id = grow(&brain, "older", 1).pop().unwrap();
    let got = source(&window, &brain, &id);
    assert_eq!(got["latest"]["id"], established(&brain, &id), "{got}");
    assert!(got.get("absent").is_none(), "{got}");
    assert!(got["participants"].is_array());

    // Exactly the bound exhausts every link; one more cannot be proved safe under import ordering.
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "magnet-bound-links");
    let window = Window::new(&brain, "no-dist".as_ref());
    let wrote = grow(&brain, "alone", LINKS_MOST as u32 - 1);
    let (post, id) = (wrote[0].clone(), wrote[1].clone());
    let got = source(&window, &brain, &id);
    assert_eq!(got["latest"]["id"], post.as_str(), "{got}");
    assert!(got.get("absent").is_none(), "{got}");
    let over = grow(&brain, "alone", LINKS_MOST as u32);
    let id = &over[1];
    let got = source(&window, &brain, &id);
    assert!(got.get("latest").is_none(), "{got}");
    assert!(
        reason_of(&got, "latest").contains("accepted import order"),
        "{got}"
    );

    // Joins enough to read no further, naming no more than are shown: whether there are others isn't
    // settled, so nothing is said of who takes part.
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "magnet-bound-joins");
    let window = Window::new(&brain, "no-dist".as_ref());
    let id = grow(&brain, "rejoins", JOINS_MOST as u32).pop().unwrap();
    let got = source(&window, &brain, &id);
    assert!(
        got.get("participants").is_none() && got.get("participants_more").is_none(),
        "{got}"
    );
    assert!(
        reason_of(&got, "participants").contains(&format!("first {JOINS_MOST} joins")),
        "{got}"
    );
    assert!(got["latest"]["id"].is_string(), "{got}");
    let spent = ticks(
        &brain,
        JOINS_MOST,
        JOINS,
        &[&id, "participates-in", &JOINS_MOST.to_string()],
    );
    grow(&brain, "rejoins", 100);
    assert_eq!(
        spent,
        ticks(
            &brain,
            JOINS_MOST,
            JOINS,
            &[&id, "participates-in", &JOINS_MOST.to_string()],
        ),
        "the most this can read costs the same with more joins beyond it"
    );
}

/// The newest by the order a page reads, sorted as the read mustn't, to hold its answer against.
fn established(brain: &std::path::Path, id: &str) -> String {
    let reader = Brain::open(brain).unwrap();
    let mut scope = reader.read_scope(ReadClass::Connector).unwrap();
    let mut out = String::new();
    scope
        .query(
            SORTS_POSTS,
            &[Param::Text("in-conversation"), Param::Text(id)],
            &mut |row| {
                if let Value::Text(text) = row.value(0)? {
                    out = String::from_utf8(text.to_vec()).unwrap();
                }
                Ok(Flow::Stop)
            },
        )
        .unwrap();
    out
}

fn links_into(brain: &std::path::Path, id: &str) -> u64 {
    let reader = Brain::open(brain).unwrap();
    let mut scope = reader.read_scope(ReadClass::Connector).unwrap();
    let mut out = 0;
    scope
        .query(
            "SELECT COUNT(*) FROM entry WHERE link_to = ?1 AND link_relation = ?2",
            &[Param::Text(id), Param::Text("in-conversation")],
            &mut |row| {
                out = row.value(0)?.integer().unwrap_or(0) as u64;
                Ok(Flow::Stop)
            },
        )
        .unwrap();
    out
}

#[test]
fn accepted_import_order_never_makes_an_earlier_tied_post_latest() {
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "magnet-import-order");
    let window = Window::new(&brain, "no-dist".as_ref());
    let wrote = grow(&brain, "import-order", 1);
    let (a, b, id) = (&wrote[0], &wrote[1], &wrote[2]);

    assert_eq!(established(&brain, id), *b);
    let got = as_json(&summary_on(&window, &brain, id));
    assert_eq!(got["latest"]["id"], *b, "{got}");
    assert_ne!(got["latest"]["id"], *a, "{got}");

    // Exactly the bounded number of links still proves B. One more makes the unseen prefix
    // potentially decisive under the same accepted import ordering, so the field fails closed.
    let held = links_into(&brain, id);
    assert!(
        held <= LINKS_MOST as u64,
        "fixture already exceeds the bound: {held}"
    );
    grow(&brain, "links", LINKS_MOST as u32 - held as u32);
    let got = as_json(&summary_on(&window, &brain, id));
    assert_eq!(got["latest"]["id"], *b, "{got}");
    grow(&brain, "links", 1);
    let got = as_json(&summary_on(&window, &brain, id));
    assert!(got.get("latest").is_none(), "{got}");
    let absent = got["absent"].as_array().unwrap();
    assert_eq!(absent.len(), 1, "{got}");
    assert_eq!(absent[0]["field"], "latest", "{got}");
    assert!(
        absent[0]["reason"]
            .as_str()
            .unwrap()
            .contains("accepted import order"),
        "{got}"
    );
}

#[test]
fn a_post_linked_again_is_never_said_to_be_the_newest_when_it_isn_t() {
    let source = |window: &Window, brain: &std::path::Path, id: &str| {
        let got = as_json(&summary_on(window, brain, id));
        assert_eq!(got["status"], "ok", "{got}");
        got
    };
    let says = |got: &serde_json::Value, post: &str| {
        assert_eq!(got["latest"]["id"], post, "{got}");
        assert!(got.get("absent").is_none(), "{got}");
    };
    let withheld = |got: &serde_json::Value, why: &str| {
        assert!(got.get("latest").is_none(), "{got}");
        let all = got["absent"].as_array().unwrap();
        assert_eq!(all.len(), 1, "{got}");
        assert_eq!(all[0]["field"], "latest");
        assert!(all[0]["reason"].as_str().unwrap().contains(why), "{got}");
    };

    // Two posts at one time, and the earlier linked again: the later is still the newest.
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "magnet-tied");
    let window = Window::new(&brain, "no-dist".as_ref());
    let wrote = grow(&brain, "tied", 2);
    let (a, b, id) = (wrote[0].clone(), wrote[1].clone(), wrote[2].clone());
    let again = format!("relink:{a}");
    says(&source(&window, &brain, &id), &b);
    grow(&brain, &again, 1);
    assert_eq!(established(&brain, &id), b);
    says(&source(&window, &brain, &id), &b);

    // Links that aren't posts change nothing through the exact boundary.
    let held = links_into(&brain, &id);
    assert!(
        held <= LINKS_MOST as u64,
        "fixture already exceeds the bound: {held}"
    );
    grow(&brain, "links", LINKS_MOST as u32 - held as u32);
    says(&source(&window, &brain, &id), &b);

    // One more and it isn't among them: it says so, and never says the post linked again.
    grow(&brain, &again, 1);
    withheld(&source(&window, &brain, &id), "accepted import order");
    assert_eq!(
        established(&brain, &id),
        b,
        "it was knowable only by walking"
    );
    let rows = NEWEST_ROWS.to_string();
    let params = ["in-conversation", id.as_str(), rows.as_str()];
    // Enough that all it reads is links to that post, so what's read is alike before and after.
    grow(&brain, &again, NEWEST_ROWS as u32);
    let spent = ticks(&brain, NEWEST_ROWS, NEWEST, &params);
    grow(&brain, &again, 100);
    assert_eq!(
        spent,
        ticks(&brain, NEWEST_ROWS, NEWEST, &params),
        "the most this can read costs the same with more links"
    );
    withheld(&source(&window, &brain, &id), "accepted import order");

    // Three at one time, the two earlier linked again, then the newest itself.
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "magnet-tied-three");
    let window = Window::new(&brain, "no-dist".as_ref());
    let wrote = grow(&brain, "tied", 3);
    let (a, b, c, id) = (&wrote[0], &wrote[1], &wrote[2], &wrote[3]);
    grow(&brain, &format!("relink:{a}"), 1);
    grow(&brain, &format!("relink:{b}"), 1);
    assert_eq!(&established(&brain, id), c);
    says(&source(&window, &brain, id), c);
    let held = links_into(&brain, id);
    assert!(
        held <= LINKS_MOST as u64,
        "fixture already exceeds the bound: {held}"
    );
    grow(
        &brain,
        &format!("relink:{c}"),
        LINKS_MOST as u32 - held as u32,
    );
    says(&source(&window, &brain, id), c);
    // One more link leaves an unseen prefix whose imported posts cannot be ordered safely.
    grow(&brain, &format!("relink:{c}"), 1);
    withheld(&source(&window, &brain, id), "accepted import order");

    // A post of an earlier time linked again cannot displace the newest when all links are read.
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "magnet-relinked");
    let window = Window::new(&brain, "no-dist".as_ref());
    let wrote = grow(&brain, "posts", 1);
    let (earlier, id) = (wrote[0].clone(), wrote[1].clone());
    let later = grow(&brain, "posts", 1).remove(0);
    says(&source(&window, &brain, &id), &later);
    grow(&brain, &format!("relink:{earlier}"), 1);
    assert_eq!(established(&brain, &id), later);
    says(&source(&window, &brain, &id), &later);

    // All the links there are settle it too: up to the most it reads, one post linked again and again.
    let wrote = grow(&brain, "alone", LINKS_MOST as u32 - 1);
    says(&source(&window, &brain, &wrote[1]), &wrote[0]);
    let wrote = grow(&brain, "alone", LINKS_MOST as u32);
    withheld(&source(&window, &brain, &wrote[1]), "accepted import order");
}

#[test]
fn a_summary_s_fields_cost_the_same_on_a_much_larger_conversation() {
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "magnet-grown");
    let window = Window::new(&brain, "no-dist".as_ref());
    // The same kind of newest post before and after: one plain post, with nothing edited or deleted.
    let first = grow(&brain, "posts", LINKS_MOST as u32);
    let id = &first[1];
    let newest_rows = NEWEST_ROWS.to_string();
    let newest_params = ["in-conversation", id.as_str(), newest_rows.as_str()];
    let sorted_params = ["in-conversation", id.as_str()];
    let newest_before = ticks(&brain, 2, NEWEST, &newest_params);
    let walked_before = ticks(&brain, NEWEST_ROWS, NEWEST, &newest_params);
    let sorted_before = ticks(&brain, 1, SORTS_POSTS, &sorted_params);
    let before = spent_on(&window, &brain, id);
    let small = summary_on(&window, &brain, id);
    let posts_before = small
        .get("summary")
        .unwrap()
        .get("posts")
        .unwrap()
        .dumps()
        .parse::<u64>()
        .unwrap();
    let small_json = as_json(&small);
    assert!(small_json.get("latest").is_none(), "{small_json}");
    assert!(
        small_json["absent"][0]["reason"]
            .as_str()
            .unwrap()
            .contains("accepted import order"),
        "{small_json}"
    );

    const MORE: u32 = 1500;
    grow(&brain, "posts", MORE);
    let after = spent_on(&window, &brain, id);
    assert_eq!(before, after, "the same statements, giving the same rows");
    // And the same work in SQLite, for the two links it stops at and for every link it may read. The
    // same read sorted grows with the posts, so this meter would see it.
    assert_eq!(newest_before, ticks(&brain, 2, NEWEST, &newest_params));
    assert_eq!(
        walked_before,
        ticks(&brain, NEWEST_ROWS, NEWEST, &newest_params)
    );
    let sorted_after = ticks(&brain, 1, SORTS_POSTS, &sorted_params);
    assert!(
        sorted_after > sorted_before + u64::from(MORE),
        "{sorted_before} then {sorted_after}"
    );
    assert!(after.len() as u32 <= SUMMARY_ONE, "{after:#?}");
    for (sql, _) in &after {
        for walks in ["t(root", "operational", "ROW_NUMBER", "json_extract(value"] {
            assert!(!sql.contains(walks), "a summary read {walks}: {sql}");
        }
    }
    let large = summary_on(&window, &brain, id);
    let summary = large.get("summary").unwrap();
    assert_eq!(
        summary.get("posts").unwrap().dumps(),
        (posts_before + u64::from(MORE)).to_string()
    );
    let large_json = as_json(&large);
    assert!(large_json.get("latest").is_none(), "{large_json}");
    assert!(
        large_json["absent"][0]["reason"]
            .as_str()
            .unwrap()
            .contains("accepted import order"),
        "{large_json}"
    );

    // More people than are named: within the same bound, and the rows stay at what is named. Which
    // statements depends only on whether one of those named was ever renamed.
    assert!(large.get("participants_more").is_none());
    grow(&brain, "people", 30);
    let many = summary_on(&window, &brain, id);
    let named = many.get("participants").unwrap().as_list().unwrap();
    assert_eq!(named.len(), PARTICIPANTS_MOST);
    assert_eq!(many.get("participants_more"), Some(&Py::Bool(true)));
    let mut ids: Vec<String> = named
        .iter()
        .map(|p| p.get("id").and_then(Py::as_str).unwrap().to_owned())
        .collect();
    let listed = ids.clone();
    ids.sort();
    ids.dedup();
    assert_eq!(listed, ids, "by id, each once");
    assert!(named.iter().all(|p| {
        p.get("alias")
            .and_then(Py::as_str)
            .is_some_and(|a| !a.is_empty())
    }));
    let crowded = spent_on(&window, &brain, id);
    assert!(crowded.len() as u32 <= SUMMARY_ONE, "{crowded:#?}");
    let most = crowded.iter().map(|(_, rows)| *rows).max().unwrap();
    assert!(most <= 2 * (PARTICIPANTS_MOST + 1), "{crowded:#?}");

    // What finds them costs the same with more people still, in SQLite too, up to where it stops. The
    // same read sorted and taken once each grows with who joined.
    let joins_most = JOINS_MOST.to_string();
    let joins_params = [id.as_str(), "participates-in", joins_most.as_str()];
    let people_params = [id.as_str(), "participates-in"];
    let found = PARTICIPANTS_MOST + 1;
    let joins_before = ticks(&brain, found, JOINS, &joins_params);
    let sorted_before = ticks(&brain, found, SORTS_PEOPLE, &people_params);
    grow(&brain, "people", 90);
    assert_eq!(joins_before, ticks(&brain, found, JOINS, &joins_params));
    let sorted_after = ticks(&brain, found, SORTS_PEOPLE, &people_params);
    assert!(
        sorted_after > sorted_before + 50,
        "{sorted_before} then {sorted_after}"
    );
}

#[test]
fn a_summary_s_fields_have_the_fixture_s_shape() {
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "magnet-shape");
    let id = grow(&brain, "alone", 0).remove(1);
    let reader = Brain::open(&brain).unwrap();
    let window = Window::new(&brain, "no-dist".as_ref());
    let ids = [id];
    let d = definition(&[
        ids[0].clone(),
        "ent-not-there".to_owned(),
        r#"{"kind":"web","domain":"example.com"}"#.to_owned(),
    ]);
    let request = asked(d, MagnetMode::Summary, NO_BUNDLE(), None, None, WITHIN);
    let answer = as_json(&read(&window, &reader, &request).unwrap());

    let fixture = conformance("summary_answer.json");
    let (held, none) = (&fixture["sources"][0], &fixture["sources"][1]);
    let got = &answer["sources"][0];
    assert!(got["participants"].is_array());
    let mut want = summary_fields(held);
    // Said only when there are others, and this Conversation has few.
    want.as_object_mut().unwrap().remove("participants_more");
    same_shape("source", &want, &summary_fields(got));
    assert_eq!(held["participants_more"], serde_json::json!(true));

    // A source that wasn't read says none of them, as the fixture's doesn't.
    same_shape(
        "not read",
        &summary_fields(none),
        &summary_fields(&answer["sources"][1]),
    );
    let absent = conformance("summary_absent_answer.json");
    same_shape(
        "another kind",
        &summary_fields(&absent["sources"][1]),
        &summary_fields(&answer["sources"][2]),
    );
    assert_eq!(answer["sources"][1]["status"], "unavailable");
    assert_eq!(answer["sources"][2]["status"], "unavailable");

    // A page says none of them either.
    let key = format!("conversation:{}", ids[0]);
    let paged = asked(
        definition(&ids[..1]),
        page(&["post"], Some(&key)),
        NO_BUNDLE(),
        None,
        None,
        WITHIN,
    );
    let paged = as_json(&read(&window, &reader, &paged).unwrap());
    same_shape(
        "page",
        &serde_json::json!({}),
        &summary_fields(&paged["sources"][0]),
    );
}

#[test]
fn a_field_that_can_t_be_answered_is_absent_with_its_reason_and_the_summary_stands() {
    let brain = support::changed_seed(env!("CARGO_TARGET_TMPDIR").as_ref(), "magnet-absent");
    let id = grow(&brain, "alone", 0).remove(1);
    let inner = Brain::open(&brain).unwrap();
    let ids = [id];
    let window = Window::new(&brain, "no-dist".as_ref());
    let fixture = conformance("summary_absent_answer.json");
    let summary_of = |reader: &Trouble| {
        let request = asked(
            definition(&ids[..1]),
            MagnetMode::Summary,
            NO_BUNDLE(),
            None,
            None,
            WITHIN,
        );
        as_json(&read(&window, reader, &request).unwrap())["sources"][0].clone()
    };
    // Its newest post can't be read: only `latest` goes.
    let whole = summary_of(&Trouble {
        inner: Brain::open(&brain).unwrap(),
        fails: None,
        slow: None,
        opened: AtomicUsize::new(0),
    });
    let post = whole["latest"]["id"].as_str().unwrap().to_owned();
    let got = summary_of(&Trouble {
        inner,
        fails: Some(post),
        slow: None,
        opened: AtomicUsize::new(0),
    });
    assert_eq!(got["status"], "ok", "{got}");
    assert!(got["summary"]["title"].is_string());
    assert!(got.get("latest").is_none());
    same_shape(
        "latest absent",
        &summary_fields(&fixture["sources"][0]),
        &summary_fields(&got),
    );
    assert_eq!(got["absent"][0]["field"], "latest");
    assert!(
        got["absent"][0]["reason"]
            .as_str()
            .is_some_and(|r| !r.is_empty())
    );

    // Who takes part can't be read: only `participants` goes.
    let got = summary_of(&Trouble {
        inner: Brain::open(&brain).unwrap(),
        fails: Some("participates-in".to_owned()),
        slow: None,
        opened: AtomicUsize::new(0),
    });
    assert_eq!(got["status"], "ok", "{got}");
    assert!(got.get("participants").is_none() && got.get("participants_more").is_none());
    assert!(got["latest"]["id"].is_string());
    assert_eq!(got["absent"][0]["field"], "participants");
}

#[test]
fn definitions_read_here_as_python_reads_them() {
    let all = conformance("definitions.json");
    for d in all["readable"].as_array().unwrap() {
        let id = d["id"].as_str().unwrap();
        let got = MagnetDefinition::parse(id, &d.to_string()).unwrap();
        assert_eq!(got.sources.len(), d["sources"].as_array().unwrap().len());
    }
    for d in all["later_schema"].as_array().unwrap() {
        assert!(matches!(
            MagnetDefinition::parse("mag-64e4a4583ab4e8bd", &d.to_string()),
            Err(NotADefinition::LaterSchema(_))
        ));
    }
    for d in all["repeated_sources"].as_array().unwrap() {
        let id = d["id"].as_str().unwrap();
        assert!(
            matches!(
                MagnetDefinition::parse(id, &d.to_string()),
                Err(NotADefinition::Malformed(_))
            ),
            "{d}"
        );
    }
    for date in all["dates"].as_array().unwrap() {
        assert_eq!(
            mentis_ops::magnet::epoch_of(date["said"].as_str().unwrap()),
            date["at"].as_f64(),
            "{date}"
        );
    }
}

#[test]
fn a_new_definition_says_what_it_keeps_and_applies() {
    let all = conformance("definitions.json");
    let d = &all["readable"][1];
    let got = MagnetDefinition::parse("mag-0325404c1ee81e10", &d.to_string()).unwrap();
    assert_eq!(got.kept, ["phrases"]);
    assert_eq!(
        got.types.as_deref(),
        Some(&["post".to_owned(), "file".to_owned()][..])
    );
    assert!(got.after.unwrap().at.is_some() && got.before.unwrap().at.is_some());
    assert!(got.sources.iter().all(|s| s.unavailable.is_some()));
}

#[test]
fn source_keys_are_the_client_s() {
    for row in conformance("source_keys.json").as_array().unwrap() {
        let source = &row["source"];
        // A source of any kind, keyed in the definition it sits in.
        let text = format!(r#"{{"id":"mag-k","sources":[{source}],"selection":{{}}}}"#);
        let got = MagnetDefinition::parse("mag-k", &text).unwrap();
        assert_eq!(got.sources[0].key, row["key"].as_str().unwrap(), "{source}");
    }
}

#[test]
fn object_types_are_the_client_s() {
    for row in conformance("object_types.json").as_array().unwrap() {
        let object = mentis_ops::pyjson::loads(&row["row"].to_string()).unwrap();
        let want: Vec<String> = row["want"]
            .as_array()
            .unwrap()
            .iter()
            .map(|w| w.as_str().unwrap().to_owned())
            .collect();
        assert_eq!(
            mentis_ops::magnet::object_type(&object, &want),
            row["type"].as_str(),
            "{row}"
        );
    }
}
