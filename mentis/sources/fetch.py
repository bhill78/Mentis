"""The one bounded HTTPS GET every web connector goes through.

WHAT THIS IS. Part W (amendment adm-c38044ee5157 §2) added the first
outbound network path in acquisition that is not Git's. It is deliberately
ONE function -- `get` -- in ONE module, so that every bound the owner asked
for is written once, named once, and tested once, and so a reviewer has a
single place to read. `mentis.sources.feeds` and `mentis.sources.webpages`
fetch nothing themselves; they call this.

MODELLED ON `mentis.sources.git`'s remote half, which is the existing
connector with a network path: a fixed scheme list (`git.SCHEMES`),
timeouts as named constants, an address that may carry no credential, and
errors that are redacted before they are shown.

WHAT IS BOUNDED, AND WHERE (every one of these is a named constant with a
test in `tests/test_sources_fetch_bounds.py`):

  SCHEMES              `https` only. No `http`, `file`, `ftp`, `data`, no
                       remote-helper anything. Two independent reasons it
                       holds: `canonical_url` refuses the scheme, and the
                       opener below HAS NO HANDLER for any other scheme, so
                       even a bug that skipped the check could not open one.
  public addresses     the SSRF guard. Every address the host resolves to is
                       checked BEFORE a socket is opened, and the address
                       ACTUALLY CONNECTED TO is checked again from the
                       socket's own peer name before a single byte is
                       written -- so a name that resolves differently the
                       second time (DNS rebinding) is refused with the
                       connection unused. Loopback, private, link-local,
                       multicast, reserved, unique-local, CGNAT and
                       unspecified are all refused, and the refusal says
                       which. There is NO test hook that admits a private
                       address: `git._TEST_SCHEMES` has no counterpart here
                       on purpose, because a bypass of this check is the
                       whole risk.
  GET only             `method="GET"`, always. No cookie processor, no
                       authentication handler, no credential of any kind:
                       an address carrying a user name or token is refused
                       rather than stripped, and `FORBIDDEN_HEADERS` names
                       what is never sent. There is nothing here for a
                       credential to come from, and nothing that could
                       learn one.
  NO PROXY             the opener has no `ProxyHandler`, so this machine's
                       proxy environment cannot redirect a checked address
                       to an unchecked one. The address checked is the
                       address connected to.
  CONNECT_TIMEOUT_S    how long opening and the TLS handshake may take.
  READ_TIMEOUT_S       how long any single read may block, set on the
                       socket once it is connected.
  MAX_RESPONSE_BYTES   the response cap, applied to the declared
                       `Content-Length` first and then to the bytes
                       actually read (cap + 1 is read, and one byte over is
                       a refusal, so a lying header changes nothing).
  MAX_REDIRECTS        the redirect cap. Redirects are NOT followed by
                       urllib -- `_NoRedirect` switches that off -- but by
                       the loop in `get`, which puts every hop through
                       `canonical_url` and the address check again. Every
                       rule above therefore holds for hop 3 exactly as for
                       hop 0.
  Budget               per-sweep caps a connector passes in: how many
                       fetches and how many bytes one sweep may spend in
                       total. The connectors' own per-collection caps
                       (feeds, queries, pages, entries) are theirs.

WHAT THIS NEVER DOES. No JavaScript is executed; nothing a document
references is fetched (no images, stylesheets, scripts or iframes); no URL
is guessed or inferred. One address in, one response out.

ABSENCE IS REPORTED. A failure raises `Unreachable`, which carries the HTTP
status when there was one, so a connector can record "this feed failed" or
"this page is gone (404)" as what it is -- `mentis.sources.git:52-61`'s rule,
kept. Nothing here ever silently returns nothing.

WHAT ELSE IS HERE. Two things both web connectors need and neither should
own, so that `feeds` and `webpages` share them instead of importing each
other: what a fetched HTML document reduces to (`text_of_html`,
`links_in_html` -- text and the links the document itself states, nothing
executed and nothing fetched), and what stands in for a machine-local
binding when a collection is a public address (`Network`, `NET_BINDING`).
"""

from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser

from mentis.sources import Refused

__all__ = ["get", "Budget", "Response", "Unreachable", "canonical_url",
           "address_refusal", "public_addresses_of", "robots", "Robots",
           "text_of_html", "links_in_html", "Network", "NET_BINDING"]

#: THE ONLY TRANSPORT. `http` sends everything in the clear and is trivially
#: redirected; `file` and `ftp` reach this machine and its network.
SCHEMES = ("https",)

#: A User-Agent that says honestly what this is and where to complain.
USER_AGENT = ("Mentis/1.0 (+https://github.com/bhill78/Mentis; personal "
              "knowledge collection; one GET per source, no JavaScript)")

#: HOW LONG. Opening and the handshake; then any one read.
CONNECT_TIMEOUT_S = 10
READ_TIMEOUT_S = 30

#: HOW MUCH of one response is read, and how many hops are followed.
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3

#: An address longer than this is refused unread.
MAX_URL_CHARS = 2048

#: Headers that are never sent, whatever asks. Checked by a test.
FORBIDDEN_HEADERS = ("cookie", "authorization", "proxy-authorization",
                     "www-authenticate", "set-cookie")

#: The statuses `get` treats as a hop, each re-checked from the top.
REDIRECT_STATUS = (301, 302, 303, 307, 308)

#: robots.txt: how much of one is read, and how long one is believed within
#: a single sweep.
ROBOTS_MAX_BYTES = 64 * 1024


class Unreachable(Refused):
    """The address did not answer, or answered with something that is not a
    document: a network failure, a timeout, a TLS failure, or an HTTP status
    that is not 200. `status` is the HTTP status when there was one.

    It is a `Refused`, so every caller already reports it rather than
    dropping it; what it is NOT is an inference that anything is absent."""

    def __init__(self, message, *, status: int | None = None):
        super().__init__(message)
        self.status = status


# -- what an address may be ----------------------------------------------------

_HOST = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
                   r"|\[[0-9A-Fa-f:.]+\])$")

#: Unique-local IPv6 (fc00::/7) by name, so the refusal says which range it
#: was rather than the generic "private".
_UNIQUE_LOCAL = ipaddress.ip_network("fc00::/7")
#: Carrier-grade NAT (RFC 6598): not the public internet either.
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _redact(text: str) -> str:
    """An address as it is safe to put in an error.

    Two things come out: anything before an `@` in an address (a user name or
    token looks exactly like a name, as `git.canonical_remote` says), and the
    query string (a key is sometimes passed there). Taking a little too much
    out of an error is harmless; leaving a credential in is not. The query a
    `web-search` collection asked is recorded in the act, so nothing is lost
    by not repeating it here."""
    text = re.sub(r"([A-Za-z][A-Za-z0-9+.-]*://)[^\s@'\"]*@", r"\1", text)
    return re.sub(r"(https?://[^\s'\"]*)\?[^\s'\"]*", r"\1?...", text)


def _no_dots(path: str) -> str:
    """`/a/b/../c` as `/a/c`, so one page has one key."""
    out: list[str] = []
    for seg in path.split("/"):
        if seg == ".":
            continue
        if seg == "..":
            if out and out[-1] not in ("", ".."):
                out.pop()
            continue
        out.append(seg)
    done = "/".join(out)
    return done if done.startswith("/") else "/" + done


def canonical_url(url, *, what: str = "address") -> str:
    """The address this will fetch, normalised -- or a refusal that says why.

    PURE: no name is resolved and no socket is opened here, so a scope can be
    checked without touching the network. Scheme and host lowercased, the
    default port dropped, dot segments removed, the fragment dropped (it is
    never sent), the query kept exactly as given. REFUSED: any scheme but
    https, any credential in the address, a malformed host or port, control
    characters, whitespace, and anything over `MAX_URL_CHARS`."""
    if not isinstance(url, str) or not url.strip():
        raise Refused(f"an {what} is needed")
    url = url.strip()
    if len(url) > MAX_URL_CHARS:
        raise Refused(f"an {what} is at most {MAX_URL_CHARS} characters")
    if any(c.isspace() or ord(c) < 0x20 or ord(c) == 0x7f for c in url):
        raise Refused(f"an {what} has no spaces or control characters")
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError as exc:
        raise Refused(f"that is not an {what} ({exc})") from None
    scheme = (parts.scheme or "").lower()
    if scheme not in SCHEMES:
        raise Refused(
            f"`{scheme or url[:40]}` is not fetched: only https:// addresses "
            "are read, never http, file, ftp or anything else")
    if "@" in (parts.netloc or ""):
        raise Refused(
            "the address carries a user name or token. Nothing that could be "
            "a credential is accepted in an address, and none is ever sent: "
            "give the address without one")
    try:
        host, port = parts.hostname, parts.port
    except ValueError:
        raise Refused("that address has no usable port") from None
    if not host or not _HOST.match(f"[{host}]" if ":" in host else host):
        raise Refused(f"{(host or '')[:60]!r} is not a host name")
    if port is not None and not 0 < port < 65536:
        raise Refused(f"{port} is not a port")
    netloc = f"[{host}]" if ":" in host else host
    if port is not None and port != 443:
        netloc = f"{netloc}:{port}"
    return urllib.parse.urlunsplit(
        (scheme, netloc, _no_dots(parts.path or "/"), parts.query, ""))


#: QUERY FIELDS THAT LOOK LIKE A CREDENTIAL. `git.canonical_remote` refuses a
#: query string outright for this reason; a feed or search address cannot --
#: `?q=` IS the query -- so a DECLARED address is refused when one of its
#: fields is named like a secret instead. Nothing here can use a credential,
#: and an address shaped like it carries one would be written into the record
#: by the declaration. Redirects are not checked against this: a signed CDN
#: address a site redirects to is the site's, not ours, and refusing it would
#: break ordinary pages.
CREDENTIAL_FIELDS = ("key", "apikey", "api_key", "token", "access_token",
                     "refresh_token", "auth", "authorization", "password",
                     "passwd", "pwd", "secret", "client_secret", "signature",
                     "sig", "session", "sessionid", "credential", "bearer")


def declared_url(url, *, what: str = "address") -> str:
    """`canonical_url` for an address a SCOPE declares -- so it is also
    refused when it looks like it carries a credential."""
    one = canonical_url(url, what=what)
    query = urllib.parse.urlsplit(one).query
    for name, _ in urllib.parse.parse_qsl(query, keep_blank_values=True):
        if name.strip().lower().replace("-", "_") in CREDENTIAL_FIELDS:
            raise Refused(
                f"that {what} has a `{name}` field, which is how a "
                "credential is usually passed. Nothing here can use one and "
                "nothing may be recorded carrying one: give an address that "
                "needs no credential.")
    return one


def address_refusal(address: str) -> str | None:
    """Which non-public range an IP address is in, or None if it is public.

    THE SSRF GUARD'S ONE JUDGEMENT. The specific ranges the amendment names
    are tested first so the refusal can say which one it was; `is_global` is
    the backstop, so a range nobody listed is refused too rather than
    admitted by omission. An IPv4-mapped or 6to4 IPv6 address is unwrapped
    first, because `::ffff:127.0.0.1` is loopback however it is spelled."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return "not an IP address"
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.sixtofour is not None:
            ip = ip.sixtofour
        elif ip.teredo is not None:
            ip = ip.teredo[1]
    if ip.is_unspecified:
        return "unspecified"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link-local"
    if ip.is_multicast:
        return "multicast"
    if ip.version == 6 and ip in _UNIQUE_LOCAL:
        return "unique-local"
    if ip.version == 4 and ip in _CGNAT:
        return "carrier-grade NAT"
    if ip.is_reserved:
        return "reserved"
    if ip.is_private:
        return "private"
    if not ip.is_global:
        return "not a public"
    return None


def public_addresses_of(url: str) -> list[str]:
    """Every address the URL's host resolves to, each checked public.

    ONE NON-PUBLIC ANSWER REFUSES THE WHOLE ADDRESS. A host that answers with
    both a public and a private address is exactly the shape of an attack, and
    choosing the public one would be this module deciding which answer it
    liked."""
    parts = urllib.parse.urlsplit(url)
    host, port = parts.hostname or "", parts.port or 443
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise Unreachable(f"{host} could not be resolved from this machine "
                          f"({exc.strerror or exc})") from None
    except (OSError, UnicodeError) as exc:
        raise Unreachable(f"{host} could not be resolved from this machine "
                          f"({type(exc).__name__})") from None
    addresses = [i[4][0] for i in infos]
    if not addresses:
        raise Unreachable(f"{host} resolves to no address from this machine")
    for address in addresses:
        why = address_refusal(address)
        if why is not None:
            raise Refused(
                f"{host} resolves to {address}, which is not a public "
                f"address ({why}). Only public addresses are fetched: "
                "nothing inside this machine or this network is reached from "
                "a collection. Nothing was requested.")
    return addresses


# -- the connection: the peer is checked, and only then written to --------------

_CONTEXT: ssl.SSLContext | None = None


def _context() -> ssl.SSLContext:
    """One verifying TLS context, made once: building it reads this
    machine's certificate store, and a sweep of forty pages should not do
    that forty times. Certificates are required and the host name is
    checked; neither is ever switched off, here or anywhere."""
    global _CONTEXT
    if _CONTEXT is None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        _CONTEXT = ctx
    return _CONTEXT


class _Connection(http.client.HTTPSConnection):
    """An HTTPS connection that re-checks the address it actually reached.

    `public_addresses_of` has already refused a host whose names resolve
    anywhere private. This is the second check, and the one the amendment
    asks for in those words: it reads the peer address off the connected
    socket, so a name that resolved to a public address when it was checked
    and to a private one when it was connected is refused HERE, with the
    request still unsent and nothing read. It also puts the read timeout on
    the socket, so connecting and reading are bounded separately."""

    def connect(self):
        super().connect()
        try:
            peer = self.sock.getpeername()[0]
        except OSError as exc:                             # pragma: no cover
            self.close()
            raise Unreachable("the connection gave no peer address "
                              f"({type(exc).__name__})") from None
        why = address_refusal(peer)
        if why is not None:
            self.close()
            raise Refused(
                f"{self.host} connected to {peer}, which is not a public "
                f"address ({why}) -- it resolved to a public one when it was "
                "checked. Nothing was sent and nothing was read.")
        self.sock.settimeout(READ_TIMEOUT_S)


class _Https(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_Connection, req, context=self._context)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib follows redirects without re-checking anything; `get` follows
    them itself instead, so each hop goes through every rule again."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener() -> urllib.request.OpenerDirector:
    """An opener built by hand rather than by `build_opener`.

    WHAT IS NOT IN IT is the point: no `HTTPHandler` (so `http://` cannot be
    opened at all), no `FileHandler`, `FTPHandler` or `DataHandler`, no
    `ProxyHandler` (so the environment cannot redirect a checked address), no
    `HTTPCookieProcessor`, and none of the authentication handlers. It can
    open exactly one kind of address."""
    opener = urllib.request.OpenerDirector()
    opener.add_handler(_Https(context=_context()))
    opener.add_handler(_NoRedirect())
    opener.add_handler(urllib.request.HTTPErrorProcessor())
    opener.add_handler(urllib.request.HTTPDefaultErrorHandler())
    opener.addheaders = []
    return opener


def _headers(accept: str | None) -> dict:
    sent = {"User-Agent": USER_AGENT, "Accept": accept or "*/*",
            # identity, so the byte cap is on the bytes that arrive.
            "Accept-Encoding": "identity", "Connection": "close"}
    assert not {k.lower() for k in sent} & set(FORBIDDEN_HEADERS)
    return sent


def _exchange(req: urllib.request.Request, *, timeout: int):
    """THE ONLY PLACE urllib IS CALLED. One request, one response object --
    an error status comes back as a response too (`HTTPError` carries the
    status, the headers and the body), so `get` handles every status in one
    place. A test replaces this to exercise `get`'s own bounds offline."""
    try:
        return _opener().open(req, timeout=timeout)
    except urllib.error.HTTPError as err:
        return err
    except urllib.error.URLError as exc:
        raise Unreachable(_redact(f"{req.full_url} could not be reached from "
                                  f"this machine ({exc.reason})")) from None
    except ssl.SSLError as exc:
        raise Unreachable(_redact(f"{req.full_url} could not be reached "
                                  f"securely ({exc})")) from None
    except (TimeoutError, socket.timeout):
        raise Unreachable(_redact(
            f"{req.full_url} did not answer within {CONNECT_TIMEOUT_S} "
            "seconds")) from None
    except OSError as exc:
        raise Unreachable(_redact(f"{req.full_url} could not be reached from "
                                  f"this machine ({type(exc).__name__}: "
                                  f"{exc})")) from None


@dataclass(frozen=True)
class Response:
    """One answered GET. `body` is already within the byte cap."""
    url: str
    final_url: str
    status: int
    media_type: str
    charset: str | None
    body: bytes
    redirects: tuple = ()

    def text(self) -> str:
        return self.body.decode(self.charset or "utf-8", "replace")


class Budget:
    """What one sweep may spend in total: how many fetches, how many bytes.

    A connector makes one and passes it to every `get` of that sweep, so the
    per-sweep caps the amendment asks for are enforced in the one place the
    bytes actually arrive. Over the cap is a refusal naming the cap, never a
    quiet stop."""

    def __init__(self, *, max_fetches: int, max_bytes: int):
        self.max_fetches = int(max_fetches)
        self.max_bytes = int(max_bytes)
        self.fetches = 0
        self.bytes = 0

    def fetch(self, address: str) -> None:
        if self.fetches >= self.max_fetches:
            raise Refused(f"this sweep has already fetched {self.fetches} "
                          f"addresses, which is its limit of "
                          f"{self.max_fetches}; narrow the collection's scope")
        self.fetches += 1

    def spend(self, size: int) -> None:
        self.bytes += int(size)
        if self.bytes > self.max_bytes:
            raise Refused(f"this sweep has read {self.bytes} bytes, over its "
                          f"limit of {self.max_bytes} bytes; narrow the "
                          "collection's scope")

    def left(self) -> dict:
        return {"fetches": self.fetches, "max_fetches": self.max_fetches,
                "bytes": self.bytes, "max_bytes": self.max_bytes}


def _media(headers) -> tuple[str, str | None]:
    raw = (headers.get("Content-Type") or "").strip()
    kind = raw.split(";", 1)[0].strip().lower()
    charset = None
    for bit in raw.split(";")[1:]:
        name, _, value = bit.strip().partition("=")
        if name.strip().lower() == "charset":
            charset = value.strip().strip('"').lower() or None
    return kind, charset


def get(url, *, accept: str | None = None, budget: Budget | None = None,
        max_bytes: int | None = None) -> Response:
    """One bounded HTTPS GET. Every rule in the module docstring, applied.

    Raises `Refused` for anything this will not do, and `Unreachable` (a
    `Refused` carrying `status`) for an address that did not answer or
    answered with something other than 200. Never returns None, and never
    returns a partial body."""
    cap = MAX_RESPONSE_BYTES if max_bytes is None else int(max_bytes)
    asked = canonical_url(url)
    target, hops = asked, []
    for hop in range(MAX_REDIRECTS + 1):
        # BEFORE ANY SOCKET: the host's addresses must all be public. On a
        # redirect this runs again for the new host, which is the point.
        public_addresses_of(target)
        if budget is not None:
            budget.fetch(target)
        resp = _exchange(urllib.request.Request(
            target, method="GET", headers=_headers(accept)),
            timeout=CONNECT_TIMEOUT_S)
        status = int(getattr(resp, "status", None)
                     or getattr(resp, "code", 0) or 0)
        try:
            if status in REDIRECT_STATUS:
                where = (resp.headers.get("Location") or "").strip()
                if not where:
                    raise Unreachable(
                        _redact(f"{target} answered {status} with no "
                                "Location to follow"), status=status)
                if hop >= MAX_REDIRECTS:
                    raise Refused(_redact(
                        f"{asked} redirects more than {MAX_REDIRECTS} times "
                        f"({' -> '.join(hops + [target])}); nothing was "
                        "read"))
                # EVERY RULE AGAIN, for this hop: https only, no credential,
                # a public address. A relative Location is joined onto the
                # address that gave it, so a path cannot change the scheme.
                hops.append(target)
                target = canonical_url(urllib.parse.urljoin(target, where))
                continue
            if status != 200:
                raise Unreachable(
                    _redact(f"{target} answered HTTP {status}"), status=status)
            declared = (resp.headers.get("Content-Length") or "").strip()
            if declared.isdigit() and int(declared) > cap:
                raise Refused(_redact(
                    f"{target} says it is {declared} bytes, over the "
                    f"{cap}-byte limit for one response; nothing was read"))
            # cap + 1: one byte over the cap is a refusal, so a response that
            # understated its length in the header gains nothing by it.
            body = resp.read(cap + 1)
            if len(body) > cap:
                raise Refused(_redact(
                    f"{target} is over the {cap}-byte limit for one "
                    "response; it was not read"))
        finally:
            try:
                resp.close()
            except Exception:                              # pragma: no cover
                pass
        if budget is not None:
            budget.spend(len(body))
        kind, charset = _media(resp.headers)
        return Response(url=asked, final_url=target, status=status,
                        media_type=kind, charset=charset, body=body,
                        redirects=tuple(hops))
    raise Refused(f"{asked} redirects more than {MAX_REDIRECTS} times"
                  )                                        # pragma: no cover


# -- robots.txt ----------------------------------------------------------------

@dataclass
class Robots:
    """What one host's robots.txt says, fetched once per sweep.

    FETCHED THROUGH `get` LIKE EVERYTHING ELSE -- not through
    `urllib.robotparser.RobotFileParser.read`, which opens its own
    unbounded, unchecked connection. Only the parser is borrowed, and it
    touches no network.

    WHEN IT CANNOT BE READ. A 404 or any other 4xx means no rules, so
    fetching is allowed (what every crawler and the standard do). Anything
    else -- unreachable, a timeout, a 5xx, a robots.txt over
    `ROBOTS_MAX_BYTES` -- means the host's wishes are unknown, and this
    refuses the page rather than guessing. The reason is kept, so a page
    withheld for this says so."""
    host: str
    allowed: object = None
    why: str | None = None

    def may(self, url: str) -> str | None:
        """None if the page may be fetched, else why it may not."""
        if self.why is not None:
            return self.why
        if self.allowed is None:
            return None
        if self.allowed.can_fetch(USER_AGENT, url):
            return None
        return (f"refused by robots.txt at {self.host}: that host asks "
                "automated readers not to fetch this address")


def robots(url: str, *, budget: Budget | None = None,
           cache: dict | None = None) -> Robots:
    """This host's robots.txt, from `cache` if this sweep already has it.

    THE CACHE IS THE CALLER'S, AND LIVES FOR ONE SWEEP. There is deliberately
    no module-level cache: a robots.txt remembered across sweeps would be a
    host's wishes from an unknown time ago, believed forever. Called with
    none, nothing is remembered and the file is fetched."""
    from urllib.robotparser import RobotFileParser
    parts = urllib.parse.urlsplit(canonical_url(url))
    host = parts.netloc
    cache = {} if cache is None else cache
    if host in cache:
        return cache[host]
    where = urllib.parse.urlunsplit((parts.scheme, host, "/robots.txt", "", ""))
    try:
        answer = get(where, accept="text/plain", budget=budget,
                     max_bytes=ROBOTS_MAX_BYTES)
        rules = RobotFileParser()
        rules.parse(answer.text().splitlines())
        got = Robots(host=host, allowed=rules)
    except Unreachable as exc:
        if exc.status is not None and 400 <= exc.status < 500:
            got = Robots(host=host)                 # no rules: nothing asked
        else:
            got = Robots(host=host, why=(
                f"robots.txt at {host} could not be read ({exc}), so what "
                "that host asks of automated readers is unknown and the page "
                "was not fetched"))
    except Refused as exc:
        got = Robots(host=host, why=(
            f"robots.txt at {host} could not be read ({exc}), so what that "
            "host asks of automated readers is unknown and the page was not "
            "fetched"))
    cache[host] = got
    return got


# -- what a fetched document reduces to ----------------------------------------
#
# NO JAVASCRIPT, NO SUBRESOURCES, NO INFERRED URLS. This is a parser, not a
# browser: it executes nothing, requests nothing, and invents no address.
# `links_in_html` returns only the addresses the document itself writes down
# in an `<a href>`, each put through `canonical_url` -- so a `javascript:`,
# `mailto:`, `data:` or `http:` link is dropped here and could not be
# fetched even if a caller asked.

#: Elements whose text is not the document's text. `script` and `style`
#: first, because their content is code.
_SKIP = ("script", "style", "noscript", "template", "svg", "math", "iframe",
         "object", "embed", "canvas", "button", "select", "textarea")

#: Elements that end a line, so the reduced text keeps the document's shape.
_BREAK = ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
          "section", "article", "aside", "header", "footer", "nav", "main",
          "blockquote", "pre", "table", "thead", "tbody", "ul", "ol", "dl",
          "dd", "dt", "figure", "figcaption", "hr", "td", "th", "title")


class _Document(HTMLParser):
    """HTML as text, its title, and the links it states."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.links: list[str] = []
        self.title_parts: list[str] = []
        self._skip = 0
        self._title = False

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        if tag == "title":
            self._title = True
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)
        if tag in _BREAK:
            self.out.append("\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in _SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._title = False
        if tag in _BREAK:
            self.out.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._title:
            self.title_parts.append(data)
        self.out.append(data)


def _tidy(text: str) -> str:
    lines = [" ".join(ln.split()) for ln in text.split("\n")]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


def read_html(raw: str) -> tuple[str, str, list[str]]:
    """(text, title, links as written) for one HTML document."""
    doc = _Document()
    try:
        doc.feed(raw)
        doc.close()
    except Exception:                       # noqa: BLE001 -- malformed HTML
        pass                                # what was parsed is what we have
    return (_tidy("".join(doc.out)),
            " ".join("".join(doc.title_parts).split()), doc.links)


def text_of_html(raw: str) -> str:
    """HTML as plain text. Used for a page's body and for a feed entry's
    summary, which is escaped HTML."""
    return read_html(raw)[0]


def links_in_html(raw: str, base: str) -> list[str]:
    """Only the https addresses the document itself states, normalised and
    in the order it states them. Nothing is inferred and nothing fetched."""
    out: list[str] = []
    for href in read_html(raw)[2]:
        try:
            where = canonical_url(urllib.parse.urljoin(base, href.strip()))
        except Refused:
            continue                        # not https, or not an address
        if where not in out:
            out.append(where)
    return out


# -- what stands in for a binding ----------------------------------------------

#: A collection of public addresses has NOTHING MACHINE-LOCAL TO BIND: the
#: addresses are declared in its scope, in the record, because a public
#: address is a fact about the collection and not about this machine -- and
#: because `canonical_url` refuses an address carrying a credential, so there
#: is no secret for a machine-local binding to keep. This constant stands in
#: the binding's place, so the sweep act says truthfully what the collection
#: was read through and the binding-change machinery is a no-op rather than a
#: fiction. Nothing is written to `mentis.sources.bindings`' file.
NET_BINDING = "net-public-web"


class Network:
    """The binding of a collection that is a set of public addresses."""

    def __init__(self, what: str):
        self.what = what

    def binding(self, corpus, collection):
        return {"binding": NET_BINDING, "root": None, "bound_at": None,
                "remote": "the public web"}

    def bind(self, *a, **kw):
        raise Refused(f"a {self.what} collection is not bound to anything on "
                      "this machine: its addresses are declared in its scope")

    def unbind(self, *a, **kw):
        raise Refused(f"a {self.what} collection has no binding on this "
                      "machine")
