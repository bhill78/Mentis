//! A request's head, read the way Python's `http.server` and `email` parser read it, and nothing
//! more. `mentis/web/__init__.py:6323-6364` is what is being matched.
//!
//! **Why no HTTP library.** Python's refusals are its own answers, with its own status text and
//! bodies, and the libraries answer some of the same requests before any code here would run
//! (`Transfer-Encoding : chunked` is the case `docs/rust/contracts/route-table.md` names). Passing
//! a head on byte for byte needs the bytes, and a parsed head has lost them. So the front reads
//! the head itself.
//!
//! **What this file may decide is one way round only.** Whatever the front can't be sure of goes
//! to Python, which runs the same checks and answers for itself. So a mistake here that is too
//! lenient costs nothing. Refusing what Python would take is the mistake to avoid, and each refusal
//! below is one line of Python's.
//!
//! **The boot secret is the exception, so it is decided here as well.** Forwarding adds the proof
//! that a request came from the front, so "send it to Python" isn't safe for anything Python would
//! read as under `/private/`. [`Head::may_carry_proof`] says, from [`python_reads`], and
//! `forward::for_python` won't add the proof without asking. A front that misreads a line the other
//! way leaves Python answering a request with no proof, which is Python refusing it.

use std::net::Ipv6Addr;
use std::ops::Range;

use crate::launch::PRIVATE_PREFIX;

/// `http.client._MAXLINE`: the longest request line or header line.
pub const MAX_LINE: usize = 65536;
/// `http.client._MAXHEADERS`.
pub const MAX_HEADERS: usize = 100;

/// One header as `email.message.Message.get` gives it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Header {
    pub name: String,
    pub value: String,
    /// Where its lines are in the head, continuation lines included.
    pub raw: Range<usize>,
}

/// What the request line says.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Line {
    /// `<method> <target> HTTP/<major>.<minor>`, below 2.0, with a method whose name Python's
    /// `repr` shows as it is.
    Plain {
        method: String,
        target: String,
        /// Python's `close_connection` after the version, before any `Connection` header.
        http_1_1: bool,
    },
    /// `GET <target>`, HTTP/0.9's form. Python routes it as it does any GET, after reading headers
    /// for it, and writes the answer's body alone, with no status line and no headers.
    Bare { target: String },
    /// Anything else with words in it. Python has an answer for each, none of them reaches a route,
    /// and every one of them ends the connection, so it gets the head to give it.
    Odd,
    /// No words at all. Python ends the connection without answering.
    Empty,
}

/// A head that isn't a request, in Python's words.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Refusal {
    /// `http.client.LineTooLong`, from `parse_request`.
    HeaderLineTooLong,
    /// `http.client.HTTPException`, from `parse_request`.
    TooManyHeaders,
    /// `handle_one_request`, before anything is parsed.
    RequestLineTooLong,
    /// A defect from the `email` parser, or something left over after the headers.
    NotNameValue,
    MoreThanOneContentLength,
    ContentLengthNotDigits,
}

/// A head, read.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Head {
    /// Exactly what was sent, including the end of the head.
    pub raw: Vec<u8>,
    pub line: Line,
    pub headers: Vec<Header>,
    /// Where a header can be added: straight after the last one, inside the block whatever else
    /// the block holds.
    pub add_at: usize,
    /// Set by [`parse`], and `None` when nothing is wrong with it.
    pub refusal: Option<Refusal>,
    /// `multipart/` and `message/` send the `email` parser down paths this file doesn't follow.
    /// Python gets the question whatever the table says.
    pub only_python_can_say: bool,
}

impl Head {
    /// `email.message.Message.get`: the first with this name, case-insensitively.
    pub fn get(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|header| header.name.eq_ignore_ascii_case(name))
            .map(|header| header.value.as_str())
    }

    /// `headers.get(name)` is truthy in Python.
    pub fn has_value(&self, name: &str) -> bool {
        self.get(name).is_some_and(|value| !value.is_empty())
    }

    /// `int(headers.get("Content-Length") or 0)`. Only after [`Refusal`]s have been answered, so
    /// the value is digits. One past `u64` still means "more than will ever come".
    pub fn content_length(&self) -> u64 {
        match self.get("Content-Length") {
            Some(digits) if !digits.is_empty() => digits.parse().unwrap_or(u64::MAX),
            _ => 0,
        }
    }

    /// Whether Python may be told this request came from the front. Only a line it would route can
    /// need that, and only to somewhere that isn't `/private/`. The rest have no use for it: Python
    /// answers them from their first line or their method, with no reference to the proof.
    pub fn may_carry_proof(&self) -> bool {
        match &self.line {
            Line::Plain { target, .. } | Line::Bare { target } => {
                python_reads(target) == Reads::Elsewhere
            }
            Line::Odd | Line::Empty => false,
        }
    }

    /// `urlparse` raises on this target, as far as the front can tell. Python's handler dies on it,
    /// so a connection it then closes without a word is its answer to this, and isn't Python going.
    pub fn python_cannot_parse_its_target(&self) -> bool {
        match &self.line {
            Line::Plain { target, .. } | Line::Bare { target } => read_target(target).1,
            Line::Odd | Line::Empty => false,
        }
    }

    /// [`Head::content_length`], once a [`Refusal`] has had its say: `None` of those here means a
    /// body of this length. A refused head's isn't read.
    pub fn content_length_if_framed(&self) -> u64 {
        if self.refusal.is_some() {
            0
        } else {
            self.content_length()
        }
    }

    pub fn expects_continue(&self) -> bool {
        matches!(self.line, Line::Plain { http_1_1: true, .. })
            && self
                .get("Expect")
                .is_some_and(|value| value.eq_ignore_ascii_case("100-continue"))
    }

    /// `close_connection` once `parse_request` has seen the `Connection` header.
    pub fn client_asked_to_close(&self) -> bool {
        let Line::Plain { http_1_1, .. } = self.line else {
            return true;
        };
        let asked = self.get("Connection").unwrap_or("");
        if asked.eq_ignore_ascii_case("close") {
            true
        } else if asked.eq_ignore_ascii_case("keep-alive") {
            false
        } else {
            !http_1_1
        }
    }

    /// `_unconsumed_body`, for a request whose framing is good: its answer closes the connection.
    pub fn body_goes_unread(&self, method: &str) -> bool {
        if self.has_value("Transfer-Encoding") {
            return true;
        }
        if method == "POST" {
            return false;
        }
        self.get("Content-Length")
            .filter(|value| !value.is_empty())
            .unwrap_or("0")
            != "0"
    }
}

/// `str.isspace`, for a character of a head decoded as Latin-1.
pub fn python_space(byte: u8) -> bool {
    matches!(byte, 0x09..=0x0d | 0x1c..=0x20 | 0x85 | 0xa0)
}

/// Latin-1, as Python decodes a head.
pub fn latin1(bytes: &[u8]) -> String {
    bytes.iter().map(|&b| char::from(b)).collect()
}

/// `true` for a line that ends the head when read with `readline`: Python compares it whole.
fn ends_head(line: &[u8]) -> bool {
    line == b"\r\n" || line == b"\n"
}

/// How far the head reaches in `buffer`, by `readline`'s rule. `None` when more bytes could change
/// the answer.
///
/// A head ends at a line that is only a line ending, or at the end of what the client will send
/// (`at_eof`). Lines too long or too many end it early: Python stops reading there and refuses.
pub fn head_end(buffer: &[u8], at_eof: bool) -> Option<HeadEnd> {
    let (first, rest_start) = match memchr_newline(buffer, 0) {
        Some(end) => (&buffer[..end], end),
        None if buffer.len() > MAX_LINE => return Some(HeadEnd::RequestLineTooLong),
        None if at_eof => {
            return Some(HeadEnd::At(buffer.len()));
        }
        None => return None,
    };
    if first.len() > MAX_LINE {
        return Some(HeadEnd::RequestLineTooLong);
    }
    if answered_from_its_first_line(first) {
        return Some(HeadEnd::At(rest_start));
    }
    let mut at = rest_start;
    let mut lines = 0;
    loop {
        let Some(end) = memchr_newline(buffer, at) else {
            if buffer.len() - at > MAX_LINE {
                return Some(HeadEnd::At(buffer.len()));
            }
            return at_eof.then_some(HeadEnd::At(buffer.len()));
        };
        let line = &buffer[at..end];
        if line.len() > MAX_LINE {
            return Some(HeadEnd::At(end));
        }
        if ends_head(line) {
            return Some(HeadEnd::At(end));
        }
        lines += 1;
        if lines > MAX_HEADERS {
            return Some(HeadEnd::At(end));
        }
        at = end;
    }
}

/// `parse_request` answers these before it reads a header, so waiting for more would hold up an
/// answer Python gives at once: no words, one word, more than three, a version it can't read or
/// won't speak, and HTTP/0.9 asking for anything but GET.
fn answered_from_its_first_line(line: &[u8]) -> bool {
    match python_words(without_ending(line))[..] {
        [_, _, version] => !http_version(version).is_some_and(|(major, _)| major < 2),
        [method, _] => method != b"GET",
        _ => true,
    }
}

/// Where a head ended, by [`head_end`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HeadEnd {
    At(usize),
    RequestLineTooLong,
}

/// The end of the line starting at `from`, past its `\n`.
fn memchr_newline(buffer: &[u8], from: usize) -> Option<usize> {
    buffer[from..]
        .iter()
        .position(|&b| b == b'\n')
        .map(|at| from + at + 1)
}

/// `email.feedparser.headerRE`: `^(From |[\041-\071\073-\176]*:|[\t ])`.
fn looks_like_a_header_line(line: &[u8]) -> bool {
    if line.starts_with(b"From ") || line.first().is_some_and(|&b| b == b'\t' || b == b' ') {
        return true;
    }
    match line.iter().position(|&b| b == b':') {
        Some(colon) => line[..colon]
            .iter()
            .all(|b| matches!(b, 0x21..=0x39 | 0x3b..=0x7e)),
        None => false,
    }
}

/// The line ending at the end of `line`, by universal newlines.
fn without_ending(line: &[u8]) -> &[u8] {
    let line = line.strip_suffix(b"\n").unwrap_or(line);
    line.strip_suffix(b"\r").unwrap_or(line)
}

/// `line.split()`, for a request line.
fn python_words(line: &[u8]) -> Vec<&[u8]> {
    line.split(|&b| python_space(b))
        .filter(|word| !word.is_empty())
        .collect()
}

fn read_line(words: &[&[u8]]) -> Line {
    match words {
        [] => Line::Empty,
        [b"GET", target] => Line::Bare {
            target: latin1(target),
        },
        [method, target, version] => {
            let simple_method = !method.is_empty()
                && method
                    .iter()
                    .all(|b| b.is_ascii_alphanumeric() || *b == b'_' || *b == b'-');
            match (simple_method, http_version(version)) {
                (true, Some((major, minor))) if major < 2 => Line::Plain {
                    method: latin1(method),
                    target: latin1(target),
                    http_1_1: (major, minor) >= (1, 1),
                },
                _ => Line::Odd,
            }
        }
        _ => Line::Odd,
    }
}

/// `HTTP/<digits>.<digits>`, each short enough for Python to read it.
fn http_version(word: &[u8]) -> Option<(u64, u64)> {
    let version = word.strip_prefix(b"HTTP/")?;
    let dot = version.iter().position(|&b| b == b'.')?;
    let (major, minor) = (&version[..dot], &version[dot + 1..]);
    let digits = |part: &[u8]| {
        (!part.is_empty() && part.len() <= 10 && part.iter().all(u8::is_ascii_digit))
            .then(|| latin1(part).parse::<u64>().ok())
            .flatten()
    };
    Some((digits(major)?, digits(minor)?))
}

/// What Python's parse makes of a request's target.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Reads {
    /// Its path is under `/private/`, so it is the front's own and never goes to Python.
    Private,
    /// Its path would be, but `urlparse` raises on it, as far as the front can tell. Python ends the
    /// connection without a word, so it goes there to do that, without the proof. If the front has
    /// this wrong and Python does parse it, Python has no proof in front of it and refuses.
    PrivateIfItParsed,
    /// Anywhere else, or nowhere: it may carry the proof.
    Elsewhere,
}

/// `parse_request`'s `//` and then `urllib.parse.urlparse(self.path).path`, Python 3.12's, as far as
/// whether it starts `/private/`. `tests/front/request_forms.py` holds this to the real thing.
///
/// Left out because they can't change that answer: taking out tabs and line endings (they end a word
/// of the request line, so a target has none), and `;params`, which `_splitparams` looks for only
/// after the last `/` and so can't reach the prefix's. `_checknetloc` is left out because nothing in
/// Latin-1 normalises to what it looks for.
pub fn python_reads(target: &str) -> Reads {
    match read_target(target) {
        (false, _) => Reads::Elsewhere,
        (true, false) => Reads::Private,
        (true, true) => Reads::PrivateIfItParsed,
    }
}

/// Whether the path would be under `/private/`, and whether `urlparse` raises.
fn read_target(target: &str) -> (bool, bool) {
    let collapsed;
    let url = if target.starts_with("//") {
        collapsed = format!("/{}", target.trim_start_matches('/'));
        collapsed.as_str()
    } else {
        target
    };
    // `_WHATWG_C0_CONTROL_OR_SPACE`.
    let url = url.trim_start_matches(|c: char| c <= ' ');
    let after_scheme = match url.find(':') {
        Some(colon)
            if colon > 0
                && url.as_bytes()[0].is_ascii_alphabetic()
                && url[..colon]
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'+' | b'-' | b'.')) =>
        {
            &url[colon + 1..]
        }
        _ => url,
    };
    let (netloc, rest) = match after_scheme.strip_prefix("//") {
        Some(after) => after.split_at(after.find(['/', '?', '#']).unwrap_or(after.len())),
        None => ("", after_scheme),
    };
    let path = rest.split(['#', '?']).next().unwrap_or("");
    (path.starts_with(PRIVATE_PREFIX), netloc_raises(netloc))
}

/// The checks `urlsplit` makes of a netloc with brackets in it.
fn netloc_raises(netloc: &str) -> bool {
    if netloc.contains('[') != netloc.contains(']') {
        return true;
    }
    if !netloc.contains('[') {
        return false;
    }
    // `_check_bracketed_netloc`.
    let host_and_port = netloc.rsplit_once('@').map_or(netloc, |(_, after)| after);
    let host = match host_and_port.split_once('[') {
        Some((before, _)) if !before.is_empty() => return true,
        Some((_, bracketed)) => {
            let (host, port) = bracketed.split_once(']').unwrap_or((bracketed, ""));
            if !port.is_empty() && !port.starts_with(':') {
                return true;
            }
            host
        }
        None => host_and_port
            .split_once(':')
            .map_or(host_and_port, |(host, _)| host),
    };
    // `_check_bracketed_host`.
    if let Some(future) = host.strip_prefix('v') {
        return !future.split_once('.').is_some_and(|(version, rest)| {
            !version.is_empty()
                && version.bytes().all(|b| b.is_ascii_hexdigit())
                && !rest.is_empty()
        });
    }
    // `ipaddress.ip_address`, with a scope that is one non-empty word.
    let address = match host.split_once('%') {
        Some((_, scope)) if scope.is_empty() || scope.contains('%') => return true,
        Some((address, _)) => address,
        None => host,
    };
    address.parse::<Ipv6Addr>().is_err()
}

/// Read a head that [`head_end`] bounded.
pub fn parse(raw: Vec<u8>) -> Head {
    let first_end = memchr_newline(&raw, 0).unwrap_or(raw.len());
    let first_line = without_ending(&raw[..first_end]);
    let line = read_line(&python_words(first_line));

    let mut head = Head {
        raw: Vec::new(),
        line,
        headers: Vec::new(),
        add_at: first_end,
        refusal: None,
        only_python_can_say: false,
    };
    if matches!(head.line, Line::Empty) {
        head.raw = raw;
        return head;
    }
    read_headers(&raw, first_end, &mut head);
    head.raw = raw;

    if head.refusal.is_some() {
        return head;
    }
    let lengths: Vec<&str> = head
        .headers
        .iter()
        .filter(|header| header.name.eq_ignore_ascii_case("Content-Length"))
        .map(|header| header.value.as_str())
        .collect();
    if lengths.len() > 1 {
        head.refusal = Some(Refusal::MoreThanOneContentLength);
    } else if let [value] = lengths[..]
        && (value.is_empty() || !value.bytes().all(|b| b.is_ascii_digit()))
    {
        head.refusal = Some(Refusal::ContentLengthNotDigits);
    }
    let content_type = head.get("Content-Type").unwrap_or("").to_ascii_lowercase();
    head.only_python_can_say =
        content_type.starts_with("multipart/") || content_type.starts_with("message/");
    head
}

/// `http.client.parse_headers`, then the `email` parser's reading of the block.
fn read_headers(raw: &[u8], block_start: usize, head: &mut Head) {
    // First by `readline`, as `parse_headers` counts and limits them.
    let mut at = block_start;
    let mut physical = 0;
    let mut block_end = block_start;
    while at < raw.len() {
        let end = memchr_newline(raw, at).unwrap_or(raw.len());
        let line = &raw[at..end];
        if line.len() > MAX_LINE {
            head.refusal = Some(Refusal::HeaderLineTooLong);
            return;
        }
        if ends_head(line) {
            break;
        }
        physical += 1;
        if physical > MAX_HEADERS {
            head.refusal = Some(Refusal::TooManyHeaders);
            return;
        }
        at = end;
        block_end = end;
    }

    // Then by the `email` parser's lines: universal newlines, so a bare CR ends one too. Reading
    // these any other way is how a smuggled header gets past the front and not past Python.
    let mut lines = Vec::new();
    let mut from = block_start;
    let mut index = block_start;
    while index < block_end {
        match raw[index] {
            b'\n' => {
                lines.push(from..index + 1);
                index += 1;
                from = index;
            }
            b'\r' => {
                let end = if raw.get(index + 1) == Some(&b'\n') && index + 1 < block_end {
                    index + 2
                } else {
                    index + 1
                };
                lines.push(from..end);
                index = end;
                from = index;
            }
            _ => index += 1,
        }
    }
    if from < block_end {
        lines.push(from..block_end);
    }

    let mut current: Option<(String, Range<usize>)> = None;
    let mut leftover_from = None;
    let mut last_kept = block_start;
    for (number, range) in lines.iter().enumerate() {
        let line = &raw[range.clone()];
        if without_ending(line).is_empty() {
            // The parser's own separator: what follows is a payload, whitespace or not.
            leftover_from = Some(range.end);
            break;
        }
        if !looks_like_a_header_line(line) {
            head.refusal = Some(Refusal::NotNameValue);
            return;
        }
        if line[0] == b' ' || line[0] == b'\t' {
            match &mut current {
                Some((_, whole)) => whole.end = range.end,
                None => {
                    head.refusal = Some(Refusal::NotNameValue);
                    return;
                }
            }
            last_kept = range.end;
            continue;
        }
        store(raw, &mut current, &mut head.headers);
        if line.starts_with(b"From ") {
            if number == 0 {
                // A Unix envelope line: not a header, and no defect.
                last_kept = range.end;
                continue;
            }
            // Later than that it is a defect, or the start of a payload that then isn't blank.
            head.refusal = Some(Refusal::NotNameValue);
            return;
        }
        if line[0] == b':' {
            head.refusal = Some(Refusal::NotNameValue);
            return;
        }
        current = Some((String::new(), range.clone()));
        last_kept = range.end;
    }
    store(raw, &mut current, &mut head.headers);
    head.add_at = last_kept;

    if let Some(from) = leftover_from
        && raw[from..block_end].iter().any(|&b| !python_space(b))
    {
        head.refusal = Some(Refusal::NotNameValue);
    }
}

/// `Compat32.header_source_parse`: the first line's value with its leading blanks gone, the
/// continuation lines as they are, and the final line ending gone.
fn store(raw: &[u8], current: &mut Option<(String, Range<usize>)>, into: &mut Vec<Header>) {
    let Some((_, range)) = current.take() else {
        return;
    };
    let whole = &raw[range.clone()];
    let colon = whole
        .iter()
        .position(|&b| b == b':')
        .expect("a line is only kept as a header once it has a colon");
    let name = latin1(&whole[..colon]);
    let mut value = &whole[colon + 1..];
    while let [b' ' | b'\t', rest @ ..] = value {
        value = rest;
    }
    while let [rest @ .., b'\r' | b'\n'] = value {
        value = rest;
    }
    into.push(Header {
        name,
        value: latin1(value),
        raw: range,
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn head(text: &[u8]) -> Head {
        parse(text.to_vec())
    }

    #[test]
    fn a_plain_get_is_read_with_its_headers_in_order() {
        let got = head(b"GET /api/pulse?since=1 HTTP/1.1\r\nHost: a\r\nX-Two:  b \r\n\r\n");
        assert_eq!(
            got.line,
            Line::Plain {
                method: "GET".into(),
                target: "/api/pulse?since=1".into(),
                http_1_1: true
            }
        );
        assert_eq!(got.get("host"), Some("a"));
        assert_eq!(got.get("x-two"), Some("b "));
        assert_eq!(got.refusal, None);
        assert_eq!(&got.raw[got.add_at..], b"\r\n");
    }

    #[test]
    fn a_space_before_the_colon_is_python_s_400() {
        let got = head(b"GET / HTTP/1.1\r\nTransfer-Encoding : chunked\r\nHost: a\r\n\r\n");
        assert_eq!(got.refusal, Some(Refusal::NotNameValue));
    }

    #[test]
    fn content_length_is_one_value_of_digits() {
        for (text, refusal) in [
            ("Content-Length: 2", None),
            ("Content-Length: 0", None),
            (
                "Content-Length: 2\r\nContent-Length: 2",
                Some(Refusal::MoreThanOneContentLength),
            ),
            (
                "Content-Length: 2\r\ncontent-length: 3",
                Some(Refusal::MoreThanOneContentLength),
            ),
            ("Content-Length: +2", Some(Refusal::ContentLengthNotDigits)),
            ("Content-Length: 2 ", Some(Refusal::ContentLengthNotDigits)),
            ("Content-Length: x", Some(Refusal::ContentLengthNotDigits)),
            ("Content-Length: ", Some(Refusal::ContentLengthNotDigits)),
            (
                "Content-Length: 2\r\n 3",
                Some(Refusal::ContentLengthNotDigits),
            ),
        ] {
            let got = head(format!("POST /x HTTP/1.1\r\n{text}\r\n\r\n").as_bytes());
            assert_eq!(got.refusal, refusal, "{text}");
        }
    }

    #[test]
    fn the_email_parser_s_other_defects_are_refused_too() {
        for text in [
            &b"GET / HTTP/1.1\r\n continuation first\r\n\r\n"[..],
            b"GET / HTTP/1.1\r\n: no name\r\n\r\n",
            b"GET / HTTP/1.1\r\nno colon here\r\n\r\n",
            b"GET / HTTP/1.1\r\nA: b\r\nFrom someone\r\nC: d\r\n\r\n",
            b"GET / HTTP/1.1\r\nA: b\r\nFrom someone\r\n\r\n",
            b"GET / HTTP/1.1\r\nA: b\r\rSmuggled: yes\r\n\r\n",
        ] {
            assert_eq!(
                head(text).refusal,
                Some(Refusal::NotNameValue),
                "{}",
                latin1(text)
            );
        }
    }

    #[test]
    fn a_bare_cr_ends_a_header_as_it_does_in_python() {
        let got = head(b"GET / HTTP/1.1\r\nA: b\rX-Mentis-Peer: forged\r\nC: d\r\n\r\n");
        assert_eq!(got.refusal, None);
        assert_eq!(got.get("A"), Some("b"));
        assert_eq!(got.get("X-Mentis-Peer"), Some("forged"));
        assert_eq!(got.get("C"), Some("d"));
    }

    #[test]
    fn a_folded_header_keeps_its_lines_and_its_whole_range() {
        let text = b"GET / HTTP/1.1\r\nA: b\r\n c\r\nD: e\r\n\r\n";
        let got = head(text);
        assert_eq!(got.get("A"), Some("b\r\n c"));
        let a = &got.headers[0];
        assert_eq!(&text[a.raw.clone()], b"A: b\r\n c\r\n");
    }

    #[test]
    fn an_envelope_first_line_is_no_header_and_no_defect() {
        let got = head(b"GET / HTTP/1.1\r\nFrom x\r\nA: b\r\n\r\n");
        assert_eq!(got.refusal, None);
        assert_eq!(got.headers.len(), 1);
        assert_eq!(&got.raw[got.add_at..], b"\r\n");
    }

    #[test]
    fn what_a_request_line_may_be() {
        let plain = |text: &[u8]| head(text).line;
        assert!(matches!(
            plain(b"GET / HTTP/1.0\r\n\r\n"),
            Line::Plain {
                http_1_1: false,
                ..
            }
        ));
        assert_eq!(plain(b"GET /\r\n\r\n"), Line::Bare { target: "/".into() });
        for odd in [
            &b"POST /\r\n\r\n"[..],
            b"GET / HTTP/x\r\n\r\n",
            b"GET / HTTP/2.0\r\n\r\n",
            b"GET / extra HTTP/1.1\r\n\r\n",
            b"G'T / HTTP/1.1\r\n\r\n",
            b"GET /\xa0a HTTP/1.1\r\n\r\n",
        ] {
            assert_eq!(plain(odd), Line::Odd, "{}", latin1(odd));
        }
        assert_eq!(plain(b"\r\n"), Line::Empty);
    }

    #[test]
    fn a_target_is_read_as_python_s_own_parse_reads_it() {
        let table = include_str!("../../tests/python_targets.tsv");
        let mut wrong = Vec::new();
        for line in table.lines() {
            let (hex, reads) = line.split_once('\t').unwrap();
            let bytes: Vec<u8> = (0..hex.len() / 2)
                .map(|at| u8::from_str_radix(&hex[at * 2..at * 2 + 2], 16).unwrap())
                .collect();
            let target = latin1(&bytes);
            let expected = match reads {
                "private" => Reads::Private,
                "raises" => Reads::PrivateIfItParsed,
                _ => Reads::Elsewhere,
            };
            if python_reads(&target) != expected {
                wrong.push(format!("{target:?}: Python {reads}"));
            }
        }
        assert!(table.lines().count() > 1000, "the table is what it was");
        assert!(wrong.is_empty(), "{} wrong: {wrong:#?}", wrong.len());
    }

    #[test]
    fn only_a_line_python_routes_elsewhere_may_carry_the_proof() {
        for (text, carries) in [
            (&b"GET /x HTTP/1.1\r\n\r\n"[..], true),
            (b"GET /x\r\n\r\n", true),
            (b"GET x/private/y HTTP/1.1\r\n\r\n", true),
            (b"GET /private/x HTTP/1.1\r\n\r\n", false),
            (b"GET /private/x\r\n\r\n", false),
            (b"GET //private/x\r\n\r\n", false),
            (b"GET http://[/private/x HTTP/1.1\r\n\r\n", false),
            (b"G'T /x HTTP/1.1\r\n\r\n", false),
            (b"GET /x HTTP/2.0\r\n\r\n", false),
            (b"POST /x\r\n\r\n", false),
            (b"GET\r\n\r\n", false),
            (b"\r\n", false),
        ] {
            assert_eq!(head(text).may_carry_proof(), carries, "{}", latin1(text));
        }
    }

    #[test]
    fn multipart_is_left_to_python() {
        let got = head(b"POST /x HTTP/1.1\r\nContent-Type: Multipart/form-data\r\n\r\n");
        assert!(got.only_python_can_say);
        assert_eq!(got.refusal, None);
    }

    #[test]
    fn the_end_of_a_head_is_where_readline_finds_it() {
        assert_eq!(head_end(b"GET / HTTP/1.1\r\nA: b\r\n", false), None);
        assert_eq!(
            head_end(b"GET / HTTP/1.1\r\nA: b\r\n", true),
            Some(HeadEnd::At(22))
        );
        assert_eq!(
            head_end(b"GET / HTTP/1.1\r\nA: b\r\n\r\nrest", false),
            Some(HeadEnd::At(24))
        );
        assert_eq!(
            head_end(b"GET / HTTP/1.1\nA: b\n\nrest", false),
            Some(HeadEnd::At(21))
        );
        // A bare CR line isn't the end by readline's rule, though the email parser stops there.
        assert_eq!(
            head_end(b"GET / HTTP/1.1\r\nA: b\r\r\n\r\n", false),
            Some(HeadEnd::At(25))
        );
        for answered_at_once in [
            &b"
"[..],
            b"GET
",
            b"GET / b c
",
            b"GET / HTTP/x
",
            b"GET / HTTP/2.0
",
            b"POST /x
",
        ] {
            assert_eq!(
                head_end(answered_at_once, false),
                Some(HeadEnd::At(answered_at_once.len())),
                "{}",
                latin1(answered_at_once)
            );
        }
        assert_eq!(
            head_end(
                b"GET /x
Host: a
",
                false
            ),
            None
        );
        let long = vec![b'x'; MAX_LINE + 1];
        assert_eq!(head_end(&long, false), Some(HeadEnd::RequestLineTooLong));
    }

    #[test]
    fn limits_are_python_s() {
        let mut many = b"GET / HTTP/1.1\r\n".to_vec();
        for n in 0..MAX_HEADERS {
            many.extend_from_slice(format!("A{n}: b\r\n").as_bytes());
        }
        let mut allowed = many.clone();
        allowed.extend_from_slice(b"\r\n");
        assert_eq!(head(&allowed).refusal, None);
        many.extend_from_slice(b"One-More: b\r\n\r\n");
        assert_eq!(head(&many).refusal, Some(Refusal::TooManyHeaders));

        let mut long = b"GET / HTTP/1.1\r\nA: ".to_vec();
        long.extend(std::iter::repeat_n(b'x', MAX_LINE));
        long.extend_from_slice(b"\r\n\r\n");
        assert_eq!(head(&long).refusal, Some(Refusal::HeaderLineTooLong));
    }
}
