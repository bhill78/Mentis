//! What Python's two run registries look like from here, and how they join a durable read. The
//! fields are `/private/live`'s (`docs/rust/R4-R6-live-fields.md`); holding them and judging their
//! age is the front's. An op takes an [`Overlay`] in its `Args` and never reads a snapshot itself.
//!
//! **Nothing here is authority or a write decision.** Every "no" is [`OpError::NotOwned`], which
//! forwards the request to Python.

use std::collections::BTreeMap;
use std::fmt;
use std::marker::PhantomData;
use std::sync::Arc;

use mentis_record::{Position, ReadScope};
use serde::de::{Deserializer, MapAccess, Visitor};
use serde::ser::SerializeMap;
use serde::{Deserialize, Serialize, Serializer};

use crate::expectation_states::{ExpectationState, ExpectationStates, ExpectationStatesArgs};
use crate::stored::Stored;
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest};

/// One `Conversations.active_execution_rows` row: a live handle, in `Execution`'s six named members.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct ActiveExecution {
    pub reference: String,
    pub participant: String,
    pub conversation: Option<String>,
    pub runtime: Option<String>,
    pub persona: Option<String>,
    pub for_expectation: Option<String>,
}

/// `Some` even for a `null`, so a member Python sent as `null` stays apart from one it didn't send.
fn present<'de, D: Deserializer<'de>>(from: D) -> Result<Option<Stored>, D::Error> {
    Stored::deserialize(from).map(Some)
}

/// One `MentisService.run_observations` value. What a member says is Python's and is handed on as
/// it came, so only the members a read compares are decoded.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RunObservation {
    pub run: String,
    pub instance: String,
    pub opened_at: f64,
    pub performing_since: Option<f64>,
    pub last_event: Stored,
    pub ended_at: Option<f64>,
    pub stop: Stored,
    pub outcome: Stored,
    /// Absent until the run has ended.
    #[serde(
        default,
        deserialize_with = "present",
        skip_serializing_if = "Option::is_none"
    )]
    pub consent_applied: Option<Stored>,
    /// Absent until the run has ended.
    #[serde(
        default,
        deserialize_with = "present",
        skip_serializing_if = "Option::is_none"
    )]
    pub tooling: Option<Stored>,
    pub permission: Stored,
    pub permissions: Vec<Stored>,
    pub activity: Option<String>,
    pub activity_at: Option<f64>,
    /// Whether MARS's `running()` holds this run's instance.
    pub running: bool,
}

/// `run_observations`: the map by run, in Python's order, which a sorted map wouldn't keep.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct RunObservations(pub Vec<RunObservation>);

impl RunObservations {
    pub fn get(&self, run: &str) -> Option<&RunObservation> {
        self.0.iter().find(|row| row.run == run)
    }
}

impl Serialize for RunObservations {
    fn serialize<S: Serializer>(&self, to: S) -> Result<S::Ok, S::Error> {
        let mut map = to.serialize_map(Some(self.0.len()))?;
        for row in &self.0 {
            map.serialize_entry(&row.run, row)?;
        }
        map.end()
    }
}

impl<'de> Deserialize<'de> for RunObservations {
    fn deserialize<D: Deserializer<'de>>(from: D) -> Result<RunObservations, D::Error> {
        struct Rows;
        impl<'de> Visitor<'de> for Rows {
            type Value = RunObservations;

            fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str("a map of runs")
            }

            fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<RunObservations, A::Error> {
                let mut rows = Vec::new();
                while let Some((_, row)) = map.next_entry::<String, RunObservation>()? {
                    rows.push(row);
                }
                Ok(RunObservations(rows))
            }
        }
        from.deserialize_map(Rows)
    }
}

/// Whether a poll sampled at `marker` is before a read at `read`: **any** component of the read is
/// further on. `Position` is three independent maxima and has no ordering of its own.
fn poll_is_before(marker: Position, read: Position) -> bool {
    read.entry > marker.entry
        || read.operational > marker.operational
        || read.delivery > marker.delivery
}

fn forward(why: &str) -> OpError {
    OpError::NotOwned { why: why.into() }
}

/// One fresh snapshot's two fields, and where the record stood just before it was asked for.
///
/// **Having one means the snapshot is fresh:** the front gives none otherwise, so stale and
/// unavailable reads forward before they get here. What remains to judge is per read: whether the
/// field is present, and whether the poll is coherent with that read's durable position.
///
/// Its `Debug` says which fields are there and where the marker is, and never what they hold. There
/// is no `PartialEq`: comparing against a guess would read the lists without a coherence decision.
///
/// There is deliberately no callback surface on which a static or panic hook can receive an
/// unchecked list. The old static-exfiltration consumer no longer has a method to call:
///
/// ```compile_fail,E0599
/// # use mentis_ops::overlay::{ActiveExecution, Overlay};
/// # use std::sync::Mutex;
/// static OUT: Mutex<Vec<ActiveExecution>> = Mutex::new(Vec::new());
/// # fn raw(overlay: &Overlay, position: mentis_record::Position) {
/// let _ = overlay.work_out(position, 0usize, |_, live| {
///     *OUT.lock().unwrap() = live.active_executions()?.to_vec();
///     Ok(None)
/// });
/// # }
/// ```
///
/// The panic-hook consumer is absent for the same reason:
///
/// ```compile_fail,E0599
/// # use mentis_ops::overlay::Overlay;
/// # fn raw(overlay: &Overlay, position: mentis_record::Position) {
/// let _ = overlay.work_out(position, 0usize, |_, live| {
///     std::panic::panic_any(live.active_executions()?.to_vec())
/// });
/// # }
/// ```
///
/// The redacted wrapper itself remains non-comparable:
///
/// ```compile_fail,E0369
/// # use mentis_ops::overlay::Overlay;
/// # fn raw(left: &Overlay, right: &Overlay) {
/// let _ = left == right;
/// # }
/// ```
#[derive(Clone, Default)]
pub struct Overlay {
    active: Option<Arc<Vec<ActiveExecution>>>,
    runs: Option<Arc<RunObservations>>,
    marker: Option<Position>,
}

impl Overlay {
    /// Crate-boundary decoder hook for `mentis-server::live`. Route code should obtain an
    /// `Overlay` from the front's `Snapshots`; this remains public only because decoding and read
    /// operations are deliberately separate crates. A caller can forge `marker`, which is a stated
    /// safe-code limit of the contract.
    #[doc(hidden)]
    pub fn from_decoded_poll_for_server(
        active: Option<Arc<Vec<ActiveExecution>>>,
        runs: Option<Arc<RunObservations>>,
        marker: Option<Position>,
    ) -> Self {
        Self {
            active,
            runs,
            marker,
        }
    }

    fn active_field(&self) -> Result<&[ActiveExecution], OpError> {
        self.active
            .as_deref()
            .map(Vec::as_slice)
            .ok_or_else(|| forward("no active_executions in this snapshot"))
    }

    fn runs_field(&self) -> Result<&RunObservations, OpError> {
        self.runs
            .as_deref()
            .ok_or_else(|| forward("no run_observations in this snapshot"))
    }

    fn require_coherent(&self, read: &ReadToken<'_>) -> Result<(), OpError> {
        if self.coherent_with(read) {
            Ok(())
        } else {
            Err(forward("this poll is before the durable read"))
        }
    }

    /// The live handles, for a read at `read` whose answer shows them, such as `/api/activity` and
    /// the `RUNNING` lines. Forwards if the field was omitted or the poll isn't coherent with `read`.
    pub fn active_executions(&self, read: &ReadToken<'_>) -> Result<&[ActiveExecution], OpError> {
        let active = self.active_field()?;
        self.require_coherent(read)?;
        Ok(active)
    }

    /// The held runs, as [`Overlay::active_executions`] gives the handles.
    pub fn run_observations(&self, read: &ReadToken<'_>) -> Result<&RunObservations, OpError> {
        let runs = self.runs_field()?;
        self.require_coherent(read)?;
        Ok(runs)
    }

    /// Whether this poll can speak for a read at `read`: it has a marker, and isn't before it.
    fn coherent_with(&self, read: &ReadToken<'_>) -> bool {
        self.marker
            .is_some_and(|marker| !poll_is_before(marker, read.position))
    }

    /// `/api/conversations`' fixed comparison: one count per durable Conversation row. A changed
    /// answer needs a coherent poll; an unchanged answer is the durable map itself.
    ///
    /// ```
    /// use mentis_ops::OpError;
    /// use mentis_ops::overlay::Overlay;
    /// use mentis_record::Position;
    ///
    /// # use std::collections::BTreeMap;
    /// # use mentis_ops::overlay::ReadToken;
    /// fn counts(
    ///     overlay: &mentis_ops::overlay::Overlay,
    ///     read: &ReadToken<'_>,
    ///     durable: BTreeMap<String, usize>,
    /// ) -> Result<BTreeMap<String, usize>, mentis_ops::OpError>
    /// {
    ///     overlay.conversation_counts(read, durable)
    /// }
    /// ```
    pub fn conversation_counts(
        &self,
        read: &ReadToken<'_>,
        durable: BTreeMap<String, usize>,
    ) -> Result<BTreeMap<String, usize>, OpError> {
        let mut changed = durable.clone();
        changed.values_mut().for_each(|count| *count = 0);
        for execution in self.active_field()? {
            if let Some(count) = execution
                .conversation
                .as_ref()
                .and_then(|conversation| changed.get_mut(conversation))
            {
                *count += 1;
            }
        }
        if changed == durable {
            Ok(durable)
        } else {
            self.require_coherent(read)?;
            Ok(changed)
        }
    }

    /// `_live`'s fixed compare-first step. The durable read supplies its open runs and the worker
    /// keys already in its answer. `true` means the caller may now obtain the coherent lists and
    /// add aliases and other durable display fields; `false` is the unchanged durable answer.
    pub fn live_workers_changed(
        &self,
        read: &ReadToken<'_>,
        open_runs: &[OpenRun],
        durable: &LiveWorkers,
    ) -> Result<bool, OpError> {
        let runs = self.runs_field()?;
        let mut changed = LiveWorkers::new();
        for open in open_runs {
            if runs
                .get(&open.run)
                .is_some_and(|held| held.ended_at.is_none())
            {
                changed
                    .entry(open.conversation.clone())
                    .or_default()
                    .push((Some(open.run.clone()), open.participant.clone()));
            }
        }
        // Python fixes this set before it walks active executions. Two uncovered executions for
        // the same participant therefore remain two rows; the first must not cover the second.
        let covered: std::collections::BTreeSet<_> = changed
            .iter()
            .flat_map(|(conversation, workers)| {
                workers
                    .iter()
                    .map(move |worker| (conversation.clone(), worker.1.clone()))
            })
            .collect();
        for execution in self.active_field()? {
            let conversation = execution.conversation.clone().unwrap_or_default();
            if !covered.contains(&(conversation.clone(), execution.participant.clone())) {
                changed
                    .entry(conversation)
                    .or_default()
                    .push((None, execution.participant.clone()));
            }
        }
        if changed == *durable {
            Ok(false)
        } else {
            self.require_coherent(read)?;
            Ok(true)
        }
    }

    /// `expectation_state`'s rule, `conversation/__init__.py:3732-3738`: a handle naming this
    /// expectation, or one naming none whose carrier and Conversation are this one's. `state` is
    /// read first inside the op and `read` is then minted from that same still-held scope.
    pub fn live_execution(
        &self,
        state: &ExpectationState,
        read: &ReadToken<'_>,
    ) -> Result<LiveExecution, OpError> {
        let responder = state.expected_of.as_deref().filter(|who| !who.is_empty());
        let mut added: Vec<&str> = Vec::new();
        for e in self.active_field()? {
            let exact = e.for_expectation.as_deref() == Some(state.expectation.as_str());
            let fallback = e.for_expectation.is_none()
                && responder == Some(e.participant.as_str())
                && e.conversation == state.conversation;
            if (exact || fallback) && !state.durable_open.contains(&e.reference) {
                added.push(&e.reference);
            }
        }
        let mut refs = state.durable_open.clone();
        refs.extend(added.iter().map(|id| (*id).to_owned()));
        refs.sort();
        refs.dedup();
        Ok(LiveExecution {
            added: !added.is_empty(),
            durably_open: !state.durable_open.is_empty(),
            coherent: self.coherent_with(read),
            refs,
        })
    }
}

/// One record-owned scope's position, usable only while that scope is borrowed. Its fields are
/// private, it has no public constructor, and it is not serializable or constructible from the
/// public `ReadAnswer::as_of`.
///
/// A public `Position` is not a token:
///
/// ```compile_fail,E0308
/// # use mentis_ops::overlay::Overlay;
/// # fn raw(overlay: &Overlay, position: mentis_record::Position) {
/// let _ = overlay.active_executions(&position);
/// # }
/// ```
///
/// Nor is there a constructor that turns one into a token:
///
/// ```compile_fail,E0599
/// # use mentis_ops::overlay::ReadToken;
/// # fn raw(position: mentis_record::Position) {
/// let _ = ReadToken::new(position);
/// # }
/// ```
///
/// Nor a conversion from a public position:
///
/// ```compile_fail,E0277
/// # use mentis_ops::overlay::ReadToken;
/// # fn raw(position: mentis_record::Position) {
/// let _: ReadToken<'_> = position.into();
/// # }
/// ```
///
/// Even code handed a real minting function cannot make its borrow outlive the scope:
///
/// ```compile_fail,E0521
/// # use mentis_ops::ReadScope;
/// # use mentis_ops::overlay::ReadToken;
/// fn needs_static(_: ReadToken<'static>) {}
/// fn raw(
///     scope: &mut dyn ReadScope,
///     mint: for<'a> fn(&'a mut dyn ReadScope) -> ReadToken<'a>,
/// ) {
///     needs_static(mint(scope));
/// }
/// ```
pub struct ReadToken<'scope> {
    position: Position,
    _scope: PhantomData<fn(&'scope mut dyn ReadScope) -> &'scope mut dyn ReadScope>,
}

/// Minted only inside `mentis-ops`, where a [`ReadOp`](crate::ReadOp) has the real scope in hand.
/// Server route code cannot call this or construct a token.
pub(crate) fn read_token<'scope>(scope: &'scope mut dyn ReadScope) -> ReadToken<'scope> {
    ReadToken {
        position: scope.position(),
        _scope: PhantomData,
    }
}

// This uses the real minter, not a signature copied into a doctest. Invariance above makes an
// accidentally `ReadToken<'static>` return fail this assignment (M10).
const _: for<'scope> fn(&'scope mut dyn ReadScope) -> ReadToken<'scope> = read_token;

/// One durably open run used by `_live`'s comparison.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OpenRun {
    pub run: String,
    pub conversation: String,
    pub participant: String,
}

/// `_live`'s comparison-only shape: Conversation to `(run, participant)`, with `None` for an
/// execution not covered by a held open run.
pub type LiveWorkers = BTreeMap<String, Vec<(Option<String>, String)>>;

/// One of the fixed live-snapshot projections. This is the shared R4.1 seam operation: it mints
/// the coherence token from the same real scope that supplies the durable position. Later route
/// ops may move their durable queries into dedicated operations; they must keep this order.
#[derive(Clone)]
pub enum LiveProjection {
    ActiveCount,
    RunCount,
    ConversationCounts(BTreeMap<String, usize>),
    LiveWorkersChanged {
        open_runs: Vec<OpenRun>,
        durable: LiveWorkers,
    },
    ExecutionBool {
        expectation: String,
    },
    ExecutionRefs {
        expectation: String,
    },
}

#[derive(Clone)]
pub struct LiveSnapshotArgs {
    pub overlay: Overlay,
    pub projection: LiveProjection,
}

/// A bounded, serializable result rather than either decoded live list.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LiveProjectionResult {
    Count(usize),
    ConversationCounts(BTreeMap<String, usize>),
    Changed(bool),
    Bool(bool),
    Refs(Vec<String>),
}

/// Runs a fixed snapshot projection against a token minted from `scope` by the operation itself.
pub struct LiveSnapshotRead;

impl ReadOp for LiveSnapshotRead {
    type Args = LiveSnapshotArgs;
    type Row = LiveProjectionResult;

    const NAME: &'static str = "live-snapshot";
    const BUDGET: Budget = ExpectationStates::BUDGET;

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Self::Args>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let execution = match &request.args.projection {
            LiveProjection::ExecutionBool { expectation }
            | LiveProjection::ExecutionRefs { expectation } => {
                let asked = ReadRequest {
                    args: ExpectationStatesArgs {
                        ids: vec![expectation.clone()],
                    },
                    cursor: None,
                    limit: None,
                    deadline: request.deadline,
                };
                let mut rows = ExpectationStates.read(scope, &asked)?.rows;
                Some(rows.pop().ok_or_else(|| OpError::NotFound {
                    what: expectation.clone(),
                })?)
            }
            _ => None,
        };

        let read = read_token(scope);
        let overlay = &request.args.overlay;
        let row = match &request.args.projection {
            LiveProjection::ActiveCount => {
                LiveProjectionResult::Count(overlay.active_executions(&read)?.len())
            }
            LiveProjection::RunCount => {
                LiveProjectionResult::Count(overlay.run_observations(&read)?.0.len())
            }
            LiveProjection::ConversationCounts(durable) => {
                LiveProjectionResult::ConversationCounts(
                    overlay.conversation_counts(&read, durable.clone())?,
                )
            }
            LiveProjection::LiveWorkersChanged { open_runs, durable } => {
                LiveProjectionResult::Changed(
                    overlay.live_workers_changed(&read, open_runs, durable)?,
                )
            }
            LiveProjection::ExecutionBool { .. } => LiveProjectionResult::Bool(
                overlay
                    .live_execution(execution.as_ref().unwrap(), &read)?
                    .as_bool()?,
            ),
            LiveProjection::ExecutionRefs { .. } => LiveProjectionResult::Refs(
                overlay
                    .live_execution(execution.as_ref().unwrap(), &read)?
                    .refs()?
                    .to_vec(),
            ),
        };
        Ok(ReadAnswer {
            rows: vec![row],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

impl fmt::Debug for Overlay {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Overlay")
            .field("has_active_executions", &self.active.is_some())
            .field("has_run_observations", &self.runs.is_some())
            .field("marker", &self.marker)
            .finish()
    }
}

/// Python's raw `live_execution` for one expectation: the sorted union of durable and overlay
/// references. There is no way
/// to get at it without saying which answer it is for, because the two forward differently. So its
/// `Debug` says nothing of what it holds, and there is no `PartialEq` to compare it by.
///
/// ```compile_fail,E0369
/// # use mentis_ops::overlay::LiveExecution;
/// # fn raw(left: &LiveExecution, right: &LiveExecution) {
/// let _ = left == right;
/// # }
/// ```
#[derive(Clone)]
pub struct LiveExecution {
    refs: Vec<String>,
    /// The overlay holds a reference the record doesn't.
    added: bool,
    durably_open: bool,
    coherent: bool,
}

impl LiveExecution {
    /// `bool(union)`, what `_expectation_view` emits: Turn, thread, decision and intake views. A run
    /// the record holds open is true whatever the overlay adds, so only an overlay that alone makes
    /// it true has to be coherent.
    pub fn as_bool(&self) -> Result<bool, OpError> {
        if self.added && !self.durably_open && !self.coherent {
            return Err(forward("only an older poll says this expectation is live"));
        }
        Ok(!self.refs.is_empty())
    }

    /// The raw sorted list, for full Conversation's `owed` rows and the POST `expect` answer. A
    /// normal running dispatch has two references here, so any reference the overlay adds has to be
    /// coherent.
    pub fn refs(&self) -> Result<&[String], OpError> {
        if self.added && !self.coherent {
            return Err(forward("this poll is before the durable read"));
        }
        Ok(&self.refs)
    }
}

impl fmt::Debug for LiveExecution {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("LiveExecution").finish_non_exhaustive()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::expectation_states::Assigned;
    use mentis_record::{Flow, Param, RecordError, Row};

    const AT: Position = Position {
        entry: 5,
        operational: 5,
        delivery: 5,
    };

    fn token(at: Position) -> ReadToken<'static> {
        ReadToken {
            position: at,
            _scope: PhantomData,
        }
    }

    fn state(durable: &[&str]) -> ExpectationState {
        ExpectationState {
            expectation: "opr-e".into(),
            turn: None,
            conversation: Some("ent-c".into()),
            expects: Stored::null(),
            requires: Vec::new(),
            options: Stored::null(),
            material: Vec::new(),
            because: None,
            recorded_by: None,
            requested_by: None,
            expected_of: Some("ent-p".into()),
            assigned: Assigned {
                carrier: Some("ent-p".into()),
                by: None,
                at: None,
                assignment: None,
                history: Vec::new(),
            },
            unassigned: false,
            response_present: false,
            satisfied_by: Vec::new(),
            withdrawn: None,
            lapsed: None,
            replies_from_expected: Vec::new(),
            durable_open: durable.iter().map(|id| (*id).to_owned()).collect(),
            failures: Vec::new(),
            delegations: Vec::new(),
            latest_activity: None,
            input: None,
            form: None,
            index: None,
            question: None,
            answer: None,
        }
    }

    fn handle(reference: &str, who: &str, where_: &str, names: Option<&str>) -> ActiveExecution {
        ActiveExecution {
            reference: reference.into(),
            participant: who.into(),
            conversation: Some(where_.into()),
            runtime: None,
            persona: None,
            for_expectation: names.map(str::to_owned),
        }
    }

    fn observation(run: &str, ended_at: Option<f64>) -> RunObservation {
        RunObservation {
            run: run.into(),
            instance: "inst".into(),
            opened_at: 1.0,
            performing_since: None,
            last_event: Stored::null(),
            ended_at,
            stop: Stored::null(),
            outcome: Stored::null(),
            consent_applied: None,
            tooling: None,
            permission: Stored::null(),
            permissions: Vec::new(),
            activity: None,
            activity_at: None,
            running: true,
        }
    }

    fn both(marker: Option<Position>) -> Overlay {
        Overlay::from_decoded_poll_for_server(
            Some(Arc::new(vec![handle("x", "ent-p", "ent-c", Some("opr-e"))])),
            Some(Arc::new(RunObservations::default())),
            marker,
        )
    }

    fn incoherent() -> [Overlay; 5] {
        [
            both(None),
            both(Some(Position { entry: 4, ..AT })),
            both(Some(Position {
                operational: 4,
                ..AT
            })),
            both(Some(Position { delivery: 4, ..AT })),
            both(Some(Position {
                entry: 9,
                operational: 4,
                delivery: 9,
            })),
        ]
    }

    fn is_forwarded<T: fmt::Debug>(got: Result<T, OpError>) -> bool {
        matches!(got, Err(OpError::NotOwned { .. }))
    }

    struct Scope(Position);

    impl ReadScope for Scope {
        fn position(&self) -> Position {
            self.0
        }

        fn query(
            &mut self,
            _sql: &'static str,
            _params: &[Param<'_>],
            _each: &mut dyn FnMut(&dyn Row) -> Result<Flow, RecordError>,
        ) -> Result<(), RecordError> {
            unreachable!()
        }

        fn statements(&self) -> u32 {
            1
        }
    }

    #[test]
    fn the_token_is_minted_from_the_scope_s_position() {
        let mut scope = Scope(AT);
        let read = read_token(&mut scope);
        assert_eq!(read.position, AT);
    }

    #[test]
    fn the_scope_minted_token_decides_coherence() {
        let poll = both(Some(Position { entry: 4, ..AT }));
        let mut current = Scope(AT);
        let current = read_token(&mut current);
        assert!(is_forwarded(poll.active_executions(&current)));

        let mut older = Scope(Position { entry: 4, ..AT });
        let older = read_token(&mut older);
        assert_eq!(poll.active_executions(&older).unwrap().len(), 1);
    }

    #[test]
    fn before_is_any_component_further_on() {
        assert!(!poll_is_before(AT, AT));
        for read in [
            Position { entry: 6, ..AT },
            Position {
                operational: 6,
                ..AT
            },
            Position { delivery: 6, ..AT },
            Position {
                entry: 1,
                operational: 6,
                delivery: 1,
            },
        ] {
            assert!(poll_is_before(AT, read), "{read}");
        }
    }

    #[test]
    fn the_raw_lists_forward_on_every_incoherent_poll_shape() {
        let read = token(AT);
        for poll in incoherent() {
            assert!(is_forwarded(poll.active_executions(&read)), "{poll:?}");
            assert!(is_forwarded(poll.run_observations(&read)), "{poll:?}");
        }
    }

    #[test]
    fn the_raw_lists_answer_a_coherent_poll() {
        let read = token(AT);
        let later = Position {
            entry: 9,
            operational: 9,
            delivery: 9,
        };
        for poll in [both(Some(AT)), both(Some(later))] {
            assert_eq!(poll.active_executions(&read).unwrap().len(), 1);
            assert!(poll.run_observations(&read).unwrap().0.is_empty());
        }
    }

    #[test]
    fn the_conversation_list_count_returns_the_exact_durable_value_or_forwards() {
        let read = token(AT);
        let rows = |n| BTreeMap::from([("ent-c".to_owned(), n), ("ent-d".to_owned(), 0)]);
        for poll in incoherent() {
            let durable = rows(1);
            let got = poll.conversation_counts(&read, durable.clone()).unwrap();
            assert_eq!(got, durable);
            assert!(is_forwarded(poll.conversation_counts(&read, rows(0))));
        }
        assert_eq!(
            both(Some(AT)).conversation_counts(&read, rows(0)),
            Ok(rows(1))
        );
    }

    #[test]
    fn an_absent_count_field_forwards_even_when_the_durable_count_is_zero() {
        let read = token(AT);
        let none = Overlay::from_decoded_poll_for_server(None, None, Some(AT));
        assert!(is_forwarded(none.conversation_counts(
            &read,
            BTreeMap::from([("ent-c".to_owned(), 0)])
        )));
    }

    #[test]
    fn fluid_live_compare_first_covers_both_fields_and_every_poll_shape() {
        let read = token(AT);
        let poll_at = |marker| {
            Overlay::from_decoded_poll_for_server(
                Some(Arc::new(vec![handle("x", "ent-q", "ent-c", None)])),
                Some(Arc::new(RunObservations(vec![
                    observation("opr-going", None),
                    observation("opr-ended", Some(2.0)),
                ]))),
                marker,
            )
        };
        let open = [
            OpenRun {
                run: "opr-going".into(),
                conversation: "ent-d".into(),
                participant: "ent-p".into(),
            },
            OpenRun {
                run: "opr-ended".into(),
                conversation: "ent-d".into(),
                participant: "ent-p".into(),
            },
        ];
        let same = LiveWorkers::from([
            ("ent-c".to_owned(), vec![(None, "ent-q".to_owned())]),
            (
                "ent-d".to_owned(),
                vec![(Some("opr-going".to_owned()), "ent-p".to_owned())],
            ),
        ]);
        for poll in [
            poll_at(None),
            poll_at(Some(Position { entry: 4, ..AT })),
            poll_at(Some(Position {
                operational: 4,
                ..AT
            })),
            poll_at(Some(Position { delivery: 4, ..AT })),
        ] {
            assert_eq!(poll.live_workers_changed(&read, &open, &same), Ok(false));
            assert!(is_forwarded(poll.live_workers_changed(
                &read,
                &open,
                &LiveWorkers::new()
            )));
        }
        let coherent = poll_at(Some(AT));
        assert_eq!(
            coherent.live_workers_changed(&read, &open, &LiveWorkers::new()),
            Ok(true)
        );
        assert_eq!(coherent.active_executions(&read).unwrap().len(), 1);
        assert_eq!(coherent.run_observations(&read).unwrap().0.len(), 2);

        let no_active = Overlay::from_decoded_poll_for_server(
            None,
            Some(Arc::new(RunObservations::default())),
            Some(AT),
        );
        assert!(is_forwarded(
            no_active.live_workers_changed(&read, &open, &same)
        ));
        let no_runs =
            Overlay::from_decoded_poll_for_server(Some(Arc::new(Vec::new())), None, Some(AT));
        assert!(is_forwarded(
            no_runs.live_workers_changed(&read, &open, &same)
        ));
    }

    #[test]
    fn fluid_live_keeps_duplicate_uncovered_executions_as_python_does() {
        let duplicate = handle("x", "ent-p", "ent-c", None);
        let poll = Overlay::from_decoded_poll_for_server(
            Some(Arc::new(vec![duplicate.clone(), duplicate])),
            Some(Arc::new(RunObservations::default())),
            Some(AT),
        );
        let read = token(AT);
        let python = LiveWorkers::from([(
            "ent-c".to_owned(),
            vec![(None, "ent-p".to_owned()), (None, "ent-p".to_owned())],
        )]);
        assert_eq!(poll.live_workers_changed(&read, &[], &python), Ok(false));
    }

    #[test]
    fn live_execution_uses_exact_and_fallback_rules() {
        let read = token(AT);
        let poll = Overlay::from_decoded_poll_for_server(
            Some(Arc::new(vec![
                handle("exact", "other", "elsewhere", Some("opr-e")),
                handle("fallback", "ent-p", "ent-c", None),
                handle("wrong-person", "other", "ent-c", None),
                handle("wrong-conversation", "ent-p", "ent-d", None),
                handle("wrong-expectation", "ent-p", "ent-c", Some("opr-x")),
            ])),
            None,
            Some(AT),
        );
        assert_eq!(
            poll.live_execution(&state(&[]), &read)
                .unwrap()
                .refs()
                .unwrap(),
            ["exact", "fallback"]
        );
    }

    #[test]
    fn live_execution_boolean_and_refs_forward_only_when_their_answer_changes() {
        let read = token(AT);
        for poll in incoherent() {
            let durable = poll.live_execution(&state(&["durable"]), &read).unwrap();
            assert_eq!(durable.as_bool(), Ok(true));
            assert!(is_forwarded(durable.refs()));

            let overlay_only = poll.live_execution(&state(&[]), &read).unwrap();
            assert!(is_forwarded(overlay_only.as_bool()));
            assert!(is_forwarded(overlay_only.refs()));
        }
        let coherent = both(Some(AT));
        let live = coherent.live_execution(&state(&[]), &read).unwrap();
        assert_eq!(live.as_bool(), Ok(true));
        assert_eq!(live.refs().unwrap(), ["x"]);
    }

    #[test]
    fn an_absent_active_field_forwards_every_path_that_needs_it() {
        let read = token(AT);
        let none = Overlay::from_decoded_poll_for_server(
            None,
            Some(Arc::new(RunObservations::default())),
            Some(AT),
        );
        assert!(is_forwarded(none.active_executions(&read)));
        assert!(is_forwarded(none.live_execution(&state(&[]), &read)));
        assert!(is_forwarded(
            none.conversation_counts(&read, BTreeMap::new())
        ));
    }

    #[test]
    fn debug_says_nothing_of_what_the_lists_and_references_hold() {
        let read = token(AT);
        let poll = Overlay::from_decoded_poll_for_server(
            Some(Arc::new(vec![handle(
                "secret-handle",
                "secret-who",
                "secret-where",
                Some("secret-for"),
            )])),
            Some(Arc::new(RunObservations(vec![observation(
                "secret-run",
                None,
            )]))),
            Some(AT),
        );
        let mut named = state(&["secret-durable"]);
        named.expectation = "secret-for".into();
        let live = poll.live_execution(&named, &read).unwrap();
        let seen = [
            format!("{poll:?}"),
            format!("{poll:#?}"),
            format!("{live:?}"),
            format!("{live:#?}"),
        ];
        for text in seen {
            for secret in [
                "secret-handle",
                "secret-who",
                "secret-where",
                "secret-for",
                "secret-run",
                "secret-durable",
            ] {
                assert!(!text.contains(secret), "{text}");
            }
        }
    }
}
