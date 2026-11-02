//! Per-route latency in the front's log. `R1-acceptance.md`, "After a deploy": the release report
//! compares these with the bench while real agents are active, which is the only evidence of what
//! reached DAY-TO-DAY. It decides nothing, and nothing reads it at run time.

use std::collections::BTreeMap;
use std::sync::Mutex;
use std::time::Duration;

/// How often a line is written, when anything changed.
pub const LOG_EVERY: Duration = Duration::from_secs(10);

/// Buckets double from 50 microseconds, so 25 of them reach about 28 minutes. A percentile is the
/// top of its bucket: an overstatement of at most double, and it needs no sample kept.
const BUCKETS: usize = 25;
const FIRST_BUCKET_US: u64 = 50;

#[derive(Clone, Debug, Default)]
struct Route {
    counts: [u64; BUCKETS],
    total: u64,
}

impl Route {
    fn add(&mut self, took: Duration) {
        let micros = u64::try_from(took.as_micros()).unwrap_or(u64::MAX);
        let mut top = FIRST_BUCKET_US;
        let mut bucket = 0;
        while micros > top && bucket + 1 < BUCKETS {
            top = top.saturating_mul(2);
            bucket += 1;
        }
        self.counts[bucket] += 1;
        self.total += 1;
    }

    fn percentile_ms(&self, percent: u64) -> f64 {
        let wanted = (self.total * percent).div_ceil(100).max(1);
        let mut seen = 0;
        let mut top = FIRST_BUCKET_US;
        for count in self.counts {
            seen += count;
            if seen >= wanted {
                break;
            }
            top = top.saturating_mul(2);
        }
        top as f64 / 1000.0
    }
}

/// Since this front started. Cheap enough for every request: one short lock, no file.
#[derive(Debug, Default)]
pub struct Latency {
    routes: Mutex<BTreeMap<String, Route>>,
    written_at_total: Mutex<u64>,
}

impl Latency {
    pub fn record(&self, route: &str, took: Duration) {
        let mut routes = self.routes.lock().expect("no panic is held across this");
        match routes.get_mut(route) {
            Some(known) => known.add(took),
            None => {
                let mut new = Route::default();
                new.add(took);
                routes.insert(route.to_owned(), new);
            }
        }
    }

    /// A line per route, each JSON, if anything happened since the last time.
    pub fn lines_if_changed(&self) -> Vec<String> {
        let routes = self.routes.lock().expect("no panic is held across this");
        let total: u64 = routes.values().map(|route| route.total).sum();
        let mut written = self
            .written_at_total
            .lock()
            .expect("no panic is held across this");
        if total == *written {
            return Vec::new();
        }
        *written = total;
        routes
            .iter()
            .map(|(name, route)| {
                serde_json::json!({
                    "event": "latency",
                    "route": name,
                    "count": route.total,
                    "p50_ms": route.percentile_ms(50),
                    "p95_ms": route.percentile_ms(95),
                })
                .to_string()
            })
            .collect()
    }
}

/// What a request's time is filed under when no rule named it: `/api/worker` apart, because it is
/// how an agent's calls are seen in the log, and the rest by family. A path never becomes a name,
/// so the log can't grow with what is asked.
pub fn unnamed_route(path: &str) -> &'static str {
    if path == "/api/worker" {
        "forwarded:/api/worker"
    } else if path.starts_with("/fluid/api/") {
        "forwarded:/fluid/api"
    } else if path.starts_with("/api/") {
        "forwarded:/api"
    } else {
        "forwarded:other"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn percentiles_are_bucket_tops() {
        let mut route = Route::default();
        for _ in 0..94 {
            route.add(Duration::from_micros(40));
        }
        for _ in 0..6 {
            route.add(Duration::from_millis(10));
        }
        assert_eq!(route.percentile_ms(50), 0.05);
        assert_eq!(route.percentile_ms(95), 12.8);
    }

    #[test]
    fn something_longer_than_the_buckets_stays_in_the_last_one() {
        let mut route = Route::default();
        route.add(Duration::from_secs(100_000));
        assert_eq!(route.counts[BUCKETS - 1], 1);
    }

    #[test]
    fn a_line_is_written_only_when_something_moved() {
        let log = Latency::default();
        assert!(log.lines_if_changed().is_empty());
        log.record("static", Duration::from_millis(1));
        log.record("forwarded:/api/worker", Duration::from_millis(2));
        let lines = log.lines_if_changed();
        assert_eq!(lines.len(), 2);
        let line: serde_json::Value = serde_json::from_str(&lines[1]).unwrap();
        assert_eq!(line["route"], "static");
        assert_eq!(line["count"], 1);
        assert!(log.lines_if_changed().is_empty());
    }

    #[test]
    fn no_path_becomes_a_name() {
        assert_eq!(unnamed_route("/api/worker"), "forwarded:/api/worker");
        assert_eq!(unnamed_route("/api/worker/session"), "forwarded:/api");
        assert_eq!(unnamed_route("/fluid/api/posts/1"), "forwarded:/fluid/api");
        assert_eq!(unnamed_route("/whatever/you/like"), "forwarded:other");
    }
}
