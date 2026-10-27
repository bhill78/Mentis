"""Searching inside acquired text, with excerpts that cite exact bytes.

SOURCES A (spec `adm-fc4356b9eff0`, approved "Yes, A after B"). This reverses
decision 4 ("`#` matches acquired object names and labels only. No content
indexing") FOR SCANNING ONLY: there is no stored index, and nothing here
writes anything.

WHAT IS SEARCHED is exactly what `read_source` serves of the latest record:
for each declared collection, the latest PRESENT observation of each object,
whose bytes are held, not purged and verify against their digest -- in one
or more REPRESENTATIONS:

  * its own bytes, when its recorded encoding is text (`encoding.text` --
    strict UTF-8, no NUL, decided at acquisition). Markdown, plain text, CSV
    and code are all that one class and are read directly; nothing is
    extracted from them in production (Sources C, C0). Offsets are BYTES in
    the stored file, cited `adm-…@d12[s:e]`.
  * each current extraction configured for its payload type (Sources C,
    C3; `mentis.sources.extract`): one exact extractor identity's linear
    text, beside the corpus. Offsets are CODE POINTS in that
    representation, cited `adm-…@d12~<extractor_id>/<r12>[s:e]{scheme:token}`,
    and each hit names the representation it came from and its source
    location. One that is missing is made now, in the background, and
    `search` waits for it a bounded time (`extract.engine.WAIT`); any still
    being made is said to be pending. `first_in_each` (`find`, `#`) never
    waits: it starts the extraction and says it is pending.

Every hit says its unit (`byte` or `codepoint`) and its representation
(`extraction` is None for a file's own bytes). What was NOT searched is
COUNTED, by payload type, in `not_searched` -- a file with no extractor, one
pending, one whose extraction is empty or failed, one whose last attempt
failed for a reason of the environment and is tried again later
(`transient`), one whose extractor cannot run here -- and never presented
as searched. Corrupt or missing bytes are
counted as unreadable, never read.

MATCHING is a literal phrase, case-insensitive by Unicode casefold on both
sides and NFC-normalised: `fold(s) = NFC(casefold(NFC(s)))`. No regex, no
wildcards.

OFFSETS ARE BYTES OF THE TEXT SEARCHED, never positions in the folded text
(converted to code points last, for a representation).
Folding changes lengths (`ß` -> `ss`, `ﬁ` -> `fi`, `e` + U+0301 -> `é`), so
the folded text is built in PIECES that remember where each came from: text
that folds one character to one character maps character by character;
anything else is cut into segments that NFC cannot join across, and each
segment folds as a whole. A match is mapped back through its pieces; one
that starts or ends inside a segment widens to the whole segment, so the
cited bytes are always whole characters and always contain the match (`s`
against `Straße` cites the `ß`). `read_source(ref, offset=excerpt.offset,
length=excerpt.length)` returns the excerpt exactly.

A MATCH IS A DISTINCT SPAN OF STORED BYTES. Matches do not overlap in the
folded text (`aa` in `aaaa` is two), and matches whose widened spans meet
inside one segment (`s` twice inside `ß`) are one match, citing the union of
their bytes -- so every count is of places a reader can tell apart. A match
whose span is longer than an excerpt (`EXCERPT_BYTES`) cannot be quoted
whole in one: it is never returned with a partial excerpt, and is counted in
`not_returned.over_excerpt`, with its file.

BOUNDS ARE SAID, NOT HIDDEN. The answer is the hit set H: the first
`PER_FILE` matches of each representation of each file, by position, over
files in collection order (name casefolded, then id), then key order (code
point), then representation (the file's own bytes first, then extractions in
configured order). Any further match
of a file is counted, not returned: `more_in_file` on every hit of that
file, the same in every answer, and `not_returned.beyond_per_file` in all;
`read_source` reads on from the cited bytes. One answer is `H[offset:offset +
limit]`, so continuing by `next_offset` reaches every hit in H exactly once, in
order, and `total_matches = hits_total + beyond_per_file + over_excerpt`. A
scan budget stops a query that would read too much, and says where.

A SEARCH CONTINUES IN BOUNDED SLICES (Stage F; owner Turn ent-61a9c4ea762a:
"Allow searches to continue beyond the existing 256 MiB scan budget through
bounded continuation. Report examined coverage and remaining scope
honestly. Never present partial search results as exhaustive."). The walk
is every present object in scope in the order above (`_plan`); a slice is
the run of it from where the last one stopped that fits the budget, counted
in RECORDED bytes (`_cost`), so where a slice ends depends on the record
alone and asking for the same slice again gives the same objects. An
answer that did not reach the end of the walk gives a `continuation`: the
object the next slice starts with, the phrase and scope it belongs to, and
where the record stood for each collection in scope (`_state_of`) and for
the configured extractors. The next slice is searched only if all of that
still holds; otherwise it is refused, naming what moved, and nothing is
searched -- slices of two states of the record are never joined. The
slices of one search are the walk cut into consecutive runs, so the hit sets
of all of them, in order, are exactly the hit set of one unbounded search:
nothing twice and nothing skipped. Every answer says its `coverage` --
objects and bytes examined before it, in it and still to come -- and is
`complete` only when the walk has reached its end; `exhaustive` only when,
besides, nothing reached went unsearched. Neither is ever claimed of a
partial answer, with matches or without. The token is plain data, checked
against the record on use, never stored: nothing here writes anything.

CHEAP WHEN WARM, AND STILL NOT AN INDEX. Each verified file version is kept
in this process's memory, keyed by what would change if the file did (the
same key `artifacts.describe(verify="cached")` uses), bounded by
`CACHE_BYTES` of what it really holds -- the bytes, the folded text and the
map back (`Folded.cost`) -- and discarded with the process. The map is two
integer arrays, an entry per piece, and runs of text that fold one to one
share a piece. It holds the folded text of bytes already verified; it is
never written anywhere, and a changed file is read and verified again.
"""

from __future__ import annotations

import base64
import bisect
import collections
import hashlib
import hmac
import json
import re
import secrets
import sys
import threading
from array import array
import unicodedata

from mentis.sources import (Refused, bindings, declarations, effective_scope,
                            fingerprint, latest, observation)
from mentis.sources import registry
from mentis.sources import reading
from mentis.sources.extract import cite as C, config as XC, engine
from mentis.spine import held

#: At most this many hits of one representation in one answer.
PER_FILE = 3
#: Hits in one answer, by default and at most.
LIMIT = 20
LIMIT_MAX = 100
#: An excerpt: about this many lines either side of the match ...
CONTEXT_LINES = 3
#: ... and never more than this many bytes.
EXCERPT_BYTES = 4 * 1024
#: A snippet, in characters.
SNIPPET_CHARS = 240
#: The bytes of text one query may scan before it stops and says so.
BUDGET = 256 * 1024 * 1024
#: The longest phrase, in characters. A phrase is a few words, and an
#: excerpt must be able to hold the whole match.
PHRASE_CHARS = 500
#: What this process keeps folded in memory, in bytes it really holds.
CACHE_BYTES = 64 * 1024 * 1024
#: Non-ASCII text that folds one character to one may share a piece up to
#: this many characters; a position inside one is found by decoding it.
RUN_CHARS = 64


# -- folding, with the way back to bytes --------------------------------------

def fold(s: str) -> str:
    """The form both sides are compared in."""
    return unicodedata.normalize(
        "NFC", unicodedata.normalize("NFC", s).casefold())


def _composes_after() -> frozenset[str]:
    """Characters NFC may join to the character BEFORE them: the second half
    of every primary canonical composition, and the Hangul medial and final
    jamo. A segment may not start with one. (Unicode's NFC_Quick_Check=Maybe
    set, derived here because Python does not expose it.)"""
    out = set()
    for cp in range(0x30000):
        d = unicodedata.decomposition(chr(cp))
        if not d or d.startswith("<"):
            continue
        parts = d.split()
        if len(parts) != 2:
            continue
        pair = "".join(chr(int(p, 16)) for p in parts)
        if unicodedata.normalize("NFC", pair) == chr(cp):
            out.add(pair[1])
    out.update(chr(c) for c in range(0x1161, 0x1176))      # Hangul V
    out.update(chr(c) for c in range(0x11A8, 0x11C3))      # Hangul T
    return frozenset(out)


_JOINS: frozenset[str] | None = None
_JOINS_LOCK = threading.Lock()


def _joins() -> frozenset[str]:
    global _JOINS
    if _JOINS is None:
        with _JOINS_LOCK:
            if _JOINS is None:
                _JOINS = _composes_after()
    return _JOINS


_NON_ASCII = re.compile(r"[^\x00-\x7f]+")
#: The kinds of piece: ASCII, one character to one byte; one character to
#: one character, at most `RUN_CHARS`; one segment, mapped only whole.
_ASCII, _ONE, _WHOLE = 0, 1, 2


class Folded:
    """One file's text, folded, with the way back to its bytes.

    Piece `i` is the folded text from `fstart[i]` to `fstart[i + 1]`, which
    came from the file's bytes from `bstart[i]` to `bstart[i + 1]`, and is
    of `kind[i]`. Two integer arrays and a byte per piece, so what a file
    costs to keep is known: `cost`."""

    __slots__ = ("data", "text", "fstart", "bstart", "kind", "whole", "cost")

    def __init__(self, data: bytes):
        self.data = data
        text = data.decode("utf-8")                         # strict
        joins = _joins()
        parts: list[str] = []
        fstart, bstart, kind = array("q"), array("q"), bytearray()
        f = b = run = 0

        def put(src: str, out: str, k: int):
            nonlocal f, b, run
            last = kind[-1] if kind else _WHOLE
            if k != _WHOLE and last != _WHOLE and (
                    last == k == _ASCII or run + len(out) <= RUN_CHARS):
                kind[-1] = max(last, k)          # joins the open piece
                run += len(out)
            else:
                fstart.append(f)
                bstart.append(b)
                kind.append(k)
                run = len(out)
            parts.append(out)
            f += len(out)
            b += len(src) if k == _ASCII else len(src.encode("utf-8"))

        def seg(src: str):
            out = fold(src)
            put(src, out, _ONE if len(src) == 1 == len(out) else _WHOLE)

        pos = 0
        for m in _NON_ASCII.finditer(text):
            a, z = m.start(), m.end()
            # A mark or a joining character belongs with the character
            # before it, even when that one is ASCII (`e` + U+0301).
            if a > pos and (unicodedata.combining(text[a])
                            or text[a] in joins):
                a -= 1
            if a > pos:
                put(text[pos:a], text[pos:a].lower(), _ASCII)
            at = a
            for i in range(a + 1, z):
                c = text[i]
                if not unicodedata.combining(c) and c not in joins:
                    seg(text[at:i])
                    at = i
            seg(text[at:z])
            pos = z
        if pos < len(text):
            put(text[pos:], text[pos:].lower(), _ASCII)
        self.text = "".join(parts)
        fstart.append(f)                                    # the ends
        bstart.append(b)
        self.fstart, self.bstart, self.kind = fstart, bstart, bytes(kind)
        self.whole = _WHOLE in self.kind
        self.cost = sum(map(sys.getsizeof, (
            self, data, self.text, fstart, bstart, self.kind)))

    def _piece(self, fi: int) -> int:
        return bisect.bisect_right(self.fstart, fi, 0, len(self.kind)) - 1

    def _byte(self, i: int, fi: int) -> int:
        """The byte that folded position `fi`, inside one-to-one piece `i`,
        came from."""
        n, at = fi - self.fstart[i], self.bstart[i]
        if self.kind[i] == _ASCII:
            return at + n
        piece = self.data[at:self.bstart[i + 1]].decode("utf-8")
        return at + len(piece[:n].encode("utf-8"))

    def span(self, fs: int, fe: int) -> tuple[int, int]:
        """The byte range in the file that folded to `text[fs:fe]`, widened
        to whole segments."""
        i = self._piece(fs)
        start = (self.bstart[i] if self.kind[i] == _WHOLE
                 else self._byte(i, fs))
        j = self._piece(fe - 1)
        end = (self.bstart[j + 1] if self.kind[j] == _WHOLE
               else self._byte(j, fe))
        return start, end

    def line_of(self, offset: int) -> int:
        return self.data.count(b"\n", 0, offset) + 1

    def matches(self, needle: str):
        """Every non-overlapping match, in order, as folded positions."""
        at = self.text.find(needle)
        while at >= 0:
            yield at
            at = self.text.find(needle, at + len(needle))

    def spans(self, needle: str):
        """Every match as a DISTINCT span of bytes, in order: matches whose
        spans meet inside one segment are one, citing their union."""
        n, cur = len(needle), None
        for at in self.matches(needle):
            s, e = self.span(at, at + n)
            if cur is not None and s < cur[1]:
                cur = (cur[0], max(cur[1], e))
                continue
            if cur is not None:
                yield cur
            cur = (s, e)
        if cur is not None:
            yield cur

    def count(self, needle: str) -> tuple[int, int]:
        """(matches an excerpt can hold, matches too long for one)."""
        if not self.whole and len(needle) * 4 <= EXCERPT_BYTES:
            # one to one throughout: no span widens, so none can meet
            # another, and none outgrows an excerpt
            return self.text.count(needle), 0
        ok = over = 0
        for s, e in self.spans(needle):
            if e - s > EXCERPT_BYTES:
                over += 1
            else:
                ok += 1
        return ok, over

    def first(self, needle: str, n: int) -> list[tuple[int, int]]:
        """The first `n` matches an excerpt can hold."""
        out = []
        for s, e in self.spans(needle):
            if e - s <= EXCERPT_BYTES:
                out.append((s, e))
                if len(out) == n:
                    break
        return out


class _Cache:
    """Folded file versions, least recently used first, bounded by what
    each really holds (`Folded.cost`). One that alone exceeds the bound is
    not kept."""

    def __init__(self, cap: int):
        self.cap = cap
        self.held: collections.OrderedDict = collections.OrderedDict()
        self.size = 0
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            got = self.held.get(key)
            if got is not None:
                self.held.move_to_end(key)
            return got

    def put(self, key, value: Folded):
        with self.lock:
            if key in self.held or value.cost > self.cap:
                return
            self.held[key] = value
            self.size += value.cost
            while self.size > self.cap:
                _, old = self.held.popitem(last=False)
                self.size -= old.cost


_CACHE = _Cache(CACHE_BYTES)


def _load(root, digest) -> tuple[str, Folded | None]:
    """A verified file version, folded: ("present", Folded), or the state
    that kept it from being read -- `missing`, `corrupt` or `not-utf8`.

    VERIFIED THE WAY `reading.read` VERIFIES: sha256 against the digest
    before a byte is used. Kept by (digest, size, mtime), so a file that
    changes on disk is read and verified again."""
    try:
        st = held.path(root, digest).stat()
    except (FileNotFoundError, ValueError):
        return "missing", None
    key = (str(root), digest, st.st_size, st.st_mtime_ns)
    got = _CACHE.get(key)
    if got is not None:
        return "present", got
    state, data = held.state(root, digest, verify=True)
    if state != "present":
        return state, None
    try:
        got = Folded(data)
    except UnicodeDecodeError:
        return "not-utf8", None
    _CACHE.put(key, got)
    return "present", got


# -- what one query reads ------------------------------------------------------

def _phrase(q) -> str:
    if not isinstance(q, str) or not q.strip():
        raise Refused("search needs a phrase: an empty or whitespace-only "
                      "query is refused")
    q = q.strip()
    if len(q) > PHRASE_CHARS:
        raise Refused(f"a phrase is at most {PHRASE_CHARS} characters; this "
                      f"one is {len(q)}")
    return q


def _purged(corpus) -> set[str]:
    return {(lk.get("link") or {}).get("to")
            for lk in corpus.links(relation=held.PURGED)}


def _rep(root, digest: str, got) -> Folded:
    """A stored representation, folded, kept by its EXACT identity -- the
    source digest, the extractor id and the representation digest -- so
    two representations of one source never share an entry, and neither
    shares one with the source's own bytes."""
    key = ("representation", str(root), digest, got.extractor_id,
           got.representation_digest)
    f = _CACHE.get(key)
    if f is None:
        f = Folded(got.data)
        _CACHE.put(key, f)
    return f


# -- the walk, and where a slice of it starts -----------------------------------

def _state_of(corpus, d, items: dict, purged: set) -> dict:
    """Where the record stood for one collection, as far as a search reads
    it: its declaration, which Admission is latest for each object (the
    same fingerprint a plan is confirmed against), which of those are
    purged, its effective scope revision, and its machine binding token.
    Anything that would change what a search walks or reads changes this."""
    eff = effective_scope(corpus, d["collection"], d)
    scope_act = eff.get("act")
    bnd = bindings.binding(corpus, d["collection"])
    bnd_token = bnd.get("binding") if bnd else None
    decl_info = [d["name"], d["connector"], d.get("declaration")]
    adm_fp = fingerprint(items)
    purged_ids = sorted(e["id"] for e in items.values() if e["id"] in purged)
    purged_fp = hashlib.sha256(json.dumps(purged_ids).encode()).hexdigest()[:16]
    h = hashlib.sha256(json.dumps(
        [d["collection"], decl_info, scope_act, bnd_token, adm_fp, purged_ids],
        ensure_ascii=True).encode()).hexdigest()[:16]
    return {
        "h": h,
        "scope": scope_act,
        "bnd": bnd_token,
        "adm": adm_fp,
        "purged": purged_fp,
        "decl": decl_info,
    }


def _config_state() -> str:
    """Which extractors are configured for which payload types: not the
    record, but it decides what of each file is searched."""
    return hashlib.sha256(json.dumps(
        sorted((t, list(v)) for t, v in XC.CURRENT.items())
    ).encode()).hexdigest()[:16]


def _cost(e, o, purged: set) -> int:
    """What one object counts against a slice's budget: its RECORDED size
    when the scan would read its bytes -- text read directly, or a file
    with an extractor, whose source bytes are verified before an extraction
    of them is used -- and 0 when it reads nothing of it (no extractor, not
    held, purged). From the record alone, so where a slice ends depends on
    nothing else."""
    t = o.get("payload_type") or "unknown"
    if not ((o.get("encoding") or {}).get("text")
            or engine.has_extractor(t)):
        return 0
    if (e["body"].get("content") != "held"
            or not held.digest_of(e["body"].get("locator"))
            or e["id"] in purged):
        return 0
    return o.get("size") or 0


def _plan(corpus, collection: str | None) -> dict:
    """THE WALK: every present object in scope, in search order --
    collections by name casefolded then id, then key -- with what each
    costs, and where the record stood for each collection. Reads only the
    record. A slice is a run of it; a continuation names where the next
    run starts."""
    if collection:
        decls = [reading._collection(corpus, collection)]
    else:
        decls = sorted(declarations(corpus),
                       key=lambda d: (d["name"].casefold(), d["collection"]))
    purged = _purged(corpus)
    walk: list[tuple] = []
    latests: list[tuple] = []
    for di, d in enumerate(decls):
        items = latest(corpus, reading._source(d))
        latests.append((d, items))
        for key, e in sorted(items.items()):
            o = observation(e)
            if o.get("state") != "present":
                continue                    # recorded absent: nothing held
            walk.append((di, key, d, e, o, _cost(e, o, purged)))
    return {"decls": decls, "walk": walk, "latests": latests,
            "purged": purged, "corpus": corpus,
            "scope": decls[0]["collection"] if collection else None}


def _states(plan: dict) -> dict[str, dict]:
    """Where the record stood for each collection in the plan's scope --
    worked out only when a continuation is checked or given, never for an
    answer that needs neither (`find`, `#`)."""
    if "states" not in plan:
        corpus = plan["corpus"]
        plan["states"] = {d["collection"]: _state_of(corpus, d, items,
                                                     plan["purged"])
                          for d, items in plan["latests"]}
    return plan["states"]


def _prefix_hash(rows: list[tuple]) -> str:
    """A cryptographic fingerprint of the exact objects examined before
    a continuation slice, in order, from the record: their collection, key,
    and admission id. Any skipped, duplicated or reordered file changes this."""
    items = [[w[2]["collection"], w[1], w[3]["id"]] for w in rows]
    return hashlib.sha256(
        json.dumps(items, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def _start(plan, at, n: int = 1, pfx: str | None = None) -> int:
    """The first object of the walk at `at` (collection, key).
    Validates that `at` exists in the walk and matches the prefix of
    examined objects."""
    if at is None:
        return 0
    order = {d["collection"]: i for i, d in enumerate(plan["decls"])}
    if at[0] not in order:
        raise Refused(f"this continuation starts in {at[0]!r}, which is not "
                      "in this search's scope; search again from the start")
    walk = plan["walk"]
    keys = [(w[0], w[1]) for w in walk]
    target = (order[at[0]], at[1])
    idx = bisect.bisect_left(keys, target)
    if idx >= len(walk) or keys[idx] != target:
        raise Refused(f"this continuation starts at {at!r}, which is not "
                      "an object in this search's scope; search again from the start")
    if n > 1 and idx == 0:
        raise Refused(f"this continuation claims to be slice {n} but starts "
                      "at the first object in scope; search again from the start")
    if pfx is not None:
        expected_pfx = _prefix_hash(walk[:idx])
        if pfx != expected_pfx:
            raise Refused("this continuation does not match the objects "
                          "examined in this scope; search again from the start")
    return idx


def _scan(corpus, q: str, plan: dict, budget: int, start: int = 0,
          *, is_slice: bool = True) -> dict:
    """ONE SLICE of the walk, from object `start`: every searchable
    representation in it, in order, with how many times it matches, and
    everything that was not searched, counted. Reads only the record, the
    held store and the extraction store; `jobs` are the extractions it
    found missing.

    A SLICE READS AT MOST `budget` of what the walk costs (`_cost`). It
    stops BEFORE the object that would take it over, which the next slice
    starts with; an object that alone costs more than `budget` is never
    read -- no slice could hold it -- and is counted in
    `not_searched.over_slice`, so the walk always moves on and every slice
    is bounded. Where a slice ends is decided by the record alone, so the
    same slice is the same objects every time it is asked.

    When `is_slice` is False (`first_in_each`), budgets by what is actually
    scanned (scanned text + extraction bytes) without recorded-source charging,
    as on main 1492424f."""
    needle = fold(q)
    purged = plan["purged"]
    root = corpus.root
    walk = plan["walk"]
    files: list[dict] = []
    by_type: dict[str, int] = {}
    reasons: dict[str, dict[str, int]] = {}
    listed: list[dict] = []
    unreadable: list[dict] = []
    alone: list[dict] = []
    over_budget_files: list[dict] = []
    searched = {"files": 0, "bytes": 0, "extractions": 0,
                "extraction_bytes": 0}
    too_long: list[dict] = []
    jobs: list[tuple] = []
    truncated = None
    spent = 0
    stop = len(walk)

    def spent_bytes() -> int:
        return searched["bytes"] + searched["extraction_bytes"]

    def unsearched(t, reason, row=None, ext=None, why=None):
        reasons.setdefault(reason, {})
        reasons[reason][t] = reasons[reason].get(t, 0) + 1
        if row is not None and len(listed) < LIMIT_MAX:
            listed.append({
                "ref": row["entry"]["id"],
                "collection": row["decl"]["collection"], "key": row["key"],
                "payload_type": t, "state": reason,
                "extractor_id": ext.id if ext is not None else None,
                "why": why})

    for at in range(start, len(walk)):
        _, key, d, e, o, cost = walk[at]
        t = o.get("payload_type") or "unknown"
        text = bool((o.get("encoding") or {}).get("text"))
        extracted = engine.has_extractor(t)
        if not text and not extracted:
            by_type[t] = by_type.get(t, 0) + 1
            unsearched(t, "no_extractor")
            continue
        row = {"decl": d, "entry": e, "key": key}

        if not is_slice:
            # Main 1492424f budgeting: charge what is actually scanned
            if truncated is not None:
                over_budget_files.append(row)
                continue
            why = None
            digest = held.digest_of(e["body"].get("locator"))
            if e["body"].get("content") != "held" or not digest:
                why = "not held"
            elif e["id"] in purged:
                why = "purged"
            size = o.get("size") or 0
            if why is None and text and spent_bytes() + size > budget:
                truncated = {"collection": d["collection"], "key": key,
                             "budget_bytes": budget}
                over_budget_files.append(row)
                continue
            got = None
            if why is None:
                if text:
                    st, got = _load(root, digest)
                else:
                    st = engine.verified(root, digest)
                if st != "present":
                    why = st
            if why is not None:
                unreadable.append({"ref": e["id"],
                                   "collection": d["collection"],
                                   "key": key, "why": why})
                continue
            any_searched = False
            if text:
                any_searched = True
                searched["files"] += 1
                searched["bytes"] += len(got.data)
                n, long_ = got.count(needle)
                if long_:
                    too_long.append({"ref": e["id"],
                                     "collection": d["collection"],
                                     "key": key, "matches": long_})
                if n:
                    files.append({**row, "folded": got, "digest": digest,
                                  "count": n, "rep": None})
            exts = (engine.configured(t, engine.head(root, digest))
                    if extracted else [])
            if extracted and not exts and not text:
                unsearched(t, "no_extractor", row, None,
                           "no configured extractor accepts these bytes")
            for name, ext in exts:
                if ext is None:
                    unsearched(t, "unavailable", row, None,
                               f"{name} is configured but not registered "
                               "here")
                    continue
                st, rep, why = engine.state(root, digest, ext)
                if st in (engine.MISSING, engine.PENDING):
                    jobs.append((digest, ext))
                    unsearched(t, "extraction_pending", row, ext, why)
                    continue
                if st != "ok":
                    unsearched(t, st, row, ext, why)
                    continue
                if spent_bytes() + len(rep.data) > budget:
                    truncated = {"collection": d["collection"], "key": key,
                                 "extractor_id": ext.id,
                                 "budget_bytes": budget}
                    over_budget_files.append(row)
                    break
                f = _rep(root, digest, rep)
                any_searched = True
                searched["extractions"] += 1
                searched["extraction_bytes"] += len(rep.data)
                n, long_ = f.count(needle)
                if long_:
                    too_long.append({"ref": e["id"],
                                     "collection": d["collection"],
                                     "key": key, "matches": long_,
                                     "extractor_id": ext.id})
                if n:
                    files.append({**row, "folded": f, "digest": digest,
                                  "count": n, "rep": rep})
            if not text and not any_searched:
                by_type[t] = by_type.get(t, 0) + 1
            continue

        # Sliced continuation search (is_slice = True):
        # Slices must end ONLY at object boundaries.
        if cost > budget:
            alone.append({"ref": e["id"], "collection": d["collection"],
                          "key": key, "size": cost})
            continue
        if spent + cost > budget:
            truncated = {"collection": d["collection"], "key": key,
                         "budget_bytes": budget}
            stop = at
            break
        why = None
        digest = held.digest_of(e["body"].get("locator"))
        if e["body"].get("content") != "held" or not digest:
            why = "not held"
        elif e["id"] in purged:
            why = "purged"
        got = None
        if why is None:
            if text:
                st, got = _load(root, digest)
            else:
                st = engine.verified(root, digest)
            if st != "present":
                why = st
        if why is not None:
            unreadable.append({"ref": e["id"],
                               "collection": d["collection"],
                               "key": key, "why": why})
            continue
        exts = (engine.configured(t, engine.head(root, digest))
                if extracted else [])
        if extracted and not exts and not text:
            unsearched(t, "no_extractor", row, None,
                       "no configured extractor accepts these bytes")

        # Determine all ready searchable representations before searching
        ready_exts = []
        for name, ext in exts:
            if ext is None:
                continue
            st_ext, rep, why_ext = engine.state(root, digest, ext)
            if st_ext == "ok":
                ready_exts.append((name, ext, rep))

        text_len = len(got.data) if (text and got is not None) else 0
        obj_bytes = text_len + sum(len(rep.data) for _, _, rep in ready_exts)

        if obj_bytes > budget:
            item = {"ref": e["id"], "collection": d["collection"],
                    "key": key, "size": obj_bytes}
            if not text and len(ready_exts) == 1:
                item["extractor_id"] = ready_exts[0][1].id
            alone.append(item)
            continue

        if spent_bytes() + obj_bytes > budget and spent_bytes() > 0:
            truncated = {"collection": d["collection"], "key": key,
                         "budget_bytes": budget}
            stop = at
            break

        # Object fits completely in this slice
        spent += cost
        any_searched = False
        if text:
            any_searched = True
            searched["files"] += 1
            searched["bytes"] += text_len
            n, long_ = got.count(needle)
            if long_:
                too_long.append({"ref": e["id"],
                                 "collection": d["collection"],
                                 "key": key, "matches": long_})
            if n:
                files.append({**row, "folded": got, "digest": digest,
                              "count": n, "rep": None})

        for name, ext in exts:
            if ext is None:
                unsearched(t, "unavailable", row, None,
                           f"{name} is configured but not registered "
                           "here")
                continue
            st_ext, rep, why_ext = engine.state(root, digest, ext)
            if st_ext in (engine.MISSING, engine.PENDING):
                jobs.append((digest, ext))
                unsearched(t, "extraction_pending", row, ext, why_ext)
                continue
            if st_ext != "ok":
                unsearched(t, st_ext, row, ext, why_ext)
                continue
            f = _rep(root, digest, rep)
            any_searched = True
            searched["extractions"] += 1
            searched["extraction_bytes"] += len(rep.data)
            n, long_ = f.count(needle)
            if long_:
                too_long.append({"ref": e["id"],
                                 "collection": d["collection"],
                                 "key": key, "matches": long_,
                                 "extractor_id": ext.id})
            if n:
                files.append({**row, "folded": f, "digest": digest,
                              "count": n, "rep": rep})
        if not text and not any_searched:
            by_type[t] = by_type.get(t, 0) + 1

    if not is_slice:
        return {"needle": needle, "files": files, "searched": searched,
                "too_long": too_long, "jobs": jobs,
                "not_searched": {
                    "non_text": sum(by_type.values()),
                    "by_type": dict(sorted(by_type.items())),
                    "extraction": {r: dict(sorted(v.items()))
                                   for r, v in sorted(reasons.items())},
                    "extraction_files": listed,
                    "unreadable": len(unreadable),
                    "unreadable_files": unreadable[:LIMIT_MAX],
                    "over_budget": len(over_budget_files)},
                "truncated": truncated, "start": start, "stop": len(walk),
                "spent": spent_bytes()}

    # what the slice did not reach: the searchable objects after it
    over = sum(1 for w in walk[stop:]
               if (w[4].get("encoding") or {}).get("text")
               or engine.has_extractor(w[4].get("payload_type") or "unknown"))
    return {"needle": needle, "files": files, "searched": searched,
            "too_long": too_long, "jobs": jobs,
            "not_searched": {
                "non_text": sum(by_type.values()),
                "by_type": dict(sorted(by_type.items())),
                "extraction": {r: dict(sorted(v.items()))
                               for r, v in sorted(reasons.items())},
                "extraction_files": listed,
                "unreadable": len(unreadable),
                "unreadable_files": unreadable[:LIMIT_MAX],
                "over_slice": len(alone),
                "over_slice_files": alone[:LIMIT_MAX],
                "over_budget": over},
            "truncated": truncated, "start": start, "stop": stop,
            "spent": spent_bytes()}


def _scan_waiting(corpus, q, plan, budget, wait, start=0,
                  *, is_slice: bool = True) -> dict:
    """`_scan`; if it found extractions missing, make them in the
    background, wait for them up to `wait` seconds and scan again. Whatever
    is still being made is reported as pending (C2: on demand at first
    search). Both scans are of the same slice of the same plan."""
    s = _scan(corpus, q, plan, budget, start, is_slice=is_slice)
    if s["jobs"]:
        engine.schedule(corpus.root, s["jobs"])
        if wait and wait > 0:
            engine.wait(corpus.root, s["jobs"], wait)
            s = _scan(corpus, q, plan, budget, start, is_slice=is_slice)
            if s["jobs"]:
                engine.schedule(corpus.root, s["jobs"])
    return s


# -- continuing a search ----------------------------------------------------------

#: What a continuation starts with; any other is refused, never guessed at.
TOKEN = "srch1."

_AUTH_KEY = secrets.token_bytes(32)


def _sign(body_dict: dict) -> str:
    clean = {k: v for k, v in body_dict.items() if k != "sig"}
    raw = json.dumps(clean, ensure_ascii=True, separators=(",", ":"),
                     sort_keys=True).encode("ascii")
    return hmac.new(_AUTH_KEY, raw, hashlib.sha256).hexdigest()[:16]


def _qid(q: str) -> str:
    return hashlib.sha256(fold(q).encode("utf-8")).hexdigest()[:16]


def _token(body: dict) -> str:
    body = dict(body)
    body["sig"] = _sign(body)
    raw = json.dumps(body, ensure_ascii=True, separators=(",", ":"),
                     sort_keys=True).encode("ascii")
    return TOKEN + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _untoken(tok) -> dict:
    bad = Refused("that continuation is not one this search gave: pass the "
                  "`continuation` of the last answer exactly, or search "
                  "again from the start")
    if not isinstance(tok, str) or not tok.startswith(TOKEN):
        raise bad
    raw = tok[len(TOKEN):]
    try:
        body = json.loads(base64.urlsafe_b64decode(
            raw + "=" * (-len(raw) % 4)).decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        raise bad from None
    if not (isinstance(body, dict) and body.get("v") == 1
            and isinstance(body.get("at"), list) and len(body["at"]) == 2
            and all(isinstance(x, str) for x in body["at"])
            and isinstance(body.get("fp"), dict)
            and all(isinstance(body.get(k), int) and body[k] >= 0
                    for k in ("n", "m", "u"))):
        raise bad
    sig = body.get("sig")
    if not isinstance(sig, str) or not hmac.compare_digest(sig, _sign(body)):
        raise Refused("that continuation is not one this server can verify: "
                      "it was issued by another server process or before a "
                      "restart, or was altered; search again from the start")
    return body


def _check(prior: dict, q: str, plan: dict) -> None:
    """A continuation is of THIS search, over THIS state of the record --
    else it is refused, saying exactly what moved. Never a slice of one
    state of the record joined to slices of another."""
    if prior.get("q") != _qid(q):
        raise Refused("this continuation belongs to a search for another "
                      "phrase; search for this one from the start")
    if prior.get("c") != plan["scope"]:
        raise Refused("this continuation belongs to a search of "
                      f"{'collection ' + repr(prior.get('c')) if prior.get('c') else 'every collection'}"
                      f", not of {'collection ' + repr(plan['scope']) if plan['scope'] else 'every collection'}"
                      "; search again from the start")
    then, now = prior["fp"], _states(plan)
    names = {d["collection"]: d["name"] for d in plan["decls"]}

    def said(cols):
        return ", ".join(f"{names.get(c, c)!r} ({c})" if c in names
                         else repr(c) for c in sorted(cols))

    moved = []
    changed = [c for c in now if c in then and (
        (then[c].get("h") if isinstance(then[c], dict) else then[c])
        != (now[c].get("h") if isinstance(now[c], dict) else now[c])
    )]
    for c in sorted(changed):
        then_c = then[c]
        now_c = now[c]
        if isinstance(then_c, dict) and isinstance(now_c, dict):
            c_moved = []
            if then_c.get("scope") != now_c.get("scope"):
                c_moved.append(f"a scope revision in {said([c])}")
            if then_c.get("bnd") != now_c.get("bnd"):
                c_moved.append(f"a binding change in {said([c])}")
            if then_c.get("adm") != now_c.get("adm"):
                c_moved.append(f"new observations in {said([c])}")
            if then_c.get("purged") != now_c.get("purged"):
                c_moved.append(f"a purge in {said([c])}")
            if then_c.get("decl") != now_c.get("decl"):
                c_moved.append(f"a changed declaration in {said([c])}")
            if c_moved:
                moved.extend(c_moved)
            else:
                moved.append(f"a record change in {said([c])}")
        else:
            moved.append(f"new observations, a purge or a changed declaration in {said([c])}")
    if set(now) - set(then):
        moved.append(f"declared since: {said(set(now) - set(then))}")
    if set(then) - set(now):
        moved.append(f"no longer declared: {said(set(then) - set(now))}")
    if prior.get("x") != _config_state():
        moved.append("the extractors configured for search changed")
    if moved:
        raise Refused(
            "the record changed since this search began, so its next slice "
            "would be of a different state than the slices before it: "
            + "; ".join(moved) + ". Nothing was searched; search again from "
            "the start to search the record as it is now")


def _coverage(plan: dict, s: dict, prior: dict | None, matches: int,
              unsearched: int) -> dict:
    """HOW MUCH OF THE SCOPE HAS BEEN EXAMINED, from the record: objects
    and the bytes the scan budget counts, before this slice, in it, and
    after it. `complete` only when the walk reached its end; until then the
    answer is partial and says so, matches or none."""
    walk, a, z = plan["walk"], s["start"], s["stop"]

    def part(rows):
        return {"objects": len(rows), "bytes": sum(w[5] for w in rows)}

    total, before, here, rest = (part(walk), part(walk[:a]),
                                 part(walk[a:z]), part(walk[z:]))
    done = {"objects": before["objects"] + here["objects"],
            "bytes": before["bytes"] + here["bytes"]}
    complete = z >= len(walk)
    m0 = prior["m"] if prior else 0
    u0 = prior["u"] if prior else 0
    so_far = m0 + matches
    n = prior["n"] if prior else 1
    if complete and u0 + unsearched == 0:
        said = (f"complete: every one of the {total['objects']} objects in "
                "scope was examined and searched"
                + (f"; {so_far} matches in all" if so_far
                   else "; the phrase occurs nowhere in them"))
    elif complete:
        said = (f"complete: every one of the {total['objects']} objects in "
                "scope was reached, but not everything in them could be "
                "searched -- see not_searched in each slice. "
                + (f"{so_far} matches in what was searched"
                   if so_far else "No match in what was searched; that is "
                   "not a finding that the phrase is absent from what was "
                   "not"))
    else:
        said = (f"PARTIAL, not exhaustive: {done['objects']} of "
                f"{total['objects']} objects examined ({done['bytes']} of "
                f"{total['bytes']} bytes); {rest['objects']} objects "
                f"({rest['bytes']} bytes) not yet examined. "
                + (f"{so_far} matches so far" if so_far else
                   "No match so far -- the rest has not been searched")
                + ". Continue with `continuation` to search the rest")
    return {"complete": complete,
            "exhaustive": complete and u0 + unsearched == 0,
            "slice": n, "total": total, "before_this_slice": before,
            "this_slice": here, "examined": done, "remaining": rest,
            "matches_so_far": so_far, "matches_before_this_slice": m0,
            "unit": "objects: the present objects in scope, each reached "
                    "in search order whether searched or counted in "
                    "not_searched; bytes: the recorded size of those whose "
                    "bytes a search reads -- what the scan budget counts",
            "said": said}


def _unsearched(ns: dict) -> int:
    """How many things in one slice were not searched, for `exhaustive`."""
    return (ns["non_text"] + ns["unreadable"] + ns["over_slice"]
            + sum(n for r, v in ns["extraction"].items()
                  if r != "no_extractor" for n in v.values()))


def _excerpt(f: Folded, start: int, end: int) -> tuple[int, int]:
    """About `CONTEXT_LINES` lines either side of `[start, end)`, at most
    `EXCERPT_BYTES`, starting and ending on character boundaries. Cut to
    the cap, it keeps the match and as much either side as fits."""
    data = f.data
    lo = data.rfind(b"\n", 0, start) + 1              # the match's line
    for _ in range(CONTEXT_LINES):
        if lo == 0:
            break
        lo = data.rfind(b"\n", 0, lo - 1) + 1
    hi = end
    for _ in range(CONTEXT_LINES + 1):
        nl = data.find(b"\n", hi)
        if nl < 0:
            hi = len(data)
            break
        hi = nl + 1
    if hi - lo > EXCERPT_BYTES:
        if end - start >= EXCERPT_BYTES:
            lo, hi = start, start + EXCERPT_BYTES
        else:
            room = EXCERPT_BYTES - (end - start)
            before = min(start - lo, room // 2)
            after = min(hi - end, room - before)
            before = min(start - lo, room - after)
            lo, hi = start - before, end + after
    # inward to whole characters: never inside a UTF-8 sequence
    while lo < start and (data[lo] & 0xC0) == 0x80:
        lo += 1
    while hi < len(data) and hi > lo + 1 and (data[hi] & 0xC0) == 0x80:
        hi -= 1
    return lo, hi


def _snippet(f: Folded, start: int, end: int) -> str:
    """At most `SNIPPET_CHARS` characters around the match, on one line."""
    data = f.data
    match = data[start:end].decode("utf-8")
    room = SNIPPET_CHARS - 2 - len(match)
    if room <= 0:
        out = match[:SNIPPET_CHARS - 1] + "…"
    else:
        before = data[max(0, start - 4 * room):start].decode("utf-8", "ignore")
        after = data[end:end + 4 * room].decode("utf-8", "ignore")
        b = before[len(before) - min(len(before), room // 2):]
        a = after[:room - len(b)]
        out = (("…" if len(b) < len(before) else "") + b + match + a
               + ("…" if len(a) < len(after) else ""))
    return " ".join(out.split())


class _Embeds:
    """What each embed in an excerpt is, from the record (G2) -- the same
    words `links` and `rendered` use -- worked out once per collection."""

    def __init__(self, corpus):
        self.corpus = corpus
        self.status: dict[str, object] = {}

    def __call__(self, d, e, f: Folded, lo: int, hi: int) -> list[dict]:
        from mentis import artifacts
        try:
            mod = registry._module(d["connector"])
        except Refused:
            return []
        find = getattr(mod, "embeds_in", None)
        if find is None:
            return []
        rels = [r for r in observation(e).get("relations") or ()
                if r.get("rel") == "embeds"]
        if d["collection"] not in self.status:
            self.status[d["collection"]] = reading._target_status(
                self.corpus, d, reading._latest(self.corpus, d))
        status = self.status[d["collection"]]
        used: set[int] = set()
        out = []
        for m in find(f.data, lo, hi):
            i = next((j for j, r in enumerate(rels) if j not in used
                      and r.get("syntax") == m["syntax"]
                      and r.get("authored") == m["authored"]), None)
            if i is None:
                out.append({**m, "target": reading.NOT_RESOLVED})
                continue
            used.add(i)
            r = rels[i]
            row = {**m, "resolved": r.get("resolved"), **status(r)}
            if row.get("target") == reading.ACQUIRED:
                t = artifacts.describe(self.corpus, row["target_ref"],
                                       verify=False)
                row["state"] = t["state"]
                got = (artifacts.sniffed(self.corpus, t.get("digest"))
                       if t["state"] == "held" else None)
                row["view"] = got["view"] if got else None
            out.append(row)
        return out


def _cp(f: Folded, b: int) -> int:
    """The code point at byte `b` of a representation's UTF-8."""
    return len(f.data[:b].decode("utf-8"))


def _hit(corpus, row, k: int, span: tuple[int, int], embeds) -> dict:
    d, e, f, rep = row["decl"], row["entry"], row["folded"], row["rep"]
    start, end = span
    lo, hi = _excerpt(f, start, end)
    out = {"ref": e["id"], "collection": d["collection"],
           "collection_name": d["name"], "key": row["key"],
           "label": reading._label(d, row["key"], observation(e)),
           "digest": row["digest"], "source_digest": row["digest"],
           "snippet": _snippet(f, start, end),
           "match": {"n": k + 1, "of": row["count"]},
           "more_in_file": row["count"] - min(row["count"], PER_FILE)}
    if rep is None:
        # THE FILE'S OWN BYTES: byte offsets, the direct cite (C0, A).
        out.update(extraction=None, unit="byte", offset=start, end=end,
                   line=f.line_of(start),
                   excerpt={"offset": lo, "length": hi - lo, "unit": "byte",
                            "cite": C.direct(e["id"], row["digest"], lo,
                                             hi)},
                   cite=C.direct(e["id"], row["digest"], start, end),
                   embeds_in_excerpt=embeds(d, e, f, lo, hi))
        return out
    # AN EXTRACTION: code points in exactly this representation (C3).
    s, t, xlo, xhi = (_cp(f, start), _cp(f, end), _cp(f, lo), _cp(f, hi))
    where = engine.locate(rep, s, t)
    out.update(extraction={"extractor_id": rep.extractor_id,
                           "representation_digest":
                               rep.representation_digest,
                           "map_digest": rep.manifest["map_digest"],
                           "locator_scheme": rep.manifest["locator_scheme"]},
               unit="codepoint", offset=s, end=t, line=None,
               loc=where["loc"], display=where["display"],
               excerpt={"offset": xlo, "length": xhi - xlo,
                        "unit": "codepoint",
                        "cite": engine.cite(e["id"], row["digest"], rep,
                                            xlo, xhi)},
               cite=C.extracted(e["id"], row["digest"], rep.extractor_id,
                                rep.representation_digest, s, t,
                                where["scheme"], where["token"]),
               embeds_in_excerpt=[])
    return out


def search(corpus, q, *, collection: str | None = None, offset: int = 0,
           limit: int = LIMIT, budget: int = BUDGET,
           wait: float | None = None,
           continuation: str | None = None) -> dict:
    """One window of one slice of the places a phrase occurs in acquired text
    (A1, C3; Stage F). Without `continuation`, the first slice; with the
    `continuation` an answer gave, the next -- refused if the record moved
    in between. `offset` pages through the hits of the slice it is given
    with; `next` is exactly what to ask for after this answer."""
    q = _phrase(q)
    offset = max(0, int(offset or 0))
    limit = max(1, min(int(limit or LIMIT), LIMIT_MAX))
    prior = _untoken(continuation) if continuation else None
    plan = _plan(corpus, collection)
    if prior is not None:
        _check(prior, q, plan)
    start = _start(plan, prior["at"] if prior else None,
                   n=prior.get("n", 1) if prior else 1,
                   pfx=prior.get("pfx") if prior else None)
    s = _scan_waiting(corpus, q, plan, budget,
                      engine.WAIT if wait is None else wait, start)
    files, needle = s["files"], s["needle"]
    # H, in order: the first PER_FILE of each file. An answer is a slice.
    every = [(i, k) for i, row in enumerate(files)
             for k in range(min(row["count"], PER_FILE))]
    window = every[offset:offset + limit]
    nxt = offset + limit if offset + limit < len(every) else None
    spans = {i: files[i]["folded"].first(needle, PER_FILE)
             for i in {i for i, _ in window}}
    embeds = _Embeds(corpus)
    hits = [_hit(corpus, files[i], k, spans[i][k], embeds)
            for i, k in window]
    beyond = sum(r["count"] for r in files) - len(every)
    too_long = sum(t["matches"] for t in s["too_long"])
    total = len(every) + beyond + too_long
    unsearched = _unsearched(s["not_searched"])
    coverage = _coverage(plan, s, prior, total, unsearched)
    more = None
    if not coverage["complete"]:
        w = plan["walk"][s["stop"]]
        more = _token({"v": 1, "q": _qid(q), "c": plan["scope"],
                       "at": [w[2]["collection"], w[1]],
                       "pfx": _prefix_hash(plan["walk"][:s["stop"]]),
                       "fp": _states(plan), "x": _config_state(),
                       "n": coverage["slice"] + 1,
                       "m": coverage["matches_so_far"],
                       "u": (prior["u"] if prior else 0) + unsearched})
    following = ({"continuation": continuation, "offset": nxt}
                 if nxt is not None else
                 {"continuation": more, "offset": 0} if more else None)
    return {"q": q, "collection": collection, "hits": hits,
            "hits_total": len(every),
            "total_matches": total,
            "files_with_hits": len({r["entry"]["id"] for r in files}),
            "not_returned": {"beyond_per_file": beyond,
                             "over_excerpt": too_long,
                             "over_excerpt_files": s["too_long"][:LIMIT_MAX]},
            "offset": offset, "limit": limit, "next_offset": nxt,
            "searched": s["searched"], "not_searched": s["not_searched"],
            "truncated": s["truncated"] is not None,
            "stopped_at": s["truncated"],
            "coverage": coverage,
            "continuation": more,
            "next": following,
            "slice": {"n": coverage["slice"], "continuation": continuation,
                      "budget_bytes": budget},
            "matching": "literal phrase; Unicode casefold and NFC on both "
                        "sides; no regex or wildcards. Matches do not "
                        "overlap; one inside a character that folds to "
                        "several (ß, ﬁ) cites that whole character, and "
                        "matches citing the same bytes are one",
            "order": f"the first {PER_FILE} matches of each representation "
                     "of each file, by position; files by collection "
                     "(name, casefolded), then key; a file's own bytes "
                     "before its extractions. Further matches are counted "
                     "in more_in_file, not returned: read on from the cite "
                     "with read_source. next_offset pages through this "
                     "slice's hits, each once (ask with the same "
                     "continuation); `continuation` starts the next slice, "
                     "and `next` is exactly what to ask for after this "
                     "answer. A match longer than an excerpt is "
                     "counted in not_returned.over_excerpt",
            "note": "the latest present observation of each acquired file, "
                    "read from the held bytes and verified -- never the "
                    "live folder -- or from an extraction of them. A hit's "
                    "`unit` says what its offsets count: `byte` in the "
                    "stored file, read with read_source(ref, "
                    "offset=excerpt.offset, length=excerpt.length); "
                    "`codepoint` in the extraction it names, read with "
                    "read_source(ref, offset=excerpt.offset, "
                    "length=excerpt.length, extraction=<extractor_id>). "
                    "Either returns the excerpt exactly"}


def first_in_each(corpus, q, *, budget: int = BUDGET,
                  wait: float = 0.0) -> dict:
    """The first hit of each file that has one, for `find` and `#` (A2): at
    most one per file, with how many there were.

    IT NEVER WAITS FOR AN EXTRACTION. It serves every `#` keystroke and every
    agent's `find`, so a missing extraction is started in the background
    and reported at once in `not_searched.extraction.extraction_pending`;
    the next `find`, or a `search_sources` (which does wait, a bounded
    time), sees it once it is made."""
    q = _phrase(q)
    s = _scan_waiting(corpus, q, _plan(corpus, None), budget, wait,
                      is_slice=False)
    embeds = lambda *a: []                                 # noqa: E731
    hits, seen = [], set()
    for row in s["files"]:
        if row["entry"]["id"] in seen:
            continue
        seen.add(row["entry"]["id"])
        h = _hit(corpus, row, 0, row["folded"].first(s["needle"], 1)[0],
                 embeds)
        h.pop("embeds_in_excerpt")
        hits.append(h)
    return {"hits": hits, "searched": s["searched"],
            "not_searched": s["not_searched"],
            "truncated": s["truncated"] is not None}
