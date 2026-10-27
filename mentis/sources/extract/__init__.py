"""Source extraction kept beside the corpus: the contract (Sources C, C1).

SPEC `adm-6a79371b5763` (revision 2, approved by the owner with the scope
correction: a source extraction capability, not one format's).
Everything in this package except the first adapter module and the
configuration entry that names it is FORMAT-NEUTRAL: it
stores, digests and returns locations, and asks a registered locator scheme
what one means. It never reads a field of a location itself.

WHAT AN EXTRACTION IS. Derived material beside the corpus (R1), never a
corpus post: one linear text representation of one source's exact retained
bytes, made by one declared extractor, with an origin map from code-point
spans of that text back to places in the source. It is keyed by the source
content digest and the extractor's identity (R2), lives under
`<brain>/derived/extractions/` (`store`), and can be deleted at any time and
made again identically (R6, C1.6).

TEXT SOURCES GET NONE (C0). A source whose stored bytes are text --
`encoding.text`, decided at acquisition -- is read and searched directly,
cited by its own bytes, and nothing is written here for it. There is no
"identity extractor". Which payload types have an extractor at all is
configuration (`config.CURRENT`), so a later text format may be given one
(HTML visible text, say) and its raw bytes stay searchable beside it.

THE CONTRACT. Every extractor declares:

  name            e.g. `docx-text`, `html-visible`, `xlsx-cells`
  version         the extractor's own version
  options         every setting that affects its output
  deps            pinned versions of every library that affects its output
  accepts         payload types, and byte signatures, it handles
  locator_scheme  `name/version` of the scheme its map's locations use
  extract(bytes, options) -> (text, map, status), deterministic
  installed()     the versions of `deps` present in this process

`extractor_id = name@version+<hash(options, deps)>` (`identity`). The hash
input is canonical JSON -- sorted keys, fixed separators -- of the options
and of the deps, which always include the Unicode version this process
normalises with (`NORMALISATION`), because the core's NFC is part of every
representation. Changing any of them is a new id beside the old one.

AN IDENTITY OWNS ITS INPUTS. An `Extractor` takes a private deep snapshot
of its options and deps when it is made (a canonical JSON round trip, which
also refuses anything that is not JSON) and computes its id from that
snapshot at once. A caller's dict edited later, a variant made with
`dataclasses.replace` from a shallow copy, or an `extract` callback that
edits the options it is handed (a fresh deep copy every time) cannot change
what an existing id means. `intact()` recomputes the id from what the
extractor now holds; one that is not intact is never registered and never
run.

A RUNNABLE EXTRACTOR IS EXACTLY ITS DECLARED IDENTITY. `runnable()` refuses
one that is not intact, and one whose installed libraries differ from what
it declares: a changed library is never run under an old id.

AN ERROR OF THE ENVIRONMENT IS NOT AN OUTPUT. An extractor raises
`Transient` -- or the process raises `MemoryError`, `OSError`,
`RecursionError` or `ImportError` (`TRANSIENT`) -- when the failure says
something about this process rather than about these bytes under this
identity. Such a failure is never stored; anything else an extractor
raises on the bytes is its deterministic `failed:` output.

THE REPRESENTATION (C1.1): UTF-8, NFC, `\\n` line ends, and nothing else --
one linear text; structure belongs in the map. Its status is `ok`,
`empty: <reason>` or `failed: <reason>`, and an empty or failed one is
reported, never hidden.

THE MAP (C1.2): spans `{start, end, loc}` in CODE POINTS of the text,
contiguous and in order from 0 to its length; a span may be empty (`start ==
end`), which is how an origin with no text is kept in order. `loc` is
validated against the scheme's declared schema (`check_loc`) and otherwise
passed through untouched. `assemble` builds text and map from (raw text,
loc) pieces and normalises each piece by itself, so a span's offsets are
offsets in the normalised text; a normalisation that would join text across
two spans is refused as a failure, never silently re-aligned.

LOCATOR SCHEMES (C1.3) register `name/version`, a JSON schema for `loc`,
`display(loc)` (for people), `token(loc)` (compact, for citations, no
whitespace or braces), `span(first, last)` (a location covering a range that
crosses spans) and `narrow(loc, lo, hi, length)` (the location of part of
one span; the default is the span's own).
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

#: What the core's normalisation depends on. Part of every extractor's
#: identity: a different Unicode version can normalise differently.
NORMALISATION = {"unicodedata": unicodedata.unidata_version}

_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.-]*$")
_SCHEME = re.compile(r"^[a-z0-9][a-z0-9.-]*/[0-9]+$")
#: An extractor id: `name@version+hash12`.
ID = r"[a-z0-9][a-z0-9.-]*@[0-9A-Za-z][0-9A-Za-z.-]*\+[0-9a-f]{12}"
_ID = re.compile(f"^{ID}$")
#: What a token may not hold, so a citation can be found in running text.
_TOKEN_BAD = re.compile(r"[\s{}]")

OK = "ok"
EMPTY = "empty"
FAILED = "failed"


class Unavailable(LookupError):
    """This extractor identity cannot be run here, and says why."""


class Transient(Unavailable):
    """This extraction could not be made just now, for a reason of this
    process or machine rather than of the bytes: not stored, tried again
    later. An extractor may raise it itself."""


#: Exceptions that say something about the environment, not the bytes.
TRANSIENT = (Transient, MemoryError, OSError, RecursionError, ImportError)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def kind_of(status: str) -> str:
    """`ok`, `empty` or `failed`: the word before any reason."""
    return status.split(":", 1)[0].strip()


# -- locator schemes ------------------------------------------------------------

def _same(loc, lo, hi, length):
    return loc


@dataclass(frozen=True)
class Scheme:
    name: str
    schema: dict
    display: Callable[[dict], str]
    token: Callable[[dict], str]
    span: Callable[[dict, dict], dict]
    narrow: Callable[[dict, int, int, int], dict] = _same


_TYPES = {"object": dict, "integer": int, "string": str, "array": list,
          "boolean": bool, "number": (int, float)}


def _valid(value, schema: dict, where: str) -> str | None:
    """The subset of JSON Schema a locator schema may use: `type`,
    `properties`, `required`, `additionalProperties: false`, `items`,
    `minimum`. Why `value` does not satisfy it, or None."""
    t = schema.get("type")
    if t is not None:
        py = _TYPES.get(t)
        if py is None:
            return f"{where}: unknown type {t!r} in the scheme's schema"
        if isinstance(value, bool) and t in ("integer", "number"):
            return f"{where} is a boolean, not {t}"
        if not isinstance(value, py):
            return f"{where} is {type(value).__name__}, not {t}"
    if "minimum" in schema and isinstance(value, (int, float)) \
            and value < schema["minimum"]:
        return f"{where} is below {schema['minimum']}"
    if isinstance(value, dict):
        props = schema.get("properties") or {}
        for k in schema.get("required") or ():
            if k not in value:
                return f"{where} lacks {k!r}"
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(props))
            if extra:
                return f"{where} has fields the scheme does not: {extra}"
        for k, sub in props.items():
            if k in value:
                why = _valid(value[k], sub, f"{where}.{k}")
                if why:
                    return why
    if isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            why = _valid(v, schema["items"], f"{where}[{i}]")
            if why:
                return why
    return None


# -- extractors -----------------------------------------------------------------

@dataclass(frozen=True)
class Extractor:
    name: str
    version: str
    options: dict
    deps: dict
    accepts: tuple
    locator_scheme: str
    extract: Callable[[bytes, dict], tuple]
    installed: Callable[[], dict]
    #: byte prefixes the payload must start with; empty accepts any
    signatures: tuple = ()
    licence: str = ""
    #: Always computed here; a value passed in (`dataclasses.replace` hands
    #: on the original's) is ignored.
    _id: object = field(default="", compare=False, repr=False)

    def __post_init__(self):
        # A PRIVATE DEEP SNAPSHOT, and the id computed from it now: nothing
        # the caller still holds -- nor the module dict a variant was copied
        # from -- shares an object with what this id was computed from.
        for f in ("options", "deps"):
            object.__setattr__(self, f, snapshot(getattr(self, f)))
        object.__setattr__(self, "_id", identity(
            self.name, self.version, self.options, self.all_deps))

    @property
    def all_deps(self) -> dict:
        return {**self.deps, **NORMALISATION}

    @property
    def id(self) -> str:
        return self._id

    def intact(self) -> bool:
        """What it holds still hashes to its id."""
        try:
            return identity(self.name, self.version, self.options,
                            self.all_deps) == self._id
        except (TypeError, ValueError):
            return False

    def options_copy(self) -> dict:
        """A fresh deep copy of its options, for one run of `extract`."""
        return snapshot(self.options)

    def takes(self, payload_type: str | None, head: bytes) -> bool:
        if payload_type not in self.accepts:
            return False
        return not self.signatures or any(head.startswith(s)
                                          for s in self.signatures)


def snapshot(value: dict) -> dict:
    """A deep copy that shares nothing with `value`, through canonical JSON:
    exactly what the identity hashes. Refuses what is not a JSON object."""
    if not isinstance(value, dict):
        raise TypeError(f"options and deps are JSON objects, not "
                        f"{type(value).__name__}")
    return json.loads(canonical(value))


def identity(name: str, version: str, options: dict, deps: dict) -> str:
    """`name@version+<hash(options, deps)>`, over canonical JSON."""
    h = sha256(canonical({"deps": deps, "options": options}).encode("utf-8"))
    return f"{name}@{version}+{h[:12]}"


_LOCK = threading.Lock()
#: Every registered identity, current or not: an old one stays runnable
#: for its citations for as long as it is registered.
_BY_ID: dict[str, Extractor] = {}
#: The current identity of each name.
_CURRENT: dict[str, str] = {}
_SCHEMES: dict[str, Scheme] = {}


def register_scheme(s: Scheme) -> Scheme:
    if not _SCHEME.match(s.name):
        raise ValueError(f"a locator scheme is `name/version`, not {s.name!r}")
    with _LOCK:
        _SCHEMES[s.name] = s
    return s


def register(ext: Extractor, *, current: bool = True) -> Extractor:
    """Register an extractor identity. With `current`, it becomes the one
    its name means from now on; an earlier identity of that name stays
    registered, beside it, and is never overwritten."""
    if not _NAME.match(ext.name) or not _VERSION.match(ext.version):
        raise ValueError(f"not an extractor name and version: "
                         f"{ext.name!r} {ext.version!r}")
    if ext.locator_scheme not in _SCHEMES:
        raise ValueError(f"{ext.name} uses {ext.locator_scheme!r}, which is "
                         "not a registered locator scheme")
    if not ext.intact():
        raise ValueError(f"{ext.id}: its options or deps no longer hash to "
                         "its id")
    with _LOCK:
        was = _BY_ID.get(ext.id)
        if was is not None and was != ext:
            raise ValueError(f"{ext.id} is already registered as something "
                             "else; an identity is never redefined")
        _BY_ID[ext.id] = ext
        if current:
            _CURRENT[ext.name] = ext.id
    return ext


def unregister(extractor_id: str) -> None:
    """Retire an identity in this process (tests; a release note in life)."""
    with _LOCK:
        ext = _BY_ID.pop(extractor_id, None)
        if ext is not None and _CURRENT.get(ext.name) == extractor_id:
            _CURRENT.pop(ext.name)


def by_id(extractor_id: str) -> Extractor | None:
    return _BY_ID.get(extractor_id)


def current(name: str) -> Extractor | None:
    i = _CURRENT.get(name)
    return _BY_ID.get(i) if i else None


def scheme(name: str) -> Scheme | None:
    return _SCHEMES.get(name)


def runnable(ext: Extractor | None) -> str | None:
    """Why this identity cannot be run here, or None. What it holds must
    still hash to its id, and its installed libraries must be exactly the
    versions its identity declares."""
    if ext is None:
        return "this extractor is not registered here"
    if not ext.intact():
        return ("its options or deps no longer hash to its id; an identity "
                "is never run with inputs other than its own")
    try:
        have = {**ext.installed(), **NORMALISATION}
    except Exception as exc:                              # noqa: BLE001
        return f"its libraries cannot be inspected: {exc}"
    want = ext.all_deps
    off = {k: {"declared": v, "installed": have.get(k)}
           for k, v in want.items() if have.get(k) != v}
    if off:
        return f"installed libraries differ from its declared identity: {off}"
    return None


def is_id(s) -> bool:
    return isinstance(s, str) and bool(_ID.match(s))


# -- the representation and its map ------------------------------------------------

def normalise(raw: str) -> str:
    """One piece of extracted text as the representation holds it: line ends
    `\\n`, lone surrogates as U+FFFD, NFC."""
    s = raw.replace("\r\n", "\n").replace("\r", "\n")
    s = s.encode("utf-8", "replace").decode("utf-8") if _has_surrogate(s) \
        else s
    return unicodedata.normalize("NFC", s)


def _has_surrogate(s: str) -> bool:
    try:
        s.encode("utf-8")
        return False
    except UnicodeEncodeError:
        return True


class Misaligned(ValueError):
    """Normalising the joined text would move text across origin spans."""


def assemble(pieces) -> tuple[str, list[dict]]:
    """Text and map from `(raw text, loc)` pieces, in order. Each piece is
    normalised by itself, so its span is exactly its normalised text. If the
    joined text would normalise differently -- a piece that starts with a
    mark composing with the end of the one before -- that is refused
    (`Misaligned`): re-aligning it silently would move characters from one
    origin to another."""
    parts: list[str] = []
    spans: list[dict] = []
    at = 0
    for raw, loc in pieces:
        s = normalise(raw)
        parts.append(s)
        spans.append({"start": at, "end": at + len(s), "loc": loc})
        at += len(s)
    text = "".join(parts)
    if not unicodedata.is_normalized("NFC", text):
        raise Misaligned("the pieces are each NFC but their join is not: "
                         "normalising it would move text across origin "
                         "spans")
    return text, spans


def check_loc(sch: Scheme, loc) -> str | None:
    return _valid(loc, sch.schema, "loc")


def check(text, spans, status, sch: Scheme) -> str | None:
    """Why this output is not a representation the store may hold, or
    None. The core's own check of every extractor's output (C1.1, C1.2)."""
    if not isinstance(status, str) or kind_of(status) not in (OK, EMPTY,
                                                             FAILED):
        return f"status {status!r} is not ok, empty: or failed:"
    if not isinstance(text, str):
        return "text is not a string"
    if "\r" in text:
        return "text holds a carriage return"
    if _has_surrogate(text):
        return "text is not encodable as UTF-8"
    if not unicodedata.is_normalized("NFC", text):
        return "text is not NFC"
    if kind_of(status) == OK and not text:
        return "status ok with no text"
    if kind_of(status) != OK and text:
        return f"status {kind_of(status)} with text"
    if not isinstance(spans, list):
        return "map is not a list"
    at = 0
    for i, sp in enumerate(spans):
        if not isinstance(sp, dict) or set(sp) != {"start", "end", "loc"}:
            return f"map[{i}] is not exactly {{start, end, loc}}"
        s, e = sp["start"], sp["end"]
        if any(isinstance(x, bool) or not isinstance(x, int) for x in (s, e)):
            return f"map[{i}] offsets are not integers"
        if s != at or e < s:
            return (f"map[{i}] is [{s}:{e}]; spans are contiguous and in "
                    f"order, so it starts at {at}")
        why = check_loc(sch, sp["loc"])
        if why:
            return f"map[{i}]: {why}"
        at = e
    if at != len(text):
        return f"map covers [0:{at}] of a text of {len(text)} code points"
    return None


# -- locating a range ---------------------------------------------------------------

def _first_at(spans, pos: int) -> int:
    """The first span that holds code point `pos` (start <= pos < end)."""
    lo, hi = 0, len(spans)
    while lo < hi:
        mid = (lo + hi) // 2
        if spans[mid]["end"] <= pos:
            lo = mid + 1
        else:
            hi = mid
    return lo


def locate(spans: list[dict], sch: Scheme, start: int, end: int) -> dict:
    """The location of code points `[start, end)`, from the map, by the
    scheme's own functions: the span holding it narrowed to it, or the
    scheme's `span` of the first and last narrowed pieces when it crosses
    spans. Empty spans inside the range are passed over."""
    if not spans or not (0 <= start < end <= spans[-1]["end"]):
        raise ValueError(f"[{start}:{end}] is not inside the representation")
    i = _first_at(spans, start)
    j = _first_at(spans, end - 1)
    a, b = spans[i], spans[j]
    first = sch.narrow(a["loc"], start - a["start"],
                       min(end, a["end"]) - a["start"], a["end"] - a["start"])
    if i == j:
        return first
    last = sch.narrow(b["loc"], max(start, b["start"]) - b["start"],
                      end - b["start"], b["end"] - b["start"])
    return sch.span(first, last)


def token(sch: Scheme, loc: dict) -> str:
    t = sch.token(loc)
    if not isinstance(t, str) or not t or _TOKEN_BAD.search(t):
        raise ValueError(f"{sch.name} gave the token {t!r}; a token is "
                         "non-empty, with no whitespace or braces")
    return t
