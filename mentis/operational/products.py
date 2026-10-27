"""What operational work LEFT BEHIND, read from the record and nothing else.

Happening answers "what is going on". This answers the next question down:
"what durable thing does that work now leave in the brain, and how did it come
to exist". Both are reconstructed; neither is stored.

THE ONE RULE. Production is read from the ordinary `produced` Relation and
from NOTHING ELSE. Not from `about[]`, which has always meant "this act
concerned these things" and never meant production. Not from a Kind name, not
from an act name, not from prose. An act that mentions a Finding referenced it;
an act with a `produced` link to that Finding made it. The fixture holds both
cases on purpose, one Turn apart, because the difference is invisible to any
reading that guesses.

WHAT IS GENERIC AND WHAT IS NOT. A Kind is self-describing and open-ended:
anybody may define one through the ordinary public vocabulary, so nothing here
may enumerate Kind names. What a product IS comes back as the Kind's own
declared terminology -- its name, its declared `meaning`, its declared fields
and whatever else it declared -- carried verbatim for a reader to render. A
FAMILY is different: `entry` and `admission` are substrate, fixed and few, and
keying on one is reading the record rather than guessing at it.

Built on the public seam only -- no store, no SQL, no record shapes.
"""

from __future__ import annotations

PRODUCED = "produced"

#: The substrate families a product can belong to, and the declared field that
#: carries each one's own summary line where the Kind does not say. This is
#: FAMILY knowledge -- substrate, closed and small -- never Kind knowledge.
_FAMILY_SUMMARY = {"admission": ("locator", "source")}


def _definition_properties(corpus, entry) -> tuple[dict, list[str] | None]:
    """A Kind's own declared description, verbatim, and its declared fields.

    The definition the entry was WRITTEN AGAINST, never a later version of it,
    so what a product says it is cannot be changed underneath it.
    """
    defn = corpus.definition_for(entry)
    if defn is None:
        return {}, None
    props = dict(defn["body"])
    fields = props.pop("fields", None)
    # `kind`/`relation` name the definition; they are its identity, returned
    # separately, and are not part of what it DECLARED about itself.
    props.pop("kind", None)
    props.pop("relation", None)
    props.pop("inverse", None)
    props.pop("directed", None)
    props.pop("substrate_role", None)
    return props, (list(fields) if isinstance(fields, (list, tuple)) else None)


def describe_entry(corpus, entry_id) -> dict | None:
    """What a durable Entry says it is, in its own declared terms.

    Nothing here interprets. `meaning` is the string the Kind's author wrote
    when they defined it; where a Kind declared none, it comes back absent and
    a reader must say so rather than supply one.
    """
    got = corpus.read([entry_id])
    if not got:
        return None
    e = got[0]
    ref = e.get("definition") or {}
    props, declared = _definition_properties(corpus, e)
    body = e.get("body") or {}
    family = e.get("family")
    fields = declared or _FAMILY_SUMMARY.get(family) or sorted(body)
    summary = next((body[f] for f in fields
                    if isinstance(body.get(f), str) and body[f].strip()), None)
    return {
        "entry": entry_id,
        "family": family,
        "kind": ref.get("name"),
        "version": ref.get("version"),
        # The Kind's own words. Absent where the Kind declared none.
        "meaning": props.get("meaning"),
        "properties": props,
        "fields": list(fields),
        "body": body,
        "summary": summary,
        "attributed_to": e.get("attributed_to"),
        "written_by": e.get("written_by"),
        "at": e.get("recorded_at"),
    }


def products_of(brain, act_ids=None) -> dict[str, list[dict]]:
    """Per operational act, the durable Entries it brought into being.

    Keyed by act id; an act that produced nothing is simply absent. Reading
    every `produced` link once and grouping beats asking per act, and the
    answer is the same.

    NAMED ACTS ARE ASKED ABOUT BY NAME. With `act_ids`, only those acts'
    `produced` links are read, in one indexed read: every Source sweep
    `produces` each Admission it made, so reading the whole relation to answer
    for one Conversation's acts read one link per Admission in the Brain (R2).
    """
    corpus = brain.primary
    wanted = None if act_ids is None else set(act_ids)
    out: dict[str, list[dict]] = {}
    for link in corpus.links(relation=PRODUCED, frm_any=wanted):
        ref = link["link"]
        frm, to = ref["from"], ref["to"]
        if wanted is not None and frm not in wanted:
            continue
        seen = describe_entry(corpus, to)
        if seen is None:
            # The relation points at something this brain cannot read. Say so;
            # do not drop it, and do not invent what it was.
            seen = {"entry": to, "family": None, "kind": None, "meaning": None,
                    "properties": {}, "fields": [], "body": {},
                    "summary": None, "unreadable": True}
        out.setdefault(frm, []).append({**seen,
                                        "why": (link.get("body") or {}).get("reason")})
    for rows in out.values():
        rows.sort(key=lambda r: (r.get("at") or 0, r["entry"]))
    return out


def provenance_of(brain, entry_id) -> dict:
    """From a durable Entry back to the work that made it.

    `produced-by` is the inverse of `produced`; the act it names carries the
    actor, the execution, the Turn and the Conversation, and `caused_by` walks
    back from there to the steer that started it. Every fact below is read from
    the same record the forward direction was read from -- there is no second
    provenance store, and there must never be one.
    """
    cv, corpus = brain.conversations, brain.primary
    product = describe_entry(corpus, entry_id)
    made_by = [x["link"]["from"] for x in corpus.links(relation=PRODUCED, to=entry_id)]
    if not made_by:
        return {"entry": entry_id, "product": product, "produced_by": [],
                "why_not": "no act claims to have produced this, so nothing "
                           "here says anything did"}
    acts = {a["id"]: a for a in cv.history()}
    out = []
    for aid in made_by:
        act = acts.get(aid)
        if act is None:
            out.append({"act": aid, "missing": True})
            continue
        chain = causal_chain(acts, aid)
        turn = act.get("turn") or next(
            (acts[c]["turn"] for c in chain if acts.get(c, {}).get("turn")), None)
        out.append({
            "act": aid,
            "act_type": act["act"],
            "actor": act["actor"],
            "actor_alias": cv.alias(act["actor"]),
            "because": act.get("because"),
            "at": act.get("at"),
            "execution": act.get("execution"),
            "runtime": act.get("runtime"),
            "conversation": act.get("conversation"),
            "turn": turn,
            "turn_number": cv.turn_number(turn) if turn else None,
            # oldest first: the steer, then what it caused, down to this act
            "caused_by": list(reversed(chain)),
        })
    return {"entry": entry_id, "product": product, "produced_by": out}


def causal_chain(acts: dict, act_id) -> list[str]:
    """`caused_by` walked back from one act, newest first, cycles refused."""
    chain, seen, at = [], {act_id}, acts.get(act_id, {}).get("caused_by")
    while at and at not in seen:
        seen.add(at)
        chain.append(at)
        at = acts.get(at, {}).get("caused_by")
    return chain
