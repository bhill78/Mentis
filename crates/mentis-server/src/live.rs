//! `GET /private/live`: what the front knows of run state, which only Python holds until R7.
//! Contract: `docs/rust/contracts/live-snapshot.md`.

use std::sync::Arc;
use std::time::Duration;

use mentis_ops::overlay::Overlay;
pub use mentis_ops::overlay::{ActiveExecution, RunObservation, RunObservations};
use mentis_record::Position;
use serde::de::{DeserializeOwned, Deserializer};
use serde::{Deserialize, Serialize};
use serde_json::value::RawValue;

pub const LIVE_PATH: &str = "/private/live";

/// The envelope this build reads. A release that only adds to `fields` keeps it; anything else
/// changes it, and a front that doesn't know the new one says `Unavailable`.
pub const SNAPSHOT_SCHEMA: u32 = 1;

/// Poll this often...
pub const POLL_EVERY: Duration = Duration::from_millis(500);
/// ...each poll giving up after this...
pub const POLL_TIMEOUT: Duration = Duration::from_millis(250);
/// ...and only while a pulse was asked for this recently.
pub const POLL_WHILE_ASKED_WITHIN: Duration = Duration::from_secs(5);

/// A snapshot is fresh up to this age, inclusive. Past it, R1's pulse says so, and from R4 a read
/// that shows run or work state forwards and never answers from the snapshot.
pub const STALE_AFTER: Duration = Duration::from_secs(2);
/// Stale up to this, inclusive, and unavailable past it. See [`freshness`] for what it is counted
/// from.
pub const UNAVAILABLE_AFTER: Duration = Duration::from_secs(10);

/// The live half of a pulse token while the state is [`Liveness::Unavailable`]. Constant, so a
/// reader rereads once on the way in and once on the way out, not on every beat. Readers only
/// compare it (`fluid/identity/activity.ts:146`).
pub const UNAVAILABLE_HASH: &str = "unavailable";

/// The snapshot.
///
/// **Later releases only add named fields.** So this is deliberately not `deny_unknown_fields`, and
/// every field a later release adds must be optional here.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct LiveSnapshot {
    /// See [`SNAPSHOT_SCHEMA`].
    pub schema: u32,
    /// Random per Python process. A changed one discards what is held ([`discards`]).
    pub boot_id: String,
    /// Goes up within a boot when `(live_now, run_marks)` differs from the last snapshot taken.
    pub generation: u64,
    /// `sha256(repr((live_now, run_marks)))[:12]`, Python's expression at `web/__init__.py:172`.
    /// Rust never computes it: `repr` is Python's. It is the live half of the pulse token, and the
    /// only thing R1 uses from here.
    pub live_hash: String,
    /// `time.time()` in Python when this was taken. For logs and reports: freshness is judged from
    /// the front's own monotonic clock (see the contract).
    pub taken_at: f64,
    fields: LiveFields,
}

impl LiveSnapshot {
    /// The only projection of decoded added fields available to the rest of the server. Route code
    /// can receive an `Overlay`; it cannot read either decoded list directly.
    pub(crate) fn overlay(&self, marker: Option<Position>) -> Overlay {
        Overlay::new(
            self.fields.active_executions.clone(),
            self.fields.run_observations.clone(),
            marker,
        )
    }

    #[cfg(test)]
    pub(crate) fn empty(boot: &str, generation: u64, live_hash: &str) -> Self {
        Self {
            schema: SNAPSHOT_SCHEMA,
            boot_id: boot.into(),
            generation,
            live_hash: live_hash.into(),
            taken_at: 1.0,
            fields: LiveFields::default(),
        }
    }
}

/// What the snapshot carries for reads. R1 reads none of it. R4 to R6 can't start until the fields
/// they need are listed here and reviewed.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
struct LiveFields {
    pub live_now: Vec<LiveInstance>,
    pub run_marks: Vec<RunMark>,
    /// `None` when the field was omitted, or isn't what this build can read: a route that needs it
    /// forwards. See [`or_absent`].
    #[serde(
        default,
        deserialize_with = "or_absent",
        skip_serializing_if = "Option::is_none"
    )]
    pub active_executions: Option<Arc<Vec<ActiveExecution>>>,
    /// As `active_executions` is.
    #[serde(
        default,
        deserialize_with = "or_absent",
        skip_serializing_if = "Option::is_none"
    )]
    pub run_observations: Option<Arc<RunObservations>>,
}

/// An added field that can't be read is an absent one, **and costs the snapshot nothing:** the pulse
/// needs none of them, and a value MARS returned mustn't be able to turn every poll unreadable. It
/// is taken as raw text first, which has no depth limit, and `tooling` stays raw after that, so
/// however deep it is it goes on as it came.
fn or_absent<'de, D: Deserializer<'de>, T: DeserializeOwned>(
    from: D,
) -> Result<Option<Arc<T>>, D::Error> {
    let raw = Box::<RawValue>::deserialize(from)?;
    Ok(serde_json::from_str(raw.get()).ok().map(Arc::new))
}

/// `Service.live_now`, one (instance, liveness) pair.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct LiveInstance(pub String, pub String);

/// `Service.run_marks`, one row, positionally as Python's tuple is. Something that moves when a
/// held run's observation does: not a status, so nothing may read a state out of it.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RunMark(
    /// The run.
    pub String,
    /// `performing_since`.
    pub Option<f64>,
    /// `last_event.at`.
    pub Option<f64>,
    /// `ended_at`.
    pub Option<f64>,
    /// `stop`.
    pub bool,
    /// How many permission questions.
    pub u64,
    /// The feed's activity line.
    pub Option<String>,
);

/// What one poll's answer body is.
#[derive(Clone, Debug, PartialEq)]
pub enum PollAnswer {
    Snapshot(LiveSnapshot),
    /// A schema this build doesn't read: [`Liveness::Unavailable`], and what is held is discarded.
    UnknownSchema(u32),
    /// No schema, or not the envelope its schema says. Counts as a failed poll: age keeps growing.
    Unreadable,
}

impl PollAnswer {
    /// The schema is read first, on its own, because a later schema need not parse as this one.
    pub fn read(body: &[u8]) -> Self {
        #[derive(Deserialize)]
        struct Schema {
            schema: u32,
        }
        match serde_json::from_slice::<Schema>(body) {
            Err(_) => Self::Unreadable,
            Ok(Schema { schema }) if schema != SNAPSHOT_SCHEMA => Self::UnknownSchema(schema),
            Ok(_) => match serde_json::from_slice(body) {
                Ok(snapshot) => Self::Snapshot(snapshot),
                Err(_) => Self::Unreadable,
            },
        }
    }
}

/// Whether `answer` discards `held` rather than replacing it: a changed `boot_id` or a lower
/// `generation`. The answer isn't adopted either. With nothing held, the next poll's is.
pub fn discards(held: &LiveSnapshot, answer: &LiveSnapshot) -> bool {
    answer.boot_id != held.boot_id || answer.generation < held.generation
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Liveness {
    Fresh,
    Stale,
    Unavailable,
}

/// How a held snapshot stands, while nothing has said Python is gone.
///
/// `age` is now minus when the answering poll was sent. `polling_for` is now minus when polling
/// last turned on. **Time with polling off counts toward stale and never toward unavailable:**
/// nobody asked Python anything then, so it says nothing about Python. A resumed front is stale
/// until its first answer, and has the full [`UNAVAILABLE_AFTER`] from the moment it resumed.
pub fn freshness(age: Duration, polling_for: Duration) -> Liveness {
    if age <= STALE_AFTER {
        Liveness::Fresh
    } else if age.min(polling_for) <= UNAVAILABLE_AFTER {
        Liveness::Stale
    } else {
        Liveness::Unavailable
    }
}

/// `live` on a pulse's answer, added only when the state isn't fresh, so a fresh answer has
/// Python's shape. A listed additive difference: Fluid ignores it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct LiveMark {
    pub state: Liveness,
    /// True age, idle time included. `None` with nothing held.
    pub age_ms: Option<u64>,
}

impl LiveMark {
    pub fn of(state: Liveness, age: Option<Duration>) -> Option<Self> {
        (state != Liveness::Fresh).then(|| Self {
            state,
            age_ms: age.map(|age| u64::try_from(age.as_millis()).unwrap_or(u64::MAX)),
        })
    }
}

/// The pulse token: the durable half this front read, and the live half as [`Liveness`] allows.
/// `held` is `None` with no snapshot held, which is always `Unavailable`.
pub fn pulse_token(durable: &str, state: Liveness, held: Option<&str>) -> String {
    let live = match (state, held) {
        (Liveness::Unavailable, _) | (_, None) => UNAVAILABLE_HASH,
        (_, Some(hash)) => hash,
    };
    format!("{durable}/{live}")
}

#[cfg(test)]
mod tests {
    use super::*;

    const AS_PYTHON_SENDS_IT: &str = r#"{
        "schema": 1,
        "boot_id": "b1f3",
        "generation": 17,
        "live_hash": "a1b2c3d4e5f6",
        "taken_at": 1793562208.0485663,
        "fields": {
            "live_now": [["inst-1", "live"]],
            "run_marks": [["opr-1", 1793562000.5, null, null, false, 2, "Run npm test"],
                          ["opr-2", null, 1793562001.25, 1793562002.0, true, 0, null]]
        }
    }"#;

    const fn secs(n: u64) -> Duration {
        Duration::from_secs(n)
    }

    fn snapshot(text: &str) -> LiveSnapshot {
        match PollAnswer::read(text.as_bytes()) {
            PollAnswer::Snapshot(snapshot) => snapshot,
            other => panic!("not a snapshot: {other:?}"),
        }
    }

    fn altered(change: impl FnOnce(&mut serde_json::Value)) -> Vec<u8> {
        let mut value: serde_json::Value = serde_json::from_str(AS_PYTHON_SENDS_IT).unwrap();
        change(&mut value);
        serde_json::to_vec(&value).unwrap()
    }

    #[test]
    fn reads_what_python_sends() {
        let got = snapshot(AS_PYTHON_SENDS_IT);
        assert_eq!(got.boot_id, "b1f3");
        assert_eq!(got.generation, 17);
        assert_eq!(
            got.fields.live_now,
            [LiveInstance("inst-1".into(), "live".into())]
        );
        assert_eq!(got.fields.run_marks[0].5, 2);
        assert!(got.fields.run_marks[1].4);
        assert_eq!(got.fields.run_marks[1].6, None);
    }

    #[test]
    fn a_later_release_can_add_a_field_without_breaking_this_one() {
        let body = altered(|value| {
            value["fields"]["work_marks"] = serde_json::json!({"added": "by R4"});
        });
        assert!(matches!(
            PollAnswer::read(&body),
            PollAnswer::Snapshot(got) if got.live_hash == "a1b2c3d4e5f6"
        ));
    }

    const ACTIVE: &str = r#"[{"reference": "exe-1", "participant": "ent-p", "conversation": null,
        "runtime": "claude", "persona": null, "for_expectation": "opr-e"}]"#;
    const RUN: &str = r#"{"run": "opr-1", "instance": "inst-1", "opened_at": 1.5,
        "performing_since": null, "last_event": {"kind": "x", "at": 2.0, "what": "y"},
        "ended_at": null, "stop": null, "outcome": null, "permission": null, "permissions": [],
        "activity": "Run npm test", "activity_at": 2.5, "running": true}"#;

    #[test]
    fn the_added_fields_are_read_when_python_sends_them_and_absent_when_it_doesn_t() {
        let none = snapshot(AS_PYTHON_SENDS_IT);
        assert_eq!(none.fields.active_executions, None);
        assert_eq!(none.fields.run_observations, None);

        let body = altered(|value| {
            value["fields"]["active_executions"] = serde_json::from_str(ACTIVE).unwrap();
            let run: serde_json::Value = serde_json::from_str(RUN).unwrap();
            value["fields"]["run_observations"] = serde_json::json!({"opr-1": run});
        });
        let PollAnswer::Snapshot(got) = PollAnswer::read(&body) else {
            panic!("not a snapshot");
        };
        let active = got.fields.active_executions.unwrap();
        assert_eq!(active[0].reference, "exe-1");
        assert_eq!(active[0].for_expectation.as_deref(), Some("opr-e"));
        let runs = got.fields.run_observations.unwrap();
        let run = runs.get("opr-1").unwrap();
        assert_eq!(run.instance, "inst-1");
        assert!(run.running);
        assert_eq!(run.tooling, None, "absent until the run has ended");
    }

    #[test]
    fn a_tooling_of_null_stays_apart_from_none_and_the_order_stays_python_s() {
        let text = format!(
            r#"{{"z": {RUN}, "a": {}}}"#,
            RUN.replace(r#""running": true"#, r#""running": false, "tooling": null"#)
        );
        let runs: RunObservations = serde_json::from_str(&text).unwrap();
        let order: Vec<_> = runs.0.iter().map(|row| row.running).collect();
        assert_eq!(order, [true, false]);
        assert_eq!(runs.0[0].tooling, None);
        assert!(runs.0[1].tooling.as_ref().unwrap().is_null());
    }

    #[test]
    fn a_field_this_build_can_t_read_costs_that_field_and_not_the_poll() {
        let body = altered(|value| {
            value["fields"]["active_executions"] = serde_json::json!({"not": "a list"});
            value["fields"]["run_observations"] = serde_json::json!([1, 2]);
        });
        let PollAnswer::Snapshot(got) = PollAnswer::read(&body) else {
            panic!("the envelope is still good");
        };
        assert_eq!(got.live_hash, "a1b2c3d4e5f6");
        assert_eq!(got.fields.active_executions, None);
        assert_eq!(got.fields.run_observations, None);
    }

    #[test]
    fn a_tooling_too_deep_for_serde_is_carried_as_it_came_and_costs_nothing() {
        let deep = format!("{}1{}", "[".repeat(400), "]".repeat(400));
        let run = RUN.replace(
            r#""running": true"#,
            &format!(r#""running": true, "tooling": {deep}"#),
        );
        let body = AS_PYTHON_SENDS_IT.replace(
            r#""live_now":"#,
            &format!(r#""run_observations": {{"opr-1": {run}}}, "live_now":"#),
        );
        let PollAnswer::Snapshot(got) = PollAnswer::read(body.as_bytes()) else {
            panic!("the envelope is still good");
        };
        assert_eq!(got.live_hash, "a1b2c3d4e5f6");
        let runs = got.fields.run_observations.unwrap();
        let tooling = runs.get("opr-1").unwrap().tooling.as_ref().unwrap();
        assert_eq!(tooling.text(), deep);
    }

    #[test]
    fn an_unknown_schema_is_named_even_if_nothing_else_parses() {
        assert_eq!(
            PollAnswer::read(br#"{"schema": 2, "live": "elsewhere"}"#),
            PollAnswer::UnknownSchema(2)
        );
    }

    #[test]
    fn a_broken_envelope_is_a_failed_poll() {
        let no_generation = altered(|value| {
            value.as_object_mut().unwrap().remove("generation");
        });
        let opaque_generation = altered(|value| value["generation"] = "b1f3.17".into());
        for body in [
            &no_generation[..],
            &opaque_generation[..],
            b"{}",
            b"not json",
        ] {
            assert_eq!(PollAnswer::read(body), PollAnswer::Unreadable);
        }
    }

    #[test]
    fn a_new_boot_or_a_lower_generation_discards() {
        let held = snapshot(AS_PYTHON_SENDS_IT);
        let at = |boot: &str, generation| LiveSnapshot {
            boot_id: boot.into(),
            generation,
            ..held.clone()
        };
        assert!(!discards(&held, &at("b1f3", 17)));
        assert!(!discards(&held, &at("b1f3", 18)));
        assert!(discards(&held, &at("b1f3", 16)));
        assert!(discards(&held, &at("c9d0", 99)));
    }

    #[test]
    fn the_boundaries_while_polling() {
        let long = secs(3600);
        assert_eq!(freshness(secs(2), long), Liveness::Fresh);
        assert_eq!(
            freshness(secs(2) + Duration::from_millis(1), long),
            Liveness::Stale
        );
        assert_eq!(freshness(secs(10), long), Liveness::Stale);
        assert_eq!(
            freshness(secs(10) + Duration::from_millis(1), long),
            Liveness::Unavailable
        );
    }

    #[test]
    fn resuming_from_idle_is_stale_not_unavailable() {
        let idle = secs(3600);
        assert_eq!(freshness(idle, Duration::ZERO), Liveness::Stale);
        assert_eq!(freshness(idle, secs(10)), Liveness::Stale);
        assert_eq!(
            freshness(idle, secs(10) + Duration::from_millis(1)),
            Liveness::Unavailable
        );
    }

    #[test]
    fn a_fresh_answer_has_python_s_shape() {
        assert_eq!(LiveMark::of(Liveness::Fresh, Some(secs(1))), None);
        let stale = LiveMark::of(Liveness::Stale, Some(Duration::from_millis(2500)));
        assert_eq!(
            serde_json::to_string(&stale).unwrap(),
            r#"{"state":"stale","age_ms":2500}"#
        );
        let nothing_held = LiveMark::of(Liveness::Unavailable, None);
        assert_eq!(
            serde_json::to_string(&nothing_held).unwrap(),
            r#"{"state":"unavailable","age_ms":null}"#
        );
    }

    #[test]
    fn the_token_has_python_s_shape_and_says_unavailable_once() {
        let hash = Some("a1b2c3d4e5f6");
        assert_eq!(
            pulse_token("1.2.3", Liveness::Fresh, hash),
            "1.2.3/a1b2c3d4e5f6"
        );
        assert_eq!(
            pulse_token("1.2.3", Liveness::Stale, hash),
            "1.2.3/a1b2c3d4e5f6"
        );
        assert_eq!(
            pulse_token("1.2.3", Liveness::Unavailable, hash),
            "1.2.3/unavailable"
        );
        assert_eq!(
            pulse_token("1.2.3", Liveness::Unavailable, None),
            "1.2.3/unavailable"
        );
    }
}
