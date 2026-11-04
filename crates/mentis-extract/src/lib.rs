//! `extract(bundle, input)`: a post's objects, read by the UI's own function. `contracts/ops.md`, "For
//! R2 and R3". Python's is `_load` and `_run`, `mentis/fluid/objects.py`, and stays beside this until R7.
//!
//! **Nothing here parses Markdown or knows the record.** An input is the JSON text the bundle is
//! given and an output the JSON text it hands back, unread here, so the bytes are the bundle's.
//!
//! **An engine to a thread, and nothing shared between them.** `Runtime` is neither `Send` nor needed
//! to be: each thread of the pool owns one, compiled from the bundle the first time that bundle reaches
//! it. No lock is held over a JS call: a worker has let the queue go before it starts one. Tokio's
//! blocking threads come and go, which is why this pool has its own and not a `thread_local!` on theirs:
//! an engine costs a whole compile of the bundle, so it has to live longer than a request's thread.

use std::cell::Cell;
use std::fmt;
use std::fmt::Write as _;
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::sync::mpsc;
use std::sync::{Arc, Mutex, OnceLock, PoisonError};
use std::thread;
use std::time::{Duration, Instant};

use rquickjs::context::EvalOptions;
use rquickjs::{Context, Function, Runtime, Value};
use sha2::{Digest, Sha256};

/// `render_check.TIME_LIMIT_S`: one call. A bound, not a budget.
pub const TIME_LIMIT: Duration = Duration::from_secs(2);
/// `render_check.MEMORY_LIMIT`.
pub const MEMORY_LIMIT: usize = 64 * 1024 * 1024;
/// `render_check.MAX_CHARS`: longer text is not extracted, and says so. Counted by the caller, who has
/// the parts; it is the one limit that has words in an answer.
pub const MAX_CHARS: usize = 400_000;
/// `render_check`'s `FILE`: the bundle's name in the dist.
pub const BUNDLE_FILE: &str = "render-check.js";

/// Threads, and so engines, at most. The window reads a page's worth of posts at a time, and a person
/// waits on it, so more than one; each engine is its compiled bundle's memory, so not one per core.
const MOST_ENGINES: usize = 4;
/// The engine checks its own stack against QuickJS's default, which is the same on both sides. This
/// is comfortably more than that, so running out is always the engine's exception and never the OS's.
const THREAD_STACK: usize = 8 * 1024 * 1024;

/// What `objects.py` and `render_check.py` add to the bundle, word for word, so both sides call the same
/// functions the same way.
const CALL: &str = concat!(
    "
function mentisObjects(post) {",
    " if (typeof MentisRenderCheck.extractPost !== 'function')",
    "   throw new Error('this bundle has no extractPost: rebuild the UI');",
    " return JSON.stringify(MentisRenderCheck.extractPost(JSON.parse(post))) }",
    "
function mentisCheck(text) {",
    " return JSON.stringify(MentisRenderCheck.checkRendering(text)) }"
);

/// One version of the bundle: what was read from one path at one moment.
#[derive(Clone, Debug)]
pub struct Bundle {
    pub path: PathBuf,
    /// Lowercase hex SHA-256 of the file's bytes.
    pub digest: String,
    bytes: Arc<[u8]>,
}

impl Bundle {
    /// The file as it is now. A rebuilt UI has a new digest whatever its size and time say.
    pub fn read(path: &Path) -> std::io::Result<Bundle> {
        let bytes = std::fs::read(path)?;
        let mut digest = String::with_capacity(64);
        for byte in Sha256::digest(&bytes).iter() {
            let _ = write!(digest, "{byte:02x}");
        }
        Ok(Bundle {
            path: path.to_path_buf(),
            digest,
            bytes: bytes.into(),
        })
    }

    /// A bundle that isn't a file, for tests.
    pub fn of_source(name: &str, source: &str) -> Bundle {
        let mut digest = String::with_capacity(64);
        for byte in Sha256::digest(source.as_bytes()).iter() {
            let _ = write!(digest, "{byte:02x}");
        }
        Bundle {
            path: PathBuf::from(name),
            digest,
            bytes: Arc::from(source.as_bytes()),
        }
    }
}

/// Why nothing came back. **Every one of these is Python's to say:** the words it answers with hold its
/// own exception's name, so a caller forwards. They are kept here for the log.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Failed {
    /// The bundle isn't UTF-8 or would not compile.
    Compile(String),
    /// A JS exception, a time limit or a memory limit.
    Call(String),
    /// The pool could not run it: its threads are gone, or none could start.
    NoEngine(String),
}

impl fmt::Display for Failed {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Failed::Compile(why) => write!(f, "the bundle did not compile: {why}"),
            Failed::Call(why) => write!(f, "extraction failed: {why}"),
            Failed::NoEngine(why) => write!(f, "no engine: {why}"),
        }
    }
}

impl std::error::Error for Failed {}

/// What one call cost, for R2's report. Never a reason to behave differently.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Spent {
    /// Compiling the bundle, if this call had to.
    pub compile: Duration,
    /// The call itself.
    pub call: Duration,
}

struct Engine {
    /// Dropped after `context`, in this order, as `rquickjs` needs.
    context: Context,
    _runtime: Runtime,
    digest: String,
    path: PathBuf,
    /// When this call must have ended. The interrupt handler reads it.
    deadline: Rc<Cell<Instant>>,
}

fn exception(ctx: &rquickjs::Ctx<'_>, error: rquickjs::Error) -> String {
    rquickjs::CaughtError::from_error(ctx, error).to_string()
}

impl Engine {
    /// As `quickjs.Function` does: one global, sloppy script, then the limits. So the limit on memory
    /// counts the compiled bundle too, on both sides. `eval`'s own default here would be strict.
    fn compile(bundle: &Bundle) -> Result<Engine, Failed> {
        let source = std::str::from_utf8(&bundle.bytes)
            .map_err(|error| Failed::Compile(error.to_string()))?;
        let runtime = Runtime::new().map_err(|error| Failed::Compile(error.to_string()))?;
        let context =
            Context::full(&runtime).map_err(|error| Failed::Compile(error.to_string()))?;
        let whole = format!("{source}{CALL}");
        context.with(|ctx| {
            let mut options = EvalOptions::default();
            options.strict = false;
            ctx.eval_with_options::<Value<'_>, _>(whole, options)
                .map(|_| ())
                .map_err(|error| Failed::Compile(exception(&ctx, error)))
        })?;
        let deadline = Rc::new(Cell::new(Instant::now() + TIME_LIMIT));
        let watched = Rc::clone(&deadline);
        runtime.set_interrupt_handler(Some(Box::new(move || Instant::now() >= watched.get())));
        runtime.set_memory_limit(MEMORY_LIMIT);
        Ok(Engine {
            context,
            _runtime: runtime,
            digest: bundle.digest.clone(),
            path: bundle.path.clone(),
            deadline,
        })
    }

    fn call(&self, asked: Asked, input: &str) -> Result<String, Failed> {
        self.deadline.set(Instant::now() + TIME_LIMIT);
        self.context.with(|ctx| {
            let function: Function<'_> = ctx
                .globals()
                .get(asked.function())
                .map_err(|error| Failed::Call(exception(&ctx, error)))?;
            function
                .call::<_, String>((input,))
                .map_err(|error| Failed::Call(exception(&ctx, error)))
        })
    }
}

/// Which of the bundle's two functions a call is for.
#[derive(Clone, Copy)]
enum Asked {
    Extract,
    Check,
}

impl Asked {
    const fn function(self) -> &'static str {
        match self {
            Asked::Extract => "mentisObjects",
            Asked::Check => "mentisCheck",
        }
    }
}

struct Job {
    asked: Asked,
    bundle: Bundle,
    input: String,
    reply: mpsc::Sender<(Result<String, Failed>, Spent)>,
}

/// One thread's life: an engine per the last bundle it saw, and after a failure none, so the next call
/// compiles afresh (`objects._run`: `_engine.clear()`).
fn work(queue: &Mutex<mpsc::Receiver<Job>>) {
    let mut engine: Option<Engine> = None;
    loop {
        let job = {
            let next = queue.lock().unwrap_or_else(PoisonError::into_inner);
            next.recv()
        };
        let Ok(job) = job else {
            return;
        };
        let mut spent = Spent::default();
        let fits = engine
            .as_ref()
            .is_some_and(|have| have.digest == job.bundle.digest && have.path == job.bundle.path);
        if !fits {
            let started = Instant::now();
            engine = None;
            match Engine::compile(&job.bundle) {
                Ok(compiled) => engine = Some(compiled),
                Err(why) => {
                    let _ = job.reply.send((Err(why), spent));
                    continue;
                }
            }
            spent.compile = started.elapsed();
        }
        let started = Instant::now();
        let got = engine
            .as_ref()
            .expect("an engine for this bundle, from just above")
            .call(job.asked, &job.input);
        spent.call = started.elapsed();
        if got.is_err() {
            engine = None;
        }
        let _ = job.reply.send((got, spent));
    }
}

/// The pool. Its threads start on the first call, and end when it is dropped.
#[derive(Default)]
pub struct Engines {
    queue: OnceLock<Result<mpsc::Sender<Job>, String>>,
}

impl Engines {
    pub fn new() -> Engines {
        Engines::default()
    }

    fn sender(&self) -> Result<&mpsc::Sender<Job>, Failed> {
        self.queue
            .get_or_init(|| {
                let (send, receive) = mpsc::channel();
                let receive = Arc::new(Mutex::new(receive));
                let wanted = thread::available_parallelism()
                    .map_or(1, |n| n.get() / 2)
                    .clamp(1, MOST_ENGINES);
                let mut started = 0;
                let mut why = String::new();
                for at in 0..wanted {
                    let queue = Arc::clone(&receive);
                    match thread::Builder::new()
                        .name(format!("mentis-extract-{at}"))
                        .stack_size(THREAD_STACK)
                        .spawn(move || work(&queue))
                    {
                        Ok(_) => started += 1,
                        Err(error) => why = error.to_string(),
                    }
                }
                if started == 0 {
                    return Err(why);
                }
                Ok(send)
            })
            .as_ref()
            .map_err(|why| Failed::NoEngine(why.clone()))
    }

    /// The JSON text `MentisRenderCheck.extractPost(JSON.parse(input))` stringifies to. Blocks, for its
    /// turn and its call, so it runs on a blocking thread and holds no read scope.
    pub fn extract(&self, bundle: &Bundle, input: &str) -> Result<String, Failed> {
        self.extract_measured(bundle, input).map(|(text, _)| text)
    }

    /// [`Engines::extract`], and what it cost.
    pub fn extract_measured(
        &self,
        bundle: &Bundle,
        input: &str,
    ) -> Result<(String, Spent), Failed> {
        self.run(Asked::Extract, bundle, input)
    }

    /// The JSON text `MentisRenderCheck.checkRendering(text)` stringifies to: the UI's own readers, over
    /// a draft. Blocks as [`Engines::extract`] does.
    pub fn check(&self, bundle: &Bundle, text: &str) -> Result<String, Failed> {
        self.run(Asked::Check, bundle, text).map(|(text, _)| text)
    }

    fn run(&self, asked: Asked, bundle: &Bundle, input: &str) -> Result<(String, Spent), Failed> {
        let (reply, answer) = mpsc::channel();
        self.sender()?
            .send(Job {
                asked,
                bundle: bundle.clone(),
                input: input.to_owned(),
                reply,
            })
            .map_err(|error| Failed::NoEngine(error.to_string()))?;
        let (got, spent) = answer
            .recv()
            .map_err(|error| Failed::NoEngine(error.to_string()))?;
        got.map(|text| (text, spent))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const ECHO: &str = "var MentisRenderCheck = {extractPost: function (post) {\
        return {objects: [{key: post.id, n: post.parts.length}]} }};";

    #[test]
    fn it_calls_the_bundle_s_function_and_hands_back_its_text() {
        let engines = Engines::new();
        let bundle = Bundle::of_source("echo.js", ECHO);
        assert_eq!(
            engines
                .extract(&bundle, r#"{"id": "ent-1", "parts": [1, 2]}"#)
                .unwrap(),
            r#"{"objects":[{"key":"ent-1","n":2}]}"#
        );
    }

    #[test]
    fn a_check_calls_the_bundle_s_reader_on_the_text_as_given() {
        let engines = Engines::new();
        let source = "var MentisRenderCheck = {extractPost: function () { return {} },\
            checkRendering: function (text) { return {said: text, n: text.length} }};";
        let bundle = Bundle::of_source("check.js", source);
        assert_eq!(
            engines.check(&bundle, "a\"b\u{e9}").unwrap(),
            "{\"said\":\"a\\\"b\u{e9}\",\"n\":4}"
        );
    }

    #[test]
    fn a_bundle_with_no_check_is_a_failure_not_an_answer() {
        let engines = Engines::new();
        let bundle = Bundle::of_source("old.js", "var MentisRenderCheck = {};");
        assert!(matches!(engines.check(&bundle, "x"), Err(Failed::Call(_))));
    }

    #[test]
    fn a_script_runs_sloppy_as_python_s_does() {
        let engines = Engines::new();
        let source = "var MentisRenderCheck = {extractPost: function (post) {\
            leaked = 1; return {objects: [], sloppy: this === MentisRenderCheck} }};";
        let bundle = Bundle::of_source("sloppy.js", source);
        assert_eq!(
            engines.extract(&bundle, "{}").unwrap(),
            r#"{"objects":[],"sloppy":true}"#
        );
    }

    #[test]
    fn a_rebuilt_bundle_is_read_by_a_new_engine() {
        let engines = Engines::new();
        for at in 0..3 {
            let source = format!(
                "var MentisRenderCheck = {{extractPost: function () {{ return {{v: {at}}} }}}};"
            );
            let bundle = Bundle::of_source("same-name.js", &source);
            assert_eq!(
                engines.extract(&bundle, "{}").unwrap(),
                format!("{{\"v\":{at}}}")
            );
        }
    }

    #[test]
    fn a_bundle_with_no_extract_post_is_a_failure_not_an_answer() {
        let engines = Engines::new();
        let bundle = Bundle::of_source("old.js", "var MentisRenderCheck = {};");
        let why = engines.extract(&bundle, "{}").unwrap_err();
        assert!(why.to_string().contains("no extractPost"), "{why}");
    }

    #[test]
    fn a_bundle_that_will_not_compile_fails_and_the_next_still_runs() {
        let engines = Engines::new();
        let bad = Bundle::of_source("bad.js", "var = ;");
        assert!(matches!(
            engines.extract(&bad, "{}"),
            Err(Failed::Compile(_))
        ));
        let good = Bundle::of_source("good.js", ECHO);
        assert!(
            engines
                .extract(&good, r#"{"id": "x", "parts": []}"#)
                .is_ok()
        );
    }

    #[test]
    fn the_time_limit_ends_a_call_that_would_not_end() {
        let engines = Engines::new();
        let bundle = Bundle::of_source(
            "spins.js",
            "var MentisRenderCheck = {extractPost: function () { while (true) {} }};",
        );
        let started = Instant::now();
        assert!(matches!(
            engines.extract(&bundle, "{}"),
            Err(Failed::Call(_))
        ));
        let took = started.elapsed();
        assert!(took >= TIME_LIMIT, "{took:?}");
        assert!(took < TIME_LIMIT * 3, "{took:?}");
    }

    #[test]
    fn the_memory_limit_ends_a_call_that_would_take_it_all() {
        let engines = Engines::new();
        let bundle = Bundle::of_source(
            "grows.js",
            "var MentisRenderCheck = {extractPost: function () {\
               var all = []; while (true) { all.push(new Array(100000).fill(1)); } }};",
        );
        assert!(matches!(
            engines.extract(&bundle, "{}"),
            Err(Failed::Call(_))
        ));
        // The engine that hit it was dropped, and the next call compiles a good one.
        let good = Bundle::of_source("after.js", ECHO);
        assert!(
            engines
                .extract(&good, r#"{"id": "x", "parts": []}"#)
                .is_ok()
        );
    }

    #[test]
    fn engines_do_not_wait_for_each_other_while_a_call_runs() {
        let engines = Arc::new(Engines::new());
        let threads = thread::available_parallelism().map_or(1, |n| n.get() / 2);
        if threads < 2 {
            return;
        }
        let spins = Bundle::of_source(
            "busy.js",
            "var MentisRenderCheck = {extractPost: function () {\
               var end = Date.now() + 300; while (Date.now() < end) {} return {objects: []} }};",
        );
        let good = Bundle::of_source("quick.js", ECHO);
        // Compile the quick one first, so what's measured is the call.
        engines
            .extract(&good, r#"{"id": "x", "parts": []}"#)
            .unwrap();
        let slow = {
            let (engines, spins) = (Arc::clone(&engines), spins.clone());
            thread::spawn(move || engines.extract(&spins, "{}"))
        };
        thread::sleep(Duration::from_millis(50));
        let started = Instant::now();
        engines
            .extract(&good, r#"{"id": "x", "parts": []}"#)
            .unwrap();
        assert!(started.elapsed() < Duration::from_millis(250));
        slow.join().unwrap().unwrap();
    }
}
