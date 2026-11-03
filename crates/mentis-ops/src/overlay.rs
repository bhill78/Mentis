//! What Python's two run registries look like from here, and how they join a durable read. The
//! fields are `/private/live`'s (`docs/rust/R4-R6-live-fields.md`); holding them and judging their
//! age is the front's. An op takes an [`Overlay`] in its `Args` and never reads a snapshot itself.
//!
//! **Nothing here is authority or a write decision.** Every "no" is [`OpError::NotOwned`], which
//! forwards the request to Python.

use std::fmt;
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
#[derive(Clone, Debug, Default, PartialEq)]
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

    /// The live handles, or forward: the field was omitted from this snapshot.
    pub fn active_executions(&self) -> Result<&[ActiveExecution], OpError> {
        self.active
            .as_deref()
            .map(Vec::as_slice)
            .ok_or_else(|| forward("no active_executions in this snapshot"))
    }

    /// The held runs, or forward: the field was omitted from this snapshot.
    pub fn run_observations(&self) -> Result<&RunObservations, OpError> {
        self.runs
            .as_deref()
            .ok_or_else(|| forward("no run_observations in this snapshot"))
    }

    /// Whether this poll can speak for a read at `read`: it has a marker, and isn't before it.
    pub fn coherent_with(&self, read: Position) -> bool {
        self.marker
            .is_some_and(|marker| !poll_is_before(marker, read))
    }

    /// The coherence rule, for a read that works out its own answer, such as a live count: an
    /// overlay that makes no difference may be ignored, and one that does has to be coherent.
    pub fn may_change_answer(&self, read: Position, changes_answer: bool) -> Result<(), OpError> {
        if changes_answer && !self.coherent_with(read) {
            return Err(forward("this poll is before the durable read"));
        }
        Ok(())
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
        for e in self.active_executions()? {
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

/// Python's raw `live_execution` for one expectation: `sorted(durable ∪ overlay)`. There is no way
/// to get at it without saying which answer it is for, because the two forward differently.
#[derive(Clone, Debug, PartialEq, Eq)]
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
        assert!(is_forwarded(none.active_executions()));
        assert!(is_forwarded(none.run_observations()));
    }

    #[test]
    fn a_read_working_out_its_own_answer_uses_the_same_rule() {
        let read = Position { delivery: 6, ..AT };
        let held = overlay(Vec::new(), Some(AT));
        assert_eq!(held.may_change_answer(read, false), Ok(()));
        assert!(is_forwarded(held.may_change_answer(read, true)));
        assert_eq!(held.may_change_answer(AT, true), Ok(()));
        let unmarked = overlay(Vec::new(), None);
        assert_eq!(unmarked.may_change_answer(AT, false), Ok(()));
        assert!(is_forwarded(unmarked.may_change_answer(AT, true)));
    }
}
