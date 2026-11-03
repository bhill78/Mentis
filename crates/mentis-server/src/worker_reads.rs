//! The six moved reads as the agent door answers them: what `_result` (`worker.py:4104`) returns, as
//! the bytes of `json.dumps(value, default=str)`. **Equal bytes or forward:** a forward is always
//! correct and only slower. Spec: `docs/rust/R3-seams.md`, section 5.
//!
//! The ops say facts and this says what only the door says: the defaults, the sentences that tell a
//! reader what to do next, and the shape, key order included. Grants, framing and the mirror aren't
//! here, because nothing in a moved answer depends on who is asking (section 3).
//!
//! **Every op's `Busy` and `Record` forwards,** on top of `NotOwned`. Python has its own answer for
//! each, and `owner_decisions` and `kinds` answer a failed read in-band, so `contracts/ops.md`'s table
//! gives way to the routes, as its last rule says. `BadRequest` and `NotFound` become Python's in-band
//! refusals where this file can say them exactly.

use std::collections::HashMap;
use std::time::Instant;

use mentis_ops::capabilities::Capabilities;
use mentis_ops::governed::{Governed, GovernedArgs};
use mentis_ops::history::{History, HistoryArgs};
use mentis_ops::kinds::{Kinds, KindsArgs};
use mentis_ops::owner_decisions::{OwnerDecisions, OwnerDecisionsArgs};
use mentis_ops::resolve::{Resolve, ResolveArgs, Resolved, Shape};
use mentis_ops::set_changes::{SetChanges, SetChangesArgs};
use mentis_ops::stored::{Object, Stored};
use mentis_ops::{Cursor, OpError, ReadAnswer, ReadClass, ReadOp, ReadRequest, python};
use mentis_record::{READ_SCOPE_LIMIT, RecordReader};
use serde::Serialize;
use serde_json::{Map, Value};

/// What this door may answer. Anything else forwards.
pub const MOVED: [&str; 6] = [
    "kinds",
    "capabilities",
    "history",
    "owner_decisions",
    "governed",
    "resolve",
];

/// `worker.PAGE`, the door's default where Fluid's route takes the register's.
const PAGE: u32 = 40;
/// `worker.SINCE_MAX`: the most one page of a set's changes gives.
const SINCE_MAX: u32 = 200;
/// `register.MAX_LIMIT`.
const GOVERNED_MOST: u32 = 1000;
/// `ORIENTATION_DECISIONS`, `owner_decisions`' default.
const DECISIONS_DEFAULT: u32 = 5;

/// What Rust says to one moved read.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Read {
    /// `_send(200, value)`'s body: the exact bytes of `json.dumps(value, default=str)` of what
    /// `_result` returns.
    Body(Vec<u8>),
    /// Rust does not answer this: the request goes to Python unchanged.
    NotOwned,
}

/// Python answers this one. Nothing has been said.
struct Forward;

impl From<OpError> for Forward {
    fn from(_: OpError) -> Forward {
        Forward
    }
}

type Answered = Result<Vec<u8>, Forward>;

/// One moved read as the agent door asks it. `args` is `payload["args"]`, or empty. `at` is the time
/// `kinds` reports. Runs one op from `mentis_ops` with [`ReadClass::Agent`]. Blocking.
pub fn read(op: &str, args: &Map<String, Value>, record: &dyn RecordReader, at: f64) -> Read {
    let answered = match op {
        "kinds" => kinds(record, at),
        "capabilities" => capabilities(record),
        "history" => history(args, record),
        "owner_decisions" => owner_decisions(args, record),
        "governed" => governed(args, record),
        "resolve" => resolve(args, record),
        _ => Err(Forward),
    };
    match answered {
        Ok(body) => Read::Body(body),
        Err(Forward) => Read::NotOwned,
    }
}

// -- what a request may hold ----------------------------------------------------------------------

/// `.get(key)` where this door answers only for text or nothing. Anything else is a value Python
/// coerces or trips on. A NUL isn't Rust's to carry to a statement either.
fn text<'a>(args: &'a Map<String, Value>, key: &str) -> Result<Option<&'a str>, Forward> {
    match args.get(key) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(text)) if !text.contains('\0') => Ok(Some(text)),
        Some(_) => Err(Forward),
    }
}

/// A limit in a plain positive integer, at most `most`, or `None` for absent or null. Every other
/// spelling forwards: `0`, a negative (which Python slices with), a float, a bool, a string, and
/// anything over what the op gives.
fn limit(args: &Map<String, Value>, key: &str, most: u32) -> Result<Option<u32>, Forward> {
    match args.get(key) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::Number(given)) => match given.as_u64() {
            Some(given) if (1..=u64::from(most)).contains(&given) => Ok(Some(given as u32)),
            _ => Err(Forward),
        },
        Some(_) => Err(Forward),
    }
}

fn asked<A>(args: A, limit: Option<u32>, cursor: Option<&str>) -> ReadRequest<A> {
    ReadRequest {
        args,
        cursor: cursor.map(|cursor| Cursor(cursor.to_owned())),
        limit,
        deadline: Instant::now() + READ_SCOPE_LIMIT,
    }
}

fn run<O: ReadOp>(
    op: &O,
    record: &dyn RecordReader,
    request: &ReadRequest<O::Args>,
) -> Result<ReadAnswer<O::Row>, OpError> {
    mentis_ops::run(op, record, ReadClass::Agent, request)
}

// -- shaping --------------------------------------------------------------------------------------

/// The fields of what an op serialises, in its order, each as stored.
fn fields_of<T: Serialize>(row: &T) -> Result<Object, Forward> {
    let text = serde_json::to_string(row).map_err(|_| Forward)?;
    Object::parse(&text).ok_or(Forward)
}

fn word(text: &str) -> Stored {
    Stored::of(&text)
}

/// One answer's fields, as a `dict` builds them.
struct Dict(Object);

impl Dict {
    fn new() -> Dict {
        Dict(Object::default())
    }

    fn put(&mut self, key: &str, value: Stored) -> &mut Dict {
        self.0.set(key, value);
        self
    }

    fn say(&mut self, key: &str, words: &str) -> &mut Dict {
        self.put(key, word(words))
    }

    /// `key` as `from` holds it. A field an op always serialises, so its absence is a defect here,
    /// and Python answers.
    fn keep(&mut self, from: &Object, key: &str) -> Result<&mut Dict, Forward> {
        let value = from.get(key).ok_or(Forward)?.clone();
        Ok(self.put(key, value))
    }

    fn finish(&self) -> Answered {
        let text = serde_json::to_string(&self.0).map_err(|_| Forward)?;
        python_text(&text).map(String::into_bytes).ok_or(Forward)
    }
}

/// The one row `rows` holds, whichever op it is.
fn the_row<R>(mut answer: ReadAnswer<R>) -> Result<R, Forward> {
    answer.rows.pop().ok_or(Forward)
}

// -- capabilities ---------------------------------------------------------------------------------

fn capabilities(record: &dyn RecordReader) -> Answered {
    let row = the_row(run(&Capabilities, record, &asked((), None, None))?)?;
    let got = fields_of(&row)?;
    let mut out = Dict::new();
    out.keep(&got, "capabilities")?.keep(&got, "count")?.say(
        "note",
        "what a runtime can declare and work can require (`requires` on delegate). A requirement \
         naming anything else is refused.",
    );
    out.finish()
}

// -- kinds ----------------------------------------------------------------------------------------

fn kinds(record: &dyn RecordReader, at: f64) -> Answered {
    let row = the_row(run(&Kinds, record, &asked(KindsArgs { at }, None, None))?)?;
    let got = fields_of(&row)?;
    let mut groups_mean = Dict::new();
    groups_mean
        .say(
            "proposed",
            "written, neither established nor answered by a successor. In the record; nobody was \
             asked",
        )
        .say("standing", "established, and nothing has superseded it")
        .say(
            "history",
            "superseded -- after establishment (ended) or before it (replaced, it never held)",
        )
        .say(
            "unknown",
            "standing not determined: the Kind does not declare whether standing applies, or it \
             could not be computed. unknown_because says which",
        );
    let mut out = Dict::new();
    out.keep(&got, "as_read_at")?
        .say(
            "as_read",
            "counted from the live store at as_read_at. Not kept anywhere and not a promise: a \
             later write changes them, so ask again rather than reuse an old answer.",
        )
        .keep(&got, "kinds")?
        .keep(&got, "definitions")?
        .keep(&got, "links")?
        .put("groups_mean", Stored::of(&groups_mean.0))
        .say(
            "split_none_means",
            "no split exists for that Kind or group, and split_because or unknown_because says \
             why. None is never a count of zero",
        );
    out.finish()
}

// -- history --------------------------------------------------------------------------------------

/// `_result`'s `history` branch. An empty `set` is no set, as `if args.get("set")` reads it.
fn history(args: &Map<String, Value>, record: &dyn RecordReader) -> Answered {
    let set = text(args, "set")?;
    let since = text(args, "since")?;
    if let Some(set) = set.filter(|set| !set.is_empty()) {
        return set_changes(python::strip(set), since, args, record);
    }
    let most = limit(args, "limit", History::MOST)?;
    let filters = HistoryArgs {
        conversation: text(args, "conversation")?.map(str::to_owned),
        turn: text(args, "turn")?.map(str::to_owned),
        participant: text(args, "participant")?.map(str::to_owned),
    };
    if since.is_some_and(|since| !since.is_empty()) {
        let mut out = Dict::new();
        out.put("refused", Stored::of(&true))
            .say("asked", "history")
            .say(
                "why_not",
                "`since` reads what changed in a response set: name the set with `set`",
            );
        return out.finish();
    }
    let request = asked(filters, Some(most.unwrap_or(PAGE)), None);
    let row = the_row(run(&History, record, &request)?)?;
    let mut acts = Vec::with_capacity(row.acts.len());
    for act in &row.acts {
        let fields = fields_of(act)?;
        let mut shown = Dict::new();
        for (key, value) in &fields.0 {
            shown.put(key, value.clone());
            // `rows[-1].update(gone[r], deleted_material=r)`: the sentence is the door's.
            if key == "deleted"
                && let Some(mark) = &act.deleted
            {
                shown.say("note", &deleted_material_note(&mark.what, &mark.reference));
            }
        }
        acts.push(shown.0);
    }
    let mut out = Dict::new();
    out.put("acts", Stored::of(&acts))
        .put("matched", Stored::of(&row.matched))
        .put("not_returned", Stored::of(&row.not_returned));
    out.finish()
}

/// `_deleted_marking`'s `note`, `worker.py:4371`.
fn deleted_material_note(what: &str, reference: &str) -> String {
    format!(
        "DELETED MATERIAL: this came in on a {what} that has been deleted ({reference}). Mark any \
         passage that uses it as deleted material."
    )
}

const MORE_CHANGES: &str = "more changes follow: ask again with since=<cursor>";
const NO_MORE_CHANGES: &str = "nothing after cursor yet; keep it and ask again with since=<cursor>";

/// `Surface.set_changes` and `form_changes`: `set` is already stripped, as `_result` hands it on.
fn set_changes(
    set: &str,
    since: Option<&str>,
    args: &Map<String, Value>,
    record: &dyn RecordReader,
) -> Answered {
    let most = limit(args, "limit", SINCE_MAX)?;
    let request = asked(
        SetChangesArgs {
            set: set.to_owned(),
        },
        Some(most.unwrap_or(PAGE)),
        since,
    );
    match run(&SetChanges, record, &request) {
        Ok(mut answer) => {
            let row = answer.rows.pop().ok_or(Forward)?;
            let more = answer.more.is_some();
            let got = fields_of(&row)?;
            let mut out = Dict::new();
            out.keep(&got, "set")?;
            if row.decision_form.is_some() {
                out.keep(&got, "decision_form")?;
            }
            out.keep(&got, "since")?
                .keep(&got, "changes")?
                .keep(&got, "cursor")?
                .put("more", Stored::of(&more))
                .keep(&got, "not_returned")?;
            if row.decision_form.is_some() {
                out.keep(&got, "open")?.keep(&got, "closed")?;
            }
            out.say("note", if more { MORE_CHANGES } else { NO_MORE_CHANGES });
            out.finish()
        }
        // `since` isn't one of its entries: the op's sentence, which it shows with `repr`.
        Err(OpError::BadRequest { why }) => {
            let stripped = since.map(python::strip).filter(|since| !since.is_empty());
            let mut out = Dict::new();
            out.put("refused", Stored::of(&true))
                .say("set", set)
                .put("since", Stored::of(&stripped))
                .say("why_not", &why);
            out.finish()
        }
        // Neither a set nor a form: `exc.refusal.get("error")`.
        Err(OpError::NotFound { what }) => {
            let mut out = Dict::new();
            out.put("refused", Stored::of(&true))
                .say("why_not", &what)
                .say("set", set);
            out.finish()
        }
        Err(_) => Err(Forward),
    }
}

// -- owner_decisions ------------------------------------------------------------------------------

/// `Surface.owner_decisions`. `most` over `PAGE`, or that Python would coerce or refuse, forwards,
/// and so does a name it can't `repr` here. What a failed read says is Python's: it answers empty
/// lists (`conversation/__init__.py:6337`), which is why the route wins over `contracts/ops.md`'s
/// `Record` row.
fn owner_decisions(args: &Map<String, Value>, record: &dyn RecordReader) -> Answered {
    let most = limit(args, "most", PAGE)?;
    let refused = |why: &str| {
        let mut out = Dict::new();
        out.put("refused", Stored::of(&true))
            .say("asked", "owner_decisions")
            .say("why_not", why);
        out.finish()
    };
    let conversation = text(args, "conversation")?;
    let Some(conversation) = conversation.filter(|given| !python::strip(given).is_empty()) else {
        return refused(
            "owner_decisions needs `conversation`, a Conversation's ent-... id (`orient` lists \
             them)",
        );
    };
    let request = asked(
        OwnerDecisionsArgs {
            conversation: conversation.to_owned(),
        },
        Some(most.unwrap_or(DECISIONS_DEFAULT)),
        None,
    );
    match run(&OwnerDecisions, record, &request) {
        Ok(answer) => {
            let row = the_row(answer)?;
            let got = fields_of(&row)?;
            let mut out = Dict::new();
            out.keep(&got, "conversation")?
                .keep(&got, "open")?
                .keep(&got, "answered")?
                .keep(&got, "open_count")?
                .keep(&got, "answered_count")?;
            out.finish()
        }
        Err(OpError::NotFound { .. }) => {
            let shown = python::repr(conversation).ok_or(Forward)?;
            refused(&format!("{shown} is not a Conversation in this record"))
        }
        Err(_) => Err(Forward),
    }
}

// -- governed -------------------------------------------------------------------------------------

/// `register.GROUPS`, in a refusal of `state`.
const GROUPS: [&str; 5] = ["proposed", "recorded", "standing", "history", "unknown"];

/// `register.governed` as `Surface.governed` calls it: the door's `PAGE`, and never a cursor.
fn governed(args: &Map<String, Value>, record: &dyn RecordReader) -> Answered {
    let most = limit(args, "limit", GOVERNED_MOST)?;
    let filters = GovernedArgs {
        kind: text(args, "kind")?.map(str::to_owned),
        q: text(args, "q")?.map(str::to_owned),
        state: text(args, "state")?.map(str::to_owned),
    };
    let request = asked(filters, Some(most.unwrap_or(PAGE)), None);
    match run(&Governed, record, &request) {
        Ok(answer) => {
            let row = the_row(answer)?;
            let got = fields_of(&row)?;
            let mut because = Dict::new();
            because
                .say(
                    "directs_work",
                    "its Kind declares that its material directs how work is done, so placed and \
                     standing it GOVERNS the work -- this is what delivery carries as governance",
                )
                .say(
                    "standing_knowledge",
                    "standing is meaningful for its Kind and its material STATES something rather \
                     than directing work. It governs nothing, and delivery never carries it as \
                     governance. It is here because correcting it is a supersession and this is \
                     where it is found",
                );
            let kinds = Object::parse(got.get("kinds").ok_or(Forward)?.text()).ok_or(Forward)?;
            let mut out = Dict::new();
            out.keep(&got, "query")?
                .keep(&got, "groups")?
                .keep(&got, "totals")?
                .keep(&got, "omitted")?
                .keep(&got, "matched")?
                .keep(&got, "walked")?
                .put("kinds", Stored::of(&kinds))
                .put("listed_because", Stored::of(&because.0))
                .say(
                    "governs_is_per_row",
                    "a row's `governs` is its Kind's own declaration and not its presence in this \
                     register. Being listed here means standing applies to it, never that it \
                     directs anybody's work",
                )
                .keep(&got, "why_not")?
                .say(
                    "not_an_ask",
                    "recorded material asks nobody anything; proposed means an explicit adoption \
                     request. The ask itself is an expectation",
                );
            out.finish()
        }
        Err(OpError::BadRequest { why }) => {
            let mut out = Dict::new();
            out.say("error", &why);
            if why.starts_with("no such group ") {
                out.put("groups", Stored::of(&GROUPS));
            } else if why.starts_with("no Kind is defined as ") {
                out.say("hint", "ask /api/kinds what this record declares");
            } else {
                // A limit, or a cursor, neither of which this door lets through.
                return Err(Forward);
            }
            out.finish()
        }
        Err(_) => Err(Forward),
    }
}

// -- resolve --------------------------------------------------------------------------------------

/// A decision form on a Turn, `worker.py:1617`.
const FORM_NOTE: &str = "a decision form: each question is answered by the owner's reply naming \
     it. `history set=<form> since=<cursor>` says what was answered or withdrawn since";

/// A reaction, `worker.py:1225`.
const REACTION_NOTE: &str =
    "an attributed occurrence; it has no standing and no effect on anything";

/// The sentence `resolve` puts beside the text of behavioural material, `worker.py:1336`. Procedural
/// material governs and propositional material is carried forward, so the two ladders differ.
fn standing_sentence(row: &Resolved, knowing: &str) -> &'static str {
    let directs_work = knowing == "how";
    match (row.stands, !row.superseded_by.is_empty(), directs_work) {
        (true, _, true) => "governing: established, and not superseded",
        (true, _, false) => {
            "established: carried forward as something this Brain knows, and governing nothing"
        }
        (false, true, true) => "ended: superseded by later material",
        (false, true, false) => {
            "ended: superseded by later material, and no longer carried forward"
        }
        (false, false, true) => {
            "proposed: written down, established by nobody, and governing nothing"
        }
        (false, false, false) => {
            "proposed: written down, established by nobody, and asserted by this Brain as nothing \
             more than written down"
        }
    }
}

fn resolve(args: &Map<String, Value>, record: &dyn RecordReader) -> Answered {
    // `args["ref"]`: absent raises, and what isn't text reaches a read that isn't Rust's to imitate.
    if !matches!(args.get("ref"), Some(Value::String(_))) {
        return Err(Forward);
    }
    let reference = text(args, "ref")?.ok_or(Forward)?;
    let request = asked(
        ResolveArgs {
            reference: reference.to_owned(),
        },
        None,
        None,
    );
    let row = match run(&Resolve, record, &request) {
        Ok(answer) => the_row(answer)?,
        Err(OpError::NotFound { .. }) => {
            let mut out = Dict::new();
            out.say("ref", reference)
                .put("known", Stored::of(&false))
                .say("why_not", "this corpus holds no entry with that reference");
            return out.finish();
        }
        Err(_) => return Err(Forward),
    };

    let got = fields_of(&row)?;
    let mut out = Dict::new();
    for (key, value) in &got.0 {
        match key.as_str() {
            "ref" => {
                out.put(key, value.clone()).put("known", Stored::of(&true));
            }
            // The fact the sentence below is chosen by. Python has no such key.
            "knowing" => {}
            "decision_forms" => {
                let Shape::Turn { decision_forms, .. } = &row.shape else {
                    return Err(Forward);
                };
                let mut forms = Vec::with_capacity(decision_forms.len());
                for form in decision_forms {
                    let mut fields = fields_of(form)?;
                    fields.set("note", word(FORM_NOTE));
                    forms.push(fields);
                }
                out.put(key, Stored::of(&forms));
            }
            "about" if matches!(row.shape, Shape::Reaction { .. }) => {
                out.put(key, value.clone()).say("note", REACTION_NOTE);
            }
            _ => {
                out.put(key, value.clone());
            }
        }
    }
    if let Some(knowing) = &row.knowing {
        out.say("standing", standing_sentence(&row, knowing));
    }
    out.finish()
}

// -- json.dumps -----------------------------------------------------------------------------------

/// How deep a value this door will show. `serde_json` stops at 128 too.
const DEEPEST: u32 = 128;
/// `sys.get_int_max_str_digits()`: `json.loads` raises on an integer with more.
const MOST_DIGITS: usize = 4300;

/// `json.dumps(json.loads(text), default=str)`: the record's JSON, as Python's `json` hands it on
/// after reading it. `", "` and `": "`, ASCII escapes, floats by `repr`, and a repeated key at its
/// first place with its last value. `None` for what Python raises on or would show as something else
/// (a float past the range is `Infinity`), which is Python's to say.
pub fn python_text(text: &str) -> Option<String> {
    let mut reading = Reading {
        bytes: text.as_bytes(),
        text,
        at: 0,
    };
    let mut out = String::with_capacity(text.len() + text.len() / 4);
    reading.space();
    reading.value(&mut out, 0)?;
    reading.space();
    (reading.at == text.len()).then_some(out)
}

struct Reading<'a> {
    bytes: &'a [u8],
    text: &'a str,
    at: usize,
}

impl Reading<'_> {
    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.at).copied()
    }

    fn space(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\t' | b'\n' | b'\r')) {
            self.at += 1;
        }
    }

    fn word(&mut self, word: &str, out: &mut String) -> Option<()> {
        self.text[self.at..].starts_with(word).then(|| {
            self.at += word.len();
            out.push_str(word);
        })
    }

    fn value(&mut self, out: &mut String, depth: u32) -> Option<()> {
        if depth > DEEPEST {
            return None;
        }
        match self.peek()? {
            b'{' => self.object(out, depth),
            b'[' => self.list(out, depth),
            b'"' => self.string(out),
            b't' => self.word("true", out),
            b'f' => self.word("false", out),
            b'n' => self.word("null", out),
            _ => self.number(out),
        }
    }

    fn list(&mut self, out: &mut String, depth: u32) -> Option<()> {
        self.at += 1;
        out.push('[');
        self.space();
        if self.peek()? == b']' {
            self.at += 1;
            out.push(']');
            return Some(());
        }
        loop {
            self.space();
            self.value(out, depth + 1)?;
            self.space();
            match self.peek()? {
                b',' => {
                    self.at += 1;
                    out.push_str(", ");
                }
                b']' => {
                    self.at += 1;
                    out.push(']');
                    return Some(());
                }
                _ => return None,
            }
        }
    }

    fn object(&mut self, out: &mut String, depth: u32) -> Option<()> {
        self.at += 1;
        self.space();
        if self.peek()? == b'}' {
            self.at += 1;
            out.push_str("{}");
            return Some(());
        }
        let mut fields: Vec<(String, String)> = Vec::new();
        let mut places: HashMap<String, usize> = HashMap::new();
        loop {
            self.space();
            if self.peek()? != b'"' {
                return None;
            }
            let mut key = String::new();
            self.string(&mut key)?;
            self.space();
            if self.peek()? != b':' {
                return None;
            }
            self.at += 1;
            self.space();
            let mut value = String::new();
            self.value(&mut value, depth + 1)?;
            match places.get(&key) {
                Some(place) => fields[*place].1 = value,
                None => {
                    places.insert(key.clone(), fields.len());
                    fields.push((key, value));
                }
            }
            self.space();
            match self.peek()? {
                b',' => self.at += 1,
                b'}' => {
                    self.at += 1;
                    break;
                }
                _ => return None,
            }
        }
        out.push('{');
        for (place, (key, value)) in fields.iter().enumerate() {
            if place > 0 {
                out.push_str(", ");
            }
            out.push_str(key);
            out.push_str(": ");
            out.push_str(value);
        }
        out.push('}');
        Some(())
    }

    /// `ensure_ascii`, one UTF-16 unit at a time, so a lone surrogate goes on as Python's would.
    fn string(&mut self, out: &mut String) -> Option<()> {
        self.at += 1;
        out.push('"');
        loop {
            let byte = self.peek()?;
            match byte {
                b'"' => {
                    self.at += 1;
                    out.push('"');
                    return Some(());
                }
                b'\\' => {
                    self.at += 1;
                    let escape = self.peek()?;
                    self.at += 1;
                    let unit = match escape {
                        b'"' | b'\\' | b'/' => u16::from(escape),
                        b'b' => 0x8,
                        b'f' => 0xc,
                        b'n' => 0xa,
                        b'r' => 0xd,
                        b't' => 0x9,
                        b'u' => {
                            let hex = self.text.get(self.at..self.at + 4)?;
                            if !hex.bytes().all(|b| b.is_ascii_hexdigit()) {
                                return None;
                            }
                            self.at += 4;
                            u16::from_str_radix(hex, 16).ok()?
                        }
                        _ => return None,
                    };
                    push_unit(unit, out);
                }
                // `strict`: `json.loads` raises on a control character in a string.
                0..0x20 => return None,
                0x20..0x80 => {
                    self.at += 1;
                    push_unit(u16::from(byte), out);
                }
                _ => {
                    let c = self.text[self.at..].chars().next()?;
                    self.at += c.len_utf8();
                    let mut units = [0u16; 2];
                    for unit in c.encode_utf16(&mut units) {
                        push_unit(*unit, out);
                    }
                }
            }
        }
    }

    fn number(&mut self, out: &mut String) -> Option<()> {
        let start = self.at;
        if self.peek()? == b'-' {
            self.at += 1;
        }
        let first = self.at;
        while matches!(self.peek(), Some(b'0'..=b'9')) {
            self.at += 1;
        }
        let digits = &self.text[first..self.at];
        if digits.is_empty() || (digits.len() > 1 && digits.starts_with('0')) {
            return None;
        }
        let mut float = false;
        if self.peek() == Some(b'.') {
            float = true;
            self.at += 1;
            let fraction = self.at;
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.at += 1;
            }
            if self.at == fraction {
                return None;
            }
        }
        if matches!(self.peek(), Some(b'e' | b'E')) {
            float = true;
            self.at += 1;
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.at += 1;
            }
            let exponent = self.at;
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.at += 1;
            }
            if self.at == exponent {
                return None;
            }
        }
        let number = &self.text[start..self.at];
        if float {
            out.push_str(&float_repr(number.parse().ok()?)?);
        } else if digits.len() > MOST_DIGITS {
            return None;
        } else if digits == "0" {
            // `int("-0")` is `0`.
            out.push('0');
        } else {
            out.push_str(number);
        }
        Some(())
    }
}

/// `json.encoder`'s `ESCAPE_ASCII`: everything outside `' '` to `'~'`, and the two that need one.
fn push_unit(unit: u16, out: &mut String) {
    match unit {
        0x22 => out.push_str("\\\""),
        0x5c => out.push_str("\\\\"),
        0xa => out.push_str("\\n"),
        0xd => out.push_str("\\r"),
        0x9 => out.push_str("\\t"),
        0x8 => out.push_str("\\b"),
        0xc => out.push_str("\\f"),
        0x20..=0x7e => out.push(char::from(unit as u8)),
        _ => out.push_str(&format!("\\u{unit:04x}")),
    }
}

/// `float.__repr__`: the shortest digits that read back the same, which both languages agree on,
/// laid out as Python lays them out. `None` for what isn't finite, where `json.dumps` writes
/// `Infinity` or `NaN`.
fn float_repr(value: f64) -> Option<String> {
    if !value.is_finite() {
        return None;
    }
    if value == 0.0 {
        return Some(
            if value.is_sign_negative() {
                "-0.0"
            } else {
                "0.0"
            }
            .to_owned(),
        );
    }
    let shown = format!("{value:e}");
    let (mantissa, exponent) = shown.split_once('e')?;
    let exponent: i32 = exponent.parse().ok()?;
    let (sign, mantissa) = match mantissa.strip_prefix('-') {
        Some(rest) => ("-", rest),
        None => ("", mantissa),
    };
    let digits: String = mantissa.chars().filter(|c| *c != '.').collect();
    let point = exponent + 1;
    let length = digits.len() as i32;
    let body = if point > 16 || point <= -4 {
        let (head, rest) = digits.split_at(1);
        let dot = if rest.is_empty() { "" } else { "." };
        let power = if exponent < 0 { '-' } else { '+' };
        format!("{head}{dot}{rest}e{power}{:02}", exponent.abs())
    } else if point <= 0 {
        format!("0.{}{digits}", "0".repeat((-point) as usize))
    } else if point >= length {
        format!("{digits}{}.0", "0".repeat((point - length) as usize))
    } else {
        let (whole, fraction) = digits.split_at(point as usize);
        format!("{whole}.{fraction}")
    };
    Some(format!("{sign}{body}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_float_is_laid_out_as_python_s_repr() {
        for (value, want) in [
            (1.0, "1.0"),
            (-1.5, "-1.5"),
            (0.1, "0.1"),
            (1793500123.456, "1793500123.456"),
            (1e15, "1000000000000000.0"),
            (1e16, "1e+16"),
            (1.5e16, "1.5e+16"),
            (9999999999999998.0, "9999999999999998.0"),
            (0.0001, "0.0001"),
            (0.00001, "1e-05"),
            (1.5e-7, "1.5e-07"),
            (1e100, "1e+100"),
            (1e-100, "1e-100"),
            (0.0, "0.0"),
            (-0.0, "-0.0"),
            (5e-324, "5e-324"),
            (1.7976931348623157e308, "1.7976931348623157e+308"),
        ] {
            assert_eq!(float_repr(value).as_deref(), Some(want));
        }
        assert_eq!(float_repr(f64::INFINITY), None);
        assert_eq!(float_repr(f64::NAN), None);
    }

    #[test]
    fn stored_json_reads_back_as_python_s_dumps() {
        for (given, want) in [
            (
                r#"{"z":1,"a":[1,2,{"b":null}]}"#,
                r#"{"z": 1, "a": [1, 2, {"b": null}]}"#,
            ),
            (r#"{"z":1,"a":2,"z":3}"#, r#"{"z": 3, "a": 2}"#),
            (r#"{"a":1,"a":2}"#, r#"{"a": 2}"#),
            (r#"[1.10,1E2,-0,-0.0,1e400]"#, ""),
            (r#"[1.10,1E2,-0,-0.0]"#, "[1.1, 100.0, 0, -0.0]"),
            (
                "\"\\ud83d\\ude00\\ud800\\/é\\u00E9\\u0041\\u000a\\u007f\"",
                "\"\\ud83d\\ude00\\ud800/\\u00e9\\u00e9A\\n\\u007f\"",
            ),
            (" [ ] ", "[]"),
            ("{ }", "{}"),
        ] {
            let got = python_text(given);
            if want.is_empty() {
                assert_eq!(got, None, "{given}");
            } else {
                assert_eq!(got.as_deref(), Some(want), "{given}");
            }
        }
        assert_eq!(python_text("[1,]"), None);
        assert_eq!(python_text("01"), None);
        assert_eq!(python_text("\"a\nb\""), None);
        assert_eq!(python_text(&"[".repeat(200)), None);
        assert_eq!(python_text(&"9".repeat(4301)), None);
        assert!(python_text(&"9".repeat(4300)).is_some());
    }

    struct NoRecord;

    impl RecordReader for NoRecord {
        fn read_scope(
            &self,
            _class: ReadClass,
        ) -> Result<Box<dyn mentis_record::ReadScope>, mentis_record::RecordError> {
            Err(mentis_record::RecordError::ScopeExpired)
        }

        fn corpus_id(&self) -> &str {
            ""
        }
    }

    fn map(value: Value) -> Map<String, Value> {
        value.as_object().unwrap().clone()
    }

    /// Neither reaches the record: the door's own answers, with no read behind them.
    #[test]
    fn what_only_the_door_says_needs_no_record() {
        let body = |op: &str, args: Value| match read(op, &map(args), &NoRecord, 0.0) {
            Read::Body(body) => String::from_utf8(body).unwrap(),
            Read::NotOwned => panic!("{op}: forwarded"),
        };
        assert_eq!(
            body("history", serde_json::json!({"since": "x"})),
            "{\"refused\": true, \"asked\": \"history\", \"why_not\": \"`since` reads what changed \
             in a response set: name the set with `set`\"}"
        );
        assert_eq!(
            body("owner_decisions", serde_json::json!({})),
            "{\"refused\": true, \"asked\": \"owner_decisions\", \"why_not\": \"owner_decisions \
             needs `conversation`, a Conversation's ent-... id (`orient` lists them)\"}"
        );
    }

    #[test]
    fn a_failed_read_and_an_unknown_op_forward() {
        let empty = Map::new();
        for op in MOVED {
            let args = if op == "resolve" {
                map(serde_json::json!({"ref": "x"}))
            } else if op == "owner_decisions" {
                map(serde_json::json!({"conversation": "x"}))
            } else {
                empty.clone()
            };
            assert_eq!(read(op, &args, &NoRecord, 0.0), Read::NotOwned, "{op}");
        }
        assert_eq!(read("find", &empty, &NoRecord, 0.0), Read::NotOwned);
    }
}
