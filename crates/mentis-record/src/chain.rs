//! The chain codec and verifier: `docs/rust/R1-acceptance.md`, section G, from
//! `spine/store.py:458-548,567-592`. Rust must produce the same bytes and the same answer.

use std::fmt;
use std::fmt::Write as _;
use std::time::{Duration, Instant};

use sha2::{Digest, Sha256};

use crate::{
    CHAINED_TABLES, ChainVerifier, Flow, Param, ReadClass, ReadScope, RecordError, RecordReader,
    Row, TableChain, Value,
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
fn python_float(n: f64, out: &mut String) -> Result<(), CodecRefused> {
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

/// One table's walk: `Store.verify_chain`'s loop body, as state.
struct Walk {
    table: &'static str,
    from_first: bool,
    /// The last row that followed: Python's `prev`, and at the end its `head`. So a broken table's
    /// head is the row before the break, as Python reports it.
    prev: Vec<u8>,
    begun: bool,
    last_seq: i64,
    broke_at: Option<u64>,
}

impl Walk {
    fn broke(&mut self, seq: i64) -> Result<Flow, RecordError> {
        self.broke_at = Some(seq as u64);
        Ok(Flow::Stop)
    }

    fn step(&mut self, row: &dyn Row) -> Result<Flow, RecordError> {
        let seq = row.value(0)?.integer().unwrap_or_default();
        self.last_seq = seq;
        let count = row.column_count();
        let prev_hash = row.value(count - 2)?;
        let hash = row.value(count - 1)?;
        if is_falsy(hash) {
            if self.begun || self.from_first {
                return self.broke(seq);
            }
            return Ok(Flow::Continue);
        }
        // A prev_hash that isn't text never equals a hash. A falsy one reads as "".
        let linked: &[u8] = match prev_hash {
            Value::Text(held) => held,
            other if is_falsy(other) => b"",
            _ => return self.broke(seq),
        };
        let follows = if self.begun {
            linked == self.prev.as_slice()
        } else {
            linked.is_empty()
        };
        self.begun = true;
        if !follows {
            return self.broke(seq);
        }
        let table = self.table;
        let refused = |why: CodecRefused| RecordError::ChainRefused {
            table,
            seq: seq as u64,
            detail: why.to_string(),
        };
        let fields = (1..count - 2)
            .map(|column| row.value(column))
            .collect::<Result<Vec<_>, _>>()?;
        let material = canonical(table, &fields).map_err(refused)?;
        let want = row_hash(linked, &material);
        if hash != Value::Text(want.as_bytes()) {
            return self.broke(seq);
        }
        self.prev.clear();
        self.prev.extend_from_slice(want.as_bytes());
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
        let tables = [
            (WALK_ENTRY, COUNT_ENTRY, position.entry),
            (WALK_OPERATIONAL, COUNT_OPERATIONAL, position.operational),
            (WALK_DELIVERY, COUNT_DELIVERY, position.delivery),
        ];
        let mut out = Vec::with_capacity(tables.len());
        for (table, (walk_sql, count_sql, last)) in CHAINED_TABLES.into_iter().zip(tables) {
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
                from_first,
                prev: Vec::new(),
                begun: false,
                last_seq: 0,
                broke_at: None,
            };
            walk_table(&mut reading, walk_sql, last, &mut walk)?;
            out.push(TableChain {
                table,
                rows,
                head: (!walk.prev.is_empty())
                    .then(|| String::from_utf8_lossy(&walk.prev).into_owned()),
                broke_at_seq: walk.broke_at,
            });
        }
        Ok(out)
    }
}

/// Reads from where the last scope stopped, a scope at a time, until the walk ends.
fn walk_table(
    reading: &mut Reading<'_>,
    sql: &'static str,
    last: i64,
    walk: &mut Walk,
) -> Result<(), RecordError> {
    loop {
        let from = walk.last_seq;
        let (scope, opened) = reading.scope()?;
        let opened = *opened;
        let mut budget_spent = false;
        let answer = scope.query(
            sql,
            &[Param::Integer(from), Param::Integer(last)],
            &mut |row| {
                if opened.elapsed() >= SCOPE_BUDGET {
                    budget_spent = true;
                    return Ok(Flow::Stop);
                }
                walk.step(row)
            },
        );
        match answer {
            Ok(()) if budget_spent => reading.scope = None,
            Ok(()) => return Ok(()),
            // A scope that made progress before its limit hands on to the next. One that made
            // none would only do the same again, so that is the answer.
            Err(RecordError::ScopeExpired) if walk.last_seq > from => reading.scope = None,
            Err(error) => return Err(error),
        }
    }
}
