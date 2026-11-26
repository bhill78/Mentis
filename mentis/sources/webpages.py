"""The `web` connector: declared page addresses, fetched and reduced to text.

WHAT THIS IS. Part W of the Magnet amendment (adm-c38044ee5157 §2). One
object per URL, keyed by its NORMALISED URL, with the same connector shape
as `mentis.sources.git` -- `CONNECTOR`/`WRITER`/`RESOLVER`, `source_of`,
`selected`, `declare`/`declaration`, `plan`/`sweep`,
`preview_new`/`acquire_new`, `binding_state`, `class Connector` -- and the
same shared lifecycle in `mentis.sources.lifecycle`. Every byte comes
through `mentis.sources.fetch.get`, which holds every network bound;
nothing here opens a socket.

`depth` IS THE DANGEROUS FIELD, and it is treated as one. It DEFAULTS TO 0
-- follow nothing, fetch exactly the addresses the owner declared -- with a
hard maximum of `MAX_DEPTH`, because this is the field that turns a page
fetch into a crawler. Above 0 it follows only links THE PAGE ITSELF WRITES
DOWN in an `<a href>`, only on the same host as the page that stated them,
only `https`, at most `MAX_LINKS_PER_PAGE` from one page and at most
`MAX_PAGES_PER_SWEEP` in one sweep. No URL is guessed or inferred, no
JavaScript is executed, and nothing a page REFERENCES -- image, stylesheet,
script, iframe -- is ever fetched.

robots.txt IS RESPECTED, for the declared addresses as much as for the
followed ones: one `robots.txt` per host per sweep, fetched through the same
bounded GET (never through `RobotFileParser.read`, which would open its own
unchecked connection), and a host whose robots.txt cannot be read at all has
its pages withheld rather than guessed at. See `fetch.Robots`.

ABSENCE. A page is NEVER inferred absent (`examined` answers False for
every key), because the live web is not enumerable from here and a failure
is not evidence that something is gone. What IS reported, against the page's
own identity, every time:

  a page that 404s         `not acquired: the page answered HTTP 404`
  a page robots.txt bars   `not acquired: refused by robots.txt at <host>`
  a page over the cap      `not acquired: over ...`
  something that is not    `not acquired: <media type> is not a page this
  a web page                connector reads` -- no extractor is in scope
                            (amendment §2)

Its latest observation stands untouched in all four cases, which is
`mentis.sources.git:52-61`'s rule: absence is reported, never silently
dropped, and never inferred from a failure.

NO BINDING ON THIS MACHINE: the addresses are the scope, and there is no
credential for a machine-local binding to keep. See `fetch.Network`.
"""

from __future__ import annotations

import hashlib
import re
import sys
import time
import urllib.parse
import uuid

from mentis.sources import (DECLARED, OVER_HELD_LIMIT, PlanChanged, Refused,
                            apply, diff, effective_scope, latest,
                            record_revision, source_id)
from mentis.sources import fetch, lifecycle
from mentis.sources.filesystem import encoding_of
from mentis.sources.filesystem import selected as _selected_path
from mentis.sources.lifecycle import (Cancelled, _binding_changed, _custody,
                                      _patterns, _plan_id, _preview, _Quiet)
from mentis.spine import held

# `DECLARED` and `record_revision` look unused here and are not: the shared
# lifecycle reads them off this module (`lifecycle.declare`,
# `lifecycle.sweep` via `_this`), exactly as it does from
# `mentis.sources.git`. The same goes for `uuid`, `time` and `Refused`.

__all__ = ["Connector", "Cancelled", "selected", "text_of_html",
           "links_in_html"]

CONNECTOR = "web"
LABEL = "Web pages"
NOUN = "page"

#: What wrote these records, honestly known.
WRITER = "web-connector"

#: How a page's relations are read. Part of every observation.
RESOLVER = "web-page/1"

#: THE CAPS. Declared pages per collection; pages fetched in one sweep
#: (declared plus followed); how deep links may be followed and how many
#: from one page; and one sweep's whole allowance.
MAX_URLS = 20
MAX_PAGES_PER_SWEEP = 40
DEFAULT_DEPTH = 0
MAX_DEPTH = 2
MAX_LINKS_PER_PAGE = 20
SWEEP_FETCHES = 120
SWEEP_BYTES = 32 * 1024 * 1024
#: One page document. `fetch.MAX_RESPONSE_BYTES` would allow more; a page of
#: readable text is smaller than this.
MAX_PAGE_BYTES = 1024 * 1024

#: WHAT A PAGE MAY BE. Nothing else is read, because no new extractor is in
#: scope (amendment §2): a PDF or an image is reported as not acquired, with
#: what it was, rather than stored as bytes nothing can read.
PAGE_TYPES = ("text/html", "application/xhtml+xml", "text/plain",
              "text/markdown")

ACCEPT = "text/html, application/xhtml+xml;q=0.9, text/plain;q=0.8, */*;q=0.1"

NET_BINDING = fetch.NET_BINDING

#: The two document helpers, shared with the feed connector: see `fetch`.
text_of_html = fetch.text_of_html
links_in_html = fetch.links_in_html

bindings = fetch.Network("web page")

Refused = Refused
PlanChanged = PlanChanged
PLAN_CHANGE_REASON = ("a page changed, or the scope or the record changed "
                      "since it was previewed")


def source_of(collection: str) -> str:
    return source_id(CONNECTOR, collection)


def declaration(corpus, collection: str) -> dict | None:
    from mentis.sources import declaration as _one
    d = _one(corpus, collection)
    return d if d and d.get("connector") == CONNECTOR else None


def selected(scope: dict, key: str) -> bool:
    """Whether a scope selects a key. The addresses are in `options`; the
    patterns are over keys, exactly as a folder's are over paths, so
    `mentis.sources.reading` can ask this of any key it meets."""
    return _selected_path(scope, key)


# -- what a scope may say ------------------------------------------------------

def _list_of(value, what: str) -> list:
    if isinstance(value, str):
        value = [v for v in re.split(r"[\n,\s]+", value) if v.strip()]
    if not isinstance(value, list):
        raise Refused(f"{what} are a list")
    return value


def checked_options(options, *, base=None, root=None) -> dict:
    """The page collection's own scope fields, checked: `urls` (the declared
    addresses) and `depth` (how far links are followed, 0 by default).

    DEPTH IS CHECKED HERE AND NOWHERE ELSE, so there is one place a reviewer
    reads to know what it can be."""
    if options is not None and not isinstance(options, dict):
        raise Refused("options are {urls: [...], depth: 0}")
    got = dict(base or {})
    got.update({k: v for k, v in (options or {}).items() if v is not None})
    unknown = sorted(set(got) - {"urls", "depth"})
    if unknown:
        raise Refused(f"a {LABEL} collection has no option {unknown[0]!r}")
    urls, seen = [], set()
    for raw in _list_of(got.get("urls") or [], "page addresses"):
        one = fetch.declared_url(raw, what="page address")
        if one not in seen:
            seen.add(one)
            urls.append(one)
    if not urls:
        raise Refused("a web page collection needs at least one address")
    if len(urls) > MAX_URLS:
        raise Refused(f"a collection follows at most {MAX_URLS} page "
                      f"addresses; this one names {len(urls)}")
    raw = got.get("depth", DEFAULT_DEPTH)
    if isinstance(raw, bool):
        raise Refused(f"`depth` must be a whole number, not {raw!r}")
    if isinstance(raw, int):
        depth = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        depth = int(raw.strip())
    else:
        raise Refused(f"`depth` must be a whole number, not {raw!r}")
    if not 0 <= depth <= MAX_DEPTH:
        raise Refused(
            f"`depth` must be from 0 to {MAX_DEPTH}. 0 -- the default -- "
            "fetches exactly the addresses you named and follows nothing; "
            "above 0 the collection follows links the pages themselves "
            "state, on the same host, which is a crawl and is bounded "
            f"at {MAX_PAGES_PER_SWEEP} pages a sweep.")
    return {"urls": urls, "depth": depth}


# -- the survey: read-only, shared by plan and sweep ---------------------------

def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc


def object_key(given) -> str:
    """ONE OBJECT PER URL, keyed by its normalised URL -- as the host it is
    on, then a digest of the whole normalised address.

    WHY NOT THE URL ITSELF, WHICH READS BETTER. A Magnet's `file` source is
    how a collection is read into a Magnet, and the one rule that decides
    what it may name (`mentis.magnet.activation.file_choice` and its Rust
    twin `held_file::choice`) refuses a key holding `:`, `?`, `*`, `[`, `]`
    or an empty component -- so `https://host/a?b=1` could be acquired and
    then never read by the thing this part exists to feed. CHECKED, not
    assumed: `file_choice` accepts this shape and refuses a literal URL.

    Nothing is lost by it. `https` is the only scheme there is here, the
    normalised URL is recorded as `native.url`, it is the page's own
    permalink in `native.link`, it is the second line of the acquired text,
    and this hook is the descriptor's `normalise`, so asking for a page BY
    ITS URL still finds its object. A feed entry's key is the same shape for
    the same reason -- a guid can hold anything at all.

    Given something that is already a key, it is returned unchanged, so
    normalising is idempotent."""
    text = str(given or "").strip()
    try:
        url = fetch.canonical_url(text)
    except Refused:
        return text
    return (f"{_host(url)}/"
            + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16])


def _page_body(url: str, title: str, text: str) -> bytes:
    """The bytes acquired for one page.

    NOTHING ABOUT THIS SWEEP IS IN HERE -- no fetch time -- so a page that
    has not changed hashes to the same digest next sweep and is `unchanged`
    rather than re-admitted."""
    head = [title or url, "", url, ""]
    return ("\n".join(head) + text.strip() + "\n").encode("utf-8")


def _survey(corpus, scope, *, keep: bool, progress=None) -> dict:
    progress = progress or _Quiet()
    options = scope.get("options") or {}
    depth = int(options.get("depth") or 0)
    budget = fetch.Budget(max_fetches=SWEEP_FETCHES, max_bytes=SWEEP_BYTES)
    robots_cache: dict = {}
    observations, withheld, refused, visible = [], {}, [], []
    read: list[dict] = []
    done: set[str] = set()
    # BREADTH FIRST, declared addresses at depth 0. The queue is the only
    # thing that grows, and `MAX_PAGES_PER_SWEEP` bounds what comes off it.
    queue = [(u, 0, None) for u in options.get("urls") or []]
    fetched = 0
    while queue:
        url, at, came_from = queue.pop(0)
        if url in done:
            continue
        done.add(url)
        # THE ADDRESS IS WHAT IS FETCHED; THE KEY IS WHAT IS RECORDED. See
        # `object_key` for why they are not the same string.
        key = object_key(url)
        progress.check()
        progress.folder(_host(url))
        if fetched >= MAX_PAGES_PER_SWEEP:
            note = (f"not acquired: this sweep has already fetched "
                    f"{fetched} pages, its limit of {MAX_PAGES_PER_SWEEP}")
            if at == 0:
                withheld[key] = note
            else:
                refused.append({"path": url, "reason": note})
            continue
        if not selected(scope, key):
            visible.append(key)
            continue
        rules = fetch.robots(url, budget=budget, cache=robots_cache)
        barred = rules.may(url)
        if barred is not None:
            withheld[key] = f"not acquired: {barred}"
            read.append({"url": url, "key": key, "depth": at,
                         "status": "robots", "why": barred})
            continue
        try:
            answer = fetch.get(url, accept=ACCEPT, budget=budget,
                               max_bytes=MAX_PAGE_BYTES)
            fetched += 1
            # AND AGAIN AFTER A REDIRECT. robots.txt was consulted for the
            # address asked for; a redirect can land somewhere else, on
            # another host, that the host asks readers not to fetch. The
            # body is already here, so this is what keeps it out of the
            # record rather than what keeps it off the wire -- and it is
            # the reason a redirect cannot be used to get around robots.
            if answer.final_url != url:
                after = fetch.robots(answer.final_url, budget=budget,
                                     cache=robots_cache).may(
                                         answer.final_url)
                if after is not None:
                    raise Refused(f"{url} redirected to "
                                  f"{answer.final_url}, and {after}")
            if answer.media_type and answer.media_type not in PAGE_TYPES:
                raise Refused(
                    f"{answer.media_type} is not a page this connector "
                    "reads: it reduces HTML and plain text to text, and no "
                    "extractor for anything else is in scope")
        except Refused as exc:
            # REPORTED AGAINST THE PAGE'S OWN IDENTITY, and nothing is
            # inferred absent from it: its latest observation stands.
            withheld[key] = f"not acquired: {exc}"
            read.append({"url": url, "key": key, "depth": at,
                         "status": "failed", "why": str(exc),
                         **({"http": exc.status}
                            if getattr(exc, "status", None) else {})})
            continue
        raw = answer.text()
        text, title, _ = fetch.read_html(raw) if answer.media_type != \
            "text/plain" else (raw.strip(), "", [])
        data = _page_body(answer.final_url, title, text)
        got = _observed(corpus, key, data, keep=keep, withheld=withheld,
                        native={"label": title or url, "title": title,
                                "link": answer.final_url, "url": url,
                                "depth": at, "followed_from": came_from,
                                "media_type": answer.media_type,
                                "redirects": list(answer.redirects)})
        if got is not None:
            observations.append(got)
            progress.read(len(data))
        read.append({"url": url, "key": key, "depth": at, "status": "read",
                     "title": title, "bytes": len(answer.body)})
        if at < depth:
            # ONLY WHAT THE PAGE ITSELF STATES, only https, only this host.
            here = _host(url)
            onwards = [w for w in links_in_html(raw, answer.final_url)
                       if _host(w) == here and w not in done]
            queue.extend((w, at + 1, url)
                         for w in onwards[:MAX_LINKS_PER_PAGE])
    if read and all(r["status"] != "read" for r in read):
        raise Refused(
            "no page in this collection could be read: "
            + "; ".join(f"{r['url']}: {r.get('why')}" for r in read[:3])
            + ". Nothing was recorded, and nothing is inferred absent.")
    return {"observations": observations, "withheld": withheld,
            "visible": visible, "refused": refused, "unexamined": [],
            # THE LIVE WEB IS NOT ENUMERABLE FROM HERE: a page is never
            # inferred absent, and a failure is reported as a failure.
            "examined": lambda obj: False,
            "within": "", "read": read, "spent": budget.left(),
            "pages": fetched}


def _observed(corpus, key, data, *, keep, native, withheld) -> dict | None:
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
            "digest": digest, "size": len(data), "payload_type": "text/plain",
            "encoding": encoding_of(data), "relations": [], "native": native}


# -- the declaration, plan and sweep -------------------------------------------

_this = sys.modules[__name__]
_DRAFTS: dict[tuple[str, str], dict] = {}
DRAFT_TTL = 60 * 60
DRAFT_CAP = 16


def declare(corpus, cv, *, name: str, include=None, exclude=None,
            options=None, declarer, written_by=None) -> dict:
    return lifecycle.declare(_this, corpus, cv, name=name, include=include,
                             exclude=exclude, declarer=declarer,
                             written_by=written_by, options=options)


def _proposed(eff: dict, scope) -> dict:
    if not isinstance(scope, dict):
        raise Refused("a scope is {include: [...], exclude: [...], "
                      "options: {...}}")
    inc = _patterns(scope.get("include"), eff["include"])
    exc = _patterns(scope.get("exclude"), eff["exclude"])
    opts = checked_options(scope.get("options"), base=eff["options"])
    if (inc, exc, opts) == (eff["include"], eff["exclude"], eff["options"]):
        raise Refused("that is already this collection's scope")
    return {"include": inc, "exclude": exc, "options": opts,
            "act": eff["act"], "revision": "proposed"}


def _ready(corpus, collection: str) -> tuple[dict, dict]:
    decl = declaration(corpus, collection)
    if decl is None:
        raise Refused(f"{collection!r} is not a {LABEL} collection declared "
                      "in this corpus")
    return decl, bindings.binding(corpus, collection)


def _basis(collection, decl, bnd, s, scope) -> dict:
    return {"collection": collection, "declaration": decl["declaration"],
            "binding": bnd["binding"], "options": scope.get("options")}


def _scope_view(scope) -> dict:
    return {"include": scope["include"], "exclude": scope["exclude"],
            "options": scope.get("options")}


def _revision_options(under) -> dict:
    return {"options": under["options"]}


def _confirm_scope(scope, under, s) -> dict:
    return {"scope": _scope_view(under)} if scope is not None else {}


def _binding_extra(bnd) -> dict:
    return {"remote": bnd.get("remote"),
            "note": "a web page collection is read from its declared "
                    "addresses; nothing is bound on this machine"}


def _at(s) -> dict:
    """WHAT WAS READ: every address and what it gave. Nothing about this
    machine."""
    return {"read": s["read"], "pages": s["pages"], "spent": s["spent"]}


def _preview_result(corpus, s, d, pid, changed, bnd) -> dict:
    return {**_preview(corpus, s, d, pid=pid, changed=changed), "at": _at(s)}


def _sweep_detail(s, plan_id, bnd, changed, last, decl) -> dict:
    return {"plan": plan_id, "binding": bnd["binding"],
            "binding_changed": changed, "previous_binding": last,
            "declaration": decl["declaration"], "resolver": RESOLVER,
            "at": _at(s),
            "not_acquired": [{"path": k, "reason": v}
                             for k, v in sorted(s["withheld"].items())],
            "refused": s["refused"], "unexamined": s["unexamined"],
            "visible_not_selected": len(s["visible"])}


def _plan_snapshot(corpus, cv, collection: str, *, within=None, scope=None,
                   progress=None) -> tuple:
    if within:
        raise Refused(f"a {LABEL} collection is planned whole; `within` is a "
                      "folder's")
    decl, bnd = _ready(corpus, collection)
    eff = effective_scope(corpus, collection, decl)
    under = _proposed(eff, scope) if scope is not None else eff
    prior = latest(corpus, source_of(collection))
    s = _survey(corpus, under, keep=False, progress=progress)
    d = diff(prior, s["observations"], examined=s["examined"],
             withheld=set(s["withheld"]))
    changed, _ = _binding_changed(corpus, collection, bnd["binding"], prior)
    pid = _plan_id(_basis(collection, decl, bnd, s, under), under, s, d, prior)
    return decl, bnd, eff, under, s, d, changed, pid


def _sweep_snapshot(corpus, cv, collection, plan_id, decl, bnd, changed, last,
                    *, actor, written_by, scope, because, progress) -> tuple:
    eff = effective_scope(corpus, collection, decl)
    under = _proposed(eff, scope) if scope is not None else eff
    s = _survey(corpus, under, keep=True, progress=progress)
    progress.check()
    return decl, bnd, eff, under, s, changed, last, scope is not None, None


def plan(corpus, cv, collection: str, *, within=None, scope=None,
         progress=None) -> dict:
    return lifecycle.plan(_this, corpus, cv, collection, within=within,
                          scope=scope, progress=progress)


def sweep(corpus, cv, collection: str, plan_id: str, *, within=None,
          acknowledge_binding_change: bool = False, actor="human",
          written_by=WRITER, scope=None, because=None,
          progress=None) -> dict:
    if within:
        raise Refused(f"a {LABEL} collection is swept whole")
    progress = progress or _Quiet()
    decl, bnd = _ready(corpus, collection)
    prior0 = latest(corpus, source_of(collection))
    changed, last = _binding_changed(corpus, collection, bnd["binding"],
                                     prior0)
    return lifecycle.sweep(_this, corpus, cv, collection, plan_id, decl=decl,
                           bnd=bnd, changed=changed, last=last, actor=actor,
                           written_by=written_by, scope=scope,
                           because=because, progress=progress)


# -- a new collection: previewed before anything is declared -------------------

def _forget_drafts(corpus_id: str, root=None) -> None:
    lifecycle.forget_drafts(_this, corpus_id, root)


def preview_new(corpus, *, name: str, include=None, exclude=None,
                options=None, progress=None, remote=None) -> dict:
    name = (name or "").strip()
    if not name:
        raise Refused("a collection needs a name")
    if remote is not None:
        raise Refused("a web page collection's addresses are its scope, not "
                      "a binding; give them as options")
    inc = _patterns(include, ["*"])
    exc = _patterns(exclude, [])
    opts = checked_options(options)
    draft = f"draft-{uuid.uuid4().hex[:12]}"
    scope = {"include": inc, "exclude": exc, "options": opts, "act": draft}
    s = _survey(corpus, scope, keep=False, progress=progress)
    d = diff({}, s["observations"], examined=s["examined"],
             withheld=set(s["withheld"]))
    pid = _plan_id({"draft": draft, "name": name, "options": opts}, scope, s,
                   d, {})
    _forget_drafts(corpus.corpus_id)
    _DRAFTS[(corpus.corpus_id, draft)] = {
        "name": name, "root": None, "include": inc, "exclude": exc,
        "options": opts, "at": time.time()}
    return {"draft": draft, "collection": None, "name": name,
            **_preview(corpus, s, d, pid=pid, changed=False), "at": _at(s),
            "scope": {"include": inc, "exclude": exc, "options": opts,
                      "act": None, "revision": None},
            "confirm": {"draft": draft, "plan": pid,
                        "acknowledge_binding_change": False}}


def acquire_new(corpus, cv, draft: str, plan_id: str, *, actor="human",
                written_by=WRITER, progress=None) -> dict:
    progress = progress or _Quiet()
    _forget_drafts(corpus.corpus_id)
    got = _DRAFTS.get((corpus.corpus_id, draft))
    if got is None:
        raise Refused(f"{draft!r} is not a preview this server holds (a "
                      "restart forgets previews); preview it again")
    scope = {"include": got["include"], "exclude": got["exclude"],
             "options": got["options"], "act": draft}
    s = _survey(corpus, scope, keep=True, progress=progress)
    progress.check()

    def check(prior, d):
        now = _plan_id({"draft": draft, "name": got["name"],
                        "options": got["options"]}, scope, s, d, prior)
        if now != plan_id:
            raise PlanChanged(
                f"{plan_id} is not what would be recorded now ({now}): the "
                "pages changed since they were previewed" + _custody(corpus, s)
                + " Nothing was declared. Preview again.")

    with corpus.atomic():
        made = declare(corpus, cv, name=got["name"], include=got["include"],
                       exclude=got["exclude"], options=got["options"],
                       declarer=actor, written_by=written_by)
        col = made["collection"]
        bnd = bindings.binding(corpus, col)
        out = apply(corpus, cv, source=source_of(col), collection=col,
                    connector=CONNECTOR, observations=s["observations"],
                    examined=s["examined"], withheld=set(s["withheld"]),
                    scope={"declaration": made["declaration"],
                           "revision": None, "within": None},
                    act_detail=_sweep_detail(s, plan_id, bnd, False, None,
                                             made),
                    actor=actor, written_by=written_by, check=check,
                    observed_at=time.time())
    _DRAFTS.pop((corpus.corpus_id, draft), None)
    return {**out, "collection": col, "declaration": made["declaration"],
            "binding": bnd["binding"], "name": got["name"]}


def binding_state(corpus, collection: str) -> dict:
    return lifecycle.binding_state(_this, corpus, collection)


class Connector:
    """The web page connector over one corpus. Owner-side operations; a
    dispatched worker gets the generic reads only, as for every connector."""

    def __init__(self, corpus, cv):
        self.corpus, self.cv = corpus, cv

    def declare(self, name, *, include=None, exclude=None, options=None,
                declarer="human", written_by=None):
        return declare(self.corpus, self.cv, name=name, include=include,
                       exclude=exclude, options=options, declarer=declarer,
                       written_by=written_by)

    def bind(self, collection, root=None, written_by=None, remote=None):
        raise Refused(
            "a web page collection is not bound: its addresses are declared "
            "in its scope, which is in the record, and there is no "
            "credential anywhere in this connector to keep on this machine. "
            "Revise the scope instead.")

    def unbind(self, collection, written_by=None):
        raise Refused("a web page collection has no binding on this machine")

    def plan(self, collection, *, within=None, scope=None, progress=None):
        return plan(self.corpus, self.cv, collection, within=within,
                    scope=scope, progress=progress)

    def sweep(self, collection, plan_id, *, within=None,
              acknowledge_binding_change=False, actor="human", scope=None,
              because=None, progress=None, written_by=WRITER):
        return sweep(self.corpus, self.cv, collection, plan_id, within=within,
                     acknowledge_binding_change=acknowledge_binding_change,
                     actor=actor, scope=scope, because=because,
                     progress=progress, written_by=written_by)

    def preview_new(self, *, name, root=None, include=None, exclude=None,
                    options=None, progress=None, remote=None):
        if root is not None:
            raise Refused("a web page collection is not a folder on this "
                          "machine")
        return preview_new(self.corpus, name=name, include=include,
                           exclude=exclude, options=options,
                           progress=progress, remote=remote)

    def acquire_new(self, draft, plan_id, *, actor="human", progress=None,
                    written_by=WRITER):
        return acquire_new(self.corpus, self.cv, draft, plan_id, actor=actor,
                           progress=progress, written_by=written_by)

    def binding_state(self, collection):
        return binding_state(self.corpus, collection)

    def reveal(self, collection, obj):
        return {"revealed": False, "state": "refused",
                "why": "a web page is not on this machine; its URL is its "
                       "permalink"}
