"""Edit and Delete, append-only: a version is a successor, a deletion is one too.

NOTHING HERE IS A NEW MECHANISM. The spine already has exactly one way for
material to change: a later entry `supersedes` an earlier one, the earlier one
is kept byte-for-byte, `stands()` stops counting it, `stands(as_at=...)` still
answers for the time before, and `history()` walks the chain. That IS the
version model, so Edit and Delete are written with it and with nothing else:

  EDIT     writes the new version as an ordinary entry of the same Kind and a
           `supersedes` link from it to the version it replaces. The old value
           stays reconstructable because it was never touched.

  DELETE   writes a `deletion` record -- an entry of its own Kind carrying the
           reason -- and a `supersedes` link from it to the current version.
           The lineage now ENDS in a deletion, which is what "deleted" means
           here and all it means. Nothing is erased; there is no SQL that
           could erase it, because the store refuses UPDATE and DELETE.

WHICH VERSION IS CURRENT is the end of the chain, read forward from the entry
asked about. A Turn and a Topic keep their identity at the ROOT -- the entry
every reply, filing, reference and Turn number already points at -- so a reader
of a Turn is handed the root's id with the current version's body. Nothing that
pointed at the root is rewritten or re-pointed.

THE LADDER IS NOT MADE MORE CEREMONIOUS, AND NOT BYPASSED. Where the Kind's
current definition says standing is meaningful (or does not say either way),
an edit of material that STANDS is written as a candidate and PROPOSED to
supersede it (`proposes-to-supersede`, the existing relation): the old version
keeps standing, nothing reaches anybody new, and the owner approves it with the
existing establish-replacement act. Prior approval is never copied onto the new
words. An edit of a candidate that was never established replaces it directly,
because no approval exists to carry. Where the Kind says standing is NOT
meaningful -- a Turn, a note, a finding -- the new version simply becomes
current; it is established exactly when the version it replaces stood, which
for those Kinds records deliberate creation and approves nothing, so editing
never makes ungated material gated.

WITH ONE THING `standing_apt` DOES NOT DECIDE. Material whose Kind declares
`knowing: "how"` -- it directs how work is done -- is gated whatever
`standing_apt` says, because the ungated path establishes the new version AND
the placements are inherited from the version it replaces, so a Kind declaring
`knowing: "how"` and `standing_apt: False` had an edit put a NEW PROCEDURE in
front of the next execution with nobody having conferred anything. See `_gated`.

INERT GOING FORWARD. `inert_refusal` is asked by every act that would give
material new standing, new effect, or use it as new support: establishing it,
replacing with it, proposing with it, disputing from it, replying to it,
addressing it, filing it, referencing it from a new Turn, deriving from it,
supporting with it or supporting it, placing it or placing at it, citing it
as a result, naming it as governing new work or as a constraint's basis,
asking about it in a new request. A deleted lineage answers each of those with
a refusal that says why. History -- `stands(as_at)`, `history()`, deliveries,
acts, the retained bodies -- is left exactly as it was.

WHAT IS REFUSED IS NEW USE, CHOSEN BY A CALLER. Relationships that already
existed remain, and continue through ordinary version and replacement
continuity: a new version carries its predecessor's placements, whatever they
point at, because nobody chose them anew. Work that already existed may still
be assigned, resumed and answered, and its answer still replies to the Turn
that asked for it. Deleting material does not withdraw work; whether deleting
a request should is undecided, and nothing here decides it.
"""

from __future__ import annotations

# NOTHING FROM `mentis.*` IS IMPORTED HERE, for the reason the Conversation
# layer's own module imports nothing inward: it works through the public
# Corpus seam or it has found that the seam is not sufficient. Asserted by
# `tests/test_edit_delete.py`.
#: The Kind whose entries record deletions. Defined in `_KINDS`.
DELETION = "deletion"

#: Kinds the generic Edit does not write a new version of. A CONVERSATION'S
#: NAME AND A PARTICIPANT'S ALIAS ARE READ AS THEIR CURRENT VERSION everywhere
#: (both keep their identity at the root, below), and each changes by its own
#: operation -- `Conversations.rename_conversation`, `rename_participant` --
#: never by this Edit: the generic door stays closed to them exactly as it was.
NOT_EDITABLE_HERE = ("conversation", "participant")
CONVERSATION = "conversation"
PARTICIPANT = "participant"
#: Kinds that cannot be deleted by this act. A Topic's membership links would
#: need an un-filing semantics nobody has decided; a Conversation or a
#: Participant is not material; a deletion record deleting would be a loop.
NOT_DELETABLE_HERE = ("conversation", "participant", "topic", DELETION,
                      "anchor", "response-set", "answer", "marked-ready",
                      "own-words", "interpretation", "interpretation-reply",
                      "timer-mark")
#: ANCHORED INTERACTION (`mentis.conversation.anchors`). An anchor is a place
#: in one immutable version and is never edited or deleted; a reaction is an
#: attributed occurrence, never edited -- it changes by a NEW reaction that
#: supersedes it, and is withdrawn by the ordinary Delete. Spelled here as
#: rows, for the reason given at the top of this file.
ANCHOR = "anchor"
REACTION = "reaction"
NOT_EDITABLE_OCCURRENCES = {
    ANCHOR: "an anchor names a place in one immutable version and is never "
            "edited; anchor the new place instead",
    REACTION: "a reaction is a historical occurrence and is never edited; "
              "change it with a new reaction that names it in `changes`, or "
              "withdraw it",
    # DURABLE FILLABLE BLOCKS (`mentis.conversation.responses`): what somebody
    # filled in is what they filled in. A change is a new answer.
    "response-set": "a response set names one block of one Turn and is never "
                    "edited",
    "answer": "an answer is what somebody gave and is never edited; answer "
              "again, naming the answer it replaces",
    "marked-ready": "marking ready is a historical occurrence and is never "
                    "edited; mark ready again",
    "own-words": "own words are kept exactly as written and are never edited "
                 "here; write a new version naming the one it replaces",
    "interpretation": "an interpretation is what somebody read into these "
                      "words and is never edited; propose again",
    "interpretation-reply": "confirming, changing or declining an "
                            "interpretation is a historical occurrence and is "
                            "never edited",
    "timer-mark": "a timer mark is when somebody started or stopped and is "
                  "never edited; correct a stop with a new stop that names "
                  "the one it replaces",
}
#: THE GENERIC DOORS THAT WOULD WRITE ONE OF THESE KINDS, CLOSED. Creating
#: one through `/api/entries`, or writing a new one with the generic
#: `revise`, `edit` or the words form of `propose-supersession`, or through
#: `ladder_writes.record`, would make an answer, a set or a marking nobody gave
#: through the rules that give it meaning (`mentis.conversation.responses`
#: checks the block, the field, the deleted source and who may write). The
#: standing acts on an EXISTING entry (establish, dispute, place ...) answer
#: on these as on any entry (decision A, tests/test_anchored_interaction_
#: generic_acts.py) and change nothing these Kinds mean.
GENERIC_WRITE_CLOSED = ("response-set", "answer", "marked-ready", "own-words",
                        "interpretation", "interpretation-reply",
                        "timer-mark")


def generic_write_refusal(kind) -> dict | None:
    """Why a generic door may not write a new entry of `kind`, or None."""
    if kind in GENERIC_WRITE_CLOSED:
        return {"error": f"a {kind} is written only by its own operation "
                         "(filling in the block it belongs to), never by a "
                         "generic door", "kind": kind}
    return None

CONTRIBUTION = "contribution"
TOPIC = "topic"
#: Content parts that carry a structured reference inline, beside the
#: characters the author typed for it. `acquired` names one observation of
#: acquired source material (`adm-`), pinned (Sources slice 1, U9). `object`
#: names one object inside a post, by its post and key, pinned to the version
#: the author saw (`mentis.conversation.objectref`).
_REFERENCE_PARTS = ("topic", "turn", "conversation", "acquired", "object")


def _kind(entry) -> str | None:
    return (entry.get("definition") or {}).get("name")


def is_node(entry) -> bool:
    return entry.get("family") == "entry" and not entry.get("link")


def is_deletion(entry) -> bool:
    return is_node(entry) and _kind(entry) == DELETION


def supersedes_relation(corpus) -> str:
    """The relation carrying the superseding role, read from the data."""
    return corpus.superseding_relation()


# -- reading ---------------------------------------------------------------

def lineage(corpus, eid) -> dict:
    """This entry, every later version of it, and whether the line was deleted.

    Read FORWARD from `eid`: what came after it. Fast when nothing superseded
    it, which is almost every entry -- one indexed lookup and no walk.
    """
    got = corpus.read([eid])
    if not got:
        return {"root": eid, "versions": [], "current": None, "deletion": None}
    if not corpus.links(relation=supersedes_relation(corpus), to=eid):
        return {"root": eid, "versions": got, "current": got[0],
                "deletion": None}
    chain = corpus.history(eid)
    forward = chain[chain.index(eid):]
    by = {r["id"]: r for r in corpus.read(forward)}
    ordered = [by[x] for x in forward if x in by]
    deletion = ordered[-1] if len(ordered) > 1 and is_deletion(ordered[-1]) \
        else None
    versions = ordered[:-1] if deletion else ordered
    return {"root": eid, "versions": versions, "current": versions[-1],
            "deletion": deletion}


#: Kinds whose identity stays at the ROOT of their line: everything that points
#: at a Turn, a Topic, a Conversation or a Participant points at its first
#: entry, so its later versions are read AS it -- a renamed Conversation is the
#: Conversation every post, link, placement and act already names, under its
#: new name, and a renamed Participant is the somebody every post, act and
#: delegation already names, under its new alias. Every
#: other Kind keeps the substrate's ordinary reading, where a successor is an
#: item of its own and the one it replaced is still itself.
ROOT_IDENTITY = (CONTRIBUTION, TOPIC, CONVERSATION, PARTICIPANT)


def keeps_root_identity(entry) -> bool:
    return is_node(entry) and _kind(entry) in ROOT_IDENTITY


def deletion_of(corpus, eid) -> dict | None:
    """The deletion record that deleted this, or None.

    For a Turn or a Topic, whatever version the line is on: deleting it
    deleted the item. For any other Kind, only a deletion of THIS entry --
    a rule that was replaced and whose successor was later deleted was not
    itself deleted; it was replaced, and still reads so.
    """
    got = corpus.read([eid])
    if not got or not is_node(got[0]):
        return None
    if keeps_root_identity(got[0]):
        return lineage(corpus, eid)["deletion"]
    for sb in corpus.stands(eid)["superseded_by"]:
        rec = corpus.read([sb])
        if rec and is_deletion(rec[0]):
            return rec[0]
    return None


def line_deletion(corpus, eid) -> dict | None:
    """The deletion that ends ANY line leading on from this entry, or None.

    THE WHOLE LINE, FOR EVERY KIND. Walks forward over every successor that
    still counts -- every `supersedes` that has not itself been superseded,
    not only the latest one `history()` follows -- so a branch written onto
    an earlier version can never hide a deletion further along. A rule that
    was replaced by a version that was then deleted is in a deleted line:
    its item was deleted, and nothing may write onto it again (F1 in the
    uiux review). How it READS is unchanged -- replaced, then deleted -- and
    `presented` still says "deleted" only of the entry the deletion names.
    """
    seen, todo, found = {eid}, [eid], []
    while todo:
        cur = todo.pop()
        for nxt in corpus.stands(cur)["superseded_by"]:
            if nxt in seen:
                continue
            seen.add(nxt)
            rec = corpus.read([nxt])
            if not rec:
                continue
            if is_deletion(rec[0]):
                found.append(rec[0])
            else:
                todo.append(nxt)
    return min(found, key=lambda d: d["recorded_at"]) if found else None


def _blank(body: dict) -> dict:
    """The shape of a body with nothing in it, for a deleted item's CURRENT
    reading. The retained contents are still the entry's own and are read
    from it wherever history is asked for."""
    return {k: ([] if isinstance(v, list) else {} if isinstance(v, dict)
                else "") for k, v in (body or {}).items()}


def presented(corpus, entry: dict) -> dict:
    """The entry as a NORMAL reader should see it now.

    The root's id, its author and its time -- identity is not moved -- with
    the CURRENT version's body, and two facts beside it: `revision` when it
    was edited, `deleted` when its line ends in a deletion. A deleted entry's
    body is blanked here, never its record.
    """
    if not is_node(entry):
        return entry
    # THE COMMON CASE, IN ONE INDEXED LOOKUP: nothing ever superseded it, so
    # there is no later version and no deletion to find.
    if not corpus.links(relation=supersedes_relation(corpus), to=entry["id"]):
        return entry
    if not keeps_root_identity(entry):
        d = deletion_of(corpus, entry["id"])
        if d is None:
            return entry
        lin = {"versions": [entry], "current": entry, "deletion": d}
    else:
        lin = lineage(corpus, entry["id"])
    if len(lin["versions"]) <= 1 and not lin["deletion"]:
        return entry
    out = dict(entry)
    head = lin["current"]
    if len(lin["versions"]) > 1:
        out["body"] = head["body"]
        out["revision"] = {
            "versions": len(lin["versions"]), "current": head["id"],
            "edited_at": head["recorded_at"],
            "edited_by": head["attributed_to"]}
    if lin["deletion"]:
        d = lin["deletion"]
        out["body"] = _blank(entry["body"])
        out["deleted"] = {
            "record": d["id"], "at": d["recorded_at"],
            "by": d["attributed_to"],
            "because": (d["body"] or {}).get("reason") or None}
    return out


def history_view(corpus, eid, *, alias=lambda x: x) -> dict:
    """Every version, oldest first, and the deletion if there is one -- the
    retained contents History and Details are entitled to disclose.

    THE WHOLE LINE, not only what came after: an item read at its second
    version still shows the first. `deleted` here is the deletion that ends
    the LINE; whether this entry itself reads as deleted is `presented`'s."""
    chain = corpus.history(eid) if corpus.read([eid]) else [eid]
    lin = lineage(corpus, chain[0])
    # DETAILS NEVER LOSES A DELETION. The chain above follows one successor
    # per step; the deletion is looked for along every one of them.
    if lin["deletion"] is None and lin["versions"]:
        lin["deletion"] = line_deletion(corpus, chain[0])
    sup = supersedes_relation(corpus)

    def why(newer, older):
        for l in corpus.links(relation=sup, frm=newer, to=older):
            return (l["body"] or {}).get("reason")
        return None

    rows = []
    for i, v in enumerate(lin["versions"]):
        rows.append({"entry": v["id"], "version": i + 1, "body": v["body"],
                     "at": v["recorded_at"], "by": v["attributed_to"],
                     "by_alias": alias(v["attributed_to"]),
                     "written_by": v.get("written_by"),
                     "because": why(v["id"], lin["versions"][i - 1]["id"])
                     if i else None,
                     "current": i == len(lin["versions"]) - 1
                     and not lin["deletion"]})
    d = lin["deletion"]
    return {"entry": eid, "versions": rows,
            "current": lin["current"]["id"] if lin["current"] else None,
            "deleted": ({"record": d["id"], "at": d["recorded_at"],
                         "by": d["attributed_to"],
                         "by_alias": alias(d["attributed_to"]),
                         "because": (d["body"] or {}).get("reason") or None}
                        if d else None)}


def _is_occurrence(corpus, eid) -> bool:
    from .anchors import is_occurrence
    return is_occurrence(corpus, eid)


def _anchor_deletion(corpus, anchor) -> tuple[dict | None, str | None]:
    """(the deletion withholding what this anchor names, what it anchors):
    `anchors.source_deletion`, the one reading, for `inert_refusal`."""
    from .anchors import anchor_turn, selector_of, source_deletion
    root = anchor_turn(corpus, anchor["id"])
    sel = selector_of(anchor)
    return source_deletion(corpus, sel, root), root or sel.get("version")


def offers(corpus, entry) -> dict:
    """What an interface may offer on this entry, and why not where it may not.

    Computed by the same rules `edit` and `delete` apply, so no surface has to
    know a Kind name to avoid drawing a control that would only be refused.
    `edit_mode` says what saving would really do: `proposed` (a new version
    put to the owner while this one stands), `candidate` (a new candidate in
    place of this one) or `edited` (the new version is current at once).
    """
    eid = entry["id"]
    kind = _kind(entry)
    no = {"edit": False, "delete": False, "edit_mode": None}
    if not is_node(entry):
        return {**no, "why_not": "not an entry of a Kind"}
    if kind == REACTION and _is_occurrence(corpus, eid):
        # The same reading `delete` applies: the reactor's own line only --
        # for a reaction OCCURRENCE. Other material of the reaction Kind (a
        # generic revision) is read as before, generically.
        from .anchors import own_line
        own = own_line(corpus, eid)
        if deletion_of(corpus, eid) or own["withdrawal"]:
            return {**no, "why_not": "that was already deleted"}
        if own["changed_to"]:
            return {**no, "why_not": "a later version replaced this one",
                    "current": own["head"]}
        return {**no, "delete": True,
                "why_not": NOT_EDITABLE_OCCURRENCES[REACTION]}
    refusal = inert_refusal(corpus, eid)
    if refusal:
        return {**no, "why_not": refusal["error"]}
    head = lineage(corpus, eid)["current"]
    if head["id"] != eid and not keeps_root_identity(entry):
        return {**no, "why_not": "a later version replaced this one",
                "current": head["id"]}
    gated = _gated(corpus, kind)
    stands = corpus.stands(head["id"])["stands"]
    mode = ("proposed" if gated and stands else
            "candidate" if gated else "edited")
    editable = (kind not in NOT_EDITABLE_HERE
                and kind not in NOT_EDITABLE_OCCURRENCES)
    return {"edit": editable,
            "delete": kind not in NOT_DELETABLE_HERE,
            "edit_mode": mode if editable else None,
            "why_not": NOT_EDITABLE_OCCURRENCES.get(kind)}


# -- a Conversation's line is its own operation's ---------------------------

def conversation_line_refusal(corpus, *ids) -> dict | None:
    """Why a generic act may not write a version onto, or with, one of these,
    or None.

    A CONVERSATION'S NEXT VERSION IS ITS NEW NAME, AND ONLY RENAMING WRITES IT
    (`Conversations.rename_conversation`). The generic supersede, revise,
    proposal and establish-replacement acts would otherwise write one without
    the rename's rules or its act -- and with another Conversation as the
    replacement, make that Conversation a version of this one, hidden from
    every list while its posts still name it. So every one of those acts asks
    this of what it would end and of what would replace it, before anything is
    written. Edit was already closed to a Conversation; this closes the rest.
    """
    for eid in ids:
        if not eid or not isinstance(eid, str):
            continue
        got = corpus.read([eid])
        kind = _kind(got[0]) if got and is_node(got[0]) else None
        if kind in (CONVERSATION, PARTICIPANT):
            return {"error": f"a {kind}'s next version is its new name, "
                             "written only by renaming it; a generic "
                             "supersede, revise or proposal does not write "
                             "one", "entry": eid, "kind": kind}
    return None


# -- the refusal every forward use asks ------------------------------------

def inert_refusal(corpus, *ids) -> dict | None:
    """Why one of these may not be given new standing, effect or use, or None.

    Three answers: it IS a deletion record (an act on the record, not
    material); it is a link that records a deletion (withdrawing it would
    restore the item in place); or its line was deleted.
    """
    for eid in ids:
        if not eid:
            continue
        got = corpus.read([eid])
        if not got:
            continue
        e = got[0]
        if is_deletion(e):
            return {"error": "that is the record of a deletion, not material; "
                             "it cannot be established, replaced, edited or "
                             "used as support",
                    "entry": eid, "deletion": eid}
        link = e.get("link") or {}
        if link.get("from"):
            src = corpus.read([link["from"]])
            if src and is_deletion(src[0]):
                return {"error": "that link records a deletion. Deleted "
                                 "material is not restored in place: write "
                                 "it again as new material, with its own "
                                 "provenance",
                        "entry": eid, "deletion": link["from"]}
        # AN ANCHOR INTO DELETED MATERIAL IS NOT NEW SUPPORT EITHER. The
        # anchor itself is never deleted, but what it names is a passage of
        # the deleted Turn, so citing it now -- deriving from it, supporting
        # with it, replying through it, reacting to it, diving from it -- is
        # new use of that passage. What was already attached to it stays,
        # and a reaction or a reply on it is its actor's own occurrence and
        # is not inert by this. WHAT IT NAMES is read as `anchors.source`
        # reads it -- the anchor's Turn OR the version its selector names --
        # so an anchor in no Turn (made by the generic `revise` or
        # `/api/entries`) is inert exactly as one in a Turn is.
        if is_node(e) and _kind(e) == ANCHOR:
            d, anchored = _anchor_deletion(corpus, e)
            if d is not None:
                return {"error": "that anchors material that was deleted. "
                                 "What is attached to it stays as "
                                 "history, but it is not used as new "
                                 "support, provenance or interaction",
                        "entry": eid, "deletion": d["id"],
                        "deleted_at": d["recorded_at"],
                        "anchored": anchored}
        # ANY VERSION IN A DELETED LINE, not only the one the deletion names:
        # an earlier version is a way back into the same item.
        d = deletion_of(corpus, eid) if is_node(e) else None
        if d is None and is_node(e):
            d = line_deletion(corpus, eid)
            if d is not None:
                return {"error": "that is an earlier version of an item that "
                                 "was later deleted. The item has no current "
                                 "standing or effect, and nothing is written "
                                 "onto any version of it; if its content is "
                                 "wanted again, write it again as new "
                                 "material",
                        "entry": eid, "deletion": d["id"],
                        "deleted_at": d["recorded_at"]}
        if d is not None:
            return {"error": "that was deleted. It has no current standing or "
                             "effect and is not used as new support or "
                             "provenance; if its content is wanted again, "
                             "write it again as new material",
                    "entry": eid, "deletion": d["id"],
                    "deleted_at": d["recorded_at"]}
    return None


# -- Turn bodies -----------------------------------------------------------

def flow_text(parts) -> str:
    """What the author typed, as one string: text parts and the characters of
    inline references, in order. The thing an edit box starts from."""
    return "".join(p.get("text") or "" for p in parts or ()
                   if p.get("type") == "text"
                   or p.get("type") in _REFERENCE_PARTS)


def reparted(parts, text: str) -> list:
    """The new words as content parts, keeping everything else the Turn held.

    INLINE REFERENCES SURVIVE WHERE THEIR CHARACTERS DO. Each reference part is
    looked for, in order, in the new text; where its characters are still
    there it stays a reference at that place, and where they were removed the
    reference is gone with them -- the author deleted it. Nothing is re-resolved
    from prose. MEDIA AND ARTIFACT PARTS ARE KEPT exactly as they were, after
    the words: editing the words does not re-submit, drop or re-point anything
    the Turn attached.
    """
    refs = [p for p in parts or () if p.get("type") in _REFERENCE_PARTS
            and p.get("text")]
    kept = [p for p in parts or () if p.get("type") != "text"
            and p.get("type") not in _REFERENCE_PARTS]
    out, rest = [], text
    for r in refs:
        at = rest.find(r["text"])
        if at < 0:
            continue
        if at:
            out.append({"type": "text", "text": rest[:at]})
        out.append(dict(r))
        rest = rest[at + len(r["text"]):]
    if rest or not out:
        out.append({"type": "text", "text": rest})
    return out + kept


# -- writing ---------------------------------------------------------------

class Refused(Exception):
    def __init__(self, refusal: dict):
        super().__init__(refusal.get("error", "refused"))
        self.refusal = refusal


#: The value of `knowing` that means "this Kind's material directs how work is
#: done". Spelled here for the reason stated at the top of this module: nothing
#: from `mentis.*` is imported into this file, so the one word is a row here
#: exactly as `DELETION`, `CONTRIBUTION` and `TOPIC` above are.
KNOWING_HOW = "how"


def _standing_apt(corpus, kind):
    cur = corpus.current_definition(kind) if kind else None
    return (cur or {}).get("body", {}).get("standing_apt")


def _knowing(corpus, kind):
    """Which ladder this Kind's CURRENT definition puts its material on, or None
    where it declares neither. Read from the same one source `_standing_apt` is,
    and for the same reason: whether a Kind's material DIRECTS WORK is a fact
    about the vocabulary now, not about what an entry meant when it was written.
    """
    cur = corpus.current_definition(kind) if kind else None
    return (cur or {}).get("body", {}).get("knowing")


def _gated(corpus, kind):
    """Does a new version of this Kind's material have to be PUT FORWARD rather
    than simply become current?

    PROCEDURAL MATERIAL IS ALWAYS GATED, WHATEVER `standing_apt` SAYS, and that
    is the one thing this function adds. `standing_apt` says whether standing is
    meaningful for a Kind; it was also being used, here and nowhere else, to
    decide whether a new version could give ITSELF standing -- so a Kind
    declaring `knowing: "how"` and `standing_apt: False` had its edits
    established on write AND their placement inherited from the version they
    replaced, which means a new procedure governed the next execution the moment
    somebody edited the old one. Nobody conferred that. Reading `knowing` here
    is not a second computation of whether procedural material may govern: it is
    the ONE declared fact that says the material directs work, the same fact
    `placed_procedural` asks delivery's half of the question with.

    `standing_apt` KEEPS ITS OWN MEANING EXACTLY. False still means a new
    version of a Turn, a note or a source-material simply becomes current --
    for every Kind that does not direct work. A Topic is still excluded by name,
    because this layer defines Topic and its own meaning says its name is "a
    label for people".
    """
    if _knowing(corpus, kind) == KNOWING_HOW:
        return True
    return _standing_apt(corpus, kind) is not False and kind != TOPIC


def confers_standing(corpus, eid) -> bool:
    """Does a new, established version of this entry give it STANDING -- or
    does it, like a Turn's, a note's or a Topic's, simply become current?

    `_gated`'s answer, asked of the entry's Kind, for the doors that need to
    know whether an act on it is one only the owner may be named as doing
    (`revise`). An entry with no Kind the record holds is answered True: the
    stricter answer, and the act is refused on its own grounds anyway."""
    got = corpus.read([eid])
    kind = ((got[0].get("definition") or {}).get("name") if got else None)
    return True if not kind else bool(_gated(corpus, kind))


def _placements(corpus, eid) -> list[str]:
    """Where this version is placed NOW -- what its next version carries.
    A placement somebody ended is not carried forward -- the same answer as
    `placements_now`, asked here through the seam alone."""
    return list(dict.fromkeys(
        l["link"]["to"] for l in corpus.links(relation="scoped-to", frm=eid)
        if not corpus.stands(l["id"])["superseded_by"]))


def edit(cv, eid, *, by, fields=None, text=None, because=None,
         written_by=None, basis=None) -> dict:
    """Write the next version of this item. See the module docstring.

    `text` is for a Turn (its words; parts are rebuilt by `reparted`),
    `fields` for anything else (the Kind's own declared fields; ones left out
    keep their current values). `basis`, optional, is what the new version
    rests on; without it, it rests on what the current version rested on.
    """
    corpus = cv.corpus
    got = corpus.read([eid])
    if not got:
        raise Refused({"error": "the record holds no such entry",
                       "entry": eid})
    root = got[0]
    if not is_node(root):
        raise Refused({"error": "only an entry of a Kind can be edited; a "
                                "definition, an admission or a link is not "
                                "one", "entry": eid})
    kind = _kind(root)
    refusal = inert_refusal(corpus, eid)
    if refusal:
        raise Refused(refusal)
    if kind == CONVERSATION:
        raise Refused({"error": "a conversation is renamed by its own "
                                "operation, not by editing it", "entry": eid,
                       "kind": kind})
    if kind in NOT_EDITABLE_HERE:
        raise Refused({"error": f"a {kind}'s name is read from its first "
                                "entry everywhere it is shown, so editing one "
                                "is not offered yet", "entry": eid,
                       "kind": kind})
    if kind in NOT_EDITABLE_OCCURRENCES:
        raise Refused({"error": NOT_EDITABLE_OCCURRENCES[kind], "entry": eid,
                       "kind": kind})
    lin = lineage(corpus, eid)
    head = lin["current"]
    sup = supersedes_relation(corpus)
    if head["id"] != eid and not keeps_root_identity(root):
        # AN ITEM OF ITS OWN WAS WRITTEN AFTER THIS ONE. Editing the old one
        # would fork the line; the one to edit is the current version.
        raise Refused({"error": "a later version replaced this one; edit the "
                                "current version instead",
                       "entry": eid, "current": head["id"]})

    if kind == CONTRIBUTION:
        # A TURN IS WHAT ITS AUTHOR SAID. Somebody else's words written under
        # the author's name, even as a new version, would be a forgery; the
        # new version is attributed to whoever wrote it, so only the author
        # may write one.
        if by != root["attributed_to"]:
            raise Refused({"error": "only the author of a Turn can edit it: "
                                    "a Turn is what they said", "entry": eid,
                           "author": root["attributed_to"]})
        if not isinstance(text, str) or not text.strip():
            raise Refused({"error": "an edited Turn says something; to take "
                                    "it back, delete it", "entry": eid})
        parts = reparted(head["body"].get("parts"), text)
        if parts == head["body"].get("parts"):
            raise Refused({"error": "nothing changed", "entry": eid})
        body = {"parts": parts,
                "addressed_to": list(head["body"].get("addressed_to") or [])}
    else:
        if not isinstance(fields, dict) or not fields:
            raise Refused({"error": "an edit gives the new values, in the "
                                    "fields its Kind declares",
                           "entry": eid, "kind": kind})
        body = {**(head["body"] or {}), **fields}
        if body == head["body"]:
            raise Refused({"error": "nothing changed", "entry": eid})

    standing = corpus.stands(head["id"])
    # THE KIND'S OWN ANSWER DECIDES, never its name -- with Turn and Topic,
    # the two Kinds this layer defines and whose meaning says it: a Turn is a
    # speech event (standing_apt False) and a Topic is "not ... an epistemic
    # Kind", its name "a label for people". And procedural material is gated
    # whatever it says: see `_gated`.
    gated = _gated(corpus, kind)
    reason = because or "edited"
    # THE NEW VERSION RESTS ON WHAT THIS ONE RESTED ON. Rewording a lesson does
    # not change its evidence, and an edited outcome is still an outcome of
    # the same thing in the same place; a Kind that requires a basis gets no
    # new version without one (`ladder_writes.version_grounds`).
    from . import ladder_writes
    grounds = ([], [])
    if kind != CONTRIBUTION:
        try:
            grounds = ladder_writes.version_grounds(corpus, kind, body, head["id"],
                                                    basis)
        except ValueError as exc:
            raise Refused({"error": str(exc), "entry": eid, "kind": kind})
    with corpus.atomic():
        try:
            new = corpus.write(kind=kind, body=body, attributed_to=by,
                               written_by=written_by)
        except ValueError as exc:
            raise Refused({"error": str(exc), "entry": eid, "kind": kind})
        ladder_writes.write_grounds(corpus, new, *grounds, by=by,
                                    writer=written_by)
        if gated and standing["stands"]:
            # PROPOSED, NOT DONE. The standing version goes on standing; the
            # owner's establish-replacement is what ends it.
            proposal = corpus.propose_supersession(
                new, [head["id"]], attributed_to=by, reason=reason,
                written_by=written_by)
            oid = cv.record_act(
                actor=by, act="supersession-proposed",
                about=[head["id"], new], because=because or None,
                detail={"replacement": new, "predecessors": [head["id"]],
                        "links": proposal["links"],
                        "relation": proposal["relation"], "edit": True})
            return {"entry": eid, "edited": head["id"], "version": new,
                    "kind": kind, "act": oid, "mode": "proposed",
                    "gated": True,
                    "says": "Proposed as the new version. The current one "
                            "still stands until it is approved; approving "
                            "is the owner's establish-replacement."}
        established = None
        if not gated and standing["stands"]:
            established = corpus.establish(
                new, attributed_to=by, written_by=written_by,
                reason="the current version of material this Kind does not "
                       "adjudicate; it records deliberate creation and "
                       "approves nothing")
        if kind != CONTRIBUTION and kind != TOPIC:
            for where in _placements(corpus, head["id"]):
                corpus.write(body={"reason": "inherited from the version "
                                             "this edits"},
                             attributed_to=by, written_by=written_by,
                             link={"from": new, "to": where,
                                   "relation": "scoped-to"})
        link = corpus.write(body={"reason": reason}, attributed_to=by,
                            written_by=written_by,
                            link={"from": new, "to": head["id"],
                                  "relation": sup})
        # A Persona's intake designation moves with it (see
        # `Conversations.carry_intake_forward`). The proposed path above
        # carries nothing: there the old version still stands.
        cv.carry_intake_forward(head["id"], new, by=by,
                                written_by=written_by)
        turn = eid if kind == CONTRIBUTION else None
        oid = cv.record_act(
            actor=by, act="turn-edited" if turn else "material-edited",
            conversation=cv.conversation_of(eid) if turn else None,
            turn=turn, about=[eid, head["id"], new],
            because=because or None,
            detail={"version": new, "replaces": head["id"], "link": link,
                    "established": established, "gated": gated})
    return {"entry": eid, "edited": head["id"], "version": new, "kind": kind,
            "act": oid, "mode": "replaced-candidate" if gated else "edited",
            "gated": gated,
            "says": ("The new version is current. It is a candidate: nothing "
                     "had approved the old one, and nothing approves this "
                     "one until somebody establishes it.") if gated else
                    "The new version is current; the old one is kept."}


def delete(cv, eid, *, by, because=None, written_by=None) -> dict:
    """End this item's line with a deletion record. Erases nothing."""
    corpus = cv.corpus
    got = corpus.read([eid])
    if not got:
        raise Refused({"error": "the record holds no such entry",
                       "entry": eid})
    root = got[0]
    kind = _kind(root)
    if not is_node(root):
        raise Refused({"error": "only an entry of a Kind can be deleted; a "
                                "definition, an admission or a link is not "
                                "one. Held artifact bytes have their own "
                                "door, purge.", "entry": eid})
    if kind in NOT_DELETABLE_HERE:
        raise Refused({"error": f"deleting a {kind} is not offered: "
                                + ("a deletion record is itself the record of "
                                   "an act" if kind == DELETION else
                                   "an anchor is a place other things point "
                                   "at, and asserts nothing to take back"
                                   if kind == ANCHOR else
                                   "what should become of everything filed "
                                   "under or taking part in it is undecided"),
                       "entry": eid, "kind": kind})
    # A REACTION'S LINE IS ITS REACTOR'S OWN: the reaction and its
    # reactor's changes through `react(changes=)`. Another actor's generic
    # supersession or revision of it neither closes that line nor makes
    # its withdrawal theirs (Brian, ent-92915b5e7706 on opr-5ceb3e84bb09).
    # Only a reaction OCCURRENCE has such a line; other material of the
    # reaction Kind (a generic revision) is deleted as before, generically.
    own = None
    if kind == REACTION and _is_occurrence(corpus, eid):
        from .anchors import own_line
        own = own_line(corpus, eid)
    already = deletion_of(corpus, eid) or (
        own["withdrawal"] if own else line_deletion(corpus, eid))
    if already is not None:
        raise Refused({"error": "that was already deleted", "entry": eid,
                       "deletion": already["id"]})
    head = lineage(corpus, eid)["current"] if keeps_root_identity(root)         else root
    if own is not None:
        if own["changed_to"]:
            raise Refused({"error": "a later version replaced this one; "
                                    "delete the current version instead",
                           "entry": eid, "current": own["head"]})
    elif not keeps_root_identity(root) and corpus.stands(eid)["superseded_by"]:
        raise Refused({"error": "a later version replaced this one; delete "
                                "the current version instead", "entry": eid,
                       "current": lineage(corpus, eid)["current"]["id"]})
    turn = eid if kind == CONTRIBUTION else None
    with corpus.atomic():
        record = corpus.write(kind=DELETION,
                              body={"reason": because or "deleted"},
                              attributed_to=by, written_by=written_by)
        link = corpus.write(body={"reason": because or "deleted"},
                            attributed_to=by, written_by=written_by,
                            link={"from": record, "to": head["id"],
                                  "relation": supersedes_relation(corpus)})
        oid = cv.record_act(
            actor=by, act="turn-deleted" if turn else "material-deleted",
            conversation=cv.conversation_of(eid) if turn else None,
            turn=turn, about=[eid, head["id"]], because=because or None,
            detail={"deletion": record, "link": link, "ends": head["id"]})
    return {"entry": eid, "deleted": head["id"], "deletion": record,
            "link": link, "act": oid, "kind": kind,
            "standing": corpus.stands(head["id"]),
            "erases": "nothing. Every version, act and link is still in the "
                      "record, and history still says what it contributed "
                      "before this."}
