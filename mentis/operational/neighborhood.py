"""What a durable Entry is connected to, and how far that actually goes.

Two reads, and the difference between them is the bound:

  `neighborhood`  one hop. Every edge in it was asserted directly ABOUT this
                  object by somebody, with a reason and an author.
  `closure`       outward until there is nothing unvisited left — the
                  relationship structure EXHAUSTED rather than cut at a depth
                  this file chose.

THIS IS NOT THE CONVERSATION'S CAUSAL GRAPH. That answers "what happened
because of this Turn". This answers a different question about a different
object: "what is this durable thing connected to", where the connections are
ordinary semantic Relations between Entries.

THE TWO KINDS OF CONNECTION ARE KEPT APART, because they are not the same
sort of fact:

  SEMANTIC      Entry -> Entry, through a Relation somebody asserted:
                derived-from, supports, disputes, supersedes, and any other
                relation anybody defines. These say what the object means in
                relation to other knowledge.
  PROVENANCE    the operational act that MINTED it, through `produced`. This
                is how it came to exist, not what it means, and merging the
                two would let "this was made by that run" read like "this
                follows from that finding".

ON BOUNDS. The substrate offers no natural one: no degree counts, no depth
parameter, no scope that reaches durable Entries (a Conversation bounds its
Turns, not the Findings work produced in it). So `closure` does not invent a
depth — it stops when the walk runs out of places to go, which is a fact about
the record. Its `cap` is a safety bound against a pathological corpus, not a
semantic one, and when it bites it says so: `exhausted` goes false and
`omitted` counts what was left. That is the house rule for bounded reads here
— `Brain.orientation` returns `*_omitted` beside its caps for the same reason.
A bound that hid what it excluded would be the dishonest kind.

NO SCORE, NO RANKING. Edges come back in the order the record holds them.
Nothing here decides which relation matters more than another, and there is
no relevance number anywhere.

Built on the public seam only.
"""

from __future__ import annotations

from mentis.operational.products import describe_entry

PRODUCED = "produced"


def _relation_meaning(corpus, link) -> tuple[str, str | None]:
    """A relation's name and the words whoever defined it chose for it.

    Read from the definition the LINK WAS WRITTEN AGAINST, so an edge is
    explained in the vocabulary that was in force when somebody asserted it.
    A reader needs no list of relation names: every edge explains itself.
    """
    ref = link.get("definition") or {}
    name = ref.get("name") or (link.get("link") or {}).get("relation")
    defn = corpus.definition_for(link)
    meaning = (defn or {}).get("body", {}).get("meaning") if defn else None
    return name, meaning


def _edge(corpus, link, *, direction, other_id) -> dict:
    name, meaning = _relation_meaning(corpus, link)
    ref = link.get("link") or {}
    return {
        "link": link.get("id"),
        "relation": name,
        # The label for reading the edge the other way. It is DESCRIPTIVE: the
        # substrate materialises no inverse row, and reverse traversal is done
        # by swapping the endpoints, not by looking this up.
        "inverse": ((corpus.current_definition(name) or {}).get("body", {})
                    .get("inverse") if name else None),
        "meaning": meaning,
        "direction": direction,
        "reason": (link.get("body") or {}).get("reason"),
        "asserted_by": link.get("attributed_to"),
        "at": link.get("recorded_at"),
        "other": other_id,
        "relation_version": ref.get("relation_version"),
    }


def neighborhood(brain, entry_id, *, limit=40) -> dict:
    """One hop around a durable Entry, semantic edges and provenance apart.

    `limit` bounds each side. Whatever it excludes is COUNTED and reported;
    nothing is silently dropped.
    """
    corpus = brain.primary
    focus = describe_entry(corpus, entry_id)
    if focus is None:
        return {"entry": entry_id, "focus": None, "semantic": [],
                "produced_by": [], "produced": [], "neighbours": {},
                "omitted": 0,
                "why_not": "this brain cannot read that entry"}

    incoming = corpus.links(to=entry_id)
    outgoing = corpus.links(frm=entry_id)

    semantic: list[dict] = []
    made_by: list[dict] = []
    made: list[dict] = []
    omitted = 0

    for link, direction in ([(x, "in") for x in incoming]
                            + [(x, "out") for x in outgoing]):
        ref = link.get("link") or {}
        frm, to = ref.get("from"), ref.get("to")
        # An `establishes` link is written from an entry TO ITSELF. It is a
        # third of all links in a corpus and it is not a neighbour; standing
        # already reports it and this would only be noise.
        if frm == to:
            continue
        other = frm if direction == "in" else to
        edge = _edge(corpus, link, direction=direction, other_id=other)
        if edge["relation"] == PRODUCED:
            # Provenance, not meaning. Incoming `produced` names the act that
            # minted this; outgoing would mean this entry minted something,
            # which the substrate permits and nothing currently writes.
            (made_by if direction == "in" else made).append(edge)
            continue
        if len(semantic) >= limit:
            omitted += 1
            continue
        semantic.append(edge)

    # Describe each neighbour once, in its own declared terms, so an unknown
    # Kind is representable here for the same reason it is everywhere else.
    wanted = {e["other"] for e in semantic if str(e["other"]).startswith("ent-")}
    neighbours = {}
    for nid in wanted:
        seen = describe_entry(corpus, nid)
        neighbours[nid] = seen or {"entry": nid, "kind": None, "family": None,
                                   "summary": None, "meaning": None,
                                   "fields": [], "body": {}, "unreadable": True}

    return {
        "entry": entry_id,
        "focus": focus,
        "semantic": semantic,
        "produced_by": made_by,
        "produced": made,
        "neighbours": neighbours,
        "omitted": omitted,
        "counts": {"semantic": len(semantic), "provenance": len(made_by),
                   "total_links": len(incoming) + len(outgoing)},
    }


def closure(brain, entry_id, *, cap=60) -> dict:
    """Every durable Entry reachable from this one by semantic Relations.

    NOT A FIXED DEPTH. It walks outward until there is nothing unvisited left
    to walk to — the relationship structure is EXHAUSTED, which is a fact
    about the record rather than a number this file chose. A derivation chain
    three long returns three; one that terminates immediately returns its
    immediate neighbours and stops. Cycles are guarded by the visited set, so
    a mutually-referring pair terminates rather than spinning.

    `cap` is a safety bound on total nodes, not a semantic one. It exists so a
    pathological corpus cannot hang a browser, and when it bites it SAYS SO —
    `exhausted` goes false and `omitted` counts what was left unexplored. A
    bound that hid what it excluded would be the dishonest kind; this repo's
    other bounded reads report the same way.

    PROVENANCE IS NOT IN HERE. `produced` says how an object came to exist,
    not what it means, and drawing both as nodes and edges would let "made by
    that run" read like "follows from that finding". The provenance path is
    `provenance_of`, and it is a different question with a different answer.
    """
    corpus = brain.primary
    focus = describe_entry(corpus, entry_id)
    if focus is None:
        return {"entry": entry_id, "focus": None, "nodes": {}, "edges": [],
                "exhausted": True, "omitted": 0,
                "why_not": "this brain cannot read that entry"}

    nodes: dict[str, dict] = {entry_id: {**focus, "distance": 0}}
    edges: list[dict] = []
    seen_links: set[str] = set()
    frontier = [entry_id]
    distance = 0
    omitted = 0

    while frontier:
        distance += 1
        nxt: list[str] = []
        for here in frontier:
            for link, direction in ([(x, "in") for x in corpus.links(to=here)]
                                    + [(x, "out") for x in corpus.links(frm=here)]):
                ref = link.get("link") or {}
                frm, to = ref.get("from"), ref.get("to")
                if frm == to:
                    continue                      # `establishes` self-loop
                name = (link.get("definition") or {}).get("name") or ref.get("relation")
                if name == PRODUCED:
                    continue                      # provenance, answered elsewhere
                other = frm if direction == "in" else to
                if not str(other).startswith("ent-"):
                    continue
                lid = link.get("id")
                if lid in seen_links:
                    continue
                seen_links.add(lid)
                edges.append(_edge(corpus, link, direction=direction,
                                   other_id=other) | {"from": here})
                if other in nodes:
                    continue
                if len(nodes) >= cap:
                    omitted += 1
                    continue
                seen = describe_entry(corpus, other)
                nodes[other] = {**(seen or {"entry": other, "kind": None,
                                            "family": None, "summary": None,
                                            "meaning": None, "fields": [],
                                            "body": {}, "unreadable": True}),
                                "distance": distance}
                nxt.append(other)
        frontier = nxt

    return {
        "entry": entry_id,
        "focus": focus,
        "nodes": nodes,
        "edges": edges,
        # True when the walk ran out of places to go rather than out of budget.
        "exhausted": omitted == 0,
        "omitted": omitted,
        "reach": max((n["distance"] for n in nodes.values()), default=0),
    }
