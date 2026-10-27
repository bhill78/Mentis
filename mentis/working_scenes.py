"""Working scenes: the small figures that play above the composer while work runs.

Owner's request (Mentis Features / Upgrades, 2026-10-01): a LIBRARY of animations --
single figures, a sword fight between workers with runtime-mark heads, code delivered
back to the agent that was waiting, darts, cards, and a theater where each worker who
starts takes a seat -- to which new ones can be added WITHOUT NEW CODE.

WHAT A SCENE IS: data, never a program. Poses are short lists of drawing pieces from a
fixed vocabulary (line, circle, rect, text, head), actors move along keyframe tracks,
and `when` says what it is for (how many are working, or an event). One player in the
interface draws any scene; it never names one. Nothing in a scene is ever written into
the page as markup, style or script -- the player builds every element itself and puts
text in as text -- and every scene is checked here, both when it is added and every
time it is read, exactly as looks are (`mentis/presentation.py`).

WHERE THEY LIVE, AND WHY THERE: beside the record, like looks.

    mentis/working_scenes_builtin/<id>.json     the set Mentis ships (data files)
    <corpus>/presentation/scenes/<id>.json      scenes added to this brain
    <corpus>/presentation/scenes.json           which scenes are switched off

Not the record: an Entry establishes, so a cartoon would become knowledge retrieval can
return, and nothing that forms context, retrieves, delivers or governs reads this. Only
the `/api/presentation/scenes` routes do, and a worker grant is refused on them.

A MISSING OR UNREADABLE FILE IS DEFAULTS, NEVER AN ERROR. A scene on disk that fails the
checks is left out and counted, never served.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import re
import tempfile
import threading

FORMAT = 1
BUILTIN = pathlib.Path(__file__).with_name("working_scenes_builtin")
SUBDIR = ("presentation", "scenes")
STATE = ("presentation", "scenes.json")

#: Bounds, not policy: enough for any scene anybody will draw, and a limit on what a
#: file can make the interface do.
MAX_BYTES = 64 * 1024
MAX_ADDED = 60
MAX_POSES = 80
MAX_PIECES = 48
MAX_ACTORS = 32
MAX_KEYS = 96
MAX_TICKS = 6000          # 4 minutes at 25 ticks a second
MAX_COORD = 600.0
MAX_TEXT = 24
MAX_WORKERS = 12

#: The ONLY colours a scene may name. The interface maps each to a token of the
#: atmosphere in force, so a scene can never carry a colour value of its own.
COLOURS = ("ink", "steel", "gold", "red", "paper", "wood", "seat", "faint", "live")
#: The events a scene may be played for. `handback`: a delegated worker's result went
#: back to the work that was waiting on it (the record's `work-resumed` act).
EVENTS = ("handback",)
#: Who an actor is. A worker by order of arrival, or one side of a handback.
ROLE = re.compile(r"worker:(0|[1-9][0-9]?)|receiver|returner")
ANCHORS = ("line", "left", "seat")
KEYS = {"t", "x", "y", "o", "pose", "every", "face", "arc", "ease"}

_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_POSE = re.compile(r"[a-z0-9][a-z0-9-]{0,29}")

_lock = threading.Lock()


class Refused(ValueError):
    """A scene that is not one. The message says exactly what is wrong."""


# -- checking --------------------------------------------------------------------------------

def _num(v, where, lo=-MAX_COORD, hi=MAX_COORD) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise Refused(f"{where}: {v!r} is not a number")
    if not lo <= v <= hi:
        raise Refused(f"{where}: {v} is outside {lo}..{hi}")
    return float(v) if isinstance(v, float) else v


def _int(v, where, lo, hi) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise Refused(f"{where}: {v!r} is not a whole number")
    if not lo <= v <= hi:
        raise Refused(f"{where}: {v} is outside {lo}..{hi}")
    return v


def _colour(v, where, default) -> str:
    if v is None:
        return default
    if v not in COLOURS:
        raise Refused(f"{where}: {v!r} is not one of {list(COLOURS)}")
    return v


def _piece(p, where) -> list:
    """One drawing piece, normalised to its full form."""
    if not isinstance(p, list) or not p or not isinstance(p[0], str):
        raise Refused(f"{where}: a piece is a list starting with its kind")
    k, a = p[0], p[1:]
    if k == "line":
        if not 4 <= len(a) <= 6:
            raise Refused(f"{where}: line is [x1, y1, x2, y2, colour?, width?]")
        return ["line", *(_num(v, where) for v in a[:4]),
                _colour(a[4] if len(a) > 4 else None, where, "ink"),
                _num(a[5], where, 0.2, 6) if len(a) > 5 else 1.4]
    if k == "circle":
        if not 3 <= len(a) <= 5:
            raise Refused(f"{where}: circle is [cx, cy, r, stroke?, fill?]")
        return ["circle", _num(a[0], where), _num(a[1], where), _num(a[2], where, 0.2, 80),
                _colour(a[3] if len(a) > 3 else None, where, "ink"),
                _colour(a[4], where, "ink") if len(a) > 4 and a[4] is not None else None]
    if k == "rect":
        if not 4 <= len(a) <= 7:
            raise Refused(f"{where}: rect is [x, y, w, h, fill?, stroke?, strokeWidth?]")
        return ["rect", _num(a[0], where), _num(a[1], where), _num(a[2], where, 0, 400),
                _num(a[3], where, 0, 400), _colour(a[4] if len(a) > 4 else None, where, "ink"),
                _colour(a[5], where, "ink") if len(a) > 5 and a[5] is not None else None,
                _num(a[6], where, 0, 4) if len(a) > 6 else 0]
    if k == "text":
        if not 3 <= len(a) <= 5:
            raise Refused(f"{where}: text is [x, y, string, size?, colour?]")
        s = a[2]
        if not isinstance(s, str) or not 0 < len(s) <= MAX_TEXT or any(
                ord(c) < 32 for c in s):
            raise Refused(f"{where}: text must be 1..{MAX_TEXT} printable characters")
        return ["text", _num(a[0], where), _num(a[1], where), s,
                _num(a[3], where, 3, 24) if len(a) > 3 else 7,
                _colour(a[4] if len(a) > 4 else None, where, "ink")]
    if k == "head":
        if len(a) != 3:
            raise Refused(f"{where}: head is [cx, cy, r]")
        return ["head", _num(a[0], where), _num(a[1], where), _num(a[2], where, 1, 40)]
    raise Refused(f"{where}: {k!r} is not a piece; pieces are line, circle, rect, text, head")


def _x(v, where):
    if not (isinstance(v, list) and len(v) == 2 and v[0] in ANCHORS):
        raise Refused(f"{where}: x is [anchor, offset] with anchor one of {list(ANCHORS)}")
    return [v[0], _num(v[1], where)]


def _keyframe(k, where, poses, *, timed=True) -> dict:
    if not isinstance(k, dict):
        raise Refused(f"{where}: a keyframe is an object")
    extra = set(k) - KEYS
    if extra:
        raise Refused(f"{where}: unknown keys {sorted(extra)}")
    out = {}
    if timed:
        out["t"] = _int(k.get("t"), f"{where}.t", 0, MAX_TICKS)
    if "x" in k:
        out["x"] = _x(k["x"], f"{where}.x")
    if "y" in k:
        out["y"] = _num(k["y"], f"{where}.y")
    if "o" in k:
        out["o"] = _num(k["o"], f"{where}.o", 0, 1)
    if "arc" in k:
        out["arc"] = _num(k["arc"], f"{where}.arc", -80, 80)
    if "face" in k:
        if k["face"] not in (1, -1):
            raise Refused(f"{where}.face: 1 or -1")
        out["face"] = k["face"]
    if "ease" in k:
        if k["ease"] not in ("out", "in", "linear"):
            raise Refused(f"{where}.ease: out, in or linear")
        out["ease"] = k["ease"]
    if "every" in k:
        out["every"] = _int(k["every"], f"{where}.every", 1, 600)
    if "pose" in k:
        p = k["pose"]
        names = p if isinstance(p, list) else [p]
        if not names or len(names) > 16:
            raise Refused(f"{where}.pose: one pose, or a cycle of 1..16")
        for n in names:
            if n not in poses:
                raise Refused(f"{where}.pose: {n!r} is not a pose of this scene")
        out["pose"] = p
    return out


def _track(t, where, poses) -> list:
    if not isinstance(t, list) or not 1 <= len(t) <= MAX_KEYS:
        raise Refused(f"{where}: a track is 1..{MAX_KEYS} keyframes")
    out = [_keyframe(k, f"{where}[{i}]", poses) for i, k in enumerate(t)]
    if any(b["t"] < a["t"] for a, b in zip(out, out[1:])):
        raise Refused(f"{where}: keyframes must not go back in time")
    if "x" not in out[0] or "pose" not in out[0]:
        raise Refused(f"{where}: the first keyframe says x and pose")
    return out


def check(scene) -> dict:
    """The scene, normalised, or `Refused` saying what is wrong."""
    if not isinstance(scene, dict):
        raise Refused("a scene is a JSON object")
    if len(json.dumps(scene)) > MAX_BYTES:
        raise Refused(f"a scene is at most {MAX_BYTES} bytes")
    if scene.get("format") != FORMAT:
        raise Refused(f"format must be {FORMAT}")
    sid = scene.get("id")
    if not isinstance(sid, str) or not _ID.fullmatch(sid):
        raise Refused("id: lowercase letters, digits and dashes, at most 40")
    name = scene.get("name")
    if not isinstance(name, str) or not 0 < len(name.strip()) <= 60:
        raise Refused("name: 1..60 characters")
    about = scene.get("about", "")
    if not isinstance(about, str) or len(about) > 400:
        raise Refused("about: at most 400 characters")

    when = scene.get("when")
    if not isinstance(when, dict) or len(when) != 1:
        raise Refused('when: {"workers": [min, max]} or {"event": "handback"}')
    if "workers" in when:
        w = when["workers"]
        if not (isinstance(w, list) and len(w) == 2):
            raise Refused("when.workers: [min, max]")
        lo = _int(w[0], "when.workers[0]", 1, MAX_WORKERS)
        hi = _int(w[1], "when.workers[1]", lo, MAX_WORKERS)
        when = {"workers": [lo, hi]}
    elif "event" in when:
        if when["event"] not in EVENTS:
            raise Refused(f"when.event: one of {list(EVENTS)}")
        when = {"event": when["event"]}
    else:
        raise Refused('when: {"workers": [min, max]} or {"event": "handback"}')

    loop, length = scene.get("loop"), scene.get("length")
    if "event" in when:
        if loop is not None or length is None:
            raise Refused("an event scene plays once: give `length`, not `loop`")
        length = _int(length, "length", 10, MAX_TICKS)
    elif loop is not None:
        loop = _int(loop, "loop", 10, MAX_TICKS)
    elif not any("each" in a for a in scene.get("actors") or [] if isinstance(a, dict)):
        raise Refused("a scene for workers loops: give `loop`")

    seats = scene.get("seats")
    if seats is not None:
        if not isinstance(seats, dict) or set(seats) - {"from", "step", "count"}:
            raise Refused("seats: {from, step, count}")
        seats = {"from": _num(seats.get("from"), "seats.from"),
                 "step": _num(seats.get("step"), "seats.step", -200, 200),
                 "count": _int(seats.get("count"), "seats.count", 1, MAX_WORKERS)}

    raw = scene.get("poses")
    if not isinstance(raw, dict) or not 1 <= len(raw) <= MAX_POSES:
        raise Refused(f"poses: 1..{MAX_POSES} named poses")
    poses = {}
    for n, pieces in raw.items():
        if not isinstance(n, str) or not _POSE.fullmatch(n):
            raise Refused(f"pose name {n!r}: lowercase letters, digits and dashes")
        if not isinstance(pieces, list) or not 1 <= len(pieces) <= MAX_PIECES:
            raise Refused(f"poses.{n}: 1..{MAX_PIECES} pieces")
        poses[n] = [_piece(p, f"poses.{n}[{i}]") for i, p in enumerate(pieces)]

    actors_raw = scene.get("actors")
    if not isinstance(actors_raw, list) or not 1 <= len(actors_raw) <= MAX_ACTORS:
        raise Refused(f"actors: 1..{MAX_ACTORS}")
    actors = []
    for i, a in enumerate(actors_raw):
        where = f"actors[{i}]"
        if not isinstance(a, dict):
            raise Refused(f"{where}: an object")
        extra = set(a) - {"who", "each", "still", "track", "arrive", "leave"}
        if extra:
            raise Refused(f"{where}: unknown keys {sorted(extra)}")
        out = {}
        if "who" in a:
            if not isinstance(a["who"], str) or not ROLE.fullmatch(a["who"]):
                raise Refused(f"{where}.who: worker:N, receiver or returner")
            if a["who"] in ("receiver", "returner") and "event" not in when:
                raise Refused(f"{where}.who: {a['who']} exists only in a handback scene")
            out["who"] = a["who"]
        if "each" in a:
            if a["each"] not in ("seat", "worker") or seats is None or "who" in a:
                raise Refused(f"{where}.each: seat or worker, in a scene with seats")
            out["each"] = a["each"]
        if out.get("each") == "worker":
            out["arrive"] = _track(a.get("arrive"), f"{where}.arrive", poses)
            out["leave"] = _track(a.get("leave"), f"{where}.leave", poses)
        else:
            out["track"] = _track(a.get("track"), f"{where}.track", poses)
        if "still" in a:
            out["still"] = _keyframe(a["still"], f"{where}.still", poses, timed=False)
        actors.append(out)
    return {"format": FORMAT, "id": sid, "name": name.strip(), "about": about,
            "when": when, **({"loop": loop} if loop else {}),
            **({"length": length} if length else {}),
            **({"seats": seats} if seats else {}), "poses": poses, "actors": actors}


# -- reading ---------------------------------------------------------------------------------

def _read_dir(d: pathlib.Path, source: str) -> tuple[dict, list]:
    found, dropped = {}, []
    if not d.is_dir():
        return found, dropped
    for f in sorted(d.glob("*.json")):
        try:
            if f.stat().st_size > MAX_BYTES * 2:
                raise Refused("too large")
            s = check(json.loads(f.read_text(encoding="utf-8")))
            if s["id"] != f.stem:
                raise Refused(f"id {s['id']!r} does not match its file name")
            found[s["id"]] = {**s, "source": source}
        except (OSError, ValueError) as exc:
            dropped.append({"file": f.name, "why": str(exc)})
    return found, dropped


def _off(root: str) -> list:
    try:
        data = json.loads(pathlib.Path(root, *STATE).read_text(encoding="utf-8"))
        off = data.get("off") if isinstance(data, dict) else None
        return [x for x in off if isinstance(x, str) and _ID.fullmatch(x)][:500] \
            if isinstance(off, list) else []
    except (OSError, ValueError):
        return []


def library(root: str) -> dict:
    """Every scene, checked: the shipped set, then this brain's own (which replace a
    shipped scene of the same id), each saying whether it is on."""
    shipped, d1 = _read_dir(BUILTIN, "shipped")
    added, d2 = _read_dir(pathlib.Path(root, *SUBDIR), "added")
    off = set(_off(root))
    scenes = [{**s, "on": s["id"] not in off}
              for s in {**shipped, **added}.values()]
    out = {"format": FORMAT, "scenes": scenes,
           "vocabulary": {"pieces": ["line", "circle", "rect", "text", "head"],
                          "colours": list(COLOURS), "events": list(EVENTS),
                          "anchors": list(ANCHORS)}}
    if d1 or d2:
        out["dropped"] = d1 + d2
    return out


# -- writing ---------------------------------------------------------------------------------

def _atomic(path: pathlib.Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".incoming-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def add(root: str, scene) -> dict:
    """Add a scene to this brain, or replace one of its own or a shipped one by id."""
    s = check(scene)
    d = pathlib.Path(root, *SUBDIR)
    with _lock:
        existing = {f.stem for f in d.glob("*.json")} if d.is_dir() else set()
        if s["id"] not in existing and len(existing) >= MAX_ADDED:
            raise Refused(f"a brain holds at most {MAX_ADDED} added scenes")
        _atomic(d / f"{s['id']}.json", s)
    return library(root)


def change(root: str, sid: str, *, on=None, remove=False) -> dict:
    """Switch a scene on or off, or remove one this brain added. A shipped scene is
    never removed -- it can only be switched off."""
    if not isinstance(sid, str) or not _ID.fullmatch(sid):
        raise Refused("no such scene")
    with _lock:
        if remove:
            f = pathlib.Path(root, *SUBDIR, f"{sid}.json")
            if not f.is_file():
                raise Refused(f"{sid!r} is not a scene this brain added; shipped scenes "
                              "can be switched off, not removed")
            f.unlink()
            # gone, so not "off" either: added again later, it starts on
            on = True if on is None else on
        if on is not None:
            off = [x for x in _off(root) if x != sid]
            if not on:
                off.append(sid)
            _atomic(pathlib.Path(root, *STATE), {"off": off})
    return library(root)
