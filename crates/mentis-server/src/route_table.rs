//! The route table: which side answers a request. Contract: `docs/rust/contracts/route-table.md`.
//!
//! **Unknown means forwarded.** A request no rule matches goes to Python, and so does any path the
//! front would otherwise have to interpret: matching is on the raw path, with no decoding or
//! normalising, so an odd spelling of an owned route falls through to Python's answer.

use std::collections::HashSet;
use std::fmt;
use std::path::{Path, PathBuf};
use std::sync::{Arc, RwLock};
use std::time::Duration;

use serde::Deserialize;
use sha2::{Digest, Sha256};

/// The format this build reads. Any other is refused.
pub const FORMAT: u32 = 1;

/// How often the front looks at the file.
pub const REREAD_EVERY: Duration = Duration::from_secs(1);

/// The table a front uses when it is given no file.
pub const DEFAULT_TABLE: &str = include_str!("../route-table.default.json");

/// Who answers.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Owner {
    Rust,
    Python,
}

/// One rule, as written in the file.
#[derive(Clone, Debug, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuleFile {
    /// The handler's name for `rust`, and how logs name this rule either way. Unique.
    pub id: String,
    /// `GET`, `POST`, `OPTIONS`, or `*` for any method. Upper case, as sent.
    pub method: String,
    /// See [`Pattern`].
    pub path: String,
    pub owner: Owner,
    /// `false` once Python's handler is retired: naming `python` is then refused, because it would
    /// send the route to a handler that no longer exists. Defaults to true.
    #[serde(default = "yes")]
    pub python_handler: bool,
}

fn yes() -> bool {
    true
}

/// The file.
#[derive(Clone, Debug, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TableFile {
    pub format: u32,
    pub routes: Vec<RuleFile>,
}

/// A path pattern, from most to least specific:
///
/// - `/api/pulse`: exactly this path.
/// - `/fluid/api/posts/{}/anchors`: `{}` is one non-empty segment, with no decoding.
/// - `/fluid/api/*`: this prefix, at a segment boundary, and anything below it.
/// - `*`: any path. The last resort, for static files.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Pattern {
    Exact(String),
    Segments(Vec<Option<String>>),
    Prefix(String),
    Any,
}

impl Pattern {
    fn parse(text: &str) -> Result<Pattern, String> {
        if text == "*" {
            return Ok(Pattern::Any);
        }
        if !text.starts_with('/') {
            return Err("a path starts with / or is the single character *".into());
        }
        if let Some(prefix) = text.strip_suffix("/*") {
            if prefix.contains('{') || prefix.contains('*') {
                return Err("a prefix has no {} and only one trailing *".into());
            }
            return Ok(Pattern::Prefix(format!("{prefix}/")));
        }
        if text.contains('*') {
            return Err("* is only allowed as a trailing /* or alone".into());
        }
        if !text.contains('{') {
            return Ok(Pattern::Exact(text.to_owned()));
        }
        let mut segments = Vec::new();
        for segment in text[1..].split('/') {
            match segment {
                "{}" => segments.push(None),
                s if s.contains('{') || s.contains('}') => {
                    return Err("{} is a whole segment".into());
                }
                s => segments.push(Some(s.to_owned())),
            }
        }
        Ok(Pattern::Segments(segments))
    }

    fn matches(&self, path: &str) -> bool {
        match self {
            Pattern::Exact(exact) => path == exact,
            Pattern::Prefix(prefix) => path.starts_with(prefix.as_str()),
            Pattern::Any => true,
            Pattern::Segments(want) => {
                let Some(rest) = path.strip_prefix('/') else {
                    return false;
                };
                let got: Vec<&str> = rest.split('/').collect();
                got.len() == want.len()
                    && got.iter().zip(want).all(|(have, wanted)| match wanted {
                        Some(literal) => have == literal,
                        None => !have.is_empty(),
                    })
            }
        }
    }

    /// Higher wins. Exact, then the most literal segments, then the longest prefix, then `*`.
    fn specificity(&self) -> (u8, usize) {
        match self {
            Pattern::Exact(_) => (3, 0),
            Pattern::Segments(s) => (2, s.iter().filter(|x| x.is_some()).count()),
            Pattern::Prefix(p) => (1, p.len()),
            Pattern::Any => (0, 0),
        }
    }
}

/// A rule ready to match.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Rule {
    pub id: String,
    /// `None` is any method.
    pub method: Option<String>,
    pub pattern: Pattern,
    pub owner: Owner,
}

/// The answer to "who has this request".
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Decision<'a> {
    /// Run this handler. It may still forward a case it does not own.
    Rust { handler: &'a str },
    /// Forward unchanged. `rule` is `None` when no rule matched.
    Python { rule: Option<&'a str> },
}

/// Why a table was not taken. The front keeps what it has and says this.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TableRefused {
    /// The file could not be read.
    Unreadable(String),
    /// Not JSON, or not this shape.
    Malformed(String),
    /// A format this build does not read.
    Format(u32),
    /// A rule is wrong: the rule's id, and why.
    Rule { id: String, why: String },
}

impl fmt::Display for TableRefused {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            TableRefused::Unreadable(why) => write!(f, "the route table cannot be read: {why}"),
            TableRefused::Malformed(why) => write!(f, "the route table is malformed: {why}"),
            TableRefused::Format(got) => {
                write!(f, "route table format {got}; this build reads {FORMAT}")
            }
            TableRefused::Rule { id, why } => write!(f, "route table rule {id:?}: {why}"),
        }
    }
}

impl std::error::Error for TableRefused {}

/// A table that passed every check. Immutable: a re-read makes a new one.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RouteTable {
    /// Most specific first; a method-naming rule before `*` at the same specificity.
    rules: Vec<Rule>,
}

impl RouteTable {
    /// Parse and check. `handlers` is every handler this binary has: a `rust` rule naming anything
    /// else is refused here, so a table can never send a request to code that isn't there.
    pub fn parse(text: &str, handlers: &[&str]) -> Result<RouteTable, TableRefused> {
        let file: TableFile = serde_json::from_str(text)
            .map_err(|error| TableRefused::Malformed(error.to_string()))?;
        if file.format != FORMAT {
            return Err(TableRefused::Format(file.format));
        }
        let mut seen_ids = HashSet::new();
        let mut seen_routes = HashSet::new();
        let mut rules = Vec::with_capacity(file.routes.len());
        for rule in file.routes {
            let refuse = |why: String| TableRefused::Rule {
                id: rule.id.clone(),
                why,
            };
            if rule.id.is_empty() {
                return Err(refuse("a rule needs an id".into()));
            }
            if !seen_ids.insert(rule.id.clone()) {
                return Err(refuse("this id is used twice".into()));
            }
            if !matches!(rule.method.as_str(), "GET" | "POST" | "OPTIONS" | "*") {
                return Err(refuse(format!(
                    "{:?} is not GET, POST, OPTIONS or *",
                    rule.method
                )));
            }
            if !seen_routes.insert((rule.method.clone(), rule.path.clone())) {
                return Err(refuse("another rule has this method and path".into()));
            }
            let pattern = Pattern::parse(&rule.path).map_err(refuse)?;
            match rule.owner {
                Owner::Rust if !handlers.contains(&rule.id.as_str()) => {
                    return Err(refuse("this build has no such handler".into()));
                }
                Owner::Python if !rule.python_handler => {
                    return Err(refuse(
                        "Python's handler is retired, so it can't be python".into(),
                    ));
                }
                _ => {}
            }
            rules.push(Rule {
                id: rule.id,
                method: (rule.method != "*").then_some(rule.method),
                pattern,
                owner: rule.owner,
            });
        }
        // stable: file order settles nothing that matters, because exact duplicates are refused
        rules.sort_by_key(|rule| {
            let (kind, weight) = rule.pattern.specificity();
            std::cmp::Reverse((kind, weight, rule.method.is_some()))
        });
        Ok(RouteTable { rules })
    }

    /// Who has `method` `path`. `path` is the request target's path exactly as sent, before any
    /// `?`. Nothing is decoded, trimmed or collapsed.
    pub fn decide(&self, method: &str, path: &str) -> Decision<'_> {
        for rule in &self.rules {
            let method_fits = rule.method.as_deref().is_none_or(|wanted| wanted == method);
            if method_fits && rule.pattern.matches(path) {
                return match rule.owner {
                    Owner::Rust => Decision::Rust { handler: &rule.id },
                    Owner::Python => Decision::Python {
                        rule: Some(&rule.id),
                    },
                };
            }
        }
        Decision::Python { rule: None }
    }
}

/// What a re-read did.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Reread {
    /// The file's bytes are what was last looked at.
    Unchanged,
    /// A new table is in force from the next request. The digest is of the bytes it was made from.
    Taken { digest: String },
    /// The file is wrong. What was in force stays in force. Reported once per version of the file.
    Refused(TableRefused),
}

/// The table in force, and the file it follows. Reading is cheap and never waits on the file.
#[derive(Debug)]
pub struct LiveRouteTable {
    in_force: RwLock<Arc<RouteTable>>,
    file: Option<PathBuf>,
    handlers: Vec<&'static str>,
    /// The bytes last looked at, good or bad, so a bad file is reported once.
    last_seen: RwLock<Option<Vec<u8>>>,
    /// The digest of the bytes the table started on, for the first line of the log. `None` for the
    /// table in the binary.
    started_on: Option<String>,
}

/// What the log says of a table's file: `contracts/route-table.md`'s digest.
fn digest_of(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

impl LiveRouteTable {
    /// At start, a bad table is a refusal to start: nobody is serving on a table they didn't mean.
    pub fn start(file: Option<&Path>, handlers: &[&'static str]) -> Result<Self, TableRefused> {
        let (text, seen) = match file {
            Some(path) => {
                let bytes = std::fs::read(path)
                    .map_err(|error| TableRefused::Unreadable(error.to_string()))?;
                let text = String::from_utf8(bytes.clone())
                    .map_err(|error| TableRefused::Malformed(error.to_string()))?;
                (text, Some(bytes))
            }
            None => (DEFAULT_TABLE.to_owned(), None),
        };
        let table = RouteTable::parse(&text, handlers)?;
        let started_on = seen.as_deref().map(digest_of);
        Ok(LiveRouteTable {
            in_force: RwLock::new(Arc::new(table)),
            file: file.map(Path::to_path_buf),
            handlers: handlers.to_vec(),
            last_seen: RwLock::new(seen),
            started_on,
        })
    }

    /// The digest of the bytes this table started on.
    pub fn started_on(&self) -> Option<&str> {
        self.started_on.as_deref()
    }

    /// The file it follows. `None` for the table in the binary.
    pub fn file(&self) -> Option<&Path> {
        self.file.as_deref()
    }

    /// The table for one request. A request keeps the table it started with.
    pub fn current(&self) -> Arc<RouteTable> {
        self.in_force
            .read()
            .expect("the table lock is never held across a panic")
            .clone()
    }

    /// Look at the file again. Called every [`REREAD_EVERY`], on a blocking thread. With no file
    /// there is nothing to look at: a front started on the default table stays on it.
    pub fn reread(&self) -> Reread {
        let Some(path) = &self.file else {
            return Reread::Unchanged;
        };
        let bytes = match std::fs::read(path) {
            Ok(bytes) => bytes,
            Err(error) => {
                return self.refused(Vec::new(), TableRefused::Unreadable(error.to_string()));
            }
        };
        if self.seen(&bytes) {
            return Reread::Unchanged;
        }
        let parsed = std::str::from_utf8(&bytes)
            .map_err(|error| TableRefused::Malformed(error.to_string()))
            .and_then(|text| RouteTable::parse(text, &self.handlers));
        match parsed {
            Ok(table) => {
                *self
                    .in_force
                    .write()
                    .expect("the table lock is never held across a panic") = Arc::new(table);
                let digest = digest_of(&bytes);
                *self.last_seen.write().expect("nor this one") = Some(bytes);
                Reread::Taken { digest }
            }
            Err(why) => self.refused(bytes, why),
        }
    }

    fn seen(&self, bytes: &[u8]) -> bool {
        self.last_seen.read().expect("nor this one").as_deref() == Some(bytes)
    }

    fn refused(&self, bytes: Vec<u8>, why: TableRefused) -> Reread {
        if self.seen(&bytes) {
            return Reread::Unchanged;
        }
        *self.last_seen.write().expect("nor this one") = Some(bytes);
        Reread::Refused(why)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const HANDLERS: &[&str] = &["pulse", "static", "anchors"];

    fn table(routes: &str) -> RouteTable {
        RouteTable::parse(&format!(r#"{{"format":1,"routes":[{routes}]}}"#), HANDLERS).unwrap()
    }

    fn refused(routes: &str) -> TableRefused {
        RouteTable::parse(&format!(r#"{{"format":1,"routes":[{routes}]}}"#), HANDLERS).unwrap_err()
    }

    #[test]
    fn the_shipped_default_owns_r1_s_routes_and_python_keeps_the_rest() {
        let t = RouteTable::parse(DEFAULT_TABLE, crate::HANDLERS).unwrap();
        for (path, handler) in [
            ("/api/pulse", "pulse"),
            ("/fluid/api/topics", "topics"),
            ("/fluid/api/names", "names"),
            ("/", "static"),
            ("/assets/app.js", "static"),
            ("/fluid", "static"),
        ] {
            assert_eq!(t.decide("GET", path), Decision::Rust { handler }, "{path}");
        }
        for path in [
            "/api/server",
            "/api/pulse/",
            "/fluid/api/runs",
            "/fluid/api/topics/",
        ] {
            assert!(
                matches!(t.decide("GET", path), Decision::Python { rule: Some(_) }),
                "{path}"
            );
        }
        for method in ["POST", "OPTIONS"] {
            for path in ["/", "/api/pulse", "/fluid/api/topics"] {
                assert_eq!(
                    t.decide(method, path),
                    Decision::Python { rule: None },
                    "{path}"
                );
            }
        }
    }

    #[test]
    fn the_shipped_default_owns_the_window_and_only_the_window_s_routes() {
        let t = RouteTable::parse(DEFAULT_TABLE, crate::HANDLERS).unwrap();
        for (path, handler) in [
            ("/fluid/api/posts", "posts"),
            (
                "/fluid/api/collections/conversation",
                "conversation-collection",
            ),
            ("/fluid/api/collections/thread", "thread-collection"),
            ("/fluid/api/objects", "objects"),
            ("/fluid/api/objects/live:ent-1:k", "object"),
            ("/fluid/api/magnets/mag-a/read", "magnet-read"),
        ] {
            assert_eq!(t.decide("GET", path), Decision::Rust { handler }, "{path}");
        }
        for path in [
            "/fluid/api/posts/ent-1/anchors",
            "/fluid/api/objects/a/b",
            "/fluid/api/magnets/mag-a",
            "/fluid/api/magnets/mag-a/read/more",
            "/fluid/api/objects/",
            "/fluid/api/collections/stream",
            "/fluid/api/collections/selection",
            "/fluid/api/latest",
            "/fluid/api/changes",
            "/fluid/api/object-refs",
        ] {
            assert!(
                matches!(t.decide("GET", path), Decision::Python { rule: Some(_) }),
                "{path}"
            );
        }
        assert_eq!(
            t.decide("POST", "/fluid/api/posts"),
            Decision::Python { rule: None }
        );
    }

    #[test]
    fn unknown_means_forwarded() {
        let t = table(r#"{"id":"pulse","method":"GET","path":"/api/pulse","owner":"rust"}"#);
        assert_eq!(
            t.decide("GET", "/api/pulse"),
            Decision::Rust { handler: "pulse" }
        );
        assert_eq!(
            t.decide("POST", "/api/pulse"),
            Decision::Python { rule: None }
        );
        assert_eq!(
            t.decide("GET", "/api/other"),
            Decision::Python { rule: None }
        );
    }

    #[test]
    fn a_spelling_the_rule_does_not_name_goes_to_python_and_is_never_reinterpreted() {
        let t = table(r#"{"id":"pulse","method":"GET","path":"/api/pulse","owner":"rust"}"#);
        for odd in [
            "/api/pulse/",
            "/api/pulse;x",
            "/api//pulse",
            "/api/%70ulse",
            "/API/pulse",
            "//api/pulse",
        ] {
            assert_eq!(
                t.decide("GET", odd),
                Decision::Python { rule: None },
                "{odd}"
            );
        }
    }

    #[test]
    fn the_most_specific_rule_wins_whatever_order_the_file_says() {
        let t = table(
            r#"{"id":"static","method":"GET","path":"*","owner":"rust"},
               {"id":"fluid","method":"GET","path":"/fluid/api/*","owner":"python"},
               {"id":"api","method":"GET","path":"/api/*","owner":"python"},
               {"id":"anchors","method":"GET","path":"/fluid/api/posts/{}/anchors","owner":"rust"},
               {"id":"pulse","method":"GET","path":"/api/pulse","owner":"rust"}"#,
        );
        assert_eq!(
            t.decide("GET", "/api/pulse"),
            Decision::Rust { handler: "pulse" }
        );
        assert_eq!(
            t.decide("GET", "/api/turns"),
            Decision::Python { rule: Some("api") }
        );
        assert_eq!(
            t.decide("GET", "/fluid/api/posts/ent-1/anchors"),
            Decision::Rust { handler: "anchors" }
        );
        assert_eq!(
            t.decide("GET", "/fluid/api/posts//anchors"),
            Decision::Python {
                rule: Some("fluid")
            }
        );
        assert_eq!(
            t.decide("GET", "/fluid/api/posts/a/b/anchors"),
            Decision::Python {
                rule: Some("fluid")
            }
        );
        assert_eq!(
            t.decide("GET", "/fluid?c=x"),
            Decision::Rust { handler: "static" }
        );
        assert_eq!(t.decide("GET", "/"), Decision::Rust { handler: "static" });
        assert_eq!(t.decide("POST", "/"), Decision::Python { rule: None });
    }

    #[test]
    fn a_prefix_stops_at_a_segment_boundary() {
        let t = table(
            r#"{"id":"api","method":"GET","path":"/api/*","owner":"python"},
                         {"id":"static","method":"GET","path":"*","owner":"rust"}"#,
        );
        assert_eq!(
            t.decide("GET", "/apiary"),
            Decision::Rust { handler: "static" }
        );
        assert_eq!(
            t.decide("GET", "/api/x"),
            Decision::Python { rule: Some("api") }
        );
    }

    #[test]
    fn a_method_naming_rule_beats_any_method_at_the_same_path() {
        let t = table(
            r#"{"id":"everything","method":"*","path":"/api/pulse","owner":"python"},
                         {"id":"pulse","method":"GET","path":"/api/pulse","owner":"rust"}"#,
        );
        assert_eq!(
            t.decide("GET", "/api/pulse"),
            Decision::Rust { handler: "pulse" }
        );
        assert_eq!(
            t.decide("POST", "/api/pulse"),
            Decision::Python {
                rule: Some("everything")
            }
        );
    }

    #[test]
    fn a_rust_rule_needs_a_handler_in_this_build() {
        let why = refused(r#"{"id":"window","method":"GET","path":"/x","owner":"rust"}"#);
        assert!(
            matches!(why, TableRefused::Rule { ref id, .. } if id == "window"),
            "{why}"
        );
    }

    #[test]
    fn a_retired_handler_cannot_be_rolled_back_to() {
        let why = refused(
            r#"{"id":"pulse","method":"GET","path":"/api/pulse","owner":"python","python_handler":false}"#,
        );
        assert!(why.to_string().contains("retired"), "{why}");
        table(
            r#"{"id":"pulse","method":"GET","path":"/api/pulse","owner":"rust","python_handler":false}"#,
        );
    }

    #[test]
    fn every_other_mistake_is_refused_with_its_rule_named() {
        for (routes, says) in [
            (
                r#"{"id":"","method":"GET","path":"/x","owner":"python"}"#,
                "needs an id",
            ),
            (
                r#"{"id":"a","method":"GET","path":"/x","owner":"python"},{"id":"a","method":"GET","path":"/y","owner":"python"}"#,
                "twice",
            ),
            (
                r#"{"id":"a","method":"GET","path":"/x","owner":"python"},{"id":"b","method":"GET","path":"/x","owner":"python"}"#,
                "another rule",
            ),
            (
                r#"{"id":"a","method":"get","path":"/x","owner":"python"}"#,
                "is not GET",
            ),
            (
                r#"{"id":"a","method":"DELETE","path":"/x","owner":"python"}"#,
                "is not GET",
            ),
            (
                r#"{"id":"a","method":"GET","path":"x","owner":"python"}"#,
                "starts with",
            ),
            (
                r#"{"id":"a","method":"GET","path":"/x*","owner":"python"}"#,
                "trailing",
            ),
            (
                r#"{"id":"a","method":"GET","path":"/{}/*","owner":"python"}"#,
                "prefix",
            ),
            (
                r#"{"id":"a","method":"GET","path":"/a{}b/c","owner":"python"}"#,
                "whole segment",
            ),
        ] {
            let why = refused(routes).to_string();
            assert!(why.contains(says), "{routes}: {why}");
        }
    }

    #[test]
    fn the_file_is_strict_about_its_shape_and_format() {
        assert!(matches!(
            RouteTable::parse("{", &[]),
            Err(TableRefused::Malformed(_))
        ));
        assert!(matches!(
            RouteTable::parse(r#"{"format":2,"routes":[]}"#, &[]),
            Err(TableRefused::Format(2))
        ));
        assert!(matches!(
            RouteTable::parse(r#"{"format":1,"routes":[],"default":"rust"}"#, &[]),
            Err(TableRefused::Malformed(_))
        ));
        assert!(matches!(
            RouteTable::parse(
                r#"{"format":1,"routes":[{"id":"a","method":"GET","path":"/x","owner":"mars"}]}"#,
                &[]
            ),
            Err(TableRefused::Malformed(_))
        ));
    }

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("mentis-routes-{}-{name}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        dir.join("routes.json")
    }

    const OWNS_PULSE: &str = r#"{"format":1,"routes":[{"id":"pulse","method":"GET","path":"/api/pulse","owner":"rust"}]}"#;
    const PULSE_BACK: &str = r#"{"format":1,"routes":[{"id":"pulse","method":"GET","path":"/api/pulse","owner":"python"}]}"#;

    #[test]
    fn a_route_goes_back_to_python_with_no_restart_and_a_request_keeps_its_table() {
        let path = scratch("rollback");
        std::fs::write(&path, OWNS_PULSE).unwrap();
        let live = LiveRouteTable::start(Some(&path), &["pulse"]).unwrap();
        let before = live.current();
        assert_eq!(live.reread(), Reread::Unchanged);

        std::fs::write(&path, PULSE_BACK).unwrap();
        assert!(matches!(live.reread(), Reread::Taken { .. }));
        assert_eq!(
            live.current().decide("GET", "/api/pulse"),
            Decision::Python {
                rule: Some("pulse")
            }
        );
        assert_eq!(
            before.decide("GET", "/api/pulse"),
            Decision::Rust { handler: "pulse" }
        );
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn a_bad_file_leaves_the_table_in_force_and_is_reported_once() {
        let path = scratch("bad");
        std::fs::write(&path, OWNS_PULSE).unwrap();
        let live = LiveRouteTable::start(Some(&path), &["pulse"]).unwrap();

        std::fs::write(&path, "{ half a file").unwrap();
        assert!(matches!(
            live.reread(),
            Reread::Refused(TableRefused::Malformed(_))
        ));
        assert_eq!(live.reread(), Reread::Unchanged);
        assert_eq!(
            live.current().decide("GET", "/api/pulse"),
            Decision::Rust { handler: "pulse" }
        );

        std::fs::remove_file(&path).unwrap();
        assert!(matches!(
            live.reread(),
            Reread::Refused(TableRefused::Unreadable(_))
        ));
        assert_eq!(live.reread(), Reread::Unchanged);
        assert_eq!(
            live.current().decide("GET", "/api/pulse"),
            Decision::Rust { handler: "pulse" }
        );

        std::fs::write(&path, PULSE_BACK).unwrap();
        assert!(matches!(live.reread(), Reread::Taken { .. }));
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn the_digest_is_of_the_bytes_put_in_force_whatever_the_file_says_by_then() {
        let path = scratch("digest");
        std::fs::write(&path, OWNS_PULSE).unwrap();
        let live = LiveRouteTable::start(Some(&path), &["pulse"]).unwrap();
        // The file is rewritten after each read: only the bytes that were read may be logged.
        std::fs::write(&path, PULSE_BACK).unwrap();
        assert_eq!(
            live.started_on(),
            Some(digest_of(OWNS_PULSE.as_bytes()).as_str())
        );
        let taken = live.reread();
        std::fs::write(&path, OWNS_PULSE).unwrap();
        assert_eq!(
            taken,
            Reread::Taken {
                digest: digest_of(PULSE_BACK.as_bytes())
            }
        );
        // sha256 of "abc", so this is the digest people compare and not a lookalike.
        assert_eq!(
            digest_of(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn at_start_a_bad_table_is_a_refusal_and_no_file_is_the_default() {
        let path = scratch("start");
        std::fs::write(
            &path,
            r#"{"format":1,"routes":[{"id":"nope","method":"GET","path":"/x","owner":"rust"}]}"#,
        )
        .unwrap();
        assert!(LiveRouteTable::start(Some(&path), &[]).is_err());
        assert!(LiveRouteTable::start(Some(&path.with_extension("missing")), &[]).is_err());

        let live = LiveRouteTable::start(None, crate::HANDLERS).unwrap();
        assert_eq!(live.reread(), Reread::Unchanged);
        assert_eq!(
            live.current().decide("POST", "/x"),
            Decision::Python { rule: None }
        );
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }
}
