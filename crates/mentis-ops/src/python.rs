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

/// `str.splitlines`'s boundaries. `\r\n` counts as two here, which only [`first_line`] reads, and it
/// skips the empty line between them.
fn ends_a_line(c: char) -> bool {
    matches!(
        c,
        '\n' | '\r'
            | '\u{b}'
            | '\u{c}'
            | '\u{1c}'
            | '\u{1d}'
            | '\u{1e}'
            | '\u{85}'
            | '\u{2028}'
            | '\u{2029}'
    )
}

/// `text.splitlines()`, but for the empty line a `\r\n` shows between its two ends: nothing that
/// reads this keeps an empty line.
pub fn lines(text: &str) -> impl Iterator<Item = &str> {
    text.split(ends_a_line)
}

/// `first_line`, `conversation/__init__.py:7050`: the first line that says anything, cut at `most`
/// characters.
pub fn first_line(text: &str, most: usize) -> String {
    for line in text.split(ends_a_line) {
        let line = strip(line);
        if line.is_empty() {
            continue;
        }
        if line.chars().count() <= most {
            return line.to_owned();
        }
        let mut cut: String = line.chars().take(most - 1).collect();
        cut.push('\u{2026}');
        return cut;
    }
    String::new()
}

/// `_when`, `worker.py:696`: UTC to the second, after `datetime.fromtimestamp` has rounded to the
/// microsecond, half to even.
pub fn when(at: f64) -> String {
    let mut seconds = at.floor();
    let micros = ((at - seconds) * 1e6).round_ties_even();
    if micros >= 1e6 {
        seconds += 1.0;
    }
    let seconds = seconds as i64;
    let (days, of_day) = (seconds.div_euclid(86_400), seconds.rem_euclid(86_400));
    // Days to a civil date, on the proleptic Gregorian calendar.
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let day_of_era = z.rem_euclid(146_097);
    let year_of_era =
        (day_of_era - day_of_era / 1460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let shifted_month = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * shifted_month + 2) / 5 + 1;
    let month = if shifted_month < 10 {
        shifted_month + 3
    } else {
        shifted_month - 9
    };
    let year = year_of_era + era * 400 + i64::from(month <= 2);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        of_day / 3600,
        of_day % 3600 / 60,
        of_day % 60
    )
}

/// `repr(text)` for what is plainly the same in both: printable ASCII, with no quote and no
/// backslash. `None` for anything else, so Python says it.
pub fn repr(text: &str) -> Option<String> {
    let plain = text
        .bytes()
        .all(|b| (0x20..0x7f).contains(&b) && b != b'\'' && b != b'"' && b != b'\\');
    plain.then(|| format!("'{text}'"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn when_is_utc_to_the_second_after_rounding_to_the_microsecond() {
        assert_eq!(when(0.0), "1970-01-01T00:00:00Z");
        assert_eq!(when(1793500000.001), "2026-11-01T02:26:40Z");
        assert_eq!(when(951782400.0), "2000-02-29T00:00:00Z");
        assert_eq!(when(59.9999999), "1970-01-01T00:01:00Z");
        assert_eq!(when(59.9999), "1970-01-01T00:00:59Z");
    }

    #[test]
    fn a_first_line_is_the_first_that_says_anything_and_is_cut() {
        assert_eq!(first_line("\n  \r\n  words  \nmore", 140), "words");
        assert_eq!(first_line("abcdef", 6), "abcdef");
        assert_eq!(first_line("abcdefg", 6), "abcde\u{2026}");
        assert_eq!(first_line("", 6), "");
        assert_eq!(first_line("a\u{2028}b", 6), "a");
    }

    #[test]
    fn a_repr_is_given_only_where_it_is_plain() {
        assert_eq!(repr("rule").as_deref(), Some("'rule'"));
        assert_eq!(repr("it's"), None);
        assert_eq!(repr("caf\u{e9}"), None);
        assert_eq!(repr("a\nb"), None);
    }

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
