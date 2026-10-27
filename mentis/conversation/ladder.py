"""The Epistemic Ladder, read from the record: status, evidence and use.

THREE TIERS, AND NONE OF THEM IS STORED. Material an agent or person wrote down
and nobody established is RECORDED evidence. Material of a `knowing: that`
Kind the owner established is ADOPTED knowledge -- the Brain's working position,
within its limits. Material of a `knowing: how` Kind that stands and is placed
or named GOVERNS work. Which of these an entry is, and where it is on the way
between them, is computed here from links and acts every time it is asked,
because a status kept as a mutable flag is a second copy of the record that can
disagree with it -- and the record is the one that is right.

WHAT THIS MODULE IS FOR. Three readers need the same answers and must not get
different ones: delivery (`Conversations.compose`, which decides what a run is
handed and labels it), the Ladder APIs that feed Fluid's Learning, For adoption
and item views, and the register. So the reads live here, once, with the
signatures the shared contract (adm-f1e2ba554f77 §4) fixed, and every caller
asks them rather than re-deriving status from links of its own.

READS ONLY. Nothing here writes, establishes, opens an ask or closes one. The
acts that change any of these answers -- record, request adoption, adopt,
decline, challenge, set aside -- are the web and worker layers', and this
module only reports what they left in the record.

NO KIND NAME DECIDES ANYTHING. Which material is propositional is `knowing` on
the Kind's CURRENT definition; whether recording one needs a basis is its
`requires_basis`, which the write door asks and nothing here does: delivery
labels unbased material "no basis recorded" (owner decision 6) rather than
asking any Kind property whether to deliver it. Relation names are used, because a relation
name is what a link IS -- the contract fixes them (§2) -- but no branch here
asks whether an entry is a `lesson` or a `finding`.
"""

from __future__ import annotations

from . import KNOWING_THAT, knowing_of
from .governance import WITHDRAWS, _alias, _said, disputes_of
from .versions import CONTRIBUTION, deletion_of

# -- the relations the ladder is written on (contract §2) -------------------

DERIVED_FROM = "derived-from"
EXTRACTED_FROM = "extracted-from"
OUTCOME_OF = "outcome-of"
IN_CONTEXT = "in-context"
SUPPORTS = "supports"
DISPUTES = "disputes"
PROPOSES = "proposes"
DECLINES = "declines"
# WITHDRAWS is governance's: `disputes_of` reads it to close a challenge.
PROPOSES_TO_SUPERSEDE = "proposes-to-supersede"
PRODUCED = "produced"

#: WHAT AN ENTRY WAS CONCLUDED OR DRAWN FROM. Both directions of lineage are
#: read over these two and no others: `supports` and `disputes` are argument,
#: not ancestry, and may form any shape (§2).
BASIS_RELATIONS = (DERIVED_FROM, EXTRACTED_FROM)

#: WHAT AN ENTRY RESTS ON, as a reader is shown it: its basis, and -- for an
#: outcome -- what was tried and where, which are an outcome's grounds the way
#: a basis is a lesson's. Not lineage: an outcome is not descended from what
#: it is an outcome of, and `lineage` keeps reading BASIS_RELATIONS alone.
GROUNDS_RELATIONS = (*BASIS_RELATIONS, OUTCOME_OF, IN_CONTEXT)

#: THE ACTS THAT SAY WHO RECORDED SOMETHING, best first. `material-recorded`
#: is the act `record_material` writes; `material-proposed` is what every
#: earlier door wrote and is still what an alias writes, so material from
#: before this release is attributed by the same read.
RECORDING_ACTS = ("material-recorded", "material-proposed")

#: THE STATUS VALUES, in the precedence `adoption_status` applies (§2).
DELETED = "deleted"
SUPERSEDED = "superseded"
ADOPTED = "adopted"
ADOPTION_REQUESTED = "adoption_requested"
DECLINED = "declined"
RECORDED = "recorded"

#: THE TWO KNOWLEDGE BOUNDS (owner decision 4): adopted knowledge and
#: relevant experience are each cut on their own, so recorded material can
#: never crowd adopted material out of a delivery, nor the reverse.
ADOPTED_BOUND = 5
EXPERIENCE_BOUND = 5

#: The tiers a delivered component can be on. `Component.tier` holds one of
#: these, or None for what is on no ladder (orientation, the request).
GOVERNING = "governing"
ADOPTED_TIER = "adopted"
EXPERIENCE = "experience"

#: HOW MANY OUTCOMES A TRAILER CARRIES. Three is the contract's number, and it
#: is a rendering bound, not a judgement: every outcome stays readable from
#: `outcomes_of`, and the trailer says how many there were in all.
TRAILER_OUTCOMES = 3


# -- small reads --------------------------------------------------------------


def _entry(corpus, eid):
    got = corpus.read([eid]) if eid else []
    return got[0] if got else None


def _kind(entry) -> str | None:
    return ((entry or {}).get("definition") or {}).get("name")


def _declared(corpus, kind, prop):
    """A property of the Kind's CURRENT definition, or None where absent."""
    if not kind:
        return None
    return ((corpus.current_definition(kind) or {}).get("body") or {}).get(prop)


def _text(entry) -> str:
    v = ((entry or {}).get("body") or {}).get("text")
    return v if isinstance(v, str) else ""


def is_act_words(corpus, eid) -> bool:
    """Is this entry the WORDS OF AN ACT on something else, rather than
    material in its own right?

    A challenge is written as a note holding the objection, linked `disputes`
    to its target; an adoption request is a note holding the because, linked
    `proposes`; a decline is a note holding the reason, linked `declines`; a
    withdrawal is a note holding the reason, linked `withdraws`; a set-aside
    is a `supports` naming the dispute it answers. Each of those
    notes is ESTABLISHED by its act or may be recorded beside it -- and neither
    makes it something the Brain has adopted or something an agent recorded as
    what work taught it. Its words already travel WITH ITS TARGET (as the
    target's challenge, request or decline), so offering it again on its own
    would deliver an objection as if it were knowledge, labelled "adopted".
    """
    for x in corpus.links(frm=eid):
        rel = x["link"]["relation"]
        if rel in (DISPUTES, PROPOSES, DECLINES, WITHDRAWS):
            return True
        if rel == SUPPORTS and (x.get("body") or {}).get("sets_aside"):
            return True
    return False


# -- status -------------------------------------------------------------------


def _requests(corpus, eid) -> tuple[list[dict], list[dict]]:
    """The adoption requests naming this entry, and the declines that close
    them. A decline names its request in `body.request`; one that names none
    is read as answering every request open when it was written, since that is
    the only thing a decline without a request can have meant."""
    requests = sorted(corpus.links(relation=PROPOSES, to=eid),
                      key=lambda x: x["recorded_at"])
    declines = sorted(corpus.links(relation=DECLINES, to=eid),
                      key=lambda x: x["recorded_at"])
    return requests, declines


def _open_requests(requests, declines) -> list[dict]:
    closed = set()
    for d in declines:
        named = (d.get("body") or {}).get("request")
        if named:
            closed.add(named)
        else:
            closed.update(r["id"] for r in requests
                          if r["recorded_at"] <= d["recorded_at"])
    return [r for r in requests if r["id"] not in closed]


def adoption_status(corpus, eid) -> str:
    """Where this entry is on the ladder, derived from the record now (§2).

    IN PRECEDENCE ORDER, and the order is the point. A deletion is a
    supersession whose successor is a deletion record, so it is asked first or
    it would read as merely superseded. What stands is adopted whatever was
    once requested or declined about it: adoption is the owner's act and it
    answers every request. Only then do requests speak: one with no decline
    naming it is open; requests that were all declined leave the material
    DECLINED -- which says the owner chose not to adopt it, and says nothing
    about whether it is true. Everything else is simply recorded.
    """
    if deletion_of(corpus, eid) is not None:
        return DELETED
    standing = corpus.stands(eid)
    if standing["superseded_by"]:
        return SUPERSEDED
    if standing["stands"]:
        return ADOPTED
    requests, declines = _requests(corpus, eid)
    if requests:
        return (ADOPTION_REQUESTED if _open_requests(requests, declines)
                else DECLINED)
    return RECORDED


# -- evidence -----------------------------------------------------------------


def _label(corpus, ref) -> tuple[str | None, str]:
    """A held reference as a reader recognises it: its Kind and a short
    statement. An artifact is named by its reference -- its bytes are not this
    module's to read -- and a Turn by its first line."""
    if not ref.startswith("ent-"):
        return None, ref
    e = _entry(corpus, ref)
    if e is None:
        return None, ref
    kind = _kind(e)
    if kind == CONTRIBUTION:
        parts = (e.get("body") or {}).get("parts") or []
        said = " ".join(p.get("text", "") for p in parts
                        if isinstance(p, dict) and p.get("type") == "text")
        return kind, (said.strip().splitlines() or [""])[0][:160]
    _, said = _said(corpus, ref)
    return kind, (said or "")[:160]


#: HOW MUCH OF A CITED PASSAGE IS QUOTED. A cite names bytes of an artifact;
#: short text passages are shown as what they say, anything else by range.
EXCERPT_BYTES = 400


def _artifact(corpus, ref, cite):
    """An artifact basis as a reader is shown it: its name, the cited byte
    range, and -- where the range is short text -- the passage itself. The
    digest and range were checked when the cite was written."""
    import re
    from mentis.artifacts import describe
    m = re.search(r"\[(\d+):(\d+)\]$", cite or "")
    span = [int(m[1]), int(m[2])] if m else None
    short = bool(span) and span[1] - span[0] <= EXCERPT_BYTES
    try:
        a = describe(corpus, ref, verify=True if short else "cached")
    except Exception:                                     # noqa: BLE001
        a = {}
    excerpt = None
    data = a.get("_bytes")
    if short and data:
        try:
            excerpt = data[span[0]:span[1]].decode("utf-8").strip() or None
        except UnicodeDecodeError:
            excerpt = None
    if a.get("state") in (None, "unknown", "not-an-artifact"):
        return None, span, excerpt
    return ({"name": a.get("name"), "size": a.get("size"),
             "media_type": a.get("claimed_media_type"), "url": a.get("url")},
            span, excerpt)


def basis_of(corpus, eid) -> list[dict]:
    """What this entry rests on, oldest first.

    Its own `derived-from` and `extracted-from` links -- written with it by
    `record_material`, or later by `derive-from` -- and, for an outcome, its
    `outcome-of` and `in-context` (GROUNDS_RELATIONS): an outcome recorded
    with both is not material "with no basis". `cite` is the passage of an
    artifact the link body names, kept as given; an artifact basis also says
    its `artifact` name, the cited `range` and, for short text, the `excerpt`.
    """
    out = []
    for x in sorted(corpus.links(frm=eid), key=lambda x: x["recorded_at"]):
        rel = x["link"]["relation"]
        if rel not in GROUNDS_RELATIONS:
            continue
        ref = x["link"]["to"]
        kind, label = _label(corpus, ref)
        cite = (x.get("body") or {}).get("cite")
        row = {"ref": ref, "relation": rel, "kind": kind, "label": label,
               "cite": cite}
        if ref.startswith("adm-"):
            art, span, excerpt = _artifact(corpus, ref, cite)
            row.update(artifact=art, range=span, excerpt=excerpt)
            if art and art.get("name"):
                row["label"] = art["name"]
        out.append(row)
    return out


def outcomes_of(corpus, eid, limit=None) -> list[dict]:
    """What happened when this was tried, newest first.

    NEVER ADDED UP. Each outcome is returned as what it is -- its `result`,
    whether it was actually `attempted`, its words, and the circumstances it is
    true of -- because a tally of results is a score, and the latest one does
    not win either. An outcome that was itself superseded (edited, deleted) is
    not this item's outcome any more and is left out.
    """
    rows = []
    for x in corpus.links(relation=OUTCOME_OF, to=eid):
        oid = x["link"]["from"]
        o = _entry(corpus, oid)
        if o is None or corpus.stands(oid)["superseded_by"]:
            continue
        body = o.get("body") or {}
        ctx = [c["link"]["to"] for c in corpus.links(relation=IN_CONTEXT,
                                                     frm=oid)]
        rows.append({"id": oid, "result": body.get("result"),
                     "attempted": body.get("attempted"),
                     "text": body.get("text"),
                     "in_context": ctx[0] if ctx else None,
                     "recorded_at": o.get("recorded_at")})
    rows.sort(key=lambda r: r["recorded_at"] or 0, reverse=True)
    return rows[:limit] if limit is not None else rows


def _withdrawals(corpus, eid) -> dict[str, dict]:
    """The earliest withdrawal of each challenge to this entry, by dispute."""
    out = {}
    for x in sorted(corpus.links(relation=WITHDRAWS, to=eid),
                    key=lambda x: x["recorded_at"]):
        dispute = (x.get("body") or {}).get("dispute")
        if dispute and dispute not in out:
            by = x.get("attributed_to")
            out[dispute] = {"link": x["id"], "by": by, "by_alias": _alias(corpus, by),
                            "because": _text(_entry(corpus, x["link"]["from"])),
                            "at": x.get("recorded_at")}
    return out


def challenges_of(corpus, eid) -> list[dict]:
    """Every challenge to this entry, each with its resolution.

    `governance.disputes_of`, said in the Ladder's shape. A challenge revokes
    nothing and none is ever hidden: `resolution` is `open`, `withdrawn` (the
    challenger took it back, `withdrawn` says who, why and when) or `set_aside`
    (the owner answered it, `set_aside` says the same). Whichever came first
    is the resolution; both stay readable. Delivery quotes only open ones; the
    item view and history show all of them.
    """
    out = []
    withdrawn = _withdrawals(corpus, eid)
    for d in disputes_of(corpus, eid):
        objection = _entry(corpus, d["disputed_by"])
        aside = d["set_aside"]
        aside = ({"link": aside["link"], "by": aside["by"],
                  "by_alias": aside["by_alias"],
                  "because": aside.get("reason"),
                  "at": aside["at"]} if aside else None)
        back = withdrawn.get(d["link"])
        resolution = "open"
        if back or aside:
            resolution = ("withdrawn" if back and (not aside or
                          (back["at"] or 0) <= (aside["at"] or 0))
                          else "set_aside")
        out.append({
            "link": d["link"], "objection": d["disputed_by"],
            "by": d["by"], "by_alias": d["by_alias"],
            "because": _text(objection) or d.get("reason") or "",
            "at": d["at"],
            "resolution": resolution,
            "withdrawn": back,
            "set_aside": aside})
    return out


def open_challenges(corpus, eid) -> list[dict]:
    return [c for c in challenges_of(corpus, eid) if c["resolution"] == "open"]


def _recording_act(corpus, eid) -> dict | None:
    """The act that recorded this entry, read through the `produced` link the
    recording door writes from its act to the entry."""
    acts = []
    for x in corpus.links(relation=PRODUCED, to=eid):
        got = corpus.operational(id=x["link"]["from"])
        if got:
            acts.append(got[0])
    for name in RECORDING_ACTS:
        mine = [a for a in acts if a.get("act") == name]
        if mine:
            return min(mine, key=lambda a: a.get("at") or 0)
    return acts[0] if acts else None


def recorded_by(corpus, cv, eid) -> dict:
    """Who recorded this, from where, in what work -- read off the act.

    THE ACT IS THE SOURCE, the entry is the fallback. `record_material` and
    `propose_material` record actor, Conversation, Turn, execution, runtime and
    (from this release) persona on their act, so nothing is stored twice. An
    entry written through a door that records no act -- the owner's generic
    authoring door -- is attributed to whoever the entry names, with every
    field the act would have supplied left None rather than guessed.

    `model` IS NONE UNLESS AN ACT SAID IT. No delivery record carries a model
    (`governance._unknown_model`), and a runtime is not a model.
    """
    e = _entry(corpus, eid) or {}
    act = _recording_act(corpus, eid)
    detail = (act or {}).get("detail") or {}
    who = (act or {}).get("actor") or e.get("attributed_to")
    conv = (act or {}).get("conversation")
    turn = (act or {}).get("turn")
    if conv is None and turn is not None:
        conv = cv.conversation_of(turn)
    persona = detail.get("persona")
    worn = _entry(corpus, persona) if isinstance(persona, str) and persona.startswith("ent-") else None
    return {"participant": who,
            "alias": cv.alias(who) if who else None,
            "runtime": (act or {}).get("runtime"),
            "model": detail.get("model"),
            "persona": persona,
            "persona_name": ((worn or {}).get("body") or {}).get("name") if worn else None,
            "conversation": conv,
            "conversation_name": cv.conversation_name(conv) if conv else None,
            "turn": turn,
            "number": cv.turn_number(turn) if turn else None,
            "execution": (act or {}).get("execution"),
            "at": e.get("recorded_at"),
            "act": (act or {}).get("id")}


def cited_by(corpus, eid) -> list[dict]:
    """Later material that names this as its basis, as what it is an outcome
    of, or as evidence it offers support to -- oldest first.

    A `supports` that SETS A DISPUTE ASIDE is not a citation: it answers a
    challenge to this entry, and `challenges_of` reports it there.
    """
    out = []
    for x in sorted(corpus.links(to=eid), key=lambda x: x["recorded_at"]):
        rel = x["link"]["relation"]
        if rel not in (DERIVED_FROM, OUTCOME_OF, SUPPORTS):
            continue
        if rel == SUPPORTS and (x.get("body") or {}).get("sets_aside"):
            continue
        frm = x["link"]["from"]
        out.append({"entry": frm, "kind": _kind(_entry(corpus, frm)),
                    "relation": rel, "by": x.get("attributed_to"),
                    "by_alias": _alias(corpus, x.get("attributed_to")),
                    "at": x.get("recorded_at")})
    return out


def lineage(corpus, eid, depth=3) -> dict:
    """What this came from, and what came from it, `depth` steps each way.

    UP is the basis, followed: what this was derived or extracted from, and
    what that was. DOWN is what was concluded from this, what happened when it
    was tried, and what was proposed to replace it. Each node says which
    relation brought it and from which node, so the strip can be drawn without
    a second read. Bounded, and a cycle cannot loop it: an id is visited once.
    """
    def node(ref, rel, via, d):
        kind, label = _label(corpus, ref)
        row = {"id": ref, "kind": kind, "label": label, "relation": rel,
               "via": via, "depth": d}
        e = _entry(corpus, ref) if kind else None
        if e is not None and "result" in (e.get("body") or {}):
            row["result"] = e["body"].get("result")
            row["attempted"] = e["body"].get("attempted")
        return row

    up, seen, frontier = [], {eid}, [eid]
    for d in range(1, depth + 1):
        nxt = []
        for cur in frontier:
            if not cur.startswith("ent-"):
                continue
            for x in corpus.links(frm=cur):
                rel, to = x["link"]["relation"], x["link"]["to"]
                if rel in BASIS_RELATIONS and to not in seen:
                    seen.add(to)
                    up.append(node(to, rel, cur, d))
                    nxt.append(to)
        frontier = nxt

    down, seen, frontier = [], {eid}, [eid]
    for d in range(1, depth + 1):
        nxt = []
        for cur in frontier:
            for x in corpus.links(to=cur):
                rel, frm = x["link"]["relation"], x["link"]["from"]
                if (rel in (*BASIS_RELATIONS, OUTCOME_OF,
                            PROPOSES_TO_SUPERSEDE) and frm not in seen):
                    seen.add(frm)
                    down.append(node(frm, rel, cur, d))
                    nxt.append(frm)
        frontier = nxt
    return {"up": up, "down": down}


# -- use by later work --------------------------------------------------------


def _tier_of_source(s) -> str | None:
    """The tier a delivery record's source row was delivered on.

    Recorded from this release; for an older row it is what the composition
    of the time could have meant. Before experience existed the question
    channel carried only standing material, so a `question:` row is adopted;
    governance-supplied material through any other scope governed."""
    if s.get("tier"):
        return s["tier"]
    if (s.get("scope") or "").startswith("question:"):
        return ADOPTED_TIER
    if s.get("supplied_as") == "governance":
        return GOVERNING
    return None


def delivered_to(cv, eid, *, deliveries=None) -> list[dict]:
    """Every execution a delivery record says this was delivered to, oldest
    first, and on which tier.

    FROM DELIVERY RECORDS AND NOTHING ELSE. Not who it applies to and not who
    could have been given it: who WAS, by the record the boundary wrote. A
    delivery says nothing about whether it was read.
    """
    out = []
    # `deliveries`: the log, where a caller reading many items read it once.
    for d in (cv._c.deliveries() if deliveries is None else deliveries):
        for s in d.get("behavioural_sources") or ():
            if s.get("source_id") != eid:
                continue
            out.append({"execution": d.get("execution"),
                        "participant": d.get("participant"),
                        "participant_alias": (cv.alias(d["participant"])
                                              if d.get("participant") else None),
                        "runtime": d.get("runtime"),
                        "conversation": d.get("conversation"),
                        "at": d.get("at"),
                        "tier": _tier_of_source(s)})
            break
    out.sort(key=lambda r: r["at"] or 0)
    return out


def _run_began(corpus, d) -> float:
    """When the run a delivery record was written for began.

    TWO IDS FOR ONE RUN. The delivery record names the execution boundary's
    reference (`exe-...`); the run's own acts name the runtime's execution
    (measured on INTEGRATION: `exe-566c84730519` delivered, every act of the
    same run `b16330b9-...`). So: the earliest act under the delivery's own
    id where there is one, else the latest `execution-started` by the same
    participant in the same Conversation at or before the delivery."""
    at = d.get("at") or 0
    acts = corpus.operational(execution=d["execution"]) if d.get("execution") else []
    if acts:
        return min([at, *((a.get("at") or 0) for a in acts)])
    if not d.get("conversation"):
        return at
    starts = [a.get("at") or 0 for a in corpus.operational(conversation=d["conversation"])
              if a.get("act") == "execution-started"
              and a.get("actor") in (d.get("participant"), None)
              and (a.get("at") or 0) <= at]
    return max(starts) if starts else at


def usage(corpus, cv, eid) -> dict:
    """How later work used this: delivered, cited, and what happened after.

    COUNTS OF RECORDS, NOT A SCORE. `outcomes_after_delivery` counts the
    outcomes recorded against this item after it was first delivered, by what
    they said happened; anything other than worked or failed is `other`,
    because the record checks `result` against no list. Never delivered means
    there is no "after", so it is None -- not zero, which would claim the
    looking had been done.

    "AFTER" IS AFTER THE RUN BEGAN. A dispatched run's delivery record is
    written when the run ends, so the outcome that run itself recorded is
    earlier than its delivery record and would not count. The run begins at
    `_run_began`; a delivery whose start the record cannot find begins at its
    own record.
    """
    delivered = delivered_to(cv, eid)
    cited = cited_by(corpus, eid)
    after = None
    if delivered:
        first = _run_began(corpus, delivered[0])
        after = {"worked": 0, "failed": 0, "other": 0}
        for o in outcomes_of(corpus, eid):
            if (o["recorded_at"] or 0) < first:
                continue
            r = str(o.get("result") or "").strip().lower()
            after[r if r in ("worked", "failed") else "other"] += 1
    return {"delivered": len(delivered),
            "executions": len({d["execution"] for d in delivered}),
            "cited": len(cited),
            "outcomes_after_delivery": after}


# -- what travels with delivered material ------------------------------------


def trailer(corpus, cv, eid) -> dict:
    """What travels with an adopted or experience component (§1.3).

    Attribution, basis, limits, the latest outcomes (at most three, with the
    total said), every OPEN challenge quoted, and the adoption status. All of
    it is read now; none of it is a summary somebody wrote.
    """
    e = _entry(corpus, eid) or {}
    outcomes = outcomes_of(corpus, eid)
    open_ = open_challenges(corpus, eid)
    limits = (e.get("body") or {}).get("limits")
    return {"recorded_by": recorded_by(corpus, cv, eid),
            "basis": basis_of(corpus, eid),
            "limits": limits if isinstance(limits, str) and limits.strip()
            else None,
            "outcomes": outcomes[:TRAILER_OUTCOMES],
            "outcomes_total": len(outcomes),
            "challenges": open_,
            "status": adoption_status(corpus, eid)}


def why_this_holds(corpus, eid) -> dict:
    """For GOVERNING material: the evidence on the item, and open challenges.

    One line a run can read beside a rule -- what supports it, what it was
    derived from, what happened when it was tried -- and the challenges still
    open against it, which do not stop it governing and are said so.
    """
    support = [x for x in corpus.links(relation=SUPPORTS, to=eid)
               if not (x.get("body") or {}).get("sets_aside")]
    basis = basis_of(corpus, eid)
    outcomes = outcomes_of(corpus, eid)
    kinds: dict[str, int] = {}
    for x in support:
        k = _kind(_entry(corpus, x["link"]["from"])) or "evidence"
        kinds[k] = kinds.get(k, 0) + 1
    for b in basis:
        k = b["kind"] or "source"
        kinds[k] = kinds.get(k, 0) + 1
    parts = [f"{n} {k}" for k, n in sorted(kinds.items())]
    if outcomes:
        parts.append(f"{len(outcomes)} outcome"
                     f"{'s' if len(outcomes) != 1 else ''} ("
                     + ", ".join(str(o["result"]) for o in
                                 outcomes[:TRAILER_OUTCOMES]) + ")")
    return {"why": ("why this holds: " + ", ".join(parts)) if parts
            else None,
            "supports": [x["link"]["from"] for x in support],
            "basis": basis, "outcomes": outcomes[:TRAILER_OUTCOMES],
            "challenges": open_challenges(corpus, eid)}


def _quote(s, n=120) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


#: WHAT THE STATUS SAYS TO A RUN, in words that ask for nothing.
_STATUS_WORDS = {
    ADOPTED: "adopted by the owner: the Brain's working position, within its "
             "limits",
    ADOPTION_REQUESTED: "adoption requested, not adopted",
    DECLINED: "adoption declined (says nothing about whether it is true), "
              "not adopted",
    RECORDED: "recorded, not adopted",
}

#: THE EXPERIENCE QUALIFIER'S WORDING. It says what the material is and asks
#: for nothing, so a recorded lesson rendered beside a rule cannot acquire the
#: force of one from the sentence introducing it.
EXPERIENCE_SAYS = ("recorded, not adopted; weigh it as evidence and check its "
                   "basis -- it is not an instruction")


def render_trailer(tr: dict, tier: str) -> str:
    """The trailer as one compact line under the component's words."""
    rb = tr["recorded_by"]
    who = [rb.get("alias") or rb.get("participant") or "unknown"]
    if rb.get("runtime"):
        who.append(rb["runtime"])
    if rb.get("persona"):
        who.append(f"as {rb.get('persona_name') or rb['persona']}")
    if rb.get("conversation_name") or rb.get("number"):
        who.append(f"{rb.get('conversation_name') or rb.get('conversation')}"
                   + (f" #{rb['number']}" if rb.get("number") else ""))
    bits = ["recorded by " + " · ".join(who)]
    if tr["basis"]:
        refs = ", ".join(f"{b['relation']} {b['ref']}"
                         + (f"[{b['cite']}]" if b.get("cite") else "")
                         for b in tr["basis"][:4])
        more = len(tr["basis"]) - 4
        bits.append(f"basis: {len(tr['basis'])} ({refs}"
                    + (f", +{more} more" if more > 0 else "") + ")")
    else:
        bits.append("basis: no basis recorded")
    if tr["limits"]:
        bits.append(f"limits: {_quote(tr['limits'])}")
    if tr["outcomes"]:
        said = "; ".join(
            f"{o['result']}" + (", attempted" if o.get("attempted") is True
                                else ", not attempted"
                                if o.get("attempted") is False else "")
            + f" ({o['id']})" for o in tr["outcomes"])
        extra = tr.get("outcomes_total", len(tr["outcomes"])) - len(
            tr["outcomes"])
        bits.append(f"outcomes: {said}"
                    + (f"; {extra} earlier" if extra > 0 else ""))
    for c in tr["challenges"]:
        bits.append(f"challenged by {c.get('by_alias') or c.get('by')}: "
                    f"“{_quote(c['because'])}”")
    status = _STATUS_WORDS.get(tr["status"], tr["status"])
    if tier == EXPERIENCE:
        status = EXPERIENCE_SAYS if tr["status"] == RECORDED else (
            f"{status}; weigh it as evidence and check its basis -- it is "
            f"not an instruction")
    bits.append(f"status: {status}")
    return "  — " + " · ".join(bits)


def render_governing_note(note: dict) -> str:
    """Why-this-holds and open challenges, under a governing component, or
    "" where there is neither: established with no evidence linked and
    nothing challenged is not worth a line, and saying "no evidence" under
    every rule would teach a run to skip the line that matters."""
    bits = [note["why"]] if note.get("why") else []
    for c in note["challenges"]:
        bits.append(f"open challenge by {c.get('by_alias') or c.get('by')}: "
                    f"“{_quote(c['because'])}” -- it still governs")
    return ("  — " + " · ".join(bits)) if bits else ""


# -- Relevant experience: who is eligible, and why not ------------------------


def experience_refusal(corpus, cv, eid, kind) -> str | None:
    """Why this RECORDED entry may not reach a run as experience, or None.

    THE CONDITIONS, each a fact about the record, never a name:

      not the words of an act (an objection, a request's because, a decline's
      or a withdrawal's reason -- they travel with their target);

      not deleted or superseded (MENTIS SUPPLIES WHAT IT CARRIES FORWARD, and
      a replaced version is not carried); not adopted, which is delivered as
      adopted knowledge instead.

    AND NOTHING ELSE, by the owner's decisions. Experience is recalled
    Brain-wide, each item showing its Conversation (D3); material with no
    basis is delivered labelled "no basis recorded" (D6); declined material
    stays, since declining says nothing about truth (D9).
    """
    if is_act_words(corpus, eid):
        return "the words of an act on other material, which travel with it"
    status = adoption_status(corpus, eid)
    if status in (DELETED, SUPERSEDED, ADOPTED):
        return {DELETED: "deleted", SUPERSEDED: "superseded",
                ADOPTED: "adopted, so delivered as adopted knowledge"}[status]
    return None


def neighbourhood(corpus, eid) -> list[tuple[str, str, str]]:
    """What a matched entry brings with it: what was concluded from it, and
    what happened when each of those was tried (S4).

    A PROBLEM BRINGS ITS SOLUTIONS AND THEIR OUTCOMES, said structurally: the
    entries `derived-from` this one, and the outcomes `outcome-of` each of
    them. No Kind is named, so a finding that gave rise to a lesson brings the
    lesson the same way. Returned as (entry, relation, via) in record order;
    eligibility is the caller's, asked of each the same way it is asked of a
    matched entry.
    """
    out, seen = [], {eid}
    for x in sorted(corpus.links(relation=DERIVED_FROM, to=eid),
                    key=lambda x: x["recorded_at"]):
        child = x["link"]["from"]
        if child in seen:
            continue
        seen.add(child)
        out.append((child, DERIVED_FROM, eid))
        for o in sorted(corpus.links(relation=OUTCOME_OF, to=child),
                        key=lambda x: x["recorded_at"]):
            oid = o["link"]["from"]
            if oid not in seen:
                seen.add(oid)
                out.append((oid, OUTCOME_OF, child))
    return out


def propositional(corpus, kind) -> bool:
    return knowing_of(corpus, kind) == KNOWING_THAT
