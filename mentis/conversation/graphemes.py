"""Where a passage of text may begin and end: grapheme-cluster boundaries.

A selected-text Anchor names a range of CODE POINTS inside one text part of an
immutable Turn version. A range whose edge falls inside a user-perceived
character -- between a thumb and its skin tone, inside a flag, before a
combining accent, inside a Devanagari conjunct -- does not name a passage
anybody could have selected, so it is refused.

FULL UAX #29, NOT AN APPROXIMATION. Round 3 tried a narrow standard-library
check and it disagreed with the standard on Indic conjuncts (GB9c), Thai SARA
AM, Prepend (GB9b) and ZWJ between ordinary letters, because `unicodedata`
does not expose the properties the rules are written in. This module asks the
third-party `regex` module's `\\X`, which implements the extended grapheme
cluster rules, and the suite runs the official `GraphemeBreakTest` file for
the Unicode version that module implements (`UNICODE_VERSION`).

THE DEPENDENCY IS LOADED LAZILY and its absence is an ANSWER: `boundaries`
raises `Unavailable`, which the anchor service turns into a refusal of the
text-range anchor. Nothing else in Mentis needs it, so a server without it
still starts and everything else still works.

UTF-16 IS A BOUNDARY CONVERSION. Browsers count in UTF-16 code units; the
record counts code points. `utf16_to_codepoint` refuses an offset inside a
surrogate pair rather than rounding it.
"""

from __future__ import annotations

#: The exact dependency this was verified against, and the Unicode version
#: it implements (upstream changelog: 17.0.0 from 2025.10.20, 18.0.0 only from
#: 2026.9.29). See docs/design/anchored-interaction.md §4.1.
DEPENDENCY = "regex==2026.6.28"
UNICODE_VERSION = "17.0.0"


class Unavailable(RuntimeError):
    """The grapheme segmenter is not installed in this interpreter."""


_X = None


def _cluster():
    global _X
    if _X is None:
        try:
            import regex
        except ImportError as exc:          # pragma: no cover - environment
            raise Unavailable(
                f"grapheme boundaries need {DEPENDENCY} (see requirements.txt), "
                f"and it is not installed here") from exc
        _X = regex.compile(r"\X")
    return _X


def boundaries(text: str) -> set[int]:
    """Every code-point offset in `text` that is an extended grapheme cluster
    boundary, including 0 and len(text)."""
    out = {0}
    for m in _cluster().finditer(text):
        out.add(m.end())
    return out


def utf16_to_codepoint(text: str, offset: int) -> int:
    """A UTF-16 code-unit offset into `text`, as a code-point offset."""
    if offset < 0:
        raise ValueError("a UTF-16 offset is not negative")
    units = 0
    for i, ch in enumerate(text):
        if units == offset:
            return i
        units += 2 if ord(ch) > 0xFFFF else 1
        if units > offset:
            raise ValueError(f"UTF-16 offset {offset} falls inside a surrogate "
                             f"pair (code point {i})")
    if units == offset:
        return len(text)
    raise ValueError(f"UTF-16 offset {offset} is past the end of the text")


def codepoint_to_utf16(text: str, offset: int) -> int:
    """A code-point offset into `text`, in UTF-16 code units."""
    return sum(2 if ord(ch) > 0xFFFF else 1 for ch in text[:offset])
