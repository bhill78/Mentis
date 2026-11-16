#![forbid(unsafe_code)]

//! The one read catalogue. Contract: `docs/rust/contracts/ops.md`.
//!
//! A read is a [`ReadOp`]. Fluid routes, agent reads (R3) and Magnet sources are thin adapters: an
//! adapter parses its request, checks what is its to check, runs one op, and shapes the answer as
//! that route has always shaped it. R2 and R3 build on this signature without talking to each
//! other, so it only gains: new variants of `#[non_exhaustive]` enums and new optional fields.

pub mod acts;
pub mod annotations;
pub mod capabilities;
pub mod changes;
pub mod expectation_states;
pub mod forms;
pub mod governed;
pub mod history;
pub mod kinds;
pub mod lists;
pub mod magnet;
pub mod moved;
pub mod names;
pub mod needs_you;
pub mod overlay;
pub mod owner_decisions;
pub mod pulse;
pub mod pyjson;
pub mod python;
pub mod resolve;
pub mod response_sets;
pub mod set_changes;
pub mod stored;
pub mod topics;
pub mod turn_line;
pub mod views;
pub mod vocabulary;
pub mod window;

// R5.1: references and object reads.
pub mod find;
pub mod object_reads;
pub mod post_search;
pub mod render_report;

use std::fmt;
use std::time::Instant;

use mentis_record::{Flow, Param, Row};
pub use mentis_record::{Id, Position, ReadClass, ReadScope, RecordError};
pub use mentis_rules as rules;

use serde::Serialize;

/// Statements an op may run per call, at each state a statement count varies with. Fixed per call
/// and never per id. Checked against [`ReadScope::statements`] in tests; never at run time.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Budget {
    pub statements: u32,
}

/// An opaque place to continue from. An op makes them and only that op reads them.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(transparent)]
pub struct Cursor(pub String);

/// What an adapter asks of an op.
#[derive(Clone, Debug)]
pub struct ReadRequest<A> {
    /// The op's own arguments, already parsed. Parsing a route's query is the adapter's.
    pub args: A,
    pub cursor: Option<Cursor>,
    /// `None` is the op's default; the op enforces its own maximum.
    pub limit: Option<u32>,
    /// When the caller stops caring. An op past it stops and answers what it has, or
    /// [`OpError::Busy`], rather than running for nobody. [`run`] holds every op to it.
    pub deadline: Instant,
}

/// Something a bounded read did not reach. Silence would read as "nothing there".
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct NotSearched {
    pub what: String,
    pub why: String,
}

/// An op's answer. `rows` is whole: a partial answer says so through `more` and `not_searched`.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ReadAnswer<R> {
    pub rows: Vec<R>,
    /// The scope's position: a route's change cursor is this, never a second look.
    #[serde(serialize_with = "position_as_text")]
    pub as_of: Position,
    pub more: Option<Cursor>,
    pub not_searched: Vec<NotSearched>,
}

pub(crate) fn position_as_text<S: serde::Serializer>(
    at: &Position,
    to: S,
) -> Result<S::Ok, S::Error> {
    to.collect_str(at)
}

/// Why an op gave no answer. What each becomes at a door is in the contract.
#[derive(Clone, Debug, PartialEq, Eq)]
#[non_exhaustive]
pub enum OpError {
    /// **Unknown means forwarded.** A case of this route Rust does not own. Nothing was answered;
    /// the adapter forwards the request to Python unchanged, or 503 with the reason if it can't.
    NotOwned { why: String },
    /// Over the class's cap or past the deadline. Fast, and nothing partial was promised.
    Busy { why: String },
    /// The request itself is wrong, in the words the route has always used.
    BadRequest { why: String },
    /// The thing asked about is not in the record.
    NotFound { what: String },
    /// A read failed. Includes the scope's limit passing.
    Record(RecordError),
}

impl From<RecordError> for OpError {
    fn from(error: RecordError) -> Self {
        match error {
            RecordError::Busy { class } => OpError::Busy {
                why: format!("the {class} readers are all in use"),
            },
            other => OpError::Record(other),
        }
    }
}

impl fmt::Display for OpError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            OpError::NotOwned { why } => write!(f, "not owned here: {why}"),
            OpError::Busy { why } => write!(f, "busy: {why}"),
            OpError::BadRequest { why } => f.write_str(why),
            OpError::NotFound { what } => write!(f, "not found: {what}"),
            OpError::Record(error) => write!(f, "{error}"),
        }
    }
}

impl std::error::Error for OpError {}

/// One read. Implementations hold no lock across a statement or a JS call, keep no memo the answer
/// depends on, never write, never read a live snapshot themselves (a live input is in `Args`) and
/// know nothing of a grant: authority is the door's, before the op runs.
///
/// **Blocking,** like the scope it reads through: the adapter runs it on a blocking thread.
pub trait ReadOp: Send + Sync {
    type Args: Send;
    type Row: Serialize + Send;

    /// Stable, for logs and budgets: `"topics"`, `"posts"`, `"resolve"`.
    const NAME: &'static str;
    /// The most statements one call may run, at any state of the record.
    const BUDGET: Budget;

    /// Whether this op answers over erased content itself (`erasure-design.md` 5). An op that
    /// doesn't is never answered from a row whose content was erased: [`run`] sees the marker go
    /// by and the request goes on to Python, which presents erased posts and Conversations.
    const READS_ERASED: bool = false;

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<Self::Row>, OpError>;
}

/// Whether a value is attested erasure's marker, `{"erased": "<deletion act>"}`, as a body,
/// detail or material holds it once its content is gone.
pub fn is_erased(value: mentis_record::Value<'_>) -> bool {
    let mentis_record::Value::Text(held) = value else {
        return false;
    };
    let trimmed = held.trim_ascii_start();
    if !trimmed.starts_with(b"{\"erased\"") {
        return false;
    }
    std::str::from_utf8(held)
        .ok()
        .and_then(|text| serde_json::from_str::<serde_json::Value>(text).ok())
        .and_then(|value| {
            let members = value.as_object()?;
            (members.len() == 1 && members.get("erased")?.is_string()).then_some(())
        })
        .is_some()
}

/// A scope that goes no further once its request's deadline has passed: no statement starts, and a
/// running one stops at its next row. What it can't stop is a statement between two rows, which
/// only the scope's own limit ends. It also notes whether any row it gave held erased content.
struct UntilDeadline<'a> {
    scope: &'a mut dyn ReadScope,
    deadline: Instant,
    passed: bool,
    erased_seen: bool,
}

impl ReadScope for UntilDeadline<'_> {
    fn position(&self) -> Position {
        self.scope.position()
    }

    fn query(
        &mut self,
        sql: &'static str,
        params: &[Param<'_>],
        each: &mut dyn FnMut(&dyn Row) -> Result<Flow, RecordError>,
    ) -> Result<(), RecordError> {
        let deadline = self.deadline;
        let passed = &mut self.passed;
        let erased_seen = &mut self.erased_seen;
        if Instant::now() >= deadline {
            *passed = true;
            return Err(RecordError::ScopeExpired);
        }
        self.scope.query(sql, params, &mut |row| {
            if Instant::now() >= deadline {
                *passed = true;
                return Err(RecordError::ScopeExpired);
            }
            if !*erased_seen {
                for column in 0..row.column_count() {
                    if is_erased(row.value(column)?) {
                        *erased_seen = true;
                        break;
                    }
                }
            }
            each(row)
        })
    }

    fn statements(&self) -> u32 {
        self.scope.statements()
    }
}

fn past_its_deadline<O: ReadOp>() -> OpError {
    OpError::Busy {
        why: format!("{} ran past its deadline", O::NAME),
    }
}

/// The one way an adapter runs an op: a scope from `class`'s pool, the op, the scope released.
/// A busy class answers at once.
///
/// **Past the request's deadline the answer is [`OpError::Busy`], with nothing partial,** because
/// `rows` is whole: on arrival, before a scope is taken; once the scope is open; before any
/// statement; and at any row. An op that has read everything it needs answers, however late, since
/// stopping then saves nobody anything. A statement yielding no rows goes on to the scope's own
/// limit, [`mentis_record::READ_SCOPE_LIMIT`], which is unchanged.
pub fn run<O: ReadOp>(
    op: &O,
    reader: &dyn mentis_record::RecordReader,
    class: ReadClass,
    request: &ReadRequest<O::Args>,
) -> Result<ReadAnswer<O::Row>, OpError> {
    if Instant::now() >= request.deadline {
        return Err(past_its_deadline::<O>());
    }
    let mut scope = reader.read_scope(class)?;
    if Instant::now() >= request.deadline {
        return Err(past_its_deadline::<O>());
    }
    let mut bounded = UntilDeadline {
        scope: scope.as_mut(),
        deadline: request.deadline,
        passed: false,
        erased_seen: false,
    };
    let answer = op.read(&mut bounded, request);
    if bounded.passed && answer.is_err() {
        return Err(past_its_deadline::<O>());
    }
    if bounded.erased_seen && !O::READS_ERASED {
        return Err(OpError::NotOwned {
            why: format!("{} read erased content, which Python presents", O::NAME),
        });
    }
    answer
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_answer_travels_with_its_position_as_text() {
        let answer: ReadAnswer<u8> = ReadAnswer {
            rows: vec![1],
            as_of: Position {
                entry: 1,
                operational: 2,
                delivery: 3,
            },
            more: Some(Cursor("c".into())),
            not_searched: vec![],
        };
        assert_eq!(
            serde_json::to_value(&answer).unwrap(),
            serde_json::json!({"rows": [1], "as_of": "1.2.3", "more": "c", "not_searched": []})
        );
    }

    struct OneColumn;

    impl Row for OneColumn {
        fn column_count(&self) -> usize {
            1
        }

        fn value(&self, _column: usize) -> Result<mentis_record::Value<'_>, RecordError> {
            Ok(mentis_record::Value::Integer(1))
        }
    }

    /// One statement with no end of rows, each taking a millisecond.
    struct Endless;

    impl ReadScope for Endless {
        fn position(&self) -> Position {
            Position {
                entry: 1,
                operational: 2,
                delivery: 3,
            }
        }

        fn query(
            &mut self,
            _sql: &'static str,
            _params: &[Param<'_>],
            each: &mut dyn FnMut(&dyn Row) -> Result<Flow, RecordError>,
        ) -> Result<(), RecordError> {
            while each(&OneColumn)? == Flow::Continue {
                std::thread::sleep(std::time::Duration::from_millis(1));
            }
            Ok(())
        }

        fn statements(&self) -> u32 {
            1
        }
    }

    impl mentis_record::RecordReader for Endless {
        fn read_scope(&self, _class: ReadClass) -> Result<Box<dyn ReadScope>, RecordError> {
            Ok(Box::new(Endless))
        }

        fn corpus_id(&self) -> &str {
            ""
        }
    }

    /// Reads until told to stop, as a long read would. It says what it would have answered, so a
    /// partial answer can't pass for Busy.
    struct ReadsOn;

    impl ReadOp for ReadsOn {
        type Args = ();
        type Row = u64;
        const NAME: &'static str = "reads-on";
        const BUDGET: Budget = Budget { statements: 2 };

        fn read(
            &self,
            scope: &mut dyn ReadScope,
            _request: &ReadRequest<()>,
        ) -> Result<ReadAnswer<u64>, OpError> {
            let mut rows = 0;
            scope.query("SELECT 1", &[], &mut |_| {
                rows += 1;
                Ok(Flow::Continue)
            })?;
            Ok(ReadAnswer {
                rows: vec![rows],
                as_of: scope.position(),
                more: None,
                not_searched: Vec::new(),
            })
        }
    }

    #[test]
    fn a_long_statement_stops_at_the_first_row_past_the_deadline_and_is_busy() {
        let started = Instant::now();
        let asked = ReadRequest {
            args: (),
            cursor: None,
            limit: None,
            deadline: started + std::time::Duration::from_millis(20),
        };
        let got = run(&ReadsOn, &Endless, ReadClass::Foreground, &asked);
        assert_eq!(
            got.unwrap_err(),
            OpError::Busy {
                why: "reads-on ran past its deadline".into()
            }
        );
        assert!(started.elapsed() < std::time::Duration::from_secs(1));
    }

    /// One row of one text column.
    struct Holding(&'static str);

    impl Row for Holding {
        fn column_count(&self) -> usize {
            2
        }

        fn value(&self, column: usize) -> Result<mentis_record::Value<'_>, RecordError> {
            Ok(match column {
                0 => mentis_record::Value::Text(b"ent-1"),
                _ => mentis_record::Value::Text(self.0.as_bytes()),
            })
        }
    }

    impl ReadScope for Holding {
        fn position(&self) -> Position {
            Position::default()
        }

        fn query(
            &mut self,
            _sql: &'static str,
            _params: &[Param<'_>],
            each: &mut dyn FnMut(&dyn Row) -> Result<Flow, RecordError>,
        ) -> Result<(), RecordError> {
            each(&Holding(self.0))?;
            Ok(())
        }

        fn statements(&self) -> u32 {
            1
        }
    }

    impl mentis_record::RecordReader for Holding {
        fn read_scope(&self, _class: ReadClass) -> Result<Box<dyn ReadScope>, RecordError> {
            Ok(Box::new(Holding(self.0)))
        }

        fn corpus_id(&self) -> &str {
            ""
        }
    }

    struct Reads<const ERASED: bool>;

    impl<const ERASED: bool> ReadOp for Reads<ERASED> {
        type Args = ();
        type Row = u64;
        const NAME: &'static str = "reads";
        const BUDGET: Budget = Budget { statements: 1 };
        const READS_ERASED: bool = ERASED;

        fn read(
            &self,
            scope: &mut dyn ReadScope,
            _request: &ReadRequest<()>,
        ) -> Result<ReadAnswer<u64>, OpError> {
            scope.query("SELECT id, body FROM entry", &[], &mut |_| {
                Ok(Flow::Continue)
            })?;
            Ok(ReadAnswer {
                rows: vec![1],
                as_of: scope.position(),
                more: None,
                not_searched: Vec::new(),
            })
        }
    }

    fn asked() -> ReadRequest<()> {
        ReadRequest {
            args: (),
            cursor: None,
            limit: None,
            deadline: Instant::now() + std::time::Duration::from_secs(5),
        }
    }

    #[test]
    fn an_op_that_reads_an_erased_row_goes_on_to_python() {
        for marker in [
            r#"{"erased": "opr-0123456789ab"}"#,
            r#"{"erased":"opr-0123456789ab"}"#,
        ] {
            let got = run(
                &Reads::<false>,
                &Holding(marker),
                ReadClass::Foreground,
                &asked(),
            );
            assert!(matches!(got, Err(OpError::NotOwned { .. })), "{marker}");
            // An op that presents erased rows itself is answered.
            let got = run(
                &Reads::<true>,
                &Holding(marker),
                ReadClass::Foreground,
                &asked(),
            );
            assert_eq!(got.unwrap().rows, [1]);
        }
        for ordinary in [
            r#"{"text": "hello"}"#,
            r#"{"erased": "opr-1", "text": "x"}"#,
            r#"{"erasure": {"rows": 3}}"#,
            r#"{"erased": 1}"#,
            "erased",
        ] {
            let got = run(
                &Reads::<false>,
                &Holding(ordinary),
                ReadClass::Foreground,
                &asked(),
            );
            assert_eq!(got.unwrap().rows, [1], "{ordinary}");
        }
    }

    #[test]
    fn a_busy_record_is_a_busy_op_and_everything_else_stays_a_record_error() {
        assert!(matches!(
            OpError::from(RecordError::Busy { class: "agent" }),
            OpError::Busy { .. }
        ));
        assert_eq!(
            OpError::from(RecordError::ScopeExpired),
            OpError::Record(RecordError::ScopeExpired)
        );
    }
}
