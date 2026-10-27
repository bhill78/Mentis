"""Citations of acquired sources: ONE parser for both forms (C1.5).

    adm-<hex>@<srcdigest12>[<start>:<end>]
        DIRECT. UTF-8 byte offsets into the source's own retained bytes --
        text sources (C0), exactly as Sources A writes them.

    adm-<hex>@<srcdigest12>~<extractor_id>/<repdigest12>[<start>:<end>]{<scheme>:<token>}
        EXTRACTED. Code-point offsets into one exact representation:
        the source (R4), the extractor identity and representation digest
        (R5), the canonical position, and the source location carried in
        the citation itself, so it still says where to look when the store
        is gone and the extractor cannot be run (R3, R6).

`~` is the only thing that tells them apart. The extractor id holds its own
`@` and `+` (`name@version+hash12`); the source's `@` is the first one after
the `adm-` id, and the id runs to the `/` before the representation digest.
`{scheme:token}` splits on the FIRST `:` -- a scheme name never holds one,
a token may (`Sheet1!B4:C9`, `h:Combat>Grappling#3`).

A citation that is malformed or partial is refused with the reason. Nothing
is truncated, guessed or completed, and `format(parse(s)) == s` for every
citation this accepts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mentis.sources.extract import ID

ADM = r"adm-[0-9a-f]{8,}"
D12 = r"[0-9a-f]{12}"
SCHEME = r"[a-z0-9][a-z0-9.-]*/[0-9]+"
TOKEN = r"[^\s{}]+"

_DIRECT = re.compile(rf"^({ADM})@({D12})\[(0|[1-9][0-9]*):(0|[1-9][0-9]*)\]$")
_EXTRACTED = re.compile(
    rf"^({ADM})@({D12})~({ID})/({D12})"
    rf"\[(0|[1-9][0-9]*):(0|[1-9][0-9]*)\]\{{({SCHEME}):({TOKEN})\}}$")
#: An extracted citation inside running text.
IN_TEXT = re.compile(
    rf"(?<![\w/-]){ADM}@{D12}~{ID}/{D12}"
    rf"\[(?:0|[1-9][0-9]*):(?:0|[1-9][0-9]*)\]\{{{SCHEME}:{TOKEN}\}}")


class Malformed(ValueError):
    """Not a citation this parser accepts, and why."""


@dataclass(frozen=True)
class Cite:
    ref: str
    source12: str
    start: int
    end: int
    #: None for a direct citation
    extractor_id: str | None = None
    representation12: str | None = None
    scheme: str | None = None
    token: str | None = None

    @property
    def extracted(self) -> bool:
        return self.extractor_id is not None

    @property
    def unit(self) -> str:
        return "codepoint" if self.extracted else "byte"

    def __str__(self) -> str:
        return format_cite(self)

    def public(self) -> dict:
        out = {"ref": self.ref, "source_digest12": self.source12,
               "start": self.start, "end": self.end, "unit": self.unit,
               "form": "extracted" if self.extracted else "direct"}
        if self.extracted:
            out.update(extractor_id=self.extractor_id,
                       representation_digest12=self.representation12,
                       scheme=self.scheme, token=self.token)
        return out


def format_cite(c: Cite) -> str:
    stem = f"{c.ref}@{c.source12}"
    if not c.extracted:
        return f"{stem}[{c.start}:{c.end}]"
    return (f"{stem}~{c.extractor_id}/{c.representation12}"
            f"[{c.start}:{c.end}]{{{c.scheme}:{c.token}}}")


def direct(ref: str, source_digest: str, start: int, end: int) -> str:
    return format_cite(Cite(ref, source_digest[:12], start, end))


def extracted(ref: str, source_digest: str, extractor_id: str,
              representation_digest: str, start: int, end: int,
              scheme: str, token: str) -> str:
    c = Cite(ref, source_digest[:12], start, end, extractor_id,
             representation_digest[:12], scheme, token)
    s = format_cite(c)
    parse(s)                                  # never write what is refused
    return s


def parse(s) -> Cite:
    if not isinstance(s, str):
        raise Malformed("a citation is text")
    if s != s.strip():
        raise Malformed("a citation has no surrounding whitespace")
    m = _EXTRACTED.match(s)
    if m:
        ref, d12, xid, r12, a, b, sch, tok = m.groups()
        c = Cite(ref, d12, int(a), int(b), xid, r12, sch, tok)
    else:
        m = _DIRECT.match(s)
        if not m:
            raise Malformed(_why(s))
        ref, d12, a, b = m.groups()
        c = Cite(ref, d12, int(a), int(b))
    if c.end <= c.start:
        raise Malformed(f"[{c.start}:{c.end}] is empty or reversed")
    return c


def _why(s: str) -> str:
    """The first thing wrong with something that is not a citation."""
    m = re.match(rf"^{ADM}", s)
    if not m:
        return "a citation starts with the source's adm- reference"
    rest = s[m.end():]
    if not re.match(rf"^@{D12}", rest):
        return ("after the adm- reference comes @ and the first 12 hex "
                "digits of the source digest")
    rest = rest[13:]
    if rest.startswith("~"):
        m2 = re.match(rf"^~({ID})", rest)
        if not m2:
            return ("after ~ comes the extractor id, name@version+hash12")
        rest = rest[m2.end():]
        if not re.match(rf"^/{D12}", rest):
            return ("after the extractor id comes / and the first 12 hex "
                    "digits of the representation digest")
        rest = rest[13:]
        if not re.match(r"^\[(0|[1-9][0-9]*):(0|[1-9][0-9]*)\]", rest):
            return "an extracted citation gives [start:end] in code points"
        rest = rest[rest.index("]") + 1:]
        if not rest:
            return ("an extracted citation ends with {scheme:token}, the "
                    "source location; it is missing")
        return ("{scheme:token} is a registered scheme name/version, a "
                "colon, and a token with no whitespace or braces, closing "
                "the citation")
    if not re.match(r"^\[(0|[1-9][0-9]*):(0|[1-9][0-9]*)\]", rest):
        return "a direct citation gives [start:end] in bytes"
    return "a direct citation ends at its ]"
