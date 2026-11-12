"""Conversation threading, kept beside work lineage and never merged with it.

THREE DIFFERENT THINGS, AND THIS MODULE KEEPS THEM APART (Workstream R,
owner-authorized correction round, 2026-11-12):

  threading      which post a post replies to (`replies-to`). Conversational
                 context: what "this", "it" and "that work" mean.
  work lineage   which request continues, delegates or revises which
                 (`caused_by`, `work-delegated`). Authority and requirements
                 follow it, and nothing here changes it.
  owner decision a choice the owner made on a decision form. Binding.

THE INCIDENT THIS EXISTS FOR. The owner approved a Builder's round-3 delivery
by replying to it. The run that carried the approval was given the approval's
words and the last four posts; nothing said what it replied to, so it took
"this work" to mean the newest delivery in the Conversation and merged and
deployed that. Here the reply target is read from the record -- the post, its
author, its position, its opening words, and the WORK IDENTITY it belongs to:
the requests it answered or recorded (state and latest claim), the delegation
that produced it and the request above that, and what was returned. It is
said as context, never as a decision, and it grants nothing.

EVERYTHING HERE IS A READ OF THE RECORD, computed when asked. The one thing
written is `in_reply_to` on a request recorded from a reply (`in_reply_to`),
additively in the request's own detail -- the thread and the work the reply
target belonged to at that moment. It is not a continuation link and not a
decision.
"""

from __future__ import annotations

import datetime

#: How many requests one post's work identity names, and how far up a
#: delegation it reads. A post answers one request almost always; the bound is
#: what keeps an odd record from making a prompt long.
MOST_REQUESTS = 4
#: How far a lineage walk goes (continuations, delegations).
MOST_DEPTH = 12
#: The opening words shown of a post.
OPENING = 240

#: The acts that say a post answered a request, and where each keeps it.
_ANSWERING = ("turn-said", "outcome-claimed", "manual-session-outcome-recorded")

#: Expectations that are work. A decision, input or permission question
#: recorded on a post is owed BY somebody about work, and is not the work.
_WORK_EXPECTS = (None, "result")


# -- what a post is, and the work it belongs to ---------------------------------

def _opening(cv, turn, most=OPENING) -> tuple[str, dict | None]:
    from mentis.conversation.versions import flow_text, presented
    got = cv._entry(turn) if hasattr(cv, "_entry") else cv._c.read([turn])
    if not got:
        return "", None
    try:
        e = presented(cv._c, got[0])
    except Exception:                                     # noqa: BLE001
        e = got[0]
    words = " ".join(flow_text((e.get("body") or {}).get("parts")).split())
    if len(words) > most:
        words = words[:most - 1] + "…"
    return words, e


def replies_to_of(cv, turn) -> str | None:
    """The post `turn` replies to, or None."""
    from mentis.conversation import REPLIES_TO
    if not turn:
        return None
    return next((x["link"]["to"] for x in
                 cv._c.links(relation=REPLIES_TO, frm=turn)), None)


def replies_of(cv, turn) -> list[str]:
    """The posts replying to `turn`, in the order they were written."""
    return [x["link"]["from"] for x in cv._replies_to(turn)] if turn else []


def requests_of_post(cv, turn) -> list[dict]:
    """The requests a post recorded or answered, from the acts on it: each
    `{"expectation", "role"}`, role "recorded" (the post asked for it: an
    owner's request, or a delegation) or "answered" (the post is a reply that
    answers it: `respond`, the dispatch fallback, a claim, a session outcome).
    Decision, input and permission questions are not work and are left out."""
    if not turn:
        return []
    out, seen = [], set()

    def add(exp, role):
        if exp and exp not in seen and len(out) < MOST_REQUESTS:
            seen.add(exp)
            out.append({"expectation": exp, "role": role})

    for a in sorted(cv.history(turn=turn), key=lambda a: a.get("at") or 0):
        d = a.get("detail") or {}
        if a["act"] == "expectation-recorded":
            if d.get("expects") in _WORK_EXPECTS and not d.get("form"):
                add(a["id"], "recorded")
        elif a["act"] == "turn-said" and d.get("answers_request"):
            add(d["answers_request"], "answered")
        elif a["act"] in _ANSWERING[1:] and a.get("caused_by"):
            add(a["caused_by"], "answered")
        elif a["act"] == "result-returned" and a.get("caused_by"):
            started = cv._act(a["caused_by"])
            if started and started.get("caused_by"):
                add(started["caused_by"], "answered")
    return out


def _status(cv, exp_id) -> dict:
    """A request's state and latest claim, as the record says them now."""
    from mentis.operational import completion as _completion
    try:
        s = cv.expectation_state(exp_id)
    except ValueError:
        return {"state": "unknown"}
    state = ("withdrawn" if s.get("withdrawn") else
             "met" if s.get("satisfied_by") else "open")
    out = {"state": state, "carrier": s.get("expected_of"),
           "carrier_alias": (cv.alias(s["expected_of"])
                             if s.get("expected_of") else None)}
    try:
        claim = _completion.latest_claim(cv, exp_id)
    except Exception:                                     # noqa: BLE001
        claim = None
    if claim:
        cd = claim.get("detail") or {}
        out["claim"] = {"act": claim["id"], "result": cd.get("result"),
                        "summary": cd.get("summary"),
                        "evidence": list(cd.get("evidence") or ())[:6],
                        "results": list(cd.get("results") or ())[:6]}
    return out


def _returned(cv, exp_id) -> list[str]:
    from mentis.conversation import ARTIFACT_RETURNED
    return [a["about"][0] for a in cv._children(exp_id)
            if a["act"] == ARTIFACT_RETURNED and a.get("about")][:8]


def _delegated_by(cv, exp: dict) -> dict | None:
    """Who delegated this request, on which post, under which request."""
    from mentis.artifacts import _delegation
    if _delegation(cv, exp) is None or not exp.get("caused_by"):
        return None
    parent = cv._act(exp["caused_by"])
    if not parent or parent["act"] != "expectation-recorded":
        return None
    return {"turn": exp.get("turn"), "by": exp.get("actor"),
            "by_alias": cv.alias(exp["actor"]) if exp.get("actor") else None,
            "parent": parent["id"], "parent_turn": parent.get("turn"),
            "parent_opening": _opening(cv, parent.get("turn"), 120)[0],
            **{f"parent_{k}": v for k, v in _status(cv, parent["id"]).items()
               if k in ("state", "claim")}}


def describe_request(cv, exp_id, role=None) -> dict:
    """One request of a work identity: state, latest claim, the delegation
    that produced it and the request above it, and what it returned."""
    exp = cv._act(exp_id) or {}
    row = {"expectation": exp_id, **({"role": role} if role else {}),
           "turn": exp.get("turn"),
           "opening": _opening(cv, exp.get("turn"), 120)[0],
           **_status(cv, exp_id)}
    if exp.get("act") == "expectation-recorded":
        up = _delegated_by(cv, exp)
        if up:
            row["delegated"] = up
        art = _returned(cv, exp_id)
        if art:
            row["returned"] = art
    return row


def work_identity(cv, turn) -> dict | None:
    """What a post is and the work it belongs to, read now. None when the
    record does not hold it."""
    if not turn:
        return None
    words, e = _opening(cv, turn)
    if e is None:
        return {"turn": turn, "known": False}
    return {"turn": turn, "known": True,
            "conversation": cv.conversation_of(turn),
            "number": cv.turn_number(turn),
            "author": e.get("attributed_to"),
            "author_alias": cv.alias(e.get("attributed_to")),
            "at": e.get("recorded_at"),
            **({"deleted": True} if e.get("deleted") else {}),
            "opening": "" if e.get("deleted") else words,
            "requests": [describe_request(cv, r["expectation"], r["role"])
                         for r in requests_of_post(cv, turn)]}


def in_reply_to(cv, replies_to) -> dict | None:
    """What a request recorded from a reply stores (`in_reply_to`): the post
    it replies to, its author, and the requests that post belongs to -- the
    ones it recorded or answered, then the requests those were delegated
    under. Threading plus work identity; not lineage, not a decision."""
    if not replies_to:
        return None
    got = cv._c.read([replies_to])
    if not got:
        return None
    reqs = []
    for r in requests_of_post(cv, replies_to):
        if r["expectation"] not in reqs:
            reqs.append(r["expectation"])
    for r in list(reqs):
        exp = cv._act(r) or {}
        up = _delegated_by(cv, exp) if exp.get("act") == "expectation-recorded" else None
        if up and up["parent"] not in reqs:
            reqs.append(up["parent"])
    return {"turn": replies_to, "author": got[0].get("attributed_to"),
            "number": cv.turn_number(replies_to), "requests": reqs}


def reply_target_of(cv, expectation) -> str | None:
    """The post the request `expectation` was asked in reply to, or None.

    `in_reply_to` where the request recorded it; for an older request, the
    reply link of its own post when that post is the requester's own words
    (a delegation's post replies to the carrier's request, which is lineage
    the run is told elsewhere, not a reply target)."""
    exp = cv._act(expectation) if expectation else None
    if not exp or exp.get("act") != "expectation-recorded":
        return None
    d = exp.get("detail") or {}
    if isinstance(d.get("in_reply_to"), dict) and d["in_reply_to"].get("turn"):
        return d["in_reply_to"]["turn"]
    from mentis.artifacts import _delegation
    if _delegation(cv, exp) is not None or not exp.get("turn"):
        return None
    got = cv._c.read([exp["turn"]])
    if not got or got[0].get("attributed_to") != exp.get("actor"):
        return None
    return replies_to_of(cv, exp["turn"])


# -- said to a run ----------------------------------------------------------------

def _when(at) -> str:
    if not at:
        return "?"
    return datetime.datetime.fromtimestamp(
        at, datetime.timezone.utc).strftime("%Y-%m-%d %H:%MZ")


def _request_line(r: dict) -> str:
    who = f", carried by {r['carrier_alias']}" if r.get("carrier_alias") else ""
    role = {"recorded": "asked for in it", "answered": "answered by it"}.get(
        r.get("role"), "")
    line = (f"  - request {r['expectation']}" + (f" ({role})" if role else "")
            + f"{who}; {r.get('state', 'unknown')}")
    c = r.get("claim")
    if c:
        line += f"; latest claim {c.get('result')}"
        if c.get("summary"):
            line += f": {c['summary']}"
        if c.get("evidence"):
            line += " · evidence: " + "; ".join(str(x) for x in c["evidence"])
    if r.get("opening") and r.get("role") != "recorded":
        line += f"\n    the request: {r['opening']}"
    up = r.get("delegated")
    if up:
        line += (f"\n    delegated by {up.get('by_alias') or up.get('by')} on "
                 f"{up.get('turn')} under request {up['parent']} "
                 f"({up.get('parent_state', 'unknown')}"
                 + (f"; latest claim {up['parent_claim'].get('result')}"
                    if up.get("parent_claim") else "") + ")"
                 + (f": {up['parent_opening']}" if up.get("parent_opening")
                    else ""))
    if r.get("returned"):
        line += "\n    returned: " + ", ".join(r["returned"])
    return line


def identity_lines(ident: dict | None, *, head: str) -> list[str]:
    """A work identity as lines a run reads: `head`, the post, then its
    requests."""
    if not ident:
        return []
    if not ident.get("known"):
        return [head, f"- {ident['turn']}: NOT AVAILABLE, the record does not "
                      "hold it. Nothing was substituted."]
    num = f"#{ident['number']} " if ident.get("number") is not None else ""
    post = (f"- {num}{ident['turn']} by {ident.get('author_alias')}, "
            f"{_when(ident.get('at'))}")
    if ident.get("deleted"):
        post += ": DELETED; what it said is not part of the work"
    else:
        post += f"\n  begins: {ident.get('opening') or '(no text)'}"
    lines = [head, post]
    if ident.get("requests"):
        lines.append("  the work it belongs to:")
        lines.extend(_request_line(r) for r in ident["requests"])
    else:
        lines.append("  it recorded and answered no request.")
    return lines


#: What a run carrying an owner's reply is told about the post it replies to.
REPLY_TARGET_HEAD = (
    "IN REPLY TO. The owner wrote this request as a reply to the post below. "
    "It is the conversational context: \"this\", \"it\" and \"that work\" in "
    "the request mean this post and the work it belongs to -- not the newest "
    "post in the Conversation. It is context, not a decision, and it grants "
    "nothing. Read it in full with `resolve` before acting on it.")


def reply_target_block(cv, expectation) -> str:
    """The lines a run carrying `expectation` is told about the post the
    request replies to, read from the record on every run of it (first,
    resumed, retried, restarted). '' when it replies to nothing."""
    target = reply_target_of(cv, expectation)
    if not target:
        return ""
    return "\n".join(identity_lines(work_identity(cv, target),
                                    head=REPLY_TARGET_HEAD))


# -- where a run may place its own posts --------------------------------------------

#: Posts Mentis writes or records FOR a piece of work, beside its answers: a
#: detached operation's arming post and the report Turn its helper posts
#: (`operational.detached`). They are within the work's thread (review R4).
_FOR_THE_WORK = ("detached-armed", "detached-reported")


def _answers_to(cv, exp_id) -> list[str]:
    """The posts that answered one request, and the posts recorded for it
    (a detached operation's arming post and its report)."""
    out = []
    for a in cv._children(exp_id):
        d = a.get("detail") or {}
        if a["act"] == "turn-said" and d.get("answers_request") == exp_id \
                and a.get("turn"):
            out.append(a["turn"])
        elif a["act"] in _ANSWERING[1:] and a.get("turn"):
            out.append(a["turn"])
        elif a["act"] in _FOR_THE_WORK and a.get("turn"):
            out.append(a["turn"])
    return out


def _related(cv, exp: dict) -> list[str]:
    """What a request's recorded lineage names beside `caused_by`: what its
    requirements record it continues, revises, implements or verifies
    (`routing.requirements.relation.ref`, Workstream S), and what a detected
    continuation named -- requests (`opr-`) and posts (`ent-`, a result
    Turn), at most MOST_REFS of them. Read, never inferred."""
    d = exp.get("detail") or {}
    rel = (((d.get("routing") or {}).get("requirements") or {})
           .get("relation") or {})
    refs = []
    if rel.get("value") not in (None, "new"):
        refs += list(rel.get("ref") or ())
    refs += list((rel.get("detected") or {}).get("ref") or ())
    out = []
    for r in refs:
        if (isinstance(r, str) and r.startswith(("opr-", "ent-"))
                and r not in out):
            out.append(r)
        if len(out) >= MOST_REFS:
            break
    return out


#: The most records a thread walk reads (counted per record read), and the
#: most lineage refs it reads of one request (review A-D).
MOST_NODES = 4 * MOST_DEPTH
MOST_REFS = 8


def thread_of(cv, expectation) -> dict:
    """The work a run carries, as places: `{"own", "reply_target", "posts",
    "conversations"}`.

    ALLOWED CONVERSATIONS FIRST (review A, B): the carried request's
    Conversation, its causal ancestors', and every Conversation opened under,
    or delegated into from, the carried request or work it delegated. A post
    anywhere else is never within the thread.

    POSTS, CAUSAL CHAIN FIRST (review D): the request's own post and the post
    it replies to; up the `caused_by` chain and down its delegations, each
    request's post, the posts that answered it or were recorded for it, what
    it replies to, and attached follow-ups; then, while the budget lasts,
    the lineage its requirements record (requests or result posts, review C)
    -- whose posts count only in an allowed Conversation. Lineage into other
    Conversations stays a reference and imports nothing. At most MOST_NODES
    records are read, and at most MOST_NODES posts kept."""
    budget = [MOST_NODES]
    cache: dict = {}

    def read(ref):
        if ref in cache:
            return cache[ref]
        if budget[0] <= 0:
            return None
        budget[0] -= 1
        got = cv._act(ref)
        cache[ref] = got
        return got

    exp = read(expectation) if expectation else None
    if not exp:
        return {"own": None, "reply_target": None, "posts": [],
                "conversations": []}
    posts: list = []
    allowed: list = []

    def allow(cid):
        if cid and cid not in allowed:
            allowed.append(cid)

    def add(*ts):
        for t in ts:
            if t and t not in posts and len(posts) < MOST_NODES:
                posts.append(t)

    def take(node):
        """A request of the work: its posts, follow-ups, opened places."""
        add(node.get("turn"), *_answers_to(cv, node["id"]))
        if node["id"] != expectation:
            add(reply_target_of(cv, node["id"]))
        for a in cv._children(node["id"]):
            d = a.get("detail") or {}
            if a["act"] == "follow-up-attached" and d.get("request"):
                f = read(d["request"]) or {}
                add(f.get("turn"), reply_target_of(cv, d["request"]))
            elif a["act"] == "conversation-opened":
                allow(a.get("conversation"))

    own = exp.get("turn")
    target = reply_target_of(cv, expectation)
    allow(exp.get("conversation"))
    add(own, target)
    work = [exp]
    seen = {exp["id"]}
    take(exp)
    # 1. up the causal chain
    cur = exp
    while cur.get("caused_by") and cur["caused_by"] not in seen:
        up = read(cur["caused_by"])
        if not up or up.get("act") != "expectation-recorded":
            break
        seen.add(up["id"])
        allow(up.get("conversation"))
        take(up)
        work.append(up)
        cur = up
    # 2. down its delegations
    frontier = [exp]
    while frontier and budget[0] > 0:
        nxt = []
        for node in frontier:
            for a in cv._children(node["id"]):
                if a["act"] != "work-delegated":
                    continue
                for child in a.get("about") or ():
                    if child in seen:
                        continue
                    c = read(child)
                    if not c:
                        continue
                    seen.add(child)
                    allow(c.get("conversation"))
                    take(c)
                    work.append(c)
                    nxt.append(c)
        frontier = nxt
    # 3. the lineage the work's requirements record, within the budget
    queue = list(work)
    while queue and budget[0] > 0:
        node = queue.pop(0)
        for ref in _related(cv, node):
            if budget[0] <= 0:
                break
            if ref.startswith("ent-"):
                where = (cv.conversation_of(ref)
                         if hasattr(cv, "conversation_of") else None)
                if where in allowed:
                    add(ref)
                reqs = [r["expectation"] for r in requests_of_post(cv, ref)]
            else:
                reqs = [ref]
            for r in reqs:
                if r in seen:
                    continue
                seen.add(r)
                got = read(r)
                if not got or got.get("act") != "expectation-recorded":
                    continue
                if got.get("conversation") in allowed:
                    take(got)
                queue.append(got)
    return {"own": own, "reply_target": target, "posts": posts,
            "conversations": allowed}


def placement_refusal(cv, expectation, target, *, participant=None,
                      what="reply there") -> str | None:
    """None when a run carrying `expectation` may place a post or record on
    `target`; otherwise the words that refuse it and list where it may.
    Not a post in a Conversation is not this rule's question (None).

    THE CONVERSATION IS ASKED FIRST (review A, B): a post outside the work's
    allowed Conversations (`thread_of`) is refused whatever else is true of
    it; inside them, it must be within the thread or addressed to you."""
    if not expectation or not target:
        return None
    got = cv._c.read([target])
    if not got or not cv._is(got[0], "contribution"):
        return None
    t = thread_of(cv, expectation)
    where_it_is = cv.conversation_of(target)
    if where_it_is is not None and where_it_is not in t["conversations"]:
        return (f"{target} is in another Conversation ({where_it_is}), "
                f"which is not one the work you carry ({expectation}) runs "
                f"in, so you may not {what}. The work's Conversations: "
                + ", ".join(t["conversations"]) + ".")
    if target in t["posts"]:
        return None
    if participant and participant in (
            (got[0].get("body") or {}).get("addressed_to") or ()):
        return None
    where = []
    if t["own"]:
        where.append(f"the request's own post {t['own']}")
    if t["reply_target"]:
        where.append(f"the post it replies to {t['reply_target']}")
    rest = [p for p in t["posts"] if p not in (t["own"], t["reply_target"])]
    if rest:
        where.append("posts of the requests you carry, continue or delegate: "
                     + ", ".join(rest[:12])
                     + (f" (and {len(rest) - 12} more)" if len(rest) > 12
                        else ""))
    where.append("a post addressed to you")
    return (f"{target} is not in the thread of the work you carry "
            f"({expectation}), so you may not {what}. You may place it on: "
            + "; ".join(where) + ".")


# -- an earlier round the owner has since replied past ------------------------------

def _subtree(cv, exp_id, budget) -> list[str]:
    """`exp_id` and the requests delegated under it, breadth first."""
    out, frontier = [exp_id], [exp_id]
    while frontier and len(out) < budget:
        nxt = []
        for e in frontier:
            for a in cv._children(e):
                if a["act"] == "work-delegated":
                    for child in a.get("about") or ():
                        if child not in out:
                            out.append(child)
                            nxt.append(child)
        frontier = nxt
    return out[:budget]


def owner_replied_later(cv, expectation, owner) -> dict | None:
    """The owner's latest reply in the line of work `expectation` started,
    carried as a request: `{"turn", "request", "at", "via"}`, or None.

    DERIVED, NOT RECORDED. From the posts that answered this request (or work
    delegated under it), the owner's replies to them that recorded a request;
    then the same from each of those, to the newest. So round 1 and round 2
    of a design, still open, say that the owner has since replied to a later
    round -- and which request carries that reply -- instead of reading as
    fresh pending choices. Nothing is closed or changed by it."""
    if not expectation or not owner:
        return None
    latest, frontier, seen, steps = None, [expectation], {expectation}, 0
    while frontier and steps < MOST_DEPTH:
        steps += 1
        found = []
        for e in frontier:
            for req in _subtree(cv, e, 24):
                for post in _answers_to(cv, req):
                    for reply in replies_of(cv, post):
                        got = cv._c.read([reply])
                        if not got or got[0].get("attributed_to") != owner:
                            continue
                        for a in cv.history(turn=reply):
                            d = a.get("detail") or {}
                            if (a["act"] == "expectation-recorded"
                                    and a.get("actor") == owner
                                    and d.get("expects") in _WORK_EXPECTS
                                    and a["id"] not in seen):
                                seen.add(a["id"])
                                found.append({"turn": reply, "request": a["id"],
                                              "at": a.get("at") or 0,
                                              "via": post})
        if not found:
            break
        newest = max(found, key=lambda f: f["at"])
        if latest is None or newest["at"] >= latest["at"]:
            latest = newest
        frontier = [f["request"] for f in found]
    return latest


def replied_words(r: dict | None) -> str:
    """`owner replied: <turn> → <request>`, or ''."""
    if not r:
        return ""
    return f"owner replied: {r['turn']} → {r['request']}"
