"""What people fill in, kept: response sets, answers and marked-ready.

DURABLE FILLABLE BLOCKS (design revision 3, adm-a32b134770fc; build plan
adm-ba8fea710d8a, package P2a). A form, checklist, editable table or pad in a
Turn is filled in through a RESPONSE SET, and everything written to it is an
attributed, immutable entry. Nothing is stored as a status: whether a set is
valid, ready, changed since ready, in conflict or missing something is
READ from the entries every time (`state`).

  RESPONSE SET   `response-set`: one block in one Turn part -- the post's
                 ROOT, the text part, the block's `name=`, its type -- and a
                 mode: `shared` (one set everybody fills in; the default) or
                 `each` (one set per person, for feedback; `holder` says
                 whose). Opened once per (post, part, block, mode, holder):
                 opening it again finds it. It `responds-to` the post.
  ANSWER         `answer`: one field's value, `in-response-set` its set. It
                 names the answers it REPLACES (`replaces`, a list), and a
                 `supersedes` link to each says so to the generic reader too.
                 Answers are never edited or deleted.
  MARKED READY   `marked-ready`: "my input is finished" (Done), naming the
                 exact answers it covers. A later answer makes the set
                 "changed since ready"; nothing un-marks it.
  OWN WORDS      `own-words`: free text a person adds to a set in their own
                 words, kept exactly as written, under their name (P2b, F1).
                 A new version names the one it `replaces` and supersedes it;
                 the earlier wording stays, and only its author writes the
                 next. Not `contribution`, which is the Turn Kind (plan C1).
  INTERPRETATION `interpretation`: somebody else's reading of own words -- in
                 practice an agent's, under its own name. It cites the exact
                 passage it came from (a range of code points in one version
                 of the words, checked against the excerpt the proposer saw,
                 read from the words every time and never copied) and
                 proposes ONE thing: set a field to a value, add a row, or add
                 a field to the form. It records the post version it was read
                 against, and for a field, that field's declaration then.
  REPLY          `interpretation-reply`: what the person whose words they are
                 did with an interpretation -- `confirmed`, `changed` or
                 `declined`, once. Confirming or changing a proposed field
                 value is THEIR answer, written through `answer` and named on
                 the reply; a row or a field is not written into the post
                 (only its author edits a Turn), so confirming one records it
                 for the form's author to act on.
  TIMER MARK     `timer-mark`: a start, stop, continue, box-end or break-end
                 on a timer block, in the person's own `each` set. Written
                 and read by `mentis.conversation.timers`, which holds its
                 rules; listed here because it is kept exactly as answers
                 are (below): not knowledge, never generically written,
                 never deleted, nothing new on a deleted post, keyed retries.

UNCONFIRMED UNTIL THE PERSON SAYS (F1). Nothing an interpretation proposes is
an answer, and it never replaces the words. It is PENDING until replied to,
and OUT OF DATE -- computed, never stored -- when the field it maps to is no
longer declared as it was at the version it records (revision 2, section 7),
or when the field it proposes adding now exists. An out-of-date proposal can
be declined, not confirmed: it is to be read again. `accounting` lists every
passage of the current words and what became of it, and what no
interpretation has cited yet, for the agent to account for every point.

USING A FORM ELSEWHERE (revision 2, section 1). `show` shows a set in another
Conversation the post is included in (a `shown-in` link): the same answers,
and each answer records the Conversation it was given in. `start_new` opens a
separate set on the same block, `started_from` the first, copying earlier
answers only for the fields asked for.

CONFLICTS ARE KEPT. A field's current value is its HEAD: an answer no other
answer in the set replaces. Two answers that both replace the same one (two
tabs, two people) are both heads; both are kept and the field reads as a
conflict, listing both, until an answer names both as replaced. Read from the
answers' own `replaces`, never from `supersedes` links alone: the generic
`seam.history` follows only the newest link at a fork (plan C13), and another
actor's generic `supersede` is not somebody answering.

THE BLOCK'S OWN RULES DECIDE, run where the UI runs them. Every value is
checked by `render_check.answers` -- `checkAnswers` in
`ui/src/experimental/spec/fill.ts`, from the bundle, in QuickJS -- against the
post's CURRENT version (P1). Refused: no such block, a block that cannot be
saved (no usable unique `name=`, a table with no `key=`, repeated checklist
items), an unknown field, a value of the wrong shape. Recorded WITH its
problems: a value the block's rules find wrong (out of range, not a choice) --
what the person typed is kept and the set reads not valid. WHERE THE ENGINE IS
ABSENT (Intel macOS, by decision) the answer is recorded and marked `not
checked here`, never refused (owner choice R5, as settled). EVERY OTHER CHECK
THAT DOES NOT RUN REFUSES (R1): no bundle, a bundle older than `checkAnswers`,
a time or memory limit. A long post is checked like any other.

NOT KNOWLEDGE. None of these Kinds declares `knowing`, exactly as anchors and
reactions do not, so retrieval, delivery, adoption and the register never
read them. Their standing is not meaningful (`standing_apt` False). The
generic doors that would write one -- `/api/entries`, `revise`, `edit`, the
words form of `propose-supersession`, and `ladder_writes.record` behind the
material and adoption tools -- are closed to them
(`versions.GENERIC_WRITE_CLOSED`), and they are never deleted.

DELETED SOURCE (F5). Every write asks `versions.inert_refusal` of the post: a
deleted post accepts no new set, answer or marked-ready. Its sets and
answers stay, and `state` and `field_history` read them, saying the source
was deleted.

VERSIONS (F2). Each answer records the post version it was checked against.
When the post is edited, earlier answers stay on their version and the field
reads `earlier_version`; `move` carries them to the current version as new
answers that replace them: at once only when every field of the earlier
version, answered or not, is still declared with the same id and kind,
otherwise as a preview that writes nothing until it is confirmed, and then
only for the fields that still match.

WHO WRITES (F3). A `shared` set takes anybody's answers; an `each` set only its
holder's. On a block in a post addressed to the owner, somebody else may not
answer, move answers or write own words there -- they propose instead
(`interpret`) -- when the caller says who the owner is (`owner=`). Only the
person whose words were interpreted replies to an interpretation.

A CONFIRMATION SEES WHAT IT REPLACES. Confirming or changing a proposed field
value names the field's answers it was made against (`replaces`: the heads
the person saw, empty when they saw none). If the field's heads are not
exactly those now, it is refused with the current heads, writing nothing:
nothing is ever replaced that the person did not see.

NOTHING FROM OUTSIDE `mentis.conversation` IS IMPORTED, as in `anchors`.
"""

from __future__ import annotations

from . import graphemes, render_check
from .anchors import included_in, keyed
from .versions import (Refused, deletion_of, inert_refusal, is_node,
                       lineage, supersedes_relation)

RESPONSE_SET = "response-set"
ANSWER = "answer"
MARKED_READY = "marked-ready"
OWN_WORDS = "own-words"
INTERPRETATION = "interpretation"
INTERPRETATION_REPLY = "interpretation-reply"
#: Written by `mentis.conversation.timers`, into a set this module opens.
TIMER_MARK = "timer-mark"
#: The Kinds kept in response sets; never knowledge, never generically written.
KINDS = (RESPONSE_SET, ANSWER, MARKED_READY, OWN_WORDS, INTERPRETATION,
         INTERPRETATION_REPLY, TIMER_MARK)
RESPONDS_TO = "responds-to"
IN_RESPONSE_SET = "in-response-set"
SHOWN_IN = "shown-in"
CONTRIBUTION = "contribution"
CONVERSATION = "conversation"
MODES = ("shared", "each")
#: What an interpretation may propose.
PROPOSALS = ("set-field", "add-row", "add-field")
#: What the person whose words they are may do with one, once.
OUTCOMES = ("confirmed", "changed", "declined")
UNITS = ("codepoint", "utf16")
#: What a recorded answer says when nothing could check it here.
NOT_CHECKED_HERE = "not checked here"


def _kind(e) -> str | None:
    return (e.get("definition") or {}).get("name")


def _one(corpus, eid, kind, what):
    got = corpus.read([eid]) if isinstance(eid, str) and eid else []
    if not got or not is_node(got[0]):
        raise Refused({"error": f"the record holds no such {what}", "ref": eid})
    if _kind(got[0]) != kind:
        raise Refused({"error": f"{eid} is not a {what}", "ref": eid,
                       "kind": _kind(got[0])})
    return got[0]


def _inert(corpus, post):
    refusal = inert_refusal(corpus, post)
    if refusal:
        raise Refused({**refusal, "error": "the post this block is in was "
                       "deleted, so it accepts no new answers; what was "
                       "already answered is kept as history",
                       "source_deleted": True})


# -- the post and its block ---------------------------------------------------

def post_root(corpus, version) -> str:
    """The Turn a version is a version of: its root."""
    return corpus.history(version)[0]


def current_version(corpus, root) -> dict:
    """The Turn's current version entry (its root when never edited)."""
    return lineage(corpus, root)["current"] or corpus.read([root])[0]


def part_text(version, part) -> str | None:
    parts = (version.get("body") or {}).get("parts") or []
    if not isinstance(part, int) or isinstance(part, bool) \
            or not 0 <= part < len(parts):
        return None
    p = parts[part]
    return p.get("text") if isinstance(p, dict) and p.get("type") == "text" \
        else None


def _block_check(corpus, root, part, block, values):
    """The fill rules for these values, against the post's current version.
    (check, version id). Refuses a part that is not text."""
    ver = current_version(corpus, root)
    text = part_text(ver, part)
    if text is None:
        raise Refused({"error": "that post has no such text part",
                       "post": root, "part": part})
    return render_check.answers(text, block, values), ver["id"]


def _refuse_unsaveable(check, block):
    """Refuse what can never be an answer; pass a 'not checked here'.

    FAIL CLOSED. The one check that may be skipped is the one this platform
    cannot run: the engine is absent (`engine_absent`, owner choice R5), and
    the answer is recorded 'not checked here'. Any other check that did not
    run -- no bundle, a stale bundle, a time or memory limit -- refuses, with
    the reason, so nothing is ever recorded unchecked that could have been
    checked."""
    if not check.get("checked"):
        if check.get("engine_absent"):
            return
        raise Refused({"error": "these values were not saved: they could not "
                                "be checked against the block's rules, and an "
                                "answer is saved only once it is checked. "
                                + str(check.get("why_not") or "no reason was "
                                      "given"),
                       "block": block, "why_not": check.get("why_not"),
                       **({"stale_bundle": True}
                          if check.get("stale_bundle") else {})})
    if not check["found"]:
        raise Refused({"error": f"no block in this post says name={block}",
                       "block": block})
    if not check["saveable"]:
        raise Refused({"error": "what is filled in this block cannot be "
                                "saved: " + "; ".join(check["why"]),
                       "block": block, "why": check["why"]})
    if check["refused"]:
        raise Refused({"error": "; ".join(r["msg"] for r in check["refused"]),
                       "block": block, "refused": check["refused"]})


def _addressed_to(entry) -> list:
    return list((entry.get("body") or {}).get("addressed_to") or [])


# -- response sets ------------------------------------------------------------

def sets_on(cv, post) -> list[dict]:
    """Every response set on this post (its root), oldest first."""
    corpus = cv.corpus
    root = post_root(corpus, post)
    ids = [x["link"]["from"] for x in corpus.links(relation=RESPONDS_TO, to=root)]
    return [e for e in corpus.read(ids) if _kind(e) == RESPONSE_SET]


def open_set(cv, post, *, block, part=0, mode="shared", by, holder=None,
             written_by=None, op=None, act_kw=None) -> dict:
    """Find or open the response set for this block. Idempotent per (post
    root, part, block, mode, holder). Refused on a deleted post, and for a
    block that cannot be saved.

    `holder`, for an `each` set, is whose own set it is: `by` unless it is
    named. Only `timers.mark` names somebody else -- the owner, for a mark an
    agent writes on the owner's direction, which it has checked first -- and
    the set is then opened under `by`, who opened it, for `holder`."""
    corpus = cv.corpus
    _one(corpus, by, "participant", "participant")
    if mode not in MODES:
        raise Refused({"error": "a response set's mode is 'shared' or 'each'",
                       "mode": mode})
    if not isinstance(block, str) or not block:
        raise Refused({"error": "a response set names its block by name="})
    _one(corpus, post, CONTRIBUTION, "Turn")
    root = post_root(corpus, post)
    holder = (holder or by) if mode == "each" else None
    if holder != by and holder is not None:
        _one(corpus, holder, "participant", "participant")
    asked = {"route": "response-set", "post": root, "part": part,
             "block": block, "mode": mode,
             **({"holder": holder} if holder not in (None, by) else {})}

    def write():
        _inert(corpus, root)
        for s in sets_on(cv, root):
            b = s["body"]
            # A set started from another (`start_new`) is a deliberate second
            # one, never what opening the block finds.
            if (b.get("part"), b.get("block"), b.get("mode"), b.get("holder")) \
                    == (part, block, mode, holder) and not b.get("started_from"):
                return {"set": s["id"], "created": False, "post": root}
        check, version = _block_check(corpus, root, part, block, {})
        _refuse_unsaveable(check, block)
        conv = cv.conversation_of(root)
        sid = corpus.write(kind=RESPONSE_SET, body={
            "post": root, "version": version, "part": part, "block": block,
            "type": check.get("type") if check.get("checked") else None,
            "mode": mode, "holder": holder},
            attributed_to=by, written_by=written_by)
        corpus.write(body={"reason": "responds to this post"},
                     attributed_to=by, written_by=written_by,
                     link={"from": sid, "to": root, "relation": RESPONDS_TO})
        cv.record_act(actor=by, act="response-set-opened", conversation=conv,
                      turn=root, about=[sid, root],
                      detail={"block": block, "part": part, "mode": mode},
                      **(act_kw or {}))
        return {"set": sid, "created": True, "post": root}

    with corpus.atomic():
        return keyed(cv, by, op, asked, write, act_kw=act_kw)


def _set(corpus, sid) -> dict:
    return _one(corpus, sid, RESPONSE_SET, "response set")


def _members(corpus, sid, kind) -> list[dict]:
    ids = [x["link"]["from"] for x in corpus.links(relation=IN_RESPONSE_SET, to=sid)]
    got = [e for e in corpus.read(ids) if _kind(e) == kind]
    order = {eid: i for i, eid in enumerate(ids)}
    return sorted(got, key=lambda e: (e["recorded_at"], order.get(e["id"], 0)))


def answers_in(cv, sid) -> list[dict]:
    """Every answer in the set, oldest first."""
    return _members(cv.corpus, sid, ANSWER)


def heads(answers) -> dict[str, list[dict]]:
    """Per field, the answers no other answer in the set replaces. More than
    one is a conflict, kept, not resolved."""
    replaced = {r for a in answers for r in (a["body"].get("replaces") or [])}
    out: dict[str, list[dict]] = {}
    for a in answers:
        if a["id"] not in replaced:
            out.setdefault(a["body"]["field"], []).append(a)
    return out


# -- answers ------------------------------------------------------------------

def _where(cv, sid, root, conversation) -> str | None:
    """The Conversation something is given in: the post's home unless named,
    and a named one only where this set is shown (`show`)."""
    home = cv.conversation_of(root)
    if conversation is None or conversation == home:
        return home
    if conversation not in shown_in(cv, sid):
        raise Refused({"error": "this set is not shown in that Conversation, "
                                "so nothing is given in it there; show it "
                                "there first", "conversation": conversation,
                       "home": home})
    return conversation


def _only_owner_here(corpus, root, by, owner, what):
    """F3: on a post addressed to the owner, only the owner gives `what`."""
    post = corpus.read([root])[0]
    if owner and by != owner and owner in _addressed_to(post):
        raise Refused({"error": f"this block is in a post addressed to the "
                                f"owner, so only the owner {what}; anybody "
                                f"else may propose instead",
                       "owner": owner, "may": "propose"})


def answer(cv, sid, *, field, value, replaces=(), note=None, by,
           owner=None, conversation=None, written_by=None, op=None,
           act_kw=None) -> dict:
    """Record one field's value in the set. See the module docstring for what
    is refused and what is recorded with its problems. `conversation` is
    where it was given: the post's home unless the set is shown elsewhere."""
    corpus = cv.corpus
    _one(corpus, by, "participant", "participant")
    s = _set(corpus, sid)
    sb = s["body"]
    root = sb["post"]
    if isinstance(replaces, str):
        replaces = [replaces]
    replaces = list(replaces or [])
    asked = {"route": "answer", "set": sid, "field": field, "value": value,
             "replaces": replaces, "note": note, "conversation": conversation}

    def write():
        _inert(corpus, root)
        if not isinstance(field, str) or not field:
            raise Refused({"error": "an answer names the field it answers"})
        if sb.get("mode") == "each" and sb.get("holder") != by:
            raise Refused({"error": "this response set is its holder's own; "
                                    "only they answer in it",
                           "holder": sb.get("holder")})
        _only_owner_here(corpus, root, by, owner, "answers it")
        given_in = _where(cv, sid, root, conversation)
        mine = {a["id"]: a for a in answers_in(cv, sid)}
        for r in replaces:
            old = mine.get(r)
            if old is None:
                raise Refused({"error": "an answer replaces only answers in "
                                        "the same response set", "replaces": r})
            if old["body"]["field"] != field:
                raise Refused({"error": "an answer replaces only answers to the "
                                        "same field", "replaces": r,
                               "field": old["body"]["field"]})
        check, version = _block_check(corpus, root, sb.get("part", 0),
                                      sb["block"], {field: value})
        _refuse_unsaveable(check, sb["block"])
        conv = given_in
        aid = corpus.write(kind=ANSWER, body={
            "set": sid, "field": field, "value": value,
            "note": note if isinstance(note, str) and note.strip() else None,
            "replaces": replaces, "version": version,
            "check": _recorded_check(check, field), "conversation": given_in},
            attributed_to=by, written_by=written_by)
        corpus.write(body={"reason": "answers in this set"}, attributed_to=by,
                     written_by=written_by,
                     link={"from": aid, "to": sid, "relation": IN_RESPONSE_SET})
        sup = supersedes_relation(corpus)
        for r in replaces:
            corpus.write(body={"reason": "a later answer to the same field"},
                         attributed_to=by, written_by=written_by,
                         link={"from": aid, "to": r, "relation": sup})
        cv.record_act(actor=by, act="answer-recorded", conversation=conv,
                      turn=root, about=[aid, sid, *replaces],
                      detail={"field": field, "set": sid}, **(act_kw or {}))
        others = [h["id"] for h in heads(answers_in(cv, sid)).get(field, [])
                  if h["id"] != aid]
        kept = _recorded_check(check, field)
        return {"answer": aid, "set": sid, "field": field,
                "checked": kept["checked"],
                **({"problems": kept["problems"]} if kept["checked"]
                   else {"says": NOT_CHECKED_HERE, "why_not": kept["why_not"]}),
                **({"conflict": sorted([aid, *others])} if others else {})}

    with corpus.atomic():
        return keyed(cv, by, op, asked, write, act_kw=act_kw)


def _recorded_check(check, field) -> dict:
    """What is kept on the answer about its check: the field's own problems,
    or that nothing checked it here, and why."""
    if not check.get("checked"):
        return {"checked": False, "says": NOT_CHECKED_HERE,
                "why_not": check.get("why_not")}
    return {"checked": True,
            "problems": [p["msg"] for p in check["problems"]
                         if p["field"] == field],
            "renderer": (check.get("renderer") or {}).get("sha256")}


# -- marked ready -------------------------------------------------------------

def mark_ready(cv, sid, *, by, seen=None, written_by=None, op=None,
               act_kw=None) -> dict:
    """Done: the input is finished, as it now stands. Names the exact answers
    it covers. Refused while a field is in conflict, and -- when `seen` (the
    answer ids the person was looking at) is given -- when the set has changed
    since."""
    corpus = cv.corpus
    _one(corpus, by, "participant", "participant")
    s = _set(corpus, sid)
    root = s["body"]["post"]
    asked = {"route": "marked-ready", "set": sid,
             "seen": sorted(seen) if seen is not None else None}

    def write():
        _inert(corpus, root)
        if s["body"].get("mode") == "each" and s["body"].get("holder") != by:
            raise Refused({"error": "this response set is its holder's own; "
                                    "only they mark it ready"})
        h = heads(answers_in(cv, sid))
        torn = sorted(f for f, xs in h.items() if len(xs) > 1)
        if torn:
            raise Refused({"error": "these fields have two answers in conflict; "
                                    "answer them again first: " + ", ".join(torn),
                           "conflicts": torn})
        covers = sorted(xs[0]["id"] for xs in h.values())
        if seen is not None and sorted(seen) != covers:
            raise Refused({"error": "the answers changed since you looked; "
                                    "nothing was marked ready",
                           "current": covers})
        conv = cv.conversation_of(root)
        mid = corpus.write(kind=MARKED_READY, body={"set": sid, "answers": covers},
                           attributed_to=by, written_by=written_by)
        corpus.write(body={"reason": "marked ready"}, attributed_to=by,
                     written_by=written_by,
                     link={"from": mid, "to": sid, "relation": IN_RESPONSE_SET})
        cv.record_act(actor=by, act="marked-ready", conversation=conv,
                      turn=root, about=[mid, sid, *covers], **(act_kw or {}))
        return {"marked_ready": mid, "set": sid, "answers": covers}

    with corpus.atomic():
        return keyed(cv, by, op, asked, write, act_kw=act_kw)


# -- reading ------------------------------------------------------------------

def _row(cv, a) -> dict:
    b = a["body"]
    return {"answer": a["id"], "field": b["field"], "value": b["value"],
            "note": b.get("note"), "replaces": list(b.get("replaces") or []),
            "version": b.get("version"), "by": a["attributed_to"],
            "by_alias": cv.alias(a["attributed_to"]), "at": a["recorded_at"],
            "check": b.get("check"),
            "conversation": b.get("conversation")}


def state(cv, sid) -> dict:
    """The set as it stands, computed from its entries. Nothing here is stored."""
    corpus = cv.corpus
    s = _set(corpus, sid)
    sb = s["body"]
    root = sb["post"]
    gone = deletion_of(corpus, root)
    every = answers_in(cv, sid)
    h = heads(every)
    fields = {}
    current_values = {}
    for f, xs in h.items():
        rows = [_row(cv, a) for a in xs]
        fields[f] = {"value": rows[0]["value"] if len(rows) == 1 else None,
                     "answer": rows[0]["answer"] if len(rows) == 1 else None,
                     "heads": rows, "conflict": len(rows) > 1}
        if len(rows) == 1:
            current_values[f] = rows[0]["value"]
    readies = _members(corpus, sid, MARKED_READY)
    last = readies[-1] if readies else None
    covers = sorted(xs[0]["id"] for xs in h.values() if len(xs) == 1)
    out = {"set": sid, "post": root, "part": sb.get("part"),
           "block": sb["block"], "type": sb.get("type"), "mode": sb.get("mode"),
           "holder": sb.get("holder"), "fields": fields,
           "conflicts": sorted(f for f, v in fields.items() if v["conflict"]),
           "answers": len(every),
           "ready": bool(last) and sorted(last["body"]["answers"]) == covers
           and not any(v["conflict"] for v in fields.values()),
           "marked_ready": ({"entry": last["id"], "by": last["attributed_to"],
                             "at": last["recorded_at"],
                             "answers": last["body"]["answers"]}
                            if last else None),
           "source_deleted": ({"record": gone["id"], "at": gone["recorded_at"],
                               "by": gone["attributed_to"]} if gone else None)}
    out["changed_since_ready"] = bool(last) and not out["ready"]
    out["started_from"] = sb.get("started_from")
    out["shown_in"] = shown_in(cv, sid)
    if gone:
        # F5: kept as history, checked against nothing now.
        out.update(checked=False, why_not="the source post was deleted",
                   valid=None, missing=None, problems=None)
        return _with_words(cv, sid, out, None)
    check, version = _block_check(corpus, root, sb.get("part", 0), sb["block"],
                                  current_values)
    out["version"] = version
    for v in fields.values():
        for r in v["heads"]:
            r["earlier_version"] = r["version"] != version
    if not check.get("checked"):
        out.update(checked=False, why_not=check.get("why_not"), valid=None,
                   missing=None, problems=None)
        return _with_words(cv, sid, out, None)
    out.update(checked=True, valid=check["valid"] and not out["conflicts"],
               missing=check["missing"], problems=check["problems"],
               refused=check["refused"], not_asked=check["not_asked"],
               saveable=check["saveable"], why=check["why"])
    return _with_words(cv, sid, out,
                       {f["id"]: f for f in check["fields"]}
                       if check["found"] else {})


def _with_words(cv, sid, out, now) -> dict:
    """The set's own words and interpretations, beside its answers. `now` is
    the block's fields at the current version, or None when unread."""
    out["own_words"] = [_words_row(cv, w) for w in words_heads(cv, sid)]
    out["proposals"] = [interpretation_view(cv, i, now)
                        for i in interpretations_in(cv, sid)]
    out["pending"] = sum(1 for p in out["proposals"]
                         if p["status"] == "pending")
    return out


def field_history(cv, sid, field) -> list[dict]:
    """Every answer ever given to one field, oldest first, conflicts and all.
    Read for a deleted source too."""
    _set(cv.corpus, sid)
    return [_row(cv, a) for a in answers_in(cv, sid) if a["body"]["field"] == field]


def conflicts(cv, sid) -> dict[str, list[str]]:
    """{field: [answer ids in conflict]} for every field with more than one head."""
    return {f: [a["id"] for a in xs] for f, xs in heads(answers_in(cv, sid)).items()
            if len(xs) > 1}


# -- moving answers to the current version (F2) -------------------------------

def _fields_at(corpus, version_id, part, block) -> dict | None:
    """{field id: kind} of the block in that version, or None unchecked."""
    got = corpus.read([version_id])
    text = part_text(got[0], part) if got else None
    if text is None:
        return {}
    check = render_check.answers(text, block, {})
    if not check.get("checked"):
        return None
    return {f["id"]: f["kind"] for f in check["fields"]} if check["found"] else {}


def move(cv, sid, *, by, confirm=False, owner=None, written_by=None, op=None,
         act_kw=None) -> dict:
    """Carry answers on earlier versions to the current one. One step only
    when every field each earlier version declared -- answered or not -- is
    still declared with the same id and kind; any removed, retyped or renamed
    field makes it a preview (`moved: False`) until `confirm`, which moves
    only the answers whose field still matches. On a post addressed to the
    owner only the owner moves answers (F3, as for `answer`)."""
    corpus = cv.corpus
    _one(corpus, by, "participant", "participant")
    s = _set(corpus, sid)
    sb = s["body"]
    root = sb["post"]

    def write():
        _inert(corpus, root)
        _only_owner_here(corpus, root, by, owner, "moves its answers")
        now = current_version(corpus, root)["id"]
        old = [xs[0] for xs in heads(answers_in(cv, sid)).values()
               if len(xs) == 1 and xs[0]["body"].get("version") != now]
        cur = _fields_at(corpus, now, sb.get("part", 0), sb["block"])
        if cur is None:
            raise Refused({"error": "the fields could not be read here (the "
                                    "render engine is not installed), so "
                                    "nothing is moved"})
        plan, earlier = [], {}
        for a in old:
            v = a["body"]["version"]
            if v not in earlier:
                earlier[v] = _fields_at(corpus, v, sb.get("part", 0),
                                        sb["block"])
            was = earlier[v] or {}
            f = a["body"]["field"]
            plan.append({"answer": a["id"], "field": f,
                         "matches": f in cur and was.get(f) == cur.get(f)})
        # Every field the earlier versions declared, not only the answered
        # ones: a field gone, retyped or renamed is shown before it moves.
        kept = all(was is not None and all(cur.get(f) == k
                                           for f, k in was.items())
                   for was in earlier.values())
        clean = kept and all(p["matches"] for p in plan)
        if not plan or (not clean and not confirm):
            return {"set": sid, "moved": False, "version": now, "plan": plan,
                    "one_step": clean}
        moved = []
        for p in plan:
            if not p["matches"]:
                continue
            a = next(x for x in old if x["id"] == p["answer"])
            # Not keyed one by one: the move as a whole is (below), so a
            # retried move replays what it first came to.
            got = answer(cv, sid, field=p["field"], value=a["body"]["value"],
                         replaces=[a["id"]], note=a["body"].get("note"), by=by,
                         owner=owner, conversation=a["body"].get("conversation"),
                         written_by=written_by, act_kw=act_kw)
            moved.append(got["answer"])
        return {"set": sid, "moved": True, "version": now, "plan": plan,
                "one_step": clean, "answers": moved}

    with corpus.atomic():
        return keyed(cv, by, op, {"route": "move", "set": sid,
                                  "confirm": bool(confirm)}, write,
                     act_kw=act_kw)


# -- own words (F1) -----------------------------------------------------------

def own_words_in(cv, sid) -> list[dict]:
    """Every version of every own words in the set, oldest first."""
    return _members(cv.corpus, sid, OWN_WORDS)


def words_heads(cv, sid) -> list[dict]:
    """The own words no later version replaces, oldest first: what each
    person's words now read. Two versions replacing the same one are both
    kept, as with answers."""
    every = own_words_in(cv, sid)
    replaced = {r for w in every for r in (w["body"].get("replaces") or [])}
    return [w for w in every if w["id"] not in replaced]


def _words_row(cv, w) -> dict:
    b = w["body"]
    return {"words": w["id"], "text": b["text"],
            "replaces": list(b.get("replaces") or []),
            "conversation": b.get("conversation"), "by": w["attributed_to"],
            "by_alias": cv.alias(w["attributed_to"]), "at": w["recorded_at"]}


def write_words(cv, sid, *, text, replaces=(), by, owner=None,
                conversation=None, written_by=None, op=None,
                act_kw=None) -> dict:
    """Keep somebody's own words in the set exactly as written. A new
    version names what it `replaces`: their own earlier words in this set,
    which stay as they were."""
    corpus = cv.corpus
    _one(corpus, by, "participant", "participant")
    s = _set(corpus, sid)
    sb = s["body"]
    root = sb["post"]
    if isinstance(replaces, str):
        replaces = [replaces]
    replaces = list(replaces or [])
    asked = {"route": "own-words", "set": sid, "text": text,
             "replaces": replaces, "conversation": conversation}

    def write():
        _inert(corpus, root)
        if not isinstance(text, str) or not text.strip():
            raise Refused({"error": "own words are some words: the text is "
                                    "empty, so nothing was kept"})
        if sb.get("mode") == "each" and sb.get("holder") != by:
            raise Refused({"error": "this response set is its holder's own; "
                                    "only they write in it",
                           "holder": sb.get("holder")})
        _only_owner_here(corpus, root, by, owner, "writes own words in it")
        given_in = _where(cv, sid, root, conversation)
        mine = {w["id"]: w for w in own_words_in(cv, sid)}
        for r in replaces:
            old = mine.get(r)
            if old is None:
                raise Refused({"error": "own words replace only own words in "
                                        "the same response set",
                               "replaces": r})
            if old["attributed_to"] != by:
                raise Refused({"error": "these are somebody else's words; "
                                        "nobody replaces another person's "
                                        "words, so write your own beside them",
                               "replaces": r, "by": old["attributed_to"]})
        wid = corpus.write(kind=OWN_WORDS, body={
            "set": sid, "text": text, "replaces": replaces,
            "conversation": given_in},
            attributed_to=by, written_by=written_by)
        corpus.write(body={"reason": "own words in this set"},
                     attributed_to=by, written_by=written_by,
                     link={"from": wid, "to": sid, "relation": IN_RESPONSE_SET})
        sup = supersedes_relation(corpus)
        for r in replaces:
            corpus.write(body={"reason": "a later version of the same words"},
                         attributed_to=by, written_by=written_by,
                         link={"from": wid, "to": r, "relation": sup})
        cv.record_act(actor=by, act="own-words-recorded", conversation=given_in,
                      turn=root, about=[wid, sid, *replaces],
                      detail={"set": sid}, **(act_kw or {}))
        return {"words": wid, "set": sid, "replaces": replaces}

    with corpus.atomic():
        return keyed(cv, by, op, asked, write, act_kw=act_kw)


def words_history(cv, sid, *, by=None) -> list[dict]:
    """Every version of the own words in the set, oldest first; one
    person's when `by` is named."""
    _set(cv.corpus, sid)
    return [_words_row(cv, w) for w in own_words_in(cv, sid)
            if by is None or w["attributed_to"] == by]


# -- interpretations (F1) -----------------------------------------------------

def _passage(text, passage) -> dict:
    """The cited passage as stored -- code points, on grapheme boundaries,
    matching the excerpt the proposer saw -- or a refusal."""
    if not isinstance(passage, dict):
        raise Refused({"error": "an interpretation cites the passage it came "
                                "from: {start, end, unit, expected_excerpt}"})
    start, end = passage.get("start"), passage.get("end")
    unit = passage.get("unit", "codepoint")
    if not all(isinstance(x, int) and not isinstance(x, bool)
               for x in (start, end)):
        raise Refused({"error": "a passage's start and end are integers"})
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
        raise Refused({"error": "the passage is not inside these words (a "
                                "passage is non-empty)", "start": start,
                       "end": end, "length": len(text)})
    try:
        edges = graphemes.boundaries(text)
    except graphemes.Unavailable as exc:
        raise Refused({"error": str(exc)})
    for edge in (start, end):
        if edge not in edges:
            raise Refused({"error": "the passage edge splits a user-perceived "
                                    "character", "at": edge})
    if passage.get("expected_excerpt") != text[start:end]:
        raise Refused({"error": "the excerpt you saw does not match these "
                                "words at that passage; nothing was proposed",
                       "expected": passage.get("expected_excerpt")})
    return {"start": start, "end": end, "unit": "codepoint"}


def _fields_now(corpus, root, part, block) -> dict | None:
    """{field id: declaration} at the post's current version; None unread."""
    check, _ = _block_check(corpus, root, part, block, {})
    if not check.get("checked"):
        return None
    return {f["id"]: f for f in check["fields"]} if check["found"] else {}


def _proposal(corpus, sb, root, proposes) -> tuple[dict, dict | None, dict]:
    """(what is proposed, as kept; the field's declaration it maps to, for a
    field value; the check of a proposed value). Refuses what could never be
    confirmed."""
    if not isinstance(proposes, dict) or proposes.get("type") not in PROPOSALS:
        raise Refused({"error": "an interpretation proposes one of: "
                                + ", ".join(PROPOSALS), "proposes": proposes})
    typ = proposes["type"]
    part = sb.get("part", 0)
    if typ == "set-field":
        field = proposes.get("field")
        if not isinstance(field, str) or not field or "value" not in proposes:
            raise Refused({"error": "a proposed answer names its field and "
                                    "its value"})
        check, _ = _block_check(corpus, root, part, sb["block"],
                                {field: proposes["value"]})
        _refuse_unsaveable(check, sb["block"])
        mapped = (next((f for f in check["fields"] if f["id"] == field), None)
                  if check.get("checked") else None)
        return ({"type": typ, "field": field, "value": proposes["value"]},
                mapped, _recorded_check(check, field))
    if typ == "add-row":
        row = proposes.get("row")
        if not isinstance(row, dict) or not row or not all(
                isinstance(k, str) and k and isinstance(v, str)
                for k, v in row.items()):
            raise Refused({"error": "a proposed row is an object of column "
                                    "names to text, with at least one"})
        return {"type": typ, "row": dict(row)}, None, {}
    spec = proposes.get("field")
    if not isinstance(spec, dict) or not isinstance(spec.get("id"), str) \
            or not spec["id"].strip() or not isinstance(spec.get("kind"), str) \
            or not spec["kind"].strip():
        raise Refused({"error": "a proposed field says at least its id and "
                                "its kind: {id, kind, label?}"})
    now = _fields_now(corpus, root, part, sb["block"])
    if now and spec["id"] in now:
        raise Refused({"error": "the form already has a field with that id",
                       "field": spec["id"]})
    return {"type": typ, "field": dict(spec)}, None, {}


def interpretations_in(cv, sid) -> list[dict]:
    return _members(cv.corpus, sid, INTERPRETATION)


def replies_in(cv, sid) -> dict[str, dict]:
    """{interpretation id: its reply}: the first, which is the only one."""
    out: dict[str, dict] = {}
    for r in _members(cv.corpus, sid, INTERPRETATION_REPLY):
        out.setdefault(r["body"]["interpretation"], r)
    return out


def interpret(cv, sid, *, words, passage, proposes, by, written_by=None,
              op=None, act_kw=None) -> dict:
    """Propose what a passage of somebody's own words means for the form,
    under the proposer's name. Unconfirmed until that person replies."""
    corpus = cv.corpus
    _one(corpus, by, "participant", "participant")
    s = _set(corpus, sid)
    sb = s["body"]
    root = sb["post"]
    asked = {"route": "interpretation", "set": sid, "words": words,
             "passage": passage, "proposes": proposes}

    def write():
        _inert(corpus, root)
        w = _one(corpus, words, OWN_WORDS, "own words")
        if w["body"].get("set") != sid:
            raise Refused({"error": "those own words are in another response "
                                    "set", "words": words})
        if w["attributed_to"] == by:
            raise Refused({"error": "these are your own words: an "
                                    "interpretation is somebody else's reading "
                                    "of them, for you to confirm. Answer the "
                                    "field yourself instead"})
        cited = _passage(w["body"]["text"], passage)
        kept, mapped, check = _proposal(corpus, sb, root, proposes)
        version = current_version(corpus, root)["id"]
        iid = corpus.write(kind=INTERPRETATION, body={
            "set": sid, "words": words, "passage": cited, "proposes": kept,
            "version": version, "mapped": mapped,
            **({"check": check} if check else {})},
            attributed_to=by, written_by=written_by)
        corpus.write(body={"reason": "an interpretation in this set"},
                     attributed_to=by, written_by=written_by,
                     link={"from": iid, "to": sid, "relation": IN_RESPONSE_SET})
        cv.record_act(actor=by, act="interpretation-proposed",
                      conversation=cv.conversation_of(root), turn=root,
                      about=[iid, sid, words],
                      detail={"set": sid, "proposes": kept["type"],
                              "for": w["attributed_to"]}, **(act_kw or {}))
        out = {"interpretation": iid, "set": sid, "words": words,
               "excerpt": w["body"]["text"][cited["start"]:cited["end"]],
               "for": w["attributed_to"], "version": version}
        if check:
            out["checked"] = check["checked"]
            out.update({"problems": check["problems"]} if check["checked"]
                       else {"says": NOT_CHECKED_HERE})
        return out

    with corpus.atomic():
        return keyed(cv, by, op, asked, write, act_kw=act_kw)


def _out_of_date(i, now) -> tuple[bool | None, str | None]:
    """Is what this interpretation read still there to apply? Computed from
    the block's fields now (`now`; None when unread)."""
    p = i["body"]["proposes"]
    if now is None:
        return None, None
    if p["type"] == "set-field":
        f = now.get(p["field"])
        if f is None:
            return True, "the form no longer has this field"
        if i["body"].get("mapped") is not None and f != i["body"]["mapped"]:
            return True, "this field changed after it was read"
        return False, None
    if p["type"] == "add-field" and p["field"]["id"] in now:
        return True, "the form has this field now"
    return False, None


def interpretation_view(cv, i, now, replies=None) -> dict:
    """One interpretation as it stands: its passage read from the words,
    pending or what its reply said, and whether it is out of date."""
    corpus = cv.corpus
    b = i["body"]
    w = corpus.read([b["words"]])
    text = w[0]["body"]["text"] if w else ""
    cited = b["passage"]
    r = (replies if replies is not None
         else replies_in(cv, b["set"])).get(i["id"])
    stale, why = _out_of_date(i, now)
    return {"interpretation": i["id"], "by": i["attributed_to"],
            "by_alias": cv.alias(i["attributed_to"]), "at": i["recorded_at"],
            "words": b["words"],
            "for": w[0]["attributed_to"] if w else None,
            "passage": cited, "excerpt": text[cited["start"]:cited["end"]],
            "proposes": b["proposes"], "version": b.get("version"),
            "check": b.get("check"),
            "status": r["body"]["outcome"] if r else "pending",
            "reply": ({"reply": r["id"], "by": r["attributed_to"],
                       "at": r["recorded_at"], "answer": r["body"].get("answer"),
                       "changed_to": r["body"].get("changed_to"),
                       "reason": r["body"].get("reason")} if r else None),
            "out_of_date": stale, "why_out_of_date": why,
            "state": ("out of date" if not r and stale
                      else r["body"]["outcome"] if r else "pending")}


def handover(cv, sid) -> dict:
    """What an agent is handed besides the answers: the own words as they now
    read and every interpretation in the set with its state, each by its exact
    entry, and the passages no interpretation has cited. Read now, so a
    caller that records it records the revision it handed over."""
    acc = accounting(cv, sid)
    words = [{k: w[k] for k in ("words", "text", "by", "by_alias", "at",
                                "replaces", "not_cited")}
             for w in acc["words"]]
    current = {w["words"] for w in words}
    sb = _set(cv.corpus, sid)["body"]
    now = (None if deletion_of(cv.corpus, sb["post"]) else
           _fields_now(cv.corpus, sb["post"], sb.get("part", 0), sb["block"]))
    replies = replies_in(cv, sid)
    proposals = []
    for i in interpretations_in(cv, sid):
        v = interpretation_view(cv, i, now, replies)
        r = v["reply"] or {}
        proposals.append({k: v[k] for k in ("interpretation", "words", "by",
                                            "by_alias", "excerpt", "proposes",
                                            "state")}
                         | {"reply": r.get("reply"), "answer": r.get("answer"),
                            "changed_to": r.get("changed_to"),
                            "on_earlier_wording": v["words"] not in current})
    return {"set": sid, "words": words, "proposals": proposals}


def handed(given) -> dict:
    """The exact revisions a `handover` handed, as an act keeps them: the own
    words' entries, and each interpretation with its state then."""
    return {"words": [w["words"] for w in given["words"]],
            "proposals": [{k: p[k] for k in ("interpretation", "state",
                                             "reply", "answer")}
                          for p in given["proposals"]]}


def reply(cv, iid, *, outcome, by, value=None, changed_to=None,
          replaces=None, reason=None, owner=None, written_by=None, op=None,
          act_kw=None) -> dict:
    """Confirm, change or decline an interpretation, once, as the person whose
    words it read. Confirming or changing a field value writes their answer
    (`answer`), replacing `replaces`: the field's answers the person saw
    (absent means they saw none). Refused with the current heads when those
    are not exactly what is there now, so it never replaces an answer it did
    not see; the reply's act records them (`against`), and the
    answer replaces exactly them. `value` is the changed
    value. For a row or a field, `changed_to` is the changed proposal."""
    corpus = cv.corpus
    _one(corpus, by, "participant", "participant")
    i = _one(corpus, iid, INTERPRETATION, "interpretation")
    ib = i["body"]
    sid = ib["set"]
    s = _set(corpus, sid)
    root = s["body"]["post"]
    if isinstance(replaces, str):
        replaces = [replaces]
    asked = {"route": "interpretation-reply", "interpretation": iid,
             "outcome": outcome, "value": value, "changed_to": changed_to,
             "replaces": None if replaces is None else list(replaces),
             "reason": reason}

    def write():
        _inert(corpus, root)
        if outcome not in OUTCOMES:
            raise Refused({"error": "an interpretation is confirmed, changed "
                                    "or declined", "outcome": outcome})
        whose = corpus.read([ib["words"]])[0]["attributed_to"]
        if by != whose:
            raise Refused({"error": "only the person whose words these are "
                                    "confirms, changes or declines what was "
                                    "read into them", "for": whose})
        earlier = replies_in(cv, sid).get(iid)
        if earlier is not None:
            raise Refused({"error": "this interpretation was already "
                                    f"{earlier['body']['outcome']}; ask for it "
                                    "to be read again instead",
                           "reply": earlier["id"],
                           "outcome": earlier["body"]["outcome"]})
        p = ib["proposes"]
        against = None
        body = {"set": sid, "interpretation": iid, "outcome": outcome,
                "answer": None, "changed_to": None,
                "reason": reason if isinstance(reason, str) and reason.strip()
                else None}
        if outcome != "declined":
            stale, why = _out_of_date(i, _fields_now(
                corpus, root, s["body"].get("part", 0), s["body"]["block"]))
            if stale:
                raise Refused({"error": f"{why}, so this interpretation is out "
                                        "of date: decline it, or ask for your "
                                        "words to be read again",
                               "out_of_date": True})
            if p["type"] == "set-field":
                if outcome == "changed" and value is None:
                    raise Refused({"error": "a changed answer says its value"})
                given = p["value"] if outcome == "confirmed" else value
                seen = sorted(replaces or [])
                now = sorted(h["id"] for h in
                             heads(answers_in(cv, sid)).get(p["field"], []))
                if seen != now:
                    raise Refused({"error": "this field's answers changed since "
                                            "you looked, so nothing was "
                                            "confirmed: look again, then "
                                            "confirm naming the answers it "
                                            "replaces", "field": p["field"],
                                   "seen": seen, "current": now})
                got = answer(cv, sid, field=p["field"], value=given,
                             replaces=seen, by=by, owner=owner,
                             note=None, written_by=written_by, act_kw=act_kw)
                body["answer"] = got["answer"]
                against = seen
            elif outcome == "changed":
                if not isinstance(changed_to, dict):
                    raise Refused({"error": "a changed proposal says what it "
                                            "is changed to"})
                kept, _, _ = _proposal(corpus, s["body"], root,
                                       {**changed_to, "type": p["type"]})
                body["changed_to"] = kept
        rid = corpus.write(kind=INTERPRETATION_REPLY, body=body,
                           attributed_to=by, written_by=written_by)
        corpus.write(body={"reason": f"interpretation {outcome}"},
                     attributed_to=by, written_by=written_by,
                     link={"from": rid, "to": sid, "relation": IN_RESPONSE_SET})
        cv.record_act(actor=by, act=f"interpretation-{outcome}",
                      conversation=cv.conversation_of(root), turn=root,
                      about=[rid, iid, sid, *([body["answer"]]
                                              if body["answer"] else [])],
                      detail={"set": sid, "interpretation": iid,
                              **({"against": against}
                                 if against is not None else {})},
                      **(act_kw or {}))
        return {"reply": rid, "interpretation": iid, "outcome": outcome,
                "set": sid, **({"answer": body["answer"]}
                               if body["answer"] else {})}

    with corpus.atomic():
        return keyed(cv, by, op, asked, write, act_kw=act_kw)


def accounting(cv, sid) -> dict:
    """For each person's words as they now read: every passage an
    interpretation cited and what became of it, and the stretches no
    interpretation has cited yet. What an agent accounts for when it goes
    on; computed, never stored."""
    corpus = cv.corpus
    s = _set(corpus, sid)
    root = s["body"]["post"]
    now = (None if deletion_of(corpus, root) else
           _fields_now(corpus, root, s["body"].get("part", 0),
                       s["body"]["block"]))
    replies = replies_in(cv, sid)
    every = interpretations_in(cv, sid)
    out = []
    for w in words_heads(cv, sid):
        text = w["body"]["text"]
        mine = [interpretation_view(cv, i, now, replies) for i in every
                if i["body"]["words"] == w["id"]]
        covered = sorted((v["passage"]["start"], v["passage"]["end"])
                         for v in mine)
        out.append({**_words_row(cv, w), "passages": mine,
                    "not_cited": _gaps(text, covered),
                    "on_earlier_wording": [
                        interpretation_view(cv, i, now, replies) for i in every
                        if i["body"]["words"] in _earlier(cv, sid, w["id"])]})
    return {"set": sid, "words": out}


def _earlier(cv, sid, wid) -> set:
    """Every earlier version a version of own words replaces, transitively."""
    by_id = {w["id"]: w for w in own_words_in(cv, sid)}
    seen, todo = set(), list(by_id.get(wid, {}).get("body", {}).get(
        "replaces") or [])
    while todo:
        x = todo.pop()
        if x in seen:
            continue
        seen.add(x)
        todo.extend(by_id.get(x, {}).get("body", {}).get("replaces") or [])
    return seen


def _gaps(text, covered) -> list[dict]:
    """The stretches of `text` with something other than space in them that
    no cited range covers."""
    out, at = [], 0
    for start, end in covered + [(len(text), len(text))]:
        if start > at and text[at:start].strip():
            out.append({"start": at, "end": start, "excerpt": text[at:start]})
        at = max(at, end)
    return out


# -- using a form elsewhere (revision 2, section 1) ---------------------------

def shown_in(cv, sid) -> list[str]:
    """The Conversations, other than the post's home, this set is shown in."""
    return [x["link"]["to"]
            for x in cv.corpus.links(relation=SHOWN_IN, frm=sid)]


def show(cv, sid, *, conversation, by, written_by=None, op=None,
         act_kw=None) -> dict:
    """Show the same answers in another Conversation the post is in now.
    Showing it again finds it."""
    corpus = cv.corpus
    _one(corpus, by, "participant", "participant")
    s = _set(corpus, sid)
    root = s["body"]["post"]
    asked = {"route": "response-set-shown", "set": sid,
             "conversation": conversation}

    def write():
        _inert(corpus, root)
        _one(corpus, conversation, CONVERSATION, "Conversation")
        home = cv.conversation_of(root)
        if conversation == home:
            return {"set": sid, "conversation": conversation, "home": True,
                    "created": False}
        if conversation in shown_in(cv, sid):
            return {"set": sid, "conversation": conversation, "home": False,
                    "created": False}
        if not included_in(corpus, root, conversation):
            raise Refused({"error": "the post this block is in is not in that "
                                    "Conversation, so its answers cannot be "
                                    "shown there; include the post there "
                                    "first", "conversation": conversation,
                           "post": root})
        corpus.write(body={"reason": "the same answers, shown here"},
                     attributed_to=by, written_by=written_by,
                     link={"from": sid, "to": conversation,
                           "relation": SHOWN_IN})
        cv.record_act(actor=by, act="response-set-shown",
                      conversation=conversation, turn=root,
                      about=[sid, root, conversation],
                      detail={"set": sid}, **(act_kw or {}))
        return {"set": sid, "conversation": conversation, "home": False,
                "created": True}

    with corpus.atomic():
        return keyed(cv, by, op, asked, write, act_kw=act_kw)


def start_new(cv, sid, *, by, copy=(), conversation=None, owner=None,
              written_by=None, op=None, act_kw=None) -> dict:
    """Open a separate set on the same block, `started_from` this one.
    Earlier answers are copied only for the fields in `copy` (or every
    answered field, for `copy=True`), as new answers by `by`."""
    corpus = cv.corpus
    _one(corpus, by, "participant", "participant")
    s = _set(corpus, sid)
    sb = s["body"]
    root = sb["post"]
    asked = {"route": "response-set-started", "set": sid,
             "copy": copy if copy is True else sorted(copy or ()),
             "conversation": conversation}

    def write():
        _inert(corpus, root)
        home = cv.conversation_of(root)
        where = conversation or home
        if where != home and where not in shown_in(cv, sid) \
                and not included_in(corpus, root, where):
            raise Refused({"error": "the post this block is in is not in that "
                                    "Conversation", "conversation": where})
        check, version = _block_check(corpus, root, sb.get("part", 0),
                                      sb["block"], {})
        _refuse_unsaveable(check, sb["block"])
        h = heads(answers_in(cv, sid))
        fields = sorted(h) if copy is True else list(copy or ())
        torn = [f for f in fields if len(h.get(f, [])) > 1]
        if torn:
            raise Refused({"error": "these fields have answers in conflict, so "
                                    "there is no one value to copy: "
                                    + ", ".join(torn), "conflicts": torn})
        missing = [f for f in fields if f not in h]
        if missing:
            raise Refused({"error": "nothing was answered to copy for: "
                                    + ", ".join(missing), "fields": missing})
        new = corpus.write(kind=RESPONSE_SET, body={
            "post": root, "version": version, "part": sb.get("part", 0),
            "block": sb["block"], "type": sb.get("type"),
            "mode": sb.get("mode"),
            "holder": by if sb.get("mode") == "each" else None,
            "started_from": sid, "conversation": where},
            attributed_to=by, written_by=written_by)
        corpus.write(body={"reason": "responds to this post"},
                     attributed_to=by, written_by=written_by,
                     link={"from": new, "to": root, "relation": RESPONDS_TO})
        if where != home and where not in shown_in(cv, new):
            corpus.write(body={"reason": "started here"}, attributed_to=by,
                         written_by=written_by,
                         link={"from": new, "to": where, "relation": SHOWN_IN})
        copied = {}
        for f in fields:
            old = h[f][0]
            got = answer(cv, new, field=f, value=old["body"]["value"],
                         note=old["body"].get("note"), by=by, owner=owner,
                         conversation=where, written_by=written_by,
                         act_kw=act_kw)
            copied[got["answer"]] = old["id"]
        cv.record_act(actor=by, act="response-set-started", conversation=where,
                      turn=root, about=[new, sid, root],
                      detail={"set": new, "from": sid, "copied": copied},
                      **(act_kw or {}))
        return {"set": new, "started_from": sid, "post": root,
                "conversation": where, "copied": copied}

    with corpus.atomic():
        return keyed(cv, by, op, asked, write, act_kw=act_kw)
