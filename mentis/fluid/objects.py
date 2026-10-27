"""A post's Markdown objects, addressable by the server (Fluid stage F1).

ONE SOURCE OF OBJECT IDENTITY. The keys are not derived here. The UI's own
`objectsOfPost` (ui/src/experimental/postobjects.ts) keys a post's objects --
the function the conversation already keys its blocks with, plus the media
reader's keys for attachments and what a run returned -- and the UI build
bundles it into `ui/dist/render-check.js` beside the render check. This module
runs that bundle in the same embedded engine (QuickJS) the render check uses
(`mentis.conversation.render_check`); the Fluid client imports the same
function. Nothing here parses Markdown.

ADDRESSES. Two, and each says which it is:

  exact   `exact:<version>:<part>:<key>`  one object in one immutable version
          of a post. It never changes and never stops resolving while the
          post stands. `<part>` is the index in that version's parts, `-` for
          what a run returned (which is no part).
  live    `live:<root>:<key>`  the object under that key in whatever version
          is current. It resolves to the current version's object, or says
          it no longer resolves -- never a guess at a near one.

The key is the client's key, verbatim; it is the last field, so it may hold
`:`. In a URL path the address is one percent-encoded segment.

CACHED BY VERSION, NEVER BY LIVE ADDRESS. A version is immutable, so what was
read from it cannot go stale. The cache key is the version id together with
the two things beside the version that the keys also depend on, so no entry
can outlive what it was read from: the artifacts a run returned with the post
(an act, which a later recovery can add to) and the bundle that read it, by
its path and the digest of its bytes (a rebuilt UI may read differently, and
a size or a time says nothing about what changed). A live address is resolved to its version
on every request.

WITHOUT THE ENGINE (Intel macOS, by decision; see render_check) nothing is
extracted: answers say `extracted: false` with `why_not`, and hand back the
`input` the bundle would have been given, so the client keys it with the same
function.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import threading
from collections import OrderedDict

from mentis import artifacts as _artifacts
from mentis.conversation import render_check as _rc
from mentis.conversation import versions as _versions

from . import read as _read

#: The bundle the UI build writes (the render check's own).
BUNDLE = _rc.BUNDLE
TIME_LIMIT_S = _rc.TIME_LIMIT_S
MEMORY_LIMIT = _rc.MEMORY_LIMIT
#: Longer text is not extracted, and says so (the render check's bound).
MAX_CHARS = _rc.MAX_CHARS
#: Extractions kept, by version. A bound on memory, not a freshness rule.
CACHE_MAX = 512
#: How far back a live address that no longer resolves is looked for.
LOOK_BACK = 20

_lock = threading.Lock()
_engine: dict = {}
_cache: "OrderedDict[tuple, dict]" = OrderedDict()
#: Counted for tests and measurement: extractions run, and served from cache.
stats = {"cold": 0, "cached": 0}


class Unresolved(LookupError):
    """An address that names nothing now: answered 404, saying why."""

    def __init__(self, address, why, **more):
        super().__init__(why)
        self.payload = {"error": why, "kind": "Unresolved",
                        "address": address, "resolves": False, "why": why,
                        **more}


# -- the engine -----------------------------------------------------------------

def _load(path: pathlib.Path):
    import quickjs  # absent: nothing is extracted, and that is said
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if _engine.get("digest") == digest and _engine.get("path") == str(path):
        return _engine
    fn = quickjs.Function(
        "mentisObjects",
        raw.decode("utf-8") + "\nfunction mentisObjects(post) {"
        " if (typeof MentisRenderCheck.extractPost !== 'function')"
        "   throw new Error('this bundle has no extractPost: rebuild the UI');"
        " return JSON.stringify(MentisRenderCheck.extractPost(JSON.parse(post))) }")
    fn.set_time_limit(TIME_LIMIT_S)
    fn.set_memory_limit(MEMORY_LIMIT)
    _engine.clear()
    _engine.update(fn=fn, digest=digest, path=str(path),
                   renderer={"bundle": str(path), "sha256": digest[:16]})
    return _engine


def _why_not_engine(exc) -> str:
    if _rc.intel_mac():
        return ("the render engine (quickjs-ng) is not installed, so the server "
                "did not extract this post's objects. That is expected on Intel "
                "macOS (requirements.txt leaves it out there). The client keys "
                "them from `input` with the same function")
    return ("the render engine (quickjs-ng) is not installed, so the server did "
            f"not extract this post's objects ({exc}). requirements.txt pins it "
            "for this platform: install it with `pip install -r "
            "requirements.txt`. The client keys them from `input` with the "
            "same function")


def _run(post: dict, bundle) -> tuple[dict | None, str | None, dict | None]:
    """(extraction, why_not, renderer). Never raises."""
    path = pathlib.Path(bundle) if bundle else BUNDLE
    size = sum(len(p.get("text") or "") for p in post["parts"]
               if isinstance(p, dict))
    if size > MAX_CHARS:
        return None, (f"the post's text is {size} characters; extraction reads"
                      f" at most {MAX_CHARS}"), None
    try:
        with _lock:
            eng = _load(path)
            got = json.loads(eng["fn"](json.dumps(post)))
            renderer = dict(eng["renderer"])
        if not isinstance(got, dict) or not isinstance(got.get("objects"), list):
            return None, "the bundle returned a malformed extraction", None
        return got, None, renderer
    except ModuleNotFoundError as exc:
        return None, _why_not_engine(exc), None
    except FileNotFoundError:
        return None, (f"the object reader is not built: {path} is missing (it is"
                      " written by the UI build)"), None
    except Exception as exc:                              # noqa: BLE001
        with _lock:
            _engine.clear()
        return None, f"extraction failed: {type(exc).__name__}: {exc}"[:600], None


def _bundle_digest(bundle) -> str | None:
    """The bundle's path and the digest of its bytes: what the cache is keyed
    by, so a bundle whose content changed -- whatever its size and mtime say
    -- never answers from an entry read by the old one."""
    path = pathlib.Path(bundle) if bundle else BUNDLE
    try:
        with open(path, "rb") as fh:
            digest = hashlib.file_digest(fh, "sha256").hexdigest()
    except OSError:
        return None
    return f"{path}:{digest}"


# -- reading a post -----------------------------------------------------------------

def returned_refs(corpus, root) -> list[str]:
    """What the run that posted `root` returned with it, read off the act that
    recorded the reply -- where production reads it -- in the acts' order."""
    out = []
    for a in corpus.operational(turn=[root]):
        if a["act"] in _read.RETURNING_ACTS:
            for ref in (a.get("detail") or {}).get("returned_artifacts") or []:
                out.append(ref)
    return out


def input_of(corpus, root, version_entry, returned) -> dict:
    """What the bundle is given for one version: the ROOT id every key hangs
    from, the version's parts annotated as the reader sees them
    (`artifacts.annotate_part`, which decides what is an attachment), and
    what the run returned, described."""
    parts = [_artifacts.annotate_part(corpus, p)
             for p in (version_entry.get("body") or {}).get("parts") or []]
    return {"id": root, "parts": parts,
            "returned_with": [_artifacts.public(
                _artifacts.describe(corpus, ref, verify="cached"))
                for ref in returned]}


def extract(corpus, root, version_entry, *, returned=None, bundle=None,
            digest=None) -> dict:
    """One version's objects: `{"extracted": True, "objects", "renderer",
    "cached"}` or `{"extracted": False, "why_not", "input"}`. `digest` is the
    bundle's (`_bundle_digest`), when a caller reading many versions has
    already taken it once."""
    returned = returned_refs(corpus, root) if returned is None else returned
    key = (version_entry["id"], tuple(returned),
           digest if digest is not None else _bundle_digest(bundle))
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            stats["cached"] += 1
            return {**hit, "cached": True}
    post = input_of(corpus, root, version_entry, returned)
    got, why_not, renderer = _run(post, bundle)
    if got is None:
        return {"extracted": False, "why_not": why_not, "input": post}
    out = {"extracted": True, "objects": got["objects"], "renderer": renderer}
    with _lock:
        stats["cold"] += 1
        _cache[key] = out
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)
    return {**out, "cached": False}


def _part_token(part) -> str:
    return "-" if part is None else str(part)


def exact_address(version, obj) -> str:
    return f"exact:{version}:{_part_token(obj.get('part'))}:{obj['key']}"


def live_address(root, obj) -> str:
    return f"live:{root}:{obj['key']}"


def parse_address(address: str) -> dict:
    """`exact:<version>:<part>:<key>` or `live:<root>:<key>`; anything else
    is a malformed question (400), never a guess."""
    if address.startswith("exact:"):
        bits = address.split(":", 3)
        if len(bits) == 4 and bits[1] and bits[3] and \
                (bits[2] == "-" or bits[2].isdigit()):
            return {"form": "exact", "version": bits[1],
                    "part": None if bits[2] == "-" else int(bits[2]),
                    "key": bits[3]}
    elif address.startswith("live:"):
        bits = address.split(":", 2)
        if len(bits) == 3 and bits[1] and bits[2]:
            return {"form": "live", "root": bits[1], "key": bits[2]}
    raise _read.BadRequest(
        f"not an object address: {address!r} -- an address is "
        "exact:<version>:<part>:<key> or live:<root>:<key>")


def _root_of(corpus, eid):
    """(root, entry) when `eid` is a post or a version of one, else (None, entry)."""
    got = corpus.read([eid])
    if not got or not _read._is_post(got[0]):
        return None, (got[0] if got else None)
    chain = corpus.history(eid)
    root = chain[0] if chain else eid
    if root not in _read.homes_of(corpus, [root]):
        return None, got[0]
    return root, got[0]


def _where(corpus, root) -> dict:
    homes = _read.homes_of(corpus, [root])
    home = homes.get(root)
    number = _read.numbers_of(corpus, homes).get(root)
    return {"home": home, "home_name": _read._names(corpus, [home]).get(home)
            if home else None, "number": number}


def _listing(o, root, version) -> dict:
    """An object as listed: what it is and where, never its content."""
    out = {k: o.get(k) for k in ("key", "part", "kind", "type", "title", "name",
                                 "identity", "stable", "parent", "page",
                                 "line", "end", "formats")}
    if o.get("duplicate"):
        out["duplicate"] = o["duplicate"]
    out["declared"] = o.get("identity") == "declared"
    out["address"] = {"exact": exact_address(version, o),
                      "live": live_address(root, o)}
    if o.get("block"):
        out["block"] = o["block"]
    if o.get("ref"):
        out["ref"] = o["ref"]
        out["artifact"] = {"ref": o["ref"],
                           "url": f"/api/artifacts/{o['ref']}"}
    if o.get("media_type"):
        out["media_type"] = o["media_type"]
    # ADDITIVE (Objects round): a link object's URL, words, domain and video
    # (B5/B6), and what every object is (`is`, the kind registry).
    if o.get("link"):
        out["link"] = o["link"]
    if o.get("is"):
        out["is"] = o["is"]
    return out


def post_objects(corpus, root, version=None, *, bundle=None) -> dict:
    """`GET /fluid/api/objects?post=<root>[&version=<id>]`."""
    found, entry = _root_of(corpus, root)
    if found is None:
        raise _read.BadRequest(f"not a post: {root!r}")
    if found != root:
        raise _read.BadRequest(
            f"{root} is a version of the post {found}: ask with "
            f"post={found}&version={root}")
    line = _versions.lineage(corpus, root)
    return _listed(corpus, root, line, _where(corpus, root),
                   returned_refs(corpus, root), version, bundle=bundle)


def _listed(corpus, root, line, where, returned, version=None, *,
            bundle=None, digest=None) -> dict:
    """One post's listing, from what was read about it: the answer
    `objects?post=` gives, and each post of a batched one."""
    ids = [v["id"] for v in line["versions"]]
    current = ids[-1] if ids else root
    base = {"post": root, "current_version": current, "versions": ids,
            **where}
    if line["deletion"]:
        return {**base, "version": None, "deleted": True, "objects": [],
                "extracted": None,
                "why": "the post was deleted; its objects are not served"}
    if version and version not in ids:
        raise Unresolved(f"post={root}&version={version}",
                         f"{version} is not a version of the post {root}",
                         post=root, versions=ids)
    v = version or current
    ventry = line["versions"][ids.index(v)]
    got = extract(corpus, root, ventry, returned=returned, bundle=bundle,
                  digest=digest)
    out = {**base, "version": v, "current": v == current, "deleted": False}
    if not got["extracted"]:
        return {**out, "extracted": False, "why_not": got["why_not"],
                "input": got["input"]}
    objs = [_listing(o, root, v) for o in got["objects"]]
    if v != current:
        now = extract(corpus, root, line["versions"][-1], returned=returned,
                      bundle=bundle, digest=digest)
        if now["extracted"]:
            keys = {o["key"] for o in now["objects"]}
            for o in objs:
                o["live_resolves"] = o["key"] in keys
    return {**out, "extracted": True, "cached": got["cached"],
            "renderer": got["renderer"], "objects": objs}


# -- many posts at once (F6) ------------------------------------------------------
#
# ADDITIVE. `objects?post=` answers as it always has. A post card names what
# This post will show for it ("checklist · chart -> This post"), and This post
# shows a post's objects with its whole thread's: asked one post at a time,
# that was a request per reply (15 for #236). These read the same listings
# for many posts in a FIXED NUMBER OF STATEMENTS beside the extractions
# (cached by version, as every listing is): one read of the entries, one of
# which were superseded, one of their homes, one of what runs returned with
# them, and the numbers and names of their homes.

#: The most posts one batched listing names, as `posts?ids=`.
BATCH = _read.BATCH
#: The newest replies a thread's listing and its summary read, at most. The
#: root is always read; `omitted` says how many older replies were not.
THREAD_MAX = _read.PAGE_MAX


def _lines(corpus, ids) -> dict:
    """post -> its lineage, `versions.lineage`'s answer, asking which were
    superseded ONCE for the set: an entry nothing superseded is its own only
    version, and only an edited or deleted one is walked."""
    entries = {e["id"]: e for e in corpus.read(list(ids))} if ids else {}
    touched = {x["link"]["to"] for x in corpus.links(
        relation=corpus.superseding_relation(), to_any=list(entries))} \
        if entries else set()
    return {i: (_versions.lineage(corpus, i) if i in touched else
                {"root": i, "versions": [e], "current": e, "deletion": None})
            for i, e in entries.items()}


def _returned_of(corpus, ids) -> dict:
    """post -> what its run returned with it (`returned_refs`), for a set of
    posts in one read."""
    out = {i: [] for i in ids}
    for a in (corpus.operational(turn=list(ids)) if ids else ()):
        if a["act"] in _read.RETURNING_ACTS and a.get("turn") in out:
            for ref in (a.get("detail") or {}).get("returned_artifacts") or []:
                out[a["turn"]].append(ref)
    return out


def _many(corpus, ids, *, bundle=None) -> list[dict]:
    """Each post's listing, as `objects?post=` gives it, in the order asked;
    one that is not a post (or is a later version of one) is `{"post",
    "error"}` and never fails the others."""
    ids = list(dict.fromkeys(ids))
    lines = _lines(corpus, ids)
    # A post has a home; a later version of one has none, and is refused.
    homes = _read.homes_of(corpus, [i for i in ids if i in lines and
                                    _read._is_post(_first_entry(lines[i]))])
    numbers = _read.numbers_of(corpus, homes)
    names = _read._names(corpus, list(set(homes.values())))
    returned = _returned_of(corpus, list(homes))
    digest = _bundle_digest(bundle)
    out = []
    for i in ids:
        if i not in homes:
            out.append({"post": i, "error": "not a post" if i in lines else
                        "the record holds no such entry"})
            continue
        where = {"home": homes[i], "home_name": names.get(homes[i]),
                 "number": numbers.get(i)}
        out.append(_listed(corpus, i, lines[i], where, returned[i],
                           bundle=bundle, digest=digest))
    return out


def _first_entry(line) -> dict:
    """The entry a lineage was read from (its first version), to say whether
    it is a post at all."""
    return (line["versions"] or [{}])[0]


def posts_objects(corpus, ids, *, bundle=None) -> dict:
    """`GET /fluid/api/objects?posts=<root>,<root>`: each post's listing,
    exactly as `objects?post=<root>` gives it, in the order asked."""
    return {"posts": _many(corpus, ids, bundle=bundle), "limit": BATCH}


#: As deep as `reply_closure` follows a thread.
MAX_DEPTH = 500


def _closures(corpus, roots) -> dict:
    """root -> its thread: `reply_closure(root)`'s rows -- (id, seq,
    recorded_at, parent, depth, home) in (recorded_at, seq) order, a node
    under its FIRST `replies-to` link, kept once at its shallowest depth --
    for MANY roots in a few statements: the tree is walked a level at a time
    for all of them together, two indexed reads a level (the links down, and
    the children's first links), then one of the heads and one of the homes.
    A recursive statement per root was ~22ms each on the live Brain: 25 roots
    with replies on a page cost 560ms."""
    rel = _read.REPLIES_TO
    out = {r: [] for r in roots}
    seen = {r: {r} for r in roots}
    frontier = {r: [r] for r in roots}
    depth = 0
    while frontier and depth < MAX_DEPTH:
        depth += 1
        nodes = sorted({n for ns in frontier.values() for n in ns})
        down = corpus.links(relation=rel, to_any=nodes)
        kids = sorted({x["link"]["from"] for x in down})
        first = _read._first(corpus.links(relation=rel, frm_any=kids)) \
            if kids else {}
        children = {}
        for x in down:
            c, p = x["link"]["from"], x["link"]["to"]
            if first.get(c) == p:
                children.setdefault(p, {})[c] = None
        nxt = {}
        for r, ns in frontier.items():
            for p in ns:
                for c in children.get(p, ()):
                    if c not in seen[r]:
                        seen[r].add(c)
                        out[r].append((c, p, depth))
                        nxt.setdefault(r, []).append(c)
        frontier = nxt
    members = sorted({c for rows in out.values() for c, _p, _d in rows})
    heads = corpus.heads(members) if members else {}
    homes = _read.homes_of(corpus, members) if members else {}
    return {r: sorted(((c, heads[c][0], heads[c][6], p, d, homes.get(c))
                       for c, p, d in rows if c in heads),
                      key=lambda t: (t[2], t[1]))
            for r, rows in out.items()}


def _closure(corpus, root) -> list:
    return _closures(corpus, [root])[root]


def thread_objects(corpus, root, *, bundle=None) -> dict:
    """`GET /fluid/api/objects?thread=<root>`: what This post shows for a
    post -- its own listing and every reply's under it, at any depth and
    wherever each lives, root first, then the replies in stream order. At
    most THREAD_MAX replies, the newest; `omitted` counts the older ones."""
    # As `objects?post=`: a later version is refused, naming its post.
    found, _entry = _root_of(corpus, root)
    if found is None:
        raise _read.BadRequest(f"not a post: {root!r}")
    if found != root:
        raise _read.BadRequest(
            f"{root} is a version of the post {found}: ask with "
            f"thread={found}")
    rows = _closure(corpus, root)
    kept = rows[-THREAD_MAX:]
    return {"root": root, "replies": len(rows),
            "omitted": len(rows) - len(kept),
            "posts": _many(corpus, [root] + [r[0] for r in kept],
                           bundle=bundle)}


# -- a document's words, at most what is drawn (F6 final fix round) ---------------
#
# ADDITIVE. A Markdown or text attachment is drawn as its words, at most
# DOC_MAX bytes of them. `/api/artifacts/<ref>` sends the whole file and has
# no ranges, so a large one crossed the wire whole to be cut in the browser.
# This sends only what is drawn, from the same verified bytes that route
# serves (`artifacts.describe`), and says whether there was more.

#: The most of a document read for drawing, in bytes (the client's DOC_MAX).
DOC_MAX = 256 * 1024


def document_text(corpus, ref, limit=DOC_MAX) -> dict:
    """`GET /fluid/api/document?ref=<adm-...>`: `{"ref", "size", "cut",
    "text"}` -- the first `limit` bytes as UTF-8 (a character the cut split
    is left out), or Unresolved (404) saying why there are no bytes."""
    d = _artifacts.describe(corpus, ref)
    data = d.pop("_bytes", None)
    if data is None:
        raise Unresolved(f"document={ref}", f"no bytes to read: the artifact "
                         f"is {d.get('state')}", state=d.get("state"))
    head = data[:limit]
    if len(data) > limit:
        # Up to three bytes of a character cut in two are left out, not shown as U+FFFD.
        for k in range(4):
            try:
                text = head[:len(head) - k].decode("utf-8")
                break
            except UnicodeDecodeError:
                continue
        else:
            text = head.decode("utf-8", errors="replace")
    else:
        text = head.decode("utf-8", errors="replace")
    return {"ref": ref, "size": len(data), "cut": len(data) > limit,
            "text": text}


# -- what a post card names (F6) ----------------------------------------------------
#
# ONE ANSWER (Objects round). What an object is -- and so what the chip calls
# it -- is decided by the UI's kind registry (ui/src/experimental/objectkinds.ts
# `kindOf`), which the bundle puts on every object it extracts as `is`; the
# chip reads `is.chip`. What follows is the same rule written out for an
# object that carries no `is` (one read by a bundle built before the
# registry); tests hold the two equal.

#: A block's kind, as the post card's chip names it (the demo's "doc"):
#: objectkinds.ts `CHIP_NAME`.
CHIP_NAME = {"pad": "note", "ref": "reference", "markdown": "doc"}
_IMAGE = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
#: What is drawn as its words, as the client's `docKind` decides (F6 final
#: fix round: .py and .json were file cards while .ts and .md were text).
_TEXT = (".md", ".markdown", ".txt", ".py", ".json", ".jsonl", ".ts",
         ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".scss", ".xml",
         ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".sh", ".ps1",
         ".bat", ".sql", ".csv", ".tsv", ".log", ".rs", ".go", ".java",
         ".kt", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift",
         ".diff", ".patch", ".env", ".gitignore", ".dockerfile")
_TEXT_TYPES = ("application/json", "application/xml", "application/javascript",
               "application/x-python", "application/x-sh", "application/yaml",
               "application/x-yaml", "application/toml", "application/sql",
               "application/x-ndjson")


def is_text(media_type, name) -> bool:
    """Whether an attachment is drawn as its words: any text type but HTML
    (opened, not read as source), a structured text type, or a text file's
    name."""
    mt = str(media_type or "").lower().split(";")[0].strip()
    nm = str(name or "").lower()
    return (mt.startswith("text/") and mt != "text/html") or \
        mt in _TEXT_TYPES or mt.endswith(("+json", "+xml")) or \
        nm.endswith(_TEXT)
#: Kinds remembered by extraction key, past the extraction cache's bound:
#: a few words each, so a conversation's cards are not extracted again
#: after other posts pushed their extractions out.
KINDS_MAX = 8192
_kinds: "OrderedDict[tuple, tuple]" = OrderedDict()


def chip_kind(o) -> str | None:
    """How the chip names one object This post draws (the zone's default
    SHOW: top level, never the post's own text), or None for one it does
    not draw."""
    if isinstance(o.get("is"), dict) and "chip" in o["is"]:
        return o["is"]["chip"]
    if o.get("parent") is not None or o.get("kind") == "post-text":
        return None
    if o.get("kind") == "block":
        t = str(o.get("type") or "block").lower()
        return CHIP_NAME.get(t, t)
    mt = str(o.get("media_type") or "").lower()
    name = str(o.get("title") or "").lower()
    if o.get("kind") == "figure" or mt.startswith("image/") \
            or name.endswith(_IMAGE):
        return "image"
    if is_text(mt, name):
        return "doc"
    return "file"


def _kinds_of_version(corpus, root, ventry, returned, digest, bundle):
    """The chip kinds of one version's objects, in order, or None when the
    server could not extract them."""
    key = (ventry["id"], tuple(returned), digest)
    with _lock:
        if key in _kinds:
            _kinds.move_to_end(key)
            hit = _kinds[key]
            return None if hit is None else list(hit)
    got = extract(corpus, root, ventry, returned=returned, bundle=bundle,
                  digest=digest)
    # A FAILED EXTRACTION IS REMEMBERED TOO (None), under the same bound, so
    # a post the engine cannot read is not read again on every card read.
    # The key holds the bundle's digest: a rebuilt bundle is asked afresh.
    kinds = None if not got["extracted"] else \
        tuple(k for k in (chip_kind(o) for o in got["objects"]) if k)
    with _lock:
        _kinds[key] = kinds
        while len(_kinds) > KINDS_MAX:
            _kinds.popitem(last=False)
    return None if kinds is None else list(kinds)


def thread_summaries(corpus, posts, *, bundle=None) -> None:
    """ADD `thread` to each post of a `posts?ids=` answer (`&thread=1`):
    `{"replies", "by_home", "kinds", "extracted"}` -- the whole thread's
    count (every reply under it, at any depth, from any Conversation: the
    count its replies sheet heads), where those replies live, and what This
    post shows for it, by kind in order first met ("checklist", "chart",
    "doc"...): a reply's own objects; a post's with its thread's (at most
    THREAD_MAX replies, as `objects?thread=` reads). Nothing else in the
    answer changes.

    Bounded: every thread is walked together (`_closures`: two statements a
    level of the deepest, and two more), and every post whose objects are
    named is read in one batch (`_lines`, `_returned_of`), beside the
    extractions, which are cached by version."""
    ok = [p for p in posts if not p.get("error")]
    members = {}
    closures = _closures(corpus, [p["id"] for p in ok
                                  if p["replies"]["count"]])
    for p in ok:
        if p["id"] in closures and p.get("reply_to") is None:
            members[p["id"]] = [r[0] for r in closures[p["id"]][-THREAD_MAX:]]
    named = list(dict.fromkeys([p["id"] for p in ok]
                               + [m for ms in members.values() for m in ms]))
    lines = _lines(corpus, named)
    returned = _returned_of(corpus, named)
    digest = _bundle_digest(bundle)
    memo = {}

    def kinds(pid):
        if pid not in memo:
            line = lines.get(pid)
            if not line or line["deletion"] or not line["versions"]:
                memo[pid] = []
            else:
                memo[pid] = _kinds_of_version(corpus, pid,
                                              line["versions"][-1],
                                              returned.get(pid, []), digest,
                                              bundle)
        return memo[pid]

    for p in ok:
        rows = closures.get(p["id"], [])
        by_home = {}
        for r in rows:
            by_home[r[5]] = by_home.get(r[5], 0) + 1
        counts, extracted = {}, True
        for pid in [p["id"]] + members.get(p["id"], []):
            got = kinds(pid)
            if got is None:
                extracted = False
                continue
            for k in got:
                counts[k] = counts.get(k, 0) + 1
        p["thread"] = {"replies": len(rows), "by_home": by_home,
                       "kinds": [[k, n] for k, n in counts.items()],
                       "extracted": extracted}


def _content(o, fmt, address):
    if fmt == "json":
        return o.get("json")
    if fmt in ("md", "csv"):
        if fmt not in (o.get("formats") or ()):
            raise _read.BadRequest(
                f"{address} has no {fmt} form; it has: "
                + ", ".join(o.get("formats") or ()))
        return o.get(fmt)
    raise _read.BadRequest("format is json, md or csv")


def one_object(corpus, address: str, fmt: str = "json", *, bundle=None) -> dict:
    """`GET /fluid/api/objects/<address>?format=json|md|csv`."""
    a = parse_address(address)
    if fmt not in ("json", "md", "csv"):
        raise _read.BadRequest("format is json, md or csv")
    if a["form"] == "exact":
        root, entry = _root_of(corpus, a["version"])
        if root is None:
            raise Unresolved(address, f"{a['version']} is not a version of any"
                             " post" if entry else
                             f"the record holds no entry {a['version']}")
        line = _versions.lineage(corpus, root)
        ids = [v["id"] for v in line["versions"]]
        if a["version"] not in ids:
            raise Unresolved(address, f"{a['version']} is not a version of the"
                             f" post {root}", post=root)
        version = a["version"]
    else:
        root, entry = _root_of(corpus, a["root"])
        if root is None or root != a["root"]:
            raise Unresolved(address, (
                f"{a['root']} is a version, not a post: a live address names "
                f"the post ({root})") if root else
                f"{a['root']} is not a post" if entry else
                f"the record holds no entry {a['root']}")
        line = _versions.lineage(corpus, root)
        ids = [v["id"] for v in line["versions"]]
        version = ids[-1] if ids else root
    if line["deletion"]:
        raise Unresolved(address, "the post was deleted; its objects are not "
                         "served", post=root, deleted=True)
    where = _where(corpus, root)
    ventry = line["versions"][ids.index(version)]
    got = extract(corpus, root, ventry, bundle=bundle)
    head = {"address": address, "form": a["form"], "post": root,
            "version": version, "current": version == ids[-1],
            "current_version": ids[-1], **where}
    if not got["extracted"]:
        return {**head, "extracted": False, "why_not": got["why_not"],
                "input": got["input"], "resolves": None}
    want = [o for o in got["objects"] if o["key"] == a["key"]]
    if a["form"] == "exact" and want and want[0].get("part") != a["part"]:
        raise Unresolved(address, (
            f"the object {a['key']!r} is in part {_part_token(want[0]['part'])}"
            f" of {version}, not part {_part_token(a['part'])}"), post=root,
            version=version)
    if not want:
        if a["form"] == "exact":
            raise Unresolved(address, f"version {version} of {root} has no "
                             f"object {a['key']!r}", post=root,
                             version=version)
        last = None
        for v in reversed(line["versions"][-LOOK_BACK - 1:-1]):
            old = extract(corpus, root, v, bundle=bundle)
            if old["extracted"] and any(o["key"] == a["key"]
                                        for o in old["objects"]):
                last = v["id"]
                break
        raise Unresolved(address, (
            f"no longer resolves: the current version {version} of {root} has "
            f"no object {a['key']!r}"), post=root, version=version,
            last_version=last)
    o = want[0]
    content = _content(o, fmt, address)
    listed = _listing(o, root, version)
    if o.get("ref") and o["kind"] in ("media", "figure"):
        listed["artifact"]["state"] = _artifacts.describe(
            corpus, o["ref"], verify=False)["state"]
    return {**head, "extracted": True, "resolves": True,
            "cached": got["cached"], "object": listed, "format": fmt,
            "content": content}

