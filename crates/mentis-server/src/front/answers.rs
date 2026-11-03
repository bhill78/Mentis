//! Answers the front gives itself, byte for byte as `_Handler` gives them: the same status text,
//! the same headers in the same order, the same JSON spacing.
//!
//! `R1-acceptance.md` lists what may differ from Python alone and none of this is on the list. So
//! `Server` says what Python's says: a client can't tell which side answered, and any difference
//! is one somebody has to explain.

use std::time::{SystemTime, UNIX_EPOCH};

use super::head::Refusal;

/// `BaseHTTPRequestHandler.version_string()`, for the Python R1 runs on.
pub const SERVER: &str = "BaseHTTP/0.6 Python/3.12.10";

/// `error_message_format`.
const ERROR_PAGE: [&str; 4] = [
    "<!DOCTYPE HTML>\n<html lang=\"en\">\n    <head>\n        <meta charset=\"utf-8\">\n        <title>Error response</title>\n    </head>\n    <body>\n        <h1>Error response</h1>\n        <p>Error code: ",
    "</p>\n        <p>Message: ",
    ".</p>\n        <p>Error code explanation: ",
    ".</p>\n    </body>\n</html>\n",
];

/// `http.HTTPStatus(code).phrase`, for what the front or a handler answers.
pub fn phrase(code: u16) -> &'static str {
    match code {
        200 => "OK",
        201 => "Created",
        204 => "No Content",
        400 => "Bad Request",
        403 => "Forbidden",
        404 => "Not Found",
        409 => "Conflict",
        // Python 3.13's. `door.json` holds an activation's to these words on every Python.
        413 => "Content Too Large",
        415 => "Unsupported Media Type",
        421 => "Misdirected Request",
        422 => "Unprocessable Entity",
        500 => "Internal Server Error",
        501 => "Not Implemented",
        502 => "Bad Gateway",
        503 => "Service Unavailable",
        _ => "",
    }
}

/// An answer, ready to send.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Written {
    pub bytes: Vec<u8>,
    /// This answer ends the connection.
    pub closes: bool,
}

/// `email.utils.formatdate(usegmt=True)`, what `date_time_string` gives.
fn http_date(seconds: u64) -> String {
    const DAYS: [&str; 7] = ["Thu", "Fri", "Sat", "Sun", "Mon", "Tue", "Wed"];
    const MONTHS: [&str; 12] = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    let days = seconds / 86400;
    let in_day = seconds % 86400;
    // Howard Hinnant's civil_from_days.
    let shifted = days + 719_468;
    let era = shifted / 146_097;
    let of_era = shifted % 146_097;
    let year_of_era = (of_era - of_era / 1460 + of_era / 36_524 - of_era / 146_096) / 365;
    let day_of_year = of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let shifted_month = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * shifted_month + 2) / 5 + 1;
    let month = if shifted_month < 10 {
        shifted_month + 3
    } else {
        shifted_month - 9
    };
    let year = year_of_era + era * 400 + u64::from(month <= 2);
    format!(
        "{}, {:02} {} {} {:02}:{:02}:{:02} GMT",
        DAYS[(days % 7) as usize],
        day,
        MONTHS[(month - 1) as usize],
        year,
        in_day / 3600,
        in_day % 3600 / 60,
        in_day % 60
    )
}

fn now_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |since| since.as_secs())
}

/// `_Handler.send_response` as far as `Connection: close`.
fn status_block(code: u16, message: &str, closing: bool) -> String {
    let mut out = format!(
        "HTTP/1.1 {code} {message}\r\nServer: {SERVER}\r\nDate: {}\r\n",
        http_date(now_seconds())
    );
    if closing {
        out.push_str("Connection: close\r\n");
    }
    out
}

/// `_Handler._send`. A status of 400 or more closes, and so does an answer whose request's body
/// went unread. `client_closes` is the client's own `Connection: close`, which Python honours
/// without saying so in a header.
pub fn send(
    code: u16,
    content_type: &str,
    body: &[u8],
    body_unread: bool,
    client_closes: bool,
) -> Written {
    let closing = code >= 400 || body_unread;
    let mut head = status_block(code, phrase(code), closing);
    head.push_str(&format!(
        "Content-Type: {content_type}\r\nContent-Length: {}\r\nCache-Control: no-store\r\n\r\n",
        body.len()
    ));
    let mut bytes = head.into_bytes();
    bytes.extend_from_slice(body);
    Written {
        bytes,
        closes: closing || client_closes,
    }
}

/// `_artifact_send`: `_send`, and the artifact routes' protections after what it says.
pub fn send_artifact(
    code: u16,
    content_type: &str,
    body: &[u8],
    body_unread: bool,
    client_closes: bool,
) -> Written {
    let closing = code >= 400 || body_unread;
    let mut head = status_block(code, phrase(code), closing);
    head.push_str(&format!(
        "Content-Type: {content_type}\r\nContent-Length: {}\r\nCache-Control: no-store\r\n\
         X-Content-Type-Options: nosniff\r\n\
         Content-Security-Policy: sandbox; default-src 'none'; img-src data:; \
         style-src 'unsafe-inline'\r\n\
         Cross-Origin-Resource-Policy: same-origin\r\nReferrer-Policy: no-referrer\r\n\r\n",
        body.len()
    ));
    let mut bytes = head.into_bytes();
    bytes.extend_from_slice(body);
    Written {
        bytes,
        closes: closing || client_closes,
    }
}

/// `_send` with a JSON payload.
pub fn send_json(code: u16, json: &str, body_unread: bool, client_closes: bool) -> Written {
    send(
        code,
        "application/json",
        json.as_bytes(),
        body_unread,
        client_closes,
    )
}

/// `BaseHTTPRequestHandler.send_error`, under `_Handler.send_response`: `Connection: close` twice,
/// and the status line carries the message rather than the phrase. A HEAD has the headers and no
/// body.
pub fn send_error(code: u16, message: &str, explain: &str, method_is_head: bool) -> Written {
    let page = format!(
        "{}{code}{}{}{}{code} - {}{}",
        ERROR_PAGE[0],
        ERROR_PAGE[1],
        html_escape(message),
        ERROR_PAGE[2],
        html_escape(explain),
        ERROR_PAGE[3]
    );
    let mut head = status_block(code, message, true);
    head.push_str(&format!(
        "Connection: close\r\nContent-Type: text/html;charset=utf-8\r\nContent-Length: {}\r\n\r\n",
        page.len()
    ));
    let mut bytes = head.into_bytes();
    if !method_is_head {
        bytes.extend_from_slice(page.as_bytes());
    }
    Written {
        bytes,
        closes: true,
    }
}

/// `parse_request`'s refusals and `handle_one_request`'s, exactly as each is sent.
pub fn refusal(refusal: &Refusal, method_is_head: bool) -> Written {
    match refusal {
        Refusal::NotNameValue => send_error(
            400,
            "a header line is not `Name: value`",
            "Bad request syntax or unsupported method",
            method_is_head,
        ),
        Refusal::MoreThanOneContentLength => send_error(
            400,
            "more than one Content-Length",
            "Bad request syntax or unsupported method",
            method_is_head,
        ),
        Refusal::ContentLengthNotDigits => send_error(
            400,
            "Content-Length must be digits only",
            "Bad request syntax or unsupported method",
            method_is_head,
        ),
        Refusal::RequestLineTooLong => send_error(
            414,
            "Request-URI Too Long",
            "URI is too long",
            method_is_head,
        ),
        Refusal::HeaderLineTooLong => send_error(
            431,
            "Line too long",
            "got more than 65536 bytes when reading header line",
            method_is_head,
        ),
        Refusal::TooManyHeaders => send_error(
            431,
            "Too many headers",
            "got more than 100 headers",
            method_is_head,
        ),
    }
}

/// `send_error(501, "Unsupported method (%r)")`. `method` is letters, digits, `_` or `-`, so its
/// `repr` is itself in quotes.
pub fn unsupported_method(method: &str) -> Written {
    send_error(
        501,
        &format!("Unsupported method ('{method}')"),
        "Server does not support this operation",
        method == "HEAD",
    )
}

/// `html.escape(text, quote=False)`.
fn html_escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

/// `json.dumps(text)`: ASCII only, as Python's default.
pub fn json_string(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
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
    out
}

/// `json.dumps` of a flat object of strings, in this order.
pub fn json_object(fields: &[(&str, &str)]) -> String {
    let body: Vec<String> = fields
        .iter()
        .map(|(name, value)| format!("{}: {}", json_string(name), json_string(value)))
        .collect();
    format!("{{{}}}", body.join(", "))
}

/// `repr(text)` for what a Latin-1 head can hold.
pub fn python_repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::with_capacity(text.len() + 2);
    out.push(quote);
    for c in text.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            ' '..='~' => out.push(c),
            // In Latin-1, `str.isprintable` is false for controls, NBSP and the soft hyphen.
            '\u{a1}'..='\u{ac}' | '\u{ae}'..='\u{ff}' => out.push(c),
            c => out.push_str(&format!("\\x{:02x}", c as u32)),
        }
    }
    out.push(quote);
    out
}

/// `_refused_host`.
pub fn refused_host(host: Option<&str>, body_unread: bool) -> Written {
    let shown = host.map_or_else(|| "None".to_owned(), python_repr);
    let error = format!(
        "Host {shown} is not one this server answers; list it in MENTIS_ALLOWED_HOSTS to allow it"
    );
    send_json(
        421,
        &json_object(&[("error", &error), ("kind", "PermissionError")]),
        body_unread,
        true,
    )
}

/// `_missing_client`.
pub fn missing_client(body_unread: bool) -> Written {
    send_json(
        403,
        &json_object(&[
            ("error", "missing X-Mentis-Client"),
            ("kind", "PermissionError"),
        ]),
        body_unread,
        true,
    )
}

/// `do_POST`, on any `Transfer-Encoding`.
pub fn transfer_encoding_refused() -> Written {
    send_json(
        501,
        &json_object(&[(
            "error",
            "Transfer-Encoding is not accepted; send a Content-Length",
        )]),
        true,
        true,
    )
}

/// A grant on a route it isn't good for, in the words of the door that route replaced.
pub fn grant_refused(wording: &str, path: &str, body_unread: bool) -> Written {
    send_json(
        403,
        &json_object(&[
            ("error", wording),
            ("kind", "PermissionError"),
            ("asked_for", path),
        ]),
        body_unread,
        true,
    )
}

/// [`grant_refused`], at a door that sends what it refuses as an artifact route does.
pub fn grant_refused_as_artifact(wording: &str, path: &str, body_unread: bool) -> Written {
    send_artifact(
        403,
        "application/json",
        json_object(&[
            ("error", wording),
            ("kind", "PermissionError"),
            ("asked_for", path),
        ])
        .as_bytes(),
        body_unread,
        true,
    )
}

/// Anything on `/private/` the public port doesn't do (`contracts/launcher.md`).
pub fn no_such_surface(body_unread: bool) -> Written {
    send_json(
        404,
        &json_object(&[("error", "no such semantic surface")]),
        body_unread,
        true,
    )
}

/// An answer to `GET <target>`, HTTP/0.9's form. `send_response_only`, `send_header` and
/// `end_headers` write nothing for it, so all that goes is the body.
pub fn for_http_0_9(answer: Written) -> Written {
    let bytes = match answer.bytes.windows(4).position(|at| at == b"\r\n\r\n") {
        Some(end) => answer.bytes[end + 4..].to_vec(),
        None => answer.bytes,
    };
    Written {
        bytes,
        closes: true,
    }
}

/// The front's own 503, whose words are frozen in `tests/front/restart_messages.json`.
pub fn python_gone(why: PythonGone) -> Written {
    send_json(503, &json_object(&[("error", why.words())]), false, true)
}

/// Why a forwarded request got no answer from Python.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PythonGone {
    /// It was connected to, and stopped before the answer's head was whole.
    Reached,
    /// It could not be connected to, so nothing of this request was sent.
    Unreached,
}

impl PythonGone {
    pub const fn words(self) -> &'static str {
        match self {
            PythonGone::Reached => {
                "Python stopped with this request in hand, so the result is unknown. It may still have done it: check the record before repeating it."
            }
            PythonGone::Unreached => {
                "Python is not answering behind this front, so this request did not reach it and nothing was done."
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn text(written: &Written) -> String {
        String::from_utf8(written.bytes.clone()).unwrap()
    }

    /// Everything but the `Date` line, which is a moment.
    fn without_date(written: &Written) -> String {
        text(written)
            .split("\r\n")
            .filter(|line| !line.starts_with("Date: "))
            .collect::<Vec<_>>()
            .join("\r\n")
    }

    #[test]
    fn dates_read_as_python_writes_them() {
        assert_eq!(http_date(0), "Thu, 01 Jan 1970 00:00:00 GMT");
        assert_eq!(http_date(1_793_578_173), "Mon, 02 Nov 2026 00:09:33 GMT");
        assert_eq!(http_date(951_782_400), "Tue, 29 Feb 2000 00:00:00 GMT");
    }

    #[test]
    fn a_refused_host_is_as_python_sent_it() {
        assert_eq!(
            without_date(&refused_host(Some("evil.example"), false)),
            "HTTP/1.1 421 Misdirected Request\r\nServer: BaseHTTP/0.6 Python/3.12.10\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: 135\r\nCache-Control: no-store\r\n\r\n{\"error\": \"Host 'evil.example' is not one this server answers; list it in MENTIS_ALLOWED_HOSTS to allow it\", \"kind\": \"PermissionError\"}"
        );
        assert!(
            text(&refused_host(None, false)).contains("\"Host None is not one"),
            "absent"
        );
    }

    #[test]
    fn repr_of_a_host_follows_python() {
        assert_eq!(python_repr("a'b"), "\"a'b\"");
        assert_eq!(python_repr("a'b\""), "'a\\'b\"'");
        assert_eq!(python_repr("a\\b\tc"), "'a\\\\b\\tc'");
        assert_eq!(
            python_repr("\u{a0}\u{ad}\u{e9}\u{7f}"),
            "'\\xa0\\xad\u{e9}\\x7f'"
        );
    }

    #[test]
    fn json_is_python_s_with_ascii_only() {
        assert_eq!(
            json_string("a\"\\\n\u{1}\u{e9}\u{1f600}"),
            "\"a\\\"\\\\\\n\\u0001\\u00e9\\ud83d\\ude00\""
        );
        assert_eq!(
            json_object(&[("error", "x"), ("kind", "y")]),
            "{\"error\": \"x\", \"kind\": \"y\"}"
        );
    }

    #[test]
    fn an_error_page_has_the_message_in_its_status_and_two_closes() {
        let page = refusal(&Refusal::MoreThanOneContentLength, false);
        assert!(page.closes);
        assert_eq!(
            without_date(&page),
            "HTTP/1.1 400 more than one Content-Length\r\nServer: BaseHTTP/0.6 Python/3.12.10\r\nConnection: close\r\nConnection: close\r\nContent-Type: text/html;charset=utf-8\r\nContent-Length: 360\r\n\r\n<!DOCTYPE HTML>\n<html lang=\"en\">\n    <head>\n        <meta charset=\"utf-8\">\n        <title>Error response</title>\n    </head>\n    <body>\n        <h1>Error response</h1>\n        <p>Error code: 400</p>\n        <p>Message: more than one Content-Length.</p>\n        <p>Error code explanation: 400 - Bad request syntax or unsupported method.</p>\n    </body>\n</html>\n"
        );
    }

    #[test]
    fn head_is_refused_with_the_length_of_a_page_it_does_not_send() {
        let page = unsupported_method("HEAD");
        let text = text(&page);
        assert!(text.starts_with("HTTP/1.1 501 Unsupported method ('HEAD')\r\n"));
        assert!(text.ends_with("Content-Length: 357\r\n\r\n"), "{text}");
        let put = self::text(&unsupported_method("PUT"));
        assert!(
            put.contains("Content-Length: 356\r\n\r\n<!DOCTYPE"),
            "{put}"
        );
    }

    #[test]
    fn http_0_9_gets_the_body_alone() {
        let answer = for_http_0_9(no_such_surface(false));
        assert_eq!(text(&answer), "{\"error\": \"no such semantic surface\"}");
        assert!(answer.closes);
    }

    #[test]
    fn the_503_says_the_frozen_words() {
        for (why, words) in [
            (
                PythonGone::Reached,
                "Python stopped with this request in hand, so the result is unknown. It may still have done it: check the record before repeating it.",
            ),
            (
                PythonGone::Unreached,
                "Python is not answering behind this front, so this request did not reach it and nothing was done.",
            ),
        ] {
            let answer = text(&python_gone(why));
            assert!(answer.starts_with("HTTP/1.1 503 Service Unavailable\r\n"));
            assert!(
                answer.ends_with(&format!("{{\"error\": \"{words}\"}}")),
                "{answer}"
            );
        }
    }

    #[test]
    fn an_artifact_answer_says_what_send_says_then_its_protections() {
        assert_eq!(
            without_date(&send_artifact(200, "application/json", b"{}", false, false)),
            "HTTP/1.1 200 OK\r\nServer: BaseHTTP/0.6 Python/3.12.10\r\nContent-Type: application/json\r\n\
             Content-Length: 2\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n\
             Content-Security-Policy: sandbox; default-src 'none'; img-src data:; \
             style-src 'unsafe-inline'\r\nCross-Origin-Resource-Policy: same-origin\r\n\
             Referrer-Policy: no-referrer\r\n\r\n{}"
        );
        assert!(send_artifact(404, "application/json", b"{}", false, false).closes);
    }

    #[test]
    fn a_success_stays_open_unless_something_closes_it() {
        assert!(!send_json(200, "{}", false, false).closes);
        assert!(!text(&send_json(200, "{}", false, false)).contains("Connection"));
        let asked = send_json(200, "{}", false, true);
        assert!(asked.closes);
        assert!(!text(&asked).contains("Connection"));
        let unread = send_json(200, "{}", true, false);
        assert!(unread.closes);
        assert!(text(&unread).contains("Connection: close\r\n"));
    }
}
