"""The first extractor: `pdf-text`, a PDF's text layer, with locator scheme
`pdf-page/1` (Sources C, C5).

ONE PINNED, PERMISSIVELY LICENSED LIBRARY: `pypdf` 6.14.2, BSD-3-Clause,
pure Python, pinned in `requirements.txt`. Not PyMuPDF (AGPL), and nothing
else: `pypdf` needs no other package for what this does. It can decrypt
with `cryptography`, so this extractor never decrypts -- an encrypted PDF is
`failed: encrypted` -- and `cryptography` cannot change its output. Its
identity declares `pypdf` exactly; a process with any other version installed
cannot run this identity (`extract.runnable`), and a new pin is a new id.

THE TEXT. Each physical page's text, in document order, from
`PageObject.extract_text` with the options below, then normalised by the
core (`\\n`, NFC). A page with text ends with `\\n` -- added when the
library did not end it so -- so pages never run together. A page with no
text keeps its place as an EMPTY span. Every page empty is `empty: no text
layer` (OCR is later work, a different extractor).

THE LOCATION, `pdf-page/1`: `{page, char_start, char_end}`, `page` 1-based
(the physical page, as a viewer numbers it from the first, not a printed
folio), and `[char_start, char_end)` code points within that page's
normalised text, its closing `\\n` included. A range crossing pages adds
`end_page`, and `char_end` is then within that page. Tokens: `p12:340-512`,
`p12:900-p13:40`. Displays: `page 12`, `pages 12–13`.
"""

from __future__ import annotations

import io

from mentis.sources import extract as X

NAME = "pdf-text"
VERSION = "1"
LIBRARY = "pypdf"
PINNED = "6.14.2"
OPTIONS = {"library_call": "PageObject.extract_text",
           "extraction_mode": "plain",
           "orientations": [0, 90, 180, 270],
           "space_width": 200.0,
           "encrypted": "refuse",
           "page_text_ends_with_newline": True,
           "pages": "every physical page, in document order"}
SCHEME = "pdf-page/1"


def _installed() -> dict:
    from importlib import metadata
    try:
        return {LIBRARY: metadata.version(LIBRARY)}
    except metadata.PackageNotFoundError:
        return {LIBRARY: None}


def _extract(data: bytes, options: dict):
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data), strict=False)
    if r.is_encrypted:
        return "", [], "failed: encrypted; this extractor does not decrypt"
    pieces = []
    for n, pg in enumerate(r.pages, start=1):
        t = pg.extract_text(extraction_mode=options["extraction_mode"],
                            orientations=tuple(options["orientations"]),
                            space_width=options["space_width"]) or ""
        if t and not t.endswith(("\n", "\r")):
            t += "\n"
        pieces.append((t, n))
    text, spans = X.assemble((t, {"page": n, "char_start": 0,
                                  "char_end": 0}) for t, n in pieces)
    for sp in spans:                          # each page's own length
        sp["loc"]["char_end"] = sp["end"] - sp["start"]
    if not text:
        return "", spans, "empty: no text layer"
    return text, spans, "ok"


def _narrow(loc, lo, hi, length):
    return {"page": loc["page"], "char_start": loc["char_start"] + lo,
            "char_end": loc["char_start"] + hi}


def _span(first, last):
    end_page = last.get("end_page", last["page"])
    if end_page == first["page"]:
        return {"page": first["page"], "char_start": first["char_start"],
                "char_end": last["char_end"]}
    return {"page": first["page"], "char_start": first["char_start"],
            "end_page": end_page, "char_end": last["char_end"]}


def _token(loc):
    if "end_page" in loc and loc["end_page"] != loc["page"]:
        return (f"p{loc['page']}:{loc['char_start']}-"
                f"p{loc['end_page']}:{loc['char_end']}")
    return f"p{loc['page']}:{loc['char_start']}-{loc['char_end']}"


def _display(loc):
    if "end_page" in loc and loc["end_page"] != loc["page"]:
        return f"pages {loc['page']}–{loc['end_page']}"
    return f"page {loc['page']}"


_N = {"type": "integer", "minimum": 0}
_P = {"type": "integer", "minimum": 1}

PAGE_SCHEME = X.register_scheme(X.Scheme(
    name=SCHEME,
    schema={"type": "object", "required": ["page", "char_start", "char_end"],
            "properties": {"page": _P, "char_start": _N, "char_end": _N,
                           "end_page": _P},
            "additionalProperties": False},
    display=_display, token=_token, span=_span, narrow=_narrow))

PDF_TEXT = X.register(X.Extractor(
    name=NAME, version=VERSION, options=OPTIONS, deps={LIBRARY: PINNED},
    accepts=("application/pdf",), signatures=(b"%PDF-",),
    locator_scheme=SCHEME, extract=_extract, installed=_installed,
    licence="pypdf: BSD-3-Clause"))
