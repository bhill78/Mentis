"""The governed-material register: every governed entry in the Brain, findable.

WHY THIS EXISTS. Governance could be acted on where it arose -- a card on the
spine, a reference in prose -- and nowhere else. `governs()` is one
Conversation's instructions and nothing more, so a proposed Finding, a Persona
or a Rule written in some older Turn could only be reached by somebody who
already knew its `ent-*` id. This is the normal way to find it.

IT IS A READ AND IT DECIDES NOTHING. Standing is what `stands` has always
computed, and the four answers are `standing_state` -- the same function
`governs()` sorts by -- so the register and a Conversation's own header cannot
disagree. No state is stored, no queue exists, and acting on a row is the
existing inspector's business.

WHAT IS LISTED, AND THE TWO DIFFERENT REASONS -- WHICH ARE NOT MERGED. `knowing
== "how"` says the Kind's material DIRECTS HOW WORK IS DONE, and such material is
listed whatever else it declares, because that is the material delivery carries:
`compose` supplies placed, standing material of such a Kind and asks
`standing_apt` nothing. A Kind declaring `"how"` with `standing_apt` ABSENT was
therefore governing the work and missing from this register, which is the surface
that exists for finding governed material. `standing_apt` on the CURRENT Kind
definition is the other answer and is unchanged -- it says whether instances
participate in standing at all.

AND THE WORD "GOVERNED" IS NOT SAID OF MATERIAL THAT GOVERNS NOTHING. The two
reasons used to be one list, so a standing `finding`, `lesson` or `hypothesis`
appeared here under that heading while `compose` delivers none of them as
governance -- the register asserting of propositional material exactly what the
two ladders exist to stop anything asserting. Dropping them was not the answer
either: standing IS meaningful for them, correcting one is an ordinary
supersession, and this is the surface the owner finds material through, so
hiding it would leave a standing lesson reachable only by somebody who already
knew its `ent-*` id -- the defect this module was written for. So every row
carries its Kind's `knowing` and a `governs` that is that declaration and
nothing else, `kinds.directs_work` and `kinds.standing_knowledge` name the two
grounds apart (`kinds.listed` is still their union), and `listed_because` says
each ground in words. No Kind is named here:

  standing_apt true     listed
  standing_apt false    not listed, and the Kinds are named as declined
  standing_apt absent   UNKNOWN. Not listed by default -- nobody has said
                        standing is meaningful for them -- and not dropped
                        silently either: the Kinds and how many entries they
                        hold are reported, and asking for one by name lists
                        its entries in a group of their own (below).

FIVE GROUPS. Recording alone is not an obligation.
  recorded   candidates with no open adoption request, including declined
             requests. Evidence remains readable without asking anyone.
  proposed   candidates with an explicit, still-open `proposes` request.
  standing   stands.
  history    ended (it used to hold) AND replaced before establishment (it
             never held). The second is never actionable, and is never merged
             into the first: each row keeps its own `state`.
  unknown    STANDING NOT DECLARED. Entries of a Kind whose current definition
             does not say whether standing applies. They are never sorted into
             proposed, standing or history: each of those headings states an
             answer about standing, and for these nobody has given one. Their
             recorded links (`established_by`, `superseded_by`) are carried as
             the facts they are; `state` is None, because computing one would
             apply standing to a Kind that has not said standing applies.

BOUNDED. Only the definitions, the walked Kinds' entries, the `scoped-to` and
`produced` links, the acts those links name (each by its indexed id), and the
people and Conversations the rows mention are read -- each set once, not per
row. Text is matched BEFORE standing is computed, so `stands` runs only for
rows that survive the search. Each group returns at most `limit` rows, newest
first; `totals` and `omitted` say how many there are and how many were left
out, so a short list is never mistaken for a short record.
"""

from __future__ import annotations

from mentis.conversation import (KNOWING_HOW, PERSONA, PRODUCED, SCOPED_TO,
                                 knowing_of, standing_state, whole_brain_ids)

GROUP_OF = {"candidate": "proposed", "stands": "standing",
            "ended": "history", "replaced": "history"}
GROUPS = ("proposed", "recorded", "standing", "history", "unknown")
DEFAULT_LIMIT = 50
MAX_LIMIT = 1000

#: How many competing proposals one ROW carries before it says how many it left
#: out. A register row is a summary; the item's own read carries the rest.
REGISTER_PROPOSALS = 5


def kind_definitions(corpus) -> dict[str, dict]:
    """Every Kind's CURRENT definition, as it declares itself, keyed by name.

    THE ONE READ OF THE VOCABULARY, shared by `/api/kinds`, this register and
    the worker's `kinds` tool, so the UI and an agent cannot be told different
    Kinds. It reads the definitions THE STORE HOLDS -- never `seed.py` -- so a
    Brain whose vocabulary has moved on from the seed is described as it is.
    Relations are excluded: a Kind is a definition that names a `kind`.
    """
    newest: dict[str, dict] = {}
    for e in corpus.definitions():
        b = e["body"]
        name = b.get("kind")
        if not name:
            continue
        v = e["definition"]["version"]
        if name in newest and v <= newest[name]["version"]:
            continue
        newest[name] = {
            "kind": name, "fields": b.get("fields", []),
            "meaning": b.get("meaning", ""),
            "truth_apt": b.get("truth_apt"),
            "capturable": b.get("capturable"),
            # ABSENT STAYS ABSENT. `None` here means nobody has established
            # whether standing is meaningful for this Kind, which is not the
            # same answer as False.
            "standing_apt": b.get("standing_apt"),
            # WHICH LADDER THIS KIND'S MATERIAL TRAVELS, read from the same
            # declaration delivery reads and nowhere else. Absent stays absent:
            # `None` means this Kind is not knowledge, which is neither
            # `"that"` nor `"how"`.
            "knowing": b.get("knowing"),
            # WHETHER ESTABLISHING ONE NEEDS A FALSIFIER, so an authoring
            # surface can ask for it before the route refuses for the lack of
            # one. Absent stays absent.
            "expects_falsifier": b.get("expects_falsifier"),
            # WHETHER RECORDING ONE NEEDS A BASIS (owner decision 1), so an
            # agent asking `kinds` and a surface can say so before the write
            # refuses. Absent stays absent, and absent means not required.
            "requires_basis": b.get("requires_basis"),
            # HOW AN OWNER'S SURFACE OFFERS TO WRITE ONE, as the Kind declares
            # it (`seed.KIND_PROPERTIES`). Descriptive: nothing here or in
            # delivery reads them. Absent stays absent (None), and the
            # surface then falls back to what it has always offered.
            "authoring": b.get("authoring"),
            "form": b.get("form"),
            "version": v}
    return newest


def _kinds(corpus) -> dict[str, dict]:
    """Every Kind's CURRENT definition, keyed by name. Relations excluded."""
    return {name: {"kind": name, "version": d["version"],
                   "fields": d["fields"],
                   # ABSENT STAYS ABSENT: None is UNKNOWN, never False.
                   "standing_apt": d["standing_apt"],
                   # WHICH LADDER, read through the one lookup the delivery
                   # path uses. See `knowing_of`.
                   "knowing": knowing_of(corpus, name)}
            for name, d in kind_definitions(corpus).items()}


def ground_of(k: dict) -> str:
    """Why a Kind is, or is not, walked by this register, from its own
    declarations: `directs_work`, `standing_knowledge`,
    `standing_not_meaningful` or `standing_apt_unknown`.

    See `governed` for why the two grounds for being listed are kept apart.
    This is that decision, in the one place both the register and the worker's
    `kinds` tool make it."""
    if k["knowing"] == KNOWING_HOW:
        return "directs_work"
    if k["standing_apt"] is True:
        return "standing_knowledge"
    if k["standing_apt"] is False:
        return "standing_not_meaningful"
    return "standing_apt_unknown"


def group_of(k: dict, standing: dict) -> tuple[str | None, str]:
    """An entry's `state` and register group, from its Kind and `stands`.

    UNKNOWN IS NOT CONVERTED: an entry of a Kind that has not said standing
    applies gets `state` None and group `unknown`, whatever links it carries --
    computing a state would apply standing to a Kind that has not said standing
    applies."""
    if k["standing_apt"] is True or k["knowing"] == KNOWING_HOW:
        state = standing_state(standing)
        return state, GROUP_OF[state]
    return None, "unknown"


def standing_split(corpus) -> dict[str, dict]:
    """How many entries each Kind holds, and how they divide into this
    register's four groups. Keyed by name, for every Kind the store declares.

    THE SAME DECISIONS THE REGISTER MAKES, NOT A COPY OF THEM: `ground_of` says
    whether standing applies and `group_of` sorts each entry, exactly as
    `governed` does, so an agent's count and the owner's register cannot
    disagree. The total is `count_of_kind`, counted without reading.

    NOTHING UNDETERMINED IS REPORTED AS ZERO.
      * A count that could not be taken is `entries: None`, with the reason.
      * A Kind that declares standing NOT MEANINGFUL has no split at all --
        `split: None`, with the reason -- because "0 proposed" would be an
        answer about standing for a Kind that says it has none.
      * A Kind whose standing is UNDECLARED has every entry under `unknown`,
        and `proposed`, `standing` and `history` None: each of those headings
        answers a question nobody has said applies to it.
      * An entry whose standing could not be computed is counted `unknown`,
        and the failure is said in `unknown_because`.
    """
    out: dict[str, dict] = {}
    for name, k in sorted(_kinds(corpus).items()):
        ground = ground_of(k)
        row: dict = {"ground": ground}
        out[name] = row
        try:
            row["entries"] = corpus.count_of_kind(name)
        except Exception as exc:
            row["entries"] = None
            row["entries_unknown_because"] = (
                f"the store could not count them: {type(exc).__name__}: {exc}")
        if ground == "standing_not_meaningful":
            row["split"] = None
            row["split_because"] = (
                "its Kind declares standing not meaningful, so its entries are "
                "never proposed, standing or history")
            continue
        try:
            got = corpus.entries_of_kind(name)
        except Exception as exc:
            row["split"] = None
            row["split_because"] = (
                f"its entries could not be read: {type(exc).__name__}: {exc}")
            continue
        split: dict = {g: 0 for g in GROUPS}
        failed = []
        for e in got:
            try:
                _, group = group_of(k, corpus.stands(e["id"]))
                if group == "proposed":
                    from mentis.conversation.ladder_writes import requests
                    group = "proposed" if requests(corpus, e["id"], open_only=True) else "recorded"
            except Exception as exc:
                group = "unknown"
                failed.append(f"{e['id']}: {type(exc).__name__}: {exc}")
            split[group] += 1
        reasons = []
        if ground == "standing_apt_unknown":
            for g in ("proposed", "recorded", "standing", "history"):
                split[g] = None
            reasons.append("its Kind does not declare whether standing "
                           "applies, so its entries are not sorted into "
                           "proposed, standing or history")
        if failed:
            reasons.append("standing could not be computed for "
                           + "; ".join(failed))
        row["split"] = split
        if reasons:
            row["unknown_because"] = reasons
        if row["entries"] is not None and len(got) != row["entries"]:
            # TWO READS, AND THE RECORD MOVED BETWEEN THEM. Both are said
            # rather than one being made to agree with the other.
            row["split_walked"] = len(got)
    return out


def _summary(entry: dict, fields: list) -> tuple[str, str]:
    """The principal statement and the one after it, in the Kind's own order.

    The Kind's declared fields say what an entry of it is; no field name is
    special-cased here.
    """
    body = entry.get("body") or {}
    order = list(fields) + [k for k in body if k not in fields]
    said = [v.strip() for k in order
            if isinstance((v := body.get(k)), str) and v.strip()]
    return (said[0] if said else ""), (said[1] if len(said) > 1 else "")


def _limit(raw) -> int | None:
    if raw in (None, ""):
        return DEFAULT_LIMIT
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= MAX_LIMIT else None


def governed(brain, *, kind: str | None = None, q: str | None = None,
             state: str | None = None, limit=None, cursor=None) -> dict:
    corpus = brain.primary
    kinds = _kinds(corpus)
    kind = (kind or "").strip() or None
    state = (state or "").strip() or None
    tokens = [t for t in (q or "").lower().split() if t]
    cap = _limit(limit)

    if state is not None and state not in GROUPS:
        return {"error": f"no such group {state!r}", "groups": list(GROUPS)}
    if kind is not None and kind not in kinds:
        return {"error": f"no Kind is defined as {kind!r}",
                "hint": "ask /api/kinds what this record declares"}
    if cap is None:
        return {"error": f"limit must be a whole number from 1 to {MAX_LIMIT}",
                "limit": limit}
    offset = None
    if cursor is not None:
        try:
            offset = 0 if cursor in ("", "start") else int(str(cursor).removeprefix("g1."))
        except ValueError:
            return {"error": f"not a governed-material cursor: {cursor!r}"}
        if offset < 0:
            return {"error": f"not a governed-material cursor: {cursor!r}"}

    listed, declined, unknown = [], [], []
    directs_work, standing_knowledge = [], []
    for name, k in sorted(kinds.items()):
        # MATERIAL THAT DIRECTS WORK IS GOVERNED MATERIAL BY ITS OWN
        # DECLARATION, whatever `standing_apt` says, and it is listed on that
        # ground. Delivery carries placed material whose Kind declares
        # `knowing == "how"` and that currently stands, asking `stands()` and
        # never `standing_apt` -- so a Kind declaring `"how"` with
        # `standing_apt` absent had established, placed, governing material
        # delivered to every execution in a Conversation and absent from this
        # register, which is the one surface built for finding governed material.
        # `standing_apt` keeps its own meaning: it is still what decides for
        # every Kind that does NOT direct work.
        #
        # AND THE TWO GROUNDS ARE KEPT APART, BECAUSE THEY ARE DIFFERENT CLAIMS.
        # One list did both, so a standing `finding`, `lesson` or `hypothesis`
        # arrived under the word "governed" while `compose` delivers none of
        # them as governance -- the register asserting of propositional material
        # exactly the thing the two ladders exist to stop anything asserting.
        # DROPPING THEM WAS NOT THE ANSWER EITHER: standing is meaningful for
        # them, correcting one is a supersession, and this is the surface the
        # owner finds material through -- hiding it would make a standing lesson
        # reachable only by somebody who already knew its `ent-*` id, which is
        # the defect this module was written for. So both are walked, and each
        # row says which ladder it is on.
        ground = ground_of(k)
        if ground == "directs_work":
            listed.append(name)
            directs_work.append(name)
        elif ground == "standing_knowledge":
            listed.append(name)
            standing_knowledge.append(name)
        elif ground == "standing_not_meaningful":
            declined.append(name)
        else:
            unknown.append(name)

    # WHICH KINDS THIS READ WALKS. By default the ones that declare standing
    # meaningful. A Kind asked for by name is walked if its answer is true or
    # UNKNOWN; one that declares standing not meaningful is not governed
    # material by its own declaration, and the answer says so.
    if kind is None:
        walk = listed
    elif kind in declined:
        walk = []
    else:
        walk = [kind]

    # -- each set read once ------------------------------------------------
    entries, per_kind = [], {}
    for name in walk:
        got = corpus.entries_of_kind(name)
        per_kind[name] = len(got)
        entries += [(name, e) for e in got]
    ids = {e["id"] for _, e in entries}

    placed_by: dict[str, list[str]] = {}
    brain_wide = whole_brain_ids(corpus)
    made_by: dict[str, list[str]] = {}
    if ids:
        # An ended placement is history, not a place it applies. Asked of the
        # superseding links themselves rather than of `stands`, which this
        # read keeps for the rows a search kept.
        sup = corpus.superseding_relation()
        for link in corpus.links(relation=SCOPED_TO):
            if link["link"]["from"] in ids and not corpus.links(
                    relation=sup, to=link["id"]):
                placed_by.setdefault(link["link"]["from"], []).append(
                    link["link"]["to"])
        for link in corpus.links(relation=PRODUCED):
            if link["link"]["to"] in ids:
                made_by.setdefault(link["link"]["to"], []).append(
                    link["link"]["from"])
    # Only the acts a row names, each by its indexed id -- never the table.
    acts = {}
    for aid in sorted({a for v in made_by.values() for a in v}):
        got = corpus.operational(id=aid)
        if got:
            acts[aid] = got[0]

    people = {e.get("attributed_to") for _, e in entries}
    people |= {a["actor"] for a in acts.values()}
    places = {c for v in placed_by.values() for c in v}
    places |= {a.get("conversation") for a in acts.values()}
    # A CONVERSATION UNDER ITS CURRENT NAME, A PARTICIPANT UNDER ITS CURRENT
    # ALIAS: one that was renamed is read as it now reads
    # (`versions.presented`). Nothing else here reads differently.
    from mentis.conversation.versions import presented
    named = {x["id"]: (presented(corpus, x) if (x.get("definition") or {}).get(
                 "name") in ("conversation", "participant") else x
                       ).get("body") or {}
             for x in corpus.read(sorted(i for i in people | places if i))}

    personas = ({e["id"] for e in corpus.entries_of_kind(PERSONA)}
                if places else set())

    def alias(p):
        return named.get(p, {}).get("alias", p)

    def conv_name(c):
        return named.get(c, {}).get("name")

    rows = []
    for name, e in entries:
        pinned = corpus.definition_for(e) or {}
        principal, second = _summary(
            e, pinned.get("body", {}).get("fields") or kinds[name]["fields"])
        # THE WHOLE BRAIN IS SAID, NOT LEFT TO BE INFERRED: `whole_brain`
        # marks the one placement that applies in every Conversation, and a
        # reader filtering by Conversation must count it as here.
        # AND A PERSONA IS SAID, NOT LEFT TO READ AS A CONVERSATION: material
        # placed on a Persona is carried by it and reaches only an execution
        # operating as it. `destination_kind` names what the destination is.
        placed = [{"conversation": c, "name": conv_name(c),
                   **({"whole_brain": True} if c in brain_wide else {}),
                   **({"persona": True, "destination_kind": PERSONA,
                       "carried_by": (f"carried by Persona {conv_name(c) or c}"
                                      if corpus.stands(c)["stands"] else
                                      f"placed on Persona {conv_name(c) or c}, "
                                      f"which does not stand; it carries "
                                      f"nothing")}
                      if c in personas else {})}
                  for c in dict.fromkeys(placed_by.get(e["id"], []))]
        proposed_by = [{
            "act": aid, "act_type": a["act"], "actor": a["actor"],
            "actor_alias": alias(a["actor"]),
            "conversation": a.get("conversation"),
            "conversation_name": conv_name(a.get("conversation")),
            "turn": a.get("turn")}
            for aid in made_by.get(e["id"], []) if (a := acts.get(aid))]
        row = {"entry": e["id"], "kind": name,
               "standing_apt": kinds[name]["standing_apt"],
               # WHICH LADDER THIS ROW IS ON, read through the one lookup
               # delivery reads it through, and ABSENT stays absent as None.
               # `governs` is the same fact said as the answer a reader of this
               # register actually wants, so that nothing has to infer it from
               # a Kind's name -- which is the one thing nothing here may do.
               "knowing": kinds[name]["knowing"],
               "governs": kinds[name]["knowing"] == KNOWING_HOW,
               "summary": principal, "secondary": second,
               "attributed_to": e.get("attributed_to"),
               "author_alias": alias(e.get("attributed_to")),
               "at": e.get("recorded_at"),
               "placed_at": placed, "proposed_by": proposed_by}
        if tokens:
            hay = [e["id"], name, row["author_alias"] or ""]
            hay += [v for v in (e.get("body") or {}).values()
                    if isinstance(v, str)]
            hay += [p["name"] or "" for p in placed]
            hay += [p["actor_alias"] or "" for p in proposed_by]
            hay += [p["conversation_name"] or "" for p in proposed_by]
            text = " ".join(hay).lower()
            if not all(t in text for t in tokens):
                continue
        rows.append(row)

    # -- standing, only for what survived the search -------------------------
    from mentis.conversation.governance import disputes_of, proposed_supersessions
    for row in rows:
        standing = corpus.stands(row["entry"])
        row["established_by"] = standing["established_by"]
        row["superseded_by"] = standing["superseded_by"]
        # A DISPUTE IS SHOWN, NOT OBEYED. It revokes nothing: a disputed
        # entry that stands still stands.
        row["disputed_by"] = standing["incoming"].get("disputes", [])
        # WHICH OF THOSE ARE STILL OPEN: not set aside and not withdrawn
        # (`disputes_of`). Every challenge stays in `disputed_by`; this is
        # what still waits on somebody, so nothing has to count resolved
        # challenges as if they did.
        row["open_disputes"] = ([d["disputed_by"] for d in disputes_of(
            corpus, row["entry"]) if d["open"]] if row["disputed_by"] else [])
        # AND A PROPOSED REPLACEMENT IS SHOWN, AND OBEYED EVEN LESS. It is
        # NOT `superseded_by`: the row above is what ended this, and this is
        # what is merely put forward to. A row carrying four competing
        # proposals is still a row that stands, and its `state` is computed
        # from `standing` alone -- nothing here touches it.
        row["proposed"] = proposed_supersessions(
            corpus, row["entry"], limit=REGISTER_PROPOSALS)
        # A proposed version belongs in the predecessor's conversation view
        # while reaching nobody. Read the intended context from the existing
        # proposal relation, not from a placement that has not happened yet.
        proposed = row["proposed"]
        row["proposed_reach"] = sorted({
            c for link in (corpus.links(relation=proposed["relation"], frm=row["entry"])
                           if proposed else [])
            for c in placed_by.get(link["link"]["to"], [])})
        # UNKNOWN IS NOT CONVERTED. See the module docstring and `group_of`.
        row["state"], row["group"] = group_of(kinds[row["kind"]], standing)
        if row["group"] == "proposed":
            from mentis.conversation.ladder_writes import requests
            row["group"] = ("proposed" if requests(corpus, row["entry"], open_only=True)
                            else "recorded")


    if state is not None:
        rows = [r for r in rows if r["group"] == state]
    # Newest first. Entries written in the same instant keep the order they
    # were written in (the store's), so the cut `limit` makes is stable.
    order = {e["id"]: i for i, (_, e) in enumerate(entries)}
    rows.sort(key=lambda r: (r["at"] or 0, order[r["entry"]]), reverse=True)
    whole = {g: [r for r in rows if r["group"] == g] for g in GROUPS}
    if offset is None:
        groups = {g: v[:cap] for g, v in whole.items()}
        next_cursor = None
    else:
        page = rows[offset:offset + cap]
        groups = {g: [r for r in page if r["group"] == g] for g in GROUPS}
        next_cursor = (f"g1.{offset + len(page)}"
                       if offset + len(page) < len(rows) else None)

    # NOT LISTED IS NOT FORGOTTEN. Whatever this read did not walk is said,
    # with how much of it there is, so an empty group is never mistaken for
    # an empty record.
    unknown_counts = [{"kind": n, "entries": corpus.count_of_kind(n)}
                      for n in unknown if n not in walk]
    return {
        "query": {"kind": kind, "q": q or "", "state": state,
                  "limit": cap, **({"cursor": cursor} if cursor is not None else {})},
        "groups": groups,
        "totals": {g: len(v) for g, v in whole.items()},
        "omitted": {g: len(whole[g]) - len(groups[g]) for g in GROUPS},
        "matched": len(rows),
        **({"next_cursor": next_cursor} if offset is not None else {}),
        "walked": len(entries),
        "kinds": {"listed": listed, "walked": per_kind,
                  # THE TWO GROUNDS FOR BEING LISTED, NAMED SEPARATELY.
                  # `listed` is still their union, so nothing reading it breaks;
                  # what it no longer does is imply one reason.
                  "directs_work": directs_work,
                  "standing_knowledge": standing_knowledge,
                  "standing_not_meaningful": declined,
                  "standing_apt_unknown": unknown_counts},
        "listed_because": {
            "directs_work": "its Kind declares that its material directs how "
                            "work is done, so placed and standing it GOVERNS "
                            "the work -- this is what delivery carries as "
                            "governance",
            "standing_knowledge": "standing is meaningful for its Kind and its "
                                  "material STATES something rather than "
                                  "directing work. It governs nothing, and "
                                  "delivery never carries it as governance. It "
                                  "is here because correcting it is a "
                                  "supersession and this is where it is found",
        },
        "governs_is_per_row": "a row's `governs` is its Kind's own declaration "
                              "and not its presence in this register. Being "
                              "listed here means standing applies to it, never "
                              "that it directs anybody's work",
        "why_not": ("its Kind declares standing not meaningful, so it is not "
                    "governed material" if kind in declined else None),
        "not_an_ask": "recorded material asks nobody anything; proposed means an "
                      "explicit adoption request. The ask itself is an expectation",
    }
