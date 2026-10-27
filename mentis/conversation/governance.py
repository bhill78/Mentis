"""The Governance reads: history, applicability, what executions received.

WHY THIS EXISTS. The engines these questions need were built and then had no
caller. `seam.history()` returns a supersession chain and nothing asked for one;
`stands(as_at=)` answers what held at a moment and nothing asked; delivery
records carry `behavioural_sources` on every row ever written and nothing reads
them. This module is the reading side, and it is READS ONLY -- it computes,
groups and counts, and it writes nothing and decides nothing.

THREE-VALUED THROUGHOUT, AND THE THREE ARE NEVER COLLAPSED.

  absent    there is no record to answer from. Nobody looked, or nothing was
            kept. It is not a zero.
  empty     there IS a record and it lists nothing. That is an answer: this
            execution received no behavioural material, and the record says so.
  unknown   the record cannot say. The payload as it was actually rendered is
            not kept, and no delivery record carries the model. Unknown is
            never turned into "none", and nothing is counted from it.

COUNTS ARE RECORDS, NOT SCORES. Every count here is a count of delivery
records. It says how often something was named, never how good it is, never how
often it was read, understood or followed -- and where there is no record, the
thing is UNCOUNTED rather than counted as zero.

NO KIND NAMES DECIDE ANYTHING. What is placeable, what reaches as a Persona and
what reaches only when named are read from the links and scopes the record
already holds, and from the one vocabulary constant this slice itself declares
(`PERSONA`, which `compose()` already reads for the same reason).
"""

from __future__ import annotations

from mentis.conversation import (KNOWING_HOW, PERSONA, PERSONA_CARRIED_PREFIX,
                                 SCOPED_TO,
                                 WHOLE_BRAIN_SCOPE, knowing_of,
                                 placements_now, standing_state,
                                 whole_brain_ids)
from mentis.spine import seed

#: The two ordinary relations the belief axis is written on. `disputes` is a
#: challenge; `supports` is the opposing act on the SAME axis, which is what
#: setting a dispute aside is -- see `mentis/web` for the act that writes it.
DISPUTES = "disputes"
SUPPORTS = "supports"
#: The challenger taking a challenge back (`ladder_writes.withdraw`): a note
#: holding the reason `withdraws` the challenged entry, naming the dispute.
WITHDRAWS = "withdraws"

#: The substrate ROLE, not a relation name. Which relation carries it is read
#: from the definitions -- see `_supersedes_name`.
SUPERSEDES_ROLE = seed.SUPERSEDES

#: WHAT COUNTS AS A GOVERNANCE ACT, as vocabulary and in one place. "What
#: changed?" is a question about governance, so it reads these and not the
#: whole operational record -- a Turn being said is not a governance act, and
#: listing it under "what changed" would bury the four acts that are.
#:
#: Nothing branches on these names; they select rows and no more.
GOVERNANCE_ACTS = (
    "material-proposed",
    # WHERE MATERIAL APPLIES IS PART OF WHAT GOVERNS. Placing material -- at a
    # Conversation or on the whole Brain -- and ending a placement change
    # which work it reaches, so somebody catching up is told.
    "material-placed",
    "placement-ended",
    # PUTTING SOMETHING FORWARD TO REPLACE SOMETHING IS ITS OWN FACT, and it
    # was the one act on this list's own subject that the list left out:
    # `/api/entries/<id>/propose-supersession` has always written it, and a
    # catch-up between two arrivals reported the dispute that followed it and
    # not the proposal itself. A proposal establishes nothing and ends
    # nothing -- which is exactly why somebody arriving needs to be told one
    # was made, rather than finding it only by opening the item.
    "supersession-proposed",
    "material-established",
    "material-superseded",
    "material-disputed",
    "dispute-set-aside",
    "material-revised",
    # EDIT AND DELETE (`mentis.conversation.versions`). An edit of material
    # nobody adjudicates, or of a candidate, is a supersession somebody
    # arriving has to be told about; a deletion ends standing. An edit of
    # standing material is written as `supersession-proposed`, above.
    "material-edited",
    "material-deleted",
)

#: An ARRIVAL. Recorded when somebody opens Governance, append-only, and keyed
#: by who arrived and when. It is the only "last looked" fact this record has,
#: and it is deliberately not a read-marker: THERE IS NO MARK AS READ ANYWHERE.
#: A catch-up is a pair of arrivals and the acts between them, so one arrival
#: bounds nothing and never-arrived is ABSENT, not zero.
ARRIVED = "governance-arrived"

#: How a component reached an execution, from the scope the composition
#: recorded. The GROUPS are the answer to "how did this reach me?", which is a
#: different question from "what is it?" -- and the one the execution sheet is
#: read for.
PERSONA_SCOPE = "invocation:persona"
NAMED_SCOPE = "invocation:named"
INVOCATION_SCOPE = "invocation"
BRAIN_SCOPE = "brain"
CONVERSATION_PREFIX = "conversation:"


def _alias(corpus, who) -> str | None:
    """The name a participant is known by, read from the record.

    THE ID IS NOT A NAME. A surface that mentions an act has to say who did it,
    and a shortened id says nothing to anybody -- so the alias is resolved the
    same way every other read resolves one: the participant entry is read and
    its own `alias` is used. Where the record has no name for it, the id is
    returned rather than a blank, because "somebody" would lose the one thing
    that is known.
    """
    if not who:
        return None
    from mentis.conversation.versions import presented
    got = corpus.read([who])
    if not got:
        return who
    # Its CURRENT alias: a renamed Participant is known by its new one.
    return (presented(corpus, got[0]).get("body") or {}).get("alias") or who


def _link_view(corpus, link_entry) -> dict:
    """One link, as the act it is: who, when, why, and between what."""
    link = link_entry["link"]
    return {"link": link_entry["id"], "relation": link["relation"],
            "from": link["from"], "to": link["to"],
            "reason": (link_entry["body"] or {}).get("reason"),
            "by": link_entry["attributed_to"],
            # WHO, IN THE NAME THEY ARE KNOWN BY. An in-situ line naming the
            # act had only the id and showed a shortened one.
            "by_alias": _alias(corpus, link_entry["attributed_to"]),
            "written_by": link_entry["written_by"],
            "at": link_entry["recorded_at"]}


# -- the belief axis: a dispute, and whether it was set aside -----------------


def disputes_of(corpus, entry_id) -> list[dict]:
    """Every challenge to this entry, and whether each one was set aside.

    A SET-ASIDE IS NOT A THIRD LINK AND IT IS NOT A SUPERSESSION OF THE
    DISPUTE. It is the opposing act on the same axis: the challenge was made,
    it was answered, and the material held. So it is a `supports` link between
    the same two objects, naming the dispute it answers, and the `disputes`
    link is left exactly where it was.

    WHICH MEANS BOTH FACTS STAY TRUE AT ONCE. The entry was disputed AND it
    stands. Neither erases the other, and this returns both rather than
    reducing them to one word.

    AND A WITHDRAWN CHALLENGE IS NOT OPEN EITHER. The challenger taking it
    back (`withdraws`, naming the dispute) closes it exactly as a set-aside
    does, and `withdrawn` says who, why and when; `ladder.challenges_of` says
    which came first. Without it a withdrawn challenge to standing material
    was still listed as waiting on the owner.
    """
    setting_aside = {}
    for e in corpus.links(relation=SUPPORTS, to=entry_id):
        answered = (e["body"] or {}).get("sets_aside")
        if answered:
            setting_aside.setdefault(answered, []).append(e)
    taking_back = {}
    for e in corpus.links(relation=WITHDRAWS, to=entry_id):
        dispute = (e["body"] or {}).get("dispute")
        if dispute:
            taking_back.setdefault(dispute, []).append(e)
    out = []
    for e in corpus.links(relation=DISPUTES, to=entry_id):
        row = _link_view(corpus, e)
        row["disputed_by"] = e["link"]["from"]
        aside = setting_aside.get(e["id"]) or []
        # Oldest wins: setting the same dispute aside twice is two acts and
        # the first one is when it happened. Both stay readable.
        row["set_aside"] = (_link_view(corpus, sorted(
            aside, key=lambda x: x["recorded_at"])[0]) if aside else None)
        back = taking_back.get(e["id"]) or []
        row["withdrawn"] = (_link_view(corpus, sorted(
            back, key=lambda x: x["recorded_at"])[0]) if back else None)
        row["open"] = row["set_aside"] is None and row["withdrawn"] is None
        out.append(row)
    return sorted(out, key=lambda r: r["at"])


# -- proposed successors: what is put forward, and has ended nothing ---------


def _said(corpus, entry_id) -> tuple[str | None, str | None]:
    """An entry's Kind and its principal statement, for a reader who has to
    tell two pieces of material apart on sight. No field name is special-cased:
    the Kind's declared order says which statement is principal."""
    got = corpus.read([entry_id])
    if not got:
        return None, None
    e = got[0]
    kind = (e.get("definition") or {}).get("name")
    pinned = corpus.definition_for(e) or {}
    fields = (pinned.get("body") or {}).get("fields") or []
    body = e.get("body") or {}
    order = list(fields) + [k for k in body if k not in fields]
    for k in order:
        v = body.get(k)
        if isinstance(v, str) and v.strip():
            return kind, v.strip()
    return kind, None


def proposed_supersessions(corpus, entry_id, *, limit=None) -> dict | None:
    """What is PROPOSED to replace this, and what this proposes to replace.

    THE READ THE INTERFACE NEEDED, AND THE DISTINCTION IT EXISTS TO KEEP. For
    one item a reader must be able to tell, at a glance and without inferring
    it, the successors that are merely PROPOSED -- which have ended nothing and
    reach nobody -- from the one that actually superseded it. Those are two
    different facts written on two different relations, and they are returned
    in two different fields so that no caller has to decide which a list is.

    None means NOT DECLARED: this record holds no relation that proposes the
    superseding role, which is a third answer and is not "none recorded".

    The spine answers the link question; this adds only what a reader needs to
    recognise the material -- its Kind, its principal statement, and where it
    stands. Bounded by the spine's own cap, with `omitted` saying what was left
    out.
    """
    found = corpus.proposed_supersessions(entry_id, limit=limit)
    if found is None:
        return None
    for side in ("successors", "predecessors"):
        for row in found[side]["items"]:
            kind, summary = _said(corpus, row["entry"])
            standing = corpus.stands(row["entry"])
            row.update({
                "kind": kind, "summary": summary,
                "by_alias": _alias(corpus, row["attributed_to"]),
                "stands": standing["stands"],
                "state": standing_state(standing),
            })
    return found


# -- one item's history: the timeline, oldest first --------------------------


def item_history(brain, entry_id) -> dict:
    """The supersession chain through this entry, and what happened on each.

    `seam.history()` has always returned the chain and has never had a caller.
    This is the caller: for each item in the chain, oldest first, what was
    written, whether anybody established it or nobody did, where it was placed,
    what superseded it and with what reason, which challenges were made and
    whether each was set aside, and what it ended.

    IT REACHES NO VERDICT. `standing_state` gives the four exclusive words and
    disputes are carried beside them, never over them.
    """
    corpus = brain.primary
    chain = corpus.history(entry_id)
    supersedes = _supersedes_name(corpus)
    rows = []
    for eid in chain:
        got = corpus.read([eid])
        if not got:
            # An id in the chain the record cannot produce is reported as
            # missing rather than dropped: a gap in a timeline is a fact.
            rows.append({"entry": eid, "missing": True})
            continue
        e = got[0]
        standing = corpus.stands(eid)
        established = [_link_view(corpus, x)
                       for x in corpus.links(to=eid)
                       if x["id"] in standing["established_by"]]
        # EVERY PLACEMENT EVER WRITTEN, each saying whether it was ended and
        # whether it is the whole Brain -- a timeline keeps a removed
        # placement as history rather than dropping it.
        brain_wide = whole_brain_ids(corpus)
        placed = [{**_link_view(corpus, x),
                   "whole_brain": x["link"]["to"] in brain_wide,
                   "ended_by": corpus.stands(x["id"])["superseded_by"]}
                  for x in corpus.links(relation=SCOPED_TO, frm=eid)]
        ended_by = [_link_view(corpus, x)
                    for x in corpus.links(to=eid)
                    if x["link"]["relation"] == supersedes]
        ended = [_link_view(corpus, x)
                 for x in corpus.links(frm=eid)
                 if x["link"]["relation"] == supersedes]
        rows.append({
            "entry": eid,
            "kind": (e.get("definition") or {}).get("name"),
            "body": e["body"],
            "at": e["recorded_at"],
            "attributed_to": e["attributed_to"],
            "written_by": e["written_by"],
            "state": standing_state(standing),
            # NOT ESTABLISHED IS SAID, NOT LEFT BLANK. An empty list here is
            # the sentence "nobody established this", which is why the
            # timeline can state it.
            "established": established,
            "placed_at": placed,
            "superseded_by": ended_by,
            "supersedes": ended,
            "disputes": disputes_of(corpus, eid),
            # PROPOSED IS NOT DONE, AND THE TIMELINE SAYS SO IN ITS OWN LINE.
            # `superseded_by` above is what ENDED this; these are what is
            # merely put forward to. A timeline that walked only `supersedes`
            # could show an item with four proposals against it as an item
            # nothing had ever been proposed against.
            "proposed": proposed_supersessions(corpus, eid),
        })
    proposal_relation = corpus.proposal_relation()
    return {"entry": entry_id, "chain": chain, "timeline": rows,
            "oldest_first": True,
            # Absent is said. A record that never declared the relation cannot
            # answer the question, which is not the same as answering "none".
            "proposal_relation": proposal_relation,
            "proposals_readable": proposal_relation is not None}


def _supersedes_name(corpus) -> str:
    """Which relation currently carries the superseding role, READ FROM THE DATA.

    The engine knows the two roles; it does not know what anybody called them,
    and neither does this. The name is looked up in the Relation definitions,
    exactly as the spine looks it up, so a record that calls it something else
    is read correctly and nothing here holds the string.
    """
    best = None
    for e in corpus.definitions():
        b = e["body"]
        if b.get("substrate_role") != SUPERSEDES_ROLE:
            continue
        if best is None or e["definition"]["version"] > best[0]:
            best = (e["definition"]["version"], b["relation"])
    if best is None:
        raise ValueError("no relation declares the superseding role")
    return best[1]


# -- standing as at a moment -------------------------------------------------


def standing_as_at(corpus, entry_id, as_at) -> dict:
    """What the record said about this entry then, and what it says now.

    `stands(as_at=)` has been implemented since the spine was written and has
    never had a caller. The then/now comparison an execution sheet asks for is
    exactly this, and it is returned as TWO answers side by side -- never
    merged, because "it did not stand until later" is a different statement
    from "it stands".
    """
    then = corpus.stands(entry_id, as_at=as_at)
    now = corpus.stands(entry_id)
    return {
        "entry": entry_id, "as_at": as_at,
        "then": {**then, "state": standing_state(then)},
        "now": {**now, "state": standing_state(now)},
        "changed": standing_state(then) != standing_state(now),
    }


# -- how material could reach anybody at all ---------------------------------


def applies(brain, entry_ids=None) -> dict:
    """Which way each piece of standing material can reach an execution.

    FOUR WAYS, READ FROM THE RECORD AND NOT FROM ANY KIND NAME:

      placed       it is placed at a Conversation AND its Kind declares that
                   its material directs how work is done, so it reaches
                   everybody acting there, whoever they are and whatever they
                   wear.
      by_persona   it is behavioural material a Participant may be operating
                   AS, so it reaches an execution that selected it and no
                   other. `compose()` reads the same vocabulary constant for
                   the same reason.
      when_named   nothing carries it to anybody. It reaches an execution only
                   when somebody names it for that invocation.
      any_way      no filter: every standing item, whichever of the above.

    PLACEMENT ALONE IS NOT A WAY MATERIAL REACHES ANYBODY, and saying it was
    made this read disagree with delivery. `compose` carries placed material
    whose Kind declares `knowing == "how"` and no other placed material -- see
    `placed_procedural` -- so a standing `lesson` that somebody had placed was
    reported HERE as reaching everybody acting there while delivery, correctly,
    never carried it. `placed_at` is still reported for it, because the
    placement is a fact; what is not reported is a way of reaching an execution
    that nothing takes.

    APPLIES IS NOT DELIVERED. This says what COULD reach an execution from
    where the material sits now. Whether anything ever did is a delivery
    question and is answered from delivery records -- see `conditions_for`.
    """
    corpus = brain.primary
    if entry_ids is None:
        entry_ids = [e["id"] for e in _standing_material(corpus)]
    personas = {e["id"] for e in corpus.entries_of_kind(PERSONA)}
    brain_wide = whole_brain_ids(corpus)
    rows = []
    for eid in entry_ids:
        # WHERE IT IS PLACED NOW. An ended placement carries nothing.
        placed = placements_now(corpus, eid)
        everywhere = any(p in brain_wide for p in placed)
        got = corpus.read([eid])
        kind = (got[0].get("definition") or {}).get("name") if got else None
        # THE SAME DECLARED FACT DELIVERY ASKS, through the same lookup. Not a
        # second computation of what governs: `knowing_of` is the one place the
        # question is answered, and `placed_procedural` asks it of the same
        # Kind definitions on the delivery side.
        directs_work = knowing_of(corpus, kind) == KNOWING_HOW
        # A PERSONA DESTINATION IS SAID AS WHAT IT IS. Material placed ON a
        # Persona is carried by it -- it reaches an execution operating as that
        # Persona and nobody else -- so it is never reported as reaching
        # everybody acting in a Conversation.
        on_any_persona = [p for p in placed if p in personas]
        elsewhere = [p for p in placed if p not in personas]
        # ONLY A PERSONA THAT STANDS CARRIES ANYTHING (`compose` withholds the
        # rest), so one that was deleted, superseded or never established is
        # said to carry nothing rather than counted as reaching runs.
        on_personas = [p for p in on_any_persona
                       if corpus.stands(p)["stands"]]
        idle = [p for p in on_any_persona if p not in on_personas]
        carried_by = [{"persona": p, "name": _name_of(corpus, p)}
                      for p in on_personas]
        if idle and directs_work and not on_personas and not elsewhere:
            names = ", ".join(_name_of(corpus, p) or p for p in idle)
            how, why = "when_named", (
                f"placed on Persona {names}, which does not stand, so it "
                f"carries this to nobody; it reaches an execution only when "
                f"named for that invocation")
        elif on_personas and directs_work:
            names = ", ".join(c["name"] or c["persona"] for c in carried_by)
            how, why = "placed", (
                f"carried by Persona {names}: placed on that Persona, and its "
                f"Kind declares that its material directs how work is done, so "
                f"it reaches an execution operating as that Persona")
            if elsewhere:
                why += ("; it is also placed "
                        + ("on the whole Brain" if everywhere
                           else "at a conversation")
                        + ", and reaches everybody acting there")
        elif placed and directs_work and everywhere:
            how, why = "placed", ("placed on the whole Brain, and its Kind "
                                  "declares that its material directs how work "
                                  "is done, so it reaches everybody acting in "
                                  "every Conversation and at Brain scope")
        elif placed and directs_work:
            how, why = "placed", ("placed at a conversation, and its Kind "
                                  "declares that its material directs how work "
                                  "is done, so it reaches everybody acting "
                                  "there")
        elif eid in personas:
            how, why = "by_persona", ("behavioural material a participant may "
                                      "be operating as; it reaches an "
                                      "execution that selected it")
        elif placed:
            how, why = "when_named", ("placed, but its Kind does not declare "
                                      "that its material directs how work is "
                                      "done, so placement carries it to "
                                      "nobody; it reaches an execution only "
                                      "when named for that invocation")
        else:
            how, why = "when_named", ("nothing carries it; it reaches an "
                                      "execution only when named for that "
                                      "invocation")
        current = corpus.current_definition(kind) if kind else None
        rows.append({
            "entry": eid, "kind": kind, "applies": how, "why": why,
            "placed_at": placed,
            "whole_brain": everywhere,
            # WHICH of `placed_at` is the whole-Brain destination, so a reader
            # listing Conversations does not list it as one.
            "whole_brain_at": [p for p in placed if p in brain_wide],
            # WHICH of `placed_at` are Personas, and their names: material a
            # Persona carries rather than material placed where work happens.
            "carried_by": carried_by,
            # PLACED ON A PERSONA THAT DOES NOT STAND: a fact about where it
            # sits, and no way of reaching anybody.
            **({"on_personas_not_standing": idle} if idle else {}),
            # Carried, not read: a facet that wants to narrow to what can be
            # true or false has the Kind's own answer, and ABSENT stays absent.
            "truth_apt": (current or {}).get("body", {}).get("truth_apt"),
        })
    return {"rows": rows,
            "facets": {
                "any_way": len(rows),
                "placed": sum(1 for r in rows if r["applies"] == "placed"),
                "by_persona": sum(1 for r in rows
                                  if r["applies"] == "by_persona"),
                "when_named": sum(1 for r in rows
                                  if r["applies"] == "when_named"),
            },
            "limit": "what could reach an execution from where this material "
                     "sits now. Not a record that anything did."}


def _name_of(corpus, eid) -> str | None:
    got = corpus.read([eid])
    return ((got[0].get("body") or {}).get("name")) if got else None


def _walks(corpus, kind) -> bool:
    """Is this Kind's material something this read has to account for?

    TWO ANSWERS AND THEY ARE DIFFERENT FACTS. `standing_apt is True` says
    standing is meaningful for the Kind, which is what the register reads and is
    unchanged. Absent is not false, so a Kind that has said nothing is not
    walked on that ground.

    AND MATERIAL THAT DIRECTS WORK IS WALKED WHATEVER `standing_apt` SAYS,
    because DELIVERY walks it: `compose` carries placed material whose Kind
    declares `knowing == "how"` and that currently stands, and it asks
    `stands()` without consulting `standing_apt` at all. So a Kind declaring
    `knowing: "how"` with `standing_apt` ABSENT had its established, placed
    material delivered to every execution in the Conversation while being
    invisible to this read and to the governed register -- governing material
    missing from the surfaces the owner corrects material through. `standing_apt`
    is not redefined by this and nothing is scored: the set walked is the set
    delivery can carry.
    """
    return (knowing_of(corpus, kind) == KNOWING_HOW
            or (corpus.current_definition(kind) or {}
                ).get("body", {}).get("standing_apt") is True)


def _material(corpus) -> list[dict]:
    """Every entry of every Kind this module walks, standing or not.

    ONE SELECTION, AND IT IS THIS ONE. `what_ended` used to walk a second one,
    written before `knowing` existed and never brought over: it filtered on
    `standing_apt is not True` alone, so it omitted ended PROCEDURAL material
    whose Kind leaves `standing_apt` absent -- material `applies`, the governed
    register and `governs()` all include, and which delivery carried while it
    stood. An item could therefore govern work, be replaced, and not appear on
    the surface whose whole question is what has ended here. Three readers of
    one question with two answers between them is the defect; a third selection
    would be the same defect again, so `_standing_material` is this read
    filtered and not a read of its own.
    """
    out = []
    seen = set()
    for e in corpus.definitions():
        kind = e["body"].get("kind")
        if not kind or kind in seen:
            continue
        seen.add(kind)
        if not _walks(corpus, kind):
            continue
        out += corpus.entries_of_kind(kind)
    return list({r["id"]: r for r in out}.values())


def _standing_material(corpus) -> list[dict]:
    """Every entry that stands, of every Kind this read walks. See `_walks`."""
    return [e for e in _material(corpus) if corpus.stands(e["id"])["stands"]]


# -- per-row conditions, from delivery records only --------------------------


def conditions_for(brain, entry_ids) -> dict:
    """How often each item actually reached an execution, and by which way.

    READ FROM DELIVERY RECORDS AND NOTHING ELSE. An entry existing, standing or
    being placed is not evidence that anything received it; only a delivery
    record is. Where there is none, the item is UNCOUNTED -- said as absent,
    never as zero, because zero would claim the looking was done.

    `executions_with_records` is the denominator and is stated, so "named for
    3 of 11 executions" can be said without anybody having to guess what the
    11 is.
    """
    corpus = brain.primary
    rows = corpus.deliveries()
    executions = {d["execution"] for d in rows}
    counts = {eid: {"as_persona": 0, "named": 0, "any": 0} for eid in entry_ids}
    seen = {eid: set() for eid in entry_ids}
    for d in rows:
        for s in d.get("behavioural_sources") or ():
            sid = s.get("source_id")
            if sid not in counts:
                continue
            counts[sid]["any"] += 1
            seen[sid].add(d["execution"])
            if s.get("scope") == PERSONA_SCOPE:
                counts[sid]["as_persona"] += 1
            elif s.get("scope") == NAMED_SCOPE:
                counts[sid]["named"] += 1
    out = []
    for eid in entry_ids:
        c = counts[eid]
        out.append({
            "entry": eid,
            "records": c["any"],
            "selected_as_persona_in": c["as_persona"],
            "named_in": c["named"],
            "executions": len(seen[eid]),
            # ABSENT, NOT ZERO. No record names it, so nothing was counted.
            "uncounted": c["any"] == 0,
            "why_uncounted": ("no delivery record names it" if not c["any"]
                              else None),
        })
    return {"rows": out,
            "executions_with_records": len(executions),
            "counts_are": "counts of delivery records. They say how often "
                          "something was named, never how good it is and "
                          "never that anybody read it."}


# -- one execution: what it actually received --------------------------------


#: WHICH WAY IT REACHED, from the scope the composition recorded. Each answer
#: is a fact about how the material got there, not about what it is.
def _how(source) -> tuple[str, str]:
    scope = source.get("scope") or ""
    kind = source.get("source_kind") or ""
    if scope == PERSONA_SCOPE:
        return "persona_selected", "selected as the Persona for this execution"
    if scope == NAMED_SCOPE:
        return "named", "named explicitly for this invocation"
    if scope == WHOLE_BRAIN_SCOPE:
        return "placed", ("durable material placed on the whole Brain, which "
                          "reaches every Conversation and Brain-scope work")
    if scope.startswith(PERSONA_CARRIED_PREFIX):
        return "placed", ("carried by the Persona this execution operated as: "
                          "material placed on that Persona")
    if scope == BRAIN_SCOPE or kind.endswith("orientation"):
        return "orientation", "compact orientation, computed at the time"
    if kind == "request":
        return "request", "what was being asked"
    if scope.startswith(CONVERSATION_PREFIX):
        return "placed", "durable material placed at that conversation"
    if scope == INVOCATION_SCOPE:
        return "supplied", "supplied for this execution only"
    # NOT CLASSIFIED IS SAID. A scope this does not recognise is carried with
    # its own name rather than swept into one of the answers above.
    return "other", f"recorded with scope {scope!r}"


GROUPS = ("persona_selected", "named", "placed", "supplied", "orientation",
          "request", "other")


def _persona_answer(records) -> dict:
    """Which Persona these delivery records name. THREE ANSWERS, KEPT APART.

      no_record          there is no record to say. Not "none": nobody looked,
                         or nothing was kept, and nothing may be concluded.
      lists_none         there IS a record and its sources name no Persona.
                         That says none was RECORDED, which is not the same as
                         none was worn, and nothing is counted from it.
      from_the_record    the record names one, and it is given as recorded.

    ONE HELPER BECAUSE IT IS ONE QUESTION. The execution sheet asks it of one
    execution and the per-execution question asks it of every execution in a
    scope; two copies would be two chances for one of them to answer "none"
    where the other says "no record". The first Persona the records name is the
    answer, in the order the record keeps them.
    """
    if not records:
        return {"answer": "no_record", "why": "there is no record to say"}
    for d in records:
        for s in d.get("behavioural_sources") or ():
            if s.get("scope") == PERSONA_SCOPE and s.get("source_id"):
                return {"answer": "from_the_record",
                        "persona": s["source_id"]}
    return {"answer": "lists_none",
            "why": "the record lists no Persona. That says none was RECORDED, "
                   "which is not the same as none was worn; nothing is counted "
                   "from it."}


def execution_sheet(brain, execution) -> dict:
    """What ONE execution received, grouped by how it reached it.

    THE THREE ANSWERS, KEPT APART. No delivery record at all is ABSENT: nothing
    was kept and nothing may be concluded. A record listing no behavioural
    material is EMPTY, and that is a real answer -- this execution received
    none, and the record says so. And what the payload actually looked like
    once rendered, and which model ran, are UNKNOWN: the entries are immutable
    and readable, the assembly of them is not kept, and no delivery record
    carries a model.

    NO PERSONA IN THE RECORD IS NOT "NO PERSONA". A record whose sources name
    none says only that none was recorded, so this returns the open question
    rather than the word "none".
    """
    corpus = brain.primary
    records = corpus.deliveries(execution=execution)
    if not records:
        return {
            "execution": execution, "record": "absent",
            "groups": {g: [] for g in GROUPS}, "sources": 0,
            "why": "no delivery record names this execution, so what it "
                   "received is not held. That is absent, not empty.",
            "persona": _persona_answer(records),
            "rendered_payload": _unknown_payload(),
            "model": _unknown_model(),
        }
    groups = {g: [] for g in GROUPS}
    total = 0
    for d in records:
        for s in d.get("behavioural_sources") or ():
            total += 1
            how, why = _how(s)
            groups[how].append({
                "source_kind": s.get("source_kind"),
                "source_id": s.get("source_id"),
                "scope": s.get("scope"),
                "how": how, "why": why,
                # THE OTHER PLACEMENT THAT WOULD HAVE CARRIED IT, delivered
                # once. Absent where there was one reason.
                **({"also": s["also"]} if s.get("also") else {}),
                # Invocation-scoped material has no durable identity, so there
                # is nothing to open and nothing to quote. Said, not implied.
                "durable": s.get("source_id") is not None,
                "text": None if s.get("source_id") is None else "read it from "
                        "the entry, which is immutable",
            })
    return {
        "execution": execution,
        "record": "empty" if total == 0 else "present",
        "records": [d["id"] for d in records],
        "participant": records[-1].get("participant"),
        "runtime": records[-1].get("runtime"),
        "conversation": records[-1].get("conversation"),
        "mechanism": records[-1].get("mechanism"),
        "at": records[-1].get("at"),
        "groups": groups,
        "sources": total,
        "why": ("the delivery record lists no behavioural material, so this "
                "execution received none. That is empty, not absent."
                if total == 0 else None),
        "persona": _persona_answer(records),
        "rendered_payload": _unknown_payload(),
        "model": _unknown_model(),
    }


def _unknown_payload() -> dict:
    return {"known": False,
            "why": "the entries are immutable and can be read exactly as they "
                   "were; how they were assembled into the payload is not "
                   "kept. Unknown."}


def _unknown_model() -> dict:
    return {"known": False,
            "why": "no delivery record carries a model. Unknown, and not "
                   "'not recorded' by any other record's account."}


# -- the other way round: which deliveries name a given item -----------------


def deliveries_naming(brain, entry_ids, *, conversation=None, limit=50) -> dict:
    """The delivery records that name these items, newest first.

    THE OTHER DIRECTION FROM `execution_sheet`. That one starts at an execution
    and asks what reached it; this starts at an ITEM and asks which deliveries
    named it. `conditions_for` already counts those records per item, but a
    count cannot be opened -- there was no way to reach the latest record for
    an item, and no way to ask which records named TWO items at once without a
    caller reading every delivery ever written and doing it itself.

    HOW IT REACHED IS THE SAME GROUPING THE EXECUTION SHEET USES, read from the
    scope the composition recorded and from nothing else. One record may name
    the same item more than once and by more than one way; every way is kept,
    because "it was the Persona AND it was named" is two facts.

    THE THREE ANSWERS, KEPT APART. An item no delivery record names is ABSENT
    -- uncounted, never a count of zero, because zero would claim the looking
    was done. A record listing no behavioural material at all is EMPTY, which
    is a real answer about that record and is reported as its own number rather
    than being quietly excluded. And what the payload looked like once rendered
    and which model ran stay UNKNOWN on every row, as everywhere else here.

    BOUNDED, AND NEVER SILENTLY. Counts are computed over every matching
    record; `limit` bounds only what is handed back, and what was left out is
    said. `per_entry` is one of those counts, so who received an item and which
    record named it last are answered over every matching record too -- which
    is why `what_was_used` asks this rather than counting the same rows again.
    """
    corpus = brain.primary
    asked = list(dict.fromkeys(entry_ids))
    wanted = set(asked)
    rows = corpus.deliveries()
    if conversation is not None:
        rows = [d for d in rows if d.get("conversation") == conversation]

    listing_nothing = 0
    matched = []
    for order, d in enumerate(rows):
        sources = d.get("behavioural_sources") or ()
        if not sources:
            # A record that lists nothing cannot name anything. It is EMPTY,
            # and saying how many there were is how a reader knows the silence
            # was read rather than skipped.
            listing_nothing += 1
            continue
        names: dict[str, list] = {}
        for s in sources:
            sid = s.get("source_id")
            if sid not in wanted:
                continue
            how, why = _how(s)
            names.setdefault(sid, []).append({
                "source_kind": s.get("source_kind"),
                "scope": s.get("scope"),
                "how": how, "why": why})
        if not names:
            continue
        matched.append({
            "_order": order,
            "delivery": d.get("id"),
            "execution": d.get("execution"),
            "participant": d.get("participant"),
            "runtime": d.get("runtime"),
            "conversation": d.get("conversation"),
            "mechanism": d.get("mechanism"),
            "at": d.get("at"),
            # keyed by the item asked about, so a caller comparing two never
            # has to work out which of them a row is about
            "names": names,
            "carries": [e for e in asked if e in names],
            "carries_all": len(names) == len(asked) and len(asked) > 1,
            "rendered_payload": _unknown_payload(),
            "model": _unknown_model(),
        })

    # newest first: the latest record for an item is the question being asked,
    # so it is the row at the top rather than one the caller must hunt for.
    # Two records stamped the same moment are broken apart by the order the
    # record itself keeps them in, never by an id, which would order them by
    # nothing that happened.
    matched.sort(key=lambda r: (-(r["at"] or 0), -r["_order"]))
    for r in matched:
        r.pop("_order")

    per_entry = []
    for eid in asked:
        mine = [r for r in matched if eid in r["names"]]
        per_entry.append({
            "entry": eid,
            "answer": "absent" if not mine else "named",
            "records": len(mine),
            "executions": len({r["execution"] for r in mine}),
            "latest": mine[0]["delivery"] if mine else None,
            "latest_execution": mine[0]["execution"] if mine else None,
            "latest_at": mine[0]["at"] if mine else None,
            "latest_participant": mine[0]["participant"] if mine else None,
            # WHO RECEIVED IT, from the records that named it and from nothing
            # else. Not who could have, not who it applies to: the participant
            # each record names. A record naming none is counted on its own
            # rather than dropped, because a delivery with no participant is a
            # fact about the record and not a participant of no name.
            "participants": sorted({r["participant"] for r in mine
                                    if r.get("participant")}),
            "records_naming_no_participant": sum(
                1 for r in mine if not r.get("participant")),
            # ABSENT, NOT ZERO. Nothing was counted because no record named it.
            "uncounted": not mine,
            "why_uncounted": (None if mine else
                              "no delivery record names it"),
        })

    both = [r for r in matched if r["carries_all"]]
    if len(asked) > 1:
        intersection = {
            "asked": len(asked),
            "records": len(both),
            "executions": len({r["execution"] for r in both}),
            "deliveries": [r["delivery"] for r in both[:limit]],
            "means": "delivery records that name every item asked about. It "
                     "says they arrived together, not that anything followed "
                     "from their arriving together.",
        }
    else:
        intersection = {
            "asked": len(asked), "records": None,
            "why": "one item alone intersects nothing. Name a second `entry` "
                   "to ask which records carry both.",
        }

    returned = matched[:limit]
    return {
        "question": "which deliveries name these items",
        "entries": asked,
        "deliveries": returned,
        "returned": len(returned),
        "total": len(matched),
        "omitted": max(0, len(matched) - len(returned)),
        "limit": limit,
        "per_entry": per_entry,
        "intersection": intersection,
        "records_considered": len(rows),
        "records_listing_no_behavioural_material": listing_nothing,
        "filtered_by": {"conversation": conversation},
        "counts_are": "counts of delivery records. They say how often "
                      "something was named, never how good it is and never "
                      "that anybody read it.",
        "empty": ("no delivery record names any of these items" if not matched
                  else None),
    }


# -- the four history questions ----------------------------------------------


def what_changed(brain, *, conversation=None, since=None, until=None,
                 between=None, limit=500) -> dict:
    """Question one: what changed here, in governance, and why.

    GOVERNANCE ACTS ONLY. The operational record holds everything anybody did;
    this reads the acts that changed what governs, so that four of them are not
    lost inside four hundred Turns. The reason is quoted as it was recorded --
    nothing here composes a sentence on anybody's behalf.

    `between` BOUNDS BY THE RECORD'S OWN WRITE ORDER, not by the clock, and it
    is what a catch-up uses. Two acts written inside one clock tick share a
    timestamp -- on this machine the tick is coarse enough that an arrival and
    the act just after it routinely do -- so a window measured in seconds
    cannot say which came first. `seq` is assigned inside the write and can.
    """
    corpus = brain.primary
    acts = [a for a in corpus.operational(conversation=conversation,
                                          since=since, limit=None)
            if a["act"] in GOVERNANCE_ACTS
            and (until is None or a["at"] <= until)]
    if between is not None:
        lo, hi = between
        order = corpus.operational_order([lo, hi, *(a["id"] for a in acts)])
        acts = [a for a in acts
                if order.get(lo, 0) < order.get(a["id"], 0) < order.get(hi, 0)]
    acts.sort(key=lambda a: a["at"])
    rows = [{"act": a["id"], "at": a["at"], "what": a["act"],
             "actor": a["actor"], "conversation": a["conversation"],
             "turn": a["turn"], "about": a["about"],
             # THE REASON IN THE WORDS IT WAS GIVEN IN, or absent.
             "because": a["because"], "detail": a["detail"]}
            for a in acts]
    return {"question": "what changed",
            "acts": rows[-limit:] if limit else rows,
            "total": len(rows),
            "omitted": max(0, len(rows) - limit) if limit else 0,
            "window": {"since": since, "until": until},
            "vocabulary": list(GOVERNANCE_ACTS),
            "empty": "nothing here changed what governs" if not rows else None}


def what_executions_received(brain, *, conversation=None, participant=None,
                             executions=()) -> dict:
    """Question two: what did executions here actually receive.

    ONE ROW PER EXECUTION, AND THREE DISTINCT ANSWERS. Absent, empty, or a
    list. An execution the record cannot speak for is listed as absent rather
    than omitted, because omitting it would make the answer look complete.

    AND WHICH PERSONA EACH ONE RECEIVED, on its own three answers and from the
    same helper the execution sheet uses -- because "which Persona was this
    execution acting as?" is the first thing anybody asks of a row here, and it
    was the one thing the row could not say. `behavioural_sources` has carried
    it on every record ever written. A record naming none says none was
    RECORDED; no record at all says nothing at all.
    """
    corpus = brain.primary
    rows = corpus.deliveries(participant=participant)
    if conversation is not None:
        rows = [d for d in rows if d.get("conversation") == conversation]
    by_execution: dict[str, list] = {}
    for d in rows:
        by_execution.setdefault(d["execution"], []).append(d)
    for ref in executions:
        by_execution.setdefault(ref, [])
    out = []
    for ref, recs in sorted(by_execution.items(),
                            key=lambda kv: (kv[1][-1]["at"] if kv[1] else 0)):
        if not recs:
            out.append({"execution": ref, "answer": "absent",
                        "persona": _persona_answer(recs),
                        "why": "no delivery record names this execution"})
            continue
        n = sum(len(d.get("behavioural_sources") or ()) for d in recs)
        out.append({
            "execution": ref,
            "answer": "empty" if n == 0 else "received",
            "sources": n,
            "participant": recs[-1].get("participant"),
            "runtime": recs[-1].get("runtime"),
            "conversation": recs[-1].get("conversation"),
            "at": recs[-1].get("at"),
            "persona": _persona_answer(recs),
            "why": ("the record lists no behavioural material" if n == 0
                    else None)})
    return {"question": "what executions received", "executions": out,
            "total": len(out), "filtered_by": {
                "conversation": conversation, "participant": participant},
            "empty": ("no delivery record answers for this scope"
                      if not out else None)}


def what_was_used(brain, *, conversation=None) -> dict:
    """Question three: which Personas and named material were actually used.

    FROM DELIVERY RECORDS ONLY. Not from what stands, not from what is placed,
    not from what anybody intended. And the counts are counts of records: they
    are not a ranking, not a quality signal and not evidence anybody read
    anything.

    WHAT IS ABSENT IS SAID. A record whose sources name no Persona is counted
    under nothing at all; it is reported separately as records that name none.

    AND EACH ROW SAYS WHO RECEIVED IT AND WHICH RECORD NAMED IT LAST, because a
    count that cannot be opened is a number nobody can check: "this Persona was
    named in four records" left no way to ask who by and no way to reach the
    latest of them. `deliveries_naming` already answers exactly that, per item
    and over every matching record, so it is ASKED rather than recomputed here
    -- two counters over the same rows would be two things able to disagree.

    THE TWO COUNTS ARE DIFFERENT QUESTIONS AND ARE KEPT APART. `records` counts
    the records that named the item IN THIS WAY -- as the Persona, or named for
    the invocation. `records_any_way` counts the records that named it at all,
    which is the denominator `participants` and `latest` are drawn from.
    """
    corpus = brain.primary
    rows = corpus.deliveries()
    if conversation is not None:
        rows = [d for d in rows if d.get("conversation") == conversation]
    personas: dict[str, int] = {}
    named: dict[str, int] = {}
    without_persona = 0
    for d in rows:
        sources = d.get("behavioural_sources") or ()
        found = False
        for s in sources:
            if s.get("scope") == PERSONA_SCOPE and s.get("source_id"):
                personas[s["source_id"]] = personas.get(s["source_id"], 0) + 1
                found = True
            elif s.get("scope") == NAMED_SCOPE and s.get("source_id"):
                named[s["source_id"]] = named.get(s["source_id"], 0) + 1
        if not found:
            without_persona += 1
    # Only `per_entry` is read from this, and that is computed over every
    # matching record: `limit` bounds the rows handed back, which are not used.
    asked = list(personas) + [k for k in named if k not in personas]
    reach = {}
    if asked:
        reach = {r["entry"]: r for r in deliveries_naming(
            brain, asked, conversation=conversation, limit=1)["per_entry"]}

    def row(entry, records) -> dict:
        """One item, its count by this way of reaching, and who received it."""
        mine = reach.get(entry) or {}
        return {
            "entry": entry,
            "records": records,
            "records_any_way": mine.get("records"),
            "executions": mine.get("executions"),
            "participants": mine.get("participants") or [],
            "records_naming_no_participant": mine.get(
                "records_naming_no_participant"),
            # THE LATEST RECORD THAT NAMED IT, so the count can be opened.
            # None only where no record names it at all, which cannot happen
            # for a row that is here -- it is carried rather than assumed.
            "latest": ({"delivery": mine["latest"],
                        "execution": mine["latest_execution"],
                        "at": mine["latest_at"],
                        "participant": mine["latest_participant"]}
                       if mine.get("latest") else None),
        }

    return {
        "question": "what was used",
        "personas": [row(k, v)
                     for k, v in sorted(personas.items(),
                                        key=lambda kv: (-kv[1], kv[0]))],
        "named_material": [row(k, v)
                           for k, v in sorted(named.items(),
                                              key=lambda kv: (-kv[1], kv[0]))],
        "records": len(rows),
        "records_naming_no_persona": without_persona,
        "counts_are": "counts of delivery records, not scores",
        "participants_are": "the participants the records that named it name. "
                            "Who received it, never who it applies to and "
                            "never who followed it.",
        "uncounted": "anything no delivery record names is not here at all. "
                     "It is uncounted, which is not a count of zero.",
        "empty": ("no delivery record answers for this scope" if not rows
                  else None)}


def what_ended(brain, *, conversation=None) -> dict:
    """Question four: what has ended here, and what replaced it.

    NOTHING IS DELETED, AND PAST RECORDS KEEP NAMING IT. An ended item is still
    in the record, still readable, and every delivery record that named it says
    exactly what it said before. Ending is replacing; it is not removal.
    """
    corpus = brain.primary
    ended = []
    for e in _material(corpus):
        standing = corpus.stands(e["id"])
        state = standing_state(standing)
        if state not in ("ended", "replaced"):
            continue
        if conversation is not None:
            # Placed here, or on the whole Brain -- which is here too.
            at = {x["link"]["to"] for x in corpus.links(relation=SCOPED_TO,
                                                        frm=e["id"])}
            if conversation not in at and not at & whole_brain_ids(corpus):
                continue
        links = [_link_view(corpus, x) for x in corpus.links(to=e["id"])
                 if x["link"]["from"] in standing["superseded_by"]]
        ended.append({
            "entry": e["id"],
            "kind": (e.get("definition") or {}).get("name"),
            "state": state,
            "never_held": state == "replaced",
            "replaced_by": standing["superseded_by"],
            "acts": links,
            "chain": corpus.history(e["id"]),
        })
    ended.sort(key=lambda r: max([a["at"] for a in r["acts"]] or [0]))
    return {"question": "what ended",
            "ended": ended, "total": len(ended),
            "nothing_is_deleted": "an ended item is still in the record and "
                                  "every delivery record that named it still "
                                  "names it",
            "empty": "nothing here has ended" if not ended else None}


# -- arrivals, and what changed between two of them --------------------------


def arrive(cv, participant, *, conversation=None) -> str:
    """Record that somebody opened Governance. Append-only, per-participant.

    THE LAST-LOOKED TIME IS THE ARRIVAL, and it is the only one. There is no
    read-marker anywhere in this module, no per-item seen state, and nothing
    that can be set to a time somebody did not actually arrive at.
    """
    if not participant:
        raise ValueError("an arrival is somebody arriving; name the participant")
    return cv.record_act(actor=participant, act=ARRIVED,
                         conversation=conversation,
                         because="opened governance")


def arrivals(corpus, participant, *, conversation=None) -> list[dict]:
    """This participant's arrivals at this scope, oldest first."""
    return [a for a in corpus.operational(actor=participant)
            if a["act"] == ARRIVED and a["conversation"] == conversation]


def since_last_look(brain, participant, *, conversation=None) -> dict:
    """What changed between this participant's last two arrivals.

    A CATCH-UP IS A PAIR OF ARRIVALS AND THE ACTS BETWEEN THEM. So:

      no arrivals    ABSENT. This person has never opened Governance here, and
                     that is not "nothing changed" -- there is no last look for
                     anything to be since.
      one arrival    BOUNDS NOTHING, and says so. One end of a window is not a
                     window, and pretending the other end is the beginning of
                     time would report the whole record as new.
      two or more    the window is the newest pair, and the answer is the
                     governance acts inside it.
    """
    corpus = brain.primary
    seen = arrivals(corpus, participant, conversation=conversation)
    if not seen:
        return {"participant": participant, "conversation": conversation,
                "arrivals": 0, "bounded": False, "window": None,
                "changed": None,
                "why": "this participant has never opened governance here, so "
                       "there is no last look to be since. Absent, not zero."}
    if len(seen) == 1:
        return {"participant": participant, "conversation": conversation,
                "arrivals": 1, "bounded": False, "window": None,
                "changed": None, "first_arrival": seen[0]["at"],
                "why": "one arrival bounds nothing: a catch-up is a pair of "
                       "arrivals and the acts between them."}
    previous, latest = seen[-2], seen[-1]
    return {"participant": participant, "conversation": conversation,
            "arrivals": len(seen), "bounded": True,
            "window": {"from": previous["at"], "to": latest["at"],
                       "from_arrival": previous["id"],
                       "to_arrival": latest["id"]},
            "changed": what_changed(brain, conversation=conversation,
                                    since=previous["at"],
                                    between=(previous["id"], latest["id"])),
            "no_read_marker": "there is no mark-as-read anywhere. The only "
                              "last-looked fact is an arrival, and asking "
                              "this question records nothing."}
