"""The feed connectors: `rss-atom` (declared feed addresses) and
`web-search` (plain queries, resolved to a feed address by a named provider).

WHAT THIS IS. Part W of the Magnet amendment (adm-c38044ee5157 §2), the
owner's decision that "Magnets must be useful beyond software development".
Modelled on `mentis.sources.git` -- the same `CONNECTOR`/`WRITER`/`RESOLVER`,
`declare`/`declaration`, `selected`, `plan`/`sweep`,
`preview_new`/`acquire_new`, `binding_state` and `Connector`, and the same
shared lifecycle in `mentis.sources.lifecycle`. Every byte it reads comes
through `mentis.sources.fetch.get`, which holds every network bound; nothing
here opens a socket.

ONE IMPLEMENTATION, TWO CONNECTOR IDS. A search result acquires as a feed
entry, because that is what it is: the provider answers with RSS. So the
survey, the keys, the entry parsing, the caps and the absence semantics are
written ONCE, in `_Feeds`, and the two connector ids are two instances of it
that differ only in what a scope names (`feeds`, or `queries` and
`provider`) and how an address is arrived at. `mentis.sources.registry`'s
`_module` returns the instance, which answers every attribute the shared
lifecycle reads off a connector module -- the same arrangement
`mentis.sources.sqlite` uses with `mentis.sources.relational`, in one file
because this part owns one file for both.

NO BINDING ON THIS MACHINE. A feed address is public and is DECLARED, in the
record, because it is a fact about the collection and not about this machine
-- and because there is no credential anywhere in this connector for a
machine-local binding to keep (`fetch` refuses an address carrying one). So
`bindings` here is `fetch.Network`: it answers with one constant token,
`fetch.NET_BINDING`, so the sweep act says truthfully what the collection was
read through, and the binding-change machinery is a no-op rather than a
fiction. Nothing is written to `mentis.sources.bindings`' machine-local file.

ABSENCE. A FEED IS A WINDOW, not an enumeration -- exactly git's rule for a
commit window (`mentis.sources.git:52-61`). An entry that scrolls off the end
of a feed is not examined and is NEVER inferred absent: its history stands.
What IS reported, every time, is what went wrong and where:

  a feed that failed      `refused`, with the reason the fetch gave
                          (unreachable, HTTP 404, over the byte cap, a
                          redirect to a private address...)
  an entry with no id     `refused`: the feed gave it no guid, no id, and no
                          link, so it cannot be identified across sweeps and
                          is not acquired under a made-up identity
  an entry over the       `withheld` as `not acquired: over held limit`
  held limit
  an entry before `since` counted as seen and not selected

Nothing is dropped silently, and nothing absent is inferred from a failure.

robots.txt. The amendment asks for it "for `web` page fetches", and that is
where it is (`mentis.sources.webpages`). A FEED ADDRESS IS NOT CHECKED
AGAINST IT, deliberately and by that decision: a feed is published for
readers to fetch, a provider's search feed is the provider's own answer to a
reader, and one GET of an address the owner typed is what a feed reader does.
This is a decision recorded here, not an omission; widening it to feeds needs
only a call to `fetch.robots` in `_survey`.

CAPS. `MAX_FEEDS`, `MAX_QUERIES` per collection; `MAX_ENTRIES_PER_FEED` per
feed; `SWEEP_FETCHES` and `SWEEP_BYTES` for one whole sweep, carried by the
`fetch.Budget` the survey makes. Each is a named constant with a test.
"""

from __future__ import annotations

import email.utils
import hashlib
import re
import time
import unicodedata
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from mentis.sources import (DECLARED, OVER_HELD_LIMIT, PlanChanged, Refused,
                            apply, diff, effective_scope, latest,
                            record_revision, source_id)
from mentis.sources import fetch, lifecycle
from mentis.sources.filesystem import encoding_of
from mentis.sources.filesystem import selected as _selected_path
from mentis.sources.lifecycle import (Cancelled, _binding_changed, _custody,
                                      _patterns, _plan_id, _preview, _Quiet)
from mentis.spine import held

# REUSED RATHER THAN COPIED, as `git` reuses the folder connector's helpers:
# a feed entry's summary is escaped HTML, and what HTML reduces to lives in
# `fetch` so that both web connectors share it rather than importing each
# other.
text_of_html = fetch.text_of_html

__all__ = ["RSS", "SEARCH", "PROVIDERS", "Cancelled"]

#: What wrote these records, honestly known.
WRITER = "feed-connector"

#: How an entry's identity was arrived at. Part of every observation, so a
#: change to it is a change the record shows.
RESOLVER = "feed-entry/1"

#: THE CAPS. Per collection, per feed, and per sweep.
MAX_FEEDS = 20
MAX_QUERIES = 10
MAX_ENTRIES_PER_FEED = 50
MAX_QUERY_CHARS = 200
#: One sweep's whole allowance, handed to `fetch.Budget`. The fetch count is
#: the addresses plus room for their redirects.
SWEEP_FETCHES = 60
SWEEP_BYTES = 16 * 1024 * 1024
#: One feed document. Smaller than `fetch.MAX_RESPONSE_BYTES` would allow,
#: because a feed is a list of short entries and a 2 MiB one is a mistake.
MAX_FEED_BYTES = 1024 * 1024

#: WHAT THE BINDING IS. See the module docstring and `fetch.NET_BINDING`:
#: there is nothing machine-local to bind.
NET_BINDING = fetch.NET_BINDING

#: WHAT A FEED IS ASKED FOR.
ACCEPT = ("application/rss+xml, application/atom+xml, application/xml, "
          "text/xml;q=0.9, */*;q=0.1")


# -- the providers: data in the module, not code -------------------------------
#
# A QUERY IS NOT AN ADDRESS. `web-search` takes plain queries and resolves
# each to a feed address through one of these entries, so a provider can be
# added, corrected or withdrawn without touching a line of the connector.
# Each entry carries its own terms-of-use note, RECORDED as the limit it is
# rather than assumed: it goes into the observation of every object acquired
# through that provider, so the record says what the material was offered
# for.

PROVIDERS: dict[str, dict] = {
    "google-news": {
        "label": "Google News search",
        "template": ("https://news.google.com/rss/search?q={query}"
                     "&hl=en-US&gl=US&ceid=US:en"),
        "format": "RSS 2.0",
        "terms": (
            "Google offers this address as an RSS feed for a personal feed "
            "reader: personal, non-commercial use, one reader's own "
            "queries. That is what a Magnet collecting for its owner is, "
            "and it is recorded here as the limit it is rather than "
            "assumed. It is not a licence to redistribute the results, and "
            "not an API with a quota anyone has agreed."),
        "terms_url": "https://news.google.com/",
        "verified": (
            "2026-11-25, from this machine's network: HTTP 200 and real RSS "
            "2.0 for an arbitrary query, with <guid isPermaLink=\"false\"> "
            "per item, an RFC-822 <pubDate>, and <source url=...> naming the "
            "publisher."),
    },
}

#: Which provider a `web-search` collection uses when it names none.
DEFAULT_PROVIDER = "google-news"


def provider(name) -> dict:
    """One provider, or a refusal that names the ones there are."""
    key = str(name or DEFAULT_PROVIDER).strip().lower()
    got = PROVIDERS.get(key)
    if got is None:
        raise Refused(f"{key!r} is not a search provider Mentis knows; it "
                      f"knows {', '.join(sorted(PROVIDERS))}")
    return {"id": key, **got}


def provider_table() -> list[dict]:
    """The table as the interface shows it, terms note included."""
    return [{"id": k, "label": v["label"], "terms": v["terms"],
             "terms_url": v.get("terms_url")}
            for k, v in sorted(PROVIDERS.items())]


def address_for(query: str, name=None) -> str:
    """The feed address one query is resolved to. The query is percent
    encoded into the template and nothing else is: the template is ours, the
    query is the owner's words, and the two never mix."""
    from urllib.parse import quote
    chosen = provider(name)
    return fetch.canonical_url(
        chosen["template"].format(query=quote(checked_query(query), safe="")))


# -- what a scope may say ------------------------------------------------------

def checked_query(query) -> str:
    if not isinstance(query, str) or not query.strip():
        raise Refused("a search query cannot be empty")
    text = " ".join(query.split())
    if len(text) > MAX_QUERY_CHARS:
        raise Refused(f"a search query is at most {MAX_QUERY_CHARS} "
                      "characters")
    if any(ord(c) < 0x20 or ord(c) == 0x7f for c in text):
        raise Refused("a search query has no control characters")
    return text


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def checked_since(value) -> str:
    """`since` as `YYYY-MM-DD`, or empty for "everything the feed holds"."""
    text = str(value or "").strip()
    if not text:
        return ""
    if not _DATE.match(text):
        raise Refused(f"{text!r} is not a date; give one as YYYY-MM-DD")
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        raise Refused(f"{text!r} is not a date that exists") from None
    return text


def _unique(items: list) -> list:
    out = []
    for i in items:
        if i not in out:
            out.append(i)
    return out


def _list_of(value, what: str) -> list:
    if isinstance(value, str):
        value = [v for v in re.split(r"[\n,]", value) if v.strip()]
    if not isinstance(value, list):
        raise Refused(f"{what} are a list")
    return value


# -- reading a feed ------------------------------------------------------------

_ATOM = "{http://www.w3.org/2005/Atom}"
_RSS1 = "{http://purl.org/rss/1.0/}"
_DC = "{http://purl.org/dc/elements/1.1/}"


def _plain(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text(node) -> str:
    """One element's text, tags and all, as text. An Atom `type="html"` or
    an RSS `<description>` carries escaped HTML; it is reduced, never
    rendered and never fetched from."""
    if node is None:
        return ""
    raw = "".join(node.itertext())
    return text_of_html(raw).strip() if ("<" in raw and ">" in raw) \
        else " ".join(raw.split())


def _child(node, *names):
    for name in names:
        for kid in node:
            if _plain(kid.tag) == name:
                return kid
    return None


def _when(value: str) -> float | None:
    """An entry's date, from RFC 822 (RSS) or ISO 8601 (Atom), as epoch
    seconds -- or None, said rather than guessed."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        when = email.utils.parsedate_to_datetime(text)
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return when.timestamp()
    except (TypeError, ValueError):
        pass
    try:
        iso = text.replace("Z", "+00:00")
        when = datetime.fromisoformat(iso)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when.timestamp()
    except ValueError:
        return None


def _iso(when: float | None) -> str | None:
    if when is None:
        return None
    return datetime.fromtimestamp(when, timezone.utc).isoformat()


def _link_of(node, atom: bool) -> str:
    if atom:
        best = ""
        for kid in node:
            if _plain(kid.tag) != "link":
                continue
            rel = (kid.get("rel") or "alternate").lower()
            href = (kid.get("href") or "").strip()
            if href and rel == "alternate":
                return href
            best = best or href
        return best
    kid = _child(node, "link")
    if kid is not None and (kid.text or "").strip():
        return kid.text.strip()
    return (kid.get("href").strip() if kid is not None and kid.get("href")
            else "")


def parse_feed(data: bytes, *, charset: str | None = None) -> dict:
    """One feed document as `{format, title, entries}`.

    RSS 2.0, RSS 1.0 (RDF) and Atom, read by the element's LOCAL NAME, so a
    feed that declares its namespaces unusually still reads.

    A DOCTYPE IS REFUSED UNREAD. A feed has no business declaring entities,
    and an entity declaration is how a small document becomes a large one
    inside the parser. Refusing it closes that off completely, and the byte
    cap in `fetch` bounds the rest."""
    if b"<!DOCTYPE" in data[:8192].upper():
        raise Refused("this feed declares a DTD; a feed that declares "
                      "entities is not parsed")
    try:
        root = ET.fromstring(data.decode(charset or "utf-8", "replace")
                             if charset else data)
    except ET.ParseError as exc:
        raise Refused(f"this is not a feed Mentis could read as XML "
                      f"({exc})") from None
    name = _plain(root.tag).lower()
    if name == "feed":
        kind, items = "atom", [e for e in root.iter()
                               if _plain(e.tag) == "entry"]
        title = _text(_child(root, "title"))
    elif name == "rss":
        channel = _child(root, "channel")
        channel = root if channel is None else channel
        kind, items = "rss-2.0", [e for e in root.iter()
                                  if _plain(e.tag) == "item"]
        title = _text(_child(channel, "title"))
    elif name == "rdf":
        kind, items = "rss-1.0", [e for e in root.iter()
                                  if _plain(e.tag) == "item"]
        channel = _child(root, "channel")
        title = _text(_child(channel, "title")) if channel is not None else ""
    else:
        raise Refused(f"<{name}> is not an RSS or Atom feed")
    atom = kind == "atom"
    entries = []
    for item in items:
        guid = _child(item, "guid", "id")
        link = _link_of(item, atom)
        when = _when(_text(_child(item, "pubDate", "published", "updated",
                                  "date")))
        source = _child(item, "source")
        publisher = (_text(source) or (source.get("url") if source is not None
                                       else "") or "") if source is not None \
            else ""
        if not publisher:
            author = _child(item, "author")
            publisher = _text(_child(author, "name")) if author is not None \
                else ""
        entries.append({
            "guid": _text(guid), "link": link, "when": when,
            "title": _text(_child(item, "title")),
            "summary": _text(_child(item, "description", "summary",
                                    "content", "encoded")),
            "publisher": publisher,
            "guid_tag": _plain(guid.tag) if guid is not None else None,
        })
    return {"format": kind, "title": title, "entries": entries}


def identity_of(entry: dict) -> tuple[str, str] | tuple[None, None]:
    """(what identifies this entry, how it was arrived at) -- or (None, None)
    when the feed gave nothing that could identify it across sweeps.

    The amendment's rule: the feed's own `guid` or `<id>` where there is one,
    the entry link plus its date where there is not, and WHICH WAS USED is
    recorded either way."""
    if entry.get("guid"):
        return entry["guid"], (entry.get("guid_tag") or "guid")
    if entry.get("link") and entry.get("when") is not None:
        return f"{entry['link']}\n{int(entry['when'])}", "link+date"
    if entry.get("link"):
        return entry["link"], "link"
    return None, None


def _slug(text: str, *, limit: int = 40) -> str:
    """A readable, stable key prefix: the words of a query or the host of a
    feed, lowercased, with everything else as `-`."""
    flat = unicodedata.normalize("NFKD", str(text or "")).lower()
    flat = re.sub(r"[^a-z0-9]+", "-", flat).strip("-")
    return (flat[:limit].rstrip("-") or "x")


def _entry_body(line: dict, entry: dict, basis: str, how: str) -> bytes:
    """The bytes acquired for one entry.

    NOTHING ABOUT THIS SWEEP IS IN HERE -- no fetch time, no batch -- so an
    entry that has not changed hashes to the same digest at the next sweep
    and is `unchanged` rather than re-admitted."""
    lines = [entry["title"] or entry["link"] or basis, ""]
    if entry["link"]:
        lines += [entry["link"], ""]
    if entry["summary"]:
        lines += [entry["summary"], ""]
    lines += ["--",
              f"Published: {_iso(entry['when']) or 'not stated by the feed'}"]
    if entry["publisher"]:
        lines.append(f"Publisher: {entry['publisher']}")
    lines.append(line["said"])
    lines.append(f"Entry id ({how}): {basis}")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


# -- the two connectors --------------------------------------------------------

class _Feeds:
    """One of the two feed connectors. Everything is written once here; the
    two instances below differ only in their id and in what a scope says."""

    # What the shared lifecycle reads off a connector module.
    Refused = Refused
    PlanChanged = PlanChanged
    Cancelled = Cancelled
    DECLARED = DECLARED
    WRITER = WRITER
    RESOLVER = RESOLVER
    uuid = uuid
    time = time
    bindings = fetch.Network("feed")
    _Quiet = _Quiet
    _patterns = staticmethod(_patterns)
    _plan_id = staticmethod(_plan_id)
    _custody = staticmethod(_custody)
    apply = staticmethod(apply)
    effective_scope = staticmethod(effective_scope)
    record_revision = staticmethod(record_revision)
    DRAFT_TTL = 60 * 60
    DRAFT_CAP = 16
    PLAN_CHANGE_REASON = ("the feed moved, or the scope or the record "
                          "changed since it was previewed")

    def __init__(self, connector: str, *, noun: str, label: str):
        self.CONNECTOR = connector
        self.NOUN = noun
        self.LABEL = label
        self.__name__ = f"mentis.sources.feeds[{connector}]"
        self._DRAFTS: dict[tuple[str, str], dict] = {}
        self.Connector = lambda corpus, cv: Connector(self, corpus, cv)

    # -- identity -------------------------------------------------------------
    def source_of(self, collection: str) -> str:
        return source_id(self.CONNECTOR, collection)

    def declaration(self, corpus, collection: str) -> dict | None:
        from mentis.sources import declaration as _one
        d = _one(corpus, collection)
        return d if d and d.get("connector") == self.CONNECTOR else None

    def selected(self, scope: dict, key: str) -> bool:
        """Whether a scope selects a key. The addresses are in `options`; the
        patterns are over keys, exactly as a folder's are over paths, so
        `mentis.sources.reading` can ask this of any key it meets."""
        return _selected_path(scope, key)

    # -- the scope ------------------------------------------------------------
    def checked_options(self, options, *, base=None, root=None) -> dict:
        if options is not None and not isinstance(options, dict):
            raise Refused(f"options are {{{', '.join(self._fields())}}}")
        got = dict(base or {})
        got.update({k: v for k, v in (options or {}).items() if v is not None})
        unknown = sorted(set(got) - set(self._fields()))
        if unknown:
            raise Refused(f"a {self.LABEL} collection has no option "
                          f"{unknown[0]!r}")
        return self._checked(got)

    def _fields(self) -> tuple:
        return ("feeds", "since") if self.CONNECTOR == "rss-atom" \
            else ("queries", "provider")

    def _checked(self, got: dict) -> dict:
        if self.CONNECTOR == "rss-atom":
            feeds = _unique([fetch.declared_url(f, what="feed address")
                             for f in _list_of(got.get("feeds") or [],
                                               "feed addresses")])
            if not feeds:
                raise Refused("an RSS / Atom collection needs at least one "
                              "feed address")
            if len(feeds) > MAX_FEEDS:
                raise Refused(f"a collection follows at most {MAX_FEEDS} "
                              f"feeds; this one names {len(feeds)}")
            return {"feeds": feeds, "since": checked_since(got.get("since"))}
        queries = _unique([checked_query(q)
                           for q in _list_of(got.get("queries") or [],
                                             "search queries")])
        if not queries:
            raise Refused("a web search collection needs at least one query")
        if len(queries) > MAX_QUERIES:
            raise Refused(f"a collection follows at most {MAX_QUERIES} "
                          f"queries; this one names {len(queries)}")
        return {"queries": queries, "provider": provider(
            got.get("provider"))["id"]}

    def _lines(self, options: dict) -> list[dict]:
        """One row per thing that is fetched: what it is, what address it is,
        what its keys are prefixed with, and how it is said in the record."""
        if self.CONNECTOR == "rss-atom":
            return [{"kind": "feed", "shown": f, "url": f,
                     "slug": _slug(fetch.canonical_url(f).split("/")[2]),
                     "said": f"Feed: {f}", "provider": None}
                    for f in options["feeds"]]
        chosen = provider(options["provider"])
        return [{"kind": "query", "shown": q,
                 "url": address_for(q, chosen["id"]), "slug": _slug(q),
                 "said": f"Search: {q!r} through {chosen['label']}",
                 "provider": chosen["id"]}
                for q in options["queries"]]

    # -- the survey: read-only, shared by plan and sweep ----------------------
    def _survey(self, corpus, scope, *, keep: bool, progress=None) -> dict:
        progress = progress or _Quiet()
        options = scope.get("options") or {}
        since = _when(options.get("since") + "T00:00:00+00:00") \
            if options.get("since") else None
        budget = fetch.Budget(max_fetches=SWEEP_FETCHES,
                              max_bytes=SWEEP_BYTES)
        observations, withheld, refused, visible = [], {}, [], []
        read: list[dict] = []
        for line in self._lines(options):
            progress.check()
            progress.folder(line["slug"])
            try:
                answer = fetch.get(line["url"], accept=ACCEPT, budget=budget,
                                   max_bytes=MAX_FEED_BYTES)
                feed = parse_feed(answer.body, charset=answer.charset)
            except Refused as exc:
                # REPORTED, NEVER DROPPED, and nothing is inferred absent
                # from it: the entries this feed gave before are untouched.
                refused.append({"path": line["shown"],
                                "reason": f"not acquired: {exc}"})
                read.append({**{k: line[k] for k in ("kind", "shown")},
                             "status": "failed", "why": str(exc),
                             "entries": 0})
                continue
            kept = 0
            for entry in feed["entries"][:MAX_ENTRIES_PER_FEED]:
                basis, how = identity_of(entry)
                if basis is None:
                    refused.append({
                        "path": f"{line['shown']} -> "
                                f"{entry['title'][:60] or '(untitled)'}",
                        "reason": "refused: the feed gave this entry no "
                                  "guid, no id and no link, so it cannot be "
                                  "identified across sweeps"})
                    continue
                key = (f"{line['slug']}/"
                       + hashlib.sha256(
                           f"{line['url']}\n{basis}".encode("utf-8")
                       ).hexdigest()[:16])
                if since is not None and (entry["when"] or 0) < since:
                    visible.append(key)
                    continue
                if not self.selected(scope, key):
                    visible.append(key)
                    continue
                data = _entry_body(line, entry, basis, how)
                got = self._observed(
                    corpus, key, data, keep=keep, withheld=withheld,
                    native={"label": entry["title"] or entry["link"] or key,
                            "title": entry["title"],
                            "link": entry["link"],
                            "published": _iso(entry["when"]),
                            "publisher": entry["publisher"],
                            "entry_id": basis, "id_from": how,
                            "feed_format": feed["format"],
                            "feed_title": feed["title"],
                            **({"feed": line["url"]}
                               if line["kind"] == "feed" else
                               {"query": line["shown"],
                                "provider": line["provider"],
                                "provider_terms":
                                    provider(line["provider"])["terms"],
                                "search_address": line["url"]})})
                if got is not None:
                    observations.append(got)
                    kept += 1
                    progress.read(len(data))
            read.append({**{k: line[k] for k in ("kind", "shown")},
                         "status": "read", "entries": kept,
                         "offered": len(feed["entries"]),
                         "feed_title": feed["title"],
                         "format": feed["format"]})
        if read and all(r["status"] == "failed" for r in read):
            raise Refused(
                "no feed in this collection could be read: "
                + "; ".join(f"{r['shown']}: {r['why']}" for r in read[:3])
                + ". Nothing was recorded, and nothing is inferred absent.")
        return {"observations": observations, "withheld": withheld,
                "visible": visible, "refused": refused, "unexamined": [],
                # A FEED IS A WINDOW: an entry that scrolled off the end was
                # not examined, so its silence is never absence.
                "examined": lambda obj: False,
                "within": "", "read": read, "spent": budget.left()}

    def _observed(self, corpus, key, data, *, keep, native,
                  withheld) -> dict | None:
        if len(data) > held.MAX_BYTES:
            withheld[key] = OVER_HELD_LIMIT
            return None
        if keep:
            try:
                digest, _ = held.put(corpus.root, data)
            except ValueError:
                withheld[key] = OVER_HELD_LIMIT
                return None
        else:
            digest = hashlib.sha256(data).hexdigest()
        return {"object": key, "state": "present", "retention": "held",
                "digest": digest, "size": len(data),
                "payload_type": "text/plain", "encoding": encoding_of(data),
                "relations": [], "native": native}

    # -- what a plan and a sweep are ------------------------------------------
    def declare(self, corpus, cv, *, name, include=None, exclude=None,
                options=None, declarer, written_by=None) -> dict:
        return lifecycle.declare(self, corpus, cv, name=name, include=include,
                                 exclude=exclude, declarer=declarer,
                                 written_by=written_by, options=options)

    def _proposed(self, eff: dict, scope) -> dict:
        if not isinstance(scope, dict):
            raise Refused("a scope is {include: [...], exclude: [...], "
                          "options: {...}}")
        inc = _patterns(scope.get("include"), eff["include"])
        exc = _patterns(scope.get("exclude"), eff["exclude"])
        opts = self.checked_options(scope.get("options"),
                                    base=eff["options"])
        if (inc, exc, opts) == (eff["include"], eff["exclude"],
                                eff["options"]):
            raise Refused("that is already this collection's scope")
        return {"include": inc, "exclude": exc, "options": opts,
                "act": eff["act"], "revision": "proposed"}

    def _ready(self, corpus, collection: str) -> tuple[dict, dict]:
        decl = self.declaration(corpus, collection)
        if decl is None:
            raise Refused(f"{collection!r} is not a {self.LABEL} collection "
                          "declared in this corpus")
        return decl, self.bindings.binding(corpus, collection)

    def _basis(self, collection, decl, bnd, s, scope) -> dict:
        return {"collection": collection, "declaration": decl["declaration"],
                "binding": bnd["binding"], "options": scope.get("options")}

    def _scope_view(self, scope) -> dict:
        return {"include": scope["include"], "exclude": scope["exclude"],
                "options": scope.get("options")}

    def _revision_options(self, under) -> dict:
        return {"options": under["options"]}

    def _confirm_scope(self, scope, under, s) -> dict:
        return {"scope": self._scope_view(under)} if scope is not None else {}

    def _binding_extra(self, bnd) -> dict:
        return {"remote": bnd.get("remote"),
                "note": "a feed collection is read from its declared "
                        "addresses; nothing is bound on this machine"}

    def _at(self, s) -> dict:
        """WHAT WAS READ: every address, and what it gave. Not a path, and
        nothing about this machine."""
        return {"read": s["read"], "spent": s["spent"]}

    def _preview_result(self, corpus, s, d, pid, changed, bnd) -> dict:
        return {**_preview(corpus, s, d, pid=pid, changed=changed),
                "at": self._at(s)}

    def _sweep_detail(self, s, plan_id, bnd, changed, last, decl) -> dict:
        return {"plan": plan_id, "binding": bnd["binding"],
                "binding_changed": changed, "previous_binding": last,
                "declaration": decl["declaration"], "resolver": RESOLVER,
                "at": self._at(s),
                "not_acquired": [{"path": k, "reason": v}
                                 for k, v in sorted(s["withheld"].items())],
                "refused": s["refused"], "unexamined": s["unexamined"],
                "visible_not_selected": len(s["visible"])}

    def _plan_snapshot(self, corpus, cv, collection: str, *, within=None,
                       scope=None, progress=None) -> tuple:
        if within:
            raise Refused(f"a {self.LABEL} collection is planned whole; "
                          "`within` is a folder's")
        decl, bnd = self._ready(corpus, collection)
        eff = effective_scope(corpus, collection, decl)
        under = self._proposed(eff, scope) if scope is not None else eff
        prior = latest(corpus, self.source_of(collection))
        s = self._survey(corpus, under, keep=False, progress=progress)
        d = diff(prior, s["observations"], examined=s["examined"],
                 withheld=set(s["withheld"]))
        changed, _ = _binding_changed(corpus, collection, bnd["binding"],
                                      prior)
        pid = _plan_id(self._basis(collection, decl, bnd, s, under), under, s,
                       d, prior)
        return decl, bnd, eff, under, s, d, changed, pid

    def _sweep_snapshot(self, corpus, cv, collection, plan_id, decl, bnd,
                        changed, last, *, actor, written_by, scope, because,
                        progress) -> tuple:
        eff = effective_scope(corpus, collection, decl)
        under = self._proposed(eff, scope) if scope is not None else eff
        s = self._survey(corpus, under, keep=True, progress=progress)
        progress.check()
        return decl, bnd, eff, under, s, changed, last, scope is not None, None

    def plan(self, corpus, cv, collection: str, *, within=None, scope=None,
             progress=None) -> dict:
        return lifecycle.plan(self, corpus, cv, collection, within=within,
                              scope=scope, progress=progress)

    def sweep(self, corpus, cv, collection: str, plan_id: str, *, within=None,
              acknowledge_binding_change: bool = False, actor="human",
              written_by=WRITER, scope=None, because=None,
              progress=None) -> dict:
        if within:
            raise Refused(f"a {self.LABEL} collection is swept whole")
        progress = progress or _Quiet()
        decl, bnd = self._ready(corpus, collection)
        prior0 = latest(corpus, self.source_of(collection))
        changed, last = _binding_changed(corpus, collection, bnd["binding"],
                                         prior0)
        return lifecycle.sweep(self, corpus, cv, collection, plan_id,
                               decl=decl, bnd=bnd, changed=changed, last=last,
                               actor=actor, written_by=written_by, scope=scope,
                               because=because, progress=progress)

    # -- a new collection: previewed before anything is declared --------------
    def _forget_drafts(self, corpus_id: str, root=None) -> None:
        lifecycle.forget_drafts(self, corpus_id, root)

    def preview_new(self, corpus, *, name: str, include=None, exclude=None,
                    options=None, progress=None, remote=None) -> dict:
        name = (name or "").strip()
        if not name:
            raise Refused("a collection needs a name")
        if remote is not None:
            raise Refused(f"a {self.LABEL} collection's addresses are its "
                          "scope, not a binding; give them as options")
        inc = _patterns(include, ["*"])
        exc = _patterns(exclude, [])
        opts = self.checked_options(options)
        draft = f"draft-{uuid.uuid4().hex[:12]}"
        scope = {"include": inc, "exclude": exc, "options": opts,
                 "act": draft}
        s = self._survey(corpus, scope, keep=False, progress=progress)
        d = diff({}, s["observations"], examined=s["examined"],
                 withheld=set(s["withheld"]))
        pid = _plan_id({"draft": draft, "name": name, "options": opts}, scope,
                       s, d, {})
        self._forget_drafts(corpus.corpus_id)
        self._DRAFTS[(corpus.corpus_id, draft)] = {
            "name": name, "root": None, "include": inc, "exclude": exc,
            "options": opts, "at": time.time()}
        return {"draft": draft, "collection": None, "name": name,
                **_preview(corpus, s, d, pid=pid, changed=False),
                "at": self._at(s),
                "scope": {"include": inc, "exclude": exc, "options": opts,
                          "act": None, "revision": None},
                "confirm": {"draft": draft, "plan": pid,
                            "acknowledge_binding_change": False}}

    def acquire_new(self, corpus, cv, draft: str, plan_id: str, *,
                    actor="human", written_by=WRITER, progress=None) -> dict:
        progress = progress or _Quiet()
        self._forget_drafts(corpus.corpus_id)
        got = self._DRAFTS.get((corpus.corpus_id, draft))
        if got is None:
            raise Refused(f"{draft!r} is not a preview this server holds (a "
                          "restart forgets previews); preview it again")
        scope = {"include": got["include"], "exclude": got["exclude"],
                 "options": got["options"], "act": draft}
        s = self._survey(corpus, scope, keep=True, progress=progress)
        progress.check()

        def check(prior, d):
            now = _plan_id({"draft": draft, "name": got["name"],
                            "options": got["options"]}, scope, s, d, prior)
            if now != plan_id:
                raise PlanChanged(
                    f"{plan_id} is not what would be recorded now ({now}): "
                    "the feed changed since it was previewed"
                    + _custody(corpus, s) + " Nothing was declared. Preview "
                    "again.")

        with corpus.atomic():
            made = self.declare(corpus, cv, name=got["name"],
                                include=got["include"], exclude=got["exclude"],
                                options=got["options"], declarer=actor,
                                written_by=written_by)
            col = made["collection"]
            bnd = self.bindings.binding(corpus, col)
            out = apply(
                corpus, cv, source=self.source_of(col), collection=col,
                connector=self.CONNECTOR, observations=s["observations"],
                examined=s["examined"], withheld=set(s["withheld"]),
                scope={"declaration": made["declaration"], "revision": None,
                       "within": None},
                act_detail=self._sweep_detail(s, plan_id, bnd, False, None,
                                              made),
                actor=actor, written_by=written_by, check=check,
                observed_at=time.time())
        self._DRAFTS.pop((corpus.corpus_id, draft), None)
        return {**out, "collection": col,
                "declaration": made["declaration"],
                "binding": bnd["binding"], "name": got["name"]}

    def binding_state(self, corpus, collection: str) -> dict:
        return lifecycle.binding_state(self, corpus, collection)


class Connector:
    """One feed connector over one corpus. Owner-side operations; a
    dispatched worker gets the generic reads only, as for every connector."""

    def __init__(self, kind: _Feeds, corpus, cv):
        self.kind, self.corpus, self.cv = kind, corpus, cv

    def declare(self, name, *, include=None, exclude=None, options=None,
                declarer="human", written_by=None):
        return self.kind.declare(self.corpus, self.cv, name=name,
                                 include=include, exclude=exclude,
                                 options=options, declarer=declarer,
                                 written_by=written_by)

    def bind(self, collection, root=None, written_by=None, remote=None):
        raise Refused(
            f"a {self.kind.LABEL} collection is not bound: its addresses are "
            "declared in its scope, which is in the record, and there is no "
            "credential anywhere in this connector to keep on this machine. "
            "Revise the scope instead.")

    def unbind(self, collection, written_by=None):
        raise Refused(f"a {self.kind.LABEL} collection has no binding on "
                      "this machine")

    def plan(self, collection, *, within=None, scope=None, progress=None):
        return self.kind.plan(self.corpus, self.cv, collection, within=within,
                              scope=scope, progress=progress)

    def sweep(self, collection, plan_id, *, within=None,
              acknowledge_binding_change=False, actor="human", scope=None,
              because=None, progress=None, written_by=WRITER):
        return self.kind.sweep(
            self.corpus, self.cv, collection, plan_id, within=within,
            acknowledge_binding_change=acknowledge_binding_change,
            actor=actor, scope=scope, because=because, progress=progress,
            written_by=written_by)

    def preview_new(self, *, name, root=None, include=None, exclude=None,
                    options=None, progress=None, remote=None):
        if root is not None:
            raise Refused(f"a {self.kind.LABEL} collection is not a folder "
                          "on this machine")
        return self.kind.preview_new(self.corpus, name=name, include=include,
                                     exclude=exclude, options=options,
                                     progress=progress, remote=remote)

    def acquire_new(self, draft, plan_id, *, actor="human", progress=None,
                    written_by=WRITER):
        return self.kind.acquire_new(self.corpus, self.cv, draft, plan_id,
                                     actor=actor, progress=progress,
                                     written_by=written_by)

    def binding_state(self, collection):
        return self.kind.binding_state(self.corpus, collection)

    def reveal(self, collection, obj):
        return {"revealed": False, "state": "refused",
                "why": "a feed entry is not on this machine; its link is its "
                       "permalink"}


#: THE TWO CONNECTOR IDS, one implementation. `registry._module` returns
#: these.
RSS = _Feeds("rss-atom", noun="feed", label="RSS / Atom feeds")
SEARCH = _Feeds("web-search", noun="search", label="Web search")
