//! Worker `check_rendering`: `render_check.check`, `about_unresolved` and `said` as a dry run says them,
//! over the UI's own readers. **The engine and the bundle are `mentis_extract`'s:** nothing here reads
//! Markdown. Python's module stays, whole, for what posting checks (`dispatch`, `respond`, `responses`)
//! until R7.
//!
//! **What this forwards, whole:**
//!
//! - **A draft that could hold a written choice.** `with_choices` warns of one when the run raised no
//!   decision, and that takes the grant's `instance`, which the mirror doesn't hold, and `choices.find`'s
//!   regular expressions. A choice is two or more list items, so a draft with fewer than two lines that
//!   could start one holds none, and its answer can't depend on either.
//! - **`syntax=`.** Its words are `renderers.py`'s, which composes every dispatch's prompt, and a second
//!   copy of them would be the known divergence the rules forbid.
//! - **Anything the engine fails at,** whose words name Python's own exception. And what the reader
//!   hands back that isn't a well-formed report.

use std::collections::HashMap;

use mentis_extract::MAX_CHARS;
use mentis_record::{READ_SCOPE_LIMIT, ReadClass, ReadScope, RecordReader};
use serde_json::{Map, Value};

use crate::pyjson::{self, Py, dict};
use crate::window::reads::{CONTRIBUTION, CONVERSATION, heads};
use crate::window::{Prepared, Window, python_says};
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest, python};

/// `render_check.BUILD_FILE`.
const BUILD_FILE: &str = "build-identity.json";

const DRY_RUN: &str = "a dry run: nothing was written. ";
const CLEAN: &str = "No problems: every marked block in it renders.";

/// Whether this line could start a list item: `ITEM`, `conversation/choices.py:52`, read generously.
fn could_be_an_item(line: &str) -> bool {
    let line = line.trim_start_matches(python::is_space);
    line.chars()
        .next()
        .is_some_and(|c| matches!(c, '-' | '*' | '+') || c.is_numeric())
}

/// Whether `choices.find` could find anything in this text: both its readings take two items.
pub fn could_hold_a_choice(text: &str) -> bool {
    text.split('\n')
        .filter(|line| could_be_an_item(line))
        .count()
        >= 2
}

fn is_int(value: Option<&Py>) -> bool {
    matches!(value, Some(Py::Int(_)))
}

/// `malformed(report) is None`: what everything downstream reads a report as.
fn well_formed(report: &Py) -> bool {
    if !report.is_dict() {
        return false;
    }
    if !["blocks", "errors", "warnings"]
        .iter()
        .all(|name| is_int(report.get(name)))
    {
        return false;
    }
    let Some(problems) = report.get("problems").and_then(Py::as_list) else {
        return false;
    };
    problems.iter().all(|problem| {
        let words = |name: &str| matches!(problem.get(name), Some(Py::Str(_)));
        let words_or_none =
            |name: &str| matches!(problem.get(name), None | Some(Py::None | Py::Str(_)));
        problem.is_dict()
            && words("block")
            && is_int(problem.get("line"))
            && words("severity")
            && words("where")
            && words("message")
            && words_or_none("type")
            && words_or_none("fix")
            && (problem.get("part").is_none() || is_int(problem.get("part")))
    })
}

/// `str(value)` of an int this report was checked to hold.
fn digits(value: Option<&Py>) -> &str {
    match value {
        Some(Py::Int(digits)) => digits,
        _ => "",
    }
}

fn said_of(value: Option<&Py>) -> &str {
    value.and_then(Py::as_str).unwrap_or("")
}

/// `said(report, posted=False)` of a well-formed checked report.
fn said(report: &Py) -> Option<String> {
    let problems = report.get("problems").and_then(Py::as_list)?;
    if problems.is_empty() {
        return None;
    }
    let mut lines = vec![format!(
        "{} error(s) and {} warning(s) in its Markdown blocks: a block with an error is shown as \
         readable source instead of being drawn. Fix them before posting.",
        digits(report.get("errors")),
        digits(report.get("warnings"))
    )];
    for problem in problems {
        let place = match problem.get("part") {
            Some(part) => format!("part {}, ", digits(Some(part))),
            None => String::new(),
        };
        let kind = problem
            .get("type")
            .and_then(Py::as_str)
            .filter(|kind| !kind.is_empty())
            .unwrap_or("bare fence");
        let mut line = format!(
            "- block {} ({kind}), {place}line {}, {} ({}): {}",
            said_of(problem.get("block")),
            digits(problem.get("line")),
            said_of(problem.get("severity")),
            said_of(problem.get("where")),
            said_of(problem.get("message")),
        );
        if let Some(fix) = problem
            .get("fix")
            .and_then(Py::as_str)
            .filter(|fix| !fix.is_empty())
        {
            line.push_str(" Fix: ");
            line.push_str(fix);
        }
        lines.push(line);
    }
    Some(lines.join("\n"))
}

/// `about=` ids a report names: what `about_unresolved` asks the record, in its order.
fn about_ids(report: &Py) -> Result<Vec<&str>, OpError> {
    let about = match report.get("about") {
        None => return Ok(Vec::new()),
        Some(about) if !about.truthy() => return Ok(Vec::new()),
        Some(Py::List(about)) => about,
        Some(_) => return Err(python_says("an about that isn't a list")),
    };
    let mut out = Vec::new();
    for row in about {
        if !row.is_dict() {
            return Err(python_says("an about row that isn't an object"));
        }
        let ids = match row.get("ids") {
            None => continue,
            Some(ids) if !ids.truthy() => continue,
            Some(Py::List(ids)) => ids,
            Some(_) => return Err(python_says("about ids that aren't a list")),
        };
        for id in ids {
            let id = id
                .as_str()
                .ok_or_else(|| python_says("an about id that isn't text"))?;
            out.push(id);
        }
    }
    Ok(out)
}

struct KindsOf;

impl ReadOp for KindsOf {
    type Args = Vec<String>;
    type Row = Prepared<HashMap<String, Option<String>>>;

    const NAME: &'static str = "about-kinds";
    /// `corpus.heads`.
    const BUDGET: Budget = Budget { statements: 1 };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<Vec<String>>,
    ) -> Result<ReadAnswer<Self::Row>, OpError> {
        let ids: Vec<&str> = request.args.iter().map(String::as_str).collect();
        let kinds = heads(scope, &ids)?
            .into_iter()
            .map(|(id, head)| (id, head.kind))
            .collect();
        Ok(ReadAnswer {
            rows: vec![Prepared(kinds)],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}

/// `about_unresolved`: the report, with a warning for each `about=` id the record doesn't hold as a Topic,
/// Conversation or post. Its problems and warnings stay where they were.
fn with_about(mut report: Py, record: &dyn RecordReader, class: ReadClass) -> Result<Py, OpError> {
    let ids: Vec<String> = about_ids(&report)?.into_iter().map(str::to_owned).collect();
    if ids.is_empty() {
        return Ok(report);
    }
    let request = ReadRequest {
        args: ids,
        cursor: None,
        limit: None,
        deadline: std::time::Instant::now() + READ_SCOPE_LIMIT,
    };
    let mut read = crate::run(&KindsOf, record, class, &request)?;
    let Prepared(kinds) = read.rows.pop().ok_or_else(|| python_says("no kinds"))?;
    let mut extra: Vec<Py> = Vec::new();
    let empty: Vec<Py> = Vec::new();
    let rows = report.get("about").and_then(Py::as_list).unwrap_or(&empty);
    for row in rows {
        let ids = row.get("ids").and_then(Py::as_list).unwrap_or(&[]);
        for id in ids {
            let id = id.as_str().unwrap_or("");
            let why = match kinds.get(id) {
                None => "Mentis holds no entry with that id".to_owned(),
                Some(Some(kind))
                    if kind == "topic" || kind == CONVERSATION || kind == CONTRIBUTION =>
                {
                    continue;
                }
                Some(kind) => format!(
                    "it is a {}, not a Topic, Conversation or post",
                    kind.as_deref().unwrap_or("None")
                ),
            };
            let of_row = |name: &str| {
                row.get(name)
                    .cloned()
                    .ok_or_else(|| python_says("an about row short of a field"))
            };
            let mut warning = dict([
                ("block", of_row("block")?),
                ("type", Py::str("timer")),
                ("line", of_row("line")?),
                ("where", Py::str("about")),
                ("severity", Py::str("warning")),
                (
                    "message",
                    Py::Str(format!(
                        "about= names {id}, but {why}: it is shown as unresolved, and no time \
                         spent is added up for it."
                    )),
                ),
                (
                    "fix",
                    Py::Str(format!(
                        "Replace {id} with the id of an existing Topic, Conversation or post, \
                         found with the tools."
                    )),
                ),
                ("from", Py::str("check")),
            ]);
            if let Some(part) = row.get("part") {
                warning.set("part", part.clone());
            }
            extra.push(warning);
        }
    }
    if extra.is_empty() {
        return Ok(report);
    }
    let warnings: i128 = digits(report.get("warnings"))
        .parse()
        .map_err(|_| python_says("warnings past what this holds"))?;
    let added = i128::try_from(extra.len()).map_err(|_| python_says("too many warnings"))?;
    report.set("warnings", Py::int(warnings + added));
    let mut problems = report
        .get("problems")
        .and_then(Py::as_list)
        .unwrap_or(&[])
        .to_vec();
    problems.extend(extra);
    report.set("problems", Py::List(problems));
    Ok(report)
}

/// `_engine`'s `renderer`. A build identity that isn't there is none, as Python's `except` has it; one
/// that's there and this can't read is Python's to say.
fn renderer(window: &Window, bundle: &mentis_extract::Bundle) -> Result<Py, OpError> {
    let built = window
        .beside_bundle(BUILD_FILE)
        .and_then(|path| std::fs::read(path).ok())
        .and_then(|bytes| String::from_utf8(bytes).ok());
    let built = match built {
        None => Py::None,
        Some(text) => pyjson::loads(&text).ok_or_else(|| python_says("a build identity"))?,
    };
    if built.truthy() && !built.is_dict() {
        return Err(python_says("a build identity that isn't an object"));
    }
    let of_built = |name: &str| built.get(name).cloned().unwrap_or(Py::None);
    Ok(dict([
        ("bundle", Py::Str(window.bundle_text())),
        ("sha256", Py::str(&bundle.digest[..16])),
        ("built_from", of_built("commit")),
        ("built_dirty", of_built("dirty")),
    ]))
}

/// `{"ok": True, **got, "note": ...}`.
fn dry_run(got: Py, words: &str) -> Py {
    let mut out = dict([("ok", Py::Bool(true))]);
    if let Py::Dict(fields) = got {
        for (name, value) in fields {
            out.set(&name, value);
        }
    }
    out.set("note", Py::Str(format!("{DRY_RUN}{words}")));
    out
}

fn check_text(
    text: &str,
    window: &Window,
    record: &dyn RecordReader,
    class: ReadClass,
) -> Result<Py, OpError> {
    let length = text.chars().count();
    if length > MAX_CHARS {
        let why = format!("the text is {length} characters; the check reads at most {MAX_CHARS}");
        let words = format!("Its Markdown was NOT checked for rendering: {why}");
        let got = dict([("checked", Py::Bool(false)), ("why_not", Py::Str(why))]);
        return Ok(dry_run(got, &words));
    }
    let bundle = window.bundle()?;
    let answer = window
        .engines
        .check(&bundle, text)
        .map_err(|why| python_says(&why.to_string()))?;
    let report = pyjson::loads(&answer)
        .filter(well_formed)
        .ok_or_else(|| python_says("a report this can't read"))?;
    let mut got = dict([("checked", Py::Bool(true))]);
    if let Py::Dict(fields) = report {
        for (name, value) in fields {
            if name != "types" {
                got.set(&name, value);
            }
        }
    }
    got.set("renderer", renderer(window, &bundle)?);
    let got = with_about(got, record, class)?;
    let words = said(&got).unwrap_or_else(|| CLEAN.to_owned());
    Ok(dry_run(got, &words))
}

/// `_result`'s `check_rendering` branch, and the door's `with_choices` of it, where neither can say
/// anything here that this doesn't. `args` is `payload["args"]`.
pub fn check_rendering(
    args: &Map<String, Value>,
    window: &Window,
    record: &dyn RecordReader,
    class: ReadClass,
) -> Result<Py, OpError> {
    let given = |name: &str| match args.get(name) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(words)) => Ok(Some(words.as_str())),
        Some(_) => Err(python_says("a value this door doesn't coerce")),
    };
    let text = given("text")?.filter(|text| !text.is_empty());
    let syntax = given("syntax")?.filter(|syntax| !syntax.is_empty());
    let Some(text) = text else {
        if syntax.is_some() {
            return Err(python_says("the blocks' rules are renderers.py's"));
        }
        return Ok(dict([
            ("ok", Py::Bool(false)),
            (
                "error",
                Py::str("give `text` to check, or `syntax` (a block name, or all)"),
            ),
        ]));
    };
    if text.contains('\0') {
        return Err(python_says(
            "a NUL, which only Python's engine can say what it does with",
        ));
    }
    if could_hold_a_choice(text) {
        return Err(python_says("a draft that could hold a written choice"));
    }
    check_text(text, window, record, class)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_choice_takes_two_lines_that_could_start_items() {
        assert!(!could_hold_a_choice("plain\ntext"));
        assert!(!could_hold_a_choice("- one item only\nand words"));
        assert!(could_hold_a_choice("- a\n- b"));
        assert!(could_hold_a_choice("  1. a\n\u{a0}* b"));
        assert!(could_hold_a_choice("\u{663}) a\n+ b"));
        assert!(could_hold_a_choice("```checklist\n- [ ] a\n- [ ] b\n```"));
    }

    fn report(text: &str) -> Py {
        pyjson::loads(text).unwrap()
    }

    #[test]
    fn a_report_is_held_to_what_malformed_holds_it_to() {
        let good = r#"{"blocks": 1, "errors": 0, "warnings": 0, "problems": []}"#;
        assert!(well_formed(&report(good)));
        for bad in [
            r#"[]"#,
            r#"{"blocks": 1, "errors": 0, "warnings": 0}"#,
            r#"{"blocks": true, "errors": 0, "warnings": 0, "problems": []}"#,
            r#"{"blocks": 1, "errors": 0, "warnings": 0, "problems": [1]}"#,
            r#"{"blocks": 1, "errors": 0, "warnings": 0, "problems": [{"block": "b"}]}"#,
        ] {
            assert!(!well_formed(&report(bad)), "{bad}");
        }
    }

    #[test]
    fn what_a_dry_run_says_of_a_problem() {
        let got = report(
            r#"{"errors": 1, "warnings": 0, "problems": [
                {"block": "b1", "type": "chart", "line": 3, "severity": "error",
                 "where": "body", "message": "bad", "fix": "Do this."},
                {"block": "b2", "type": null, "line": 9, "part": 2, "severity": "warning",
                 "where": "info", "message": "odd", "fix": ""}]}"#,
        );
        assert_eq!(
            said(&got).unwrap(),
            "1 error(s) and 0 warning(s) in its Markdown blocks: a block with an error is shown \
             as readable source instead of being drawn. Fix them before posting.\n\
             - block b1 (chart), line 3, error (body): bad Fix: Do this.\n\
             - block b2 (bare fence), part 2, line 9, warning (info): odd"
        );
        assert_eq!(said(&report(r#"{"problems": []}"#)), None);
    }
}
