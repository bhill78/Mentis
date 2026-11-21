//! Additive, read-only decision presentation. This never interprets an answer or grants authority.
//! Mirrors `mentis.decision_presentation.fields`. Uncertain version-1 validation stays on Python,
//! just as values the existing record readers cannot represent do.

use serde::Serialize;

use crate::pyjson::{Py, loads};
use crate::stored::{Object, Stored, python_says};
use crate::{OpError, python};

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Problem {
    pub path: String,
    pub code: String,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Status {
    pub state: String,
    pub problems: Vec<Problem>,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Fields {
    // Missing and explicitly null are different; unknown stored versions remain untouched.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub presentation: Option<Stored>,
    pub presentation_status: Status,
}

fn value(v: &Stored) -> Result<Py, OpError> {
    loads(v.text()).ok_or_else(|| python_says("decision presentation Python has to read"))
}

fn valid_text(v: Option<&Py>, limit: usize) -> bool {
    v.and_then(Py::as_str).is_some_and(|s| {
        let s = python::strip(s);
        !s.is_empty() && s.chars().count() <= limit
    })
}

fn reference(v: &Py) -> bool {
    let Py::Dict(items) = v else { return false };
    if !valid_text(v.get("label"), 160) {
        return false;
    }
    let keys: &[&str] = match v.get("kind").and_then(Py::as_str) {
        Some("record") => {
            let Some(id) = v.get("id").and_then(Py::as_str) else {
                return false;
            };
            let Some(rest) = ["ent-", "opr-", "adm-"]
                .iter()
                .find_map(|p| id.strip_prefix(p))
            else {
                return false;
            };
            if rest.is_empty() || !rest.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-') {
                return false;
            }
            &["kind", "label", "id"]
        }
        Some("commit") => {
            if !valid_text(v.get("repository"), 2000) {
                return false;
            }
            let Some(sha) = v.get("sha").and_then(Py::as_str) else {
                return false;
            };
            if sha.len() != 40 || !sha.bytes().all(|b| b.is_ascii_hexdigit()) {
                return false;
            }
            &["kind", "label", "repository", "sha"]
        }
        // urllib URL parsing and its malformed-input diagnostics belong to Python.
        _ => return false,
    };
    items.iter().all(|(key, _)| keys.contains(&key.as_str()))
}

fn generic_approval(question: &str) -> bool {
    // Python re.I's four extra ASCII-letter equivalents.
    let q: String = question
        .chars()
        .map(|c| match c {
            '\u{130}' | '\u{131}' => 'i',
            '\u{17f}' => 's',
            '\u{212a}' => 'k',
            other => other.to_ascii_lowercase(),
        })
        .collect();
    matches!(
        q.trim_end_matches(['?', '.', '!', ' ']),
        "approve this work" | "approve the work"
    )
}

/// Prove the supported structural contract, without normalizing stored data. A false result
/// forwards the whole read so Python supplies its own field-specific incomplete diagnostics.
fn complete(d: &Py, because: Option<&str>, meta: &Py) -> bool {
    if !valid_text(d.get("question"), 1000) || !valid_text(because.map(Py::str).as_ref(), 2000) {
        return false;
    }
    let Py::Dict(items) = meta else { return false };
    let keys = [
        "version",
        "type",
        "scope",
        "stages",
        "primary",
        "primary_reason",
        "supporting",
        "applies_when",
    ];
    if items.iter().any(|(k, _)| !keys.contains(&k.as_str())) {
        return false;
    }
    let Some(typ) = meta.get("type").and_then(Py::as_str) else {
        return false;
    };
    if ![
        "artifact_approval",
        "action_approval",
        "choice",
        "free_response",
    ]
    .contains(&typ)
        || !valid_text(meta.get("scope"), 2000)
    {
        return false;
    }
    let Some(stages) = meta.get("stages").and_then(Py::as_list) else {
        return false;
    };
    if stages.iter().any(|s| {
        !s.as_str().is_some_and(|s| {
            [
                "design",
                "implementation",
                "integration",
                "deployment",
                "other",
            ]
            .contains(&s)
        })
    }) {
        return false;
    }
    let approval = matches!(typ, "artifact_approval" | "action_approval");
    if approval
        && (stages.is_empty()
            || generic_approval(python::strip(
                d.get("question").and_then(Py::as_str).unwrap(),
            )))
    {
        return false;
    }
    match meta.get("primary") {
        Some(Py::None) if typ != "artifact_approval" => {
            if !valid_text(meta.get("primary_reason"), 2000) {
                return false;
            }
        }
        Some(primary) if reference(primary) => {}
        _ => return false,
    }
    if let Some(refs) = meta.get("supporting") {
        let Some(refs) = refs.as_list() else {
            return false;
        };
        if refs.len() > 24 || !refs.iter().all(reference) {
            return false;
        }
    }
    for (key, limit) in [("applies_when", 1000), ("primary_reason", 2000)] {
        if meta.get(key).is_some() && !valid_text(meta.get(key), limit) {
            return false;
        }
    }
    if typ == "free_response" && d.get("options").is_some() {
        return false;
    }
    let opts = match d.get("options") {
        Some(Py::Str(s)) => loads(s).unwrap_or_else(|| Py::str(s)),
        Some(v) => v.clone(),
        None => Py::None,
    };
    if matches!(opts, Py::None) {
        return typ != "choice";
    }
    let Some(opts) = opts.as_list() else {
        return false;
    };
    if opts.len() < 2 {
        return false;
    }
    let mut labels = std::collections::HashSet::new();
    for opt in opts {
        if !valid_text(opt.get("label"), 200) || !valid_text(opt.get("consequence"), 2000) {
            return false;
        }
        let label = python::strip(opt.get("label").and_then(Py::as_str).unwrap());
        // Rust lowercasing is not Python casefold. Let Python classify Unicode option labels.
        if !label.is_ascii() || !labels.insert(label.to_ascii_lowercase()) {
            return false;
        }
    }
    true
}

pub fn fields(detail: &Object, because: Option<&str>) -> Result<Fields, OpError> {
    let d = value(&Stored::of(detail))?;
    let meta = d.get("presentation");
    let mut problems = Vec::new();
    let mut bad = |path: &str, code: &str| {
        problems.push(Problem {
            path: path.into(),
            code: code.into(),
        })
    };
    let state = match meta {
        None => {
            if !d.get("question").is_some_and(Py::truthy) {
                bad("question", "required");
            }
            if because.is_none_or(str::is_empty) {
                bad("because", "required");
            }
            if let Some(opts) = d.get("options").and_then(Py::as_list) {
                for (i, opt) in opts.iter().enumerate() {
                    if !opt.is_dict() || !opt.get("consequence").is_some_and(Py::truthy) {
                        bad(&format!("options[{i}].consequence"), "required");
                    }
                }
            }
            if d.get("question").and_then(Py::as_str).is_some_and(|q| {
                let n = "approve this work?".len();
                q.get(..n)
                    .is_some_and(|s| s.eq_ignore_ascii_case("approve this work?"))
            }) {
                bad("presentation.scope", "not_recorded");
            }
            if problems.is_empty() {
                "legacy"
            } else {
                "incomplete"
            }
        }
        Some(meta)
            if meta.is_dict() && !matches!(meta.get("version"), Some(Py::Int(v)) if v == "1") =>
        {
            bad("presentation.version", "unsupported_version");
            "unsupported"
        }
        Some(meta) if complete(&d, because, meta) => "complete",
        Some(_) => {
            return Err(python_says(
                "incomplete or unclassified decision presentation",
            ));
        }
    };
    Ok(Fields {
        presentation: detail.get("presentation").cloned(),
        presentation_status: Status {
            state: state.into(),
            problems,
        },
    })
}
