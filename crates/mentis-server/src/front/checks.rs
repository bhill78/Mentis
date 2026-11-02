//! The Host and client-header checks, for what the front answers itself. A forwarded request
//! keeps Python's own: it goes on byte for byte and they still run (`contracts/route-table.md`).

use std::collections::HashSet;
use std::net::{Ipv4Addr, Ipv6Addr};

use super::head::python_space;

/// `CLIENT_HEADER`.
pub const CLIENT_HEADER: &str = "X-Mentis-Client";
/// `mentis.worker.CAPABILITY_HEADER`.
pub const GRANT_HEADER: &str = "X-Mentis-Worker";
/// `CLIENT_EXEMPT_GET`: the identity probe.
const CLIENT_EXEMPT_GET: &[&str] = &["/api/server"];

/// `MENTIS_ALLOWED_HOSTS`, as `_host_allowed` reads it. Read once: nothing changes a running
/// process's environment.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct AllowedHosts(HashSet<String>);

impl AllowedHosts {
    pub fn from_env() -> Self {
        Self::parse(&std::env::var("MENTIS_ALLOWED_HOSTS").unwrap_or_default())
    }

    pub fn parse(listed: &str) -> Self {
        Self(
            listed
                .split(',')
                .map(|host| stripped(host).to_lowercase())
                .filter(|host| !host.is_empty())
                .collect(),
        )
    }
}

fn stripped(text: &str) -> &str {
    text.trim_matches(|c: char| u8::try_from(u32::from(c)).is_ok_and(python_space))
}

/// `_host_allowed` (`web/__init__.py:1028`).
pub fn host_allowed(host: Option<&str>, extra: &AllowedHosts) -> bool {
    let Some(host) = host.filter(|host| !host.is_empty()) else {
        return false;
    };
    let value = stripped(host).to_lowercase();

    if let Some(rest) = value.strip_prefix('[') {
        let Some((inside, after)) = rest.split_once(']') else {
            return false;
        };
        let inside_fits = !inside.is_empty()
            && inside.bytes().all(|b| {
                b.is_ascii_digit() || (b'a'..=b'f').contains(&b) || b == b':' || b == b'.'
            });
        return inside_fits && port_fits(after, true) && inside.parse::<Ipv6Addr>().is_ok();
    }

    let (with_dot, port) = match value.split_once(':') {
        Some((name, port)) => (name, Some(port)),
        None => (value.as_str(), None),
    };
    if port.is_some_and(|port| !port_fits(port, false)) {
        return false;
    }
    if with_dot.is_empty()
        || !with_dot
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'.' || b == b'-')
    {
        return false;
    }
    // `([a-z0-9.-]+?)\.?`: one trailing dot is not part of the name, if anything is left.
    let name = match with_dot.strip_suffix('.') {
        Some(short) if !short.is_empty() => short,
        _ => with_dot,
    };
    let labels: Vec<&str> = name.split('.').collect();
    if labels
        .iter()
        .any(|label| label.is_empty() || label.starts_with('-') || label.ends_with('-'))
    {
        return false;
    }
    if name.parse::<Ipv4Addr>().is_ok() {
        return true;
    }
    extra.0.contains(name)
        || labels.len() == 1
        || name.ends_with(".localhost")
        || name.ends_with(".ts.net")
}

/// `(?::\d{1,5})?`. `after_bracket` is what follows a `]`, colon and all; otherwise `port` is what
/// followed the colon.
fn port_fits(port: &str, after_bracket: bool) -> bool {
    let digits = if after_bracket {
        if port.is_empty() {
            return true;
        }
        match port.strip_prefix(':') {
            Some(digits) => digits,
            None => return false,
        }
    } else {
        port
    };
    (1..=5).contains(&digits.len()) && digits.bytes().all(|b| b.is_ascii_digit())
}

/// `_missing_client`: true when it has to refuse. A request presenting a grant is left to the
/// grant's own refusal, and an empty grant isn't presenting one.
pub fn client_missing(method: &str, path: &str, client: Option<&str>, grant: Option<&str>) -> bool {
    if grant.is_some_and(|grant| !grant.is_empty()) {
        return false;
    }
    if method == "GET" && CLIENT_EXEMPT_GET.contains(&path) {
        return false;
    }
    client != Some("1")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn allowed(host: &str) -> bool {
        host_allowed(
            Some(host),
            &AllowedHosts::parse(" Listed.Example ,, other.test"),
        )
    }

    #[test]
    fn hosts_python_allows() {
        for host in [
            "127.0.0.1",
            "127.0.0.1:8760",
            "localhost",
            "LOCALHOST:1",
            "x.localhost",
            "machine",
            "x.ts.net",
            "x.ts.net.",
            "listed.example",
            "listed.example:99",
            "[::1]",
            "[::1]:8760",
            "[2001:db8::1]:1",
            " localhost ",
        ] {
            assert!(allowed(host), "{host}");
        }
    }

    #[test]
    fn hosts_python_refuses() {
        for host in [
            "",
            "evil.example",
            "a.ts.net.evil.example",
            "localhost:1:2",
            "localhost:",
            "localhost:123456",
            "localhost:a",
            "[::1",
            "[::1]x",
            "[::1]:",
            "[::g]",
            "[1.2.3.4]",
            ".",
            "..",
            "a..b.localhost",
            "-a.localhost",
            "a-.localhost",
            "256.1.1.1.example",
            "under_score",
            "caf\u{e9}",
        ] {
            assert!(!allowed(host), "{host}");
        }
        assert!(!host_allowed(None, &AllowedHosts::default()));
    }

    #[test]
    fn client_header_rules() {
        assert!(client_missing("GET", "/api/pulse", None, None));
        assert!(client_missing("GET", "/api/pulse", Some("2"), None));
        assert!(!client_missing("GET", "/api/pulse", Some("1"), None));
        assert!(!client_missing("GET", "/api/server", None, None));
        assert!(client_missing("POST", "/api/server", None, None));
        assert!(!client_missing("GET", "/api/pulse", None, Some("g")));
        assert!(client_missing("GET", "/api/pulse", None, Some("")));
    }
}
