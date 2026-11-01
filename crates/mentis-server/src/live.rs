//! `GET /private/live`: what the front knows of run state, which only Python holds until R7.
//! Contract: `docs/rust/contracts/live-snapshot.md`.

use std::time::Duration;

use serde::{Deserialize, Serialize};

pub const LIVE_PATH: &str = "/private/live";

/// Poll this often...
pub const POLL_EVERY: Duration = Duration::from_millis(500);
/// ...each poll giving up after this...
pub const POLL_TIMEOUT: Duration = Duration::from_millis(250);
/// ...and only while a pulse was asked for this recently.
pub const POLL_WHILE_ASKED_WITHIN: Duration = Duration::from_secs(5);
/// From R4, the oldest snapshot a read that shows run or work state may use. Past it, forward; if
/// Python cannot answer, 503 with the reason. Never an older state. Nothing in R1 is bound by it.
pub const MAX_AGE_FROM_R4: Duration = Duration::from_secs(2);

/// The live half of a pulse token before any snapshot has arrived. Twelve hex digits, like every
/// other, and not one `hash` will produce by accident often enough to matter: a reader only
/// compares, so the worst case is one late refresh.
pub const NO_SNAPSHOT_HASH: &str = "000000000000";

/// The snapshot.
///
/// **Later releases only add named fields.** So this is deliberately not `deny_unknown_fields`, and
/// every field a later release adds must be optional here.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct LiveSnapshot {
    /// Changes with each Python boot and each live change, and with nothing else. Opaque: compare
    /// for equality only.
    pub generation: String,
    /// `time.time()` in Python when this was taken. For logs and reports: freshness is judged from
    /// the front's own monotonic clock (see the contract).
    pub taken_at: f64,
    /// `sha256(repr((live_now, run_marks)))[:12]`, Python's expression at `web/__init__.py:2592`.
    /// Rust never computes it: `repr` is Python's. It is the live half of the pulse token.
    pub hash: String,
    pub live_now: Vec<LiveInstance>,
    pub run_marks: Vec<RunMark>,
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

/// The pulse token: the durable half this front read, and the live half as last heard. `hash` is
/// `None` before the first snapshot. Readers only compare it (`fluid/identity/activity.ts:146`).
pub fn pulse_token(durable: &str, hash: Option<&str>) -> String {
    format!("{durable}/{}", hash.unwrap_or(NO_SNAPSHOT_HASH))
}

#[cfg(test)]
mod tests {
    use super::*;

    const AS_PYTHON_SENDS_IT: &str = r#"{
        "generation": "b1f3.17",
        "taken_at": 1793562208.0485663,
        "hash": "a1b2c3d4e5f6",
        "live_now": [["inst-1", "live"]],
        "run_marks": [["opr-1", 1793562000.5, null, null, false, 2, "Run npm test"],
                      ["opr-2", null, 1793562001.25, 1793562002.0, true, 0, null]]
    }"#;

    #[test]
    fn reads_what_python_sends() {
        let got: LiveSnapshot = serde_json::from_str(AS_PYTHON_SENDS_IT).unwrap();
        assert_eq!(got.generation, "b1f3.17");
        assert_eq!(got.live_now, [LiveInstance("inst-1".into(), "live".into())]);
        assert_eq!(got.run_marks[0].5, 2);
        assert!(got.run_marks[1].4);
        assert_eq!(got.run_marks[1].6, None);
    }

    #[test]
    fn a_later_release_can_add_a_field_without_breaking_this_one() {
        let mut value: serde_json::Value = serde_json::from_str(AS_PYTHON_SENDS_IT).unwrap();
        value["work_marks"] = serde_json::json!({"added": "by R4"});
        let got: LiveSnapshot = serde_json::from_value(value).unwrap();
        assert_eq!(got.hash, "a1b2c3d4e5f6");
    }

    #[test]
    fn a_missing_field_is_refused() {
        let mut value: serde_json::Value = serde_json::from_str(AS_PYTHON_SENDS_IT).unwrap();
        value.as_object_mut().unwrap().remove("generation");
        assert!(serde_json::from_value::<LiveSnapshot>(value).is_err());
    }

    #[test]
    fn the_token_has_python_s_shape() {
        assert_eq!(
            pulse_token("1.2.3", Some("a1b2c3d4e5f6")),
            "1.2.3/a1b2c3d4e5f6"
        );
        assert_eq!(pulse_token("1.2.3", None), "1.2.3/000000000000");
    }
}
