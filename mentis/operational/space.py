"""The whole Brain, as something that can be drawn in space. A READ.

WHY THIS EXISTS. The 3D Brain (ui/src/surfaces/space/) draws every durable
thing a Brain holds, placed by facts the record states. The reads that were
already here each answer something narrower: `/api/neighborhood` is one Entry
and what it reaches, `/api/history` is a work-history graph of operational
acts, `/api/brain` is counts and names on purpose, `/api/governed` is governed
material only. None of them says, for the whole Brain at once, what each
durable Entry is, which Conversation it belongs to and which links run between
them. That is the whole of what this answers, and nothing is written.

WHAT IS DRAWN, AND AT WHAT HEIGHT. A node is a durable Entry. Its `layer` is
the height it is drawn at, highest first:

  how       its Kind declares `knowing: how` -- rules, decisions, personas,
            instructions: what directs work.
  that      its Kind declares `knowing: that` -- what is known.
  other     a Kind the conversation substrate does not own that declares no
            `knowing` at all. Said as undeclared, never passed off as known.
  place     a Conversation or a Topic: the structure the work happens in.
  who       a Participant.
  said      a Turn, an anchor, a reaction, an observation: the talk.
  material  an Admission. Only when asked for (`material=True`): on a real
            Brain it is thousands of file reads, which would bury the rest.

The ladder is read from what each Kind DECLARES (`kind_definitions`, the one
read of the vocabulary); the only names here are the substrate's own Kinds,
which are fixed and few, exactly as `products.py` keys on families. NOT
DRAWN: the vocabulary itself, links (they are edges), a `deletion` (what it
deleted is drawn deleted instead), the `whole-brain` destination and runtime
defaults (settings, not things anybody looks for in a Brain).

WHAT A READER SEES NOW, NOT THE RAW ROW (review B1). A Turn or a Topic keeps
its identity at the ROOT of its line (`versions.ROOT_IDENTITY`): every link
points at the first entry, and later versions are read AS it. So those Kinds
are drawn once, at the root, through `versions.presented` -- the current
words, `edited` when it was, and `deleted` (words blanked) when its line ends
in a deletion -- and their later versions are never drawn as things of their
own. Any other Kind keeps the ordinary reading: a successor is its own item
and what it replaced is `replaced`; only the entry a deletion names is
`deleted`.

WHICH CONVERSATION, which is the region a node is drawn in. Read from the
links that say so: a Conversation is its own; a Topic is `topic-of` one; a
Turn is `in-conversation`; an anchor is in its Turn's, a reaction in its
anchor's, an observation in what it observes'; behavioural material is
`scoped-to` one; anything else is in the Conversation of the operational act
that `produced` it. Where none of those holds there is none, and the drawing
says so by where it puts it. Nothing is inferred from text or proximity.

ONLY LINKS THAT STILL STAND (review N1). A link something has ended -- an
ended filing, a picture replaced -- is neither an edge nor a reason a thing
sits in a region: the rule `Conversations._links_now` keeps.

THE EDGES are every standing link between two drawn nodes, except three:
`establishes` (written from an entry to itself), `produced` (provenance; acts
are not drawn) and `in-conversation` (membership IS the region -- as three
thousand strands it would be the haze the drawing exists without).

BOUNDED, AND IT SAYS SO. `cap` keeps the upper layers first and then the
newest; `omitted` counts what it left out, as every bounded read here does.
"""

from __future__ import annotations

from mentis.conversation import (
    ANCHOR, ANCHORS_IN, CONTRIBUTION, CONVERSATION, DELETION,
    IN_CONVERSATION, KNOWING_HOW, KNOWING_THAT, OBSERVATION, OBSERVES,
    PARTICIPANT, PRODUCED, REACTION, REACTS_TO, RUNTIME_DEFAULT, SCOPED_TO,
    TOPIC, TOPIC_OF, WHOLE_BRAIN,
)
from mentis.conversation.register import kind_definitions
from mentis.conversation.versions import ROOT_IDENTITY, presented

ESTABLISHES = "establishes"

#: Heights, top first. The order is the ladder's own direction and the UI
#: reads it from here rather than keeping a copy.
LAYERS = ("how", "that", "other", "place", "who", "said", "material")
#: The layers a reader is always offered, whether or not anything is in them.
_ALWAYS = ("how", "that", "place", "who", "said")

_PLACE = {CONVERSATION, TOPIC}
_SAID = {CONTRIBUTION, ANCHOR, REACTION, OBSERVATION}
_NOT_DRAWN = {DELETION, WHOLE_BRAIN, RUNTIME_DEFAULT}
#: Edges that are not drawn, and why, in the module docstring.
_NOT_EDGES = {ESTABLISHES, PRODUCED, IN_CONVERSATION}

#: Enough words to recognise a thing by. The full text is one Open away.
SAID_AT_MOST = 140
#: The most a caller may ask for. `cap` is a safety bound, and one a client
#: sets must not be able to undo it.
CAP_AT_MOST = 20000


def _relation(link) -> str | None:
    return ((link.get("definition") or {}).get("name")
            or (link.get("link") or {}).get("relation"))


def _kind(entry) -> str | None:
    return (entry.get("definition") or {}).get("name")


def _words(entry) -> str | None:
    """Everything this says, from its own body, before any cut."""
    body = entry.get("body") or {}
    if entry.get("family") == "admission":
        said = body.get("locator") or body.get("source")
    else:
        parts = body.get("parts")
        said = (" ".join(p.get("text", "") for p in parts
                         if isinstance(p, dict) and p.get("type") == "text")
                if isinstance(parts, list) else None)
        said = (said or body.get("text") or body.get("name") or body.get("alias")
                or body.get("behaviour") or body.get("title") or body.get("summary")
                or next((v for v in body.values()
                         if isinstance(v, str) and v.strip()), None))
    return said if isinstance(said, str) and said.strip() else None


def _summary(entry) -> str | None:
    """The words a reader would recognise this by: one short line."""
    said = _words(entry)
    if said is None:
        return None
    # Only as much as can be shown is normalised: a Turn can be pages long.
    said = " ".join(said[:SAID_AT_MOST * 2].split())
    return said[:SAID_AT_MOST - 1] + "…" if len(said) > SAID_AT_MOST else said


#: How much of what a CHOSEN thing says is given: enough that a Decision says
#: what was decided and why. The whole record is one Open away.
SAID_WHEN_CHOSEN = 600


def _cut(said: str, most: int = SAID_WHEN_CHOSEN) -> str:
    """At most `most` characters, cut only when it is genuinely longer: at a
    sentence that ends near the limit if there is one, else at a word, and
    then marked with "…"."""
    said = " ".join(said[:most * 2].split())
    if len(said) <= most:
        return said
    window = said[:most]
    ends = [i for i in range(len(window) - 1) if window[i] in ".!?" and window[i + 1] == " "]
    if ends and ends[-1] >= most * 0.7:
        return window[:ends[-1] + 1] + " …"
    space_at = window.rfind(" ")
    return (window[:space_at] if space_at > most * 0.5 else window).rstrip(" ,;:") + "…"


def said_of(brain, entry_id) -> dict:
    """What ONE chosen thing says, as a reader sees it now. A read.

    THE 3D BRAIN SENDS ONE LINE PER STAR AND ASKS FOR MORE ONLY FOR THE ONE
    CHOSEN (owner, 2026-10-10: say what it is AND what it says, e.g. what was
    decided and why, without opening the full record). Read through
    `versions.presented`, so an edited Turn says its current words and a
    deleted one says nothing.
    """
    corpus = brain.primary
    got = corpus.read([entry_id])
    if not got:
        return {"entry": entry_id, "said": None, "deleted": False, "edited": False,
                "why_not": "this brain cannot read that entry"}
    now = presented(corpus, got[0])
    deleted = bool(now.get("deleted"))
    words = None if deleted else _words(now)
    return {"entry": entry_id, "said": _cut(words) if words else None,
            "deleted": deleted, "edited": bool(now.get("revision")) and not deleted}


def space(brain, *, material: bool = False, cap: int = 6000) -> dict:
    corpus = brain.primary
    cap = max(0, min(int(cap), CAP_AT_MOST))
    kinds = kind_definitions(corpus)

    def layer_of(kind) -> str | None:
        if kind in _NOT_DRAWN:
            return None
        if kind in _PLACE:
            return "place"
        if kind == PARTICIPANT:
            return "who"
        if kind in _SAID:
            return "said"
        knowing = (kinds.get(kind) or {}).get("knowing")
        return ("how" if knowing == KNOWING_HOW
                else "that" if knowing == KNOWING_THAT else "other")

    # ONE READ PER KIND, NOT EVERY ROW (review N2): admissions are thousands of
    # rows on a real Brain and are only decoded when they are asked for.
    entries: list[dict] = []
    for kind in kinds:
        if layer_of(kind) is not None:
            entries.extend(corpus.entries_of_kind(kind))
    if material:
        entries.extend(e for e in corpus.all_entries() if e.get("family") == "admission")
    links = corpus.links()

    # ---- what has been superseded, and what is only a later version --------
    sup = corpus.superseding_relation()
    by_id = {e["id"]: e for e in entries}
    superseded: set[str] = set()
    later_version: set[str] = set()
    for x in links:
        if _relation(x) != sup:
            continue
        frm, to = x["link"].get("from"), x["link"].get("to")
        superseded.add(to)
        old, new = by_id.get(to), by_id.get(frm)
        if old and new and _kind(old) in ROOT_IDENTITY and _kind(new) == _kind(old):
            later_version.add(frm)

    drawn: dict[str, tuple[dict, str, str]] = {}
    for e in entries:
        if e["id"] in later_version:
            continue                      # read AS its root, never on its own
        kind = _kind(e) if e.get("family") == "entry" else "admission"
        layer = "material" if kind == "admission" else layer_of(kind)
        if layer is not None:
            drawn[e["id"]] = (e, kind, layer)

    # ---- which Conversation each belongs to, from links that still stand ---
    standing = [x for x in links if x["id"] not in superseded]
    out_of: dict[str, dict[str, str]] = {}      # relation -> from -> to (first)
    produced_by: dict[str, str] = {}
    for x in standing:
        ref = x["link"]
        rel, frm, to = _relation(x), ref.get("from"), ref.get("to")
        if rel == PRODUCED:
            produced_by.setdefault(to, frm)
        elif rel != sup:
            out_of.setdefault(rel, {}).setdefault(frm, to)

    acts = sorted({a for eid, a in produced_by.items() if eid in drawn})
    act_conv: dict[str, str | None] = {}
    for i in range(0, len(acts), 500):
        for a in corpus.operational(id=tuple(acts[i:i + 500])):
            act_conv[a["id"]] = a.get("conversation")

    def via(rel, eid):
        return out_of.get(rel, {}).get(eid)

    def region(eid, kind, depth=0) -> str | None:
        if depth > 3:
            return None
        if kind == CONVERSATION:
            return eid
        hop = (via(TOPIC_OF, eid) if kind == TOPIC
               else via(IN_CONVERSATION, eid) if kind == CONTRIBUTION
               else None)
        if hop:
            return hop
        for rel in (ANCHORS_IN, REACTS_TO, OBSERVES):
            target = via(rel, eid)
            if target and target in drawn:
                return region(target, drawn[target][1], depth + 1)
        placed = via(SCOPED_TO, eid)
        if placed and placed in drawn:
            return placed
        act = produced_by.get(eid)
        return act_conv.get(act) if act else None

    names = {}
    nodes = []
    for eid, (e, kind, layer) in drawn.items():
        # THE COMMON CASE COSTS NOTHING: only what something superseded is read
        # through `presented`, as `Conversations._contributions` does.
        now = presented(corpus, e) if eid in superseded else e
        deleted = bool(now.get("deleted"))
        if kind == CONVERSATION:
            names[eid] = (now.get("body") or {}).get("name")
        where = None if kind == PARTICIPANT else region(eid, kind)
        nodes.append({
            "entry": eid,
            "kind": kind,
            "layer": layer,
            "conversation": where if where in drawn else None,
            "at": e.get("recorded_at"),
            "summary": None if deleted else now,     # words read once kept
            "deleted": deleted,
            "edited": bool(now.get("revision")) and not deleted,
            # REPLACED is a successor's doing. A Turn or a Topic is never
            # "replaced": its versions are read as it, which is an edit.
            "replaced": (eid in superseded and not deleted
                         and kind not in ROOT_IDENTITY),
        })

    # ---- bounded, upper layers first and then the newest -------------------
    total = len(nodes)
    if total > cap:
        rank = {name: i for i, name in enumerate(LAYERS)}
        nodes.sort(key=lambda n: (rank[n["layer"]], -(n["at"] or 0)))
        nodes = nodes[:cap]
    kept = {n["entry"] for n in nodes}
    for n in nodes:
        if n["summary"] is not None:
            n["summary"] = _summary(n["summary"])
    nodes.sort(key=lambda n: (n["at"] or 0, n["entry"]))

    edges = []
    for x in standing:
        rel = _relation(x)
        ref = x["link"]
        frm, to = ref.get("from"), ref.get("to")
        if rel in _NOT_EDGES or frm == to or frm not in kept or to not in kept:
            continue
        edges.append({"link": x["id"], "from": frm, "to": to, "relation": rel})

    present = {n["layer"] for n in nodes}
    return {
        "nodes": nodes,
        "edges": edges,
        "conversations": {k: v for k, v in names.items() if k in kept},
        "layers": [name for name in LAYERS
                   if name in _ALWAYS or name in present
                   or (name == "material" and material)],
        "total": total,
        "omitted": total - len(nodes),
        "cap": cap,
        "material": material,
    }
