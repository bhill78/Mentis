//! The collection-scoped read: the latest present admissions of a DECLARED collection, optionally
//! under a path prefix, each one row with its own `adm-…@<digest12>` citation.
//!
//! WHICH CONNECTORS THIS READS, AND WHY NO LIST SAYS SO. The exact-file reader used to admit
//! `filesystem` and nothing else, by naming it in SQL. Nothing here names a connector. A `file`
//! source is read when the record shows it can be: the collection is DECLARED (the declaration says
//! which connector it is), and each object's latest Admission is that same connector's, present, held,
//! text, with a `sha256:` locator whose bytes verify. Only an implemented connector can have written
//! such a row -- `mentis.sources.registry._module` refuses an unavailable descriptor before anything is
//! acquired -- so "what the registry reports available" is exactly what this reads, derived rather than
//! listed. `git` reads today without a word about git here, and a connector that becomes available
//! reads the moment it admits its first object, with no change in this crate.
//!
//! A git collection's commit objects (`.git/commits/<sha>`, `text/x-git-commit`) are rows like any
//! other: nothing here knows a commit from a file.
//!
//! BOUNDS, all three stated and tested. [`OBJECTS_MOST`] objects per source; one row carries at most
//! `held_file::ROW_BYTES_MOST` (64 KiB, the existing cap) and says what it omitted; [`ROWS_MOST`] rows
//! in one batch across every collection-scoped source. The scan that finds the objects is bounded too
//! ([`ADMISSIONS_MOST`]), and a source whose history is longer than that says so rather than claiming
//! to have read it all.
//!
//! ABSENCE IS REPORTED, NEVER SILENTLY DROPPED (`mentis/sources/git.py:52-61`). An object whose latest
//! observation is absent, whose bytes were purged, which is not text, or whose bytes will not verify is
//! counted and named in the source's `reason`, and the source says `partial`. A collection all of whose
//! objects are like that is `unavailable`, never `ok` with nothing in it.

use std::collections::HashSet;

use mentis_record::{Flow, Param, ReadScope};
use serde_json::Value as Json;

use super::held_file::{self, Choice};
use crate::{
    OpError,
    pyjson::{self, Py},
    window::Window,
};

/// ROWS one collection-scoped source may take, and separately the objects it may REPORT as
/// unreadable. The two are counted apart on purpose: a real git collection holds `.git/changes/*`
/// change evidence that is never text, and if those shared the row budget they would crowd out the
/// commits and documents the source exists to read. Deciding an object is unreadable costs no disk
/// read -- only a row's bytes are opened and verified -- and the scan behind both is bounded by
/// [`ADMISSIONS_MOST`], so the work stays bounded either way.
pub const OBJECTS_MOST: usize = 100;
/// Rows one batch may hold across every collection-scoped source. Twenty sources at
/// [`OBJECTS_MOST`] each would be 2,000 rows of up to 64 KiB; this is the bound that keeps a batch
/// inside the 25 MiB an activation artifact may be.
pub const ROWS_MOST: usize = 200;
/// Admissions one source's scan reads to find those objects' latest observations. A collection with a
/// longer history than this is read as far as this reaches, and says so.
pub const ADMISSIONS_MOST: usize = 4_000;
/// Objects a `reason` names before it says "and N more".
const NAMED_MOST: usize = 8;

/// The latest Admissions of one collection, chosen and checked, with nothing read from disk yet.
pub(super) struct Collected {
    collection: String,
    rows: Vec<Candidate>,
    /// Objects found and not readable, with why, in the record's own order.
    skipped: Vec<(String, &'static str)>,
    /// Objects past [`OBJECTS_MOST`] or [`ROWS_MOST`], and which bound stopped them.
    left: usize,
    bound: Bound,
    /// Unreadable objects past the count one source names, counted rather than named.
    unreported: usize,
    /// Whether the scan itself reached [`ADMISSIONS_MOST`], so earlier objects may not have been seen.
    scan_full: bool,
}

struct Candidate {
    reference: String,
    digest: String,
    object: String,
    at: Py,
}

/// Which bound stopped reading further objects, said from the constant itself.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Bound {
    None,
    Objects,
    Rows,
}

impl Bound {
    fn said(self) -> String {
        match self {
            Bound::None | Bound::Objects => {
                format!("the {OBJECTS_MOST} objects one source reads")
            }
            Bound::Rows => format!("the {ROWS_MOST} rows one batch holds"),
        }
    }
}

fn unavailable(why: &str) -> OpError {
    OpError::NotFound {
        what: format!("collection unavailable: {why}"),
    }
}

/// THE CONNECTOR THE RECORD SAYS THIS COLLECTION IS. The newest `source-collection-declared` act for
/// it; a collection nobody declared is read by nothing, whatever a definition says.
pub(super) fn declared_connector(
    scope: &mut dyn ReadScope,
    collection: &str,
) -> Result<String, OpError> {
    let mut connector = None;
    scope.query(
        "SELECT json_extract(detail,'$.connector') FROM operational \
         WHERE act='source-collection-declared' \
         AND json_extract(detail,'$.collection')=?1 ORDER BY seq DESC LIMIT 1",
        &[Param::Text(collection)],
        &mut |row| {
            connector = row.value(0)?.text().map(str::to_owned);
            Ok(Flow::Stop)
        },
    )?;
    let connector =
        connector.ok_or_else(|| unavailable("no collection of that id is declared here"))?;
    if connector.is_empty() || connector.len() > 64 {
        return Err(unavailable("the declaration names no connector"));
    }
    Ok(connector)
}

/// What a collection-scoped `file` source comes to, within what is left of the batch's rows.
///
/// `left` is the batch's remaining row allowance and is decremented by what this claims, so twenty
/// sources cannot each take [`OBJECTS_MOST`].
pub(super) fn prepare(
    scope: &mut dyn ReadScope,
    source: &Py,
    left: &mut usize,
) -> Result<Collected, OpError> {
    let Some((collection, choice)) = held_file::choice(source) else {
        return Err(unavailable(held_file::CHOICE_REFUSED));
    };
    let prefix = match &choice {
        Choice::Whole => None,
        Choice::Prefix(p) => Some(p.clone()),
        // The exact form is `held_file`'s; a caller that sent it here is a defect, not a refusal.
        Choice::Exact(_) => return Err(unavailable("one exact path is read as one held file")),
    };
    let connector = declared_connector(scope, &collection)?;
    let source_id = format!("{connector}:{collection}");
    // NEWEST FIRST, AND THE FIRST ROW OF AN OBJECT IS ITS LATEST, by the record's own append order --
    // never by timestamp, exactly as `mentis.sources.latest` has it. An object seen once is settled, so
    // the scan never reads a collection's whole history to answer for one object.
    let mut seen: HashSet<String> = HashSet::new();
    let mut rows: Vec<Candidate> = Vec::new();
    let mut skipped: Vec<(String, &'static str)> = Vec::new();
    let mut scanned = 0usize;
    let mut left_over = 0usize;
    let mut bound = Bound::None;
    let mut unreported = 0usize;
    let mut purge_checks: Vec<usize> = Vec::new();
    scope.query(
        "SELECT id, body, json_extract(body,'$.envelope.bulk_source.object') FROM entry \
         WHERE family='admission' AND json_extract(body,'$.source')=?1 \
         ORDER BY seq DESC LIMIT ?2",
        &[
            Param::Text(&source_id),
            Param::Integer(ADMISSIONS_MOST as i64),
        ],
        &mut |row| {
            scanned += 1;
            let (Some(reference), Some(raw), Some(object)) = (
                row.value(0)?.text(),
                row.value(1)?.text(),
                row.value(2)?.text(),
            ) else {
                return Ok(Flow::Continue);
            };
            if !seen.insert(object.to_owned()) {
                return Ok(Flow::Continue);
            }
            if let Some(prefix) = &prefix
                && !object.starts_with(prefix.as_str())
            {
                return Ok(Flow::Continue);
            }
            if rows.len() >= OBJECTS_MOST {
                left_over += 1;
                bound = Bound::Objects;
                return Ok(Flow::Continue);
            }
            if rows.len() >= *left {
                left_over += 1;
                bound = Bound::Rows;
                return Ok(Flow::Continue);
            }
            match candidate(reference, raw, &connector, &collection, object) {
                Ok(one) => {
                    purge_checks.push(rows.len());
                    rows.push(one);
                }
                // Reported, never silently dropped -- and bounded on its own count, so a collection
                // full of change evidence still answers with its readable rows.
                Err(why) if skipped.len() < OBJECTS_MOST => {
                    skipped.push((object.to_owned(), why))
                }
                Err(_) => unreported += 1,
            }
            Ok(Flow::Continue)
        },
    )?;
    // A PURGE IS THE RECORD'S, so it is asked of each kept Admission, not inferred.
    let mut purged = Vec::new();
    for at in purge_checks {
        if held_file::purged(scope, &rows[at].reference)? {
            purged.push(at);
        }
    }
    for at in purged.into_iter().rev() {
        let one = rows.remove(at);
        skipped.push((one.object, "its bytes were purged"));
    }
    *left -= rows.len();
    Ok(Collected {
        collection,
        rows,
        skipped,
        left: left_over,
        bound,
        unreported,
        scan_full: scanned >= ADMISSIONS_MOST,
    })
}

/// One object's latest Admission, as a row to read, or why it is not one. Every check the exact-file
/// reader makes, per object: the provenance agrees with the declaration, the state is present and held,
/// the bytes are text, and the locator is a digest.
fn candidate(
    reference: &str,
    raw: &str,
    connector: &str,
    collection: &str,
    object: &str,
) -> Result<Candidate, &'static str> {
    let body: Json = serde_json::from_str(raw).map_err(|_| "its observation cannot be read")?;
    let o = &body["envelope"]["bulk_source"];
    if o["connector"] != connector || o["collection"] != collection || o["object"] != object {
        return Err("its observation's provenance disagrees with the declaration");
    }
    if o["state"] != "present" || body["content"] != "held" {
        return Err("its latest observation is absent or not held");
    }
    if o["encoding"]["text"] != true {
        return Err("it is not text");
    }
    let digest = held_file::digest_of(&body).ok_or("it has no digest locator")?;
    let at = body["admitted_at"]
        .as_f64()
        .filter(|n| n.is_finite())
        .ok_or("it records no acquisition time")?;
    Ok(Candidate {
        reference: reference.to_owned(),
        digest,
        object: object.to_owned(),
        at: pyjson::loads(&at.to_string()).expect("finite time"),
    })
}

/// What this source answers once the scope has gone: `(rows, status, reason)`. Each row's bytes are
/// verified against its digest, so one damaged object is reported and the rest still answer.
pub(super) fn finish(
    collected: Collected,
    window: &Window,
    stop: &dyn Fn() -> bool,
) -> (Vec<Py>, &'static str, Option<String>) {
    let Collected {
        collection,
        rows,
        mut skipped,
        left,
        bound,
        unreported,
        scan_full,
    } = collected;
    let mut results = Vec::with_capacity(rows.len());
    let mut shortened = 0usize;
    let mut busy = None;
    for candidate in rows {
        if stop() {
            busy = Some("the read's deadline ended before every object was read".to_owned());
            break;
        }
        match held_file::verified_bytes(window, &candidate.digest, stop) {
            Ok(bytes) => {
                let (row, cut) = held_file::row(
                    &candidate.reference,
                    &candidate.digest,
                    &collection,
                    &candidate.object,
                    candidate.at,
                    bytes,
                );
                shortened += usize::from(cut);
                results.push(row);
            }
            Err(OpError::Busy { why }) => {
                busy = Some(why);
                break;
            }
            Err(_) => skipped.push((candidate.object, "its retained bytes do not read or verify")),
        }
    }
    let mut said: Vec<String> = Vec::new();
    if !skipped.is_empty() {
        let named: Vec<String> = skipped
            .iter()
            .take(NAMED_MOST)
            .map(|(object, why)| format!("{object} ({why})"))
            .collect();
        let more = skipped.len().saturating_sub(named.len()) + unreported;
        said.push(format!(
            "{} of its objects were not read: {}{}",
            skipped.len() + unreported,
            named.join("; "),
            if more > 0 {
                format!("; and {more} more")
            } else {
                String::new()
            }
        ));
    }
    if left > 0 {
        said.push(format!(
            "{left} further objects are past {}",
            bound.said()
        ));
    }
    if scan_full {
        said.push(format!(
            "its newest {ADMISSIONS_MOST} admissions were read, and an object older than those was \
             not looked for"
        ));
    }
    if shortened > 0 {
        said.push(format!(
            "{shortened} rows carry only their first {} UTF-8 bytes; each says what it omitted and \
             where to read on",
            held_file::ROW_BYTES_MOST
        ));
    }
    if let Some(why) = busy {
        said.push(why);
    }
    let status = if results.is_empty() {
        "unavailable"
    } else if said.is_empty() {
        "ok"
    } else {
        "partial"
    };
    let reason = if said.is_empty() {
        (status == "unavailable").then(|| {
            "nothing in this collection could be read; see its objects' history".to_owned()
        })
    } else {
        Some(said.join(". "))
    };
    (results, status, reason)
}
