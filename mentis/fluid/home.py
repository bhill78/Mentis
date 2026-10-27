"""Fluid Home (stage F4a): the Home's collections, work and runs by id, and
what the change feed says of them.

PRODUCTION'S MEANING, FLUID'S SHAPE. Every word about a piece of work comes
from the domain readers production's Brain Home answers with --
`work.trunk_status` through `work_overview.project`, `Conversations.
expectations` as `/api/owed` reads it, `Conversations.open_runs` and
`runs.run_state` as `/api/working` reads them, the `turn-said` acts the
Daily Briefing reads (`ui/src/surfaces/lobby/briefing.ts`). None of
production's routes is called and nothing in production is changed: what
differs is only the shape, which is Fluid's (#211) -- a collection is ordered
ids and paging cursors, an entity is read by id in batches.

  GET /fluid/api/home/needs-you    expectations that explicitly ask the owner
  GET /fluid/api/home/work         pieces of work, by where they stand
  GET /fluid/api/work?ids=         a piece of work as it now reads
  GET /fluid/api/home/activity     runs: the open ones, then the latest ended
  GET /fluid/api/runs?ids=         a run as it now reads
  GET /fluid/api/home/briefing     the work that came back in one period
  GET /fluid/api/home/for-you      posts addressed to the owner, when written
                                   or later, or replying to a post of theirs
  GET /fluid/api/needs-you?post=   what on one post or its thread needs the
                                   owner, by Needs you's rule (#576)
  GET /fluid/api/needs-you?ids=    those requests as they now read

WHERE WORK STANDS (`state`), placed by the rules today's Ledger places it by
(`work_overview._scoped_group`), with no time window: Needs you is something
under it the owner owes; In flight is moving -- a run observed going, or
waiting on a child, a decision, or other work that moves; Completed is
claimed met; Ended is work whose runs ended without its objective claimed
met, or that will not resume by itself; Unknown is work whose state cannot be
established, said why. Work nothing has run for and that does not need the
owner is `not-started`: never In flight, never in All, and counted, so
nothing is hidden by being left out -- as the Ledger leaves it out.

WHO THE OWNER IS is the record's answer (`work_overview.owner_of`). Where the
record names none, what the owner owes is unknown, and the answers say so
rather than answering nothing.

THE WORK READ IS BRAIN-WIDE, as the Ledger's is: where a piece of work stands
is computed from everything under it, and the counts of each state need
every piece placed. It is read a causal level at a time
(`Conversations._prefetch_lineage`) inside the request's reading scope, so
its statements grow with the Conversations its work is in and the depth of
its trees, not with every node; what it RETURNS is bounded by `limit`.
"""
from __future__ import annotations

import re
import time
from datetime import date as _date
from datetime import datetime, timedelta

from mentis.conversation import (CONTRIBUTION, IN_CONVERSATION, REPLIES_TO,
                                 RUN_ENDS, RUN_START, closed_starts)
from mentis.conversation.versions import flow_text
from mentis.operational import work_overview as wo
from mentis.operational.runs import RECENT_ENDED, run_state

from . import read as _read
from . import status as _status

#: The states a piece of work is placed in, in the order All lists them.
PLACED = ("needs-you", "in-flight", "completed", "ended", "unknown")
#: Nothing has run for it and it does not need the owner: counted, never
#: listed in All (the Ledger's `not_started` and `discovered_unassigned`).
NOT_STARTED = "not-started"
#: What `?state=` may ask for. `unknown` is offered as the Ledger offers it.
STATES = ("all",) + PLACED
#: WHERE WORK STANDS, as `?state=stage:<stage>` asks for it: every request
#: at that stage (`stage.stage_of`), not-started work included when asked.
STAGE = "stage:"
STAGE_STATES = tuple(STAGE + s for s in wo.STAGES)
_GROUP = {"needs_you": "needs-you", "in_flight": "in-flight",
          "completed": "completed", "returned": "ended",
          "unknown": "unknown"}
#: A Home page, by default and at most.
PAGE, PAGE_MAX = 30, 200
#: The briefing's periods, by local hour [from, to): briefing.ts's own.
PERIODS = {"morning": (0, 11), "lunch": (11, 15), "evening": (15, 24)}
#: The most `turn-said` acts one briefing reads from its period's start. More
#: and it says the latest part of the period was not read (`truncated`).
BRIEF_SCAN = 5000
#: The most characters of a briefing line.
LINE = 200
#: How far a change's causal chain is followed up to the request it is for.
CHAIN_DEPTH = 64
#: The keys of Home's collections, as the change feed names them.
NEEDS_YOU, WORK, ACTIVITY, BRIEFING, FOR_YOU = (
    "home:needs-you", "home:work", "home:activity", "home:briefing",
    "home:for-you")
#: Addressing an existing post to somebody, later (`address_turn`).
ADDRESSED = "turn-addressed"
#: What turns a post toward somebody, as For you asks it of the record.
TOWARD_OWNER = {"kind": CONTRIBUTION, "home": IN_CONVERSATION,
                "replies": REPLIES_TO, "field": "addressed_to",
                "addressed": ADDRESSED}

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _runtime(st) -> dict:
    """What this process observes of runs: `/api/work`'s own observation."""
    from mentis.web import _runtime_observation
    return _runtime_observation(st)


def _no_owner(key, at) -> dict:
    return {"key": key, "items": [], "before": None, "owner": None,
            "unknown": True, "why": wo.NO_VIEWER, "cursor": at}


def _key_cursor(*parts) -> str:
    return "_".join(repr(p) if isinstance(p, float) else str(p)
                    for p in parts)


def _parse_key(raw, n) -> tuple:
    try:
        bits = raw.split("_")
        if len(bits) != n:
            raise ValueError
        return tuple(float(b) if "." in b or "e" in b or "inf" in b
                     else int(b) for b in bits)
    except (AttributeError, ValueError):
        raise _read.BadRequest(f"not a paging cursor: {raw!r}")


# -- the work readers, through the domain's ------------------------------------

class _Ctx(wo._Ctx):
    """`work_overview`'s per-read context, asking nothing Home does not show:
    an origin link is the Turn and its Conversation, unnumbered (the number
    is read for the page's own posts, `numbers_of`), and replies under it
    are not counted. What places and words the work is unchanged."""

    def link(self, turn, conversation=None):
        if not turn:
            return None
        return {"turn": turn, "number": None, "conversation": conversation,
                "conversation_name": None}

    def replies(self, turn, conversation):
        return None


def _prime(ctx, acts) -> None:
    """Read these requests' causal trees a LEVEL at a time, and the texts
    their titles and outcomes are read from in one batch, so what
    `project` asks node by node is answered from this reading."""
    cv = ctx.cv
    cv._prefetch_lineage([a["id"] for a in acts]
                         + [a.get("caused_by") for a in acts], acts=acts)
    turns = {a.get("turn") for a in acts}
    for a in acts:
        for d in ctx.descendants(a["id"]):
            if d["act"] in ("expectation-recorded", "result-returned"):
                turns.add(d.get("turn"))
    want = [t for t in turns if t and t not in ctx._texts]
    for e in cv.corpus.read(want) if want else ():
        ctx._texts[e["id"]] = flow_text((e.get("body") or {}).get("parts"))
    for t in want:
        ctx._texts.setdefault(t, None)


def _place(cv, act, item, found) -> str:
    """Where one projected piece of work stands, by the Ledger's own rule
    (`_scoped_group`) with no time window."""
    group, reason = wo._scoped_group(cv, act, item, since=float("-inf"),
                                     completed_since=float("-inf"),
                                     found=found)
    if group is not None:
        return _GROUP[group]
    return NOT_STARTED if reason in ("not_started",
                                     "discovered_unassigned") else "ended"


def _project(ctx, act, *, viewer, runtime, found):
    """(item, state) for one request; one that cannot be read is unknown,
    said why, beside the rest -- as `project` itself says it."""
    try:
        item = wo.project(ctx, act, viewer=viewer, runtime=runtime)
    except Exception as exc:                              # noqa: BLE001
        item = {"state": "unreadable", "group": "unknown",
                "status_words": "Unknown — could not be read",
                "last_activity_at": wo.iso(act.get("at")),
                "why_unknown": f"{type(exc).__name__}: {exc}",
                "title": None, "met_at": None}
        return item, "unknown"
    try:
        return item, _place(ctx.cv, act, item, found)
    except Exception as exc:                              # noqa: BLE001
        item["why_unknown"] = f"{type(exc).__name__}: {exc}"
        return item, "unknown"


def _newest(item) -> float:
    at = wo._newest(item)
    try:
        return wo.parse_since(at) or 0.0
    except ValueError:
        return 0.0


def work_collection(st, *, state, before, limit, at) -> dict:
    """`GET /fluid/api/home/work?state=`: the pieces of work in one state --
    or All of them, Needs you first, then In flight, Completed, Ended and
    Unknown -- newest first within each, one page; and how many are in
    every state, `not-started` among them."""
    if state not in STATES + STAGE_STATES:
        raise _read.BadRequest(f"state is one of {', '.join(STATES)}, or "
                               f"{STAGE}<stage>: one of "
                               f"{', '.join(wo.STAGES)}")
    stage = state[len(STAGE):] if state.startswith(STAGE) else None
    cv = st.cv
    viewer = wo.owner_of(cv)
    runtime = _runtime(st)
    ctx = _Ctx(cv)
    trunks = wo._trunks(cv)
    _prime(ctx, trunks)
    found = wo._found_ids(cv)
    seq = cv._write_order([a["id"] for a in trunks])
    rows = []
    counts = {s: 0 for s in PLACED + (NOT_STARTED,)}
    stages = {s: 0 for s in wo.STAGES}
    for a in trunks:
        item, where = _project(ctx, a, viewer=viewer, runtime=runtime,
                               found=found)
        counts[where] += 1
        at_stage = item.get("stage") or "unknown"
        stages[at_stage] += 1
        if stage is not None:
            if at_stage != stage:
                continue
        elif where == NOT_STARTED or (state != "all" and where != state):
            continue
        rank = PLACED.index(where) if where in PLACED else len(PLACED)
        rows.append(((rank, -_newest(item),
                      -seq.get(a["id"], -1)), a["id"]))
    counts["all"] = sum(counts[s] for s in PLACED)
    rows.sort()
    if before:
        rank, newest, s = _parse_key(before, 3)
        mark = (int(rank), -float(newest), -int(s))
        rows = [r for r in rows if r[0] > mark]
    page = rows[:limit]
    more = len(rows) > len(page)
    last = page[-1][0] if page else None
    return {"key": WORK, "state": state, "items": [r[1] for r in page],
            "before": _key_cursor(last[0], -last[1], -last[2])
            if more and last else None,
            "counts": counts, "limit": limit, "viewer": viewer,
            # by stage, over every request (`not_started` among them)
            "stages": stages,
            # A FALSE ZERO IS NOT SAID: with no owner named, Needs you is
            # unknown, as the Ledger says it.
            "needs_you_unknown": viewer is None,
            "needs_you_why": wo.NO_VIEWER if viewer is None else None,
            "runtime_why_not": runtime.get("why_not"),
            "cursor": at}


def work(st, ids) -> dict:
    """`GET /fluid/api/work?ids=`: each request as it now reads, in the
    order asked. Any expectation is answered -- a piece of work, or a child
    or a decision under one, which is what Needs you lists -- and `trunk`
    says which. One that is not an expectation is `{"id", "error"}`."""
    cv, corpus = st.cv, st.cv.corpus
    viewer = wo.owner_of(cv)
    runtime = _runtime(st)
    acts = {a["id"]: a for a in corpus.operational(id=ids)}
    exps = [acts[i] for i in ids
            if i in acts and acts[i]["act"] == "expectation-recorded"]
    ctx = _Ctx(cv)
    _prime(ctx, exps)
    found = wo._found_ids(cv) if exps else set()
    carriers = cv._carriers(exps) if exps else {}
    turns = [a["turn"] for a in exps if a.get("turn")]
    homes = _read.homes_of(corpus, turns)
    numbers = _read.numbers_of(corpus, homes)
    where = {a["id"]: homes.get(a.get("turn")) or a.get("conversation")
             for a in exps}
    names = _read._names(corpus, list(where.values())
                         + list(carriers.values())
                         + [a["actor"] for a in exps])
    out = []
    for i in ids:
        a = acts.get(i)
        if a is None or a["act"] != "expectation-recorded":
            out.append({"id": i, "error": "not a request" if a else
                        "the record holds no such act"})
            continue
        item, state = _project(ctx, a, viewer=viewer, runtime=runtime,
                               found=found)
        try:
            trunk = wo.is_trunk(cv, a)
        except Exception:                                 # noqa: BLE001
            trunk = True
        below = ctx.descendants(i)
        runs = sorted((d for d in below if d["act"] == RUN_START),
                      key=ctx.order.key)
        # THE NEWEST ACT ANYWHERE UNDER IT, as `trunk_status`'s last act is
        last = max([a, *below], key=ctx.order.key)
        carrier = carriers.get(i)
        conv = where[i]
        turn = a.get("turn")
        out.append({
            "id": i, "what": item.get("title"), "state": state,
            "status_words": item.get("status_words"),
            "stage": item.get("stage"),
            "stage_words": item.get("stage_words"),
            "why_unknown": item.get("why_unknown"),
            "trunk": trunk,
            "expects": (a.get("detail") or {}).get("expects"),
            "requested_by": a["actor"],
            "requested_by_name": names.get(a["actor"], a["actor"]),
            "carrier": carrier,
            "carrier_name": names.get(carrier) if carrier else None,
            "conversation": conv,
            "conversation_name": names.get(conv) if conv else None,
            "post": turn, "post_number": numbers.get(turn) if turn else None,
            "runs": [r["id"] for r in runs],
            "updated_at": last.get("at"),
        })
    return {"work": out, "limit": _read.BATCH, "viewer": viewer,
            "runtime_why_not": runtime.get("why_not")}


# -- needs you -------------------------------------------------------------------

def asking_owner(cv, owner) -> list[tuple[tuple, str]]:
    """THE NEEDS YOU RULE, the one definition of it: what explicitly asks
    the owner -- expectations whose current carrier is the owner and that
    nobody has answered (`/api/owed`'s rule, `work.owed_by`) -- each with
    its place in Home's order, newest first: `((-at, write order), id)`,
    sorted. Home's Needs you pages it; What needs you on a post (#576) keeps
    the ones on that post's thread. Neither restates it."""
    ids = [s["expectation"] for s in cv.expectations(of=owner)
           if not s["response_present"]]
    seq = cv._write_order(ids)
    return sorted((((-((cv._act(i) or {}).get("at") or 0.0), seq.get(i, -1)), i)
                   for i in ids))


def needs_you(st, *, before, limit, at) -> dict:
    """`GET /fluid/api/home/needs-you`: what explicitly asks the owner --
    expectations whose current carrier is the owner and that nobody has
    answered (`/api/owed`'s rule, `work.owed_by`), newest first, one page.
    Being addressed is not being asked."""
    cv = st.cv
    owner = wo.owner_of(cv)
    if owner is None:
        return _no_owner(NEEDS_YOU, at)
    keyed = asking_owner(cv, owner)
    # the total is everything asking the owner, whatever page this is
    total = len(keyed)
    if before:
        if before.startswith("opr-"):
            mark = next((k for k, i in keyed if i == before), None)
            if mark is None:
                raise _read.BadRequest(f"not asking the owner now: {before!r}")
        else:
            b_at, b_seq = _parse_key(before, 2)
            mark = (-float(b_at), int(b_seq))
        keyed = [(k, i) for k, i in keyed if k > mark]
    page = keyed[:limit]
    more = len(keyed) > len(page)
    last = page[-1][0] if page else None
    return {"key": NEEDS_YOU, "items": [i for _, i in page],
            "before": _key_cursor(-float(last[0]), last[1])
            if more and last else None,
            "total": total, "owner": owner, "limit": limit,
            "cursor": at}


# -- what needs you, item by item (forms build P11) --------------------------------

#: The kinds of item Needs You counts: a decision form (or a decision asked
#: as its own post, one item each), a block waiting for input, and any
#: other ask of the owner.
ITEM_KINDS = ("decision", "input", "request")
_ITEM_WORDS = {"decision": ("decision", "decisions"),
               "input": ("input", "inputs"),
               "request": ("request", "requests")}


def item_words(counts) -> str:
    """'2 decisions, 1 input' -- the counts said, kinds with none left out;
    '' for nothing."""
    return ", ".join(
        f"{counts[k]} {_ITEM_WORDS[k][counts[k] != 1]}"
        for k in ITEM_KINDS if counts.get(k))


def _input_block(corpus, exp) -> dict | None:
    """The block an input waits on, from its response set: name, part,
    type and set. None when the set cannot be read."""
    sid = (exp.get("detail") or {}).get("response_set")
    got = corpus.read([sid]) if sid else []
    if not got:
        return None
    b = got[0].get("body") or {}
    return {"set": sid, "block": b.get("block"), "part": b.get("part") or 0,
            "type": b.get("type")}


def _lead(corpus, turn) -> str | None:
    """A post's first line of words, as a list row heads it."""
    from mentis.conversation.versions import presented
    got = corpus.read([turn]) if turn else []
    if not got:
        return None
    text = flow_text((presented(corpus, got[0]).get("body") or {})
                     .get("parts"))
    line = next((s for s in (re.sub(r"^[#>*\-\s]+", "", x)
                             .replace("**", "").strip()
                             for x in text.splitlines()) if s), None)
    return (line[:159].rstrip() + "…") if line and len(line) > 160 else line


def needs_you_items(st, *, at) -> dict:
    """`GET /fluid/api/needs-you/items`: what asks the owner now, counted
    the way the bell and badge count it -- ONE ITEM PER FORM, not per
    question and not per Conversation. Home's Needs you rule
    (`asking_owner`), grouped: the questions of one decision form are one
    item; a decision asked as its own post is one item; a block waiting for
    the owner's input (`request_input`) is one item until Done; any other
    ask is one item. Each says where it was asked, so an entry opens that
    post at the form: `anchor` is the form's (`decision-form:<key>`) or the
    block's (`block:<name>`) place on it. Newest first, by its newest
    question. No owner named: unknown, never a false nothing."""
    cv, corpus = st.cv, st.cv.corpus
    owner = wo.owner_of(cv)
    if owner is None:
        return {**_no_owner("needs-you:items", at), "items": [],
                "counts": None, "words": None}
    ids = [i for _, i in asking_owner(cv, owner)]
    acts = [a for a in map(cv._act, ids) if a]
    on = {a["id"]: cv.asked_on(a) for a in acts}
    turns = [t for t in dict.fromkeys(on.values()) if t]
    homes = _read.homes_of(corpus, turns)
    numbers = _read.numbers_of(corpus, homes)
    names = _read._names(corpus, list(homes.values())
                         + [a["actor"] for a in acts])
    items, by_key = [], {}
    for a in acts:
        d = a.get("detail") or {}
        form = d.get("form")
        key = form or a["id"]
        if key in by_key:
            by_key[key]["asks"].append(a["id"])
            continue
        expects = d.get("expects")
        kind = ("decision" if form or expects == "decision"
                else "input" if expects == "input" else "request")
        turn = on.get(a["id"])
        conv = homes.get(turn) or a.get("conversation")
        block = _input_block(corpus, a) if kind == "input" else None
        row = {"key": key, "kind": kind, "expects": expects,
               "form": form, "asks": [a["id"]],
               "question": d.get("question"),
               "block": block,
               "anchor": ((f"block:{block['block']}" if block else None)
                          if kind == "input" else
                          f"decision-form:{key}" if kind == "decision"
                          else None),
               "post": turn, "post_number": numbers.get(turn) if turn
               else None,
               "lead": _lead(corpus, turn) if turn else None,
               "conversation": conv,
               "conversation_name": names.get(conv) if conv else None,
               "asked_by": a["actor"],
               "asked_by_name": names.get(a["actor"], a["actor"]),
               "because": a.get("because"),
               "at": a.get("at")}
        by_key[key] = row
        items.append(row)
    counts = {k: sum(1 for r in items if r["kind"] == k) for k in ITEM_KINDS}
    return {"key": "needs-you:items", "items": items,
            "counts": {**counts, "total": len(items)},
            "words": item_words(counts), "owner": owner, "cursor": at}


# -- what on one post needs you (#576) ---------------------------------------------

def _owner_answered(cv, act, state, owner) -> bool:
    """Whether the owner's own act answered this request, as
    `expectation_state` counts an answer but by the owner alone: a reply of
    theirs to the asking post (`replies_from_expected`, the carrier's, who
    is the owner here) or an `expectation-met` of theirs that is not a
    withdrawal -- for a reconsideration, only one recording selections."""
    reconsideration = (act.get("detail") or {}).get("reconsideration")
    if state.get("replies_from_expected") and not reconsideration:
        return True
    for m in filter(None, map(cv._act, state.get("satisfied_by") or ())):
        detail = m.get("detail") or {}
        if (m.get("actor") == owner and not detail.get("withdrawn")
                and (not reconsideration or "selections" in detail)):
            return True
    return False


def _ask_rows(st, acts, owner, asking) -> list[dict]:
    """Each of these `expectation-recorded` acts as Home's Needs you reads
    it, and what a card needs to answer it where it is shown: what it
    expects, the alternatives the asker stated (as recorded, or None), why,
    who asked, the post it hangs on and where that post lives.

    `open` is Home's rule itself (`asking_owner`, the ids in `asking`), not
    a copy of it. `state` is what the record says became of one that is
    not, never inferred from its having left Needs you:
      open       it needs the owner now
      withdrawn  the owner closed it unanswered (its `expectation-met` by
                 the owner, marked withdrawn)
      answered   the owner, carrying it, answered it: a reply of theirs to
                 the asking post, or an `expectation-met` of theirs
      elsewhere  somebody else carries it now (`carrier`); `answered` says
                 whether it has been answered
      closed     none of these: it asks the owner nothing now -- closed by
                 somebody else's act, say
    `answered` and `withdrawn` are what the record holds by anybody."""
    cv, corpus = st.cv, st.cv.corpus
    if not acts:
        return []
    carriers = cv._carriers(acts)
    states = {s["expectation"]: s
              for s in cv._expectation_states(acts, False)}
    # WHERE EACH WAS ASKED: its own Turn, or a decision form's post (P7),
    # which is None while that form is on no post yet.
    on = {a["id"]: cv.asked_on(a) for a in acts}
    turns = [t for t in on.values() if t]
    homes = _read.homes_of(corpus, turns)
    numbers = _read.numbers_of(corpus, homes)
    authors = {e["id"]: e["attributed_to"]
               for e in (corpus.read(list(dict.fromkeys(turns)))
                         if turns else ())}
    names = _read._names(corpus, list(homes.values())
                         + [a["actor"] for a in acts]
                         + [c for c in carriers.values() if c])
    out = []
    for a in acts:
        s = states.get(a["id"]) or {}
        turn = on.get(a["id"])
        conv = homes.get(turn) or a.get("conversation")
        carrier = carriers.get(a["id"])
        withdrawal = s.get("withdrawn")
        withdrawn = withdrawal is not None
        answered = bool(s.get("response_present")) and not withdrawn
        # WHOSE ACT IT WAS, from the record: `response_present` counts a
        # fulfilment by anybody, and a withdrawal is by whoever carried it
        # then. Answered and Withdrawn are the owner's own acts only.
        owner_withdrew = withdrawn and withdrawal.get("by") == owner
        owner_answered = carrier == owner and (
            bool((s.get("input") or {}).get("ready"))
            if (a.get("detail") or {}).get("expects") == "input"
            else _owner_answered(cv, a, s, owner))
        state = ("open" if a["id"] in asking
                 else "withdrawn" if owner_withdrew
                 else "elsewhere" if carrier != owner
                 else "answered" if owner_answered
                 else "closed")
        out.append({
            "id": a["id"],
            "expects": (a.get("detail") or {}).get("expects"),
            "options": s.get("options"),
            "because": a.get("because"),
            "asked_by": a["actor"],
            "asked_by_name": names.get(a["actor"], a["actor"]),
            "carrier": carrier,
            "carrier_name": names.get(carrier, carrier) if carrier else None,
            "open": state == "open",
            "state": state,
            "answered": answered,
            "withdrawn": withdrawn,
            "post": turn, "post_number": numbers.get(turn) if turn else None,
            "post_author": authors.get(turn),
            # what an answer is filed under, as production's answer is: the
            # asking post's Topics in its home (`topics_of`)
            "post_topics": cv.topics_of(turn, conv) if turn else [],
            "conversation": conv,
            "conversation_name": names.get(conv) if conv else None,
            "at": a.get("at"),
            # A QUESTION OF A DECISION FORM (P7): its form and own words,
            # which its post does not hold. Absent for any other ask.
            **({"form": s.get("form"), "index": s.get("index"),
                "question": s.get("question")}
               if s.get("form") else {}),
            # AN INPUT (P4 `request_input`, P11): the block it waits on, so
            # a Needs You card draws that block, answered in place.
            **({"block": _input_block(corpus, a)}
               if (a.get("detail") or {}).get("expects") == "input"
               else {}),
        })
    return out


def needs_you_on(st, post, *, at) -> dict:
    """`GET /fluid/api/needs-you?post=<id>`: what on this post, or anywhere
    in the thread under it, needs the owner -- Home's Needs you
    (`asking_owner`, the one rule) kept to these posts, in Home's order,
    each as `asks` reads it. With no owner named it is unknown, never a
    false nothing."""
    cv, corpus = st.cv, st.cv.corpus
    head = corpus.read([post]) if post else []
    if not head or not _read._is_post(head[0]):
        raise _read.BadRequest(f"not a post: {post!r}")
    key = f"needs-you:{post}"
    owner = wo.owner_of(cv)
    if owner is None:
        return {**_no_owner(key, at), "post": post, "asks": []}
    thread = {post} | {r[0] for r in corpus.reply_closure(
        post, replies=REPLIES_TO, home=IN_CONVERSATION)}
    ids = [i for _, i in asking_owner(cv, owner)]
    acts = [a for a in map(cv._act, ids) if a and cv.asked_on(a) in thread]
    rows = _ask_rows(st, acts, owner, set(ids))
    return {"key": key, "post": post, "items": [r["id"] for r in rows],
            "asks": rows, "posts": len(thread), "owner": owner,
            "cursor": at}


def asks(st, ids) -> dict:
    """`GET /fluid/api/needs-you?ids=`: each request as it now reads, in the
    order asked, open or not -- what a kept card reads to say what became of
    it. One that is not a request is `{"id", "error"}`."""
    cv, corpus = st.cv, st.cv.corpus
    found = {a["id"]: a for a in corpus.operational(id=ids)}
    acts = [found[i] for i in dict.fromkeys(ids) if i in found
            and found[i]["act"] == "expectation-recorded"]
    owner = wo.owner_of(cv)
    asking = ({i for _, i in asking_owner(cv, owner)}
              if owner is not None and acts else set())
    rows = {r["id"]: r for r in _ask_rows(st, acts, owner, asking)}
    return {"asks": [rows.get(i) or {"id": i, "error": "not a request"
                                     if i in found else
                                     "the record holds no such act"}
                     for i in ids],
            "limit": _read.BATCH}


# -- runs ------------------------------------------------------------------------

def runs(st, ids) -> dict:
    """`GET /fluid/api/runs?ids=`: each run -- its `execution-started` act --
    as it now reads, in the order asked: `run_state`'s state and words, from
    its end if the record holds one, as superseded if a later run on its
    handle ended (`closed_starts`), and otherwise from what this process
    observes of it."""
    cv, corpus = st.cv, st.cv.corpus
    acts = {a["id"]: a for a in corpus.operational(id=ids)}
    starts = [acts[i] for i in ids if i in acts and acts[i]["act"] == RUN_START]
    sids = [s["id"] for s in starts]
    handles = sorted({s["execution"] for s in starts if s.get("execution")})
    around = (corpus.operational(execution=handles, act=(RUN_START, *RUN_ENDS))
              if handles else [])
    own = corpus.operational(caused_by=sids, act=RUN_ENDS) if sids else []
    seq = corpus.operational_order([a["id"] for a in around + own])
    key = lambda a: seq.get(a["id"], -1)                    # noqa: E731
    closed = closed_starts(around, key)
    end_of = {}
    for e in sorted(own, key=key):
        end_of.setdefault(e["caused_by"], e)
    runtime = _runtime(st)
    held = runtime.get("runs")
    names = _read._names(corpus, [s["actor"] for s in starts])
    out = []
    for i in ids:
        s = acts.get(i)
        if s is None or s["act"] != RUN_START:
            out.append({"id": i, "error": "not a run" if s else
                        "the record holds no such act"})
            continue
        end = end_of.get(i)
        if end is None and i in closed:
            rs = {"state": "superseded", "source": "recorded",
                  "words": "no end recorded; a later run on the same handle "
                           "ended, so it is not open"}
        else:
            rs = run_state(s, end, None if end or held is None
                           else held.get(i))
            if end is None and held is None:
                rs.update(state="unknown", source="unknown",
                          words="execution open; what this process holds "
                                "could not be asked ("
                                + str(runtime.get("why_not")) + ")")
        d = s.get("detail") or {}
        out.append({
            "id": i, "runtime": s.get("runtime"),
            "model": d.get("requested_model") or d.get("selected_model")
            or rs.get("model"),
            "participant": s["actor"],
            "participant_name": names.get(s["actor"], s["actor"]),
            "conversation": s.get("conversation"), "post": s.get("turn"),
            "expectation": s.get("caused_by"),
            "state": rs.get("state"), "words": rs.get("words"),
            "source": rs.get("source"),
            "started_at": s.get("at"), "ended_at": end["at"] if end else None,
            # WHAT THIS SERVER HOLDS OF IT, for the card's Stop and its
            # live line (`run_state`, from `MentisService.agents_runs`).
            "held_here": bool(rs.get("held_here")),
            "activity": rs.get("activity"), "stopping": bool(rs.get("stopping")),
        })
    return {"runs": out, "limit": _read.BATCH,
            "runtime_why_not": runtime.get("why_not")}


def activity(st, *, limit, at) -> dict:
    """`GET /fluid/api/home/activity`: the runs `/api/working` shows -- every
    one the record says is open, newest first, then the most recently ended
    (`RECENT_ENDED`) -- as run ids, one page."""
    cv, corpus = st.cv, st.cv.corpus
    opened = sorted(cv.open_runs(), key=lambda a: a["at"], reverse=True)
    open_ids = [a["id"] for a in opened]
    ends = cv.history(act=RUN_ENDS, newest_first=True,
                      limit=RECENT_ENDED * 3)
    parents = [e["caused_by"] for e in ends if e.get("caused_by")]
    starts = {a["id"]: a for a in (corpus.operational(id=parents)
                                   if parents else ())}
    ended = []
    for e in ends:
        s = starts.get(e.get("caused_by"))
        if s is None or s["act"] != RUN_START or s["id"] in ended:
            continue      # failed before any run started: not a run
        ended.append(s["id"])
        if len(ended) >= RECENT_ENDED:
            break
    items = list(dict.fromkeys(open_ids + ended))
    return {"key": ACTIVITY, "items": items[:limit], "open": len(open_ids),
            "ended": len(ended), "total": len(items),
            "omitted": max(0, len(items) - limit), "limit": limit,
            "cursor": at}


# -- the briefing ------------------------------------------------------------------

def _period_now() -> str:
    h = time.localtime().tm_hour
    return next(k for k, (a, b) in PERIODS.items() if a <= h < b)


def briefing(st, *, period, day, limit, at) -> dict:
    """`GET /fluid/api/home/briefing?period=&date=`: the work that came back
    in one period of one day -- each `turn-said` act that carries
    `answers_request`, an execution's answer to somebody's request, as the
    Daily Briefing reads it -- newest first, one line each: the post's own
    first line, as it now reads.

    Mark IV writes no briefing per period, and this is not one: it is the
    day's returned work cut at the briefing's hours (`PERIODS`), in this
    server's local time. `date` is YYYY-MM-DD, today by default; `period`
    is the one it is now by default."""
    cv, corpus = st.cv, st.cv.corpus
    period = period or _period_now()
    if period not in PERIODS:
        raise _read.BadRequest("period is morning, lunch or evening")
    if day in (None, ""):
        day = _date.today()
    else:
        if not _DATE.fullmatch(day):
            raise _read.BadRequest(f"date is YYYY-MM-DD, not {day!r}")
        try:
            day = _date.fromisoformat(day)
        except ValueError as exc:
            raise _read.BadRequest(f"date is YYYY-MM-DD: {exc}")
    h0, h1 = PERIODS[period]
    midnight = datetime(day.year, day.month, day.day)
    start = (midnight + timedelta(hours=h0)).timestamp()
    end = (midnight + timedelta(hours=h1)).timestamp()
    acts = corpus.operational(act="turn-said", since=start, limit=BRIEF_SCAN)
    truncated = len(acts) >= BRIEF_SCAN and acts[-1]["at"] < end
    seen, rows = set(), []
    for a in reversed(acts):
        if a["at"] >= end or not a.get("turn") or a["turn"] in seen:
            continue
        if not (a.get("detail") or {}).get("answers_request"):
            continue
        seen.add(a["turn"])
        rows.append(a)
    page = rows[:limit]
    pids = [a["turn"] for a in page]
    entries = corpus.read(pids) if pids else []
    now = _read._now_reads(corpus, entries) if entries else {}
    homes = _read.homes_of(corpus, pids)
    items = []
    for a in page:
        cur = now.get(a["turn"]) or {}
        line = wo._plain_line(flow_text((cur.get("body") or {}).get("parts")))
        items.append({"post": a["turn"],
                      "conversation": homes.get(a["turn"])
                      or a.get("conversation"),
                      "line": wo._clip(line, LINE), "at": a["at"]})
    return {"key": BRIEFING, "period": period, "date": day.isoformat(),
            "from": start, "to": end, "items": items, "total": len(rows),
            "omitted": max(0, len(rows) - limit), "truncated": truncated,
            "limit": limit, "cursor": at}


# -- for you -----------------------------------------------------------------------

def for_you(st, *, before, limit, at) -> dict:
    """`GET /fluid/api/home/for-you`: recent posts that turn toward the
    owner -- addressed to them when written or later (`address_turn`), or
    replying to a post of theirs -- by anybody but the owner, newest first
    by when the post was written, one page. Read from the status file's
    `toward` index (`status.toward_page`), caught up first, so its cost
    does not grow with the posts recorded; `Store.toward_page`'s answer,
    which it equals, while that file is being built."""
    cv, corpus = st.cv, st.cv.corpus
    owner = wo.owner_of(cv)
    if owner is None:
        return _no_owner(FOR_YOU, at)
    rows = _status.toward_page(corpus, owner,
                               before=_read._page_key(corpus, before),
                               limit=limit + 1, **TOWARD_OWNER)
    page = rows[:limit]
    more = len(rows) > limit
    return {"key": FOR_YOU, "items": [r[0] for r in page],
            "before": _read._page_cursor(page[-1][2], page[-1][1])
            if more and page else None,
            "owner": owner, "limit": limit, "cursor": at}


# -- the change feed ---------------------------------------------------------------

def _requests_above(corpus, open_from, closed_from=()) -> tuple[set, dict]:
    """Every expectation at or above these acts on their causal chains, and
    the NEAREST one at or above each of `open_from` -- the request an act was
    recorded under, whose own answer it can change -- read a level per
    statement, at most CHAIN_DEPTH levels. `closed_from` are walked for the
    first only: a new request changes what is under its parent, not whether
    its parent is answered. (found ids, nearest id -> its act)."""
    found, nearest, seen = set(), {}, set()
    frontier = {p: False for p in closed_from if p}
    frontier.update({p: True for p in open_from if p})
    for _ in range(CHAIN_DEPTH):
        frontier = {p: o for p, o in frontier.items()
                    if (p, True) not in seen and (p, o) not in seen}
        if not frontier:
            break
        seen.update(frontier.items())
        nxt = {}
        for a in corpus.operational(id=list(frontier)):
            looking = frontier[a["id"]]
            request = a["act"] == "expectation-recorded"
            if request:
                found.add(a["id"])
                if looking:
                    nearest[a["id"]] = a
            if a.get("caused_by"):
                nxt[a["caused_by"]] = (nxt.get(a["caused_by"], False)
                                       or (looking and not request))
        frontier = nxt
    return found, nearest


def _asks_owner_moved(corpus, cv, nearest, acts, owner) -> bool:
    """MAY WHAT THE OWNER IS ASKED HAVE CHANGED? Needs you is the requests
    whose current carrier is the owner and that nobody has answered, so it
    moves only under a request the owner carries now -- recorded, answered,
    met or assigned to them -- or carried until an assignment in this
    stretch moved it away. A request of anybody else, and what is done
    under it, does not move it. With no owner named it is unknown, and
    whatever moves a request is said."""
    if not nearest:
        return False
    if owner is None:
        return True
    if owner in cv._carriers(list(nearest.values())).values():
        return True
    moved = sorted({a["caused_by"] for a in acts
                    if a["act"] == "expectation-assigned"
                    and a.get("caused_by") in nearest})
    if not moved:
        return False
    # WHO CARRIED IT BEFORE: `assigned_carrier`'s rule over the assignments
    # recorded before this stretch -- the latest by `at`, ties in write order
    new = {a["id"] for a in acts}
    earlier = {}
    for a in corpus.operational(caused_by=moved, act="expectation-assigned"):
        if a["id"] not in new and a["about"]:
            earlier.setdefault(a["caused_by"], []).append(a)
    for i in moved:
        got = sorted(earlier.get(i, ()), key=lambda a: a["at"])
        was = got[-1]["about"][0] if got else \
            (nearest[i].get("about") or [None])[0]
        if was == owner:
            return True
    return False


def _toward_owner_moved(corpus, owner, acts, entries, heads) -> bool:
    """MAY WHAT TURNS TOWARD THE OWNER HAVE CHANGED? For you is the posts by
    anybody else addressed to the owner -- when written, or later -- or
    replying to a post of theirs (`toward_page`), so it moves only when such
    a post is put in a Conversation, a reply to the owner's post is linked,
    or a post of somebody else's is addressed to the owner later. A post
    that does none of these does not move it."""
    posted = [frm for _eid, _d, frm, _to, rel in entries
              if rel == IN_CONVERSATION]
    replies = [(frm, to) for _eid, _d, frm, to, rel in entries
               if rel == REPLIES_TO]
    later = [a for a in acts if a["act"] == ADDRESSED and a.get("turn")]
    if not (posted or replies or later):
        return False
    if owner is None:
        return True

    def by(x):
        return (heads.get(x) or (None,) * 8)[7]

    if any(by(to) == owner and by(frm) != owner for frm, to in replies):
        return True
    later = [a for a in later if owner in (a.get("about") or ())]
    if later:
        authors = corpus.heads([a["turn"] for a in later])
        if any((authors.get(a["turn"]) or (None,) * 8)[7] != owner
               for a in later):
            return True
    theirs = sorted({p for p in posted if by(p) != owner})
    return any(owner in ((e.get("body") or {}).get("addressed_to") or ())
               for e in (corpus.read(theirs) if theirs else ()))


def _briefed_among(corpus, edited) -> bool:
    """Is any of these edited posts -- or the post a version is of -- one
    the briefing lists: an execution's answer to a request?"""
    turns = set(edited)
    for v in edited:
        chain = corpus.history(v)
        if chain:
            turns.add(chain[0])
    return any((a.get("detail") or {}).get("answers_request")
               for a in corpus.operational(turn=sorted(turns),
                                           act="turn-said"))


def changes_of(corpus, cv, *, acts, entries, heads, edited,
               renamed=()) -> tuple[set, set]:
    """What the Home hears of one stretch of the change feed: entity keys
    (`work:<id>`, `run:<id>`) and collection keys (`home:...`) that MAY have
    changed -- and only those. Where, never what: the client reads the
    bodies again. `acts` are the stretch's acts in full (`since`'s own).

    A RUN changes when it starts and when it ends -- its own end, or a later
    run's end on its handle, which closes it (`closed_starts`). A PIECE OF
    WORK changes when anything is recorded under it -- its runs and what
    they did, assignments, delegations, decisions, its being met -- or a
    reply answers its post: every request on the causal chain above such an
    act, or on the handle's newest run, is named. It changes too when the
    Conversation it is in is renamed (`renamed`: its `conversation_name`):
    every request recorded in that Conversation is named, and no other.

    THE COLLECTIONS: Work when a piece of work may have moved; Needs you
    only when a request the owner carries, or carried, may have
    (`_asks_owner_moved`); Activity when a run starts or ends; the Briefing
    when an answer to a request is said, or a post it lists is edited; For
    you only when a post may have come to turn toward the owner
    (`_toward_owner_moved`)."""
    ents, keys = set(), set()
    owner = wo.owner_of(cv)
    starts = [a for a in acts if a["act"] == RUN_START]
    ends = [a for a in acts if a["act"] in RUN_ENDS]
    ents.update(f"run:{a['id']}" for a in starts)
    if ends:
        parents = [e["caused_by"] for e in ends if e.get("caused_by")]
        for p in corpus.operational(id=parents) if parents else ():
            if p["act"] == RUN_START:
                ents.add(f"run:{p['id']}")
        handles = sorted({e["execution"] for e in ends if e.get("execution")})
        around = (corpus.operational(execution=handles,
                                     act=(RUN_START, *RUN_ENDS))
                  if handles else [])
        if around:
            seq = corpus.operational_order([a["id"] for a in around])
            key = lambda a: seq.get(a["id"], -1)            # noqa: E731
            new = {e["id"] for e in ends}
            ents.update(f"run:{i}" for i in closed_starts(around, key)
                        - closed_starts([a for a in around
                                         if a["id"] not in new], key))
    if starts or ends:
        keys.add(ACTIVITY)
    # -- the requests above what was recorded --------------------------------
    # an act's own request is the nearest at or above its causal parent; a
    # new request is its own, and its parent moves only as work
    up = {a["caused_by"] for a in acts if a.get("caused_by")
          and a["act"] != "expectation-recorded"}
    up.update(a["id"] for a in acts if a["act"] == "expectation-recorded")
    parents_of_new = {a["caused_by"] for a in acts if a.get("caused_by")
                      and a["act"] == "expectation-recorded"}
    # an act inside a run whose chain does not reach its start: the request
    # of the newest run on that handle
    loose = sorted({a["execution"] for a in acts if a.get("execution")
                    and a["act"] not in (RUN_START, *RUN_ENDS)})
    if loose:
        newest = {}
        for s in corpus.operational(execution=loose, act=RUN_START):
            newest[s["execution"]] = s       # write order: the last wins
        up.update(s["caused_by"] for s in newest.values() if s.get("caused_by"))
    replied = [to for _eid, _d, _frm, to, rel in entries if rel == REPLIES_TO]
    if replied:
        for a in corpus.operational(turn=sorted(set(replied)),
                                    act="expectation-recorded"):
            up.add(a["id"])
    # DONE ON A BLOCK answers the input asked on its post (P4, P11): the
    # `marked-ready` act causes nothing, so its post names the request.
    readied = sorted({a["turn"] for a in acts
                      if a["act"] == "marked-ready" and a.get("turn")})
    if readied:
        for a in corpus.operational(turn=readied,
                                    act="expectation-recorded"):
            if (a.get("detail") or {}).get("expects") == "input":
                up.add(a["id"])
    requests, nearest = (_requests_above(corpus, up, parents_of_new)
                         if up or parents_of_new else (set(), {}))
    ents.update(f"work:{e}" for e in requests)
    if requests:
        keys.add(WORK)
    if _asks_owner_moved(corpus, cv, nearest, acts, owner):
        keys.add(NEEDS_YOU)
    # -- a rename: the name every piece of work in it is read with ------------
    if renamed:
        ents.update(f"work:{a['id']}" for a in corpus.operational(
            conversation=sorted(renamed), act="expectation-recorded"))
    # -- what was said ---------------------------------------------------------
    if any(a["act"] == "turn-said"
           and (a.get("detail") or {}).get("answers_request") for a in acts) \
            or (edited and _briefed_among(corpus, edited)):
        keys.add(BRIEFING)
    if _toward_owner_moved(corpus, owner, acts, entries, heads):
        keys.add(FOR_YOU)
    return ents, keys
