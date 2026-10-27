"""Agent work: the posts agents write to each other, told from the record.

A ROOM FILLS WITH AGENT-TO-AGENT POSTS -- delegation briefs, findings, the
results a run returns to the agent that asked, follow-ups nobody carries --
and the owner's own conversation is lost among them. This says which posts
are that, so a view can fold them away behind a visible control. It hides
nothing itself: it classifies, and says why.

NEVER HIDDEN COMES FIRST. A post is agent work only when NONE of these hold:

  * the owner wrote it;
  * it is addressed to the owner -- when written, or later (`turn-addressed`);
  * it carries an expectation whose current carrier is the owner (a request,
    a decision, an input asked of them -- answered or not), a decision form,
    or a fillable block somebody has responded to (a response set);
  * it answers a request the owner made (a `turn-said` whose
    `answers_request` the owner recorded, or whose request Turn is the
    owner's), or it replies to a post of the owner's;
  * the owner reacted on it;
  * anything under it, at any depth, is not itself agent work -- the owner's
    reply, somebody's answer to the owner: a thread whose root is hidden
    still shows when any reply in it is visible, so the root shows too.

AND THEN ONLY WHEN IT IS ONE OF:

  brief      the Turn of a delegation (`work-delegated` on it): "brief to @X"
  result     a run's answer to a request an AGENT made: "result to @X"
  finding    the Turn of discovered work (`work-discovered` on it)
  follow-up  a stray post by a run: written by an execution, addressed to
             nobody, replying to nothing, expecting nothing of anybody
             (`ui/src/surfaces/followups.ts` `stray`, the same rule)

No owner on the record: nothing is agent work -- unknown, never hidden.
A deep link to a post is the view's to honour: it reveals what it names.

BATCHED. The posts and everything under them are walked a level at a time
(one statement a level, at most `MAX_DEPTH`), and then the whole set is
classified in a fixed number of statements -- never one walk per post.
"""
from __future__ import annotations

REPLIES_TO = "replies-to"
ANCHORS_IN = "anchors-in"
REACTS_TO = "reacts-to"
RESPONDS_TO = "responds-to"
#: How deep under a post its replies are read. A thread deeper than this is
#: never hidden: what is below could be somebody's answer to the owner.
MAX_DEPTH = 8
#: A request through the owner's door that presented no grant: no evidence
#: an agent wrote it (`followups.ts` `byExecution`).
UNATTRIBUTED = "unattributed-local-request"
FORM_ACTS = ("decision-form", "decision-form-attached")


def _walk(corpus, roots) -> tuple[dict, set]:
    """node -> its direct replies, for the roots and everything under them,
    and the nodes whose replies were NOT read (the depth ran out)."""
    kids, seen = {}, set(roots)
    frontier, depth = sorted(seen), 0
    while frontier and depth < MAX_DEPTH:
        depth += 1
        nxt = []
        for x in corpus.links(relation=REPLIES_TO, to_any=frontier):
            c, p = x["link"]["from"], x["link"]["to"]
            kids.setdefault(p, []).append(c)
            if c not in seen:
                seen.add(c)
                nxt.append(c)
        frontier = sorted(nxt)
    return kids, set(frontier)


def classify(cv, post_ids, owner) -> dict:
    """post -> `{"kind", "why", "to"}` when it is agent work, else None.
    `owner` is the owner Participant (`work_overview.owner_of`); None
    classifies nothing as agent work."""
    pids = list(dict.fromkeys(p for p in post_ids if p))
    if not pids or owner is None:
        return {p: None for p in pids}
    corpus = cv.corpus
    kids, unread = _walk(corpus, pids)
    nodes = sorted(set(pids) | {c for cs in kids.values() for c in cs})
    entries = {e["id"]: e for e in corpus.read(nodes)}
    acts = corpus.operational(turn=nodes)
    on = {}
    for a in acts:
        on.setdefault(a["turn"], []).append(a)
    exps = [a for a in acts if a["act"] == "expectation-recorded"]
    carriers = cv._carriers(exps) if exps else {}
    asked_ids = sorted({(a.get("detail") or {}).get("answers_request")
                        for a in acts if a["act"] == "turn-said"
                        and (a.get("detail") or {}).get("answers_request")})
    asked = {a["id"]: a for a in corpus.operational(id=asked_ids)} \
        if asked_ids else {}
    parent = {}
    for x in corpus.links(relation=REPLIES_TO, frm_any=nodes):
        parent.setdefault(x["link"]["from"], x["link"]["to"])
    authors = {i: h[7] for i, h in corpus.heads(
        list(parent.values())
        + [a.get("turn") for a in asked.values()]).items()}
    anchors = {x["link"]["from"]: x["link"]["to"] for x in corpus.links(
        relation=ANCHORS_IN, to_any=nodes)}
    reacted = {anchors[x["link"]["to"]] for x in corpus.links(
        relation=REACTS_TO, to_any=list(anchors))
        if x.get("attributed_to") == owner and x["link"]["to"] in anchors} \
        if anchors else set()
    answered = {x["link"]["to"] for x in corpus.links(
        relation=RESPONDS_TO, to_any=nodes)}

    def base(n):
        """`n` on its own -- nothing under it read: a kind, or None."""
        e = entries.get(n)
        if e is None or e.get("attributed_to") == owner:
            return None
        mine = on.get(n, ())
        to_owner = owner in ((e.get("body") or {}).get("addressed_to") or ())
        addressed = to_owner or any(
            a["act"] == "turn-addressed" and owner in (a.get("about") or ())
            for a in mine)
        if addressed or n in reacted or n in answered:
            return None
        if authors.get(parent.get(n)) == owner:
            return None
        if any(a["act"] in FORM_ACTS for a in mine):
            return None
        carried = [carriers.get(a["id"]) for a in mine
                   if a["act"] == "expectation-recorded"]
        if owner in carried:
            return None
        results = []
        for a in mine:
            if a["act"] != "turn-said":
                continue
            req = (a.get("detail") or {}).get("answers_request")
            if not req:
                continue
            r = asked.get(req)
            by = r["actor"] if r else None
            if by == owner or (r and authors.get(r.get("turn")) == owner) \
                    or r is None:
                return None          # an answer to the owner, or unknown
            results.append(by)
        brief = next((a for a in mine if a["act"] == "work-delegated"), None)
        if brief is not None:
            who = (brief.get("detail") or {}).get("participant")
            return {"kind": "brief", "to": who}
        if results:
            return {"kind": "result", "to": results[0]}
        if any(a["act"] == "work-discovered" for a in mine):
            return {"kind": "finding", "to": None}
        written = e.get("written_by")
        if (written and written != UNATTRIBUTED and n not in parent
                and not addressed
                and not ((e.get("body") or {}).get("addressed_to"))
                and not any(a["act"] == "turn-addressed" for a in mine)
                and not any(c for c in carried)):
            return {"kind": "follow-up", "to": None}
        return None

    kinds = {n: base(n) for n in nodes}
    memo = {}

    def hidden(n, path=()):
        """Agent work, and so is everything under it."""
        if n in memo:
            return memo[n]
        if kinds.get(n) is None or n in unread or n in path:
            memo[n] = False
            return False
        out = True
        for c in kids.get(n, ()):
            e = entries.get(c) or {}
            if e.get("deleted") and e.get("attributed_to") != owner:
                continue     # a deleted reply shows nothing to keep
            if not hidden(c, path + (n,)):
                out = False
                break
        memo[n] = out
        return out

    names = {}
    targets = sorted({k["to"] for n in pids if hidden(n)
                      for k in [kinds[n]] if k.get("to")})
    for t in targets:
        names[t] = cv.alias(t)
    out = {}
    for n in pids:
        if not hidden(n):
            out[n] = None
            continue
        k = kinds[n]
        to = names.get(k["to"]) if k.get("to") else None
        why = {"brief": f"brief to {to}" if to else "delegation brief",
               "result": f"result to {to}" if to else "result to an agent",
               "finding": "finding",
               "follow-up": "follow-up"}[k["kind"]]
        out[n] = {"kind": k["kind"], "why": why, "to": k.get("to"),
                  "to_name": to}
    return out
