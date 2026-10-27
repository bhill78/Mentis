"""Which extractors are current, by payload type (C1.7). Configuration, not
record: changing it changes what is searched from now on, and never what an
existing citation points at.

PRODUCTION GIVES TEXT NOTHING (C0). Markdown, plain text, CSV and code are
read and searched as their own bytes, so no text type is listed here and no
extraction is ever made for one. A later text format whose raw bytes are a
poor representation (HTML visible text, say) would be listed like any other
type, and its raw bytes would stay searchable beside it.

The first and only production extractor is `pdf-text` (Sources C, C5).
"""

from __future__ import annotations

#: payload type -> extractor names, in order.
CURRENT: dict[str, tuple[str, ...]] = {
    "application/pdf": ("pdf-text",),
}

_LOADED = False


def load() -> None:
    """Register the production extractors and their schemes, once."""
    global _LOADED
    if not _LOADED:
        import mentis.sources.extract.pdf  # noqa: F401  (registers itself)
        _LOADED = True


def names_for(payload_type: str | None) -> tuple[str, ...]:
    load()
    return CURRENT.get(payload_type or "", ())
