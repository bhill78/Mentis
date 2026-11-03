//! What Python's two run registries look like from here, and how they join a durable read. The
//! fields are `/private/live`'s (`docs/rust/R4-R6-live-fields.md`); holding them and judging their
//! age is the front's. An op takes an [`Overlay`] in its `Args` and never reads a snapshot itself.
//!
//! **Nothing here is authority or a write decision.** Every "no" is [`OpError::NotOwned`], which
//! forwards the request to Python.

use std::collections::BTreeMap;
use std::fmt;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::Arc;

use mentis_record::Position;
use serde::de::{Deserializer, MapAccess, Visitor};
use serde::ser::SerializeMap;
use serde::{Deserialize, Serialize, Serializer};

use crate::OpError;
use crate::expectation_states::ExpectationState;
use crate::stored::Stored;

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
pub fn poll_is_before(marker: Position, read: Position) -> bool {
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
#[derive(Clone, Default)]
pub struct Overlay {
    active: Option<Arc<Vec<ActiveExecution>>>,
    runs: Option<Arc<RunObservations>>,
    marker: Option<Position>,
}

impl Overlay {
    pub fn new(
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

    fn active_field(&self) -> Result<&[ActiveExecution], Absent> {
        self.active.as_deref().map(Vec::as_slice).ok_or(Absent {
            why: "no active_executions in this snapshot",
        })
    }

    fn runs_field(&self) -> Result<&RunObservations, Absent> {
        self.runs.as_deref().ok_or(Absent {
            why: "no run_observations in this snapshot",
        })
    }

    fn require_coherent(&self, read: Position) -> Result<(), OpError> {
        if self.coherent_with(read) {
            Ok(())
        } else {
            Err(forward("this poll is before the durable read"))
        }
    }

    /// The live handles, for a read at `read` whose answer shows them, such as `/api/activity` and
    /// the `RUNNING` lines. Forwards if the field was omitted or the poll isn't coherent with `read`.
    pub fn active_executions(&self, read: Position) -> Result<&[ActiveExecution], OpError> {
        let active = self.active_field()?;
        self.require_coherent(read)?;
        Ok(active)
    }

    /// The held runs, as [`Overlay::active_executions`] gives the handles.
    pub fn run_observations(&self, read: Position) -> Result<&RunObservations, OpError> {
        let runs = self.runs_field()?;
        self.require_coherent(read)?;
        Ok(runs)
    }

    /// Whether this poll can speak for a read at `read`: it has a marker, and isn't before it.
    pub fn coherent_with(&self, read: Position) -> bool {
        self.marker
            .is_some_and(|marker| !poll_is_before(marker, read))
    }

    /// The coherence rule, for a read with a durable answer that the overlay may or may not change,
    /// such as a live count or `_live`. `durable` goes in before the overlay is seen. `compare` sees
    /// the fields whatever the poll, and returns `None` if they make no difference, which answers
    /// exactly `durable`, or `Some(changed)`, which has to be coherent with `read` and otherwise
    /// forwards. An absent field forwards, whichever it was going to return.
    ///
    /// ```
    /// use mentis_ops::OpError;
    /// use mentis_ops::overlay::Overlay;
    /// use mentis_record::Position;
    ///
    /// fn live_count(overlay: &Overlay, read: Position, durable: usize) -> Result<usize, OpError> {
    ///     overlay.work_out(read, durable, |durable, live| {
    ///         let count = live.active_executions()?.len();
    ///         Ok((count != *durable).then_some(count))
    ///     })
    /// }
    /// ```
    ///
    /// A list has nowhere to go on a `None`, which takes no value of the caller's:
    ///
    /// ```compile_fail,E0618
    /// # use mentis_ops::overlay::Overlay;
    /// # fn raw(overlay: &Overlay, read: mentis_record::Position) {
    /// let _ = overlay.work_out(read, 0usize, |_, live| {
    ///     Ok(None(live.active_executions()?.to_vec()))
    /// });
    /// # }
    /// ```
    ///
    /// Nor can a list be the answer, which would be the same route with `Vec::new()` as the durable
    /// value:
    ///
    /// ```compile_fail,E0277
    /// # use mentis_ops::overlay::Overlay;
    /// # fn raw(overlay: &Overlay, read: mentis_record::Position) {
    /// let _ = overlay.work_out(read, Vec::new(), |_, live| {
    ///     Ok(Some(live.active_executions()?.to_vec()))
    /// });
    /// # }
    /// ```
    ///
    /// `compare` is a plain `fn`, so it captures nothing to carry a list out in:
    ///
    /// ```compile_fail,E0308
    /// # use mentis_ops::overlay::Overlay;
    /// # fn raw(overlay: &Overlay, read: mentis_record::Position) {
    /// let mut out = Vec::new();
    /// let _ = overlay.work_out(read, 0usize, |_, live| {
    ///     out = live.active_executions()?.to_vec();
    ///     Ok(None)
    /// });
    /// # }
    /// ```
    ///
    /// The answer has no interior mutability ([`Durable`]), so `compare` can't write a list into it:
    ///
    /// ```compile_fail,E0277
    /// # use mentis_ops::overlay::{ActiveExecution, Overlay};
    /// # use std::cell::RefCell;
    /// # fn raw(overlay: &Overlay, read: mentis_record::Position) {
    /// let held = RefCell::new(Vec::<ActiveExecution>::new());
    /// let _ = overlay.work_out(read, held, |held, live| {
    ///     *held.borrow_mut() = live.active_executions()?.to_vec();
    ///     Ok(None)
    /// });
    /// # }
    /// ```
    ///
    /// ...and only this crate says what is [`Durable`]:
    ///
    /// ```compile_fail,E0277
    /// struct Mine;
    /// impl mentis_ops::overlay::Durable for Mine {}
    /// ```
    ///
    /// The error can't carry one either. [`Absent`] is the only one `compare` can return:
    ///
    /// ```compile_fail,E0308
    /// # use mentis_ops::OpError;
    /// # use mentis_ops::overlay::Overlay;
    /// # fn raw(overlay: &Overlay, read: mentis_record::Position) {
    /// let _ = overlay.work_out(read, 0usize, |_, live| {
    ///     let why = format!("{:?}", live.active_executions()?);
    ///     Err(OpError::NotOwned { why })
    /// });
    /// # }
    /// ```
    ///
    /// ...and nothing out here can make one saying anything else:
    ///
    /// ```compile_fail,E0451
    /// # use mentis_ops::overlay::{Absent, Overlay};
    /// # fn raw(overlay: &Overlay, read: mentis_record::Position) {
    /// let _ = overlay.work_out(read, 0usize, |_, live| {
    ///     let why: &'static str = format!("{:?}", live.active_executions()?).leak();
    ///     Err(Absent { why })
    /// });
    /// # }
    /// ```
    ///
    /// **What this doesn't stop** is in `docs/rust/contracts/live-snapshot.md`: mainly, `compare` is
    /// ordinary code, so statics, files and `unsafe` are in its reach, and whether a call forwards
    /// says whether the overlay made a difference.
    pub fn work_out<A: Durable>(
        &self,
        read: Position,
        durable: A,
        compare: fn(&A, Unsettled<'_>) -> Result<Option<A>, Absent>,
    ) -> Result<A, OpError> {
        let live = Unsettled { overlay: self };
        // A panic's payload is a value `catch_unwind` hands to the caller, so this one stops here.
        let compared = catch_unwind(AssertUnwindSafe(|| compare(&durable, live)));
        let compared = compared.unwrap_or_else(|payload| {
            drop(payload);
            panic!("a work_out comparison panicked");
        })?;
        match compared {
            None => Ok(durable),
            Some(changed) => {
                self.require_coherent(read)?;
                Ok(changed)
            }
        }
    }

    /// `expectation_state`'s rule, `conversation/__init__.py:3732-3738`: a handle naming this
    /// expectation, or one naming none whose carrier and Conversation are this one's. `read` is the
    /// position `state` was read at ([`crate::ReadAnswer::as_of`]).
    pub fn live_execution(
        &self,
        state: &ExpectationState,
        read: Position,
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

impl fmt::Debug for Overlay {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Overlay")
            .field("has_active_executions", &self.active.is_some())
            .field("has_run_observations", &self.runs.is_some())
            .field("marker", &self.marker)
            .finish()
    }
}

/// Keeps [`Durable`] to this crate.
pub(crate) mod sealed {
    pub trait Sealed {}
}

/// What a durable answer can be in [`Overlay::work_out`]. Only this crate adds to it, and only plain
/// owned data: no references, and no interior mutability, which would let `compare` write a list
/// into the answer it is handed and get it back on a `None`. A route's own row type joins with
/// `impl sealed::Sealed for Row {}`, once it holds nothing but these.
pub trait Durable: sealed::Sealed {}

impl<T: sealed::Sealed> Durable for T {}

impl sealed::Sealed for bool {}
impl sealed::Sealed for usize {}
impl sealed::Sealed for u64 {}
impl sealed::Sealed for f64 {}
impl sealed::Sealed for String {}
impl<T: sealed::Sealed> sealed::Sealed for Option<T> {}
impl<T: sealed::Sealed> sealed::Sealed for Vec<T> {}
impl<K: sealed::Sealed, V: sealed::Sealed> sealed::Sealed for BTreeMap<K, V> {}
impl<A: sealed::Sealed, B: sealed::Sealed> sealed::Sealed for (A, B) {}

/// A field [`Unsettled`] was asked for isn't in this snapshot. Forwards. Nothing outside this module
/// can make one, and it says only which field, so it carries nothing out of [`Overlay::work_out`].
#[derive(Clone, Copy, Debug)]
pub struct Absent {
    why: &'static str,
}

impl From<Absent> for OpError {
    fn from(absent: Absent) -> OpError {
        forward(absent.why)
    }
}

/// The two fields inside [`Overlay::work_out`], before anything has said they can be used. Only that
/// call makes one, and what it lends can't outlive the call. An absent field forwards here too.
#[derive(Clone, Copy)]
pub struct Unsettled<'o> {
    overlay: &'o Overlay,
}

impl<'o> Unsettled<'o> {
    pub fn active_executions(self) -> Result<&'o [ActiveExecution], Absent> {
        self.overlay.active_field()
    }

    pub fn run_observations(self) -> Result<&'o RunObservations, Absent> {
        self.overlay.runs_field()
    }
}

impl fmt::Debug for Unsettled<'_> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Unsettled").finish_non_exhaustive()
    }
}

/// Python's raw `live_execution` for one expectation: `sorted(durable ∪ overlay)`. There is no way
/// to get at it without saying which answer it is for, because the two forward differently. So its
/// `Debug` says nothing of what it holds, and there is no `PartialEq` to compare it by.
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

    const AT: Position = Position {
        entry: 5,
        operational: 5,
        delivery: 5,
    };

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

    fn overlay(handles: Vec<ActiveExecution>, marker: Option<Position>) -> Overlay {
        Overlay::new(Some(Arc::new(handles)), None, marker)
    }

    fn is_forwarded<T: fmt::Debug>(got: Result<T, OpError>) -> bool {
        matches!(got, Err(OpError::NotOwned { .. }))
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
            // One behind and one ahead is still before: there is no total order.
            Position {
                entry: 1,
                operational: 6,
                delivery: 1,
            },
        ] {
            assert!(poll_is_before(AT, read), "{read}");
        }
        let behind = Position {
            entry: 1,
            operational: 1,
            delivery: 1,
        };
        assert!(!poll_is_before(AT, behind), "a read behind the poll");
    }

    #[test]
    fn a_handle_counts_by_the_exact_or_fallback_rule_and_no_other() {
        let handles = vec![
            handle("x-exact", "ent-other", "ent-elsewhere", Some("opr-e")),
            handle("x-fallback", "ent-p", "ent-c", None),
            handle("x-other-request", "ent-p", "ent-c", Some("opr-other")),
            handle("x-other-conversation", "ent-p", "ent-elsewhere", None),
            handle("x-other-carrier", "ent-other", "ent-c", None),
        ];
        let live = overlay(handles.clone(), Some(AT))
            .live_execution(&state(&[]), AT)
            .unwrap();
        assert_eq!(live.refs().unwrap(), ["x-exact", "x-fallback"]);

        let mut nobody = state(&[]);
        nobody.expected_of = None;
        let live = overlay(handles, Some(AT))
            .live_execution(&nobody, AT)
            .unwrap();
        assert_eq!(live.refs().unwrap(), ["x-exact"], "no carrier, no fallback");
    }

    #[test]
    fn the_union_is_sorted_and_keeps_each_reference_once() {
        let handles = vec![
            handle("m", "ent-q", "ent-c", Some("opr-e")),
            handle("a", "ent-q", "ent-c", Some("opr-e")),
            handle("z", "ent-q", "ent-c", Some("opr-e")),
        ];
        let live = overlay(handles, Some(AT))
            .live_execution(&state(&["z", "b"]), AT)
            .unwrap();
        assert_eq!(live.refs().unwrap(), ["a", "b", "m", "z"]);
        assert_eq!(live.as_bool(), Ok(true));
    }

    #[test]
    fn the_boolean_and_the_raw_list_forward_differently() {
        let read = Position { entry: 6, ..AT };
        let second = vec![handle("x", "ent-q", "ent-c", Some("opr-e"))];
        for marker in [Some(AT), None] {
            // Durably open, and an older poll adds its second reference: true either way.
            let live = overlay(second.clone(), marker)
                .live_execution(&state(&["i"]), read)
                .unwrap();
            assert_eq!(live.as_bool(), Ok(true));
            assert!(is_forwarded(live.refs()), "the list does change");
            // Durably closed, and only the older poll says live.
            let live = overlay(second.clone(), marker)
                .live_execution(&state(&[]), read)
                .unwrap();
            assert!(is_forwarded(live.as_bool()));
            assert!(is_forwarded(live.refs()));
        }
        // A coherent poll answers both.
        let live = overlay(second, Some(read))
            .live_execution(&state(&[]), read)
            .unwrap();
        assert_eq!(live.as_bool(), Ok(true));
        assert_eq!(live.refs().unwrap(), ["x"]);
    }

    #[test]
    fn an_older_poll_that_adds_nothing_forwards_nothing() {
        let read = Position { entry: 6, ..AT };
        for marker in [Some(AT), None] {
            let unrelated = vec![handle("x", "ent-q", "ent-d", None)];
            let live = overlay(unrelated, marker)
                .live_execution(&state(&["i"]), read)
                .unwrap();
            assert_eq!(live.as_bool(), Ok(true));
            assert_eq!(live.refs().unwrap(), ["i"]);
            let live = overlay(Vec::new(), marker)
                .live_execution(&state(&[]), read)
                .unwrap();
            assert_eq!(live.as_bool(), Ok(false));
            assert!(live.refs().unwrap().is_empty());
        }
    }

    #[test]
    fn an_absent_field_forwards_even_where_it_would_have_made_no_difference() {
        let none = Overlay::new(None, None, Some(AT));
        assert!(is_forwarded(none.live_execution(&state(&["i"]), AT)));
        assert!(is_forwarded(none.active_executions(AT)));
        assert!(is_forwarded(none.run_observations(AT)));
        assert!(is_forwarded(none.work_out(AT, false, |_, live| {
            live.active_executions()?;
            Ok(None)
        })));
        assert!(is_forwarded(none.work_out(AT, false, |_, live| {
            live.run_observations()?;
            Ok(None)
        })));
    }

    fn both(marker: Option<Position>) -> Overlay {
        Overlay::new(
            Some(Arc::new(vec![handle("x", "ent-q", "ent-c", None)])),
            Some(Arc::new(RunObservations::default())),
            marker,
        )
    }

    /// Each poll that can't speak for a read at `AT`, and each way it can't.
    fn incoherent() -> [Overlay; 5] {
        [
            both(None),
            both(Some(Position { entry: 4, ..AT })),
            both(Some(Position {
                operational: 4,
                ..AT
            })),
            both(Some(Position { delivery: 4, ..AT })),
            // Further on in two components doesn't make up for one behind.
            both(Some(Position {
                entry: 9,
                operational: 9,
                delivery: 4,
            })),
        ]
    }

    #[test]
    fn the_raw_lists_forward_on_a_markerless_or_older_poll() {
        for poll in incoherent() {
            assert!(is_forwarded(poll.active_executions(AT)), "{poll:?}");
            assert!(is_forwarded(poll.run_observations(AT)), "{poll:?}");
        }
    }

    #[test]
    fn the_raw_lists_answer_a_coherent_poll() {
        let later = Position {
            entry: 9,
            operational: 9,
            delivery: 9,
        };
        for poll in [both(Some(AT)), both(Some(later))] {
            assert_eq!(poll.active_executions(AT).unwrap().len(), 1);
            assert!(poll.run_observations(AT).unwrap().0.is_empty());
        }
    }

    #[test]
    fn a_read_working_out_its_own_answer_uses_the_same_rule() {
        let count = |poll: &Overlay, durable: usize| {
            poll.work_out(AT, durable, |durable, live| {
                live.run_observations()?;
                let count = live.active_executions()?.len();
                Ok((count != *durable).then_some(count))
            })
        };
        for poll in incoherent() {
            assert_eq!(count(&poll, 1), Ok(1), "no difference: {poll:?}");
            assert!(is_forwarded(count(&poll, 0)), "a difference: {poll:?}");
        }
        assert_eq!(count(&both(Some(AT)), 1), Ok(1));
        assert_eq!(count(&both(Some(AT)), 0), Ok(1), "coherent, so it may");
    }

    #[test]
    fn no_difference_answers_exactly_the_durable_value_passed_in() {
        for poll in incoherent().into_iter().chain([both(Some(AT))]) {
            let got = poll.work_out(AT, 7usize, |_, live| {
                live.active_executions()?;
                Ok(None)
            });
            assert_eq!(got, Ok(7), "{poll:?}");
        }
    }

    /// `/api/conversations`: `sum(1 for e in live if e.conversation == cid)`, for each row.
    fn counts(
        poll: &Overlay,
        durable: BTreeMap<String, usize>,
    ) -> Result<BTreeMap<String, usize>, OpError> {
        poll.work_out(AT, durable, |durable, live| {
            let mut counts = durable.clone();
            counts.values_mut().for_each(|count| *count = 0);
            for e in live.active_executions()? {
                if let Some(count) = e.conversation.as_ref().and_then(|c| counts.get_mut(c)) {
                    *count += 1;
                }
            }
            Ok((counts != *durable).then_some(counts))
        })
    }

    #[test]
    fn the_conversation_list_s_count_goes_through_it() {
        let rows = |n| BTreeMap::from([("ent-c".to_owned(), n), ("ent-d".to_owned(), 0)]);
        for poll in incoherent() {
            assert_eq!(counts(&poll, rows(1)), Ok(rows(1)), "{poll:?}");
            assert!(is_forwarded(counts(&poll, rows(0))), "{poll:?}");
        }
        assert_eq!(counts(&both(Some(AT)), rows(0)), Ok(rows(1)));
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

    /// Conversation to `(run, participant)`, as `_live` gives it.
    type Workers = BTreeMap<String, Vec<(Option<String>, String)>>;
    /// `open_runs`, as `(run, (conversation, actor))`: `_live` compares against these too.
    type OpenRuns = Vec<(String, (String, String))>;

    /// `fluid/read.py::_live`, which reads both fields against the record's open runs.
    fn live_workers(
        poll: &Overlay,
        durable: (OpenRuns, Workers),
    ) -> Result<(OpenRuns, Workers), OpError> {
        poll.work_out(AT, durable, |(open, durable), live| {
            let runs = live.run_observations()?;
            let mut out = Workers::new();
            for (run, (conversation, actor)) in open {
                if runs.get(run).is_some_and(|held| held.ended_at.is_none()) {
                    let row = (Some(run.clone()), actor.clone());
                    out.entry(conversation.clone()).or_default().push(row);
                }
            }
            for e in live.active_executions()? {
                let conversation = e.conversation.clone().unwrap_or_default();
                let covered = out
                    .get(&conversation)
                    .is_some_and(|ws| ws.iter().any(|w| w.1 == e.participant));
                if !covered {
                    let row = (None, e.participant.clone());
                    out.entry(conversation).or_default().push(row);
                }
            }
            Ok((out != *durable).then(|| (open.clone(), out)))
        })
    }

    #[test]
    fn fluid_s_live_map_goes_through_it_with_both_fields() {
        let poll_at = |marker| {
            Overlay::new(
                Some(Arc::new(vec![handle("x", "ent-q", "ent-c", None)])),
                Some(Arc::new(RunObservations(vec![
                    observation("opr-going", None),
                    observation("opr-ended", Some(2.0)),
                ]))),
                marker,
            )
        };
        let open: OpenRuns = ["opr-going", "opr-ended"]
            .map(|run| (run.to_owned(), ("ent-d".to_owned(), "ent-p".to_owned())))
            .into();
        let same = Workers::from([
            ("ent-c".to_owned(), vec![(None, "ent-q".to_owned())]),
            (
                "ent-d".to_owned(),
                vec![(Some("opr-going".to_owned()), "ent-p".to_owned())],
            ),
        ]);
        let behind = Position { entry: 4, ..AT };
        for poll in [poll_at(None), poll_at(Some(behind))] {
            let got = live_workers(&poll, (open.clone(), same.clone()));
            assert_eq!(got, Ok((open.clone(), same.clone())), "{poll:?}");
            let got = live_workers(&poll, (open.clone(), Workers::new()));
            assert!(is_forwarded(got), "{poll:?}");
        }
        let got = live_workers(&poll_at(Some(AT)), (open.clone(), Workers::new()));
        assert_eq!(got, Ok((open.clone(), same.clone())));
        let no_active = Overlay::new(None, Some(Arc::new(RunObservations::default())), Some(AT));
        assert!(is_forwarded(live_workers(&no_active, (open, same))));
    }

    /// What needs more to answer than to compare, as an alias does, compares first and reads the
    /// list only after, which by then it may.
    #[test]
    fn a_read_can_compare_first_and_read_the_list_after() {
        let answer = |poll: &Overlay, durable: usize| -> Result<Option<usize>, OpError> {
            let (_, differs) = poll.work_out(AT, (durable, false), |(durable, _), live| {
                let differs = live.active_executions()?.len() != *durable;
                Ok(differs.then_some((*durable, true)))
            })?;
            if differs {
                Ok(Some(poll.active_executions(AT)?.len()))
            } else {
                Ok(None)
            }
        };
        for poll in incoherent() {
            assert_eq!(answer(&poll, 1), Ok(None), "{poll:?}");
            assert!(is_forwarded(answer(&poll, 0)), "{poll:?}");
        }
        assert_eq!(answer(&both(Some(AT)), 0), Ok(Some(1)));
    }

    #[test]
    fn debug_says_nothing_of_what_the_lists_and_references_hold() {
        let poll = Overlay::new(
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
            None,
        );
        let mut seen = vec![format!("{poll:?}"), format!("{poll:#?}")];
        // Both kinds of reference: the one the overlay adds, and the one the record holds.
        let mut named = state(&["secret-durable"]);
        named.expectation = "secret-for".into();
        let live = poll.live_execution(&named, AT).unwrap();
        assert!(is_forwarded(live.refs()), "it does hold the added one");
        seen.extend([format!("{live:?}"), format!("{live:#?}")]);
        let coherent = Overlay {
            marker: Some(AT),
            ..poll
        };
        let unsettled = coherent.work_out(AT, String::new(), |_, live| {
            live.active_executions()?;
            Ok(Some(format!("{live:?} {live:#?}")))
        });
        seen.push(unsettled.unwrap());
        for text in &seen {
            assert!(!text.contains("secret"), "{text}");
        }
        // Nor how many, which is worked out from a list.
        assert!(
            seen[0].contains("has_active_executions: true"),
            "{}",
            seen[0]
        );
        assert!(!seen[0].contains('1'), "{}", seen[0]);
    }

    #[test]
    fn a_panic_can_t_carry_a_list_out() {
        for poll in incoherent() {
            let caught = catch_unwind(AssertUnwindSafe(|| {
                poll.work_out(AT, 0usize, |_, live| {
                    std::panic::panic_any(live.active_executions()?.to_vec())
                })
            }));
            let payload = caught.expect_err("it panicked");
            assert!(!payload.is::<Vec<ActiveExecution>>());
            assert_eq!(
                payload.downcast_ref::<&str>(),
                Some(&"a work_out comparison panicked")
            );
        }
    }
}
