"""What a Participant may be called.

THE DEFECT THIS EXISTS FOR (owner, Turn ent-a871e56fed65). Participants called
@Claude, @Codex and @Antigravity were taken for the runtimes claude, codex and
antigravity: agents picked the Participant believing they picked the runtime,
and a '@Codex' review ran on the claude runtime. A Participant's name is a
label for a somebody; a runtime is chosen by a runtime setting or by capacity
(`web.dispatch.resolve_runtime`) and never read from a name. So no
Participant may be named like a runtime at all.

ASCII ONLY (owner's decision, opr-938e0fa58007). After the leading `@` a name
is English letters, digits, `-` and `_`, starting with a letter
(`alias_problem`). Matching every look-alike in Unicode was tried twice --
a hand-built table, then Unicode's own confusables data (UTS #39) -- and
reviews still found spellings that got through, while the tightened rules
refused a real name (@Agi with an accent). Unicode matching cannot be both
airtight and fair to every real name; an ASCII alphabet can be airtight, and
says plainly what is allowed. Accented and non-Latin names are not
Participant names.

RESERVED: every name a registered runtime goes by and the model family names,
both read from `mentis.runtime_names` -- a module of data that imports
nothing. THIS LAYER NEVER IMPORTS THE RUNTIME ADAPTERS (review finding
opr-5a18023c2d46): they load the worker and everything it loads, and the
Conversation layer sits beneath all of that.

MATCHED EXACTLY ON THE ASCII FORM (`fold`): case ignored, everything but
letters and digits dropped (so '@', `-`, `_` and spaces never matter, and a
reserved name is matched with its separators removed), and the letters ASCII
itself makes look alike folded together: l, 1 and I; o and 0; rn and m;
and cl and d, which keeps the earlier review's ASCII spelling '@Coclex'
refused. A name is reserved when its fold is a reserved name's.
"""
from __future__ import annotations

import re
import unicodedata

from mentis import runtime_names as _registry

#: Model families, reserved beside the runtimes (`mentis.runtime_names`).
MODEL_FAMILIES = _registry.MODEL_FAMILIES

#: What a name may be made of, as the refusal says it.
ALLOWED = ("English letters (A-Z, a-z), digits (0-9), hyphen (-) and "
           "underscore (_), starting with a letter")

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_CHARS = re.compile(r"[A-Za-z0-9_-]")


def _bare(alias) -> str:
    s = str(alias or "")
    return s[1:] if s.startswith("@") else s


def _shown(ch: str) -> str:
    name = unicodedata.name(ch, "")
    code = f"U+{ord(ch):04X}"
    if ch == " ":
        return "a space"
    if ch.isprintable() and ch.isascii():
        return repr(ch)
    return f"{code} {name}".strip()


def alias_problem(alias) -> str | None:
    """Why this alias is not a name a Participant may take, or None.

    Only the characters are judged here, never who the name is."""
    bare = _bare(alias)
    if _NAME.fullmatch(bare):
        return None
    if not bare:
        return "a Participant needs a name"
    bad = []
    for ch in bare:
        if not _CHARS.fullmatch(ch) and ch not in bad:
            bad.append(ch)
    said = (f"; it contains {', '.join(_shown(ch) for ch in bad[:6])}"
            + (" and more" if len(bad) > 6 else "")) if bad else \
        "; it does not start with a letter"
    return (f"{alias!r} is not a name a Participant may take: after the "
            f"leading @, a name may use only {ALLOWED}{said}")


_FOLD = str.maketrans({"1": "l", "i": "l", "0": "o"})


def fold(name) -> str:
    """The form names are compared in (see the module's account)."""
    s = "".join(ch for ch in str(name or "").lower()
                if ch.isascii() and ch.isalnum())
    return s.translate(_FOLD).replace("rn", "m").replace("cl", "d")


def reserved_names() -> tuple[str, ...]:
    out: list[str] = []
    for n in (*_registry.runtime_names(), *_registry.MODEL_FAMILIES):
        if n not in out:
            out.append(n)
    return tuple(out)


def reserved_as(alias) -> str | None:
    """The reserved name this alias matches, or None when it matches none."""
    f = fold(alias)
    if not f:
        return None
    return next((n for n in reserved_names() if fold(n) == f), None)
