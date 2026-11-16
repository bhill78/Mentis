//! The deletion ledger, checked on open (owner decision 2026-11-13, amendment D; Python's
//! `spine.erasure.ledger_check`, rule for rule). A permanent deletion appends one line to
//! `<brain dir>.erasures.jsonl`, OUTSIDE the Brain directory, so restoring a Brain backup does not
//! roll it back. A Brain that does not hold a deletion its ledger lists was restored from before
//! it: serving it would bring deleted content back. Python then refuses to serve it writable, and
//! its server does not start; the front refuses to open it, so neither serves it until the owner
//! re-applies the deletions (`python -m mentis.conversation.erasure reapply`).

use std::path::{Path, PathBuf};

use rusqlite::Connection;
use serde_json::Value as Json;

use crate::chain::{erasure_digest, erasure_marker};

/// `erasure.LEDGER_SUFFIX`.
pub const LEDGER_SUFFIX: &str = ".erasures.jsonl";
const DELETION_ACT: &str = "conversation-deleted";
const REAPPLIED_ACT: &str = "conversation-erasure-reapplied";

/// `erasure.ledger_path`: `normpath(abspath(root)) + LEDGER_SUFFIX`.
pub fn ledger_path(root: &Path) -> PathBuf {
    let absolute = std::path::absolute(root).unwrap_or_else(|_| root.to_path_buf());
    let mut text = absolute.to_string_lossy().into_owned();
    while text.len() > 1 && (text.ends_with('\\') || text.ends_with('/')) && !text.ends_with(":\\")
    {
        text.pop();
    }
    PathBuf::from(text + LEDGER_SUFFIX)
}

/// What says whether the ledger or its erase sets changed: each one's length and time of last
/// change, or that it isn't there. The directory's time moves when an erase set is added, removed
/// or renamed into it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Signature {
    ledger: Option<(u64, Option<std::time::SystemTime>)>,
    erase_sets: Option<Option<std::time::SystemTime>>,
}

/// The ledger's signature now.
pub fn signature(root: &Path) -> Signature {
    let ledger = std::fs::metadata(ledger_path(root))
        .ok()
        .map(|m| (m.len(), m.modified().ok()));
    let erase_sets = std::fs::metadata(erase_set_dir(root))
        .ok()
        .map(|m| m.modified().ok());
    Signature { ledger, erase_sets }
}

/// `erasure.erase_set_dir`: `normpath(abspath(root)) + ".erasures"`, one erase set per deletion.
pub fn erase_set_dir(root: &Path) -> PathBuf {
    let ledger = ledger_path(root).to_string_lossy().into_owned();
    PathBuf::from(ledger.trim_end_matches(".jsonl"))
}

/// One ledger line (or an erase set's intent, `from_sidecar`), or what can't be read.
enum Line {
    Entry(serde_json::Map<String, Json>),
    Unreadable(String),
}

fn sha256_of(bytes: &[u8]) -> String {
    crate::chain::sha256_hex(bytes)
}

/// `erasure.read_erase_set`: the line's erase set, read and checked against the digest the line
/// holds. `Err` says why it can't be.
fn read_erase_set(root: &Path, entry: &serde_json::Map<String, Json>) -> Result<(), String> {
    let name = match entry.get("erase_set") {
        Some(Json::String(name)) if !name.is_empty() => name,
        _ => return Err("this ledger line names no erase set".into()),
    };
    let data = std::fs::read(erase_set_dir(root).join(name)).map_err(|e| e.to_string())?;
    if entry.get("erase_set_digest").and_then(Json::as_str) != Some(sha256_of(&data).as_str()) {
        return Err("the erase set does not match its ledger line".into());
    }
    serde_json::from_slice::<Json>(&data).map_err(|e| e.to_string())?;
    Ok(())
}

/// `erasure.sidecar_intents`: erase sets no readable line of this corpus names. Each is a
/// deletion's intent, as a line would say it; one that can't be read is kept as such.
fn sidecar_intents(root: &Path, corpus_id: &str, lines: &[Line]) -> Vec<Line> {
    let dir = erase_set_dir(root);
    let Ok(listing) = std::fs::read_dir(&dir) else {
        return Vec::new();
    };
    let mut names: Vec<String> = listing
        .filter_map(|e| e.ok()?.file_name().into_string().ok())
        .filter(|n| n.ends_with(".json"))
        .collect();
    names.sort();
    let named: std::collections::HashSet<&str> = lines
        .iter()
        .filter_map(|l| match l {
            Line::Entry(e) => e.get("erase_set").and_then(Json::as_str),
            Line::Unreadable(_) => None,
        })
        .collect();
    let mut out = Vec::new();
    for name in names {
        if named.contains(name.as_str()) {
            continue;
        }
        let read = std::fs::read(dir.join(&name))
            .ok()
            .and_then(|data| Some((serde_json::from_slice::<Json>(&data).ok()?, data)));
        let Some((got, data)) = read else {
            out.push(Line::Unreadable(format!("erase set {name}")));
            continue;
        };
        if got.get("corpus_id").and_then(Json::as_str) != Some(corpus_id) {
            continue;
        }
        let mut intent = serde_json::Map::new();
        intent.insert("corpus_id".into(), got["corpus_id"].clone());
        intent.insert(
            "conversation".into(),
            got.get("conversation").cloned().unwrap_or(Json::Null),
        );
        intent.insert(
            "deletion".into(),
            got.get("deletion").cloned().unwrap_or(Json::Null),
        );
        intent.insert("digest".into(), Json::Null);
        intent.insert("rows".into(), Json::Null);
        intent.insert("erase_set".into(), Json::String(name));
        intent.insert("erase_set_digest".into(), Json::String(sha256_of(&data)));
        intent.insert("from_sidecar".into(), Json::Bool(true));
        out.push(Line::Entry(intent));
    }
    out
}

/// `erasure.ledger_entries(root, corpus_id)`: this corpus's lines; an unreadable one is kept.
fn ledger_entries(root: &Path, corpus_id: Option<&str>) -> Result<Vec<Line>, String> {
    let path = ledger_path(root);
    let text = match std::fs::read(&path) {
        Ok(bytes) => {
            String::from_utf8(bytes).map_err(|_| format!("{} is not UTF-8", path.display()))?
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("{}: {error}", path.display())),
    };
    let mut out = Vec::new();
    for raw in text.lines() {
        if raw.trim().is_empty() {
            continue;
        }
        match serde_json::from_str::<Json>(raw) {
            Ok(Json::Object(entry)) => {
                let theirs = entry.get("corpus_id");
                let ours = corpus_id.map(|c| Json::String(c.to_owned()));
                if corpus_id.is_none() || theirs == ours.as_ref() {
                    out.push(Line::Entry(entry));
                }
            }
            // Python reads a line that isn't an object as a failure to open, not a pass.
            Ok(_) => return Err(format!("a line of {} is not an object", path.display())),
            Err(_) => out.push(Line::Unreadable(raw.chars().take(200).collect())),
        }
    }
    Ok(out)
}

/// `erasure._deletion_holds`: the act is there, its erasure rows match the ledger's count and
/// digest, and every row they name holds its marker.
fn deletion_holds(
    conn: &Connection,
    deletion: Option<&str>,
    rows: Option<&Json>,
    digest: Option<&Json>,
) -> rusqlite::Result<bool> {
    let Some(deletion) = deletion else {
        return Ok(false);
    };
    let act: Option<i64> = conn
        .query_row(
            "SELECT 1 FROM operational WHERE id = ?1 AND act = ?2",
            (deletion, DELETION_ACT),
            |row| row.get(0),
        )
        .map(Some)
        .or_else(|e| match e {
            rusqlite::Error::QueryReturnedNoRows => Ok(None),
            other => Err(other),
        })?;
    if act.is_none() {
        return Ok(false);
    }
    let mut statement =
        conn.prepare("SELECT tbl, row_id, row_hash, residual FROM erasure WHERE deletion = ?1")?;
    let got: Vec<(String, String, String, String)> = statement
        .query_map([deletion], |r| {
            Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?))
        })?
        .collect::<Result<_, _>>()?;
    // `rows is not None and len(got) != rows`
    if let Some(rows) = rows.filter(|r| !r.is_null())
        && !rows.as_f64().is_some_and(|n| n == got.len() as f64)
    {
        return Ok(false);
    }
    if let Some(digest) = digest.filter(|d| !d.is_null()) {
        let ours = erasure_digest(
            got.iter()
                .map(|(t, i, h, r)| (t.as_str(), i.as_str(), h.as_str(), r.as_str())),
        );
        if digest.as_str() != Some(ours.as_str()) {
            return Ok(false);
        }
    }
    let marker = erasure_marker(deletion);
    for (table, id, _, _) in &got {
        let sql = match table.as_str() {
            "entry" => "SELECT body FROM entry WHERE id = ?1",
            "operational" => "SELECT detail FROM operational WHERE id = ?1",
            "delivery" => "SELECT material FROM delivery WHERE id = ?1",
            _ => return Ok(false),
        };
        let held: Option<Option<String>> = conn
            .query_row(sql, [id], |row| row.get(0))
            .map(Some)
            .or_else(|e| match e {
                rusqlite::Error::QueryReturnedNoRows => Ok(None),
                other => Err(other),
            })?;
        if held.flatten().as_deref() != Some(marker.as_str()) {
            return Ok(false);
        }
    }
    Ok(true)
}

/// `erasure.ledger_check` and `ledger_problems`: `None` when this Brain holds every deletion its
/// ledger lists for this corpus, otherwise the words a refusal says.
pub(crate) fn problems(conn: &Connection, root: &Path, corpus_id: &str) -> Option<String> {
    let mut entries = match ledger_entries(root, Some(corpus_id)) {
        Ok(entries) => entries,
        Err(why) => return Some(format!("the deletion ledger can't be read: {why}")),
    };
    let intents = sidecar_intents(root, corpus_id, &entries);
    entries.extend(intents);
    if entries.is_empty() {
        return None;
    }
    let check = || -> rusqlite::Result<Vec<(String, String)>> {
        let has_erasure: i64 = conn.query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'erasure'",
            [],
            |r| r.get(0),
        )?;
        let mut missing = Vec::new();
        for line in &entries {
            let entry = match line {
                Line::Unreadable(text) => {
                    missing.push((
                        format!("conversation None ({text})"),
                        "a ledger line or erase set is damaged; `check --repair` rewrites the \
                         ledger from the erase sets and the record"
                            .into(),
                    ));
                    continue;
                }
                Line::Entry(entry) => entry,
            };
            let named = |key: &str| entry.get(key).and_then(Json::as_str);
            let shown = format!(
                "conversation {} (deleted {} by {}, act {})",
                named("conversation").unwrap_or("None"),
                named("at_iso")
                    .map(str::to_owned)
                    .or_else(|| entry.get("at").map(|a| a.to_string()))
                    .unwrap_or_else(|| "None".into()),
                named("by").unwrap_or("None"),
                named("deletion").unwrap_or("None"),
            );
            if has_erasure == 0 {
                // Before 0002 a line fails only where this record holds its Conversation.
                let conversation = named("conversation").filter(|c| !c.is_empty());
                let present: i64 = match conversation {
                    Some(c) => {
                        conn.query_row("SELECT COUNT(*) FROM entry WHERE id = ?1", [c], |r| {
                            r.get(0)
                        })?
                    }
                    None => 0,
                };
                if present > 0 {
                    missing.push((
                        shown,
                        "this Brain predates erasure (schema 0002) and holds it".into(),
                    ));
                }
                continue;
            }
            if entry.get("from_sidecar") != Some(&Json::Bool(true))
                && let Err(why) = read_erase_set(root, entry)
            {
                missing.push((
                    shown,
                    format!(
                        "its erase set cannot be read ({why}); `check --repair` rebuilds it \
                         from the record"
                    ),
                ));
                continue;
            }
            let deletion = named("deletion");
            if deletion_holds(conn, deletion, entry.get("rows"), entry.get("digest"))? {
                continue;
            }
            // Re-applied here: a `conversation-erasure-reapplied` act naming it, whose own
            // deletion holds.
            let mut redone = false;
            if let Some(deletion) = deletion {
                let mut statement = conn.prepare(
                    "SELECT o.detail FROM operational o WHERE o.act = ?1 AND EXISTS \
                     (SELECT 1 FROM json_each(o.about) a WHERE a.value = ?2)",
                )?;
                let details: Vec<Option<String>> = statement
                    .query_map((REAPPLIED_ACT, deletion), |r| r.get(0))?
                    .collect::<Result<_, _>>()?;
                for detail in details.into_iter().flatten() {
                    let again = serde_json::from_str::<Json>(&detail)
                        .ok()
                        .and_then(|d| d.get("deletion").and_then(Json::as_str).map(str::to_owned))
                        .filter(|a| !a.is_empty());
                    if let Some(again) = again
                        && deletion_holds(conn, Some(&again), None, None)?
                    {
                        redone = true;
                        break;
                    }
                }
            }
            if redone {
                continue;
            }
            // Never in this record: nothing to serve.
            let conversation = named("conversation");
            let present: i64 = conn.query_row(
                "SELECT COUNT(*) FROM entry WHERE id = ?1",
                [conversation],
                |r| r.get(0),
            )?;
            if present == 0 {
                continue;
            }
            missing.push((shown, "its deletion is not in this Brain".into()));
        }
        Ok(missing)
    };
    // Python's opener lets a database error pass this check; so does this.
    let missing = check().ok()?;
    if missing.is_empty() {
        return None;
    }
    let names: Vec<String> = missing
        .iter()
        .take(10)
        .map(|(shown, why)| format!("{shown}: {why}"))
        .collect();
    let more = if missing.len() > 10 {
        format!(" and {} more", missing.len() - 10)
    } else {
        String::new()
    };
    Some(format!(
        "{} permanently deleted conversation(s) listed in {} are not deleted in this Brain -- \
         it was restored from a backup taken before, or a deletion's commit did not complete. \
         Serving or exporting it would bring deleted content back, so it is not opened: \
         {}{more}. Re-apply the deletions with `python -m mentis.conversation.erasure reapply \
         \"{}\" --by <owner>`: it completes exactly the deletions the owner asked for",
        missing.len(),
        ledger_path(root).display(),
        names.join("; "),
        root.display()
    ))
}
