//! The chain codec and verifier: `docs/rust/R1-acceptance.md`, section G, from
//! `spine/store.py:458-548,567-592`. Rust must produce the same bytes and the same answer.

use std::collections::HashMap;
use std::fmt;
use std::fmt::Write as _;
use std::time::{Duration, Instant};

use sha2::{Digest, Sha256};

use crate::{
    CHAINED_TABLES, ChainBreak, ChainReport, ChainVerifier, ErasureBroken, Erasures, Flow, Param,
    ReadClass, ReadScope, RecordError, RecordReader, Row, TableChain, Value,
};

const RS: u8 = 0x1e;

/// A value the codec refuses, where Python's encoding fails or the value has no stable text.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CodecRefused {
    /// Infinity or NaN.
    NonFinite,
    /// Text that isn't UTF-8, a lone surrogate among them: Python's encoding fails on it too.
    NotUtf8,
}

impl fmt::Display for CodecRefused {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            CodecRefused::NonFinite => "a non-finite float",
            CodecRefused::NotUtf8 => "text that is not UTF-8",
        })
    }
}

/// `Store._canonical`: `table RS field RS field ...`, with `-` for NULL and otherwise
/// `<byte length>:<text>`, where text is Python's `str(value)`.
pub fn canonical(table: &str, fields: &[Value<'_>]) -> Result<Vec<u8>, CodecRefused> {
    let mut out = Vec::with_capacity(table.len() + fields.len() * 16);
    out.extend_from_slice(table.as_bytes());
    let mut text = String::new();
    for field in fields {
        out.push(RS);
        text.clear();
        let bytes: &[u8] = match *field {
            Value::Null => {
                out.push(b'-');
                continue;
            }
            Value::Text(held) => {
                std::str::from_utf8(held).map_err(|_| CodecRefused::NotUtf8)?;
                held
            }
            Value::Integer(n) => {
                let _ = write!(text, "{n}");
                text.as_bytes()
            }
            Value::Real(n) => {
                python_float(n, &mut text)?;
                text.as_bytes()
            }
            Value::Blob(held) => {
                python_bytes(held, &mut text);
                text.as_bytes()
            }
        };
        out.extend_from_slice(bytes.len().to_string().as_bytes());
        out.push(b':');
        out.extend_from_slice(bytes);
    }
    Ok(out)
}

/// Python's `repr(float)`: the shortest digits that round-trip, positional for a decimal exponent
/// from -4 to 15, otherwise `d.ddde+XX` with at least two exponent digits.
///
/// Rust's shortest form has the right number of digits and not always the right digits: where the
/// value lies exactly between two candidates it rounds up, and Python rounds half to even
/// (810299654.76953125 is `.7695312` to Python). So it gives the count, and the exact form, which
/// rounds half to even, gives the digits.
pub fn python_float(n: f64, out: &mut String) -> Result<(), CodecRefused> {
    if !n.is_finite() {
        return Err(CodecRefused::NonFinite);
    }
    let magnitude = n.abs();
    let shortest = format!("{magnitude:e}");
    let count = shortest
        .split('e')
        .next()
        .map_or(1, |m| m.replace('.', "").len());
    let exact = format!("{magnitude:.*e}", count - 1);
    let (mantissa, exponent) = exact.split_once('e').expect("`{:e}` writes an exponent");
    let exponent: i32 = exponent.parse().expect("`{:e}` writes a decimal exponent");
    let digits = mantissa.replace('.', "");
    if n.is_sign_negative() {
        out.push('-');
    }
    if (-4..16).contains(&exponent) {
        if exponent < 0 {
            out.push_str("0.");
            out.extend(std::iter::repeat_n('0', (-exponent - 1) as usize));
            out.push_str(&digits);
        } else {
            let whole = exponent as usize + 1;
            if digits.len() <= whole {
                out.push_str(&digits);
                out.extend(std::iter::repeat_n('0', whole - digits.len()));
                out.push_str(".0");
            } else {
                out.push_str(&digits[..whole]);
                out.push('.');
                out.push_str(&digits[whole..]);
            }
        }
    } else {
        let sign = if exponent < 0 { '-' } else { '+' };
        let _ = write!(out, "{mantissa}e{sign}{:02}", exponent.abs());
    }
    Ok(())
}

/// Python's `str(bytes)`, which is its `repr`.
fn python_bytes(held: &[u8], out: &mut String) {
    let quote = if held.contains(&b'\'') && !held.contains(&b'"') {
        b'"'
    } else {
        b'\''
    };
    out.push('b');
    out.push(char::from(quote));
    for &byte in held {
        match byte {
            b'\\' => out.push_str("\\\\"),
            b'\t' => out.push_str("\\t"),
            b'\n' => out.push_str("\\n"),
            b'\r' => out.push_str("\\r"),
            _ if byte == quote => {
                out.push('\\');
                out.push(char::from(quote));
            }
            0x20..=0x7e => out.push(char::from(byte)),
            _ => {
                let _ = write!(out, "\\x{byte:02x}");
            }
        }
    }
    out.push(char::from(quote));
}

/// Lowercase hex SHA-256 of `prev RS canonical`.
pub fn row_hash(prev: &[u8], canonical: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(prev);
    hasher.update([RS]);
    hasher.update(canonical);
    let mut out = String::with_capacity(64);
    for byte in hasher.finalize().iter() {
        let _ = write!(out, "{byte:02x}");
    }
    out
}

/// Each lists `seq`, the columns of `Store.CHAINED[table]` in their order, `prev_hash` and `hash`.
const WALK_ENTRY: &str = "SELECT seq, id, family, def_name, def_version, body, attributed_to, \
     written_by, recorded_at, origin, link_from, link_to, link_relation, link_relation_version, \
     prev_hash, hash FROM entry WHERE seq > ?1 AND seq <= ?2 ORDER BY seq";
const WALK_OPERATIONAL: &str = "SELECT seq, id, at, actor, act, conversation, turn, execution, \
     runtime, because, caused_by, about, detail, prev_hash, hash FROM operational \
     WHERE seq > ?1 AND seq <= ?2 ORDER BY seq";
const WALK_DELIVERY: &str = "SELECT seq, id, execution, conversation, participant, runtime, \
     mechanism, at, material, behavioural_sources, operation_ok, prev_hash, hash FROM delivery \
     WHERE seq > ?1 AND seq <= ?2 ORDER BY seq";

const COUNT_ENTRY: &str = "SELECT COUNT(*) FROM entry WHERE seq <= ?1";
const COUNT_OPERATIONAL: &str = "SELECT COUNT(*) FROM operational WHERE seq <= ?1";
const COUNT_DELIVERY: &str = "SELECT COUNT(*) FROM delivery WHERE seq <= ?1";

const FROM_FIRST: &str = "SELECT chained_from_first FROM corpus WHERE one = 1";

/// How long one scope is read before the next takes over, well inside its limit.
const SCOPE_BUDGET: Duration = Duration::from_secs(1);

/// Whether Python reads this as false, which is how `verify_chain` treats a hash and a prev_hash.
fn is_falsy(value: Value<'_>) -> bool {
    match value {
        Value::Null => true,
        Value::Integer(n) => n == 0,
        Value::Real(n) => n == 0.0,
        Value::Text(held) | Value::Blob(held) => held.is_empty(),
    }
}

/// Attested erasure (`erasure-design.md` 1.2-1.4): whether the Brain has the table, its rows, and
/// the `conversation-deleted` acts they name.
const HAS_ERASURE: &str =
    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'erasure'";
const READ_ERASURE: &str =
    "SELECT deletion, tbl, row_id, row_hash, residual FROM erasure ORDER BY seq";
const READ_DELETIONS: &str =
    "SELECT id, seq, detail FROM operational WHERE act = 'conversation-deleted' ORDER BY seq";

/// The act that attests an erasure.
pub const DELETION_ACT: &str = "conversation-deleted";

/// Each chained table's erasable content columns, as indexes into `Store.CHAINED[table]`, and the
/// one that must be NULL after erasure (`operational.because`).
fn content_columns(table: &str) -> (&'static [usize], Option<usize>) {
    match table {
        "entry" => (&[4], None),
        "operational" => (&[11], Some(8)),
        "delivery" => (&[7], None),
        _ => (&[], None),
    }
}

/// `erasure.marker`: the exact text an erased content column holds, `{"erased":"<deletion>"}`.
pub fn erasure_marker(deletion: &str) -> String {
    format!("{{\"erased\":\"{deletion}\"}}")
}

/// `erasure.holds_marker`'s first half: the value is exactly the marker naming `deletion`.
pub fn is_erasure_marker(value: Value<'_>, deletion: &str) -> bool {
    value == Value::Text(erasure_marker(deletion).as_bytes())
}

/// Lowercase hex SHA-256.
pub fn sha256_hex(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(64);
    for byte in Sha256::digest(bytes).iter() {
        let _ = write!(out, "{byte:02x}");
    }
    out
}

/// `erasure.digest`: sha256 hex of the lines `tbl RS row_id RS row_hash RS residual`, sorted by
/// `(tbl, row_id)`, joined by `\n`.
pub fn erasure_digest<'a>(
    rows: impl IntoIterator<Item = (&'a str, &'a str, &'a str, &'a str)>,
) -> String {
    let mut rows: Vec<_> = rows.into_iter().collect();
    rows.sort_by(|a, b| (a.0, a.1).cmp(&(b.0, b.1)));
    let sep = char::from(RS).to_string();
    let lines: Vec<String> = rows
        .iter()
        .map(|(tbl, id, hash, residual)| [*tbl, *id, *hash, *residual].join(&sep))
        .collect();
    sha256_hex(lines.join("\n").as_bytes())
}

/// One `erasure` row.
#[derive(Clone, Debug)]
struct ErasureRow {
    deletion: String,
    row_hash: String,
    residual: String,
}

/// The erasure rows and deletion acts, as last read. `None` rows: a Brain before 0002.
#[derive(Default)]
struct Known {
    present: bool,
    /// Per chained table, in `CHAINED_TABLES` order: row id -> its erasure row.
    rows: [HashMap<String, ErasureRow>; 3],
    /// Every erasure row: (table, row id). Rows naming another table are kept here only.
    all: Vec<(String, String, ErasureRow)>,
    /// `conversation-deleted` acts: id -> detail.
    acts: HashMap<String, Option<String>>,
}

impl Known {
    fn read(scope: &mut dyn ReadScope) -> Result<Known, RecordError> {
        let mut known = Known::default();
        let mut present = false;
        scope.query(HAS_ERASURE, &[], &mut |row| {
            present = row.value(0)?.integer().unwrap_or_default() > 0;
            Ok(Flow::Stop)
        })?;
        if !present {
            return Ok(known);
        }
        known.present = true;
        scope.query(READ_ERASURE, &[], &mut |row| {
            let text = |column: usize| -> Result<String, RecordError> {
                Ok(row.value(column)?.text().unwrap_or_default().to_string())
            };
            let table = text(1)?;
            let id = text(2)?;
            let erasure = ErasureRow {
                deletion: text(0)?,
                row_hash: text(3)?,
                residual: text(4)?,
            };
            if let Some(index) = CHAINED_TABLES.iter().position(|t| *t == table) {
                known.rows[index].insert(id.clone(), erasure.clone());
            }
            known.all.push((table, id, erasure));
            Ok(Flow::Continue)
        })?;
        scope.query(READ_DELETIONS, &[], &mut |row| {
            let id = row.value(0)?.text().unwrap_or_default().to_string();
            let detail = row.value(2)?.text().map(str::to_string);
            known.acts.insert(id, detail);
            Ok(Flow::Continue)
        })?;
        Ok(known)
    }
}

const NO_HASH_BEGUN: &str = "this row carries no hash, and the chain had already begun";
const NO_HASH_FROM_FIRST: &str =
    "this corpus has been chained since its first row, so no row may lack one";
const STARTS_ELSEWHERE: &str =
    "the chain starts here but points at a row that is not in front of it";
const DOES_NOT_FOLLOW: &str = "this row does not follow the one before it";
const NOT_ITS_HASH: &str = "the row's own content does not match its hash";
const NEITHER: &str = "the row's content matches neither its hash nor its erasure record";

/// One table's walk: `Store.verify_chain`'s loop body, as state.
struct Walk {
    table: &'static str,
    index: usize,
    from_first: bool,
    /// The last row that followed: Python's `prev`, and at the end its `head`. So a broken table's
    /// head is the row before the break, as Python reports it.
    prev: Vec<u8>,
    begun: bool,
    last_seq: i64,
    broke: Option<ChainBreak>,
    erased: u64,
    chained: u64,
    before: u64,
    pending: u64,
    /// A row that matched no erasure row known, for which the erasures are to be read again.
    reread_at: Option<i64>,
    /// The row they were last read again for, so a row is only ever read again once.
    reread_for: Option<i64>,
}

impl Walk {
    fn broke(
        &mut self,
        seq: i64,
        id: Option<&str>,
        why: &'static str,
    ) -> Result<Flow, RecordError> {
        self.last_seq = seq;
        self.broke = Some(ChainBreak {
            seq: seq as u64,
            id: id.map(str::to_owned),
            why,
        });
        Ok(Flow::Stop)
    }

    /// `erasure.holds_marker`: the content column is exactly the marker, and `because` is NULL.
    fn holds_marker(&self, fields: &[Value<'_>], deletion: &str) -> bool {
        let (content, nulled) = content_columns(self.table);
        content
            .iter()
            .all(|&c| is_erasure_marker(fields[c], deletion))
            && nulled.is_none_or(|c| fields[c] == Value::Null)
    }

    fn step(&mut self, row: &dyn Row, known: &Known) -> Result<Flow, RecordError> {
        let seq = row.value(0)?.integer().unwrap_or_default();
        let count = row.column_count();
        let prev_hash = row.value(count - 2)?;
        let hash = row.value(count - 1)?;
        let fields = (1..count - 2)
            .map(|column| row.value(column))
            .collect::<Result<Vec<_>, _>>()?;
        let id = fields.first().and_then(|v| v.text());
        let attested = id.and_then(|id| known.rows[self.index].get(id));
        if is_falsy(hash) {
            // Pre-chain and erased: counted, as before otherwise (residual not checked).
            if let Some(erasure) = attested
                && erasure.row_hash.is_empty()
                && self.holds_marker(&fields, &erasure.deletion)
            {
                self.erased += 1;
            }
            if self.begun {
                return self.broke(seq, id, NO_HASH_BEGUN);
            }
            if self.from_first {
                return self.broke(seq, id, NO_HASH_FROM_FIRST);
            }
            self.last_seq = seq;
            self.before += 1;
            return Ok(Flow::Continue);
        }
        // A prev_hash that isn't text never equals a hash. A falsy one reads as "".
        let linked: &[u8] = match prev_hash {
            Value::Text(held) => held,
            other if is_falsy(other) => b"",
            _ => {
                let why = if self.begun {
                    DOES_NOT_FOLLOW
                } else {
                    STARTS_ELSEWHERE
                };
                self.begun = true;
                return self.broke(seq, id, why);
            }
        };
        if !self.begun {
            self.begun = true;
            if !linked.is_empty() {
                return self.broke(seq, id, STARTS_ELSEWHERE);
            }
        } else if linked != self.prev.as_slice() {
            return self.broke(seq, id, DOES_NOT_FOLLOW);
        }
        let table = self.table;
        let refused = |why: CodecRefused| RecordError::ChainRefused {
            table,
            seq: seq as u64,
            detail: why.to_string(),
        };
        let material = canonical(table, &fields).map_err(refused)?;
        let want = row_hash(linked, &material);
        let stored: &[u8] = match hash {
            Value::Text(held) => held,
            _ => b"",
        };
        if hash != Value::Text(want.as_bytes()) {
            let Some(erasure) = attested else {
                // Perhaps erased after the erasures were read: read them again, once, and come
                // back to this row.
                if known.present && self.reread_for != Some(seq) {
                    self.reread_at = Some(seq);
                    return Ok(Flow::Stop);
                }
                return self.broke(seq, id, NOT_ITS_HASH);
            };
            let accepted = erasure.row_hash.as_bytes() == stored
                && known.acts.contains_key(&erasure.deletion)
                && self.holds_marker(&fields, &erasure.deletion)
                && sha256_hex(&material) == erasure.residual;
            if !accepted {
                return self.broke(seq, id, NEITHER);
            }
            self.erased += 1;
        } else if attested.is_some() {
            self.pending += 1;
        }
        self.last_seq = seq;
        self.chained += 1;
        // The next row links to the hash this one was chained with, which an erased row keeps.
        self.prev.clear();
        self.prev.extend_from_slice(stored);
        Ok(Flow::Continue)
    }
}

/// The verifier. Its scopes are `Background`'s.
pub struct Chains;

/// The scope being read, and when it was opened.
struct Reading<'r> {
    reader: &'r dyn RecordReader,
    scope: Option<(Box<dyn ReadScope>, Instant)>,
}

impl Reading<'_> {
    fn scope(&mut self) -> Result<&mut (Box<dyn ReadScope>, Instant), RecordError> {
        if self.scope.is_none() {
            let scope = self.reader.read_scope(ReadClass::Background)?;
            self.scope = Some((scope, Instant::now()));
        }
        Ok(self.scope.as_mut().expect("just made"))
    }
}

impl ChainVerifier for Chains {
    fn verify_chains(&self, reader: &dyn RecordReader) -> Result<Vec<TableChain>, RecordError> {
        Ok(self.verify_report(reader)?.tables)
    }

    fn verify_report(&self, reader: &dyn RecordReader) -> Result<ChainReport, RecordError> {
        let mut reading = Reading {
            reader,
            scope: None,
        };
        let (scope, _) = reading.scope()?;
        let position = scope.position();
        let mut from_first = false;
        scope.query(FROM_FIRST, &[], &mut |row| {
            from_first = !is_falsy(row.value(0)?);
            Ok(Flow::Stop)
        })?;
        let mut known = Known::read(scope.as_mut())?;
        let tables = [
            (WALK_ENTRY, COUNT_ENTRY, position.entry),
            (WALK_OPERATIONAL, COUNT_OPERATIONAL, position.operational),
            (WALK_DELIVERY, COUNT_DELIVERY, position.delivery),
        ];
        let mut out = Vec::with_capacity(tables.len());
        let mut pending = 0;
        for (index, (table, (walk_sql, count_sql, last))) in
            CHAINED_TABLES.into_iter().zip(tables).enumerate()
        {
            let last = last as i64;
            let mut rows = 0;
            reading
                .scope()?
                .0
                .query(count_sql, &[Param::Integer(last)], &mut |row| {
                    rows = row.value(0)?.integer().unwrap_or_default() as u64;
                    Ok(Flow::Stop)
                })?;
            let mut walk = Walk {
                table,
                index,
                from_first,
                prev: Vec::new(),
                begun: false,
                last_seq: 0,
                broke: None,
                erased: 0,
                chained: 0,
                before: 0,
                pending: 0,
                reread_at: None,
                reread_for: None,
            };
            walk_table(&mut reading, walk_sql, last, &mut walk, &mut known)?;
            pending += walk.pending;
            out.push(TableChain {
                table,
                rows,
                head: (!walk.prev.is_empty())
                    .then(|| String::from_utf8_lossy(&walk.prev).into_owned()),
                broke_at_seq: walk.broke.as_ref().map(|b| b.seq),
                erased: walk.erased,
                chained: walk.chained,
                before_the_chain: walk.before,
                broken_at: walk.broke,
            });
        }
        let mut erasures = Erasures {
            pending,
            ..Erasures::default()
        };
        if known.present {
            erasures.acts = known.acts.len() as u64;
            erasures.rows = known.all.len() as u64;
            erasures.broken = check_acts(&known);
            if erasures.broken.is_none() {
                erasures.broken = missing_rows(&mut reading, &known)?;
            }
        }
        Ok(ChainReport {
            tables: out,
            erasures,
            chained_from_first_row: from_first,
        })
    }
}

/// `erasure.check_acts`, its first two checks, in its order: per deletion named by erasure rows
/// (sorted), the act is there and its count and digest are theirs; then per act holding no
/// erasure rows (sorted), it records none.
fn check_acts(known: &Known) -> Option<ErasureBroken> {
    let mut by_act: std::collections::BTreeMap<&str, Vec<(&str, &str, &str, &str)>> =
        Default::default();
    for (table, id, erasure) in &known.all {
        by_act.entry(erasure.deletion.as_str()).or_default().push((
            table.as_str(),
            id.as_str(),
            erasure.row_hash.as_str(),
            erasure.residual.as_str(),
        ));
    }
    let stated = |deletion: &str| -> Option<serde_json::Value> {
        let detail = known.acts.get(deletion)?.as_deref()?;
        let value: serde_json::Value = serde_json::from_str(detail).ok()?;
        match value.get("erasure") {
            Some(e @ serde_json::Value::Object(_)) => Some(e.clone()),
            _ => None,
        }
    };
    for (deletion, rows) in &by_act {
        if !known.acts.contains_key(*deletion) {
            return Some(ErasureBroken::Act {
                deletion: deletion.to_string(),
                why: "erasure rows name a deletion act that is not in the record",
            });
        }
        let erasure = stated(deletion).unwrap_or(serde_json::Value::Null);
        // Python's `e.get("rows") != len(rows)`: an integral number equal to the count.
        let count_matches = match &erasure["rows"] {
            serde_json::Value::Number(n) => n.as_f64().is_some_and(|n| n == rows.len() as f64),
            serde_json::Value::Bool(b) => (*b as usize) == rows.len(),
            _ => false,
        };
        let digest_matches =
            erasure["digest"].as_str() == Some(erasure_digest(rows.iter().copied()).as_str());
        if !count_matches || !digest_matches {
            return Some(ErasureBroken::Act {
                deletion: deletion.to_string(),
                why: "the erasure rows do not match the count and digest their deletion act \
                      records",
            });
        }
    }
    let mut without: Vec<&String> = known
        .acts
        .keys()
        .filter(|act| !by_act.contains_key(act.as_str()))
        .collect();
    without.sort();
    for act in without {
        let erasure = stated(act).unwrap_or(serde_json::Value::Null);
        if truthy(&erasure["rows"]) {
            return Some(ErasureBroken::Act {
                deletion: act.clone(),
                why: "the deletion act records erasure rows the record does not hold",
            });
        }
    }
    None
}

/// Python's truth of a JSON value.
fn truthy(value: &serde_json::Value) -> bool {
    match value {
        serde_json::Value::Null => false,
        serde_json::Value::Bool(b) => *b,
        serde_json::Value::Number(n) => n.as_f64().is_some_and(|n| n != 0.0),
        serde_json::Value::String(s) => !s.is_empty(),
        serde_json::Value::Array(a) => !a.is_empty(),
        serde_json::Value::Object(o) => !o.is_empty(),
    }
}

const ENTRY_THERE: &str = "SELECT 1 FROM entry WHERE id = ?1";
const OPERATIONAL_THERE: &str = "SELECT 1 FROM operational WHERE id = ?1";
const DELIVERY_THERE: &str = "SELECT 1 FROM delivery WHERE id = ?1";

/// `erasure.check_acts`, its last check: per erasure row, sorted by (table, row id), the row it
/// names is in the record.
fn missing_rows(
    reading: &mut Reading<'_>,
    known: &Known,
) -> Result<Option<ErasureBroken>, RecordError> {
    let mut named: Vec<(&str, &str)> = known
        .all
        .iter()
        .map(|(t, id, _)| (t.as_str(), id.as_str()))
        .collect();
    named.sort();
    for (table, id) in named {
        let sql = match table {
            "entry" => ENTRY_THERE,
            "operational" => OPERATIONAL_THERE,
            "delivery" => DELIVERY_THERE,
            // The table's CHECK allows no other; one that isn't there names nothing.
            _ => {
                return Ok(Some(ErasureBroken::Row {
                    table: table.to_owned(),
                    id: id.to_owned(),
                    why: "an erasure row names a row that does not exist",
                }));
            }
        };
        let mut there = false;
        loop {
            let (scope, _) = reading.scope()?;
            match scope.query(sql, &[Param::Text(id)], &mut |_| {
                there = true;
                Ok(Flow::Stop)
            }) {
                Ok(()) => break,
                Err(RecordError::ScopeExpired) => reading.scope = None,
                Err(error) => return Err(error),
            }
        }
        if !there {
            return Ok(Some(ErasureBroken::Row {
                table: table.to_owned(),
                id: id.to_owned(),
                why: "an erasure row names a row that does not exist",
            }));
        }
    }
    Ok(None)
}

/// Reads from where the last scope stopped, a scope at a time, until the walk ends.
fn walk_table(
    reading: &mut Reading<'_>,
    sql: &'static str,
    last: i64,
    walk: &mut Walk,
    known: &mut Known,
) -> Result<(), RecordError> {
    loop {
        let from = walk.last_seq;
        let (scope, opened) = reading.scope()?;
        let opened = *opened;
        let mut budget_spent = false;
        let answer = {
            let known: &Known = known;
            scope.query(
                sql,
                &[Param::Integer(from), Param::Integer(last)],
                &mut |row| {
                    if opened.elapsed() >= SCOPE_BUDGET {
                        budget_spent = true;
                        return Ok(Flow::Stop);
                    }
                    walk.step(row, known)
                },
            )
        };
        match answer {
            Ok(()) if walk.reread_at.is_some() => {
                // Read the erasures again in this scope, and take the row again.
                walk.reread_for = walk.reread_at.take();
                *known = Known::read(scope.as_mut())?;
            }
            Ok(()) if budget_spent => reading.scope = None,
            Ok(()) => return Ok(()),
            // A scope that made progress before its limit hands on to the next. One that made
            // none would only do the same again, so that is the answer.
            Err(RecordError::ScopeExpired) if walk.last_seq > from => reading.scope = None,
            Err(error) => return Err(error),
        }
    }
}
