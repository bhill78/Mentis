"""Lab workspaces: saved workspaces and named layouts of the Workspace Lab. BESIDE the record.

Owner decisions in "Mentis Fluid Workspace" (the multi-page audit's follow-ups, turn #109):
a conversation's arrangement may be SAVED, and named layouts are kept, in the Brain rather
than in one browser, so they are there on any tab, browser or computer using the same Brain.

    <corpus>/presentation/workspaces.json              named layouts, and the defaults
    <corpus>/presentation/workspaces/<conversation>.json   that conversation's saved workspace

WHAT THEY ARE: presentation, and nothing else -- the shape of the Lab's pages and zones and
what each zone shows, by REFERENCE only: a Turn id, a block's or section's key, an
attachment's key. Never Markdown, never bytes, never a source record. A saved workspace is
one per conversation; saving again replaces it. A named layout holds rules (follow the
selection, narrowed) and only the pins its owner chose to keep. Both may say where the
conversation is drawn (docked, floating, an icon, or full).

WHY NOT THE RECORD: for the reasons `mentis/presentation.py` gives for looks. Nothing that
forms context, retrieves, delivers or governs reads this, and no worker can: only the
`/api/presentation/workspaces` routes do, and a worker grant is refused on them by `_api`.

WHAT IT TRUSTS: nothing it is sent, nor anything it reads from disk. Every workspace and
layout is checked on the way in and again on every read: its format and version, the size of
everything in it, and that every reference has the shape of one. What fails is refused (sent)
or left out and counted (read).

CONFLICTS: the later save wins. It is current state, overwritten in place; nothing here is an
act or a history.

A MISSING OR UNREADABLE FOLDER IS DEFAULTS, NEVER AN ERROR.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import re
import tempfile
import threading
import time

DIR = "presentation"
LIBRARY = "workspaces.json"
SAVED = "workspaces"
VERSION = 1

WORKSPACE_FORMAT = "mentis.workspace"
LAYOUT_FORMAT = "mentis.workspace-layout"

#: Bounds, not policy: enough for any workspace anybody will lay out, and a limit on what a
#: file can make the interface draw.
MAX_LAYOUTS = 100
MAX_DEFAULTS = 5000
MAX_BYTES = 256 * 1024
MAX_PAGES = 30
MAX_ZONES = 40           # on one page
MAX_SLOTS = 100          # in one zone
MAX_DEPTH = 8
MAX_KIDS = 12
MAX_SIZES = 200
MAX_LABEL = 200
MAX_KEY = 300

FOLLOWS = ("post", "text", "sections", "media")
KINDS = ("text", "table", "chart", "diagram", "timeline", "figure", "media", "file", "other")
SIZES = ("compact", "medium", "large")
PAGE_KINDS = ("post", "suggested", "owner")
#: Where the conversation is drawn. `full` is the conversation filling the Lab.
PRESENCES = ("docked", "floating", "icon", "full")
REPLIES = "replies"

#: a conversation id, as it names its saved workspace's file: no `.`, no `:`, no separator
_CONVERSATION = re.compile(r"[A-Za-z0-9_-]{1,80}")
#: names Windows keeps for devices, whatever follows them
_DEVICES = re.compile(r"(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])")
#: a context, as the Lab names one: `conversation:<id>`
_CTX = re.compile(r"[a-z]{1,20}:[A-Za-z0-9_.:-]{1,80}")
_TURN = re.compile(r"[A-Za-z0-9_.:-]{1,80}")
_NODE = re.compile(r"[A-Za-z0-9_-]{1,80}")
_LAYOUT_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")

_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


class Refused(ValueError):
    """What was sent is not a workspace or a layout. The message says what is wrong."""


def _lock(root: str) -> threading.Lock:
    key = str(pathlib.Path(root).resolve())
    with _locks_lock:
        return _locks.setdefault(key, threading.Lock())


def _dir(root: str) -> pathlib.Path:
    return pathlib.Path(root) / DIR


def empty() -> dict:
    return {"version": VERSION, "layouts": [], "defaults": {"all": None, "conversations": {}}}


# -- checking --------------------------------------------------------------------------------

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


def _sizes(v, where) -> dict | None:
    """A copy's size preferences, by object key."""
    if v is None:
        return None
    if not isinstance(v, dict) or len(v) > MAX_SIZES:
        raise Refused(f"{where}: sizes must be a mapping of at most {MAX_SIZES} entries")
    out = {}
    for k, s in v.items():
        _text(k, f"{where}.sizes", most=MAX_KEY)
        if s not in SIZES:
            raise Refused(f"{where}.sizes: {s!r} is not one of {list(SIZES)}")
        out[k] = s
    return out or None


def _filter(v, where) -> dict | None:
    if v is None:
        return None
    if not isinstance(v, dict) or set(v) - {"type", "name", "media", "page"}:
        raise Refused(f"{where}: a filter names only type, name, media or page")
    return {k: _text(s, f"{where}.filter.{k}", most=60) for k, s in v.items()} or None


def _view(o: dict, where) -> dict:
    """A zone's own presentation: the kinds it shows and how it draws its media."""
    out = {}
    only = o.get("only")
    if only is not None:
        if not isinstance(only, list) or len(only) > len(KINDS) or \
                not all(k in KINDS for k in only):
            raise Refused(f"{where}: only must list kinds from {list(KINDS)}")
        if only:
            out["only"] = list(dict.fromkeys(only))
    media = o.get("media")
    if media is not None:
        if media not in ("carousel", "gallery"):
            raise Refused(f"{where}: media must be carousel or gallery")
        out["media"] = media
    return out


def _extra(out: dict, sizes) -> dict:
    if sizes:
        out["sizes"] = sizes
    return out


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


# -- a saved workspace: the session's own shape ------------------------------------------------

def _slot(s, where) -> dict:
    if not isinstance(s, dict):
        raise Refused(f"{where}: a slot is a mapping")
    sid = _match(_NODE, s.get("id"), f"{where}.id")
    sizes = _sizes(s.get("sizes"), where)
    kind = s.get("kind")
    if kind == "follow":
        if s.get("show") not in FOLLOWS:
            raise Refused(f"{where}: show must be one of {list(FOLLOWS)}")
        out = {"id": sid, "kind": "follow", "show": s["show"]}
        f = _filter(s.get("filter"), where)
        if f:
            out["filter"] = f
        return _extra(out, sizes)
    if kind == "pinned":
        out = {"id": sid, "kind": "pinned",
               "turn": _match(_TURN, s.get("turn"), f"{where}.turn"),
               "key": _text(s.get("key"), f"{where}.key", most=MAX_KEY),
               "label": _text(s.get("label"), f"{where}.label", blank=True)}
        if s.get("ctx") is not None:
            out["ctx"] = _match(_CTX, s.get("ctx"), f"{where}.ctx")
        return _extra(out, sizes)
    if kind == "empty":
        return _extra({"id": sid, "kind": "empty",
                       "label": _text(s.get("label"), f"{where}.label", blank=True)}, sizes)
    raise Refused(f"{where}: a slot follows, is pinned, or is an empty place")


def _tree(n, where, depth=0, count=None) -> dict:
    count = count if count is not None else [0]
    if not isinstance(n, dict) or depth > MAX_DEPTH:
        raise Refused(f"{where}: a zone tree at most {MAX_DEPTH} deep")
    if n.get("type") == "leaf":
        count[0] += 1
        if count[0] > MAX_ZONES:
            raise Refused(f"{where}: at most {MAX_ZONES} zones on a page")
        slots = n.get("slots")
        if not isinstance(slots, list) or len(slots) > MAX_SLOTS:
            raise Refused(f"{where}: a zone holds at most {MAX_SLOTS} slots")
        return {"type": "leaf", "id": _match(_NODE, n.get("id"), f"{where}.id"),
                "name": _text(n.get("name"), f"{where}.name", most=60),
                "slots": [_slot(s, f"{where}.slots[{i}]") for i, s in enumerate(slots)],
                **_view(n, where)}
    if n.get("type") != "split" or n.get("dir") not in ("row", "col"):
        raise Refused(f"{where}: a node is a zone or a split by row or col")
    kids, sizes = n.get("kids"), n.get("sizes")
    if not isinstance(kids, list) or not isinstance(sizes, list) or \
            not 2 <= len(kids) <= MAX_KIDS or len(kids) != len(sizes):
        raise Refused(f"{where}: a split has 2..{MAX_KIDS} children, each with its share")
    shares = [_num(s, f"{where}.sizes", 0, 1) for s in sizes]
    if abs(sum(shares) - 1) > 0.01:
        raise Refused(f"{where}: shares must add up to 1")
    return {"type": "split", "dir": n["dir"], "sizes": shares,
            "kids": [_tree(k, f"{where}.kids[{i}]", depth + 1, count) for i, k in enumerate(kids)]}


def _page(p, where) -> dict:
    if not isinstance(p, dict) or p.get("kind") not in PAGE_KINDS:
        raise Refused(f"{where}: a page is post, suggested or owner")
    out = {"id": _text(p.get("id"), f"{where}.id", most=MAX_KEY), "kind": p["kind"]}
    if out["id"] == REPLIES:
        raise Refused(f"{where}: Replies & details is never saved")
    if p.get("label") is not None:
        out["label"] = _text(p.get("label"), f"{where}.label", most=120)
    if p.get("turn") is not None:
        out["turn"] = _match(_TURN, p.get("turn"), f"{where}.turn")
    if p.get("scope") is not None:
        out["scope"] = _text(p.get("scope"), f"{where}.scope", most=MAX_KEY)
    out["tree"] = _tree(p.get("tree"), f"{where}.tree")
    return out


def check_workspace(w) -> dict:
    """A saved workspace, as the Lab's session holds it, or Refused."""
    if not isinstance(w, dict):
        raise Refused("a workspace is a mapping")
    if w.get("format") != WORKSPACE_FORMAT:
        raise Refused(f"not a {WORKSPACE_FORMAT}")
    if w.get("version") != VERSION:
        raise Refused(f"workspace version {w.get('version')!r} is not {VERSION}")
    if len(json.dumps(w, ensure_ascii=False)) > MAX_BYTES:
        raise Refused(f"a workspace may be at most {MAX_BYTES} bytes")
    pages = w.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES:
        raise Refused(f"a workspace has 1..{MAX_PAGES} pages")
    got = [_page(p, f"pages[{i}]") for i, p in enumerate(pages)]
    if sum(p["kind"] == "post" for p in got) != 1:
        raise Refused("a workspace has exactly one Post page")
    if len({p["id"] for p in got}) != len(got):
        raise Refused("two pages share an id")
    active = w.get("active")
    if active != REPLIES and active not in {p["id"] for p in got}:
        active = "post"
    out = {"format": WORKSPACE_FORMAT, "version": VERSION, "pages": got, "active": active,
           "selected": _match(_TURN, w["selected"], "selected") if w.get("selected") else None}
    where = presence(w.get("presence"))
    if where:
        out["presence"] = where
    if isinstance(w.get("saved"), (int, float)) and not isinstance(w.get("saved"), bool):
        out["saved"] = float(w["saved"])
    return out


# -- a named layout: shape and rules (ui/src/lab/layouts.ts) ---------------------------------

def _lslot(s, where) -> dict:
    if not isinstance(s, dict):
        raise Refused(f"{where}: a slot is a mapping")
    sizes = _sizes(s.get("sizes"), where)
    if "follow" in s:
        if s["follow"] not in FOLLOWS:
            raise Refused(f"{where}: follow must be one of {list(FOLLOWS)}")
        out = {"follow": s["follow"]}
        f = _filter(s.get("filter"), where)
        if f:
            out["filter"] = f
        return _extra(out, sizes)
    if "pinned" in s:
        p = s["pinned"]
        if not isinstance(p, dict):
            raise Refused(f"{where}: a pin is a locator")
        return _extra({"pinned": {"ctx": _match(_CTX, p.get("ctx"), f"{where}.ctx"),
                                  "turn": _match(_TURN, p.get("turn"), f"{where}.turn"),
                                  "key": _text(p.get("key"), f"{where}.key", most=MAX_KEY),
                                  "label": _text(p.get("label"), f"{where}.label", blank=True)}},
                      sizes)
    if "empty" in s:
        return _extra({"empty": _text(s["empty"], f"{where}.empty", blank=True)}, sizes)
    raise Refused(f"{where}: a slot follows, is pinned, or is an empty place")


def _lnode(n, where, depth=0, count=None) -> dict:
    count = count if count is not None else [0]
    if not isinstance(n, dict) or depth > MAX_DEPTH:
        raise Refused(f"{where}: a zone tree at most {MAX_DEPTH} deep")
    if "zone" in n:
        count[0] += 1
        if count[0] > MAX_ZONES:
            raise Refused(f"{where}: at most {MAX_ZONES} zones on a page")
        slots = n.get("slots")
        if not isinstance(slots, list) or len(slots) > MAX_SLOTS:
            raise Refused(f"{where}: a zone holds at most {MAX_SLOTS} slots")
        return {"zone": _text(n["zone"], f"{where}.zone", most=60),
                "slots": [_lslot(s, f"{where}.slots[{i}]") for i, s in enumerate(slots)],
                **_view(n, where)}
    if n.get("split") not in ("row", "col"):
        raise Refused(f"{where}: a node is a zone or a split by row or col")
    kids, ratios = n.get("kids"), n.get("ratios")
    if not isinstance(kids, list) or not isinstance(ratios, list) or \
            not 2 <= len(kids) <= MAX_KIDS or len(kids) != len(ratios):
        raise Refused(f"{where}: a split has 2..{MAX_KIDS} children, each with its share")
    shares = [_num(r, f"{where}.ratios", 0, 1) for r in ratios]
    if abs(sum(shares) - 1) > 0.01:
        raise Refused(f"{where}: shares must add up to 1")
    return {"split": n["split"], "ratios": shares,
            "kids": [_lnode(k, f"{where}.kids[{i}]", depth + 1, count) for i, k in enumerate(kids)]}


def check_layout(l) -> dict:
    """A named layout, or Refused."""
    if not isinstance(l, dict):
        raise Refused("a layout is a mapping")
    if l.get("format") != LAYOUT_FORMAT:
        raise Refused(f"not a {LAYOUT_FORMAT}")
    if l.get("version") != VERSION:
        raise Refused(f"layout version {l.get('version')!r} is not {VERSION}")
    if len(json.dumps(l, ensure_ascii=False)) > MAX_BYTES:
        raise Refused(f"a layout may be at most {MAX_BYTES} bytes")
    pages = l.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES:
        raise Refused(f"a layout has 1..{MAX_PAGES} pages")
    got = []
    for i, p in enumerate(pages):
        if not isinstance(p, dict) or p.get("kind") not in PAGE_KINDS:
            raise Refused(f"pages[{i}]: a page is post, suggested or owner")
        page = {"kind": p["kind"]}
        if p.get("label") is not None:
            page["label"] = _text(p["label"], f"pages[{i}].label", most=60)
        page["tree"] = _lnode(p.get("tree"), f"pages[{i}].tree")
        got.append(page)
    active = l.get("active", 0)
    active = active if isinstance(active, int) and not isinstance(active, bool) \
        and 0 <= active < len(got) else 0
    out = {"format": LAYOUT_FORMAT, "version": VERSION,
           "id": _match(_LAYOUT_ID, l.get("id"), "id"),
           "name": " ".join(_text(l.get("name"), "name", most=120).split()) or "Layout",
           "saved": _text(l.get("saved") or "-", "saved", most=40),
           "pages": got, "active": active}
    where = presence(l.get("presence"))
    if where:
        out["presence"] = where
    return out


# -- reading ---------------------------------------------------------------------------------

def library(root: str) -> dict:
    """The named layouts and the defaults. Defaults when there is nothing readable.

    Everything read is checked again, as if it had just been sent. A layout that fails is
    left out and counted in `dropped`; a default that names no layout here is left out."""
    path = _dir(root) / LIBRARY
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty()
    except (OSError, ValueError):
        out = empty()
        out["unreadable"] = f"{LIBRARY} could not be read; showing the defaults"
        return out
    if not isinstance(data, dict) or data.get("version") != VERSION:
        out = empty()
        out["unreadable"] = f"{LIBRARY} is not a version {VERSION} list; showing the defaults"
        return out
    out = empty()
    layouts, dropped = [], 0
    raw = data.get("layouts")
    for l in raw if isinstance(raw, list) else []:
        try:
            layouts.append(check_layout(l))
        except Refused:
            dropped += 1
    seen, kept = set(), []
    for l in layouts[:MAX_LAYOUTS]:
        if l["id"] not in seen:
            seen.add(l["id"])
            kept.append(l)
    out["layouts"] = kept
    d = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
    out["defaults"]["all"] = d.get("all") if d.get("all") in seen else None
    convs = d.get("conversations") if isinstance(d.get("conversations"), dict) else {}
    out["defaults"]["conversations"] = {
        c: v for c, v in list(convs.items())[:MAX_DEFAULTS]
        if isinstance(c, str) and _CTX.fullmatch(c) and v in seen}
    if dropped:
        out["dropped"] = dropped
    return out


def _saved_path(root: str, conversation: str) -> pathlib.Path:
    """The file of one conversation's saved workspace, never anywhere but in `workspaces/`."""
    _match(_CONVERSATION, conversation, "conversation")
    if _DEVICES.fullmatch(conversation):
        raise Refused(f"conversation: {conversation!r} is not well formed")
    folder = (_dir(root) / SAVED).resolve()
    path = (folder / f"{conversation}.json").resolve()
    if path.parent != folder or path.name != f"{conversation}.json":
        raise Refused(f"conversation: {conversation!r} is not well formed")
    return path


def saved(root: str, conversation: str) -> dict:
    """One conversation's saved workspace: `{"workspace": ...}`, null when it has none."""
    path = _saved_path(root, conversation)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"workspace": None}
    except (OSError, ValueError):
        return {"workspace": None, "unreadable": "the saved workspace could not be read"}
    try:
        return {"workspace": check_workspace(data)}
    except Refused as exc:
        return {"workspace": None, "unreadable": f"the saved workspace is not one: {exc}"}


# -- writing ---------------------------------------------------------------------------------

class Unreadable(RuntimeError):
    """The library on disk could not be read, so nothing is written over it."""


def _for_writing(root: str) -> dict:
    data = library(root)
    if "unreadable" in data:
        raise Unreadable(f"{data['unreadable']}; it was left exactly as it is")
    data.pop("dropped", None)
    return data


def _atomic(path: pathlib.Path, data: dict):
    """All or nothing: a temporary file, then a rename over the old one."""
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


def save_workspace(root: str, conversation: str, workspace) -> dict:
    """Keep this conversation's workspace, replacing the one it had. The later save wins."""
    path = _saved_path(root, conversation)
    w = check_workspace(workspace)
    w["saved"] = time.time()
    with _lock(root):
        _atomic(path, w)
    return {"workspace": w}


def forget_workspace(root: str, conversation: str) -> dict:
    path = _saved_path(root, conversation)
    with _lock(root):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    return {"workspace": None}


def save_layout(root: str, layout) -> dict:
    """Keep a named layout: a new one, or the one of the same id replaced."""
    l = check_layout(layout)
    with _lock(root):
        data = _for_writing(root)
        rest = [x for x in data["layouts"] if x["id"] != l["id"]]
        if len(rest) >= MAX_LAYOUTS:
            raise Refused(f"a brain may keep at most {MAX_LAYOUTS} layouts; delete one first")
        data["layouts"] = rest + [l]
        _atomic(_dir(root) / LIBRARY, data)
        return data


def remove_layout(root: str, layout_id: str) -> dict:
    """Delete a named layout; defaults that named it name none."""
    _match(_LAYOUT_ID, layout_id, "layout")
    with _lock(root):
        data = _for_writing(root)
        if not any(l["id"] == layout_id for l in data["layouts"]):
            raise LookupError(f"there is no layout {layout_id}")
        data["layouts"] = [l for l in data["layouts"] if l["id"] != layout_id]
        d = data["defaults"]
        if d["all"] == layout_id:
            d["all"] = None
        d["conversations"] = {c: v for c, v in d["conversations"].items() if v != layout_id}
        _atomic(_dir(root) / LIBRARY, data)
        return data


def set_default(root: str, *, ctx, layout) -> dict:
    """The layout every conversation (`ctx` None), or one, starts from; `layout` None: none."""
    if layout is not None:
        _match(_LAYOUT_ID, layout, "layout")
    if ctx is not None:
        _match(_CTX, ctx, "ctx")
    with _lock(root):
        data = _for_writing(root)
        if layout is not None and not any(l["id"] == layout for l in data["layouts"]):
            raise LookupError(f"there is no layout {layout}")
        d = data["defaults"]
        if ctx is None:
            d["all"] = layout
        elif layout is None:
            d["conversations"].pop(ctx, None)
        else:
            if ctx not in d["conversations"] and len(d["conversations"]) >= MAX_DEFAULTS:
                raise Refused(f"at most {MAX_DEFAULTS} conversations may have a default")
            d["conversations"][ctx] = layout
        _atomic(_dir(root) / LIBRARY, data)
        return data


def bring_in(root: str, body) -> dict:
    """Layouts a browser kept before the Brain kept them, moved in once.

    A layout whose id the Brain already has is left as the Brain has it; a default is taken
    only where the Brain has none. What cannot be read is counted, never kept."""
    if not isinstance(body, dict):
        raise Refused("send the browser's layouts and defaults")
    raw = body.get("layouts")
    if not isinstance(raw, list) or len(raw) > MAX_LAYOUTS:
        raise Refused(f"at most {MAX_LAYOUTS} layouts at once")
    with _lock(root):
        data = _for_writing(root)
        have = {l["id"] for l in data["layouts"]}
        added, skipped = [], 0
        for l in raw:
            try:
                good = check_layout(l)
            except Refused:
                skipped += 1
                continue
            if good["id"] in have:
                continue
            if len(data["layouts"]) >= MAX_LAYOUTS:
                skipped += 1
                continue
            data["layouts"].append(good)
            have.add(good["id"])
            added.append(good["id"])
        changed = bool(added)
        d = body.get("defaults") if isinstance(body.get("defaults"), dict) else {}
        if data["defaults"]["all"] is None and d.get("all") in have:
            data["defaults"]["all"] = d["all"]
            changed = True
        ctxs = d.get("ctx") if isinstance(d.get("ctx"), dict) else {}
        for c, v in list(ctxs.items())[:MAX_DEFAULTS]:
            if isinstance(c, str) and _CTX.fullmatch(c) and v in have and \
                    c not in data["defaults"]["conversations"] and \
                    len(data["defaults"]["conversations"]) < MAX_DEFAULTS:
                data["defaults"]["conversations"][c] = v
                changed = True
        if changed:
            _atomic(_dir(root) / LIBRARY, data)
        return {**data, "added": added, "skipped": skipped}
