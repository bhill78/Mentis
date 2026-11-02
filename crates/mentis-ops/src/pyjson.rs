//! Values as Python holds them after `json.loads`, and `json.dumps` of them. An answer that holds a
//! body has to come out in Python's bytes: key order, `", "` and `": "`, ASCII escapes, `float.__repr__`,
//! integers of any size. `serde_json::Value` keeps none of those without features the rest of the
//! workspace would inherit, so this is the small thing it needs to be.
//!
//! **Only what can't be got wrong.** A lone surrogate, which `json.loads` keeps and a Rust `String`
//! can't hold, and nesting past [`MOST_DEPTH`], don't parse here, and the route forwards. A record
//! holds these rarely or never; when it does the answer is Python's own.

use std::collections::HashMap;

/// One value. An integer is held as its digits: `int` has no limit, and only `dumps` reads it.
#[derive(Clone, Debug, PartialEq)]
pub enum Py {
    None,
    Bool(bool),
    Int(String),
    Float(f64),
    Str(String),
    List(Vec<Py>),
    /// In insertion order. A key sent twice keeps its first place and its last value, as a `dict` does.
    Dict(Vec<(String, Py)>),
}

/// Deeper than any body the record's writers make, and shallower than where the two parsers could
/// disagree about running out of stack.
const MOST_DEPTH: usize = 200;

impl Py {
    pub fn str(text: impl Into<String>) -> Py {
        Py::Str(text.into())
    }

    pub fn int(n: impl std::fmt::Display) -> Py {
        Py::Int(n.to_string())
    }

    /// `text` or `None`.
    pub fn opt_str(text: Option<&str>) -> Py {
        text.map_or(Py::None, Py::str)
    }

    /// `bool(value)`.
    pub fn truthy(&self) -> bool {
        match self {
            Py::None => false,
            Py::Bool(value) => *value,
            Py::Int(digits) => digits != "0",
            Py::Float(value) => *value != 0.0,
            Py::Str(text) => !text.is_empty(),
            Py::List(items) => !items.is_empty(),
            Py::Dict(items) => !items.is_empty(),
        }
    }

    /// `dict.get(name)`, or `None` of any other type: a caller that has to tell asks `as_dict`.
    pub fn get(&self, name: &str) -> Option<&Py> {
        match self {
            Py::Dict(items) => items
                .iter()
                .find(|(key, _)| key == name)
                .map(|(_, value)| value),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Py::Str(text) => Some(text),
            _ => None,
        }
    }

    pub fn as_list(&self) -> Option<&[Py]> {
        match self {
            Py::List(items) => Some(items),
            _ => None,
        }
    }

    pub fn is_dict(&self) -> bool {
        matches!(self, Py::Dict(_))
    }

    /// `d[name] = value`: an existing key keeps its place.
    pub fn set(&mut self, name: &str, value: Py) {
        if let Py::Dict(items) = self {
            match items.iter_mut().find(|(key, _)| key == name) {
                Some(found) => found.1 = value,
                None => items.push((name.to_owned(), value)),
            }
        }
    }

    /// `json.dumps(self)`.
    pub fn dumps(&self) -> String {
        let mut out = String::new();
        self.write(&mut out);
        out
    }

    fn write(&self, out: &mut String) {
        match self {
            Py::None => out.push_str("null"),
            Py::Bool(true) => out.push_str("true"),
            Py::Bool(false) => out.push_str("false"),
            Py::Int(digits) => out.push_str(digits),
            Py::Float(value) => write_float(*value, out),
            Py::Str(text) => write_string(text, out),
            Py::List(items) => {
                out.push('[');
                for (at, item) in items.iter().enumerate() {
                    if at > 0 {
                        out.push_str(", ");
                    }
                    item.write(out);
                }
                out.push(']');
            }
            Py::Dict(items) => {
                out.push('{');
                for (at, (key, item)) in items.iter().enumerate() {
                    if at > 0 {
                        out.push_str(", ");
                    }
                    write_string(key, out);
                    out.push_str(": ");
                    item.write(out);
                }
                out.push('}');
            }
        }
    }
}

/// A `dict` from a literal list of fields.
pub fn dict<const N: usize>(fields: [(&str, Py); N]) -> Py {
    Py::Dict(
        fields
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

fn write_float(value: f64, out: &mut String) {
    if value.is_nan() {
        out.push_str("NaN");
    } else if value.is_infinite() {
        out.push_str(if value > 0.0 { "Infinity" } else { "-Infinity" });
    } else {
        mentis_record::python_float(value, out).expect("a finite float always has its repr");
    }
}

/// `repr(value)` of a float a record holds, as `_page_cursor` writes it.
pub fn float_repr(value: f64) -> String {
    let mut out = String::new();
    write_float(value, &mut out);
    out
}

fn write_string(text: &str, out: &mut String) {
    out.push('"');
    for c in text.chars() {
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
}

/// `repr(text)` for what prints in ASCII, the only case its words are sure to match. `None` is a
/// reason to forward.
pub fn repr(text: &str) -> Option<String> {
    if !text.chars().all(|c| matches!(c, ' '..='~')) {
        return None;
    }
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
    Some(out)
}

/// Python's `str.strip()` isn't needed here, only the JSON parser's own whitespace.
fn is_json_space(byte: u8) -> bool {
    matches!(byte, b' ' | b'\t' | b'\n' | b'\r')
}

struct Parser<'a> {
    bytes: &'a [u8],
    text: &'a str,
    at: usize,
}

/// `json.loads(text)`, or `None` where it raises or where this can't hold the answer.
pub fn loads(text: &str) -> Option<Py> {
    let mut parser = Parser {
        bytes: text.as_bytes(),
        text,
        at: 0,
    };
    parser.space();
    let value = parser.value(0)?;
    parser.space();
    (parser.at == parser.bytes.len()).then_some(value)
}

impl Parser<'_> {
    fn space(&mut self) {
        while self.bytes.get(self.at).copied().is_some_and(is_json_space) {
            self.at += 1;
        }
    }

    fn word(&mut self, word: &str) -> bool {
        if self.text[self.at..].starts_with(word) {
            self.at += word.len();
            return true;
        }
        false
    }

    fn value(&mut self, depth: usize) -> Option<Py> {
        if depth > MOST_DEPTH {
            return None;
        }
        match *self.bytes.get(self.at)? {
            b'"' => self.string().map(Py::Str),
            b'{' => self.object(depth),
            b'[' => self.array(depth),
            b'n' => self.word("null").then_some(Py::None),
            b't' => self.word("true").then_some(Py::Bool(true)),
            b'f' => self.word("false").then_some(Py::Bool(false)),
            b'N' => self.word("NaN").then_some(Py::Float(f64::NAN)),
            b'I' => self.word("Infinity").then_some(Py::Float(f64::INFINITY)),
            b'-' if self.text[self.at..].starts_with("-Infinity") => {
                self.at += "-Infinity".len();
                Some(Py::Float(f64::NEG_INFINITY))
            }
            b'-' | b'0'..=b'9' => self.number(),
            _ => None,
        }
    }

    /// `(-?(?:0|[1-9][0-9]*))(\.[0-9]+)?([eE][-+]?[0-9]+)?`, as `json.scanner.NUMBER_RE`.
    fn number(&mut self) -> Option<Py> {
        let start = self.at;
        let mut at = self.at;
        if self.bytes.get(at) == Some(&b'-') {
            at += 1;
        }
        match self.bytes.get(at)? {
            b'0' => at += 1,
            b'1'..=b'9' => {
                while self.bytes.get(at).is_some_and(u8::is_ascii_digit) {
                    at += 1;
                }
            }
            _ => return None,
        }
        let mut is_float = false;
        if self.bytes.get(at) == Some(&b'.')
            && self.bytes.get(at + 1).is_some_and(u8::is_ascii_digit)
        {
            is_float = true;
            at += 1;
            while self.bytes.get(at).is_some_and(u8::is_ascii_digit) {
                at += 1;
            }
        }
        if matches!(self.bytes.get(at), Some(b'e' | b'E')) {
            let mut past = at + 1;
            if matches!(self.bytes.get(past), Some(b'+' | b'-')) {
                past += 1;
            }
            if self.bytes.get(past).is_some_and(u8::is_ascii_digit) {
                is_float = true;
                at = past;
                while self.bytes.get(at).is_some_and(u8::is_ascii_digit) {
                    at += 1;
                }
            }
        }
        self.at = at;
        let text = &self.text[start..at];
        if is_float {
            return text.parse::<f64>().ok().map(Py::Float);
        }
        // `int("-0")` is 0. Past sys.get_int_max_str_digits `json.loads` raises.
        if text.trim_start_matches('-').len() > 4300 {
            return None;
        }
        Some(Py::Int(if text == "-0" {
            "0".to_owned()
        } else {
            text.to_owned()
        }))
    }

    fn string(&mut self) -> Option<String> {
        self.at += 1;
        let mut out = String::new();
        let mut run = self.at;
        loop {
            let byte = *self.bytes.get(self.at)?;
            match byte {
                b'"' => {
                    out.push_str(&self.text[run..self.at]);
                    self.at += 1;
                    return Some(out);
                }
                b'\\' => {
                    out.push_str(&self.text[run..self.at]);
                    self.at += 1;
                    let escape = *self.bytes.get(self.at)?;
                    self.at += 1;
                    match escape {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'b' => out.push('\u{8}'),
                        b'f' => out.push('\u{c}'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => out.push(self.unicode()?),
                        _ => return None,
                    }
                    run = self.at;
                }
                // `strict=True`: a control character in a string raises.
                0..=0x1f => return None,
                _ => self.at += 1,
            }
        }
    }

    fn four_hex(&mut self) -> Option<u32> {
        let digits = self.bytes.get(self.at..self.at + 4)?;
        if !digits.iter().all(u8::is_ascii_hexdigit) {
            return None;
        }
        let value = u32::from_str_radix(std::str::from_utf8(digits).ok()?, 16).ok()?;
        self.at += 4;
        Some(value)
    }

    /// After `\u`. A pair is one character; a lone surrogate is what this can't hold.
    fn unicode(&mut self) -> Option<char> {
        let first = self.four_hex()?;
        if (0xd800..0xdc00).contains(&first) {
            if self.bytes.get(self.at..self.at + 2)? != b"\\u" {
                return None;
            }
            self.at += 2;
            let second = self.four_hex()?;
            if !(0xdc00..0xe000).contains(&second) {
                return None;
            }
            return char::from_u32(0x10000 + ((first - 0xd800) << 10) + (second - 0xdc00));
        }
        char::from_u32(first)
    }

    fn array(&mut self, depth: usize) -> Option<Py> {
        self.at += 1;
        let mut items = Vec::new();
        self.space();
        if self.bytes.get(self.at) == Some(&b']') {
            self.at += 1;
            return Some(Py::List(items));
        }
        loop {
            self.space();
            items.push(self.value(depth + 1)?);
            self.space();
            match self.bytes.get(self.at)? {
                b',' => self.at += 1,
                b']' => {
                    self.at += 1;
                    return Some(Py::List(items));
                }
                _ => return None,
            }
        }
    }

    fn object(&mut self, depth: usize) -> Option<Py> {
        self.at += 1;
        let mut items: Vec<(String, Py)> = Vec::new();
        // Past a handful of keys a scan per key would cost more than this does.
        let mut places: HashMap<String, usize> = HashMap::new();
        self.space();
        if self.bytes.get(self.at) == Some(&b'}') {
            self.at += 1;
            return Some(Py::Dict(items));
        }
        loop {
            self.space();
            if self.bytes.get(self.at) != Some(&b'"') {
                return None;
            }
            let key = self.string()?;
            self.space();
            if self.bytes.get(self.at) != Some(&b':') {
                return None;
            }
            self.at += 1;
            self.space();
            let value = self.value(depth + 1)?;
            match places.get(&key) {
                Some(place) => items[*place].1 = value,
                None => {
                    places.insert(key.clone(), items.len());
                    items.push((key, value));
                }
            }
            self.space();
            match self.bytes.get(self.at)? {
                b',' => self.at += 1,
                b'}' => {
                    self.at += 1;
                    return Some(Py::Dict(items));
                }
                _ => return None,
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn round(text: &str) -> String {
        loads(text).unwrap().dumps()
    }

    #[test]
    fn it_comes_out_in_python_s_bytes() {
        assert_eq!(
            round(r#"{"z":1,"a":[1,2,{"k":null}],"b":true,"c":"café é 😀"}"#),
            r#"{"z": 1, "a": [1, 2, {"k": null}], "b": true, "c": "caf\u00e9 \u00e9 \ud83d\ude00"}"#
        );
    }

    #[test]
    fn numbers_stay_what_python_reads_them_as() {
        for (given, shown) in [
            ("0", "0"),
            ("-0", "0"),
            ("-0.0", "-0.0"),
            ("1.0", "1.0"),
            ("1e3", "1000.0"),
            ("1E400", "Infinity"),
            ("-1e400", "-Infinity"),
            ("NaN", "NaN"),
            ("1e16", "1e+16"),
            ("0.00001", "1e-05"),
            (
                "123456789012345678901234567890",
                "123456789012345678901234567890",
            ),
            ("1793578173.1234567", "1793578173.1234567"),
        ] {
            assert_eq!(round(given), shown, "{given}");
        }
    }

    #[test]
    fn a_key_sent_twice_keeps_its_first_place_and_last_value() {
        assert_eq!(round(r#"{"a":1,"b":2,"a":3}"#), r#"{"a": 3, "b": 2}"#);
    }

    #[test]
    fn what_python_refuses_or_this_can_t_hold_doesn_t_parse() {
        for bad in [
            "",
            "{",
            "[1,]",
            r#"{"a":1,}"#,
            "01",
            "1.",
            ".5",
            "tru",
            "{} x",
            "\"\u{1}\"",
            r#""\x""#,
            r#""\ud800""#,
            r#""\udc00""#,
            r#""\ud800A""#,
        ] {
            assert_eq!(loads(bad), None, "{bad:?}");
        }
        assert_eq!(loads(&"[".repeat(500)), None);
    }

    #[test]
    fn truth_is_python_s() {
        for no in ["null", "false", "0", "0.0", "\"\"", "[]", "{}"] {
            assert!(!loads(no).unwrap().truthy(), "{no}");
        }
        for yes in ["true", "1", "0.5", "\"x\"", "[0]", "{\"a\":0}"] {
            assert!(loads(yes).unwrap().truthy(), "{yes}");
        }
    }

    #[test]
    fn repr_only_says_what_it_is_sure_of() {
        assert_eq!(repr("a"), Some("'a'".into()));
        assert_eq!(repr("a'b"), Some("\"a'b\"".into()));
        assert_eq!(repr("a'b\"c"), Some("'a\\'b\"c'".into()));
        assert_eq!(repr("a\\b"), Some("'a\\\\b'".into()));
        assert_eq!(repr("caf\u{e9}"), None);
        assert_eq!(repr("a\tb"), None);
    }

    #[test]
    fn a_set_keeps_an_existing_key_in_its_place() {
        let mut d = dict([("a", Py::int(1)), ("b", Py::int(2))]);
        d.set("a", Py::int(3));
        d.set("c", Py::int(4));
        assert_eq!(d.dumps(), r#"{"a": 3, "b": 2, "c": 4}"#);
    }
}
