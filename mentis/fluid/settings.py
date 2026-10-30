"""Fluid's brain-wide settings (Surface Tension P2, plan §3.8), BESIDE the
record:

    GET  /fluid/api/settings   {"makeRoom"}
    POST /fluid/api/settings   {"makeRoom", "op"?}: keep it; answers {"makeRoom"}

Kept as the arrangements are (`mentis/fluid/_checks.py`), one file written
whole under the same lock:

    <corpus>/presentation/fluid-settings.json
    {"format": "mentis.fluid-settings", "version": 1, "makeRoom": ...}

`makeRoom` is the GLOBAL DEFAULT for Make room -- `off`, `drag` (while
dragging) or `expand` (also on Expand). A workspace may override it in its
arrangement (`spatial.makeRoom`); the override wins, then this, then `off`.
No file reads as the built-in default, `off`.

WHAT IT TRUSTS: nothing. Unknown keys and values are refused when sent, and a
file holding anything else is unreadable: it is read as the built-in default,
said why (`unreadable`), and never written over -- a POST is refused (the
arrangements' `Unreadable` rule) until the file is mended by hand.

AN OPERATION KEY is accepted and checked for shape, but nothing is kept for
it: setting one value is the same write however often it is sent.
"""
from __future__ import annotations

import json

from mentis.fluid import _checks as W

FORMAT = "mentis.fluid-settings"
VERSION = 1
FILE = "fluid-settings.json"
MAKE_ROOM = ("off", "drag", "expand")
DEFAULT = {"makeRoom": "off"}
MAX_OP = 120
_KEYS = {"format", "version", "makeRoom"}

Refused = W.Refused
Unreadable = W.Unreadable


def _path(root):
    return W._dir(root) / FILE


def _make_room(v) -> str:
    if not isinstance(v, str) or v not in MAKE_ROOM:
        raise Refused(f"makeRoom: {v!r} is not one of {list(MAKE_ROOM)}")
    return v


def _read(root) -> tuple[dict, str | None]:
    """(the settings, why the file is unreadable or None)."""
    try:
        data = json.loads(_path(root).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return dict(DEFAULT), None
    except (OSError, ValueError, RecursionError):
        return dict(DEFAULT), f"{FILE} could not be read"
    if not isinstance(data, dict) or set(data) != _KEYS \
            or data.get("format") != FORMAT or data.get("version") != VERSION:
        return dict(DEFAULT), f"{FILE} is not {FORMAT} version {VERSION}"
    try:
        return {"makeRoom": _make_room(data["makeRoom"])}, None
    except Refused as exc:
        return dict(DEFAULT), f"{FILE} is not settings: {exc}"


def settings(root) -> dict:
    """`GET /fluid/api/settings`."""
    got, why = _read(root)
    return {**got, "unreadable": why} if why else got


def save(root, body) -> dict:
    """`POST /fluid/api/settings` {makeRoom, op?}."""
    if not isinstance(body, dict):
        raise Refused("send {\"makeRoom\", \"op\"?}")
    extra = sorted(str(k) for k in set(body) - {"makeRoom", "op"})
    if extra:
        raise Refused(f"{extra[0]!r} is not a setting: send makeRoom")
    if "makeRoom" not in body:
        raise Refused("makeRoom: one of " + str(list(MAKE_ROOM)))
    make_room = _make_room(body["makeRoom"])
    if body.get("op") is not None:
        W._text(body["op"], "op", most=MAX_OP)
    with W._lock(root):
        _got, why = _read(root)
        if why:
            raise Unreadable(f"{why}; it was left as it is")
        W._atomic(_path(root), {"format": FORMAT, "version": VERSION,
                                "makeRoom": make_room})
    return {"makeRoom": make_room}
