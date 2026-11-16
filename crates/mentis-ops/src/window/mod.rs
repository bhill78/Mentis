//! The post window (R2): `fluid/read.py`'s `posts`, `conversation_collection` and `thread_collection`,
//! `agent_work.classify`, and `fluid/objects.py`'s readings. Python's stay, for its other callers, until
//! R7 (`docs/rust/routes.md`). **A difference from Python is a defect:** where this can't be sure of
//! Python's answer it says so as [`OpError::NotOwned`], and the request goes on to Python unchanged.
//!
//! **Two steps, so JavaScript never holds a read scope.** An op reads everything it needs, and answers
//! a [`Prepared`] that holds it. [`crate::run`] then releases the scope, and the adapter calls `finish`,
//! which hashes files and runs extractions, with no scope, no statement and no lock over any of it. A
//! cold page is many times the scope's limit, so nothing else could be right: a held scope takes one of
//! its class's connections from every other reader, and pins the WAL until the reaper arrives.

pub mod classify;
pub mod collections;
pub mod objects;
pub mod posts;
pub mod reads;

use std::collections::{BTreeMap, HashMap};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use serde::{Serialize, Serializer};

use crate::OpError;
use crate::pyjson::Py;
use objects::Extracted;

/// `fluid/objects.py`'s own numbers.
pub const CACHE_BYTES: usize = 24_000_000;
pub const CACHE_MAX: usize = 20_000;
pub const KINDS_MAX: usize = 8192;

/// Python would have to say what this is. Nothing was answered.
pub(crate) fn python_says(what: &str) -> OpError {
    OpError::NotOwned { why: what.into() }
}

/// A question this answers in the route's own words: `_read.BadRequest`.
pub(crate) fn bad_request(why: String) -> OpError {
    OpError::BadRequest { why }
}

/// A 404 of the shape `objects.Unresolved` answers: what the adapter sends, whole.
#[derive(Clone, Debug, PartialEq)]
pub struct Unresolved(pub Py);

/// `Unresolved(address, why, **more)`'s payload.
pub(crate) fn unresolved(address: &str, why: &str, more: Vec<(&str, Py)>) -> Unresolved {
    let mut payload = vec![
        ("error".to_owned(), Py::str(why)),
        ("kind".to_owned(), Py::str("Unresolved")),
        ("address".to_owned(), Py::str(address)),
        ("resolves".to_owned(), Py::Bool(false)),
        ("why".to_owned(), Py::str(why)),
    ];
    payload.extend(more.into_iter().map(|(key, value)| (key.to_owned(), value)));
    Unresolved(Py::Dict(payload))
}

/// A bounded map, least recently used out first.
pub(crate) struct Lru<V> {
    items: HashMap<Key, (V, usize, u64)>,
    order: BTreeMap<u64, Key>,
    tick: u64,
    bytes: usize,
}

/// `(version, returned, digest)`, `objects.extract`'s key: what a reading can't outlive. `body` is
/// the version's stored body, digested: a version is immutable until attested erasure replaces its
/// body (`erasure-design.md` 5), and then nothing read from the old body may be found again.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Key {
    pub version: String,
    pub returned: Vec<String>,
    pub bundle: String,
    pub body: String,
}

impl<V: Clone> Lru<V> {
    pub(crate) fn new() -> Lru<V> {
        Lru {
            items: HashMap::new(),
            order: BTreeMap::new(),
            tick: 0,
            bytes: 0,
        }
    }

    pub(crate) fn get(&mut self, key: &Key) -> Option<V> {
        let (value, _, used) = self.items.get_mut(key)?;
        let value = value.clone();
        self.order.remove(used);
        self.tick += 1;
        *used = self.tick;
        self.order.insert(self.tick, key.clone());
        Some(value)
    }

    pub(crate) fn put(&mut self, key: Key, value: V, size: usize, most: usize, most_bytes: usize) {
        self.tick += 1;
        if let Some((_, old_size, old_used)) = self.items.remove(&key) {
            self.bytes -= old_size;
            self.order.remove(&old_used);
        }
        self.bytes += size;
        self.order.insert(self.tick, key.clone());
        self.items.insert(key, (value, size, self.tick));
        while self.items.len() > most || self.bytes > most_bytes {
            let Some((_, oldest)) = self.order.pop_first() else {
                break;
            };
            if let Some((_, gone, _)) = self.items.remove(&oldest) {
                self.bytes -= gone;
            }
        }
    }
}

/// `_state_cached`'s key: what would change if the file did.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub(crate) struct FileVersion {
    pub digest: String,
    pub size: u64,
    pub modified_ns: u128,
}

/// What a front keeps for the window, for its whole life: engines, and readings that can't go stale.
pub struct Window {
    pub(crate) engines: mentis_extract::Engines,
    pub(crate) extractions: Mutex<Lru<std::sync::Arc<Extracted>>>,
    pub(crate) kinds: Mutex<Lru<Option<Vec<String>>>>,
    pub(crate) verified: Mutex<HashMap<FileVersion, &'static str>>,
    /// The Brain. `artifacts/` is read through it, never `corpus.db*`.
    pub(crate) root: PathBuf,
    /// `render_check.BUNDLE`.
    bundle: PathBuf,
}

impl Window {
    pub fn new(root: &Path, dist: &Path) -> Window {
        Window {
            engines: mentis_extract::Engines::new(),
            extractions: Mutex::new(Lru::new()),
            kinds: Mutex::new(Lru::new()),
            verified: Mutex::new(HashMap::new()),
            root: root.to_path_buf(),
            bundle: dist.join(mentis_extract::BUNDLE_FILE),
        }
    }

    /// The bundle as it is now, read before a scope is taken. If it can't be read Python says what
    /// that means: "the object reader is not built" holds a path Python spelled.
    pub fn bundle(&self) -> Result<mentis_extract::Bundle, OpError> {
        mentis_extract::Bundle::read(&self.bundle)
            .map_err(|error| python_says(&format!("the bundle can't be read: {error}")))
    }

    /// The Brain's root, for a route that reads a file beside the record.
    pub fn root(&self) -> &Path {
        &self.root
    }

    /// A file beside the bundle in the dist: `render_check.BUILD_FILE`.
    pub(crate) fn beside_bundle(&self, name: &str) -> Option<PathBuf> {
        self.bundle.parent().map(|dist| dist.join(name))
    }

    /// `str(path)`, as `objects.py` says it in `renderer` and in the cache's key.
    pub(crate) fn bundle_text(&self) -> String {
        python_path(&self.bundle)
    }
}

/// `str(pathlib.Path(text))` for the absolute paths a front is started with: on Windows `/` is `\`.
fn python_path(path: &Path) -> String {
    let text = path.to_string_lossy();
    if cfg!(windows) {
        text.replace('/', "\\")
    } else {
        text.into_owned()
    }
}

/// An op's single row, whose work isn't done yet: `finish` it. `ReadOp::Row` asks to be `Serialize`
/// for adapters that send a row as it is. This is never sent, so it only says what it is.
pub struct Prepared<P>(pub P);

impl<P> Serialize for Prepared<P> {
    fn serialize<S: Serializer>(&self, to: S) -> Result<S::Ok, S::Error> {
        to.serialize_str("a read still to be finished")
    }
}

/// An answer's end: JSON, or the 404 an address gets.
#[derive(Clone, Debug, PartialEq)]
pub enum Finished {
    Answer(Py),
    Unresolved(Unresolved),
}

impl From<Unresolved> for Finished {
    fn from(unresolved: Unresolved) -> Finished {
        Finished::Unresolved(unresolved)
    }
}
