"""Anchored Interaction: a durable, precise target inside one Turn version.

THE ANCHOR IS THE PRIMITIVE, not feedback. An `anchor` entry names a place in
ONE IMMUTABLE VERSION of a Turn -- the whole version, or a range of code points
inside one of its text parts -- and asserts nothing about it. Everything else
here is an ordinary thing pointed at an anchor:

  REACTION     a `reaction` entry (`reacts-to` the anchor): who reacted, with
               what token. An immutable occurrence. A change is a NEW reaction
               that `supersedes` the earlier one; withdrawal is the ordinary
               Delete, by the reactor. Another actor's Delete withholds its
               token and its count and is said as theirs, never as the
               reactor's withdrawal. It has no standing and no effect on
               anything.
  REPLY        an ordinary Turn that `replies-to` the anchored Turn's ROOT and
               carries one `{type: "anchor", ref}` part saying exactly where.
               No observation is written for it.
  DEEP DIVE    a fresh Conversation, `opened-from` the anchor with the reason
               on the link, whose opening Turn carries `[anchor, text(reason)]`.
               Lineage, never context: nothing of the parent Conversation is
               inherited, and its origin is resolved live (`origin`).

Productionized from the round-3 falsifying prototype (S1-S15); see
`docs/design/anchored-interaction.md` for the seam map and decisions.

RANGE IDENTITY is (version, part, start, end) in CODE POINTS, validated here:
inside one text part, on extended grapheme cluster boundaries
(`graphemes`), and matching the excerpt the caller saw. UTF-16 offsets from a
browser are converted at this boundary. Never a copied quote, a DOM path or a
fuzzy match; the excerpt is read from the version every time and never stored.

DELETION. Nothing new is built on deleted material: a deleted Turn cannot be
anchored, reacted to, replied to through an anchor or dived from, and an
anchor into a deleted Turn is inert for new use (`versions.inert_refusal`).
History stays: anchors, reactions, replies and dives already made are listed,
and their views say `deleted` with the excerpt withheld. A reaction may still
be withdrawn, and a child Conversation goes on. Nothing is cancelled.

RETRY. `keyed` gives an operation key per actor: the same key and request
replays the first outcome, the same key with a different request is refused,
a fresh key is a deliberate new occurrence. The lookup and the write share one
`corpus.atomic()`.

NOTHING FROM OUTSIDE `mentis.conversation` IS IMPORTED, for the reason the
rest of this package imports nothing inward.
"""

from __future__ import annotations

import hashlib
import json

from . import graphemes
from .versions import (Refused, deletion_of, inert_refusal, presented,
                       supersedes_relation)

ANCHOR = "anchor"
REACTION = "reaction"
CONTRIBUTION = "contribution"
CONVERSATION = "conversation"
ANCHORS_IN = "anchors-in"
REACTS_TO = "reacts-to"
OPENED_FROM = "opened-from"
REPLIES_TO = "replies-to"
IN_CONVERSATION = "in-conversation"
LINKED_INTO = "linked-into"
ANCHOR_PART = "anchor"
KEYED = "operation-keyed"

#: The selector types this slice implements, and the ones whose names are
#: kept for targets the model naturally extends to. Reserved is refused.
SELECTORS = ("version", "text-range")
RESERVED_SELECTORS = ("region", "artifact")
UNITS = ("codepoint", "utf16")

#: A reaction is a token, not a comment: a comment is a reply.
TOKEN_MAX = 32


def _kind(e) -> str | None:
    return (e.get("definition") or {}).get("name")


def _one(corpus, eid, kind=None, what="entry") -> dict:
    got = corpus.read([eid]) if isinstance(eid, str) and eid else []
    if not got or got[0].get("family") != "entry" or got[0].get("link"):
        raise Refused({"error": f"the record holds no such {what}",
                       "ref": eid})
    if kind and _kind(got[0]) != kind:
        raise Refused({"error": f"{eid} is not a{'n' if kind[0] in 'aeiou' else ''} "
                                f"{kind}", "ref": eid,
                       "kind": _kind(got[0])})
    return got[0]


def _inert(corpus, *ids):
    refusal = inert_refusal(corpus, *ids)
    if refusal:
        raise Refused(refusal)


def turn_root(corpus, version) -> str:
    """The Turn a Contribution version is a version of: its root."""
    return corpus.history(version)[0]


def anchor_turn(corpus, aid) -> str | None:
    """The Turn root this anchor is in."""
    for x in corpus.links(relation=ANCHORS_IN, frm=aid):
        return x["link"]["to"]
    return None


def conversation_of(corpus, turn) -> str | None:
    for x in corpus.links(relation=IN_CONVERSATION, frm=turn):
        return x["link"]["to"]
    return None


def included_in(corpus, turn, conversation) -> bool:
    """Is this Turn included in that Conversation NOW: a `linked-into` link
    from it to there that nothing has ended."""
    return any(not corpus.stands(x["id"])["superseded_by"]
               for x in corpus.links(relation=LINKED_INTO, frm=turn,
                                     to=conversation))


def selector_of(a) -> dict:
    """An anchor entry's selector, or {} when its body holds none: an
    anchor-Kind entry made by a generic door carries whatever it was given."""
    sel = (a.get("body") or {}).get("selector")
    return sel if isinstance(sel, dict) else {}


def source_deletion(corpus, sel, root=None) -> dict | None:
    """The deletion that withholds what a selector names, or None: the
    `deletion_of` the anchor's Turn (`root`) or the version its selector
    names. The ONE deletion reading for an anchor, asked by `source` for what
    is shown and by `versions.inert_refusal` for what may be newly used, so
    neither depends on whether the anchor happens to sit in a Turn."""
    vid = sel.get("version")
    return next((d for d in (deletion_of(corpus, x) for x in (root, vid)
                             if isinstance(x, str) and x)
                 if d is not None), None)


def source(corpus, sel, root=None) -> dict:
    """What a selector names, read from the immutable version NOW: the ONE
    reading every door that shows an anchor's words goes through (`view`,
    `origin`, and so `route_back`, `annotate_part`, `anchors_on` and the
    worker's `resolve`).

    DELETION is `deletion_of` -- the reading `inert_refusal` and the rest of
    this module use -- asked of the Turn the anchor is in AND of the version
    its selector names. An anchor in no Turn (made by the generic `revise`
    or `/api/entries`) is therefore withheld exactly as one in a Turn is,
    once that Turn is deleted (R3-1). A selector that names no such version,
    part or range reads as `unresolvable`, never as a crash (R3-5).

    Returns `deletion` (the record, or None), `unresolvable` (why, or None),
    `text` (the whole text part, for a resolvable text-range) and `excerpt`.
    """
    vid = sel.get("version")
    out = {"deletion": source_deletion(corpus, sel, root),
           "unresolvable": None, "text": None,
           "excerpt": None}
    got = corpus.read([vid]) if isinstance(vid, str) and vid else []
    if not got or got[0].get("family") != "entry" or got[0].get("link"):
        out["unresolvable"] = "the record holds no version this anchor names"
        return out
    if sel.get("type") != "text-range":
        return out
    parts = (got[0].get("body") or {}).get("parts") or []
    p, start, end = sel.get("part"), sel.get("start"), sel.get("end")
    if (not isinstance(p, int) or isinstance(p, bool) or not 0 <= p < len(parts)
            or not isinstance(parts[p], dict)
            or parts[p].get("type") != "text"):
        out["unresolvable"] = "that version has no such text part"
        return out
    text = parts[p].get("text") or ""
    if not (all(isinstance(x, int) and not isinstance(x, bool)
                for x in (start, end)) and 0 <= start < end <= len(text)):
        out["unresolvable"] = "that text part has no such range"
        return out
    out["text"], out["excerpt"] = text, text[start:end]
    return out


def anchor_parts(parts) -> list:
    return [p for p in parts or () if isinstance(p, dict)
            and p.get("type") == ANCHOR_PART]


# -- retry identity ----------------------------------------------------------

def digest(request) -> str:
    return hashlib.sha256(json.dumps(request, sort_keys=True,
                                     ensure_ascii=False,
                                     default=str).encode()).hexdigest()


def keyed(cv, actor, op, request, fn, *, conversation=None, act_kw=None):
    """Run `fn` once per (actor, op). See the module docstring.

    `request` is what the caller asked, as sent; its digest is what makes a
    retry the same operation. `fn` returns a dict of plain values, which is
    what a retry gets back with `replayed: True`. A refusal raised by `fn` is
    not recorded, so a corrected request may use the key.
    """
    corpus = cv.corpus
    if op is None or op == "":
        return fn()
    with corpus.atomic():
        prior = prior_outcome(cv, actor, op, request)
        if prior is not None:
            return prior
        result = fn()
        record_outcome(cv, actor, op, request, result,
                       conversation=conversation, act_kw=act_kw)
        return result


def prior_outcome(cv, actor, op, request) -> dict | None:
    """What this actor's earlier operation under `op` came to, or None.
    Call inside the `corpus.atomic()` that will also write the outcome."""
    if not isinstance(op, str) or not op.strip() or len(op) > 200:
        raise Refused({"error": "an operation key is a non-empty string of at "
                                "most 200 characters"})
    d = digest(request)
    # THE ACTOR'S OWN KEYED ACT FOR THIS KEY: the existing (actor, seq) index
    # bounds the read, SQLite matches the key, and only a match is decoded.
    # Read inside the write lock, so two racing requests cannot both miss.
    for a in cv.corpus.operational(actor=actor, act=KEYED,
                                   detail_is={"op": op}):
        if (a.get("detail") or {}).get("op") == op:
            if a["detail"].get("digest") != d:
                raise Refused({
                    "error": "this operation key was already used for a "
                             "different request; nothing was written. A new "
                             "occurrence uses a new key",
                    "op": op, "first": a["id"]})
            return {**a["detail"]["result"], "replayed": True}
    return None


def record_outcome(cv, actor, op, request, result, *, conversation=None,
                   act_kw=None) -> str:
    return cv.record_act(
        actor=actor, act=KEYED, conversation=conversation,
        about=[v for v in result.values()
               if isinstance(v, str) and v.startswith("ent-")][:8],
        detail={"op": op, "digest": digest(request), "result": result},
        **(act_kw or {}))


# -- anchors -----------------------------------------------------------------

def selector_for(corpus, request) -> tuple[dict, str, dict]:
    """Validate what the caller asked to anchor. Returns (selector, root,
    version entry). Refuses anything that does not name a place exactly."""
    vid = request.get("version")
    ver = _one(corpus, vid, CONTRIBUTION, "Turn version")
    root = turn_root(corpus, vid)
    _inert(corpus, root, vid)
    typ = request.get("type")
    if typ in RESERVED_SELECTORS:
        raise Refused({"error": f"a {typ!r} anchor is reserved and not offered "
                                f"yet; this slice anchors a whole version or a "
                                f"range of text", "type": typ})
    if typ == "version":
        return {"type": "version", "version": vid}, root, ver
    if typ != "text-range":
        raise Refused({"error": "an anchor's type is 'version' or 'text-range'",
                       "type": typ})
    parts = ver["body"].get("parts") or []
    p = request.get("part")
    if not isinstance(p, int) or isinstance(p, bool) or not 0 <= p < len(parts):
        raise Refused({"error": "that version has no such part", "part": p,
                       "parts": len(parts)})
    if parts[p].get("type") != "text":
        raise Refused({"error": "only a text part can be anchored by range in "
                                "this slice", "part": p,
                       "part_type": parts[p].get("type")})
    text = parts[p].get("text") or ""
    start, end, unit = request.get("start"), request.get("end"), request.get("unit")
    if not all(isinstance(x, int) and not isinstance(x, bool)
               for x in (start, end)):
        raise Refused({"error": "start and end are integers"})
    if unit not in UNITS:
        raise Refused({"error": "unit is 'codepoint', or 'utf16' as a browser "
                                "counts", "unit": unit})
    if unit == "utf16":
        try:
            start = graphemes.utf16_to_codepoint(text, start)
            end = graphemes.utf16_to_codepoint(text, end)
        except ValueError as exc:
            raise Refused({"error": str(exc)})
    if not 0 <= start < end <= len(text):
        raise Refused({"error": "the range is not inside this one text part (a "
                                "range is non-empty and may not cross parts)",
                       "start": start, "end": end, "length": len(text)})
    try:
        edges = graphemes.boundaries(text)
    except graphemes.Unavailable as exc:
        raise Refused({"error": str(exc)})
    for edge in (start, end):
        if edge not in edges:
            raise Refused({"error": "the range edge splits a user-perceived "
                                    "character", "at": edge,
                           "unicode": graphemes.UNICODE_VERSION})
    got = text[start:end]
    if request.get("expected_excerpt") != got:
        raise Refused({"error": "the excerpt you saw does not match the stored "
                                "text at that range; nothing was anchored",
                       "expected": request.get("expected_excerpt")})
    return ({"type": "text-range", "version": vid, "part": p,
             "start": start, "end": end, "unit": "codepoint"}, root, ver)


def create_anchor(cv, request, *, by, written_by=None, may_act_in=None,
                  act_kw=None) -> dict:
    """Find or create the anchor for this exact place. Identity is the
    selector: the same place asked for twice is one anchor."""
    corpus = cv.corpus
    _one(corpus, by, "participant", "participant")
    asked = {k: request.get(k) for k in ("version", "type", "part", "start",
                                         "end", "unit", "expected_excerpt")}

    def write():
        sel, root, _ = selector_for(corpus, request)
        conv = conversation_of(corpus, root)
        if may_act_in:
            may_act_in(conv)
        for x in corpus.links(relation=ANCHORS_IN, to=root):
            a = corpus.read([x["link"]["from"]])
            if a and a[0]["body"].get("selector") == sel:
                return {"anchor": a[0]["id"], "created": False,
                        "turn": root, "conversation": conv}
        aid = corpus.write(kind=ANCHOR, body={"selector": sel},
                           attributed_to=by, written_by=written_by)
        corpus.write(body={"reason": "anchored"}, attributed_to=by,
                     written_by=written_by,
                     link={"from": aid, "to": root, "relation": ANCHORS_IN})
        cv.record_act(actor=by, act="anchor-created", conversation=conv,
                      turn=root, about=[aid, sel["version"]],
                      **(act_kw or {}))
        return {"anchor": aid, "created": True, "turn": root,
                "conversation": conv}

    with corpus.atomic():
        out = keyed(cv, by, request.get("op"), {"route": "anchor", **asked},
                    write, act_kw=act_kw)
    return {**out, **view(cv, out["anchor"])}


def view(cv, aid) -> dict:
    """The anchor as it resolves now. Its excerpt is read from the version,
    and withheld once the anchored Turn is deleted -- whether or not the
    anchor is in a Turn (`source`)."""
    corpus = cv.corpus
    a = _one(corpus, aid, ANCHOR, "anchor")
    sel = selector_of(a)
    root = anchor_turn(corpus, aid)
    conv = conversation_of(corpus, root) if root else None
    src = source(corpus, sel, root)
    d = src["deletion"]
    rootentry = corpus.read([root])[0] if root else None
    now = presented(corpus, rootentry) if rootentry else None
    current = ((now or {}).get("revision") or {}).get("current", root)
    out = {"anchor": aid, "selector": sel, "turn": root, "conversation": conv,
           "by": a["attributed_to"], "at": a["recorded_at"],
           "author": rootentry["attributed_to"] if rootentry else None,
           "deleted": bool(d),
           "version_is_current": (not d) and current == sel.get("version"),
           "current_version": None if d else current}
    if d:
        out["excerpt"] = None
        out["excerpt_withheld"] = ("the anchored material was deleted; its "
                                   "words are not shown")
        return out
    if src["unresolvable"]:
        out["excerpt"] = None
        out["unresolvable"] = src["unresolvable"]
        return out
    excerpt = src["excerpt"]
    out["excerpt"] = excerpt
    if sel.get("type") == "text-range":
        text = src["text"]
        out["utf16"] = {"start": graphemes.codepoint_to_utf16(text, sel["start"]),
                        "end": graphemes.codepoint_to_utf16(text, sel["end"])}
        if now is not None and current != sel["version"]:
            # A LIKENESS, NOT AN IDENTITY: the same characters may appear in
            # the current version any number of times, and none of them is
            # this anchor.
            words = "".join(p.get("text") or "" for p in now["body"]["parts"]
                            if p.get("type") == "text")
            out["likeness_in_current"] = {"occurrences": words.count(excerpt),
                                          "is_identity": False}
    return out


def anchors_on(cv, turn) -> list[dict]:
    """Every anchor in this Turn, with what is attached to it, for drawing."""
    out = []
    for x in cv.corpus.links(relation=ANCHORS_IN, to=turn):
        aid = x["link"]["from"]
        v = view(cv, aid)
        i = interactions(cv, aid)
        v["reactions"] = i["current"]
        v["replies"] = i["replies"]
        v["deep_dives"] = i["deep_dives"]
        out.append(v)
    return out


# -- reactions ---------------------------------------------------------------

def _anchored_conversation(corpus, aid) -> tuple[str, str | None]:
    root = anchor_turn(corpus, aid)
    if root is None:
        raise Refused({"error": "that anchor is in no Turn", "anchor": aid})
    return root, conversation_of(corpus, root)


def is_occurrence(corpus, rid, aid=None) -> bool:
    """Whether this reaction-Kind entry is a REACTION OCCURRENCE: one the
    reaction operation wrote, which `reacts-to` an anchor (this one, when
    `aid` is given). Material of the reaction Kind written by a generic act
    -- a `revise`, or `/api/entries` -- reacts to nothing and is not one
    (Brian's decision (2), ent-92915b5e7706 on opr-5ceb3e84bb09)."""
    return bool(corpus.links(relation=REACTS_TO, frm=rid,
                             **({"to": aid} if aid else {})))


def own_changes(corpus, actor) -> dict:
    """{earlier reaction: the reaction that changed it}, for every change
    this actor made to their own reaction THROUGH THE REACTION OPERATION.

    Read from the `reaction-changed` acts `react(changes=)` records, never
    from the `supersedes` links alone: another actor's generic `supersede`
    or `revise` also writes such a link, and is not the reactor changing
    their mind (Brian, ent-92915b5e7706 on opr-5ceb3e84bb09)."""
    out = {}
    for a in corpus.operational(actor=actor, act="reaction-changed"):
        about = a["about"]
        if len(about) >= 3:
            out[about[2]] = about[0]
    return out


def own_line(corpus, rid, changed=None) -> dict:
    """A reaction's OWN line: the reaction, then its reactor's own changes,
    and the withdrawal that ended it if one did. Another actor's
    relationship to a reaction -- a generic supersession or revision, or a
    Delete -- neither closes this line nor joins it.

    A WITHDRAWAL IS THE REACTOR'S OWN DELETE. Another actor's Delete of a
    reaction in the line makes it unavailable for display and counting
    (`interactions`), and is not the reactor withdrawing it (Brian,
    ent-e8bbeff33d48 on opr-9257c35b2ec1)."""
    reactor = corpus.read([rid])[0]["attributed_to"]
    if changed is None:
        changed = own_changes(corpus, reactor)
    line = [rid]
    while line[-1] in changed and changed[line[-1]] not in line:
        line.append(changed[line[-1]])
    withdrawal = next((d for d in (deletion_of(corpus, x) for x in line)
                       if d is not None and d["attributed_to"] == reactor),
                      None)
    return {"line": line, "head": line[-1],
            "changed_to": line[1] if len(line) > 1 else None,
            "withdrawal": withdrawal}


def react(cv, aid, request, *, by, written_by=None, may_act_in=None,
          act_kw=None) -> dict:
    corpus = cv.corpus
    _one(corpus, by, "participant", "participant")
    asked = {k: request.get(k) for k in ("token", "changes", "because")}

    def write():
        _one(corpus, aid, ANCHOR, "anchor")
        root, conv = _anchored_conversation(corpus, aid)
        if may_act_in:
            may_act_in(conv)
        _inert(corpus, root, aid)
        token = request.get("token")
        if not isinstance(token, str) or not token.strip():
            raise Refused({"error": "a reaction carries the token its actor "
                                    "chose"})
        token = token.strip()
        if len(token) > TOKEN_MAX or "\n" in token:
            raise Refused({"error": f"a reaction is a token of at most "
                                    f"{TOKEN_MAX} characters on one line; to "
                                    f"say something, reply"})
        changes = request.get("changes")
        if changes:
            old = _one(corpus, changes, REACTION, "reaction")
            if old["body"].get("about") != aid:
                raise Refused({"error": "a change names an earlier reaction on "
                                        "THIS anchor", "changes": changes})
            if not is_occurrence(corpus, changes, aid):
                raise Refused({"error": "a change names an earlier reaction "
                                        "made on THIS anchor; that entry is "
                                        "material of the reaction Kind that "
                                        "reacts to nothing (a generic revision "
                                        "or entry), not a reaction occurrence",
                               "changes": changes})
            if old["attributed_to"] != by:
                raise Refused({"error": "only the actor who reacted can change "
                                        "that reaction", "changes": changes})
            # THE REACTOR'S OWN LINE decides, not every `supersedes` into
            # it: a reaction another actor superseded or revised is still
            # its reactor's to change (Brian, ent-92915b5e7706 on
            # opr-5ceb3e84bb09). Its own line ends only with its reactor's
            # change or its withdrawal.
            line = own_line(corpus, changes)
            if line["changed_to"] or line["withdrawal"]:
                raise Refused({"error": "that reaction was already changed or "
                                        "withdrawn; change the current one",
                               "changes": changes,
                               **({"current": line["head"]}
                                  if not line["withdrawal"] else {})})
            # DELETED BY ANOTHER ACTOR: not withdrawn, and not built on
            # either -- nothing new is written onto deleted material. The
            # reactor reacts afresh. Refused before this decision too; only
            # the reason is now true.
            gone = deletion_of(corpus, changes)
            if gone is not None:
                raise Refused({"error": "that reaction was deleted by "
                                        f"{cv.alias(gone['attributed_to'])}; "
                                        "a deleted reaction is not changed. "
                                        "React again instead",
                               "changes": changes, "deletion": gone["id"]})
        rid = corpus.write(kind=REACTION, body={"about": aid, "token": token},
                           attributed_to=by, written_by=written_by)
        corpus.write(body={"reason": "reacted"}, attributed_to=by,
                     written_by=written_by,
                     link={"from": rid, "to": aid, "relation": REACTS_TO})
        if changes:
            corpus.write(body={"reason": request.get("because")
                               or "changed reaction"},
                         attributed_to=by, written_by=written_by,
                         link={"from": rid, "to": changes,
                               "relation": supersedes_relation(corpus)})
        cv.record_act(actor=by,
                      act="reaction-changed" if changes else "reaction-recorded",
                      conversation=conv, turn=root,
                      about=[rid, aid] + ([changes] if changes else []),
                      because=request.get("because") or None,
                      **(act_kw or {}))
        return {"reaction": rid, "anchor": aid, "token": token,
                **({"changes": changes} if changes else {})}

    with corpus.atomic():
        return keyed(cv, by, request.get("op"),
                     {"route": "react", "anchor": aid, **asked}, write,
                     act_kw=act_kw)


def interactions(cv, aid) -> dict:
    """Everything attached to this anchor, as history: every reaction
    occurrence (changed and withdrawn ones included), the anchored replies,
    and the deep dives opened from it."""
    corpus = cv.corpus
    _one(corpus, aid, ANCHOR, "anchor")
    root = anchor_turn(corpus, aid)
    sup = supersedes_relation(corpus)

    # TWO DIMENSIONS, KEPT APART (Brian, ent-92915b5e7706 on
    # opr-5ceb3e84bb09). A REACTOR'S OWN LINE is what `react(changes=)` and withdrawal write, read from the
    # reactor's own `reaction-changed` acts; only it moves `changes`/
    # `changed_to` and whether the reaction is current. Anything else that
    # supersedes a reaction -- the generic `supersede` or `revise`, whoever
    # does it -- is an ordinary relationship, reported as `replaced_by`/
    # `replaces` with who did it, and changes nobody's reaction.
    changed = {}

    def own_of(actor) -> dict:
        if actor not in changed:
            changed[actor] = own_changes(corpus, actor)
        return changed[actor]

    def other(newer, older, named) -> dict:
        # `by` is whoever wrote the `supersedes` link: who did the act.
        link = corpus.links(relation=sup, frm=newer["id"], to=older["id"])
        by = link[0]["attributed_to"] if link else newer["attributed_to"]
        return {"entry": named["id"], "kind": _kind(named), "by": by,
                "by_alias": cv.alias(by)}

    reactions = []
    for x in corpus.links(relation=REACTS_TO, to=aid):
        r = corpus.read([x["link"]["from"]])[0]
        st = corpus.stands(r["id"])
        later = corpus.read(st["superseded_by"])
        # DELETION WINS ON DISPLAY; LINEAGE STAYS THE REACTOR'S (Brian,
        # ent-e8bbeff33d48 on opr-9257c35b2ec1). Deleted by its reactor is
        # their withdrawal. Deleted by anybody else, it is said as that --
        # who deleted it -- with its token withheld and nothing counted, and
        # it is not the reactor withdrawing or changing it.
        deletion = deletion_of(corpus, r["id"])
        withdrawn = (deletion is not None
                     and deletion["attributed_to"] == r["attributed_to"])
        by_other = deletion is not None and not withdrawn
        mine = own_of(r["attributed_to"])
        line = own_line(corpus, r["id"], mine)
        changed_to = line["changed_to"]
        changes = next((old for old, new in mine.items()
                        if new == r["id"]), None)
        replaced_by = [other(s, r, s) for s in later
                       if s["id"] not in ((deletion or {}).get("id"),
                                          changed_to)]
        earlier = corpus.read([y["link"]["to"] for y in corpus.links(
            relation=sup, frm=r["id"])])
        replaces = [other(r, e, e) for e in earlier if e["id"] != changes]
        row = {
            "reaction": r["id"],
            "token": None if by_other else r["body"].get("token"),
            "by": r["attributed_to"], "by_alias": cv.alias(r["attributed_to"]),
            "at": r["recorded_at"], "changes": changes,
            "changed_to": changed_to,
            "withdrawn": withdrawn,
            "in_withdrawn_line": bool(line["withdrawal"]),
            "deleted": deletion is not None,
            # SUPERSEDED BY SOMEBODY ELSE'S ACT, said as that: who did it,
            # and with what. It does not end the reaction's currency: only
            # its reactor's own change or its withdrawal does.
            "replaced_by": replaced_by, "replaces": replaces,
            "current": deletion is None and not changed_to}
        if deletion is not None:
            row.update({"deletion": deletion["id"],
                        "deleted_by": deletion["attributed_to"],
                        "deleted_by_alias": cv.alias(deletion["attributed_to"]),
                        "deleted_at": deletion["recorded_at"]})
        if by_other:
            row["token_withheld"] = (
                f"a reaction by {row['by_alias']} was deleted by "
                f"{row['deleted_by_alias']}; its token is not shown")
        reactions.append(row)
    reactions.sort(key=lambda r: r["at"])
    # NO GHOST COUNT: a deleted reaction is not current, whoever deleted it.
    current = {}
    for r in reactions:
        if r["current"]:
            current[r["token"]] = current.get(r["token"], 0) + 1
    replies = []
    if root:
        for x in corpus.links(relation=REPLIES_TO, to=root):
            e = corpus.read([x["link"]["from"]])
            if e and any(p.get("ref") == aid for p in anchor_parts(
                    presented(corpus, e[0])["body"].get("parts")
                    or e[0]["body"].get("parts"))):
                replies.append(e[0]["id"])
    dives = [x["link"]["from"] for x in corpus.links(relation=OPENED_FROM,
                                                      to=aid)]
    return {"anchor": aid, "reactions": reactions,
            "current": [{"token": t, "count": n} for t, n in current.items()],
            "replies": replies, "deep_dives": dives}


# -- the anchor part on a Turn -------------------------------------------------

def check_parts(cv, conversation, parts, replies_to) -> None:
    """The one rule for a Turn that carries an anchor part. Asked by `say`,
    which every Turn write goes through, so no door can skip it.

    Either an ANCHORED REPLY -- it replies to exactly the Turn the anchor is
    in, said in a Conversation that Turn is IN: its home, or one it is
    included in now by a `linked-into` link nothing has ended -- or the
    OPENING TURN of a Conversation opened from that anchor, which replies to
    nothing and comes first.
    """
    found = anchor_parts(parts)
    if not found:
        return
    corpus = cv.corpus
    if len(found) != 1:
        raise Refused({"error": "a Turn carries at most one anchor part"})
    aid = found[0].get("ref")
    _one(corpus, aid, ANCHOR, "anchor")
    root = anchor_turn(corpus, aid)
    if replies_to:
        if replies_to != root:
            raise Refused({"error": "an anchored reply replies to the Turn its "
                                    "anchor is in", "anchor_turn": root,
                           "replies_to": replies_to})
        # IN A CONVERSATION THE TURN IS IN (owner rule, ent-70e12b637054
        # point 3): where it was written, or where it is included now. The
        # reply belongs to the Conversation it is said in, wherever that is.
        if conversation_of(corpus, root) != conversation and \
                not included_in(corpus, root, conversation):
            raise Refused({"error": "an anchored reply is said in a "
                                    "Conversation the Turn it answers is in: "
                                    "its own, or one it is included in",
                           "anchor_conversation": conversation_of(corpus, root)})
    else:
        opened = [x["link"]["to"] for x in corpus.links(relation=OPENED_FROM,
                                                        frm=conversation)]
        if opened != [aid] or corpus.links(relation=IN_CONVERSATION,
                                           to=conversation):
            raise Refused({"error": "an anchor part without replies_to is only "
                                    "the opening Turn of a Conversation opened "
                                    "from that anchor; a reply names the Turn "
                                    "it answers", "anchor": aid})
    _inert(corpus, root, aid)


# -- deep dives --------------------------------------------------------------

def deep_dive(cv, aid, request, *, by, written_by=None, may_act_in=None,
              act_kw=None) -> dict:
    """Open a fresh Conversation to explore this anchor, for a stated reason.

    ITS NAME COMES FROM THE REASON OR FROM WHAT THE OPENER TYPED, NEVER FROM
    THE ANCHORED TEXT: a name built from the excerpt would copy the source
    into the record, where it would outlive the source's deletion (found by
    round 3's S13).
    """
    corpus = cv.corpus
    _one(corpus, by, "participant", "participant")
    asked = {k: request.get(k) for k in ("why", "name")}

    def write():
        _one(corpus, aid, ANCHOR, "anchor")
        root, parent = _anchored_conversation(corpus, aid)
        if may_act_in:
            may_act_in(parent)
        _inert(corpus, root, aid)
        why = (request.get("why") or "").strip()
        if not why:
            raise Refused({"error": "a deep dive says why separate exploration "
                                    "is being opened"})
        name = (request.get("name") or "").strip() or (
            "Deep dive: " + (why if len(why) <= 60 else why[:59] + "…"))
        child = cv.open_conversation(name, about=why, attributed_to=by,
                                     written_by=written_by)
        cv.join(by, child, attributed_to=by, written_by=written_by)
        corpus.write(body={"reason": why}, attributed_to=by,
                     written_by=written_by,
                     link={"from": child, "to": aid, "relation": OPENED_FROM})
        opening = cv.say(child, by, [{"type": ANCHOR_PART, "ref": aid},
                                     {"type": "text", "text": why}],
                         written_by=written_by)
        cv.record_act(actor=by, act="conversation-opened", conversation=child,
                      turn=opening, about=[parent, aid], because=why,
                      detail={"opened_from": aid, "parent": parent},
                      **(act_kw or {}))
        # THE OPENING TURN IS SAID LIKE EVERY TURN: the Conversation Brief and
        # every reader that finds Turns by their `turn-said` act find it. No
        # runtime on it, for the reason `respond` gives (a `turn-said` claims
        # no provider).
        cv.record_act(actor=by, act="turn-said", conversation=child,
                      turn=opening, because="the reason this deep dive was "
                                            "opened",
                      **{k: v for k, v in (act_kw or {}).items()
                         if k != "runtime"})
        return {"conversation": child, "opening_turn": opening,
                "anchor": aid, "parent": parent, "name": name}

    with corpus.atomic():
        return keyed(cv, by, request.get("op"),
                     {"route": "deep-dive", "anchor": aid, **asked}, write,
                     act_kw=act_kw)


def origin(cv, child) -> dict | None:
    """Where this Conversation was opened from, resolved now: the anchor, its
    version, the anchored Turn, the parent Conversation's name, and why.

    READS ONLY THOSE. Not the parent's Turns, instructions or placements --
    lineage is not context. The excerpt is withheld once the source is
    deleted; the child goes on regardless.
    """
    corpus = cv.corpus
    links = corpus.links(relation=OPENED_FROM, frm=child)
    if not links:
        return None
    lk = links[0]
    aid = lk["link"]["to"]
    a = corpus.read([aid])[0]
    sel = selector_of(a)
    root = anchor_turn(corpus, aid)
    parent = conversation_of(corpus, root) if root else None
    # UNDER ITS CURRENT NAME, as every reader of a Conversation's name reads it.
    pconv = presented(corpus, corpus.read([parent])[0]) if parent else None
    rootentry = corpus.read([root])[0] if root else None
    src = source(corpus, sel, root)
    deleted = bool(src["deletion"])
    return {"anchor": aid, "selector": sel, "turn": root,
            "conversation": parent,
            "conversation_name": (pconv or {}).get("body", {}).get("name"),
            "turn_author": rootentry["attributed_to"] if rootentry else None,
            "turn_author_alias": cv.alias(rootentry["attributed_to"])
            if rootentry else None,
            "anchored_by": a["attributed_to"],
            "anchored_by_alias": cv.alias(a["attributed_to"]),
            "why": (lk["body"] or {}).get("reason"),
            "opened_by": lk["attributed_to"],
            "opened_by_alias": cv.alias(lk["attributed_to"]),
            "deleted": deleted,
            "excerpt": None if deleted else src["excerpt"],
            **({"unresolvable": src["unresolvable"]}
               if src["unresolvable"] and not deleted else {})}


def origin_lines(o: dict) -> list[str]:
    """The origin as orientation says it to whoever works in the child."""
    whole = o["selector"].get("type") == "version"
    lines = [f"Opened from an anchor ({o['anchor']}) on "
             f"{'a whole Turn' if whole else 'a passage of a Turn'} "
             f"({o['turn']}) by {o['turn_author_alias']} in "
             f"“{o['conversation_name']}”, anchored by "
             f"{o['anchored_by_alias']}."]
    if o["deleted"]:
        lines.append("The anchored material was deleted; its words are not "
                     "shown.")
    elif o.get("unresolvable"):
        lines.append(f"The anchored place cannot be read: "
                     f"{o['unresolvable']}.")
    elif not whole:
        lines.append(f"The anchored passage, as that version reads: "
                     f"“{o['excerpt']}”")
    lines.append(f"Why this was opened: {o['why']}")
    return lines


def route_back(cv, ref) -> dict:
    """From a reply, a reaction, a deep-dive Conversation or an anchor, to the
    exact anchor it came from."""
    corpus = cv.corpus
    got = corpus.read([ref]) if isinstance(ref, str) and ref else []
    if not got:
        raise Refused({"error": "the record holds no such entry", "ref": ref})
    e, k = got[0], _kind(got[0])
    aid = None
    if k == ANCHOR:
        aid = ref
    elif k == CONVERSATION:
        o = origin(cv, ref)
        aid = o and o["anchor"]
    elif k == CONTRIBUTION:
        found = anchor_parts(presented(corpus, e)["body"].get("parts")
                             or e["body"].get("parts"))
        aid = found[0]["ref"] if found else None
    elif k == REACTION:
        aid = e["body"].get("about")
    if not aid:
        return {"from": ref, "anchor": None}
    return {"from": ref, **view(cv, aid)}


def annotate_part(cv, part) -> dict:
    """An anchor part as a reader draws it: the reference, and the anchor as
    it resolves now. Refused or unknown references say so."""
    try:
        return {**part, "anchor_view": view(cv, part.get("ref"))}
    except Refused as refused:
        return {**part, "anchor_view": None,
                "anchor_error": refused.refusal.get("error")}
