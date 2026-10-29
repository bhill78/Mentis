"""Fluid arrangements (stage F4a): the saved layout of the Home, and of any
Conversation, BESIDE the record.

    GET  /fluid/api/arrangements/<key>   {"key", "layout", "saved"}; null: none
    POST /fluid/api/arrangements/<key>   {"layout", "op"?}: keep it

`<key>` is `home` or a Conversation's id. Kept where the Workspace Lab keeps
its saved workspaces, and by its means (`mentis/fluid/_checks.py`, moved from
the Lab's `lab_workspaces.py` when the Lab itself was removed): under
`<corpus>/presentation/`, one file per key, written whole by a temporary file
and a rename, under the same lock:

    <corpus>/presentation/fluid-arrangements/<key>.json

WHAT ONE IS: presentation, and nothing else -- a tree of zones, split by row
or column with each child's share, each zone saying what it shows (`show`: a
word, `briefing`, `work`, `needs-you`, ...), what it is called, and a few
options of its own (a Work zone's tab, say). References by shape only; never
Markdown, never bytes, never a source record. Nothing that forms context,
retrieves, delivers or governs reads it.

THE HOME'S ARRANGEMENT, as the Home client keeps it (`home`): a split
of zones, each zone's `show` one of the Home's collections --
`briefing`, `work`, `needs-you`, `for-you`, `activity` -- and what the
owner chose in a zone kept in that zone's `options`:

    {"format": "mentis.fluid-arrangement", "version": 1,
     "tree": {"type": "split", "dir": "row", "sizes": [0.5, 0.5], "kids": [
        {"type": "zone", "id": "work", "show": "work",
         "options": {"tab": "in-flight"}},
        {"type": "zone", "id": "briefing", "show": "briefing",
         "options": {"period": "evening", "collapsed": true}}]},
     "presence": {...}?}

    options.tab        the Work zone's tab: a `?state=` of home/work --
                       all, needs-you, in-flight, completed, ended,
                       unknown (HOME_OPTIONS)
    options.period     the Briefing zone's period: morning, lunch or
                       evening; absent or null is the period it is now
    options.collapsed  true when the zone is collapsed

Each of the three may be null (not chosen). Any zone may carry them, and
other options of a plain shape (`_options`); these three are checked
for what they mean wherever they appear.

WHAT IT TRUSTS: nothing it is sent, nor anything it reads from disk -- the
Lab's rule. Every arrangement is checked on the way in and again on every
read, with the Lab's own checkers and bounds: its format and version, its
size, its depth, how many zones and children, that every share is a number
and they add up to one, and that every name has the shape of one. What fails
is refused (sent, 400) or read as none and said why (read).

CONFLICTS: the later save wins. It is current state, overwritten in place;
nothing here is an act or a history. AN OPERATION KEY (`op`) makes a retry of
a lost answer safe: the same key with the same arrangement writes nothing
again -- even after a later save, which it must not undo -- and is answered
with the arrangement as it now stands, `replayed`; the same key with a
different arrangement is refused (422). The last
MAX_OPS keys are kept beside the arrangement.

THE WORKSPACE YOU SHAPE (Fluid completion, stream A), each part optional so
every arrangement kept before reads as it did:

    zone.slot     what a conversation's zone shows (SLOT): whether it
                  follows what is read, the Show filter, the objects kept in
                  it by live address, how it presents them and how it looks,
                  and the post it is held on instead of following (`pin`)
                    {"follow": true, "pin": <post id>?, "show": "objects",
                     "kinds": [...]?,
                     "items": ["live:<post>:<key>", ...],
                     "present": "cards", "appearance": {...}?}
    pages         the place's own pages after This post, each a tree:
                    [{"id", "title", "tree", "object"?, "setAside"?}]
    setAside      sections displaced from This post by a layout, still
                  recoverable; a Page keeps the same list beside its tree
    conversation  the boundaries the reader dragged: {"width", "replies"}
                  in pixels (the conversation column, the replies panel)

THE REST OF THE PLACE (Fluid completion, stream D; #188 "each place sets a
default, and any zone can override it"; pinned threads saved per place):

    appearance    the place's default look, which every zone without its
                  own reads: {"panel", "content", "opacity"} as a slot's
    threads       the threads pinned in this place, as tabs, and which tab
                  is shown: {"pinned": [<post id>, ...], "active": <id>?}

NAMED LAYOUTS AND DEFAULTS (#107, adm-c93a 5.5) are kept beside them, in
`<corpus>/presentation/fluid-layouts.json`: a named layout is an arrangement
with its CONTENT TAKEN OUT -- no kept objects, no page's object, no pinned
thread, no zone held on a post, only the shape, each zone's rules and the place's default look, and
its own pages but none made of one object -- so it can be used for any
conversation; each
place kind (`home`, `conversation`, `unnamed`) may name the layout it starts
from (`layouts`, `save_layout`, `delete_layout`, `set_default`).

PRESETS (P12; Fluid Workspace #1010, #1011, #1012): four built-in named
layouts -- Triage, Focus, Oversight, Showcase -- each a Home arrangement and a
conversation's, shape only, every Stage zone following what is read. They are
the product's, not the Brain's: never written to the library, never edited or
deleted (`save_layout` and `delete_layout` refuse their ids), always listed
(`layouts()["presets"]`), and a place kind's default may name one. Applying
one changes a Page or place without changing defaults; defaults are an
explicit separate choice. A user who changes one saves the result under
their own name, and the preset stays as it was.
`share` is the conversation column's part of the width, which the client
turns into pixels (`conversation.width`) where it is applied.

A BRAND-NEW BRAIN -- no library and no arrangement ever saved -- starts Home
on Triage and conversations on Focus (`NEW_DEFAULTS`). A brain where anything
was arranged before keeps the defaults it has, none until chosen.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

from mentis.fluid import _checks as W

FORMAT = "mentis.fluid-arrangement"
VERSION = 2
VERSIONS = (1, 2)
FOLDER = "fluid-arrangements"
HOME = "home"
#: How many operation keys are remembered beside an arrangement.
MAX_OPS = 32
MAX_OP = 120
MAX_OPTIONS = 20
#: What a zone shows: a word, not a list -- the client says which it draws.
_SHOW = re.compile(r"[a-z][a-z0-9-]{0,39}")
_OPTION = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,39}")
#: A conversation zone's slot: what it shows of what is read, how it presents
#: it, and the backgrounds a zone or its content may have.
SHOWS = ("objects", "everything", "sections", "media", "files", "forms",
         "fillable", "kinds", "needs-you")
#: "across" (side by side, Objects round B7) was added; every earlier value stands.
PRESENTS = ("cards", "gallery", "slides", "list", "focus", "previews", "across")
BACKGROUNDS = ("transparent", "tinted", "solid")
#: A request kept in a zone from What needs you (#576).
_NEEDS_YOU = re.compile(r"needs-you:[A-Za-z0-9_-]{1,80}")
MAX_KINDS = 20
THIS_POST = "this-post"
#: Threads pinned in one place, each by its root post's id.
MAX_PINS = 20
MAX_FLOATS = 12
MAX_PREVIOUS = 20
#: Named layouts and the defaults each place kind starts from.
LAYOUTS = "fluid-layouts.json"
LAYOUT_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")
PLACES = ("home", "conversation", "unnamed")
MAX_LAYOUTS = 100
#: The Home's zone options and what each may be (see the module); None is
#: always allowed. Kept here rather than read from `home`, so a saved
#: arrangement is checked without the Home's readers.
HOME_OPTIONS = {
    "tab": ("all", "needs-you", "in-flight", "completed", "ended",
            "unknown"),
    "period": ("morning", "lunch", "evening"),
    "collapsed": (True, False),
}

Refused = W.Refused
#: The library on disk could not be read, so nothing is written over it.
Unreadable = W.Unreadable


class Conflict(ValueError):
    """An operation key already kept for a different arrangement: 422."""


# -- checking --------------------------------------------------------------------

def _options(v, where) -> dict | None:
    if v is None:
        return None
    if not isinstance(v, dict) or len(v) > MAX_OPTIONS:
        raise Refused(f"{where}: options are a mapping of at most "
                      f"{MAX_OPTIONS} entries")
    out = {}
    for k, x in v.items():
        W._match(_OPTION, k, f"{where}.options key")
        allowed = HOME_OPTIONS.get(k)
        if allowed is not None and x is not None and not any(
                x is a if isinstance(a, bool) else
                (isinstance(x, str) and x == a) for a in allowed):
            raise Refused(f"{where}.options.{k}: {x!r} is not one of "
                          f"{list(allowed)}")
        if x is None or isinstance(x, bool):
            out[k] = x
        elif isinstance(x, (int, float)):
            out[k] = W._num(x, f"{where}.options.{k}", -1e9, 1e9)
        else:
            out[k] = W._text(x, f"{where}.options.{k}", blank=True)
    return out or None


def _node(n, where, depth, count, ids) -> dict:
    if not isinstance(n, dict) or depth > W.MAX_DEPTH:
        raise Refused(f"{where}: a zone tree at most {W.MAX_DEPTH} deep")
    if n.get("type") == "zone":
        count[0] += 1
        if count[0] > W.MAX_ZONES:
            raise Refused(f"{where}: at most {W.MAX_ZONES} zones")
        zid = W._match(W._NODE, n.get("id"), f"{where}.id")
        if zid in ids:
            raise Refused(f"{where}: two zones share the id {zid!r}")
        ids.add(zid)
        out = {"type": "zone", "id": zid,
               "show": W._match(_SHOW, n.get("show"), f"{where}.show")}
        if n.get("name") is not None:
            out["name"] = W._text(n.get("name"), f"{where}.name", most=60)
        opts = _options(n.get("options"), where)
        if opts:
            out["options"] = opts
        if n.get("slot") is not None:
            out["slot"] = _slot(n.get("slot"), f"{where}.slot")
        # Fit to content (Fluid Focus): sized to what it holds along its
        # split; kept only as a boolean, anything else is not a choice.
        if isinstance(n.get("fit"), bool):
            out["fit"] = n["fit"]
        return out
    if n.get("type") != "split" or n.get("dir") not in ("row", "col"):
        raise Refused(f"{where}: a node is a zone or a split by row or col")
    kids, sizes = n.get("kids"), n.get("sizes")
    if not isinstance(kids, list) or not isinstance(sizes, list) or \
            not 2 <= len(kids) <= W.MAX_KIDS or len(kids) != len(sizes):
        raise Refused(f"{where}: a split has 2..{W.MAX_KIDS} children, each "
                      "with its share")
    shares = [W._num(s, f"{where}.sizes", 0, 1) for s in sizes]
    if abs(sum(shares) - 1) > 0.01:
        raise Refused(f"{where}: shares must add up to 1")
    return {"type": "split", "dir": n["dir"], "sizes": shares,
            "kids": [_node(k, f"{where}.kids[{i}]", depth + 1, count, ids)
                     for i, k in enumerate(kids)]}


def _slot(s, where) -> dict:
    """A conversation zone's content rule (see the module)."""
    if not isinstance(s, dict):
        raise Refused(f"{where}: a slot is a mapping")
    if not isinstance(s.get("follow"), bool):
        raise Refused(f"{where}.follow: true or false")
    show = s.get("show", "objects")
    if show not in SHOWS:
        raise Refused(f"{where}.show: {show!r} is not one of {list(SHOWS)}")
    out = {"follow": s["follow"], "show": show}
    # A following zone held on one post and its replies (P10b): the root's
    # id. A post is content, so a named layout drops it (_without_content).
    if s.get("pin") is not None:
        if not s["follow"]:
            raise Refused(f"{where}.pin: only a zone that follows is held "
                          "on a post")
        out["pin"] = W._match(W._TURN, s["pin"], f"{where}.pin")
    kinds = s.get("kinds")
    if kinds is not None:
        if not isinstance(kinds, list) or len(kinds) > MAX_KINDS:
            raise Refused(f"{where}.kinds: a list of at most {MAX_KINDS} kinds")
        got = list(dict.fromkeys(W._match(_SHOW, k, f"{where}.kinds")
                                 for k in kinds))
        if got:
            out["kinds"] = got
    items = s.get("items", [])
    if not isinstance(items, list) or len(items) > W.MAX_SLOTS:
        raise Refused(f"{where}.items: a list of at most {W.MAX_SLOTS} "
                      "objects")
    out["items"] = list(dict.fromkeys(_address(a, f"{where}.items")
                                      for a in items))
    present = s.get("present", "cards")
    if present not in PRESENTS:
        raise Refused(f"{where}.present: {present!r} is not one of "
                      f"{list(PRESENTS)}")
    out["present"] = present
    if s.get("appearance") is not None:
        out["appearance"] = _appearance(s.get("appearance"),
                                        f"{where}.appearance")
    if s.get("feed") is not None:
        feed = s["feed"]
        if not isinstance(feed, dict) or set(feed) - {"source", "options"}:
            raise Refused(f"{where}.feed: source and options only")
        if s.get("follow"):
            raise Refused(f"{where}.follow: false when a feed is present")
        feed_out = {"source": W._match(_SHOW, feed.get("source"), f"{where}.feed.source")}
        if feed.get("options") is not None:
            opts = _options(feed.get("options"), f"{where}.feed")
            if opts:
                feed_out["options"] = opts
        out["feed"] = feed_out
    return out


def _address(a, where) -> str:
    """A live object address, `live:<post>:<key>`, a request kept from
    What needs you, `needs-you:<request id>` (#576), or a 3D Brain object
    reference, `brain:<entry id>`: a reference, never content."""
    a = W._text(a, where, most=W.MAX_KEY)
    if _NEEDS_YOU.fullmatch(a):
        return a
    if a.startswith("brain:"):
        W._match(W._TURN, a[6:], f"{where}: brain entry id")
        return a
    if not a.startswith("live:") or a.count(":") < 2:
        raise Refused(f"{where}: {a!r} is not a live object address")
    return a


def _appearance(v, where) -> dict:
    if not isinstance(v, dict) or set(v) - {"panel", "content", "opacity"}:
        raise Refused(f"{where}: panel, content and opacity only")
    out = {}
    for k in ("panel", "content"):
        if v.get(k) is not None:
            if v[k] not in BACKGROUNDS:
                raise Refused(f"{where}.{k}: {v[k]!r} is not one of "
                              f"{list(BACKGROUNDS)}")
            out[k] = v[k]
    if v.get("opacity") is not None:
        out["opacity"] = W._num(v["opacity"], f"{where}.opacity", 0, 1)
    return out


def _pages(v) -> list:
    if not isinstance(v, list) or len(v) > W.MAX_PAGES - 1:
        raise Refused(f"pages: a list of at most {W.MAX_PAGES - 1} pages")
    out, ids = [], set()
    for i, p in enumerate(v):
        where = f"pages[{i}]"
        if not isinstance(p, dict):
            raise Refused(f"{where}: a page is a mapping")
        pid = W._match(W._NODE, p.get("id"), f"{where}.id")
        if pid in ids or pid == THIS_POST:
            raise Refused(f"{where}: two pages share the id {pid!r}")
        ids.add(pid)
        page_ids = set()
        count = [0]
        page = {"id": pid, "title": W._text(p.get("title"), f"{where}.title",
                                             most=60),
                "tree": _node(p.get("tree"), f"{where}.tree", 0, count, page_ids)}
        if p.get("setAside") is not None:
            aside = _set_aside(p.get("setAside"), f"{where}.setAside",
                               [0], page_ids)
            if aside:
                page["setAside"] = aside
        if p.get("object") is not None:
            page["object"] = _address(p.get("object"), f"{where}.object")
        if p.get("focus") is not None:
            focus = _focus(p.get("focus"), page_ids, f"{where}.focus")
            if focus:
                page["focus"] = focus
        out.append(page)
    return out


def _set_aside(v, where, count, ids) -> list:
    """Sections displaced from one Page by a layout, still recoverable."""
    if not isinstance(v, list) or len(v) > W.MAX_ZONES:
        raise Refused(f"{where}: a list of at most {W.MAX_ZONES} zones")
    out = []
    for i, raw in enumerate(v):
        zone = _node(raw, f"{where}[{i}]", 0, count, ids)
        if zone.get("type") != "zone":
            raise Refused(f"{where}[{i}]: one zone")
        out.append(zone)
    return out


def _conversation(v) -> dict:
    if not isinstance(v, dict) or set(v) - {"width", "replies"}:
        raise Refused("conversation: width and replies only")
    return {k: W._num(v[k], f"conversation.{k}", 0, 10000)
            for k in ("width", "replies") if v.get(k) is not None}


def _threads(v) -> dict:
    """The pinned threads: their roots' ids, in tab order, and the one shown."""
    if not isinstance(v, dict) or set(v) - {"pinned", "active"}:
        raise Refused("threads: pinned and active only")
    pinned = v.get("pinned", [])
    if not isinstance(pinned, list) or len(pinned) > MAX_PINS:
        raise Refused(f"threads.pinned: a list of at most {MAX_PINS} posts")
    out = {"pinned": list(dict.fromkeys(W._match(W._TURN, p, "threads.pinned")
                                        for p in pinned))}
    active = v.get("active")
    if active is not None:
        W._match(W._TURN, active, "threads.active")
        if active not in out["pinned"]:
            raise Refused("threads.active: one of the pinned threads")
        out["active"] = active
    return out


def _origin(o, where) -> dict:
    if not isinstance(o, dict) or set(o) - {"near", "side", "share"}:
        raise Refused(f"{where}: near, side and share only")
    side = o.get("side")
    if side not in ("left", "right", "top", "bottom"):
        raise Refused(f"{where}.side: left, right, top or bottom")
    origin = {"near": W._match(W._NODE, o.get("near"), f"{where}.near"),
              "side": side}
    if o.get("share") is not None:
        origin["share"] = W._num(o["share"], f"{where}.share", 0, 1)
    return origin


def _minimized(m, where) -> dict:
    if not isinstance(m, dict) or set(m) - {"from", "rect", "near", "at"}:
        raise Refused(f"{where}: from, rect, near and at only")
    frm = m.get("from")
    if frm not in ("column", "leaf", "float"):
        raise Refused(f"{where}.from: column, leaf or float")
    out = {"from": frm, "at": W._num(m.get("at"), f"{where}.at", 0, 1e16)}
    if m.get("rect") is not None:
        r = m["rect"]
        if not isinstance(r, dict) or set(r) - {"x", "y", "w", "h"}:
            raise Refused(f"{where}.rect: x, y, w and h only")
        out["rect"] = {
            "x": W._num(r.get("x"), f"{where}.rect.x", -100000, 100000),
            "y": W._num(r.get("y"), f"{where}.rect.y", -100000, 100000),
            "w": W._num(r.get("w"), f"{where}.rect.w", 1, 100000),
            "h": W._num(r.get("h"), f"{where}.rect.h", 1, 100000),
        }
    if m.get("near") is not None:
        out["near"] = _origin(m["near"], f"{where}.near")
    return out


def _focus(v, ids, where="focus") -> dict:
    """Fluid Focus placement, checked independently of rendered content."""
    if not isinstance(v, dict) or set(v) - {"primary", "column", "floats", "previous", "minimized"}:
        raise Refused(f"{where}: primary, column, floats, previous and minimized only")
    out = {}
    if v.get("column") is not None:
        out["column"] = _node(v["column"], f"{where}.column", 0, [0], ids)
        if out["column"].get("type") != "zone":
            raise Refused(f"{where}.column: one zone")
    floats = v.get("floats", [])
    if not isinstance(floats, list) or len(floats) > MAX_FLOATS:
        raise Refused(f"{where}.floats: a list of at most {MAX_FLOATS} floats")
    got = []
    for i, f in enumerate(floats):
        float_where = f"{where}.floats[{i}]"
        if not isinstance(f, dict) or set(f) - {"id", "zone", "x", "y", "w", "h", "origin", "min"}:
            raise Refused(f"{float_where}: id, zone, rectangle, origin and min only")
        fid = W._match(W._NODE, f.get("id"), f"{float_where}.id")
        if fid in ids:
            raise Refused(f"{float_where}: two places or contents share the id {fid!r}")
        ids.add(fid)
        zone = _node(f.get("zone"), f"{float_where}.zone", 0, [0], ids)
        if zone.get("type") != "zone":
            raise Refused(f"{float_where}.zone: one zone")
        item = {"id": fid, "zone": zone,
                "x": W._num(f.get("x"), f"{float_where}.x", -100000, 100000),
                "y": W._num(f.get("y"), f"{float_where}.y", -100000, 100000),
                "w": W._num(f.get("w"), f"{float_where}.w", 0.001, 100000),
                "h": W._num(f.get("h"), f"{float_where}.h", 0.001, 100000)}
        if f.get("origin") is not None:
            item["origin"] = _origin(f["origin"], f"{float_where}.origin")
        if "min" in f:
            if not isinstance(f["min"], bool):
                raise Refused(f"{float_where}.min: true or false")
            if f["min"]:
                item["min"] = True
        got.append(item)
    if got:
        out["floats"] = got
    if v.get("primary") is not None:
        primary = W._match(W._NODE, v["primary"], f"{where}.primary")
        content = ({z for z in ids if z not in {f["id"] for f in got}} |
                   {"conv"})
        if primary not in content:
            raise Refused(f"{where}.primary: the id of content in this arrangement")
        out["primary"] = primary
    previous = v.get("previous", [])
    if not isinstance(previous, list) or len(previous) > MAX_PREVIOUS:
        raise Refused(f"{where}.previous: a list of at most {MAX_PREVIOUS} ids")
    if previous:
        out["previous"] = [W._match(W._NODE, p, f"{where}.previous") for p in previous]
    if v.get("minimized") is not None:
        out["minimized"] = _minimized(v["minimized"], f"{where}.minimized")
    return out


def check(layout) -> dict:
    """An arrangement, as it is kept, or Refused."""
    if not isinstance(layout, dict):
        raise Refused("an arrangement is a mapping")
    if layout.get("format") != FORMAT:
        raise Refused(f"not a {FORMAT}")
    version = layout.get("version")
    if version not in VERSIONS:
        raise Refused(f"arrangement version {version!r} is not 1 or 2")
    if len(json.dumps(layout, ensure_ascii=False).encode("utf-8")) > W.MAX_BYTES:
        raise Refused(f"an arrangement may be at most {W.MAX_BYTES} bytes")
    ids = set()
    count = [0]
    out = {"format": FORMAT, "version": version,
           "tree": _node(layout.get("tree"), "tree", 0, count, ids)}
    if layout.get("setAside") is not None:
        aside = _set_aside(layout.get("setAside"), "setAside", [0], ids)
        if aside:
            out["setAside"] = aside
    where = W.presence(layout.get("presence"))
    if where:
        out["presence"] = where
    if layout.get("pages") is not None:
        pages = _pages(layout.get("pages"))
        if pages:
            out["pages"] = pages
    if layout.get("conversation") is not None:
        conv = _conversation(layout.get("conversation"))
        if conv:
            out["conversation"] = conv
    if layout.get("appearance") is not None:
        out["appearance"] = _appearance(layout.get("appearance"), "appearance")
    if layout.get("threads") is not None:
        threads = _threads(layout.get("threads"))
        if threads["pinned"]:
            out["threads"] = threads
    if layout.get("focus") is not None:
        focus = _focus(layout.get("focus"), ids)
        if focus:
            out["focus"] = focus
    return out


def _without_content(n) -> dict:
    """A tree with every kept object taken out: its shape and its rules."""
    if n.get("type") == "split":
        return {**n, "kids": [_without_content(k) for k in n["kids"]]}
    if "slot" in n:
        slot = {k: v for k, v in n["slot"].items() if k != "pin"}
        return {**n, "slot": {**slot, "items": []}}
    return n


def _shape_focus(focus, tree) -> dict:
    shaped = {}
    if "column" in focus and focus["column"].get("slot") is not None and focus["column"].get("show") != "object":
        shaped["column"] = _without_content(focus["column"])
    floats = [{**f, "zone": _without_content(f["zone"])} for f in focus.get("floats", [])
              if f["zone"].get("slot") is not None and f["zone"].get("show") != "object"]
    if floats:
        shaped["floats"] = floats
    kept_ids = {z["id"] for z in ([shaped["column"]] if "column" in shaped else [])}
    kept_ids.update(f["zone"]["id"] for f in floats)

    def add_ids(n):
        if n["type"] == "zone":
            kept_ids.add(n["id"])
        else:
            for k in n["kids"]:
                add_ids(k)

    add_ids(tree)
    if focus.get("primary") in kept_ids:
        shaped["primary"] = focus["primary"]
    return shaped


def shape_of(layout) -> dict:
    """A checked arrangement as a named layout keeps it: no content. A page
    made of one object (Open as page) is that object's, so it is not kept;
    the owner's own pages are, emptied. Pinned threads are this place's
    posts, so they are not kept either; the default look is."""
    out = {**layout, "tree": _without_content(layout["tree"])}
    out.pop("threads", None)
    out.pop("setAside", None)
    pages = []
    for p in layout.get("pages", []):
        if "object" in p:
            continue
        page = {**p, "tree": _without_content(p["tree"])}
        page.pop("setAside", None)
        if "focus" in page:
            focus = _shape_focus(page["focus"], page["tree"])
            if focus:
                page["focus"] = focus
            else:
                page.pop("focus")
        pages.append(page)
    out.pop("pages", None)
    if pages:
        out["pages"] = pages
    if "focus" in out:
        shaped = _shape_focus(out["focus"], out["tree"])
        if shaped:
            out["focus"] = shaped
        else:
            out.pop("focus", None)
    return out


def check_key(key) -> str:
    """`home`, or what has the shape of a Conversation's id. Whether the
    record holds that Conversation is the route's to ask."""
    if key == HOME:
        return key
    W._match(W._CONVERSATION, key, "key")
    if W._DEVICES.fullmatch(key):
        raise Refused(f"key: {key!r} is not well formed")
    return key


def _path(root, key):
    check_key(key)
    folder = (W._dir(root) / FOLDER).resolve()
    path = (folder / f"{key}.json").resolve()
    if path.parent != folder or path.name != f"{key}.json":
        raise Refused(f"key: {key!r} is not well formed")
    return path


def _digest(layout) -> str:
    return hashlib.sha256(json.dumps(layout, sort_keys=True,
                                     ensure_ascii=True).encode()).hexdigest()


def _ops(v) -> list:
    """The operation keys kept beside an arrangement: a list of [op, digest]
    pairs of text, or Refused -- what the file holds is checked as what is
    sent is."""
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > MAX_OPS:
        raise Refused(f"ops: a list of at most {MAX_OPS} operation keys")
    for o in v:
        if not (isinstance(o, list) and len(o) == 2
                and all(isinstance(x, str) and 0 < len(x) <= MAX_OP
                        for x in o)):
            raise Refused("ops: each is an [operation key, digest] pair")
    return [list(o) for o in v]


def _saved(v) -> float | None:
    if v is None:
        return None
    return float(W._num(v, "saved", 0, 1e11))


def _on_disk(path) -> tuple[dict | None, list, float | None, str | None]:
    """(arrangement, op keys, when it was saved, why it is unreadable) as the
    file now holds them -- read ONCE, and every part of it checked again as
    if it had just been sent. Whatever the file holds, valid JSON or not,
    the answer is these four or the reason it is not: never an exception.
    A file that is not wholly an arrangement is unreadable and nothing of it
    is used -- not its operation keys either, which a save then replaces."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [], None, None
    except (OSError, ValueError, RecursionError):
        return None, [], None, "the saved arrangement could not be read"
    if not isinstance(data, dict):
        return None, [], None, "the saved arrangement is not one"
    try:
        return (check(data.get("layout")), _ops(data.get("ops")),
                _saved(data.get("saved")), None)
    except Refused as exc:
        return None, [], None, f"the saved arrangement is not one: {exc}"
    except Exception as exc:                              # noqa: BLE001
        return None, [], None, ("the saved arrangement is not one: "
                                f"{type(exc).__name__}")


# -- reading and writing ---------------------------------------------------------

def arrangement(root, key) -> dict:
    """The saved arrangement for `key`: `{"key", "layout", "saved"}`, with
    `layout` null when there is none -- or none readable, said why
    (`unreadable`)."""
    layout, _ops, saved, why = _on_disk(_path(root, key))
    out = {"key": key, "layout": layout, "saved": saved}
    if why:
        out["unreadable"] = why
    return out


def save(root, key, body) -> dict:
    """Keep `body["layout"]` as `key`'s arrangement, replacing what it had.
    The later save wins; an operation key replays (see the module)."""
    if not isinstance(body, dict):
        raise Refused("send {\"layout\": ..., \"op\"?: ...}")
    path = _path(root, key)
    layout = check(body.get("layout"))
    op = body.get("op")
    if op is not None:
        op = W._text(op, "op", most=MAX_OP)
    digest = _digest(layout)
    with W._lock(root):
        _layout, ops, _saved_at, _why = _on_disk(path)
        if op is not None:
            for k, d in ops:
                if k != op:
                    continue
                if d != digest:
                    raise Conflict("operation key already used for a "
                                   "different arrangement")
                out = arrangement(root, key)
                return {**out, "replayed": True}
        _keep_new_defaults(root)
        saved = time.time()
        if op is not None:
            ops = (ops + [[op, digest]])[-MAX_OPS:]
        W._atomic(path, {"key": key, "layout": layout, "saved": saved,
                         "ops": ops})
    return {"key": key, "layout": layout, "saved": saved, "replayed": False}


# -- presets ------------------------------------------------------------------------

#: The Home's names for its collections (ui/src/fluid/Home.tsx COLLECTIONS).
_HOME_NAMES = {"conversation": "Conversation", "briefing": "Daily Briefing",
               "work": "Work", "needs-you": "Needs you", "for-you": "For you",
               "activity": "Activity", "kept": "Kept"}
#: The looks the zone menu offers by name (ui/src/fluid/present/types.ts).
_LOOKS = {"clear": {"panel": "transparent", "content": "transparent",
                    "opacity": 0.6},
          "quiet": {"panel": "transparent", "content": "tinted", "opacity": 0.6},
          "glass": {"panel": "tinted", "content": "tinted", "opacity": 1},
          "solid": {"panel": "solid", "content": "solid", "opacity": 1}}


def _home(show, preset, **options) -> dict:
    """A Home zone. `home: 2` is the Home's mark of an arrangement made since
    its conversation column (Home.tsx SHAPE): without it the client would
    add a second column down the left of a preset's own."""
    z = {"type": "zone", "id": f"{show}-{preset}", "show": show,
         "name": _HOME_NAMES[show], "options": {**options, "home": 2}}
    if show == "kept":
        z["slot"] = {"follow": False, "show": "objects", "items": [],
                     "present": "cards"}
    return z


def _stage(zid, show, present, look=None, name="Stage") -> dict:
    """A conversation zone following what is read."""
    slot = {"follow": True, "show": show, "items": [], "present": present}
    if look:
        slot["appearance"] = dict(_LOOKS[look])
    return {"type": "zone", "id": zid, "show": "objects", "name": name,
            "slot": slot}


def _feed(zid, source, present, name, *, options=None, kinds=(), look=None) -> dict:
    """A conversation section supplied by the shared section registry."""
    slot = {"follow": False, "show": "kinds" if kinds else "objects",
            "items": [], "present": present, "feed": {"source": source}}
    if options:
        slot["feed"]["options"] = dict(options)
    if kinds:
        slot["kinds"] = list(kinds)
    if look:
        slot["appearance"] = dict(_LOOKS[look])
    return {"type": "zone", "id": zid, "show": "objects", "name": name,
            "slot": slot}


def _split(dir, sizes, *kids) -> dict:
    return {"type": "split", "dir": dir, "sizes": list(sizes), "kids": list(kids)}


def _arr(tree, pages=(), focus=None) -> dict:
    out = {"format": FORMAT, "version": VERSION, "tree": tree}
    if pages:
        out["pages"] = [{"id": pid, "title": title, "tree": t}
                        for pid, title, t in pages]
    if focus:
        out["focus"] = focus
    return out


#: Four purposeful starting arrangements. `share` is the conversation
#: column's part of the width; float rectangles are room fractions and are
#: resolved to pixels by the client when the layout is applied.
_PRESETS = (
    {"id": "preset-triage", "name": "Triage",
     "says": "Deal with what is waiting",
     "home": _arr(_split("col", (0.12, 0.88),
                         _home("briefing", "triage", collapsed=True),
                         _split("row", (0.55, 0.45),
                                _home("needs-you", "triage"),
                                _split("col", (0.5, 0.5),
                                       _home("for-you", "triage"),
                                       _home("activity", "triage"))))),
     "conversation": _arr(
         _split("row", (0.44, 0.56),
                _stage("triage-needs", "needs-you", "list", "glass",
                       name="Needs you"),
                _split("col", (0.52, 0.48),
                       _feed("triage-actions", "actions", "list", "Actions",
                             options={"owed": "me"}, look="quiet"),
                       _feed("triage-followups", "followups", "previews",
                             "Follow ups", look="quiet")))),
     "share": 0.55},
    {"id": "preset-focus", "name": "Focus layout",
     "says": "Work through one conversation",
     "home": _arr(_split("col", (0.12, 0.88),
                         _home("briefing", "focus", collapsed=True),
                         _split("row", (0.7, 0.3),
                                _home("work", "focus", tab="in-flight"),
                                _home("needs-you", "focus")))),
     "conversation": _arr(
         _split("row", (0.78, 0.22),
                _stage("stage", "objects", "focus", "quiet"),
                _feed("focus-contents", "contents", "list", "Contents",
                      options={"grouping": "reply"}, look="clear"))),
     "share": 0.6},
    {"id": "preset-oversight", "name": "Oversight",
     "says": "Watch runs and check results",
     "home": _arr(_split("row", (0.45, 0.35, 0.2),
                         _home("work", "oversight", tab="all"),
                         _home("activity", "oversight"),
                         _home("needs-you", "oversight"))),
     "conversation": _arr(
         _split("row", (0.62, 0.38),
                _feed("oversight-contents", "contents", "previews", "Contents",
                      options={"grouping": "reply"}, look="quiet"),
                _split("col", (0.56, 0.44),
                       _feed("oversight-activity", "activity", "list",
                             "Activity", look="clear"),
                       _feed("oversight-needs", "needs-you", "list",
                             "Needs you", look="glass"))),
         pages=[("files", "Files", _stage("files", "files", "list",
                                          name="Files"))]),
     "share": 0.45},
    {"id": "preset-showcase", "name": "Showcase",
     "says": "Look through mockups, screenshots and results",
     "home": _arr(_split("row", (0.6, 0.4),
                         _home("briefing", "showcase", collapsed=False),
                         _split("col", (0.5, 0.5),
                                _home("for-you", "showcase"),
                                _home("kept", "showcase")))),
     "conversation": _arr(
         _feed("showcase-contents", "contents", "gallery", "Contents",
               options={"grouping": "kind"},
               kinds=("chart", "diagram", "image"), look="clear"),
         pages=[("media", "Media", _feed("showcase-media", "media", "slides",
                                          "Media", look="quiet"))],
         focus={"floats": [{"id": "showcase-media-float",
                             "zone": _feed("showcase-highlights", "contents",
                                           "slides", "Highlights",
                                           options={"grouping": "kind"},
                                           kinds=("chart", "diagram", "image"),
                                           look="glass"),
                             "x": 0.62, "y": 0.08,
                             "w": 0.34, "h": 0.42}]}),
     "share": 0.3},
)
# Each preset Home has the conversation column down its left, as every Home
# has it (Home.tsx homeStart): 0.3 of the width, #1010's zones in the rest.
for _p in _PRESETS:
    _p["home"]["tree"] = _split("row", (0.3, 0.7),
                                _home("conversation", _p["id"][len("preset-"):]),
                                _p["home"]["tree"])
del _p
PRESET_IDS = tuple(p["id"] for p in _PRESETS)
#: What a brand-new brain starts from (#1012).
NEW_DEFAULTS = {"home": "preset-triage", "conversation": "preset-focus",
                "unnamed": "preset-focus"}


def presets() -> list:
    """The presets as the library lists them, each checked as any named
    layout is: `{id, name, says, preset: true, share, home, conversation}`.
    A fresh copy every time, so nothing a caller does to one reaches them."""
    return [{"id": p["id"], "name": p["name"], "says": p["says"],
             "preset": True, "share": p["share"],
             "home": shape_of(check(p["home"])),
             "conversation": shape_of(check(p["conversation"]))}
            for p in _PRESETS]


def _not_a_preset(layout_id, what) -> None:
    if layout_id in PRESET_IDS or str(layout_id).startswith("preset-"):
        raise Refused(f"{layout_id!r} is a built-in layout: it cannot be "
                      f"{what}. Save your own copy under a name of your own.")


# -- named layouts and defaults ----------------------------------------------------

def _empty_library() -> dict:
    return {"layouts": [], "defaults": {p: None for p in PLACES}}


def _brand_new(root) -> bool:
    """No library and nothing ever arranged: a brain nobody has shaped."""
    folder = W._dir(root) / FOLDER
    try:
        return not any(folder.glob("*.json"))
    except OSError:
        return False


def _named(l, where) -> dict:
    if not isinstance(l, dict):
        raise Refused(f"{where}: a named layout is a mapping")
    name = " ".join(W._text(l.get("name"), f"{where}.name", most=80).split())
    if not name:
        raise Refused(f"{where}.name: a layout has a name")
    lid = W._match(LAYOUT_ID, l.get("id"), f"{where}.id")
    # A preset's id is the product's: a layout kept under it would stand in
    # for the preset, so none is kept; one the file holds from before the
    # presets is read under an id of its own (`_rekeyed`).
    _not_a_preset(lid, "changed")
    out = {"id": lid, "name": name, "layout": shape_of(check(l.get("layout")))}
    if l.get("saved") is not None:
        out["saved"] = _saved(l.get("saved"))
    return out


def layouts(root) -> dict:
    """The named layouts and each place kind's default: `{"layouts":
    [{id, name, saved, layout}], "defaults": {home, conversation, unnamed}}`.
    Everything read is checked again; what fails is left out and counted
    (`dropped`), and a default naming no layout here names none."""
    out = _library(root)
    out["presets"] = presets()
    return out


def _library(root) -> dict:
    """The library as the file holds it, checked: the presets are not in it."""
    path = W._dir(root) / LAYOUTS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        out = _empty_library()
        if _brand_new(root):
            out["defaults"] = dict(NEW_DEFAULTS)
        return out
    except (OSError, ValueError, RecursionError):
        return {**_empty_library(), "unreadable": f"{LAYOUTS} could not be read"}
    out = _empty_library()
    if not isinstance(data, dict):
        return {**out, "unreadable": f"{LAYOUTS} is not a library"}
    raw = data.get("layouts") if isinstance(data.get("layouts"), list) else []
    raw, rekeyed = _rekeyed(raw[:MAX_LAYOUTS])
    seen, dropped = set(), 0
    for i, l in enumerate(raw):
        try:
            got = _named(l, f"layouts[{i}]")
        except Refused:
            dropped += 1
            continue
        if got["id"] not in seen:
            seen.add(got["id"])
            out["layouts"].append(got)
    d = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
    # A default is a layout's id, a preset's or one kept here: anything else
    # the file holds there (a list, a mapping, a number) names none, rather
    # than failing the whole read.
    seen |= set(PRESET_IDS)
    d = {p: rekeyed.get(v, v) if isinstance(v, str) else v
         for p, v in d.items()}
    out["defaults"] = {p: d.get(p) if isinstance(d.get(p), str)
                       and d.get(p) in seen else None
                       for p in PLACES}
    if dropped:
        out["dropped"] = dropped
    if rekeyed:
        out["rekeyed"] = rekeyed
    return out


def _rekeyed(raw) -> tuple[list, dict]:
    """A LAYOUT KEPT UNDER A PRESET-LOOKING ID BEFORE THE PRESETS (P12) IS
    KEPT, UNDER AN ID OF ITS OWN. `preset-` ids are the product's now, so a
    layout saved under one before is read as `kept-<rest>` (`-2`, `-3`, ...
    while that is taken), the same id every time the same file is read; a
    default that named it follows it, since a file that holds a layout under
    a preset-looking id was written before any preset could be a default.
    The next write keeps it under the new id: it is never erased. Returns
    the layouts as read and `{old id: new id}`."""
    taken = {l.get("id") for l in raw if isinstance(l, dict)}
    out, rekeyed = [], {}
    for l in raw:
        lid = l.get("id") if isinstance(l, dict) else None
        if not (isinstance(lid, str) and lid.startswith("preset-")) or lid in rekeyed:
            out.append(l)
            continue
        base = ("kept-" + lid[len("preset-"):])[:76]
        new, n = base, 1
        while new in taken:
            n += 1
            new = f"{base}-{n}"
        taken.add(new)
        rekeyed[lid] = new
        out.append({**l, "id": new})
    return out, rekeyed


def _library_for_writing(root) -> dict:
    data = _library(root)
    if "unreadable" in data:
        raise W.Unreadable(f"{data['unreadable']}; it was left as it is")
    data.pop("dropped", None)
    data.pop("rekeyed", None)
    return data


def _answer(data) -> dict:
    return {**data, "presets": presets()}


def _keep_new_defaults(root) -> None:
    """A brand-new brain is about to be shaped (its first arrangement saved):
    the defaults it started from are written down, so they stay its own
    rather than ending with the brain's newness. Under the lock."""
    if not (W._dir(root) / LAYOUTS).exists() and _brand_new(root):
        W._atomic(W._dir(root) / LAYOUTS,
                  {"layouts": [], "defaults": dict(NEW_DEFAULTS)})


def save_layout(root, body) -> dict:
    """Keep a named layout, `{id, name, layout}`: a new one, or the one of
    the same id replaced. What it keeps is the arrangement's shape and
    rules, its content taken out (`shape_of`)."""
    l = _named(body, "layout")
    l["saved"] = time.time()
    with W._lock(root):
        data = _library_for_writing(root)
        rest = [x for x in data["layouts"] if x["id"] != l["id"]]
        if len(rest) >= MAX_LAYOUTS:
            raise Refused(f"a brain keeps at most {MAX_LAYOUTS} named "
                          "layouts; delete one first")
        data["layouts"] = rest + [l]
        W._atomic(W._dir(root) / LAYOUTS, data)
    return _answer(data)


def delete_layout(root, layout_id) -> dict:
    """Delete a named layout; a default that named it names none. A preset
    is never deleted."""
    W._match(LAYOUT_ID, layout_id, "layout")
    _not_a_preset(layout_id, "deleted")
    with W._lock(root):
        data = _library_for_writing(root)
        if not any(l["id"] == layout_id for l in data["layouts"]):
            raise LookupError(f"there is no layout {layout_id}")
        data["layouts"] = [l for l in data["layouts"] if l["id"] != layout_id]
        data["defaults"] = {p: (None if v == layout_id else v)
                            for p, v in data["defaults"].items()}
        W._atomic(W._dir(root) / LAYOUTS, data)
    return _answer(data)


def set_default(root, body) -> dict:
    """`{place, layout}`: the named layout a place kind starts from --
    `home`, every `conversation`, or `unnamed` ones; `layout` null: none.
    A preset may be named. `{places: [...], layout}` names it for several
    at once, as picking a preset does (it sets Home and the conversation
    view together)."""
    if not isinstance(body, dict):
        raise Refused(f"place: one of {list(PLACES)}")
    places = body.get("places") if "places" in body else [body.get("place")]
    if not isinstance(places, list) or not places or             any(p not in PLACES for p in places):
        raise Refused(f"place: one of {list(PLACES)}")
    layout = body.get("layout")
    if layout is not None:
        W._match(LAYOUT_ID, layout, "layout")
    with W._lock(root):
        data = _library_for_writing(root)
        if layout is not None and layout not in PRESET_IDS and not any(
                l["id"] == layout for l in data["layouts"]):
            raise LookupError(f"there is no layout {layout}")
        for p in places:
            data["defaults"][p] = layout
        W._atomic(W._dir(root) / LAYOUTS, data)
    return _answer(data)
