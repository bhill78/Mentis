//! What a grant may ask, and how a refusal is said: `permitted`, `worker.py:437`, and the words at
//! `web/__init__.py:3046` and `:3055`. **Python's table stays the authority.** A change there fails
//! `tests/front/test_permission_matrix.py`, and this file is held to the same generated matrix by
//! `tests/permitted_matrix.rs`. A rule changes in both or waits.
//!
//! This is rules and words, and the door applies them. It knows nothing of the mirror, or of whose
//! grant is being asked about.

/// `worker.READS`.
const READS: [&str; 12] = [
    "orient",
    "find",
    "resolve",
    "history",
    "kinds",
    "check_rendering",
    "governed",
    "owner_decisions",
    "capabilities",
    "brief",
    "recall",
    "work_overview",
];

/// `worker.SOURCE_READS`.
const SOURCE_READS: [&str; 5] = [
    "sources",
    "source_history",
    "source_links",
    "read_source",
    "search_sources",
];

/// `worker.ASKS`, `LADDER_ACTS` included.
const ASKS: [&str; 18] = [
    "request_decision",
    "request_input",
    "answer",
    "timer",
    "record_discovered_work",
    "return_artifact",
    "read_artifact",
    "await_work",
    "arm_detached",
    "propose_revision",
    "record_verdict",
    "propose_suitability",
    "change_workflow",
    "workspace_objects",
    "record_material",
    "request_adoption",
    "challenge",
    "withdraw_challenge",
];

/// `worker.INTERACTS`.
const INTERACTS: [&str; 2] = ["anchor", "react"];

/// `worker.HANDS_OFF`.
const HANDS_OFF: [&str; 1] = ["delegate"];

/// `worker.RESOURCES`.
const RESOURCES: [&str; 3] = ["claim_resource", "release_resource", "resources"];

/// `worker.ORGANISES`.
const ORGANISES: [&str; 5] = [
    "open_topic",
    "open_conversation",
    "summon_participant",
    "propose_material",
    "respond",
];

/// `worker.DEEP_DIVE`, `RESUME_INTAKE`, `ATTACH_FOLLOW_UP`, `COORDINATE`.
const DEEP_DIVE: &str = "deep_dive";
const RESUME_INTAKE: &str = "resume_intake";
const ATTACH_FOLLOW_UP: &str = "attach_follow_up";
const COORDINATE: &str = "coordinate";

/// `worker.SESSION_SCOPE`.
const SESSION_SCOPE: &str = "manual-session";

/// `worker.SESSION_ACTS`.
const SESSION_ACTS: [&str; 4] = [
    "record_request",
    "record_outcome",
    "take_up",
    "contribute",
];

/// `worker.SESSION_CARRIED`.
const SESSION_CARRIED: [&str; 12] = [
    "respond",
    "request_decision",
    "request_input",
    "answer",
    "timer",
    "await_work",
    "arm_detached",
    "return_artifact",
    "propose_revision",
    "read_artifact",
    "record_verdict",
    "workspace_objects",
];

/// `worker.TRANSIENT_SCOPE`: a Quick Ask's. The mirror doesn't hold it and the door forwards it,
/// because `note_deleted_reads` is Python's.
pub const TRANSIENT_SCOPE: &str = "transient-read";

/// `web/__init__.py:3046`: a token held for another corpus.
pub const OTHER_CORPUS_WORDS: &str = "this question needs a live worker grant for this corpus";

/// What every dispatched execution holds, whatever its scope.
fn base() -> impl Iterator<Item = &'static str> {
    READS
        .into_iter()
        .chain(SOURCE_READS)
        .chain(ASKS)
        .chain(INTERACTS)
        .chain(HANDS_OFF)
        .chain(RESOURCES)
}

/// `permitted("organising", operations)`, with `None` as `OPERATIONS`.
fn organising(operations: Option<&[&str]>) -> Vec<&'static str> {
    let Some(operations) = operations else {
        return base()
            .chain(ORGANISES)
            .chain([DEEP_DIVE, RESUME_INTAKE, ATTACH_FOLLOW_UP])
            .collect();
    };
    let held: Vec<&'static str> = ORGANISES
        .into_iter()
        .filter(|name| operations.contains(name))
        .collect();
    let dives = held.contains(&"open_conversation");
    let coordinates = operations.contains(&COORDINATE);
    base()
        .chain(held)
        .chain(dives.then_some(DEEP_DIVE))
        .chain(coordinates.then_some(RESUME_INTAKE))
        .chain(coordinates.then_some(ATTACH_FOLLOW_UP))
        .collect()
}

/// `worker.permitted`: the same names in the same order. `None` for `operations` is a grant that
/// doesn't carry any, which isn't the same as an empty list.
pub fn permitted(scope: Option<&str>, operations: Option<&[String]>) -> Vec<&'static str> {
    let names: Option<Vec<&str>> = operations.map(|held| held.iter().map(String::as_str).collect());
    let names = names.as_deref();
    match scope {
        Some(TRANSIENT_SCOPE) => READS
            .into_iter()
            .chain(SOURCE_READS)
            .chain(["read_artifact"])
            .collect(),
        // `AUTHORITY if operations is None else operations`, which isn't `OPERATIONS`: every
        // organising name is held, and the two derived from them follow.
        Some(SESSION_SCOPE) => {
            let authority: Vec<&str> = ORGANISES.into_iter().chain([COORDINATE]).collect();
            organising(Some(names.unwrap_or(&authority)))
                .into_iter()
                .filter(|name| !SESSION_CARRIED.contains(name))
                .chain(SESSION_ACTS)
                .collect()
        }
        Some("intake" | "organising") => organising(names),
        _ => base().collect(),
    }
}

/// Whether Rust can say `repr(text)`: printable ASCII only. Anything else, the door forwards, and
/// Python words it. A quote or a backslash is printable, and [`repr`] says those.
pub fn repr_is_simple(text: &str) -> bool {
    text.bytes().all(|b| (0x20..0x7f).contains(&b))
}

/// `repr(text)`, for text [`repr_is_simple`] accepts.
fn repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::with_capacity(text.len() + 2);
    out.push(quote);
    for c in text.chars() {
        if c == '\\' || c == quote {
            out.push('\\');
        }
        out.push(c);
    }
    out.push(quote);
    out
}

/// The refusal at `web/__init__.py:3055`, with `repr` of `op`, of `scope` and of `sorted(allowed)`.
/// `op` and `scope` are ones [`repr_is_simple`] accepts: the door forwards any other.
pub fn not_permitted_words(op: &str, scope: Option<&str>, allowed: &[&str]) -> String {
    let mut sorted = allowed.to_vec();
    sorted.sort_unstable();
    let shown: Vec<String> = sorted.iter().map(|name| repr(name)).collect();
    let op = repr(op);
    let scope = scope.map_or_else(|| "None".to_owned(), repr);
    let may = shown.join(", ");
    format!(
        "{op} is not admissible for this execution. It was dispatched with scope {scope}, which \
         may [{may}]. If the work needs someone else's role, hand it to them with `delegate`; if \
         it needs anything else listed here, return the need. This is the record telling you what \
         this run may not do -- not a malfunction, and not a reason to reach the record another \
         way. You run as the owner, so other routes exist; taking one because this said no would \
         record this as the owner's own act, under an author nobody observed. Report what you \
         could not do."
    )
}

/// `json.dumps(words)`.
fn json_text(words: &str) -> String {
    let mut out = String::with_capacity(words.len() + 2);
    out.push('"');
    for c in words.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            ' '..='~' => out.push(c),
            _ => {
                let mut units = [0u16; 2];
                for unit in c.encode_utf16(&mut units) {
                    out.push_str(&format!("\\u{unit:04x}"));
                }
            }
        }
    }
    out.push('"');
    out
}

/// The 403's body, `web/__init__.py:7104`. `NotPermitted` is a `PermissionError`, and that `except`
/// says the base class's name whichever was raised, so both refusals carry this `kind`.
pub fn refused_body(words: &str) -> String {
    format!(
        "{{\"error\": {}, \"kind\": \"PermissionError\"}}",
        json_text(words)
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_repr_quotes_as_python_s_does() {
        assert_eq!(repr("plain"), "'plain'");
        assert_eq!(repr("it's"), "\"it's\"");
        assert_eq!(repr("say \"x\""), "'say \"x\"'");
        assert_eq!(repr("it's \"x\""), "'it\\'s \"x\"'");
        assert_eq!(repr("a\\b"), "'a\\\\b'");
    }

    #[test]
    fn only_printable_ascii_is_simple() {
        assert!(repr_is_simple("it's \"a\\b\" ~"));
        assert!(repr_is_simple(""));
        assert!(!repr_is_simple("caf\u{e9}"));
        assert!(!repr_is_simple("a\nb"));
        assert!(!repr_is_simple("\u{7f}"));
    }

    #[test]
    fn a_refusal_s_body_is_python_s_shape() {
        assert_eq!(
            refused_body(OTHER_CORPUS_WORDS),
            "{\"error\": \"this question needs a live worker grant for this corpus\", \
             \"kind\": \"PermissionError\"}"
        );
        assert_eq!(
            refused_body("a\"b\\c\u{e9}"),
            "{\"error\": \"a\\\"b\\\\c\\u00e9\", \"kind\": \"PermissionError\"}"
        );
    }
}
