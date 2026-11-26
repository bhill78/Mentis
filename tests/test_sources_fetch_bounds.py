"""EVERY BOUND ON THE OUTBOUND HTTP PATH, proved (Part W, amendment
adm-c38044ee5157 §2).

OFFLINE. Nothing in this file reaches the network. Two things make that true
rather than hoped for:

  * the refusals are refused BEFORE a socket exists -- `https` only, a
    credential in the address, a non-public address -- so the real code path
    runs and stops without connecting;
  * where a bound is downstream of the exchange (the byte cap, the redirect
    cap, re-checking a redirect's address), `fetch._exchange` is replaced
    with a canned answer. That is the one function in the module that calls
    urllib, so replacing it leaves every rule in `fetch.get` under test and
    nothing else.

The live check that a real feed actually serves this machine is in
`tests/test_sources_feeds.py::test_live_*`, marked `live` and skipped by
default, so this suite never depends on a server's mood.
"""
import urllib.request

import pytest

from mentis.sources import Refused, fetch

#: A public IP LITERAL, so the address check does no DNS lookup and the test
#: is genuinely offline. example.com's documented address; `_exchange` is
#: replaced in every test that uses it, so nothing ever connects to it.
PUBLIC = "93.184.216.34"
OK = f"https://{PUBLIC}/feed.xml"


class _Answer:
    """What `_exchange` hands back: a status, headers, and bytes."""

    def __init__(self, status=200, headers=None, body=b"", size=None):
        self.status = self.code = status
        self.headers = _Headers(headers or {})
        self._body = body
        self._size = size

    def read(self, n=None):
        return self._body[:n] if n is not None else self._body

    def close(self):
        pass


class _Headers(dict):
    def get(self, key, default=None):
        for k, v in self.items():
            if k.lower() == str(key).lower():
                return v
        return default


def _answers(monkeypatch, *answers):
    """Replace the one urllib call with a canned sequence, and record every
    address it was asked for."""
    asked = []
    seq = list(answers)

    def exchange(req, *, timeout):
        asked.append(req.full_url)
        assert req.get_method() == "GET"
        return seq.pop(0) if len(seq) > 1 else seq[0]

    monkeypatch.setattr(fetch, "_exchange", exchange)
    return asked


# -- https only ----------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://example.com/feed.xml",
    "file:///C:/Windows/win.ini",
    "ftp://example.com/x",
    "data:text/plain,hello",
    "gopher://example.com/",
    "ext::cat",
    "//example.com/feed.xml",
])
def test_https_only(url):
    """Only https. No http, file, ftp, data, or anything else."""
    with pytest.raises(Refused) as exc:
        fetch.get(url)
    assert "https" in str(exc.value)


def test_schemes_is_https_alone():
    assert fetch.SCHEMES == ("https",)


def test_the_opener_can_open_nothing_but_https():
    """The second, independent reason `https` only holds: the opener has no
    handler for any other scheme, no proxy handler that could redirect one,
    and no cookie or authentication handler at all."""
    opener = fetch._opener()
    assert set(opener.handle_open) == {"https"}
    kinds = {type(h).__name__ for h in opener.handlers}
    for forbidden in ("ProxyHandler", "HTTPHandler", "FileHandler",
                      "FTPHandler", "DataHandler", "HTTPCookieProcessor",
                      "HTTPBasicAuthHandler", "HTTPDigestAuthHandler",
                      "UnknownHandler"):
        assert forbidden not in kinds
    assert opener.addheaders == []


# -- GET only, and no credential -----------------------------------------------

def test_get_only(monkeypatch):
    asked = _answers(monkeypatch, _Answer(body=b"<rss/>"))
    fetch.get(OK)
    assert asked == [OK]                      # and the stub asserts the verb


def test_no_credential_in_an_address_ever():
    for url in (f"https://token@{PUBLIC}/x", f"https://u:p@{PUBLIC}/x",
                f"https://{PUBLIC}@evil.example/x"):
        with pytest.raises(Refused) as exc:
            fetch.get(url)
        assert "credential" in str(exc.value) or "user name" in str(exc.value)


@pytest.mark.parametrize("field", ["key", "apikey", "api_key", "api-key",
                                   "token", "access_token", "auth",
                                   "password", "secret", "signature", "sig",
                                   "session"])
def test_a_declared_address_that_looks_like_it_carries_a_credential(field):
    """A feed or search address cannot refuse a query string -- `?q=` IS the
    query -- so a DECLARED one is refused when a field is named like a
    secret, rather than recorded carrying it."""
    with pytest.raises(Refused) as exc:
        fetch.declared_url(f"https://example.com/feed?{field}=abc123")
    assert "credential" in str(exc.value)
    assert "abc123" not in str(exc.value)


def test_an_ordinary_query_is_not_mistaken_for_a_credential():
    for ok in ("https://example.com/s?q=pears",
               "https://news.google.com/rss/search?q=x&hl=en-US&gl=US"
               "&ceid=US:en",
               "https://example.com/feed?format=rss&page=2"):
        assert fetch.declared_url(ok) == fetch.canonical_url(ok)


def test_a_redirect_is_not_checked_for_credential_shaped_fields(monkeypatch):
    """A signed CDN address a site redirects to is the site's, not ours;
    refusing it would break ordinary pages, and it is never what a scope
    declares."""
    asked = _answers(
        monkeypatch,
        _Answer(status=302,
                headers={"Location": f"https://{PUBLIC}/p?Signature=abc"}),
        _Answer(body=b"<html>ok</html>"))
    got = fetch.get(OK)
    assert got.final_url == f"https://{PUBLIC}/p?Signature=abc"
    assert len(asked) == 2


def test_no_cookie_or_authentication_header_is_sent():
    sent = {k.lower() for k in fetch._headers(None)}
    assert not sent & set(fetch.FORBIDDEN_HEADERS)
    assert sent == {"user-agent", "accept", "accept-encoding", "connection"}


def test_user_agent_identifies_mentis_honestly():
    assert fetch.USER_AGENT.startswith("Mentis/")
    assert "Mentis" in fetch.USER_AGENT and "+https://" in fetch.USER_AGENT


# -- the SSRF guard ------------------------------------------------------------

@pytest.mark.parametrize("address,why", [
    ("127.0.0.1", "loopback"),
    ("127.3.2.1", "loopback"),
    ("::1", "loopback"),
    ("0.0.0.0", "unspecified"),
    ("::", "unspecified"),
    ("10.0.0.5", "private"),
    ("172.16.4.4", "private"),
    ("192.168.1.1", "private"),
    ("169.254.169.254", "link-local"),
    ("fe80::1", "link-local"),
    ("224.0.0.1", "multicast"),
    ("ff02::1", "multicast"),
    ("fd00::1", "unique-local"),
    ("fc00::abcd", "unique-local"),
    ("100.64.0.1", "carrier-grade NAT"),
    ("240.0.0.1", "reserved"),
    ("::ffff:127.0.0.1", "loopback"),
    ("::ffff:10.0.0.1", "private"),
])
def test_every_named_range_is_refused(address, why):
    assert fetch.address_refusal(address) == why


@pytest.mark.parametrize("address", ["93.184.216.34", "1.1.1.1",
                                     "2606:4700:4700::1111"])
def test_a_public_address_is_allowed(address):
    assert fetch.address_refusal(address) is None


def test_a_loopback_address_is_refused_before_any_socket(monkeypatch):
    """The named bound: a loopback address is refused, and the refusal
    happens before anything is opened -- `_exchange` is made to fail loudly
    if it is ever reached."""
    def never(req, *, timeout):
        raise AssertionError("a socket was opened for a loopback address")
    monkeypatch.setattr(fetch, "_exchange", never)
    for url in ("https://127.0.0.1/x", "https://[::1]/x",
                "https://10.1.2.3/secrets", "https://169.254.169.254/latest"):
        with pytest.raises(Refused) as exc:
            fetch.get(url)
        assert "public" in str(exc.value)


def test_a_name_that_resolves_privately_is_refused(monkeypatch):
    """The check is on the ADDRESS, not the hostname: a perfectly ordinary
    name that resolves to 127.0.0.1 is refused."""
    monkeypatch.setattr(fetch.socket, "getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("127.0.0.1", 443))])
    monkeypatch.setattr(fetch, "_exchange", lambda *a, **k: (_ for _ in ()
                                                             ).throw(
        AssertionError("connected")))
    with pytest.raises(Refused) as exc:
        fetch.get("https://nice-name.example/feed.xml")
    assert "127.0.0.1" in str(exc.value)


def test_one_private_answer_refuses_the_whole_address(monkeypatch):
    """A host answering with a public AND a private address is refused, not
    partly used."""
    monkeypatch.setattr(fetch.socket, "getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("93.184.216.34", 443)),
        (2, 1, 6, "", ("192.168.0.9", 443))])
    with pytest.raises(Refused):
        fetch.get("https://split.example/feed.xml")


def test_the_peer_address_is_checked_on_the_connection_itself(monkeypatch):
    """The second check, on the socket's own peer name, so a name that
    resolves to a public address when it is checked and a private one when
    it is connected (DNS rebinding) is refused with the request unsent."""
    closed = []

    class _Sock:
        def getpeername(self):
            return ("127.0.0.1", 443)

        def settimeout(self, n):
            raise AssertionError("a private peer was made ready to read")

        def close(self):
            closed.append(True)

    def connected(self):
        self.sock = _Sock()

    monkeypatch.setattr(fetch.http.client.HTTPSConnection, "connect",
                        connected)
    conn = fetch._Connection("rebound.example")
    with pytest.raises(Refused) as exc:
        conn.connect()
    assert "loopback" in str(exc.value) and "Nothing was sent" in str(exc.value)
    assert closed


def test_there_is_no_hook_that_admits_a_private_address():
    """`git` has `_TEST_SCHEMES`; this module deliberately has no
    counterpart, because a bypass of the address check is the whole risk.
    Nothing in the module is named as a test seam over the guard."""
    assert not hasattr(fetch, "_TEST_SCHEMES")
    assert not hasattr(fetch, "_TEST_ENV")
    assert not hasattr(fetch, "_ALLOW_PRIVATE")
    assert [n for n in dir(fetch) if "_TEST" in n.upper()] == []


# -- timeouts, byte cap, redirect cap ------------------------------------------

def test_the_timeouts_are_named_and_separate():
    assert fetch.CONNECT_TIMEOUT_S == 10
    assert fetch.READ_TIMEOUT_S == 30
    assert fetch.CONNECT_TIMEOUT_S > 0 and fetch.READ_TIMEOUT_S > 0


def test_the_connect_timeout_is_what_the_exchange_is_given(monkeypatch):
    seen = {}

    def exchange(req, *, timeout):
        seen["timeout"] = timeout
        return _Answer(body=b"x")

    monkeypatch.setattr(fetch, "_exchange", exchange)
    fetch.get(OK)
    assert seen["timeout"] == fetch.CONNECT_TIMEOUT_S


def test_a_declared_length_over_the_cap_is_refused_unread(monkeypatch):
    _answers(monkeypatch, _Answer(
        headers={"Content-Length": str(fetch.MAX_RESPONSE_BYTES + 1)},
        body=b"never read"))
    with pytest.raises(Refused) as exc:
        fetch.get(OK)
    assert str(fetch.MAX_RESPONSE_BYTES) in str(exc.value)


def test_a_body_over_the_cap_is_refused_even_if_the_header_lied(monkeypatch):
    _answers(monkeypatch, _Answer(headers={"Content-Length": "3"},
                                  body=b"x" * (fetch.MAX_RESPONSE_BYTES + 10)))
    with pytest.raises(Refused) as exc:
        fetch.get(OK)
    assert "limit" in str(exc.value)


def test_a_body_exactly_at_the_cap_is_read(monkeypatch):
    _answers(monkeypatch, _Answer(body=b"x" * fetch.MAX_RESPONSE_BYTES))
    got = fetch.get(OK)
    assert len(got.body) == fetch.MAX_RESPONSE_BYTES


def test_a_caller_may_ask_for_a_smaller_cap(monkeypatch):
    _answers(monkeypatch, _Answer(body=b"x" * 100))
    with pytest.raises(Refused):
        fetch.get(OK, max_bytes=10)


def test_the_redirect_cap_holds(monkeypatch):
    hop = _Answer(status=302, headers={"Location": f"https://{PUBLIC}/again"})
    asked = _answers(monkeypatch, hop)
    with pytest.raises(Refused) as exc:
        fetch.get(OK)
    assert f"more than {fetch.MAX_REDIRECTS}" in str(exc.value)
    assert len(asked) == fetch.MAX_REDIRECTS + 1


def test_a_redirect_within_the_cap_is_followed_and_recorded(monkeypatch):
    asked = _answers(
        monkeypatch,
        _Answer(status=301, headers={"Location": "/moved/feed.xml"}),
        _Answer(body=b"<rss/>", headers={"Content-Type": "text/xml"}))
    got = fetch.get(OK)
    assert asked == [OK, f"https://{PUBLIC}/moved/feed.xml"]
    assert got.final_url == f"https://{PUBLIC}/moved/feed.xml"
    assert got.redirects == (OK,)
    assert got.media_type == "text/xml"


@pytest.mark.parametrize("where", [
    "https://127.0.0.1/admin",
    "https://[::1]/admin",
    "https://169.254.169.254/latest/meta-data/",
    "https://10.0.0.1/",
])
def test_a_redirect_to_a_private_address_is_refused(monkeypatch, where):
    """The bound the amendment names in those words: the address check is
    re-applied after EVERY redirect."""
    _answers(monkeypatch, _Answer(status=302, headers={"Location": where}))
    with pytest.raises(Refused) as exc:
        fetch.get(OK)
    assert "public" in str(exc.value)


@pytest.mark.parametrize("where", ["http://example.com/x",
                                   "file:///C:/Windows/win.ini",
                                   f"https://token@{PUBLIC}/x"])
def test_a_redirect_is_re_checked_against_every_rule(monkeypatch, where):
    _answers(monkeypatch, _Answer(status=302, headers={"Location": where}))
    with pytest.raises(Refused):
        fetch.get(OK)


def test_a_redirect_with_no_location_is_reported(monkeypatch):
    _answers(monkeypatch, _Answer(status=302))
    with pytest.raises(fetch.Unreachable) as exc:
        fetch.get(OK)
    assert exc.value.status == 302


# -- absence is reported, never dropped ----------------------------------------

@pytest.mark.parametrize("status", [404, 403, 410, 500, 503])
def test_a_status_that_is_not_200_is_reported_with_its_status(monkeypatch,
                                                              status):
    _answers(monkeypatch, _Answer(status=status, body=b"nope"))
    with pytest.raises(fetch.Unreachable) as exc:
        fetch.get(OK)
    assert exc.value.status == status
    assert str(status) in str(exc.value)


def test_an_unresolvable_name_is_reported(monkeypatch):
    def gai(*a, **k):
        raise fetch.socket.gaierror(11001, "no such host")
    monkeypatch.setattr(fetch.socket, "getaddrinfo", gai)
    with pytest.raises(fetch.Unreachable) as exc:
        fetch.get("https://nothing-here.example/feed.xml")
    assert "resolved" in str(exc.value)


# -- the per-sweep budget ------------------------------------------------------

def test_the_fetch_count_per_sweep_is_capped(monkeypatch):
    _answers(monkeypatch, _Answer(body=b"x"))
    budget = fetch.Budget(max_fetches=2, max_bytes=1 << 20)
    fetch.get(OK, budget=budget)
    fetch.get(OK, budget=budget)
    with pytest.raises(Refused) as exc:
        fetch.get(OK, budget=budget)
    assert "limit of 2" in str(exc.value)


def test_the_byte_total_per_sweep_is_capped(monkeypatch):
    _answers(monkeypatch, _Answer(body=b"x" * 600))
    budget = fetch.Budget(max_fetches=10, max_bytes=1000)
    fetch.get(OK, budget=budget)
    with pytest.raises(Refused) as exc:
        fetch.get(OK, budget=budget)
    assert "1000 bytes" in str(exc.value)


def test_a_redirect_hop_spends_from_the_fetch_budget(monkeypatch):
    _answers(monkeypatch,
             _Answer(status=302, headers={"Location": f"https://{PUBLIC}/b"}),
             _Answer(body=b"ok"))
    budget = fetch.Budget(max_fetches=5, max_bytes=1 << 20)
    fetch.get(OK, budget=budget)
    assert budget.fetches == 2


# -- addresses, normalised and redacted ----------------------------------------

@pytest.mark.parametrize("given,want", [
    ("https://Example.COM/Feed.xml", "https://example.com/Feed.xml"),
    ("https://example.com", "https://example.com/"),
    ("https://example.com:443/x", "https://example.com/x"),
    ("https://example.com:8443/x", "https://example.com:8443/x"),
    ("https://example.com/a/b/../c", "https://example.com/a/c"),
    ("https://example.com/x#part", "https://example.com/x"),
    ("https://example.com/s?q=a+b", "https://example.com/s?q=a+b"),
])
def test_an_address_normalises_to_one_key(given, want):
    assert fetch.canonical_url(given) == want


@pytest.mark.parametrize("bad", ["", "   ", "https://", "https:// space/x",
                                 "https://ex\tample.com/x",
                                 "https://example.com/" + "x" * 3000])
def test_a_malformed_address_is_refused(bad):
    with pytest.raises(Refused):
        fetch.canonical_url(bad)


def test_an_error_keeps_no_credential_or_query():
    said = fetch._redact("https://user:tok@host.example/p?key=secret failed")
    assert "tok" not in said and "secret" not in said
    assert "https://host.example/p?..." in said


def test_canonical_url_resolves_no_name(monkeypatch):
    """A scope can be checked without touching the network."""
    monkeypatch.setattr(fetch.socket, "getaddrinfo", lambda *a, **k: (_ for _
                                                                      in ()
                                                                      ).throw(
        AssertionError("resolved")))
    assert fetch.canonical_url("https://example.com/x") == \
        "https://example.com/x"


# -- robots.txt ----------------------------------------------------------------

def test_robots_is_fetched_through_the_bounded_get(monkeypatch):
    """Not through `RobotFileParser.read`, which would open its own
    unbounded, unchecked connection."""
    asked = _answers(monkeypatch, _Answer(
        body=b"User-agent: *\nDisallow: /private/\n"))
    rules = fetch.robots(f"https://{PUBLIC}/page", cache={})
    assert asked == [f"https://{PUBLIC}/robots.txt"]
    assert rules.may(f"https://{PUBLIC}/page") is None
    assert "robots.txt" in rules.may(f"https://{PUBLIC}/private/x")


def test_robots_404_means_nothing_is_asked(monkeypatch):
    _answers(monkeypatch, _Answer(status=404))
    rules = fetch.robots(f"https://{PUBLIC}/page", cache={})
    assert rules.may(f"https://{PUBLIC}/page") is None


def test_robots_unreadable_means_the_page_is_not_fetched(monkeypatch):
    _answers(monkeypatch, _Answer(status=503))
    rules = fetch.robots(f"https://{PUBLIC}/page", cache={})
    assert "unknown" in rules.may(f"https://{PUBLIC}/page")


def test_robots_is_fetched_once_per_sweep(monkeypatch):
    asked = _answers(monkeypatch, _Answer(body=b"User-agent: *\n"))
    cache = {}
    for _ in range(4):
        fetch.robots(f"https://{PUBLIC}/page", cache=cache)
    assert len(asked) == 1


def test_the_bounds_are_all_named_constants():
    """The reviewer's list, each a name rather than a literal in a call."""
    for name in ("SCHEMES", "USER_AGENT", "CONNECT_TIMEOUT_S",
                 "READ_TIMEOUT_S", "MAX_RESPONSE_BYTES", "MAX_REDIRECTS",
                 "MAX_URL_CHARS", "FORBIDDEN_HEADERS", "ROBOTS_MAX_BYTES"):
        assert getattr(fetch, name), name
