"""The checking and storage helpers Fluid's arrangements are built on.

Moved verbatim from Mark IV's `mentis/lab_workspaces.py` (the Workspace Lab's
saved workspaces, deleted with the rest of the UI-only machinery) because
`mentis.fluid.arrangements` checks and keeps its files with exactly these.
Nothing else of the Lab came with them.
"""

from __future__ import annotations

import math
import os
import pathlib
import re
import tempfile
import threading

DIR = "presentation"

#: Bounds, not policy: enough for any workspace anybody will lay out, and a limit on what a
#: file can make the interface draw.
MAX_BYTES = 256 * 1024
MAX_PAGES = 30
MAX_ZONES = 40           # on one page
MAX_SLOTS = 100          # in one zone
MAX_DEPTH = 8
MAX_KIDS = 12
MAX_LABEL = 200
MAX_KEY = 300

#: Where the conversation is drawn. `full` is the conversation filling the Lab.
PRESENCES = ("docked", "floating", "icon", "full")

#: a conversation id, as it names its saved workspace's file: no `.`, no `:`, no separator
_CONVERSATION = re.compile(r"[A-Za-z0-9_-]{1,80}")
#: names Windows keeps for devices, whatever follows them
_DEVICES = re.compile(r"(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])")
_TURN = re.compile(r"[A-Za-z0-9_.:-]{1,80}")
_NODE = re.compile(r"[A-Za-z0-9_-]{1,80}")

_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


class Refused(ValueError):
    """What was sent is not a workspace or a layout. The message says what is wrong."""


class Unreadable(RuntimeError):
    """The library on disk could not be read, so nothing is written over it."""


def _lock(root: str) -> threading.Lock:
    key = str(pathlib.Path(root).resolve())
    with _locks_lock:
        return _locks.setdefault(key, threading.Lock())


def _dir(root: str) -> pathlib.Path:
    return pathlib.Path(root) / DIR


def _text(v, where, *, most=MAX_LABEL, blank=False) -> str:
    """Printable text of at most `most` characters: a label, a name, a key."""
    if not isinstance(v, str) or len(v) > most or (not blank and not v):
        raise Refused(f"{where}: must be text of {'0' if blank else '1'}..{most} characters")
    if any(ord(c) < 32 or ord(c) == 127 for c in v):
        raise Refused(f"{where}: must not carry control characters")
    return v


def _match(rx, v, where) -> str:
    if not isinstance(v, str) or not rx.fullmatch(v):
        raise Refused(f"{where}: {v!r} is not well formed")
    return v


def _num(v, where, lo, hi) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise Refused(f"{where}: {v!r} is not a number")
    if not lo <= v <= hi:
        raise Refused(f"{where}: {v} is outside {lo}..{hi}")
    return v


def presence(v, where="presence") -> dict | None:
    """Where the conversation is drawn, with the dock's width and the window's place."""
    if v is None:
        return None
    if not isinstance(v, dict) or v.get("pres") not in PRESENCES:
        raise Refused(f"{where}: pres must be one of {list(PRESENCES)}")
    out = {"pres": v["pres"], "dock": _num(v.get("dock", 480), f"{where}.dock", 0, 10000)}
    g = v.get("float")
    if g is None:
        out["float"] = None
    elif isinstance(g, dict):
        out["float"] = {k: _num(g.get(k), f"{where}.float.{k}", -10000, 10000)
                        for k in ("x", "y", "w", "h")}
    else:
        raise Refused(f"{where}.float: must be a place or null")
    return out


def _atomic(path: pathlib.Path, data: dict):
    """All or nothing: a temporary file, then a rename over the old one."""
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".incoming-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
