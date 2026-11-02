//! What Python's `int`, `str.split`, `str.strip` and `str.lower` do, as far as a route's answer
//! depends on it. Each is tested against Python itself (`tests/python_text.rs`), every code point.

/// What `int(text)` does.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PythonInt {
    /// Its value. Past `i128`'s range it is held at the end of it, which compares as Python's would
    /// with anything a record can hold.
    Value(i128),
    /// `ValueError`.
    NotInt,
    /// It holds a character outside ASCII, where `int` reads every script's digits. Python decides.
    Unsure,
}

/// `sys.get_int_max_str_digits()`'s default: `int` refuses more digits than this.
const MOST_DIGITS: usize = 4300;

/// `str.isspace`.
pub fn is_space(c: char) -> bool {
    c.is_whitespace() || matches!(c, '\u{1c}'..='\u{1f}')
}

/// `int(text)`, base 10.
pub fn int(text: &str) -> PythonInt {
    if !text.is_ascii() {
        return PythonInt::Unsure;
    }
    // In ASCII, `Py_ISSPACE`: not all that `str.isspace` counts.
    let inner = text.trim_matches([' ', '\t', '\n', '\r', '\u{b}', '\u{c}']);
    let (negative, digits) = match inner.as_bytes().first() {
        Some(b'-') => (true, &inner[1..]),
        Some(b'+') => (false, &inner[1..]),
        _ => (false, inner),
    };
    // One `_` at a time between digits, and none at either end.
    let bytes = digits.as_bytes();
    let well_formed = !bytes.is_empty()
        && bytes[0] != b'_'
        && bytes[bytes.len() - 1] != b'_'
        && !digits.contains("__")
        && bytes.iter().all(|b| b.is_ascii_digit() || *b == b'_');
    if !well_formed {
        return PythonInt::NotInt;
    }
    let count = bytes.iter().filter(|b| b.is_ascii_digit()).count();
    if count > MOST_DIGITS {
        return PythonInt::NotInt;
    }
    let mut value: i128 = 0;
    for b in bytes.iter().filter(|b| b.is_ascii_digit()) {
        value = value
            .saturating_mul(10)
            .saturating_add(i128::from(b - b'0'));
    }
    PythonInt::Value(if negative { -value } else { value })
}

/// Characters whose case Rust's tables know and Python 3.12's don't: they were added to Unicode
/// after 15.0. `tests/python_text.rs` fails if this list is short of what the two disagree on.
fn newer_than_python(c: char) -> bool {
    matches!(u32::from(c),
        0x1C89..=0x1C8A
        | 0xA7CB..=0xA7CD
        | 0xA7CE..=0xA7CF
        | 0xA7D2
        | 0xA7D4
        | 0xA7DA..=0xA7DC
        | 0x10D50..=0x10D65
        | 0x10D70..=0x10D85
        | 0x16EA0..=0x16EB8
        | 0x16EBB..=0x16ED3
    )
}

/// `text.lower()`, or `None` where the two tables differ and Python has to say.
pub fn lower(text: &str) -> Option<String> {
    if text.chars().any(newer_than_python) {
        return None;
    }
    Some(text.to_lowercase())
}

/// `text.strip()`.
pub fn strip(text: &str) -> &str {
    text.trim_matches(is_space)
}

/// `text.split()`.
pub fn words(text: &str) -> impl Iterator<Item = &str> {
    text.split(is_space).filter(|word| !word.is_empty())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn int_reads_what_python_s_int_reads() {
        for (text, value) in [
            ("0", 0),
            ("12", 12),
            ("+12", 12),
            ("-12", -12),
            (" 12\n", 12),
            ("1_000", 1000),
            ("007", 7),
        ] {
            assert_eq!(int(text), PythonInt::Value(value), "{text:?}");
        }
        for text in [
            "", " ", "+", "-", "1 2", "_1", "1_", "1__0", "0x10", "1.0", "1e3", "abc",
        ] {
            assert_eq!(int(text), PythonInt::NotInt, "{text:?}");
        }
        assert_eq!(int("\u{663}"), PythonInt::Unsure);
        assert_eq!(int(&"9".repeat(4300)), PythonInt::Value(i128::MAX));
        assert_eq!(int(&"9".repeat(4301)), PythonInt::NotInt);
    }

    #[test]
    fn words_and_strip_use_python_s_whitespace() {
        assert_eq!(
            words("a\u{a0}b\u{1c}c  d").collect::<Vec<_>>(),
            ["a", "b", "c", "d"]
        );
        assert_eq!(strip("\u{1f} a \u{3000}"), "a");
    }
}
