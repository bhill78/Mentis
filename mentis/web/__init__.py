"""The Mentis web surface: the public semantic seam over HTTP. Headless.

One production server. No second backend and no framework -- `http.server` from
the standard library, because the whole job is handing the public seam's own
answers to whatever asks: an interface, a script, a dispatched agent's MCP
bridge (`/api/worker`). It serves no UI files; an interface is a separate
client of this API. Agents run through MARS (`mentis.execution`).

EVERY endpoint returns a COMPUTED SEMANTIC RESULT, never rows for the client to
interpret. Standing, Topic focus, orientation, expectation state, operational
ancestry, delivery truth and resurrection are all decided here, by Mentis,
exactly as they are for an agent. The browser is another ingress, not another
implementation -- if the UI could compute it, two things would decide it and
they would drift.

Writes are deliberately few: a Turn, a late addressing, an expectation. Late
addressing is the interesting one -- it records an operational act and creates
no Turn, which is the invariant the UI most easily breaks.
"""

from __future__ import annotations

import hashlib

from mentis.corpus.store import (DAY_TO_DAY as _DAY_TO_DAY,
                                 Corpus as _Manifest,
                                 role_at as _role_at)

import json
import os
import sys
import pathlib
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import mentis.api as api
from mentis.api.errors import CatalogueUnavailable
from mentis import artifacts as _artifacts
from mentis import presentation as _presentation
from mentis import working_scenes as _working_scenes
from mentis import vocabulary
from mentis.conversation import (content_of, rendering_of, standing_state,
                                 text as text_part)
from mentis.web.dispatch import dispatch_soon
from mentis.spine.store import beside_writer_refused, reading_beside_writer
# WRITING A POST IS A DOMAIN OPERATION (`mentis/conversation/posting.py`),
# shared with Fluid's command door. The names this module and its callers
# have always used for its vocabulary and helpers are kept as they were.
from mentis.conversation import posting as _posting
from mentis.conversation.posting import (                # noqa: F401
    ASK_MENTIS, ASK_PARTICIPANT, INTAKE_ACTIONS, INTAKE_REQUIRES, RECORD_ONLY,
    carry_unaddressed as _carry_unaddressed, continuation as _continuation,
    owe as _owe)
# Imported here, at process start, because that is when it reads which commit
# is running. Imported later it would read whatever was checked out then.
from mentis.web import identity as _identity            # noqa: F401


class _State:
    """One corpus, one Brain, one execution registry, for this process.

    Live executions are machine-local by design, so what this server can see is
    what it started. The UI says so rather than implying it sees every runtime.
    """

    def __init__(self, corpus_path: str, workspace: str | None = None,
                 answers_at: str | None = None,
                 writable: tuple[str, ...] = (),
                 execution=None):
        self.path = str(pathlib.Path(corpus_path).resolve())
        self.answers_at = answers_at
        # A SERVER NEVER HALF-RUNS ON A READ-ONLY BRAIN: anything the schema
        # check does not open writable -- unadopted, needing migration or a
        # newer Mentis, needing attention -- is refused here, in words
        # (`BrainNotWritable`). A missing Brain is `BrainMissing`: serving
        # never creates one (D2, `mentis.spine.migrations`).
        self.corpus = api.open_corpus(corpus_path, access="write")
        for line in self.corpus.schema_status.warnings:
            print(f"schema: WARNING: {line}")
        self.brain = api.brain(self.corpus)
        self.cv = self.brain.conversations
        # TWO STORES, AND THEY STAY TWO. The spine above holds the record --
        # Turns, acts, durable objects. The service below keeps its own
        # append-only instance corpus, which is where a summoned agent is
        # registered. `mentis/web/dispatch.py` says what that costs.
        #
        # AND AGENTS RUN THROUGH `execution` (`mentis.execution`): MARS in a
        # server, `FakeExecution` in tests. None gives a service whose runs
        # are refused as `backend_unavailable`, saying why.
        self.agents = api.connect(str(pathlib.Path(corpus_path) / "instances"),
                                  execution=execution)
        # WORKERS MAY ASK ABOUT THE RECORD THEY WERE DISPATCHED FROM. This is
        # the spine, not the instance corpus above: the question a worker gets
        # asked is about Conversations, Turns and acts. `answers_at` is
        # where THIS process can be asked about it, which a worker needs
        # because it may not open the corpus itself.
        self.agents.workers_read(str(pathlib.Path(corpus_path).resolve()),
                                 answers_at=answers_at,
                                 writable=tuple(str(pathlib.Path(w).resolve())
                                                for w in writable))
        # Where a dispatched agent works when its request declares no
        # repository directory of its own (`dispatch.declared_workspace`).
        # Not the corpus: an agent asked to do something to a repository
        # needs the repository.
        self.workspace = str(pathlib.Path(workspace or ".").resolve())
        self.writable = tuple(str(pathlib.Path(w).resolve()) for w in writable)
        # AN AGENT'S PERMISSION REQUESTS are answered under Mentis's
        # authority: the run's grant for its own reads and workspace edits,
        # the owner through a decision form for the rest
        # (`mentis/web/permissions.py`).
        from mentis.web.permissions import make_policy
        if hasattr(self.agents, "permission_policy"):
            self.agents.permission_policy = make_policy(self)


def _surface(st):
    """The reference resolver, over the corpus this server already holds."""
    from mentis.worker import Surface
    if getattr(st, "_refs", None) is None:
        st._refs = Surface(st.path, corpus=st.corpus)
    # What a delegation judges a Participant's declared default by
    # (`dispatch.runtime_judge`); None where no agent service is attached.
    st._refs.agents = getattr(st, "agents", None)
    return st._refs


def _answering_reply(st, e) -> dict | None:
    """The reply that answered one expectation, enough to name it.

    The NEWEST reply by whoever carries it, which is what the interface showed
    before: a later word on the same ask is the answer that stands.

    AS THE TURN NOW READS, like every other read of a Turn. This went to the
    corpus row directly and so showed the words the reply was WRITTEN with: an
    answer the author corrected was still quoted with its mistake, and an answer
    they deleted was republished -- in the payload sent to everyone reading the
    Conversation, not only to its author. `presented` is where the record says
    which version stands and that a deleted body is blank; there is no second
    reading of an edit or a deletion, and this is not one.
    """
    from mentis.conversation.versions import presented
    cv, corpus = st.cv, st.corpus
    ids = e.get("replies_from_expected") or ()
    if not ids:
        return None
    got = corpus.read(list(ids))
    if not got:
        return None
    entry = presented(corpus, max(got, key=lambda x: x["recorded_at"]))
    parts = (entry.get("body") or {}).get("parts") or []
    said = " ".join(p.get("text") or "" for p in parts
                    if p.get("type") == "text").strip()
    return {
        "turn": entry["id"],
        "number": cv.turn_number(entry["id"]),
        "said": said,
        "author": entry["attributed_to"],
        "chose": next((a["detail"]["chose"] for a in corpus.operational(
                          turn=entry["id"])
                       if a["act"] == "turn-said"
                       and (a.get("detail") or {}).get("chose")), None),
        # WHETHER THIS REPLY WITHDREW THE ASK rather than answering it.
        "withdrawn": bool(e.get("withdrawn")
                          and e["withdrawn"].get("reply") == entry["id"]),
    }


def _filing_view(st, f) -> dict:
    """One filing or link from `filings_of`, with names a person reads."""
    from mentis.conversation.versions import presented
    cv, corpus = st.cv, st.corpus
    got = corpus.read([f["to"]])
    return {**f, "by_alias": cv.alias(f["by"]),
            "name": (presented(corpus, got[0])["body"] or {}).get("name")
            if got else None,
            "ended": ({**f["ended"], "by_alias": cv.alias(f["ended"]["by"])}
                      if f["ended"] else None)}


def _linked_view(st, link, here) -> dict:
    """A Turn from another Conversation, as it is shown HERE through a
    `linked-into` link: the post itself -- author, time, words, as it now
    reads -- with its home number, and where it lives and who linked it."""
    from mentis.conversation.versions import presented
    cv, corpus = st.cv, st.corpus
    entry = presented(corpus, corpus.read([link["link"]["from"]])[0])
    home = cv.conversation_of(entry["id"])
    view = _turn_view(st, entry, cv.turn_number(entry["id"]), shown_in=here)
    view["linked"] = {
        "link": link["id"], "home": home,
        "home_name": cv.conversation_name(home),
        "by": link["attributed_to"], "by_alias": cv.alias(link["attributed_to"]),
        "at": link["recorded_at"]}
    return view


def in_view(rows, wanted, *, recent=None, key=lambda r: r["turn"]):
    """Which rows a Conversation read answers with: THE TOPIC FIRST, THEN ANY
    WINDOW.

    THE ORDER IS THE WHOLE POINT, and it lives here rather than inline so that
    it can be said once and tested. A Topic is a way of REACHING material, most
    of which is old; a history window is a way of not sending all of it at once.

    Window first, and a Topic stops being a reach: focusing a Topic whose thirty
    Turns are spread across a year would show only the few that happened to fall
    inside the newest N, and `TopicRail`'s "N outside this topic" would be
    counting the window rather than the Topic -- a number that reads as a fact
    about the Topic and would not be one.

    Topic first, and a Topic keeps meaning what it says: every Turn filed under
    it, of which this read is sending the most recent N.

    NOTHING PASSES `recent` YET. The windowing it is for is later work; the
    argument exists so the contract is written down and under test BEFORE
    anything depends on getting it right, which is the one moment when that is
    cheap. `wanted` None means no Topic is in force and every row is in view.

    ROWS ARRIVE IN THE RECORD'S OWN ORDER, oldest first, and a window takes the
    TAIL -- which is what makes the tail the most recent N rather than merely
    the end of a list. That is a precondition, not an accident: `cv.turns` is
    ordered by the link rows and `_links_now` says "oldest first" in its own
    docstring. Hand this an unordered list and the window means nothing.
    """
    chosen = [r for r in rows if wanted is None or key(r) in wanted]
    if recent is None:
        return chosen
    if recent < 0:
        raise ValueError("recent is a count of contributions, not a negative")
    return chosen[-recent:] if recent else []


#: HOW MUCH A CONVERSATION OPENS WITH. Threads unfocused, Turns under a
#: Topic -- see `_scope_units`. Measured, and a LOADING default only: nothing
#: older becomes unreachable, it arrives as the reader scrolls back to it.
DEFAULT_BATCH = 20


def _reply_chain(corpus, turns):
    """Who each of these Turns answers, in ONE read.

    Asking per Turn is the cost a bounded read exists to avoid: once for the
    Turn and once per ancestor while walking up is 80,000 queries to show
    fifty of a deep thread.

    ONLY THESE TURNS, NOT THE WHOLE RECORD. Every walk of the chain starts at a
    Turn in hand and climbs only while the next Turn is in hand too
    (`_threads_of`, `_ancestry`, `_subtree`, `_placed`), so the keys it ever
    looks up are the Turns it was built for. Reading every `replies-to` in the
    corpus to answer that was a scan of every entry, and grew with the whole
    Brain, Source Admissions included (R2). First link wins, in append order,
    exactly as before. `turns=None` is the whole record, as it was.
    """
    chain = {}
    for x in corpus.links(relation="replies-to", frm_any=turns):
        chain.setdefault(x["link"]["from"], x["link"]["to"])
    return chain


def _threads_of(rows, chain):
    """Each Turn's thread root, and each root's descendants, in memory.

    A Turn that answers nothing is a root. A Turn that answers something
    belongs to the thread of whatever it ultimately answers, however deep the
    chain. Cycle-guarded, because a corpus is appended to by many hands.
    """
    here = {r["turn"] for r in rows}
    order = {r["turn"]: r["number"] for r in rows}
    root_of, under = {}, {}

    def climb(tid):
        """The Turn this one ultimately answers.

        A CYCLE STILL HAS TO HAVE A ROOT. The guard used to stop the walk and
        return wherever it had got to, which for `A answers B answers A` gave
        `root_of[A] = B` and `root_of[B] = A` -- so NEITHER was its own root.
        A Turn that is nobody's root is in no thread: it never appeared in the
        flow, was never counted in the totals, and the thread read refused it
        and refused its "real" root in a loop. Both Turns were unreachable
        through the interface, silently. The oldest Turn of the cycle is the
        root, which is the same answer whichever Turn the walk entered at.
        """
        seen, up = set(), tid
        while True:
            nxt = chain.get(up)
            if nxt is None or nxt not in here:
                return up
            if nxt in seen or nxt == tid:
                ring = seen | {up, nxt}
                return min(ring, key=lambda t: (order.get(t, 0), t))
            seen.add(up)
            up = nxt

    for r in rows:
        root = climb(r["turn"])
        root_of[r["turn"]] = root
        if r["turn"] != root:
            under.setdefault(root, []).append(r)
    return root_of, under


def _ancestry(tid, chain, here):
    """The Turns from the thread's root down to this one, inclusive.

    Cycle-guarded, like every other walk of `replies-to`.
    """
    out, seen, up = [tid], {tid}, chain.get(tid)
    while up in here and up not in seen:
        out.append(up)
        seen.add(up)
        up = chain.get(up)
    out.reverse()
    return out


def _subtree(rows, chain):
    """Every Turn under each Turn, not just under each root.

    `under` is keyed by ROOT, so asking it what is beneath a reply answered
    nothing: a filed reply standing at top level in a focused flow reported
    `thread_replies: 0` with twelve replies under it, and the foot's reply
    count, its faces and the door into that sub-thread all disappeared. This
    is the same walk asked of every Turn. Cycle-guarded for the same reason
    the climb is.
    """
    here = {r["turn"]: r for r in rows}
    kids = {}
    for r in rows:
        up = chain.get(r["turn"])
        if up in here and up != r["turn"]:
            kids.setdefault(up, []).append(r)
    out = {}
    for tid in here:
        got, seen, stack = [], {tid}, list(kids.get(tid, ()))
        while stack:
            r = stack.pop()
            if r["turn"] in seen:
                continue
            seen.add(r["turn"])
            got.append(r)
            stack.extend(kids.get(r["turn"], ()))
        got.sort(key=lambda r: r["number"])
        out[tid] = got
    return out


def _scope_units(rows, wanted, root_of):
    """WHAT THIS READ PAGES BY, which is what the flow DRAWS.

    Unfocused, the Conversation flow renders thread ROOTS -- replies live in
    the thread rail -- so the unit is the thread. A page of threads cannot
    stop in the middle of one, which is why nothing here has to borrow an
    ancestor to keep a thread coherent: the question does not arise.

    With a Topic in force the flow draws the Topic's Turns flat, promoting a
    filed reply whose parent is not filed, so the unit is the TURN. That is
    not a second design: it is the same rule -- page by what is drawn -- and
    the two modes are kept apart by `unit` in the answer and by separate
    cursors, so neither mode's position can be read as the other's.

    THE TOPIC IS APPLIED FIRST, through `in_view`, which is where that order is
    said and tested. The batch is then taken from what the Topic reaches -- the
    Topic's own newest N -- and never from the Conversation's newest N filtered
    by the Topic, which would turn a reach into a window.
    """
    if wanted is not None:
        return in_view(rows, wanted), "turn"
    return [r for r in rows if root_of.get(r["turn"]) == r["turn"]], "thread"


def _root_of_turn(st, tid):
    """The thread one Turn is in, by `answers` alone. None if it is not in a
    Conversation -- which is a different answer from being its own root."""
    cv, corpus = st.cv, st.corpus
    conv = cv.conversation_of(tid)
    if not conv:
        return None
    rows = cv.turns(conv)
    root_of, _ = _threads_of(rows, _reply_chain(corpus, [r["turn"] for r in rows]))
    return root_of.get(tid, tid)


def _batch_asked(one, units):
    """Which bounded batch was asked for, or a refusal saying why not.

    A target that is not a unit of this scope is refused BY NAME. Answering
    the newest batch instead would be a different question answered silently,
    which is the one failure that cannot be told from success.
    """
    at = {u["turn"]: i for i, u in enumerate(units)}
    by_number = {u["number"]: u["turn"] for u in units}
    raw = one("batch")
    if raw is None:
        size = DEFAULT_BATCH
    elif str(raw).strip().lower() == "all":
        size = None
    else:
        text = str(raw).strip()
        # `str.isdigit` is true of '²' and `int` refuses it, so the guard
        # that exists to refuse by name raised instead. Ascii digits only.
        if not (text and all("0" <= ch <= "9" for ch in text)):
            return None, {"error": f"batch={raw!r} is not a count of units; "
                                   "give a whole number, 0, or 'all'",
                          "batch": raw}
        size = int(text)

    asked = {k: one(k) for k in ("before", "after", "around")
             if one(k) is not None}
    if len(asked) > 1:
        return None, {"error": "a batch sits before, after or around one "
                               "unit, never more than one of those",
                      **asked}
    total = len(units)
    if not asked:
        lo = 0 if size is None else max(0, total - size)
        return {"lo": lo, "hi": total,
                "mode": "all" if size is None else "recent",
                "size": size}, None

    name, value = next(iter(asked.items()))
    text = str(value).strip()
    numeric = bool(text) and all("0" <= ch <= "9" for ch in text)
    tid = by_number.get(int(text)) if numeric else text
    if tid not in at:
        return None, {"error": f"{text} is not in this view, so there is no "
                               "batch at it",
                      name: value}
    i = at[tid]
    n = DEFAULT_BATCH if size is None else size
    if name == "before":
        return {"lo": max(0, i - n), "hi": i, "mode": "before", "size": n}, None
    if name == "after":
        return {"lo": i + 1, "hi": min(total, i + 1 + n),
                "mode": "after", "size": n}, None
    half = n // 2
    lo = max(0, i - half)
    hi = min(total, lo + n)
    return {"lo": max(0, hi - n), "hi": hi, "mode": "around", "size": n}, None


def _placed(view, tid, *, root_of, chain, under, in_scope, numbers):
    """The read-relative facts a bounded reader needs, stated rather than
    inferred.

    Each one exists because the interface used to work it out from what it had
    been sent, which is a question about the response wearing the clothes of a
    question about the record:

      `root`             which thread this belongs to. The flow decides what is
                         a top-level post with it, instead of asking whether a
                         parent happens to be loaded -- which promoted every
                         reply whose parent was older into a post of its own.
      `answering_number` the coordinate of what it answers, so a reply can say
                         what it replies to with that Turn nowhere in hand.
      `parent_in_scope`  whether the parent is within THIS read's scope. With a
                         Topic in force the flow stands a filed reply at top
                         level when its parent is not filed; that test was
                         `!loaded(parent)`, true of everything once reads are
                         bounded. This is the same question asked of the record.
      `thread_replies`   how many Turns are under THIS Turn, whole, so the
                         foot's count is the record's and not the window's.
                         Under a root that is the thread; under a reply it is
                         what hangs off the reply, which `under` -- keyed by
                         root -- answered as nothing.
      `thread_repliers`  who they are, for the faces beside that count.
    """
    kids = under.get(tid, ())          # every Turn under THIS one
    view["root"] = root_of.get(tid, tid)
    parent = chain.get(tid)
    view["answering_number"] = numbers.get(parent) if parent else None
    view["parent_in_scope"] = (None if not parent
                               else parent in in_scope)
    view["thread_replies"] = len(kids)
    seen, faces = set(), []
    for r in reversed(kids):
        who = r["entry"]["attributed_to"]
        if who in seen:
            continue
        seen.add(who)
        faces.append(who)
        if len(faces) == 3:
            break
    view["thread_repliers"] = faces
    return view


def _turn_view(st, entry, number=None, shown_in=None) -> dict:
    """One Turn as a reader sees it. `shown_in` is the Conversation it is
    being shown in -- its own unless it is shown there as a link -- and its
    `topics` are that Conversation's: a Turn filed in two Conversations must
    not hand either one the other's Topics."""
    from mentis.conversation import anchors as _anchors
    cv, corpus = st.cv, st.corpus
    shown_in = shown_in or cv.conversation_of(entry["id"])
    addressees = cv.addressees_of(entry["id"])
    rows = []
    for who in addressees["all"]:
        status = cv.status_of(entry["id"], who)
        later = next((x for x in addressees["later"]
                      if x["participant"] == who), None)
        rows.append({
            "participant": who, "alias": cv.alias(who),
            "addressed": status["addressed"] or bool(later),
            "delivered": status["delivered"],
            "responded": status["responded"],
            "failed": status["failed"],
            "addressed_later": bool(later),
            "addressed_by": cv.alias(later["by"]) if later else None,
            "addressed_because": later["because"] if later else None,
        })
    on_turn = corpus.operational(turn=entry["id"])     # read once, used four times
    # THE DECISION FORMS ON THIS POST (P7): asked `on` it, or put on it as a
    # run's answer post. Each with every question and what became of it --
    # what a view needs to draw the form (P9).
    forms = [f for f in map(cv.decision_form,
                            cv.decision_forms_on(entry["id"])) if f]
    form_questions = [q["expectation"] for f in forms
                      for q in f["questions"]]
    expectations = [st.cv.expectation_state(i) for i in dict.fromkeys(
        [a["id"] for a in on_turn if a["act"] == "expectation-recorded"]
        + form_questions)]
    # WHICH RUN POSTED THIS, from the acts already in hand. The footer read it
    # off the Conversation's first thousand acts, which are its OLDEST, so the
    # newest Turns -- the ones being read -- had none. Same rule as before:
    # acts recorded in the Conversation it is shown in, carrying an execution,
    # never `execution-started` (that names the run this Turn LAUNCHED), and
    # the latest one wins.
    ran = [a for a in on_turn
           if a.get("execution") and a["act"] != "execution-started"
           and a.get("conversation") == shown_in]
    return {
        "id": entry["id"],
        "number": number if number is not None else cv.turn_number(entry["id"]),
        # WHAT STANDS BEHIND EACH PART, read now: held, missing, corrupt or
        # purged are different answers, and only `held` has bytes to draw.
        # AN ANCHOR PART SAYS WHERE IT POINTS, resolved now: the exact place,
        # its excerpt from the immutable version, or that the source was
        # deleted. Nothing about it is stored on the Turn but the reference.
        "parts": [_anchors.annotate_part(cv, p) if p.get("type") == "anchor"
                  else _artifacts.annotate_part(corpus, p)
                  for p in entry["body"]["parts"]],
        # THE ANCHORS IN THIS TURN, each with what is attached to it -- the
        # current reactions, the anchored replies, the deep dives. History of
        # each is `/api/anchors/<id>/interactions`.
        "anchors": _anchors.anchors_on(cv, entry["id"]),
        # RETURNED BY THE RUN THAT POSTED THIS, not part of it. Read off the
        # act that recorded the reply, which named them; never out of prose.
        "returned_with": [
            _artifacts.public(_artifacts.describe(corpus, ref,
                                                  verify="cached"))
            for a in on_turn
            if a["act"] in ("result-returned", "result-recovered")
            for ref in (a.get("detail") or {}).get("returned_artifacts") or []
            # A DELETED TURN SHOWS NOTHING AS CURRENTLY USABLE, including what
            # the run that posted it returned. Its Details still say so.
            if not entry.get("deleted")],
        # A REPLY NOTHING IN MENTIS SAW ARRIVE. The runtime wrote it; somebody
        # recovered it afterwards because the waiter that should have posted it
        # was gone. Said on the Turn so it is never read as an ordinary reply.
        #
        # ASKED OF THIS TURN AND NOT OF THE RUN. A recovery whose run had
        # ALREADY answered through `respond` recovers only the ENDING: the Turn
        # was written through the worker door and Mentis observed every byte of
        # it. Saying "recovered -- end not observed" of that answer is false, so
        # the act's own `response_owner` decides. The act still names this Turn,
        # because what the run RETURNED is read off it and orphaning it made a
        # recovered run's files invisible everywhere.
        "recovered": next((
            {"act": a["id"], "by": a["actor"], "by_alias": cv.alias(a["actor"]),
             "at": a["at"], "because": a.get("because"),
             "source": ((a.get("detail") or {}).get("evidence") or {})
             .get("source")}
            for a in on_turn
            if a["act"] == "result-recovered"
            and (a.get("detail") or {}).get("response_owner") != "respond"),
            None),
        "execution": ran[-1]["execution"] if ran else None,
        "runtime": ran[-1]["runtime"] if ran else None,
        "author": entry["attributed_to"],
        "author_alias": cv.alias(entry["attributed_to"]),
        "written_by": entry["written_by"],
        "at": entry["recorded_at"],
        "addressees": rows,
        "topics": cv.topics_of(entry["id"], shown_in),
        # WHICH OTHER CONVERSATIONS SHOW IT, AS A LINK. It belongs to one.
        "linked_into": cv.linked_into(entry["id"]),
        "answering": next((x["link"]["to"] for x in
                           corpus.links(relation="replies-to", frm=entry["id"])),
                          None),
        "replies": [x["link"]["from"] for x in
                    corpus.links(relation="replies-to", to=entry["id"])],
        # WHICH OFFERED ALTERNATIVE THIS REPLY CHOSE, as its author set it when
        # posting -- or None, which is every Turn that chose none.
        "chose": next((a["detail"]["chose"] for a in corpus.operational(
                          turn=entry["id"])
                       if a["act"] == "turn-said"
                       and (a.get("detail") or {}).get("chose")), None),
        # WHAT IS OWED, WHERE IT WAS ASKED. Every state the operating loop can
        # be in is a FIELD here and not a status this computes: recorded, whom
        # it is assigned to, whether a run is live, what it delegated, what
        # failed, whether anything claimed it answered, and -- the state that
        # used to be invisible -- unassigned, with the reason. An interface
        # composes those into words; a workflow board would have to invent a
        # state machine to hold the same facts, and then two things would decide
        # what is true.
        "expectations": [_expectation_view(st, e, entry)
                         for e in expectations],
        "decision_forms": forms,
        "operational_acts": len(corpus.operational(turn=entry["id"])),
        "discovered_under": _discovered_under(st, entry["id"]),
        # AGENT WORK, folded away by default (`conversation.agent_work`):
        # `{kind, why, to, to_name}`, or None for everything the owner reads.
        "agent_work": _agent_work_of(st, entry["id"]),
        # EDITED AND DELETED ARE FACTS OF THE TURN'S LINE, read from the
        # record (`versions.presented`). `parts` above is already the current
        # version's; a deleted Turn's parts are empty, and what it said is
        # disclosed only by its Details.
        "revision": entry.get("revision"),
        "deleted": ({**entry["deleted"],
                     "by_alias": cv.alias(entry["deleted"]["by"])}
                    if entry.get("deleted") else None),
    }


def _agent_work_of(st, tid):
    """Whether this Turn is agent-to-agent chatter, and why (or None)."""
    from mentis.conversation import agent_work
    from mentis.operational.work_overview import owner_of
    return agent_work.classify(st.cv, [tid], owner_of(st.cv)).get(tid)


def _expectation_view(st, e, entry=None) -> dict:
    """One expectation as a reader sees it, from `expectation_state` -- on
    the Turn view (`entry`, the post it is shown on), and for a question of
    a decision form that is on no post yet (`entry` None), where nothing
    could be continued by replying to it (`decisions_read`)."""
    cv, corpus = st.cv, st.corpus
    return {
        "id": e["expectation"], "expects": e["expects"],
        "of": e["expected_of"],
        "of_alias": cv.alias(e["expected_of"]) if e["expected_of"] else None,
        "by": e["recorded_by"], "by_alias": cv.alias(e["recorded_by"]),
        # The requester's recorded reason. The QUESTION itself is not
        # durable anywhere -- it lives only in the Turn's prose -- and
        # neither are candidate answers, so neither is shown.
        "because": e.get("because"),
        # WHAT THE ASKER STATED THE ALTERNATIVES WERE, if it stated any.
        # None is "none were stated", never "no alternatives exist":
        # the owner can always answer in their own words.
        "options": e.get("options"),
        # WHAT THE ASK NAMES, where it names governed material.
        # `expectation_state` has always computed this and this view threw
        # it away, so no surface could tell an ask that concerns governed
        # material from one that concerns none -- which is the difference
        # between a bounded decision about an item and global triage, and
        # it is also what the governance links on the card are drawn from.
        # EMPTY IS NOT A CLAIM THAT IT CONCERNS NOTHING: it says nobody
        # wrote down what.
        "material": e["material"],
        "response_present": e["response_present"],
        "live_execution": bool(e["live_execution"]),
        # NOBODY IS CARRYING THIS, which is not the same as nobody having
        # replied. `unresolved_because` is the intake act's own words.
        "unassigned": e["unassigned"],
        "unresolved_because": next(
            (a["because"] for a in corpus.operational(
                caused_by=e["expectation"])
             if a["act"] == "assignment-unresolved"), None),
        # Claimed answered, by whom, and how many acts said so. Kept apart
        # from `response_present`: a reply is not a claim of success.
        "satisfied_by": e["satisfied_by"],
        # CLOSED WITHOUT AN ANSWER: who withdrew it, when and why, or
        # None. Read before `satisfied_by`, which also names this act.
        "withdrawn": ({**e["withdrawn"],
                       "by_alias": cv.alias(e["withdrawn"]["by"])}
                      if e["withdrawn"] else None),
        # AND THE REPLY THAT ANSWERED IT, where one did. The interface
        # names the alternative taken and quotes the owner's own words, and
        # it found that reply by searching the Turns it had been sent. A
        # reply is never a thread root, so a bounded flow sends none of
        # them: every answered ask fell back to "the record shows this was
        # answered", losing the choice and the words. `expectation_state`
        # already knows which reply; this says what it was.
        "answered_by": _answering_reply(st, e),
        # WAITING ON SOMEBODY ELSE. Each delegation names the child
        # expectation to go and ask about.
        "delegations": e["delegations"],
        "failures": e["failures"],
        "requires": e["requires"],
        # WHAT A WAKE-CHECK REVIEW WAS ABOUT. Wake checks are gone (agents
        # run through MARS), so nothing is read for it; the key stays for
        # readers of this shape.
        "stopped_work": None,
        # WHETHER ANSWERING THIS WOULD CONTINUE AUTHORISED WORK, asked of
        # the machinery that would actually do it rather than guessed from
        # the shape of the ask. The interface offers "decide and continue"
        # with the words "also hands the work back", and said them whether
        # or not anything could be handed back -- so when the asker's own
        # request had already been closed, the owner was promised a
        # continuation `continuation_candidates` had no candidate for, and
        # got a run with no authority at all. This is the same read that
        # decides it, so the promise and the outcome cannot disagree.
        #
        # IT IS NOT A SECOND CONTINUATION PATH AND RESURRECTS NOTHING. It
        # answers one question -- is there authorised work this reply would
        # continue -- and finished work is still finished.
        "continues_work": bool(
            cv.continuation_candidates(
                entry["id"], requester=e["expected_of"],
                carrier=entry["attributed_to"]))
        if entry and e["expected_of"]
        and e["expected_of"] != entry["attributed_to"]
        else False,
        # A QUESTION OF A DECISION FORM (P7): which form, its place in
        # it and its own words -- its post holds no question text -- and
        # the reply that answered it. Absent for any other ask.
        **({"form": e["form"], "index": e["index"],
            "question": e["question"], "answer": e["answer"]}
           if e.get("form") else {}),
    }


def decisions_read(st, post=None, ids=()) -> dict | None:
    """WHAT A DECISION FORM IS DRAWN FROM, IN EVERY VIEW (forms build P9).

    `post`: every ask on that post as its Turn view states them -- each
    decision form on it (asked `on` it, or put on it as a run's answer
    post) with every question, and each ask recorded on the post itself,
    which is every decision asked before P7 and a single question asked as
    its own post. None when it is not a post. `ids`: these asks wherever
    they are, for the questions of a form on no post yet, which only Needs
    You shows. Classic, every Fluid view and the Needs You zone draw the
    same form from this; the UI groups it (experimental/decisions.ts).
    `you` is the owner these doors answer as."""
    from mentis.conversation.versions import presented
    from mentis.conversation.owner import _owner
    cv, corpus = st.cv, st.corpus
    if post:
        got = corpus.read([post])
        if not got or not cv._is(got[0], "contribution"):
            return None
        view = _turn_view(st, presented(corpus, got[0]))
        return {"post": {"id": view["id"], "number": view["number"],
                         "author": view["author"],
                         "author_alias": view["author_alias"],
                         "topics": view["topics"],
                         "conversation": cv.conversation_of(post),
                         "deleted": bool(view["deleted"])},
                "you": _owner(cv), "expectations": view["expectations"],
                "decision_forms": view["decision_forms"]}
    forms, asks = {}, []
    for i in ids:
        a = cv._act(i)
        if not a or a["act"] != "expectation-recorded":
            continue
        fid = (a.get("detail") or {}).get("form")
        if fid and fid not in forms:
            forms[fid] = cv.decision_form(fid)
        if not fid:
            asks.append(i)
    wanted = [q["expectation"] for f in forms.values() if f
              for q in f["questions"]] + asks
    views = []
    for i in dict.fromkeys(wanted):
        turn = cv.asked_on(i)
        entry = (presented(corpus, corpus.read([turn])[0])
                 if turn and corpus.read([turn]) else None)
        views.append(_expectation_view(st, cv.expectation_state(i), entry))
    return {"post": None, "you": _owner(cv), "expectations": views,
            "decision_forms": [f for f in forms.values() if f]}


def _discovered_under(st, turn) -> dict | None:
    """Which request's Turn this Turn was discovered under, COMPUTED.

    A finding recorded with `record_discovered_work` is its own Turn and its
    own unassigned expectation, and its `work-discovered` act is caused by the
    request the finding run was carrying. That request's Turn is the package
    the finding belongs to. Nothing new is recorded to say so, and no Turn is
    moved: this reads the causality that was already written.

    None: this Turn is not a finding (no `work-discovered` act names it).
    `turn` None with source `unknown`: it is a finding, and the record cannot
    say which Turn it was found under -- the reason travels with it.

    It is deliberately NOT a reply. A reply by the carrier to the request Turn
    counts as the request being answered; a finding is not an answer.
    """
    acts = [a for a in st.corpus.operational(turn=turn)
            if a["act"] == "work-discovered"]
    if not acts:
        return None
    act = acts[0]
    exp = st.cv._act(act["about"][0]) if act.get("about") else None
    parent_id = (exp or {}).get("caused_by") or act.get("caused_by")
    parent = st.cv._act(parent_id) if parent_id else None
    if parent is None or not parent.get("turn"):
        return {"turn": None, "number": None, "conversation": None,
                "expectation": parent_id, "source": "unknown",
                "why": ("the request it was discovered under has no Turn"
                        if parent else
                        "the request it was discovered under is not in "
                        "this record")}
    return {"turn": parent["turn"],
            "number": st.cv.turn_number(parent["turn"]),
            "conversation": parent["conversation"],
            "expectation": parent_id, "source": "computed",
            "why": "the work-discovered act is caused by the request whose "
                   "Turn this is"}


def _working_on(st, ex) -> dict:
    """What a live execution is actually working on, or the honest gap.

    THE ONLY ADMISSIBLE ANSWER IS A DURABLE ONE. An execution is a live,
    machine-local object; what it is DOING is knowable only from the acts it
    has recorded. The addressable answer is the Turn those acts were recorded
    against -- a Conversation contribution somebody can go and read.

    `execution-started` is not required to carry a Turn and often does not:
    an execution begun at Brain scope has no Turn to carry. Where no act of
    this execution names one, this says that no durable record states what the
    work is, and supplies NOTHING in its place. It does not fall back to the
    act's `because`, which is the agent's prose about why it began rather than
    a statement of the work, and it never infers from silence.
    """
    if ex is None:
        return {"working_on": None, "working_on_gap": None}
    acts = st.corpus.operational(execution=ex.reference, newest_first=True,
                                 limit=50)
    named = next((a for a in acts if a.get("turn")), None)
    if named is None:
        return {"working_on": None, "working_on_gap":
                "no act of this execution names a Turn, so the record does "
                "not say what it is working on"}
    turn = named["turn"]
    return {"working_on": {
        "turn": turn,
        "number": st.cv.turn_number(turn),
        "conversation": named.get("conversation") or ex.conversation,
        "since": named["at"],
        "from_act": named["id"],
    }, "working_on_gap": None}


def _runtime_observation(st) -> dict:
    """Which executions THIS process observes live, by id, and their liveness.

    `{"instances": None, "why_not": ...}` when it could not be asked, which is
    not the same answer as nothing running.
    """
    # `runs` IS WHAT DECIDES "RUNNING": what this process holds of each run,
    # by the run's start act. `instances` is the handles and their liveness,
    # kept for what it is -- a handle busy with one run says nothing about
    # another start on it that no end names.
    try:
        return {"runs": st.agents.agents_runs(),
                "instances": {
                    inst.instance_id: getattr(inst.liveness, "value",
                                              str(inst.liveness))
                    for inst in st.agents.agents_list()}, "why_not": None}
    except Exception as exc:                              # noqa: BLE001
        return {"runs": None, "instances": None,
                "why_not": f"{type(exc).__name__}: {exc}"}


#: How long one capacity reading answers `/api/capacity` for everyone.
CAPACITY_FRESH_S = 60.0

# THE JSON ROUTES ANSWER THE OWNER'S INTERFACE, NOT ANY PAGE IN THE BROWSER.
# Measured on 0ddae7a: every JSON answer carried `Access-Control-Allow-Origin: *`
# and a text/plain body was parsed as JSON, so a page on any other site could
# read the record and folder listings and could create Conversations, write
# Turns and start a Scratch answer with selected folders -- without a preflight.
#
# The repair is the one the artifact, recovery and look routes already use: a
# non-safelisted header a cross-origin page cannot send without a preflight,
# and a preflight that grants nothing. Plus a Host check, because a page on a
# DNS name rebound to this machine is SAME-origin and could send the header.
# This is a web boundary, not authentication: it says nothing about local
# processes, which `_api`'s docstring covers.
CLIENT_HEADER = "X-Mentis-Client"

#: Exempt from CLIENT_HEADER, each for a stated reason. `/api/server` is the
#: identity probe (`tools/mcp_bridge.py`, tools outside this repo); it reads
#: no record content, and without ACAO no other origin can read it.
CLIENT_EXEMPT_GET = frozenset({"/api/server"})


def _host_allowed(host: str | None) -> bool:
    """A Host a rebound public DNS name cannot carry.

    IP literals (a page cannot be served FROM 127.0.0.1's origin by anybody
    else), single-label names (localhost, a tailnet MagicDNS short name),
    `*.localhost`, `*.ts.net`, and whatever MENTIS_ALLOWED_HOSTS lists
    (comma-separated hostnames, no ports). Parsed strictly: a bracketed IPv6
    literal or a name, then at most ONE `:port` of digits -- nothing else."""
    import ipaddress
    import re
    if not host:
        return False
    value = host.strip().lower()
    v6 = re.fullmatch(r"\[([0-9a-f:.]+)\](?::\d{1,5})?", value)
    if v6:
        try:
            ipaddress.IPv6Address(v6.group(1))
            return True
        except ValueError:
            return False
    got = re.fullmatch(r"([a-z0-9.-]+?)\.?(?::\d{1,5})?", value)
    if not got:
        return False
    name = got.group(1)
    labels = name.split(".")
    if not name or any(not lab or lab.startswith("-") or lab.endswith("-")
                       for lab in labels):
        return False
    try:
        ipaddress.IPv4Address(name)
        return True
    except ValueError:
        pass
    extra = {h.strip().lower() for h in
             os.environ.get("MENTIS_ALLOWED_HOSTS", "").split(",") if h.strip()}
    return (name in extra or len(labels) == 1
            or name.endswith(".localhost") or name.endswith(".ts.net"))


#: THE ACT THAT SAYS A MISSED REQUEST WAS PICKED UP AGAIN, and by whom. It
#: cites the `assignment-unresolved` act it answers, so the record reads:
#: asked; not assigned, and why; resumed, by whom; assigned.
WORK_RESUMED = "work-resumed"


def _unresolved_intake(cv, expectation) -> dict | None:
    """The `assignment-unresolved` act intake recorded for this request, or
    None. Only `posting.ask_mentis` writes that act, and only by the requester."""
    exp = cv._act(expectation)
    if exp is None or exp["act"] != "expectation-recorded":
        return None
    acts = [a for a in cv._c.operational(caused_by=expectation)
            if a["act"] == "assignment-unresolved"
            and a["actor"] == exp["actor"]]
    return max(acts, key=lambda a: a["at"]) if acts else None


def _resume_refusal(cv, expectation) -> tuple[dict | None, dict | None]:
    """Why this request may not be resumed -- or (None, its unresolved act).

    EVERY REFUSAL IS ABOUT DUPLICATION. A request resumed twice, or resumed
    after somebody already carried or answered it, would be answered twice;
    each check is one way that could happen, read from the record.
    """
    def no(why, **kw):
        return {"error": why, "expectation": expectation, "resumed": False,
                **kw}, None
    try:
        state = cv.expectation_state(expectation)
    except ValueError:
        return no("that is not a request in this record")
    unresolved = _unresolved_intake(cv, expectation)
    if unresolved is None:
        return no("that is not a request Ask Mentis left unassigned; only "
                  "those are resumed here")
    if not state["unassigned"]:
        return no("it is already assigned; resuming it would take it from "
                  "whoever carries it", carrier=state["expected_of"])
    if state["satisfied_by"]:
        return no("it was already claimed met",
                  satisfied_by=state["satisfied_by"])
    # ANSWERED BY ANYBODY BUT ITS AUTHOR. With nobody assigned,
    # `response_present` cannot see a reply, so the replies are asked here.
    answered = [x["link"]["from"]
                for x in cv._c.links(relation="replies-to", to=state["turn"])
                if cv._c.read([x["link"]["from"]])[0]["attributed_to"]
                != state["requested_by"]]
    if answered:
        return no("somebody already replied to it", replies=answered)
    if state["live_execution"]:
        return no("a run is live for it", live=state["live_execution"])
    from mentis.conversation.versions import inert_refusal
    refusal = inert_refusal(cv._c, state["turn"])
    if refusal:
        return no(f"its Turn cannot be carried: {refusal['error']}")
    return None, unresolved


def resumable_intake(cv) -> list[str]:
    """Every request Ask Mentis left unassigned that nobody has since carried
    or answered, oldest first. A read: it resumes nothing."""
    seen, out = set(), []
    for a in sorted(cv._c.operational(act="assignment-unresolved"),
                    key=lambda a: a["at"]):
        exp = a.get("caused_by")
        if not exp or exp in seen:
            continue
        seen.add(exp)
        if _resume_refusal(cv, exp)[0] is None:
            out.append(exp)
    return out


def resume_intake(cv, which, *, by, enqueue, execution=None, runtime=None,
                  under=None) -> dict:
    """Carry a request intake failed to assign, AS ITSELF. The recovery path.

    The second half of `posting.ask_mentis`, run late against the request recorded
    then: the same expectation, Turn, author, `because` and `requires`, with the
    Turn's own words as the work. Nothing is written again and nothing is asked
    again. `which` is one expectation, or "all": every request intake left
    unassigned that nobody has since carried or answered.

    WHAT IT ADDS, in one transaction per request: a `work-resumed` act by `by`
    citing the `assignment-unresolved` act, then the assignment (the
    requester's, as at intake, naming the resumption) and the request's
    authority. Each dispatch is handed to `enqueue` once its writes commit.

    IDEMPOTENT BY THE RECORD, NOT BY A KEY. A resumed request is assigned, and
    an assigned request is refused, so a second call dispatches nothing --
    whoever makes it, under whatever key. The check and the writes share one
    write lock, so two racing calls cannot both pass it.

    REFUSED, with the reason, while the designation does not resolve: resuming
    then would only record the same failure again.

    NOTHING IS CHOSEN BY THE CALLER except which request. The carrier and
    Persona are the designation in force, the work is the Turn's text, and the
    authority is what intake would have granted -- so a coordinating run that
    calls this can bring about only what Ask Mentis already would have.

    NOT TRIGGERED BY ESTABLISHING A DESIGNATION, deliberately. A designation is
    a person's governance act; making it also dispatch every request left over
    from an outage would spend runtimes on work nobody re-confirmed, as a side
    effect of an edit -- and with the Persona carry-forward, of editing a
    Persona. Resuming is its own attributed act, asked for by the owner or by a
    run whose request was granted `coordinate`.
    """
    from mentis.conversation.versions import flow_text
    if not by:
        return {"error": "who is resuming it? name `by`", "resumed": False}
    many = which == "all"
    if not many and not which:
        return {"error": "name an expectation, or \"all\"", "resumed": False}
    designated = cv.intake_carrier()
    if not designated["resolved"]:
        return {"error": "the intake designation does not resolve, so there "
                         "is nobody to carry it",
                "reason": designated["reason"], "why_not": designated["detail"],
                "resumed": False}
    results, later = [], []
    for exp in (resumable_intake(cv) if many else [which]):
        with cv._c.atomic():
            # ASKED UNDER THE WRITE LOCK, beside the writes it permits -- the
            # designation too, so it cannot change between check and write.
            refusal, unresolved = _resume_refusal(cv, exp)
            designated = cv.intake_carrier()
            if refusal or not designated["resolved"]:
                results.append(refusal or {
                    "error": "the intake designation stopped resolving",
                    "reason": designated["reason"], "expectation": exp,
                    "resumed": False})
                continue
            asked = cv._act(exp)
            turn = cv._c.read([asked["turn"]])[0]
            act = cv.record_act(
                actor=by, act=WORK_RESUMED, conversation=asked["conversation"],
                turn=asked["turn"], execution=execution, runtime=runtime,
                caused_by=exp, about=[unresolved["id"]],
                because=f"intake could not assign it when it was asked "
                        f"({unresolved['detail'].get('reason')}); the "
                        f"designation now resolves",
                detail={"resumes": unresolved["id"],
                        "designation": designated["designation"],
                        **({"under": under} if under else {})})
            carried = _carry_unaddressed(
                cv, designated, conversation=asked["conversation"],
                turn=asked["turn"], author=asked["actor"], expectation=exp,
                work=flow_text(turn["body"].get("parts")),
                requires=tuple(asked["detail"].get("requires") or ()),
                enqueue=lambda **kw: later.append(kw),
                assign_detail={"resumed": act, "resumed_by": by})
            results.append({"expectation": exp, "resumed": True, "act": act,
                            "resumes": unresolved["id"],
                            "turn": asked["turn"],
                            "conversation": asked["conversation"], **carried})
    for kw in later:
        enqueue(**kw)
    if many:
        return {"resumed": [r for r in results if r.get("resumed")],
                "refused": [r for r in results if not r.get("resumed")],
                "designation": designated["designation"]}
    return results[0]


def _address_existing(st, tid, body, *, enqueue):
    """Record late addressing; an explicit ask also owes and dispatches work.

    The operation is `posting.address`; this door says who it is by and starts
    the dispatch it hands back once the addressing is durable."""
    by, refusal = _attributed(body, "by", corpus=st.corpus)
    if refusal:
        return refusal
    out, later = _posting.address(st.cv, st.corpus, tid, body, by=by,
                                  agents=st.agents)
    for kw in later:
        enqueue(st, **kw)
    return out


def _last_runtime(corpus, participant) -> str | None:
    """The runtime this Participant's most recent recorded run was on, or None.

    OBSERVED, AND ONLY THE LATEST. A Participant has no runtime; each of its
    executions has one. This is what a surface that shows the Participant
    rather than one of its Turns can honestly say -- where it last ran -- and
    a name that has never run has no answer, not a guessed one.
    """
    for a in corpus.operational(actor=participant, newest_first=True,
                                limit=24):
        if a.get("execution") and a.get("runtime"):
            return a["runtime"]
    return None


def _avatar(corpus, cv, participant, defaults=None) -> dict:
    """How a Participant is pictured: the image chosen for it, if one stands
    and its bytes are still here, and where it last ran. The interface draws
    the image, else the runtime's mark, else the initial."""
    ref = cv.avatar_of(participant)
    if ref and _artifacts.describe(corpus, ref, verify="cached").get(
            "state") != "held":
        ref = None
    return {"avatar": ref, "runtime": _last_runtime(corpus, participant),
            **_runtime_default(cv, participant, defaults)}


def _runtime_default(cv, participant, defaults=None) -> dict:
    """What runs this Participant's work when the work names no runtime.

    `default_runtime` is a person's declaration, or None. `runtime_mode` says
    which of three things is true, because they look alike and are not:
    `default` (a runtime was declared), `auto` (declared runtime-auto) and
    `undeclared` (nobody said; also runtime-auto). Never derived from the alias.
    `defaults` is `runtime_defaults_now()`, when a caller listing many names
    has already read it once.
    """
    d = (defaults.get(participant) if defaults is not None
         else cv.runtime_default_of(participant))
    if d is None:
        return {"default_runtime": None, "runtime_mode": "undeclared"}
    return {"default_runtime": d["runtime"],
            "runtime_mode": "default" if d["runtime"] else "auto",
            "runtime_declaration": d["declaration"]}


def _keyed_door(cv, by, op, request, fn):
    """Run `fn` once per (author, op) through `anchors.keyed`: a retry of the
    same request is answered with what it first came to (`replayed`), the
    same key for a different request is refused and writes nothing."""
    from mentis.conversation import anchors
    from mentis.conversation.versions import Refused
    try:
        return anchors.keyed(cv, by, op, request, fn)
    except Refused as refused:
        return refused.refusal


def _attributed(body, key="attributed_to", corpus=None):
    """WHO THE RECORD WILL SAY DID THIS, or a refusal saying nobody said.

    THE LANDMINE THIS REPLACES. Every write route reached for the attribution
    as `body.get("attributed_to") or "human"`. Two things were wrong with it
    at once. `or` treats `null`, `""` and a missing key alike, so a caller
    that sent the field and got its value wrong was answered as though it had
    never sent one. And `"human"` is not an entry this record holds: it names
    no Participant, it resolves to nothing, and material written under it
    cannot be traced to anybody. It had already produced one wrong record --
    a durable act attributed to a string -- which is what a default that
    cannot fail looks like from the far side.

    SO IT IS REFUSED. ABSENT IS NOT A PERSON. Who did something is not the
    sort of fact a server may supply on the caller's behalf: there is no
    honest value to fall back to, and inventing one writes a claim nobody
    made into material that governs. A caller that genuinely does not know
    who is acting has something to find out, not a default to inherit.

    AND THE ID IS ASKED OF THE RECORD, WHERE A CORPUS IS GIVEN. This used to
    say the further question -- whether the id names anything this record
    holds -- was asked "where each route already asks the record about its
    own arguments", and it was asked NOWHERE: every governance act accepted
    `attributed_to: "ent-DOES-NOT-EXIST"`, wrote the act under it, and the
    interface then rendered `written by @ent-DOES-NOT-EXIST`, typographically
    identical to a real alias. An unresolvable attribution is the same defect
    as `"human"` wearing a different string: material that governs, traceable
    to nobody. So the record is asked, and a `corpus` is passed by every
    route that has one. A caller that passes none gets the absence check
    alone, which is what this always did.

    WHAT IS CHECKED IS WHAT IS SAID: that the record holds an entry with this
    id. It deliberately does not go on to require a particular Kind --
    quoting, relaying and acting on behalf are real, and the substrate names
    no privileged Kind for who acted.
    """
    who = body.get(key)
    if isinstance(who, str) and who.strip():
        who = who.strip()
        if corpus is not None and not corpus.read([who]):
            return None, {
                "error": "the record holds nothing by that id, so it cannot "
                         "say who this act is by. An attribution it cannot "
                         "resolve is traceable to nobody.",
                "field": key, "given": who}
        return who, None
    return None, {"error": "this writes to the record, so it needs to say "
                           "who it is by. Name the Participant in "
                           f"`{key}`: there is no honest default for who "
                           "did something.",
                  "field": key, "given": who}


#: THE ACTS THAT CHANGE WHAT THIS BRAIN DURABLY KNOWS, and therefore the acts
#: that are refused without a stated reason. Read from the handlers below, not
#: guessed from their names:
#:
#:   establish              writes the establishing link. Standing begins here.
#:   supersede              writes `supersedes`. Standing ends here.
#:   establish-replacement  establishes the successor AND ends every
#:                          predecessor, in one act.
#:   revise                 `create_and_establish` writes the revision and
#:                          establishes it, then supersedes the proposal. It
#:                          confers standing as plainly as `establish` does.
#:
#: AND THE ONES DELIBERATELY NOT HERE. `set-aside` changes no standing -- it
#: writes a `supports` link answering a challenge, and the material stood
#: before it and stands after -- and it already refuses a blank reason on its
#: own evidence rule, so nothing here is owed it. `dispute` likewise argues
#: without changing standing and already refuses an empty challenge.
#: `propose-supersession` establishes nothing by design. `edit` and `delete`
#: move a version line rather than confer standing, and pass `because`
#: through as optional, which is what they say they do.
_CHANGES_STANDING = ("establish", "supersede", "establish-replacement",
                     "revise")

#: THE ACTS ONLY THE OWNER MAY BE NAMED AS DOING: the standing changes above,
#: and `place`, which makes standing material apply somewhere.
_OWNER_CONFERS = (*_CHANGES_STANDING, "place")


def _stated_reason(body, act, key="because"):
    """WHY THE RECORD CHANGED, or a refusal saying nobody said.

    A CHANGE TO WHAT THIS BRAIN DURABLY KNOWS, WITH NO RECORDED REASON, IS A
    CHANGE NOBODY CAN WEIGH OR OVERTURN LATER. Mark III said exactly that, at
    exactly the act that conferred standing (`mentis3/judging.py`, `promote`),
    and it is the same fact here. The establishing link carries `because` and
    so does the operational act beside it, so an act that arrives without one
    writes standing into the record with the single field a later reader needs
    left empty -- and then the only account of why this holds is a timestamp.
    Somebody wanting to overturn it has nothing to argue with.

    THIS IS A CONSTRAINT ON THE RECORD, NOT A GATE ON THE ACTOR. It asks
    nobody's permission. It adds no approval step, introduces no queue, and
    nobody has to be waited on: the owner who types a sentence is through it
    inside the same request, and no second party exists anywhere in it. It
    refuses an act that arrives without a reason, exactly as `_attributed`
    above refuses one that arrives without an actor, and for the same reason --
    there is no honest value a server may supply on the caller's behalf.

    AND BLANK IS NOT A REASON. A missing key, `null`, `""` and `"   "` are all
    the absence of one and are answered alike, which is the shape `_attributed`
    already uses for a blank actor. What the caller said is stripped and
    handed back, so what is recorded is their words and not a normalised
    paraphrase of them.

    NOT FOLDED INTO `_attributed`. That one resolves an id against the record;
    this one cannot, because free prose names nothing this record holds. Two
    different questions that happen to share a refusal shape -- generalising
    over them would mean a helper with a flag for whether its value is an id,
    which is two functions wearing one name.
    """
    said = body.get(key)
    if isinstance(said, str) and said.strip():
        return said.strip(), None
    return None, {"error": f"{act} changes what this brain durably knows, so "
                           "it records why. A change to what this brain "
                           "durably knows, with no recorded reason, is a "
                           "change nobody can weigh or overturn later. Say it "
                           f"in `{key}`.",
                  "field": key, "given": said, "act": act}


def _falsifier_refusal(corpus, eid, body, key="falsifier"):
    """The same question asked of an entry that already exists: its Kind is read
    off the entry, and the answer is `_falsifier_refusal_for_kind`'s.

    An entry whose Kind cannot be resolved is owed nothing here -- there is no
    declaration to hold it to, and inventing a requirement for material of no
    known Kind would be this layer deciding vocabulary.
    """
    got = corpus.read([eid])
    kind = ((got[0].get("definition") or {}).get("name")) if got else None
    return _falsifier_refusal_for_kind(corpus, kind, body, key=key, entry=eid)


def _falsifier_refusal_for_kind(corpus, kind, body, key="falsifier", entry=None):
    """MATERIAL THAT OWES A CHECK WHICH COULD PROVE IT WRONG IS NOT ESTABLISHED
    WITHOUT ONE. Or `None`, which is the answer in every other case.

    ASKED OF THE KIND, NOT OF AN ENTRY, so that the one door which establishes
    material that does not exist yet -- `POST /api/entries`, which creates and
    establishes in a single act -- is held to the same requirement as the doors
    that act on something already written. Review found that door standing a
    seeded `hypothesis` with no falsifier at all, which made the requirement
    something a caller could simply decline to come through.

    WHAT THE KIND DECLARES, AND ONLY THAT. `expects_falsifier` asks "does this
    owe a check that could prove it wrong" -- DECLARED, NEVER INFERRED FROM
    `truth_apt`, in the vocabulary's own words (Mark III `mentis3/kinds.json`,
    `_fields.expects_falsifier`). So nothing here reads the Kind's name, and
    nothing here reasons from `truth_apt` or `standing_apt` to it: a Kind
    called `hypothesis` that declares nothing is owed nothing, and a Kind
    called anything at all that declares `true` is owed a falsifier. A
    hypothesis that cannot be wrong is not a hypothesis; the check that could
    falsify it is what makes establishing it mean anything.

    THREE VALUES, AND ABSENT IS NOT FALSE. `true` is a requirement. `false`
    says this Kind owes no such check. ABSENT -- no such key on the current
    definition -- means NOBODY HAS SAID, which is not the same as somebody
    having said no, and is never turned into a refusal. Only an exact `true`
    refuses; `false`, absent, and anything that is not `True` do not.

    READ FROM THE CURRENT DEFINITION. ONE SOURCE, NO FALLBACK -- the same rule
    `standing_apt` is read under, and for the same reason: whether this Kind's
    instances owe a check is a fact about the vocabulary NOW, not a fact about
    what an entry meant when it was written. An entry written against v1 of
    its Kind is held to what v2 declares, while its own fields and meaning stay
    pinned to v1. `definition_for` is deliberately not consulted here.

    WHERE THE FALSIFIER IS RECORDED: IN THE ESTABLISHING ACT'S OWN BODY,
    beside the reason. It is a fact about this act of establishing -- what the
    owner would accept as proof that they were wrong to -- so it rides on the
    act that records the establishing, exactly as `because` does. No new Kind
    is invented for it, no new relation, no second act and no second approval
    step: any of those would turn one act into a small workflow, and the thing
    being asked for is a sentence, not a process.
    """
    current = corpus.current_definition(kind) if kind else None
    expects = (current or {}).get("body", {}).get("expects_falsifier")
    if expects is not True:
        return None
    said = body.get(key)
    if isinstance(said, str) and said.strip():
        return None
    return {"error": f"the current definition of {kind!r} declares that its "
                     "material owes a check that could prove it wrong, so "
                     "establishing it names one. Something that cannot be "
                     "wrong is not the sort of thing establishing means "
                     f"anything about. Say it in `{key}`.",
            **({"entry": entry} if entry else {}),
            "kind": kind, "field": key, "given": said,
            "expects_falsifier": expects,
            "expects_falsifier_from": "current-kind-definition",
            "expects_falsifier_kind_version": (
                (current or {}).get("definition", {}).get("version"))}


#: THE RELATIONS THE GENERIC AUTHORING DOOR WILL WRITE FROM A NEW ENTRY, and
#: why it is a short list rather than "anything inert". Both are seeded, both
#: are inert to the engine (`substrate_role: None`, no `proposes_role`), and
#: neither had any door at all, so an outcome could not say what it was an
#: outcome of or where it happened. Every OTHER inert relation already has a
#: door that asks its own questions -- `derive-from` a reason, `place` whether
#: the place is live, `support` what is challenged -- and this door must not
#: become the way round them. A relation joins here only by somebody deciding
#: that writing it needs no more than that both ends are held.
#:
#: `draws-on` JOINED because a Discipline is written WITH its examples,
#: references and checks, and it asks one more question than two held ends: the
#: ROLE its target plays, one of three, with a label (`_draws_on_body`). Its own
#: door, `draw-on`, asks the same questions of a link added later.
_ENTRY_LINKS = ("in-context", "outcome-of", "draws-on")


def _draws_on_source_refusal(corpus, kind) -> dict | None:
    """Why material of this Kind may not draw on anything, or None.

    ONLY MATERIAL THAT DIRECTS WORK DRAWS ON ANYTHING. A `draws-on` link is
    listed where governing material is delivered and opens the artifacts it
    names to the runs told that material; a finding or a note is not told to
    a run as governance, so a link from one would be a reference nothing
    delivers -- or, worse, a way to open bytes by being merely relevant.
    Asked of the Kind's declaration (`knowing`), never of its name."""
    from mentis.conversation import KNOWING_HOW, knowing_of
    if knowing_of(corpus, kind) == KNOWING_HOW:
        return None
    return {"error": "only material whose Kind directs how work is done "
                     "draws on examples, references or checks",
            "kind": kind, "relation": "draws-on"}


def _draws_on_body(one) -> tuple[dict | None, dict | None]:
    """The body of a `draws-on` link -- `{role, label}` -- or a refusal.
    The role is one of three and is required; the label is a short name a
    reader is shown instead of the target's contents."""
    from mentis.conversation import DRAWS_ON_ROLES
    role = one.get("role") if isinstance(one, dict) else None
    label = one.get("label") if isinstance(one, dict) else None
    if role not in DRAWS_ON_ROLES:
        return None, {"error": "a `draws-on` link says what its target is "
                               "for, in `role`",
                      "role": role, "roles": list(DRAWS_ON_ROLES)}
    if label is not None and (not isinstance(label, str) or len(label) > 200):
        return None, {"error": "a `draws-on` label is a short name, at most "
                               "200 characters", "label": label}
    return {"role": role, "label": (label or "").strip()}, None

#: THE ACT A REPORT IS RECORDED AS, and it is fixed. What a caller reports is
#: theirs to name, so the name rides in the detail; the act says what THIS DOOR
#: did. A caller-named act would let a request write `expectation-met` or
#: `result-returned`, acts other code reads meaning from.
REPORTED_ACT = "entry-reported"

#: How much a report may carry. It is a record of something that happened,
#: bounded by whoever reports it; this is the ceiling, not the expectation.
_REPORT_MAX_BYTES = 256 * 1024


def _kind_name(corpus, eid) -> str | None:
    got = corpus.read([eid])
    return ((got[0].get("definition") or {}).get("name")) if got else None


def _entry_links(corpus, said):
    """The links a new entry is written with, as `(relation, to)` pairs, or a
    refusal. Nothing given is no links; every end is asked of the record."""
    if said is None:
        return [], None
    if not isinstance(said, list):
        return None, {"error": "`links` is a list of {relation, to}",
                      "given": said}
    out = []
    for one in said:
        relation = one.get("relation") if isinstance(one, dict) else None
        to = one.get("to") if isinstance(one, dict) else None
        if relation not in _ENTRY_LINKS:
            return None, {"error": "this door writes only links that need "
                                   "nothing but two held ends; every other "
                                   "relation has a door of its own",
                          "relation": relation, "writes": list(_ENTRY_LINKS)}
        if not isinstance(to, str) or not to.strip() \
                or not corpus.read([to.strip()]):
            return None, {"error": "the record holds no such entry, so "
                                   "nothing can be linked to it",
                          "relation": relation, "to": to}
        # DELETED MATERIAL IS NOT A NEW END, here as at every other door
        # that writes a link to something (`versions.inert_refusal`).
        from mentis.conversation import versions as _versions
        refusal = _versions.inert_refusal(corpus, to.strip())
        if refusal:
            return None, {**refusal, "relation": relation}
        body = {}
        if relation == "draws-on":
            body, refusal = _draws_on_body(one)
            if refusal:
                return None, {**refusal, "relation": relation, "to": to}
        if any(r == relation and t == to.strip() for r, t, _ in out):
            continue
        out.append((relation, to.strip(), body))
    return out, None


def _entry_report(said):
    """`{"name", "detail"}` for the act a new entry is reported with, or a
    refusal. None given is no report."""
    if said is None:
        return None, None
    name = said.get("name") if isinstance(said, dict) else None
    detail = said.get("detail") if isinstance(said, dict) else None
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        return None, {"error": "a report names what it reports in `name`, "
                               "in at most 80 characters", "given": name}
    if not isinstance(detail, dict):
        return None, {"error": "a report carries its record in `detail`, "
                               "an object", "given": detail}
    size = len(json.dumps(detail, default=str))
    if size > _REPORT_MAX_BYTES:
        return None, {"error": f"a report's detail is {size} bytes, over "
                               f"the {_REPORT_MAX_BYTES} this door holds",
                      "bytes": size}
    return {"name": name.strip(), "detail": detail}, None


def _observed_writer(st, presented) -> str:
    """WHAT THE SERVER SAW, never what the request said.

    `attributed_to` is a CLAIM: the caller saying who this is by. It is
    caller-supplied and must be, because quoting somebody, relaying for
    them or acting on their behalf are all real things.

    `written_by` is what this server OBSERVED OF THE REQUEST -- which is
    not the same as what typed the words, and saying so would be a
    stronger claim than a bearer token supports. What it observes is which
    live grant, if any, the request carried. Every write route used to
    fill it from the request body, so an agent stated both and the record
    said the owner had typed it.

    THE ONLY THING THIS SERVER CAN ACTUALLY OBSERVE about a local request
    is whether it presented a worker grant. A grant was minted for one
    execution, so presenting a live one attributes the request to that
    execution, its runtime and the Participant it is carrying.

    PRESENTING NOTHING PROVES NOTHING, and is recorded as exactly that.
    It is not evidence that the owner did it; it is the absence of
    evidence about who did, and saying so is the difference between a
    record that is honest and a record that credits whoever asked.
    """
    # A header is a string. Anything else is not a grant and is not going to
    # be made into one by this function raising.
    if not isinstance(presented, str) or not presented:
        return "unattributed-local-request"
    instance_id = st.agents.authority.authorises(presented, st.path)
    inst = st.agents.known(instance_id) if instance_id else None
    if inst is None:
        # A token whose instance this process no longer holds is not
        # evidence of anything: it says a grant existed, not that the run it
        # was minted for is here. Reported as unattributed rather than as an
        # execution nobody can point at.
        return "unattributed-local-request"
    who = f"/{inst.participant}" if inst.participant else ""
    return f"observed:{inst.runtime}/{instance_id}{who}"


class _BadQuery(ValueError):
    """A GET whose query cannot be read: answered 400 with the reason, where
    any other failure of a read is the server's own (500)."""


def _turn_detail(st, tid, deliveries=None) -> dict:
    """What `GET /api/turns/<id>` answers: the Turn, every version, every filing
    and link, and the inspector. ONE PLACE, because `GET /api/turns?ids=` answers
    a list of exactly these and the two must never be able to disagree.

    Raises as the single route always did -- an id that is not an entry raises
    out of `corpus.read` -- and each caller says that in its own way: the
    single route as the request's failure, the batched read per id.

    `deliveries` IS THE DELIVERY LOG, HANDED IN BY A READER OF MANY TURNS. The
    inspector lists the deliveries that carried this Turn, and finding them
    means decoding the whole log -- measured at about two thirds of the time of
    reading 38 Turns, when each decoded it again. A batch reads it once and
    passes the same list to every Turn; nothing is kept after the request, and
    the answer per Turn is the same filter over the same log.
    """
    cv, corpus = st.cv, st.corpus
    from mentis.conversation.versions import history_view, presented
    entry = presented(corpus, corpus.read([tid])[0])
    view = _turn_view(st, entry)
    # EVERY VERSION, AND WHAT A DELETED TURN SAID. Details is where
    # retained contents are disclosed; the Turn itself shows only what
    # it now is.
    hist = history_view(corpus, tid, alias=cv.alias)
    for v in hist["versions"]:
        v["parts"] = [_artifacts.annotate_part(corpus, p)
                      for p in (v.pop("body") or {}).get("parts", [])]
    view["versions"] = hist
    # EVERY FILING AND LINK IT EVER HAD, and how each ended if it
    # did. Un-filing ends a filing; it never erases one.
    view["filings"] = [_filing_view(st, f) for f in cv.filings_of(tid)]
    standing = corpus.stands(tid)
    if deliveries is None:
        deliveries = corpus.deliveries()
    view["inspector"] = {
        "kind": (entry.get("definition") or {}).get("name"),
        "stands": standing["stands"],
        "incoming": standing["incoming"],
        "operational": corpus.operational(turn=tid),
        "deliveries": [d for d in deliveries
                       if any(m["entry"] == tid for m in d["material"])],
        "conversation": cv.conversation_of(tid),
        # WHICH THREAD IT IS IN, and its number there. The Conversation
        # flow is a batch of threads now, so a reader sent to a Turn
        # that is not in hand has to be taken to its thread -- and a
        # reply is not a unit of the flow, so asking the flow to
        # re-anchor on one is rightly refused. This is where the root
        # comes from, for the one reader that has nothing else to go on.
        "root": _root_of_turn(st, tid),
        "number": entry.get("number") or cv.turn_number(tid),
    }
    return view


#: THE MOST TURNS ONE `GET /api/turns?ids=` MAY ASK FOR. Bounded so that one
#: request cannot be made to hold the server for an unbounded time: a read of
#: one Turn is tens of milliseconds uncontended, so this many is a second or
#: two at worst, and a reader with more asks again in pieces (the Briefing
#: chunks at the same number -- `TURNS_PER_READ` in ui/src/surfaces/lobby/
#: briefing.ts). Over it is refused whole, never silently cut short.
TURNS_PER_READ = 64


class _BadRequest(ValueError):
    """A GET asked for something it may not ask: answered 400, not 500.

    A GET that raises is otherwise answered 500, which says the server failed.
    This is for the case where the server did not fail -- the question was
    malformed or too large -- so the answer says it was the request's fault.
    """


def _turns_read(st, query) -> dict:
    """MANY TURNS IN ONE READ: `GET /api/turns?ids=a,b,c`.

    WHY THIS EXISTS. The Daily Briefing reads every Turn of the day. One
    request per Turn was measured on the live Brain at 38 requests for one
    load, each 1.3-2.2 s under load (35 ms alone), queued six at a time behind
    the browser's connection limit -- up to 14 s waiting before a request was
    even sent, and the Briefing finished at ~28 s. One request for all of them
    pays the connection, the queue and the read scope once: everything a
    `Conversations.reading()` block remembers is shared by every Turn read in
    it, as it already was by the three questions inside one Turn.

    EACH ELEMENT IS EXACTLY WHAT `GET /api/turns/<id>` ANSWERS, because it is
    the same function (`_turn_detail`). Nothing is summarised, trimmed or kept;
    this is the single read, said several times in one answer.

    IN THE ORDER ASKED, ONCE EACH. An id asked twice is answered once, where it
    was first asked. ONE BAD ID NEVER FAILS THE OTHERS: a Turn that cannot be
    read is `{"id", "turn": null, "error", "kind"}` -- the words the single
    route would have failed with -- so the reader can go on saying exactly
    which Turns could not be read, as it did when each had its own request.

    The id list is refused whole (400) when it is empty, holds an id with a
    `/` in it (that is a path, not an id), or is longer than TURNS_PER_READ.
    `/api/turns` itself, with no id after it, was never a route, so this
    shape cannot be mistaken for `/api/turns/<id>/...`.
    """
    raw = ",".join(query.get("ids") or [])
    ids = list(dict.fromkeys(t.strip() for t in raw.split(",") if t.strip()))
    if not ids:
        raise _BadRequest("name the Turns to read: /api/turns?ids=<id>,<id>")
    if len(ids) > TURNS_PER_READ:
        raise _BadRequest(f"{len(ids)} Turns asked for in one read; at most "
                          f"{TURNS_PER_READ} -- ask again for the rest")
    bad = [t for t in ids if "/" in t]
    if bad:
        raise _BadRequest(f"not a Turn id: {bad[0]!r}")
    # THE SHARED LOG IS USED ONLY WHILE IT IS STILL THE RECORD'S (review
    # MINOR-1). Read once and handed to every Turn, a delivery committed part
    # way through the batch would have left later Turns showing their newer
    # acts beside an older delivery list -- the single route reads the log
    # last, so its list always covers the rest of its answer. So the log is
    # taken with the record's `steady` number, and a Turn read after that
    # number moved (or while a commit is under way) reads the log itself, at
    # the same point the single route does. A Turn during whose read the
    # number moved is read again that way. In the ordinary case nothing has
    # moved and the log is decoded once.
    at = st.corpus.steady
    log = st.corpus.deliveries()
    if at is None or st.corpus.steady != at:
        log = None
    out = []
    for tid in ids:
        try:
            got = _turn_detail(st, tid, log)
            if log is not None and st.corpus.steady != at:
                log = None
                got = _turn_detail(st, tid, None)
            out.append({"id": tid, "turn": got})
        except Exception as exc:                          # noqa: BLE001
            # A READ REFUSED BESIDE THE WRITER is not this Turn failing: the
            # whole answer is void and `_api` reads it again from the start
            # (it asks `beside_writer_refused()`, whatever was caught here).
            out.append({"id": tid, "turn": None, "error": str(exc),
                        "kind": type(exc).__name__})
    return {"turns": out, "limit": TURNS_PER_READ}


class _Refused(Exception):
    """A refusal raised from inside a transaction, carrying its own answer.

    WHY A REFUSAL HAS TO BE ABLE TO TRAVEL. Two of the supersession refusals
    are about the replacement, and on the revise path the replacement does not
    exist until the act writes it -- so they can only be checked once something
    has been written. Raising rolls the transaction back, which leaves nothing
    written, and the refusal that comes out is the same dict the caller would
    have got had it been checked first. It is not an error condition with a
    message composed here; it is the refusal, carried.
    """

    def __init__(self, refusal: dict):
        super().__init__(refusal.get("error", "refused"))
        self.refusal = refusal


def _replacement_shape_refusal(corpus, eid, replacement) -> dict | None:
    """Why this could not be a replacement for that AT ALL, or None.

    THE THREE THAT ARE TRUE OF A PROPOSAL TOO. Whether a replacement may END a
    predecessor is a question about standing and placement, and it is asked
    only when somebody actually ends something. Whether a thing is the sort of
    thing that could replace another at all -- not itself, both held, the same
    Kind -- is true of a proposal as much as of an act, because a proposal that
    names a Persona as the replacement for a Rule is not a proposal anybody
    could ever accept.

    SPLIT RATHER THAN COPIED. `_supersession_refusal` calls this first and adds
    the two that are about ending; the proposing path calls this and stops.
    Neither holds its own copy of the other's checks.
    """
    if replacement == eid:
        return {"error": "an entry cannot supersede itself", "entry": eid}
    # A CONVERSATION IS NEVER REPLACED, OR A REPLACEMENT, HERE: its next
    # version is a rename's (`versions.conversation_line_refusal`). Asked for
    # every predecessor, including those taken from a proposal.
    from mentis.conversation.versions import conversation_line_refusal
    refusal = conversation_line_refusal(corpus, eid, replacement)
    if refusal is not None:
        return refusal
    was = corpus.read([eid])
    if not was:
        return {"error": "the record holds no such entry", "entry": eid}
    got = corpus.read([replacement])
    if not got:
        return {"error": "the record holds no such entry",
                "entry": replacement}
    if (got[0].get("definition") or {}).get("name") != (
            was[0].get("definition") or {}).get("name"):
        return {"error": "a replacement is the same Kind as what it replaces",
                "entry": eid}
    return None


def _supersession_refusal(corpus, eid, replacement) -> dict | None:
    """Why this replacement may not end this predecessor, or None.

    THE FOUR REFUSALS, IN ONE PLACE BECAUSE THEY ARE NOW APPLIED SEVERAL TIMES.
    One approved successor may replace several predecessors in one act, and
    every one of those predecessors is owed the same checks it was owed when it
    was the only one. Pulled out unchanged rather than re-stated per
    predecessor, so that the two cannot drift apart.

    THE FIRST THREE ARE SHARED WITH PROPOSING, and live in
    `_replacement_shape_refusal`. The two below are the ones that are about
    ENDING something, which is why a proposal is not asked them: a proposed
    successor is not established and need not be, and a predecessor that is
    merely proposed against is not losing its scope to anybody.
    """
    shape = _replacement_shape_refusal(corpus, eid, replacement)
    if shape is not None:
        return shape
    if not corpus.stands(replacement)["stands"]:
        return {"error": "the replacement does not stand, so ending this "
                         "would leave nothing in its place", "entry": eid}
    from mentis.conversation import placements_now
    was_at = set(placements_now(corpus, eid))
    now_at = set(placements_now(corpus, replacement))
    if was_at - now_at:
        return {"error": "the replacement is not placed where this material "
                         "applies, so ending it would leave that scope "
                         "governed by nothing",
                "entry": eid, "applies_at": sorted(was_at),
                "replacement_at": sorted(now_at)}
    return None


def _whole_brain_refusal(corpus, eid) -> dict | None:
    from mentis.conversation import whole_brain_refusal
    return whole_brain_refusal(corpus, eid)


def _answered_asks(cv, entry, *, by, act) -> dict:
    """Record that acting on this item answered whatever asked about it.

    WHY AN ACT HAS TO KNOW. The owner was asked something, went and did it, and
    was then asked again -- because establishing an item and answering the
    request to establish it were two unconnected facts. They are one thing that
    happened, and the record says so here.

    THE EXISTING MACHINERY, AND ONLY IT. An ask is an expectation; an
    expectation that concerns durable material names it; fulfilment is
    `expectation-met`, which is what every other answer already writes. Nothing
    new is stored and no second notion of "answered" exists.

    ONLY OPEN ONES, AND ONLY ONES THAT NAME THIS ITEM. An ask already answered
    is not answered again, and an ask that named nothing is not swept in
    because it happened to be nearby.
    """
    answered = []
    for state in cv.asks_about(entry):
        met = cv.record_act(
            actor=by, act="expectation-met",
            conversation=state["conversation"], turn=state["turn"],
            caused_by=state["expectation"], about=[entry],
            because=f"answered by acting on the material: {act}",
            detail={"answered_by_act": act, "entry": entry})
        answered.append({"expectation": state["expectation"], "act": met,
                         "of": state["expected_of"],
                         "requested_by": state["requested_by"],
                         "turn": state["turn"]})
    if not answered:
        return {"answers": [], "answers_a_request": False}
    return {"answers": answered, "answers_a_request": True,
            "say": "The request to you is answered."}


def _named(root):
    """WHAT THIS BRAIN IS CALLED, as its own manifest says (UI polish 2, #8).

    Read-only, from `mentis-corpus.json` beside the record: the name it was
    created with and what it is for. A directory with no manifest has no
    name to report, and says so rather than borrowing the folder's.
    """
    try:
        doc = _Manifest(root).identity()
    except Exception as e:                                  # noqa: BLE001
        return {"corpus_name": None, "corpus_role": None,
                "corpus_name_why_not": f"no corpus manifest could be read: {e}"}
    return {"corpus_name": doc.get("name") or None,
            "corpus_role": doc.get("role") or None}


def _routes(st, path, query, body, method, presented=None, *, _enqueue_dispatch=None, peer=None):
    cv, corpus, brain = st.cv, st.corpus, st.brain
    one = lambda k, d=None: (query.get(k) or [d])[0]        # noqa: E731

    if path.startswith("/api/ladder/"):
        from mentis.web.ladder import routes as ladder_routes
        return ladder_routes(st, path, query, body, method, presented)

    # ---- Sources: Manage Sources, owner-side (`mentis/web/sources.py`) ----
    if path == "/api/sources" or path.startswith("/api/sources/"):
        from mentis.web.sources import routes as _source_routes
        return _source_routes(st, path, query, body, method, presented, peer=peer)

    # ---- Exchange import: preview & stage (`mentis/web/exchange_import.py`) ----
    if path.startswith("/api/exchange/import/"):
        from mentis.web.exchange_import import routes as _import_routes
        return _import_routes(st, path, query, body, method, presented)

    # ---- brain -----------------------------------------------------------
    if path == "/api/brain":
        # WHICH BRAIN THIS IS, AND NOTHING ELSE (`?identity=1`): what Fluid's
        # frame names and keys its notifications by. The orientation below
        # is ~0.8 s of reading the record, which Fluid never shows and used
        # to ask twice on every page load (the owner's slowdown, 2026-10-25).
        if one("identity"):
            return {"corpus_path": corpus.root, "corpus_id": corpus.corpus_id,
                    **_named(corpus.root)}
        o = brain.orientation(participant=one("participant"))
        return {**o, "rendered": brain.render(o), "corpus_path": corpus.root,
                "corpus_id": corpus.corpus_id, **_named(corpus.root)}

    if path == "/api/server":
        """WHAT CODE THIS RUNNING SERVER IS. Read-only, and observed.

        The commit is the one this process STARTED from, read once at start:
        a checkout afterwards changes the disk, not what is running. Anything
        not observable is None with a reason. Nothing here claims deployed,
        integrated or reviewed.
        """
        host, _, port = (st.answers_at or "").rpartition("//")[2].partition(":")
        return _identity.identity(workspace=st.workspace, corpus=st.path,
                                  host=host or None,
                                  port=int(port) if port.isdigit() else None)

    if path == "/api/owed":
        """WHAT THIS PARTICIPANT OWES. Not who was addressed.

        `/api/brain`'s `attention` is "somebody was addressed and has not
        replied", which is descriptive and must never read as an obligation.
        This is the obligation: expectations whose current carrier is the
        participant named, unanswered. Without a participant it refuses
        rather than answering for everybody.
        """
        from mentis.operational.work import owed_by
        who = one("participant")
        if not who:
            return {"error": "whose obligations? name a participant",
                    "owed": None, "total": None, "omitted": None}
        return owed_by(cv, who, limit=int(one("limit", 10)))

    if path == "/api/work" or path.startswith("/api/work/"):
        """THE WORK OVERVIEW. Every piece of work once, grouped. Read-only.

        A projection over trunks, their runs, their delegations and the
        decisions asked under them (`operational/work_overview.py`), shaped
        as `ui/src/work/contract.ts`. Nothing is stored. The same runtime
        observation `/api/conversations/{cid}/work` uses qualifies runs the
        record already says started; it never creates one.

        THE VIEWER IS THE OWNER UNLESS NAMED, read from the record as the
        baseline identifies them. Where the record names no owner, what
        anybody owes is UNKNOWN and is said to be.

        `active_since` IS TODAY'S LEDGER (owner decision A): what needs the
        viewer, what is moving, and what was active since then, chosen
        before any status is computed (`work_overview._in_scope`).
        """
        from mentis.operational import work_overview as wo
        viewer = one("viewer") or wo.owner_of(cv)
        runtime = _runtime_observation(st)
        if path == "/api/work":
            # A QUERY THAT CANNOT BE READ IS REFUSED AS ONE (400), naming the
            # field, never answered as if it had not been asked.
            for field in ("completed_since", "active_since"):
                try:
                    wo.parse_since(one(field))
                except ValueError as exc:
                    raise _BadQuery(f"{field} is an ISO 8601 time: {exc}")
            limit = one("limit")
            try:
                limit = None if limit in (None, "") else int(limit)
            except ValueError:
                raise _BadQuery(f"limit is a whole number, not {limit!r}")
            if limit is not None and limit < 0:
                raise _BadQuery(f"limit is a whole number, not {limit}")
            # ONE COMPUTATION PER QUESTION, reused while the record and
            # the runs observed are what it was read from
            # (`foundation.shared_answer`, the owner's slowdown).
            from mentis.conversation.shared_answer import answers_of
            from mentis.operational import stage as _stage
            args = (viewer, one("conversation") or None,
                    one("completed_since"), one("active_since"), limit)
            return answers_of(st).get(
                ("api/work", args),
                lambda: wo.overview(cv, viewer=viewer, runtime=runtime,
                                    conversation=args[1],
                                    completed_since=args[2],
                                    active_since=args[3], limit=limit),
                version=lambda: (None if cv.corpus.steady is None
                                 else (cv.corpus.steady, repr(runtime),
                                       _stage.answer_version(st))))
        expectation = urllib.parse.unquote(path[len("/api/work/"):])
        # NOT A TRUNK IS NOT FOUND: None is this server's 404.
        return wo.detail(cv, expectation, viewer=viewer, runtime=runtime)

    if path == "/api/participants":
        """EVERY NAME THE BRAIN HOLDS. Searched, never pruned.

        `q` and `limit` were added for the composer, which offers a small
        factual candidate set before anything is typed and searches the whole
        population afterwards. NOT SUGGESTED IS NOT FORGOTTEN: nothing is
        expired, hidden or dropped from the record to keep a list short, and a
        name last used months ago is found by typing it.

        MEASURED, AND DELIBERATELY NOT INDEXED. This is a linear scan of
        every Participant. At 817 identities a query answers in 9ms, which is
        below the threshold at which anybody could notice, so an index would
        be machinery bought against a cost nobody is paying. The scan is
        roughly 1ms per 100 names, so the shape to watch for is tens of
        thousands; that is where a prefix index would start to earn itself.
        Recorded here rather than built.

        Both are optional and the unfiltered answer is unchanged, so the
        identity surface that already reads this route is untouched. `matched`
        says how many the query found, so a caller showing `limit` of them can
        say what it is not showing rather than implying there is no more.
        """
        q = (one("q", "") or "").strip().lower().lstrip("@")
        rows = [
            {"participant": p["id"], "alias": p["body"]["alias"],
             "about": p["body"]["about"],
             "conversations": cv.conversations_of(p["id"])}
            for p in cv.all_participants()]
        if q:
            rows = [r for r in rows if q in r["alias"].lower().lstrip("@")]
        n = len(rows)
        limit = one("limit")
        if limit:
            rows = rows[:int(limit)]
        # AFTER the limit, so a composer search pays for 24 pictures, not all.
        # Declared runtimes are read ONCE for the whole list, not per name.
        defaults = cv.runtime_defaults_now()
        for r in rows:
            r.update(_avatar(corpus, cv, r["participant"], defaults))
        return {"participants": rows, "matched": n}

    if (path.startswith("/api/participants/")
            and path.endswith("/rename") and method == "POST"):
        """RENAME A PARTICIPANT, KEEPING WHO THEY ARE. THE OWNER'S ACT.

        {attributed_to, alias, because?}. `Conversations.rename_participant`
        writes the new alias as the Participant's next version: every post,
        act and delegation still names the same Participant, the old alias
        stays in the record, and from now on it is refused for new
        addressing with the new one named. Refused for anybody but the owner,
        as every act that changes what a somebody is called for everybody
        else -- AND REFUSED OUTRIGHT WHERE THE RECORD NAMES NO OWNER (review
        finding opr-55d2af2ccc16): with nobody whose act this is, any
        attribution at all would otherwise be accepted.
        """
        from mentis.conversation.versions import Refused
        from mentis.conversation.owner import _owner
        pid = path[len("/api/participants/"):-len("/rename")]
        by, unattributed = _attributed(body, corpus=corpus)
        if unattributed:
            return unattributed
        owner = _owner(cv)
        if not owner:
            return {"error": "only the owner may rename a Participant, and "
                             "this Brain has no owner yet; establish one "
                             "first", "participant": pid, "attributed_to": by,
                    "owner": None}
        if by != owner:
            return {"error": "only the owner may rename a Participant: this "
                             f"act names {by!r}, who is not the owner",
                    "participant": pid, "attributed_to": by, "owner": owner}
        try:
            got = cv.rename_participant(
                pid, body.get("alias"), by=by,
                because=(str(body.get("because") or "").strip() or None),
                written_by=_observed_writer(st, presented))
        except Refused as refused:
            return refused.refusal
        return {"ok": True, **got}

    if (path.startswith("/api/participants/")
            and path.endswith("/runtime-default") and method == "POST"):
        """DECLARE WHICH RUNTIME RUNS A PARTICIPANT'S WORK WHEN IT NAMES NONE.

        `runtime` is one of the runtimes this Mentis knows, or null for
        runtime-auto. A person's act through the owner's door; the worker door
        has no operation that reaches it. It changes what NEW work is bound
        to: work already recorded keeps the runtime it was bound to.
        """
        pid = path[len("/api/participants/"):-len("/runtime-default")]
        by, unattributed = _attributed(body, corpus=corpus)
        if unattributed:
            return unattributed
        if not cv._is_kind(pid, "participant"):
            return {"error": f"{pid} is not a Participant"}
        runtime = (str(body.get("runtime") or "").strip() or None)
        known = (st.agents.runtime_names() if st.agents is not None else [])
        if runtime and runtime not in known:
            return {"error": f"{runtime!r} is not a runtime this Mentis "
                             f"knows; known: {known}", "known": known}
        eid = cv.declare_runtime_default(
            pid, runtime, by=by, written_by=_observed_writer(st, presented),
            because=(f"declared {runtime} as the default runtime" if runtime
                     else "declared runtime-auto"))
        return {"participant": pid, "declaration": eid,
                **_runtime_default(cv, pid)}

    if (path.startswith("/api/participants/") and path.endswith("/avatar")
            and method == "POST"):
        """PICTURE A PARTICIPANT, OR GO BACK TO THE DEFAULT.

        `staged` is bytes the browser already sent to `/api/artifacts`; they
        cross into Mentis here, through the same `hold` every other crossing
        uses, so the picture has an Admission, an act and a `produced` link
        like any attachment. `artifact` names an image Mentis already holds.
        `clear` ends the chosen picture, and the runtime's mark or the
        initial shows again.

        IMAGES ONLY, DECIDED BY THE BYTES. What the artifact route will serve
        as an image -- PNG, JPEG, GIF -- is what may be chosen. SVG is served
        as text there on purpose, and is refused here rather than loosening
        that.
        """
        pid = path[len("/api/participants/"):-len("/avatar")]
        by, unattributed = _attributed(body, corpus=corpus)
        if unattributed:
            return unattributed
        if not cv._is_kind(pid, "participant"):
            return {"error": f"{pid} is not a Participant"}
        wrote = _observed_writer(st, presented)
        if body.get("clear"):
            ended = cv.clear_avatar(pid, by=by, written_by=wrote)
            return {"participant": pid, "ended": ended,
                    **_avatar(corpus, cv, pid)}
        staged, ref = body.get("staged"), body.get("artifact")
        if staged:
            digest = _artifacts.held.digest_of(staged)
            if digest is None or not _artifacts.held.has(corpus.root, digest):
                return {"error": f"{staged} was never received here; "
                                 "upload it again"}
            data = _artifacts.held.read(corpus.root, digest)
            if _artifacts.treatment(data, None)["view"] != "image":
                return {"error": "a picture must be a PNG, JPEG or GIF"}
            with corpus.atomic():
                ref = _artifacts.hold(
                    corpus, cv, data, act=_artifacts.SUBMITTED, actor=by,
                    source=f"avatar:{pid}", door="human-ingress",
                    claimed_name=body.get("name"),
                    claimed_media_type=body.get("media_type"),
                    because="chosen as a Participant's picture",
                    written_by=wrote)["admission"]
                link = cv.set_avatar(pid, ref, by=by, written_by=wrote)
        elif ref:
            d = _artifacts.describe(corpus, ref)
            if d.get("state") != "held":
                return {"error": f"{ref} is {d.get('state')}, not a held "
                                 "artifact"}
            if d.get("treatment", {}).get("view") != "image":
                return {"error": "a picture must be a PNG, JPEG or GIF"}
            link = cv.set_avatar(pid, ref, by=by, written_by=wrote)
        else:
            return {"error": "send `staged`, `artifact` or `clear`"}
        return {"participant": pid, "pictured_by": link,
                **_avatar(corpus, cv, pid)}

    if path == "/api/personas" and method == "POST":
        """Define a Persona. Its own shape, because its Kind declares one.

        NOT THE SAME FORM AS AN INSTRUCTION, and deliberately not. A Persona
        declares `name`, `behaviour` and `about`; an instruction declares
        `text` and `about`. They are both Kinds and that is not a reason to
        author them through one shape -- the fields a Kind declares are what
        it means, and flattening them would lose it.

        `define_persona` creates and establishes, because an owner defining
        one is not proposing it to themselves.
        """
        name = (body.get("name") or "").strip()
        behaviour = (body.get("behaviour") or "").strip()
        if not name or not behaviour:
            return {"error": "a Persona needs a name and a behaviour"}
        by, unattributed = _attributed(body, corpus=corpus)
        if unattributed:
            return unattributed
        if body.get("propose"):
            # A Persona can be proposed like anything else, and `propose`
            # used to be accepted and ignored here -- which established it
            # while reporting that it had not been.
            pid = corpus.write(kind="persona", attributed_to=by,
                               body={"name": name, "behaviour": behaviour,
                                     "about": body.get("about", "")},
                               written_by=_observed_writer(st, presented))
        else:
            # THE OBSERVED WRITER ON THIS BRANCH TOO. The propose branch above
            # passed it and this one did not, so a Persona established through a
            # request that presented a live worker grant was byte-identical to
            # one the owner made: `written_by` was left to default while
            # `attributed_to` carried whatever the request claimed. That is a
            # provenance defect and nothing about authority -- what this server
            # observed of the request is recorded either way, and the answer for
            # a request that presented nothing is still
            # `unattributed-local-request`.
            pid = cv.define_persona(name, behaviour,
                                    about=body.get("about", ""),
                                    attributed_to=by,
                                    written_by=_observed_writer(st, presented))
        return {"persona": pid, "name": name, "standing": corpus.stands(pid)}

    if path == "/api/personas":
        return {"personas": [
            {"persona": p["id"], "name": p["body"]["name"],
             "behaviour": p["body"]["behaviour"],
             "about": p["body"].get("about", ""),
             "stands": corpus.stands(p["id"])["stands"]}
            for p in corpus.entries_of_kind("persona")
            # A Persona nobody can use is not offered. Superseded ones stay
            # in the record and out of the picker.
            if corpus.stands(p["id"])["stands"]]}

    if path == "/api/integrity":
        """Are the durable streams internally consistent. Asked, not assumed.

        Narrower than `has this record been altered`, and the answer says
        so in its own words: it detects editing under the chain, it
        prevents nothing, and it does not catch a chain that was rewritten
        rather than edited beneath.

        AND WHETHER THE VOCABULARY THIS BRAIN CARRIES IS THE ONE THE CODE READS,
        which is a different question with the same shape: is the record
        internally consistent with itself. A declaration added to the shipped
        vocabulary reaches NEW corpora only -- the spine seeds an EMPTY corpus
        and the Conversation layer defines only an UNDEFINED Kind -- so a Brain
        that already exists can be running code that branches on a property its
        definitions do not carry. Measured on the live Brain: 17 of 17 Kinds
        carried no `knowing`, and every procedure placed in it was still
        established, still placed, and delivered to nobody, with `withheld`
        empty and `governs()` returning nothing.

        IT REPORTS AND REPAIRS NOTHING. Startup must not quietly rewrite
        somebody's vocabulary, and neither must a read: `missing` names each
        Kind, the property, what the vocabulary declares, and the tool to run.
        No state is stored and nothing here is a queue.
        """
        out = corpus.verify_chain()
        missing = vocabulary.missing_declarations(corpus)
        out["declarations"] = {
            "missing": missing,
            "total": len(missing),
            "ok": not missing,
            "means": "these Kinds' current definitions do not carry a "
                     "declaration the shipped vocabulary declares for them, and "
                     "production branches on every property named here. Run the "
                     "tool each row names.",
            "not_repaired_here": "nothing in this read or at startup changes a "
                                 "definition; a migration is a deliberate act",
        }
        return out

    if path == "/api/intake":
        """Who carries a request addressed to nobody, and every designation ever.

        A READ, and it decides nothing. It exists because the answer must be
        inspectable: when Ask Mentis leaves a request unassigned, the reason is
        here in the same words the intake act recorded, and the designations
        below say what was written, what stands and what superseded what. There
        is no management screen, and no way to set one from here -- designating a
        carrier is establishing something, so it is a person's act.
        """
        carrier = cv.intake_carrier()
        rows = cv.intake_designations()
        for r in rows:
            r["alias"] = cv.alias(r["participant"])
            got = corpus.read([r["persona"]])
            r["persona_name"] = got[0]["body"].get("name") if got else None
            r["persona_stands"] = corpus.stands(r["persona"])["stands"]
        return {"carrier": carrier, "designations": rows,
                "requires": list(INTAKE_REQUIRES),
                # WHAT INTAKE LEFT UNASSIGNED AND NOBODY HAS SINCE CARRIED OR
                # ANSWERED: what `/api/intake/resume` with "all" would resume.
                "resumable": resumable_intake(cv),
                "note": "one designation in force resolves; none or several is "
                        "unresolved and is a person's decision, never a tie "
                        "broken by recency"}

    if path == "/api/intake/resume" and method == "POST":
        """Carry requests Ask Mentis could not assign when they were asked.

        `{"expectation": "<id>" | "all", "by": "<Participant>"}`. Each is
        resumed AS ITSELF -- see `resume_intake` -- and anything that is
        already assigned, answered, met or running is refused and dispatches
        nothing, so calling this twice is safe. Refused whole while the
        designation does not resolve.

        THE OWNER'S DOOR, and `by` is who the record says resumed it. A run
        reaches the same function through the `resume_intake` operation, and
        only when its own request was granted `coordinate`.
        """
        which = str(body.get("expectation") or "").strip()
        by = str(body.get("by") or "").strip()
        if by and not cv._is_kind(by, "participant"):
            return {"error": f"{by!r} is not a Participant in this record",
                    "resumed": False}
        return resume_intake(
            cv, which, by=by,
            enqueue=lambda **kw: (_enqueue_dispatch or dispatch_soon)(st, **kw))

    if path in ("/api/kinds", "/api/governance/authoring"):
        """What Kinds exist and what fields each one declares.

        SO NOTHING ELSE HAS TO KNOW. An authoring surface needs to know that
        a rule has `text` and a Persona has `name` and `behaviour` -- and if
        it held that list itself, a Kind name would live in interface code
        and a new Kind would need a code change. It asks instead. The
        answer comes from the definitions, which are ordinary entries.

        ONE READ, SHARED with the governed register and the worker's `kinds`
        tool -- see `register.kind_definitions` -- so the UI and an agent are
        never told different vocabularies.
        """
        from mentis.conversation.register import kind_definitions
        from mentis.web.governance_ui import authoring_listing
        # Keep the vocabulary contract shared with the agent reader intact.
        # Only the UI adapter describes the existing creation doors, and
        # Fluid's door reads the same listing (`/fluid/api/governance/...`).
        if path == "/api/governance/authoring":
            return authoring_listing(corpus)
        return {"kinds": sorted(kind_definitions(corpus).values(),
                                key=lambda r: r["kind"])}

    if path == "/api/governance/subjects":
        """The `about` subjects procedural material already names, offered
        to an authoring form as suggestions so one subject is not written two
        ways. A read; see `governance_ui.subjects`."""
        from mentis.web.governance_ui import subjects
        return {"subjects": subjects(corpus)}

    # ---- the governed-material register ------------------------------------
    if path == "/api/governed":
        """Every governed entry in this Brain, findable without its id.

        A READ over `stands`, sorted by the same `standing_state` that
        `governs()` uses; see `mentis.conversation.register`. `kind`, `q` and
        `state` (proposed | standing | history | unknown) narrow it; `limit`
        bounds each group, and `omitted` says how many it left out. What counts as
        governed is each Kind's current `standing_apt`, never a list here.
        """
        from mentis.conversation.register import governed
        return governed(brain, kind=one("kind"), q=one("q"),
                        state=one("state"), limit=one("limit"),
                        cursor=one("cursor"))

    # ---- activity: honest, from operational history -----------------------
    if path == "/api/pulse":
        """HAS ANYTHING MOVED. The whole of the live-update mechanism.

        THE PROBLEM THIS SOLVES, said plainly: every surface already knows
        how to read itself and already has a `reload`, and the shell already
        has an `onChanged` that rereads all of them. What was missing was
        nobody ever telling the client that the record had moved unless the
        client had moved it, so an agent's acknowledgement, reply, status or
        product arrived unseen until somebody pressed refresh.

        So this returns something to COMPARE and nothing else. No domain
        object, no diff, no list of what changed, no second state model: a
        reader that sees a different token rereads what it already reads.
        Measured at 12.5 microseconds a call, which is why this can simply
        be asked for rather than subscribed to.

        TWO HALVES, because two different things move. The durable half is
        the record itself. The live half is execution the record has not
        heard about yet -- an agent that has started but not answered is
        machine-local until it says something, and that interval is exactly
        when somebody is watching to see whether their work was picked up.
        """
        durable = corpus.advance()
        # AND THE RUNS THIS PROCESS HOLDS, as far as it has observed them, so
        # a run moving from one observed state to another rereads too.
        live = (st.agents.live_now(), st.agents.run_marks())
        out = {"token": "%d.%d.%d/%s" % (
            durable[0], durable[1], durable[2],
            hashlib.sha256(repr(live).encode()).hexdigest()[:12])}
        # AND WHERE IT MOVED, for a reader that says what it last saw, so each
        # reader rereads only where it is concerned (`mentis/web/moved.py`).
        # Asked only when the durable half differs; None says "everything".
        since = one("since")
        if since and since != "%d.%d.%d" % durable:
            from mentis.web.moved import moved as _moved
            out["moved"] = _moved(corpus, since)
        return out

    # ---- one run, live: what MARS reports of it, and Stop -----------------
    # `GET /api/runs/<run>/feed?after=<seq>`: the run's feed since `after`
    # (`mentis.core.run_feed`): its messages, tool calls, plan and usage,
    # what it is doing now, a permission it waits on, and how it ended. Only
    # a run THIS process holds has one; any other says so.
    # `POST /api/runs/<run>/stop` {"why"?}: ask MARS to cancel the session.
    # STOPPING A SESSION IS NOT FINISHING THE WORK: the run ends cancelled and
    # what it was asked to do stays open in the record.
    if path.startswith("/api/runs/"):
        import re as _re
        m = _re.match(r"^/api/runs/([^/]+)/(feed|stop)$", path)
        if m:
            run, what = urllib.parse.unquote(m.group(1)), m.group(2)
            if what == "feed" and method == "GET":
                try:
                    after = max(0, int(one("after") or 0))
                except ValueError:
                    after = 0
                got = st.agents.agents_run_feed(run, after)
                return got or {"run": run, "held_here": False, "events": [],
                               "next": after,
                               "note": "this server does not hold that run: "
                                       "a run's live feed is kept only by the "
                                       "process running it"}
            if what == "stop" and method == "POST":
                from mentis.conversation.owner import _owner
                start = cv._act(run)
                if start is None:
                    raise _BadRequest(f"{run!r} is not a recorded run")
                owner = _owner(cv)
                why = str((body or {}).get("why") or "").strip() or                     "stopped from Fluid"
                asked = st.agents.agents_halt_run(run, by=owner or "owner", why=why)
                if asked and owner:
                    cv.record_act(actor=owner,
                                  act="execution-stop-asked",
                                  conversation=start.get("conversation"),
                                  turn=start.get("turn"),
                                  execution=start.get("execution"),
                                  runtime=start.get("runtime"),
                                  caused_by=run, because=why)
                feed = st.agents.agents_run_feed(run, 0) or {}
                return {"run": run, "asked": asked,
                        "state": ("stopping" if asked else
                                  "already-ended" if feed.get("ended_at") else
                                  "not-held-here" if not feed else "not-running"),
                        "note": "the session is asked to stop; the work it was "
                                "doing is not marked done"}

    if path == "/api/activity":
        live = {e.participant: e for e in cv.active_executions()}
        # WHAT EACH OF THEIR OPEN RUNS IS DOING, in the words `/api/working`
        # uses -- the same function, read once, not a second reading.
        #
        # EACH RUN SAYS WHERE IT RUNS AND WHAT IT IS ON, BY ITS OWN START ACT:
        # its `conversation`, the post it was dispatched on (`working_on`),
        # and whether it is `live` -- open and held here (`runs.is_live`). A
        # reader showing one Conversation's work counts the runs whose
        # `conversation` is that one, one entry per run: never a
        # Participant's every run wherever it is a member, and never two runs
        # of one Participant folded into one.
        from mentis.operational.runs import is_live, working
        try:
            by_actor: dict = {}
            for r in working(cv, st.agents, recent=0)["open"]:
                turn = r.get("turn")
                by_actor.setdefault(r["actor"], []).append({
                    **{k: r.get(k) for k in ("run", "state", "words", "at",
                                             "source", "held_here",
                                             "activity", "activity_at",
                                             "stopping", "permission",
                                             "conversation", "turn")},
                    "live": is_live(r),
                    "working_on": ({"turn": turn,
                                    "number": cv.turn_number(turn),
                                    "conversation": r.get("conversation"),
                                    "since": r.get("started_at")}
                                   if turn else None)})
        except Exception:                                 # noqa: BLE001
            by_actor = {}
        rows = []
        for p in cv.all_participants():
            pid = p["id"]
            ex = live.get(pid)
            recent = corpus.operational(actor=pid, newest_first=True, limit=6)
            rows.append({
                "runs": by_actor.get(pid, []),
                "participant": pid, "alias": p["body"]["alias"],
                "about": p["body"]["about"],
                # A held run that has not begun its execution handle yet is
                # somebody working too (`_live` in `mentis.fluid.read`).
                "has_live_execution": ex is not None or any(
                    r["live"] for r in by_actor.get(pid, ())),
                "execution": ex.reference if ex else None,
                "runtime": ex.runtime if ex else None,
                "scope": ("brain" if ex and not ex.conversation
                          else "conversation" if ex else None),
                "conversation": ex.conversation if ex else None,
                "recent_acts": [{"id": a["id"], "act": a["act"], "at": a["at"],
                                 "conversation": a["conversation"],
                                 "turn": a["turn"], "because": a["because"]}
                                for a in recent],
                "conversations": cv.conversations_of(pid),
                **_working_on(st, ex),
            })
        return {"activity": rows,
                "note": ("live executions are machine-local: this server sees "
                         "the ones it started. A Participant existing is not "
                         "an agent running.")}

    # ---- conversations ----------------------------------------------------
    if path == "/api/capacity":
        """HOW MUCH OF EACH RUNTIME IS LEFT, where the runtime says so.

        SEPARATE FROM `/api/execution` FOR A MEASURED REASON. Observing
        capacity means reading rate-limit events and rollout session files,
        and doing it for three runtimes took SEVEN SECONDS. The composer takes
        the execution reading when it mounts, so capacity cannot live there
        without making every composer wait seven seconds for a number that is
        decoration. It is asked for separately and arrives when it arrives.

        NOT ESTABLISHED IS NOT ZERO. A reading that established nothing
        travels as `why_not`, with the adapter's reason. A runtime with no
        capacity information and a runtime with none remaining are opposite
        facts.

        WINDOWS ARE NOT BLENDED. A five-hour window and a seven-day window are
        different promises in different units; averaging them would invent a
        quantity no provider reported.

        GROUPS, WHERE A RUNTIME HAS THEM. Antigravity's quota belongs to
        groups of models; each window says its `group`, and `model_groups`
        says which model draws on which, with `null` where the runtime's own
        grouping does not place it. `observed_at` travels so the age of a
        reused reading can be said.

        EVERY WINDOW EXPIRED IS SAID, NOT EMPTIED. Dropping expired windows
        once left an `established` reading with no windows and no reason --
        measured, Codex vanished from the picker. The plan is still
        established, so `established` stays as it is; `why_not` carries
        when the last window reset and that nothing newer was read.
        """
        # ONE PROBE AT A TIME, AND ITS READING SHARED FOR A MINUTE: three
        # runtimes' rate-limit files take 7-20 s to read, and every Fluid
        # page that opened asked again (the owner's slowdown).
        from mentis.conversation.shared_answer import answers_of

        def _observe():
            out = {}
            for rt in st.agents.runtimes_discover():
                if not rt.present:
                    continue
                try:
                    cap = st.agents.capacity_observe(rt.kind)
                    live = cap.live_windows()
                    why_not = None if cap.established else (
                        cap.notes[0] if cap.notes else "this runtime reports no capacity")
                    if cap.windows and not live:
                        # Every adapter states `resets_at` as epoch seconds, but
                        # Claude's and Codex's are the provider's value verbatim;
                        # one that is not a usable instant still gets a reason.
                        import time as _time
                        try:
                            last = max(float(w.resets_at) for w in cap.windows)
                            when = _time.strftime("%Y-%m-%d %H:%M",
                                                  _time.localtime(last))
                        except (TypeError, ValueError, OverflowError, OSError):
                            when = "an instant now past"
                        why_not = ("the last reading's window(s) reset at "
                                   + when + "; no newer reading")
                    out[rt.kind] = {
                        "established": cap.established,
                        "plan": getattr(cap.plan, "value", None),
                        "why_not": why_not,
                        "observed_at": cap.observed_at,
                        "windows": [
                            {"label": w.label, "used_fraction": w.used_fraction,
                             "resets_at": w.resets_at, "group": w.group}
                            for w in live],
                        "model_groups": dict(cap.model_groups),
                        # Local model servers' own report: resources, not
                        # quota, so it never becomes a window (MARS `local`).
                        **({"local": cap.local} if cap.local is not None else {}),
                    }
                    if cap.local is not None:
                        out[rt.kind]["why_not"] = None
                except Exception as exc:
                    out[rt.kind] = {"established": False, "windows": [],
                                    "why_not": f"{type(exc).__name__}: {exc}"}
            return {"capacity": out}
        return answers_of(st).get("api/capacity", _observe,
                                  version=lambda: 0,
                                  fresh_for=CAPACITY_FRESH_S)

    if path == "/api/references":
        """What a `#` could mean, and what one turns out to be.

        THE SAME SEAM A DISPATCHED WORKER USES. `mentis/worker.py` already
        answers "find me this by name" and "what is this reference" for
        agents; the composer needs exactly those two answers, and running a
        second implementation would let the picker and the workers disagree
        about what exists. One resolver, two callers.

        `here` does not filter. Referring to something in another
        Conversation is most of the point of referring to anything.
        """
        ref = one("ref")
        surface = _surface(st)
        if ref:
            return surface.resolve(ref)
        return surface.find(one("q", "") or "", int(one("limit", 12)),
                            here=one("conversation"))

    from mentis.worker import SESSION_ROUTE
    if path in (SESSION_ROUTE, SESSION_ROUTE + "/end") and method == "POST":
        """A grant for a session somebody started by hand, or giving one back.

        STANDING ACCESS, BY OWNER DECISION (2026-10-13), for the `claude`,
        `codex` and `agy` sessions the owner opens themselves -- and for a
        session on a runtime Mentis has no adapter for, named by a label
        (`worker.session_label_problem`): the machine-wide
        MCP registration asks here when it starts, and everything after goes
        through `/api/worker` under the grant this returns, like a dispatched
        run's. What the grant admits is `permitted(SESSION_SCOPE)` -- the reads
        and `propose_material` -- and nothing here or there can establish.

        An owner request like every other route here (CLIENT_HEADER), and a
        request PRESENTING a worker grant never reaches it: a dispatched run
        cannot trade its grant for this one through the interface.
        """
        from mentis.worker import (SESSION_PARTICIPANT, SESSION_SCOPE,
                                   permitted)
        payload = body if isinstance(body, dict) else {}
        asked = str(payload.get("corpus") or "")
        if asked and str(pathlib.Path(asked).resolve()) != st.path:
            raise ValueError(
                f"this Mentis does not own that corpus: asked about {asked!r}, "
                f"owns {st.path!r}")
        grants = st.agents.authority
        cv = _surface(st).cv
        if path.endswith("/end"):
            ended = grants.end_session(str(payload.get("grant") or ""),
                                       st.path)
            if ended:
                cv.record_act(actor=ended["participant"],
                              act="manual-session-ended",
                              execution=ended["instance"],
                              runtime=ended["runtime"])
            return {"ok": True,
                    "ended": ended["instance"] if ended else None}
        runtime = str(payload.get("runtime") or "").strip()
        # A RUNTIME MENTIS DOES NOT NAME ITSELF -- not one of its registered
        # runtimes (`conversation.runtime_names`) and not a backend MARS
        # lists -- is accepted as a LABEL: the scope is `SESSION_SCOPE`
        # exactly as for a known one, and the label is only written on the
        # session's acts (`session_label_problem`).
        from mentis.conversation.runtime_names import RUNTIMES
        if runtime not in set(RUNTIMES) | set(st.agents.runtime_names()):
            from mentis.worker import session_label_problem
            problem = session_label_problem(runtime)
            if problem:
                raise ValueError(problem) from None
        pid = cv.resolve_participant(
            SESSION_PARTICIPANT,
            about="Sessions the owner started by hand on any runtime. Which "
                  "runtime and which session are on each act, not here.",
            written_by="mentis/manual-session")
        # A SESSION THAT LOST ITS GRANT -- this server restarted -- asks again
        # as the execution it already is, so the Conversations it opened stay
        # its own. Only one this record shows starting as that Participant on
        # that runtime, that has not ended, and that no live grant holds.
        continues = str(payload.get("continues") or "").strip() or None
        if continues:
            acts = cv.history(execution=continues)
            started = any(a["act"] == "manual-session-started"
                          and a["actor"] == pid and a["runtime"] == runtime
                          for a in acts)
            ended = any(a["act"] == "manual-session-ended" for a in acts)
            if not started or ended or grants.session_held(continues,
                                                           st.path):
                raise PermissionError(
                    f"{continues!r} is not a {runtime} session this record "
                    f"shows started and not ended, with no live grant; start "
                    f"a new session instead")
        token, execution = grants.grant_session(
            st.path, runtime=runtime, participant=pid, execution=continues)
        cv.record_act(actor=pid, act=("manual-session-renewed" if continues
                                      else "manual-session-started"),
                      execution=execution, runtime=runtime,
                      detail={"scope": SESSION_SCOPE})
        return {"grant": token, "execution": execution, "participant": pid,
                "alias": SESSION_PARTICIPANT, "runtime": runtime,
                "scope": SESSION_SCOPE,
                "permits": list(permitted(SESSION_SCOPE))}

    if path == "/api/worker" and method == "POST":
        """The four reads, performed HERE, for a worker that may not open the
        corpus.

        WHY THIS ROUTE AND NOT A DAEMON. This process already opens the
        corpus, already holds the `Surface` that `/api/references` uses, and
        is already the local owner of the record a worker was dispatched
        from. A second service to answer four reads it can already answer
        would be architecture bought for nothing.

        THE BOUNDARY IS THE POINT. A sandboxed worker cannot open a WAL spine
        it may not write beside, and must not be given permission to -- so it
        stops opening anything. It sends an operation, its arguments, and
        which corpus it means. The corpus handle, and every permission that
        goes with it, stays on this side. A worker's filesystem rights no
        longer decide what it may read of the record.

        NARROW ON PURPOSE, AND STILL ONE DOOR. `_result` dispatches the four
        reads; `_operate` dispatches the bounded operations an execution
        dispatched to carry an unaddressed request also holds. Neither accepts a
        path, an arbitrary corpus write, an establishment, or an actor -- and
        WHICH SET APPLIES IS READ OFF THE GRANT, never off the request. An
        ordinary worker presenting an organising operation is refused here, which
        is what keeps organising authority from spreading down a delegation
        chain. Handing work on (`worker.HANDS_OFF`) is not organising and every
        dispatched run holds it, so a chain may be as deep as the work needs;
        no depth counter exists, deliberately.

        AND IT IS NOT OPEN BECAUSE IT IS LOCAL. Reaching this port is not
        permission to ask anything through it. The caller presents the opaque
        grant its execution was dispatched with, and the grant names the
        corpus it is for, so a worker cannot ask about a record it was not
        sent to -- being on this machine buys nothing.
        """
        from mentis.worker import (READS, SOURCE_READS, NotPermitted,
                                   _operate, _result, note_deleted_reads,
                                   permitted)

        payload = body if isinstance(body, dict) else {}
        asked = str(payload.get("corpus") or "")
        # The caller says which record it means, and is refused if this is not
        # it. An owner that answered about whatever it happened to hold would
        # be the same silent substitution `workers_read` exists to prevent.
        if asked and str(pathlib.Path(asked).resolve()) != st.path:
            raise ValueError(
                f"this Mentis does not own that corpus: asked about {asked!r}, "
                f"owns {st.path!r}")
        # Scope is decided against the grant, not against what was asked for.
        grant = st.agents.authority.grant_for(presented, st.path)
        if grant is None:
            raise PermissionError(
                "this question needs a live worker grant for this corpus")
        op = str(payload.get("op") or "")
        allowed = permitted(grant.get("scope"), grant.get("operations"))
        if op not in allowed:
            # A REFUSAL IS AN ANSWER, AND IT SAYS SO WHERE IT HAPPENS. This
            # used to be told to a run by an untracked file beside the
            # checkout, and only about `propose_material`. It belongs here,
            # at the one door every refused operation comes through.
            raise NotPermitted(
                f"{op!r} is not admissible for this execution. It was "
                f"dispatched with scope {grant.get('scope')!r}, which may "
                f"{sorted(allowed)}. If the work needs someone else's role, "
                f"hand it to them with `delegate`; if it needs anything else "
                f"listed here, return the need. This is the "
                f"record telling you what this run may not do -- not a "
                f"malfunction, and not a reason to reach the record another "
                f"way. You run as the owner, so other routes exist; taking "
                f"one because this said no would record this as the owner's own "
                f"act, under an author nobody observed. Report what you "
                f"could not do.")
        args = dict(payload.get("args") or {})
        # WHICH SIDE ANSWERS IS ABOUT WHAT THE OPERATION IS, not about who may
        # do it: `_result` answers the reads, `_operate` answers the acts. The
        # source reads are reads, and they are in their own set rather than in
        # `READS` because a Scratch answer's holding them was decided apart --
        # so both names are asked here. Reading `op in READS` alone sent them to
        # `_operate`, which has no branch for them.
        if op in READS + SOURCE_READS:
            # WHAT THIS RUN MAY DO, handed to the read that reports it. Derived
            # here from the grant, the same place the admission decision comes
            # from, so `orient` cannot say one thing while the door does another.
            surface = _surface(st)
            surface.permits = allowed
            # WHO IS ASKING, from the same grant: `brief` is composed for them.
            # Passed with the call, not set on the Surface, which every
            # request thread shares.
            caller = grant.get("participant")
            # ONE ANSWER PER QUESTION, FOR THIS READ ONLY -- the scope every
            # web GET already reads in (`_Handler._api`), on the Conversations the
            # Surface reads through. Measured on the real Brain: without it an
            # agent's `find` recomputed what a scoped read asks once, at about
            # twice the latency. `READS` only: the source reads ask nothing it
            # holds. Thread-local and ended by any write, exactly as for GET.
            if op in READS:
                with surface.cv.reading():
                    value = _result(surface, op, args, participant=caller)
            else:
                value = _result(surface, op, args, participant=caller)
            # A DRY RUN BY A RUN SAYS A CHOICE WRITTEN INSTEAD OF ASKED (P8),
            # when the run asking has raised no decision. Scratch, which calls
            # the check with no run, is never told this.
            if op == "check_rendering" and isinstance(value, dict):
                from mentis.conversation import render_check
                text = args.get("text")
                value = render_check.with_choices(
                    value, [(None, text if isinstance(text, str) else "")],
                    st.corpus, grant.get("instance"), posted=False)
            # DELETED MATERIAL A READ SHOWED, noted for a Quick Ask's banner
            # as its `read_artifact` bytes are. In memory; nothing recorded.
            note_deleted_reads(grant, op, value)
            return value
        out = _operate(_surface(st), op, args, grant)
        # A DELEGATION IS RECORDED BEFORE IT IS RUN, AND RUNNING IT IS THIS
        # SIDE'S JOB. The worker asked for work to be handed to somebody; the
        # Turn and the child expectation are already durable, and the dispatch
        # goes through the same path the owner's own addressing uses.
        #
        # WHAT A WORKER CAN AND CANNOT INFLUENCE HERE, stated correctly after a
        # reviewer caught this comment claiming "nothing a worker sends decides
        # the runtime". It cannot send a workspace, a deadline or
        # `new_instance` -- none of those is read. ANY RUN CAN pass on a
        # runtime, a model and an effort with the work it hands on, because
        # the owner decided that a decision about them must be able to reach
        # the work it was about, and that configuring the delegation of work a
        # run carries is part of handing it on (the F-2 revision of owner
        # ruling ent-fb17dc421a42). What takes `coordinate`
        # (`worker.may_coordinate`) is picking up work the run does not carry,
        # refused in `_operate` before anything is recorded. Effort joined the other two when a local
        # thinking model spent its whole output budget reasoning and the owner
        # chose to switch that off rather than change the model or the window;
        # they arrive as constraints that selection honours or refuses, never
        # as a choice. ANY RUN CAN state `requires`, and that is the design:
        # stating what the work genuinely needs is the whole of how eligibility
        # works. Since the three runtimes declare different capabilities, a
        # requirement can narrow the field to one -- so `requires` is a real
        # influence on WHERE work runs, exercised by naming a need rather than
        # a provider. The names are checked against declared capabilities in
        # `_operate`, so it cannot be used to name something nothing can mean.
        # A RESUMED REQUEST'S DISPATCHES are already whole -- the same keyword
        # set `posting.ask_mentis` hands `dispatch_soon` -- because nothing in them
        # came from the run.
        for kw in (out.pop("dispatches", None) or ()
                   if isinstance(out, dict) else ()):
            (_enqueue_dispatch or dispatch_soon)(st, **kw)
        spec = out.pop("dispatch", None) if isinstance(out, dict) else None
        if spec:
            dispatch_soon(
                st, conversation=out["conversation"],
                turn=spec.get("turn") or out["turn"],
                participant=spec["participant"], work=spec["work"],
                persona=spec.get("persona"),
                # CONSTRAINTS THE OWNER DECIDED, passed on by the coordinator
                # and recorded with who supplied them. Selection honours them
                # or refuses; nothing here chooses.
                runtime=spec.get("runtime"), model=spec.get("model"),
                effort=spec.get("effort"),
                requires=spec.get("requires") or (),
                expectation=out["expectation"])
        return out

    if path.startswith("/api/who/"):
        """WHAT THE RECORD KNOWS ABOUT ONE NAME. Observed, never inferred.

        Everything here is read from the same two places a dispatched worker
        reads: what the Participant entry says, and what the operational acts
        recorded. Nothing is derived from the prose in `about` -- a line of
        description is a description, and reading "agent" out of it would be
        inference dressed as a capability.

        WHICH IS WHY THERE IS NO `callable` FIELD. Whether a name can be run
        is not a fact this record holds. What it holds is whether that name
        HAS been run, and on what, which is a different and better-founded
        thing: `runtimes` and `models` below are the ones actually observed in
        this name's own history, not a claim about what it could do next.

        No scores, no ranking, no counts presented as quality.
        """
        pid = path[len("/api/who/"):]
        surface = _surface(st)
        who = surface.resolve(pid)
        if not who.get("known"):
            return who
        acts = surface.history(participant=pid, limit=60)["acts"]
        runs = [a for a in acts if a.get("execution")]
        runtimes, models = [], []
        for a in runs:
            if a.get("runtime") and a["runtime"] not in runtimes:
                runtimes.append(a["runtime"])
            m = (a.get("detail") or {}).get("observed_model")
            if m and m not in models:
                models.append(m)
        live, open_runs = [], []
        try:
            # THE SAME COLLISION AS THE DISPATCH ONE, ON A DISPLAY SURFACE.
            # Matching the instance's Address NAME against this name's alias
            # showed one @Ada's live work under a different, deliberately
            # separate @Ada. So this reads RUNS, whose start act names the
            # Participant exactly -- the same reading `/api/working` gives,
            # not a second one. "Working now" is an open run this process
            # holds; an open run nothing here holds is listed, not claimed.
            from mentis.operational.runs import working
            open_runs = [
                {k: r[k] for k in ("run", "instance", "runtime", "state",
                                   "words", "at", "source", "held_here",
                                   "conversation", "turn")}
                for r in working(cv, st.agents, recent=0)["open"]
                if r["actor"] == pid]
            live = [r["instance"] for r in open_runs if r["held_here"]]
        except Exception:
            live, open_runs = [], []
        return {
            **who,
            "working_now": live,
            "open_runs": open_runs,
            # Observed in this name's own history. Not a capability claim.
            "runtimes_observed": runtimes,
            "models_observed": models,
            **_avatar(corpus, cv, pid),
            # WHAT A DEFAULT MAY BE DECLARED AS: the runtimes this Mentis
            # knows how to run, not the ones observed for this name.
            "runtimes_known": (st.agents.runtime_names()
                               if st.agents is not None else []),
            "recent": runs[:6],
            "acts_seen": len(acts),
        }

    if path == "/api/working":
        """WHAT IS ACTUALLY RUNNING, and nothing that merely might be.

        ITS OWN ROUTE BECAUSE IT IS THE CHEAP ONE. `/api/execution` discovers
        runtimes and asks each for its model catalogue, which was measured at
        three and a half seconds; polling that to animate an indicator would
        be absurd. This is a dictionary lookup and a pass over acts.

        RUNS, NOT HANDLES. This used to list instances and their liveness --
        and an instance is a reusable session handle whose last recorded row
        is written when a run ENDS. So while a reused handle carried its next
        run, the file said `finished, exit 0` (about the run before) and this
        said `busy` (about the handle), both true and of different runs. It
        now lists the RECORD's open runs -- a start no end names -- and asks
        this process only what it holds of each (`mentis.operational.runs`,
        the one place a run's state is worded). An open run nothing here
        holds is listed as exactly that: open, current state unknown. It is
        not hidden because this process did not start it.

        A local model and a hosted one arrive by the same path. Local
        capacity is capacity, not a separate species.

        `count=1` IS THE CLOSED ACTIVITY SURFACE'S WHOLE READ. The Lobby says
        "N active runs" and the collapsed Activity strip says "N running"
        while nobody has asked to see a run; those want a number, so they ask
        for one. It is the same `open_runs` the full answer lists -- so the
        number cannot disagree with the rows -- and nothing else: this
        process is not asked what it holds, no ended run is read, and no row
        is worded or followed to the work it waits on. The rows are read when
        Activity is opened, and only then.
        """
        if one("count") == "1":
            try:
                return {"open": len(cv.open_runs()), "counted": True}
            except Exception as exc:
                return {"open": None, "counted": False,
                        "why_not": f"{type(exc).__name__}: {exc}"}
        from mentis.operational.runs import working
        try:
            return working(cv, st.agents)
        except Exception as exc:
            # COULD NOT ASK IS NOT NOTHING RUNNING. An empty list here would
            # render as "nobody is working", which is a claim; this says the
            # question could not be answered, and why.
            return {"open": [], "ended": [],
                    "why_not": f"{type(exc).__name__}: {exc}"}

    if path == "/api/execution":
        """WHAT THIS MACHINE CAN ACTUALLY RUN, discovered rather than listed.

        The composer's `@` picker offers runtimes, models and efforts. None of
        those are configuration here: `runtimes_discover` looks for the real
        executables and `models_list` asks each runtime what it can run. A
        runtime that is not installed comes back `present: false` and the
        picker shows it as absent rather than hiding it -- absent and
        unavailable are different answers, and a person choosing where work
        goes deserves to see which one this is.

        EFFORTS ARE NOT NORMALISED. Each runtime's own effort vocabulary is
        passed through as that runtime said it. There is no common scale,
        because the measured vocabularies genuinely differ.
        """
        out = []
        for rt in st.agents.runtimes_discover():
            row = {"kind": rt.kind, "present": rt.present,
                   "version": rt.version.value,
                   "capabilities": sorted(c.value if hasattr(c, "value") else str(c)
                                          for c in rt.capabilities),
                   "notes": list(rt.notes), "models": []}
            if rt.present:
                try:
                    row["models"] = [
                        {"slug": m.slug, "name": m.display_name or m.slug,
                         "efforts": list(m.efforts),
                         "default_effort": m.default_effort,
                         "locality": m.locality,
                         # WHO SERVES IT, which this payload knew and dropped.
                         # `ModelInfo` has carried `provider` since local models
                         # were discovered, and the picker never saw it -- so a
                         # model served by Ollama was offered under the heading
                         # `codex` with nothing to say otherwise, and the harness
                         # read as the answerer. None means the runtime serves
                         # the model itself, which is a real answer.
                         "provider": m.provider,
                         # Which names reach it, and what this catalogue is,
                         # where the runtime says (Claude: its aliases, and
                         # "what they resolve to, not the full /model menu").
                         "aliases": list(m.details.get("aliases") or []),
                         "catalogue": m.details.get("catalogue")}
                        for m in st.agents.models_list(rt.kind)]
                except Exception as exc:
                    # A runtime present but unwilling to enumerate is a fact,
                    # not an empty list. The picker says so.
                    row["models_why_not"] = (
                        f"models could not be read: {exc}"
                        if isinstance(exc, CatalogueUnavailable)
                        else f"{type(exc).__name__}: {exc}")
            out.append(row)
        return {"runtimes": out, "workspace": st.workspace}

    if method == "POST" and path == "/api/conversations":
        """Open a Conversation. A name, and nothing else required.

        THE SUBSTRATE ASKS FOR ONE THING, so this asks for one thing.
        `open_conversation` takes a name and an optional line about it; no
        agent, Topic, persona, theme or participant is needed to bring one
        into being, and demanding any of them here would be this seam
        inventing ceremony the record does not want.

        There is no draft-conversation state anywhere. A Conversation either
        exists or it does not.
        """
        name = (body.get("name") or "").strip()
        if not name:
            return {"error": "a conversation needs a name"}
        # EVERY DURABLE WRITE CARRIES THE OBSERVATION, not only the ones
        # about governed material. Found by review: conversations, turns,
        # participants and topics were storing no observed writer at all,
        # so the promise held for instructions and quietly failed here.
        new = cv.open_conversation(name, about=body.get("about", ""),
                                   written_by=_observed_writer(st, presented))
        # Whoever opened it takes part in it. Anything else would leave the
        # owner outside the room they just made.
        author = body.get("author")
        if author:
            cv.join(author, new)
        return {"conversation": new, "name": name}

    if path == "/api/conversations":
        out = []
        for c in cv.all_conversations():
            cid = c["id"]
            # COUNTED, NOT READ. This asked for every Turn of every Conversation
            # -- all of their prose, inflated and version-resolved -- and used
            # the whole lot for two numbers. Same two numbers, no bodies.
            turns, last_activity = cv.contribution_tally(cid)
            live = [e for e in cv.active_executions() if e.conversation == cid]
            out.append({
                "id": cid, "name": c["body"]["name"], "about": c["body"]["about"],
                "turns": turns,
                # Posts linked in from elsewhere: shown here, counted apart,
                # never numbered here.
                "linked": len(cv.links_here(cid)),
                "participants": len(cv.participants(cid)),
                # `turns` per Topic STAYS. ConvPicker and MoveBox both render it
                # off this payload, so it is not an unread field -- it is a read
                # field that was being counted the expensive way.
                "topics": [{"id": t["id"], "name": t["body"]["name"],
                            "turns": cv.topic_contribution_count(t["id"])}
                           for t in cv.topics(cid)],
                "awaiting": len(cv.awaiting_response(cid)),
                "live_executions": len(live),
                "last_activity": last_activity,
                # WHEN IT WAS MADE. A Conversation nobody has posted in yet has
                # no `last_activity`; the Sidebar dialog's recent list orders it
                # by this instead, so one made a minute ago is not ranked below
                # every Conversation that has ever had a post.
                "created": c["recorded_at"],
            })
        return {"conversations": sorted(out, key=lambda c: -(c["last_activity"] or 0))}

    if path.startswith("/api/conversations/"):
        rest = path[len("/api/conversations/"):]
        cid, _, tail = rest.partition("/")
        # NOTHING IS WRITTEN INTO A CONVERSATION'S LATER VERSION -- a post, a
        # Topic, a participant, an instruction: a rename's version is the
        # Conversation it renames, never one of its own. Refused with that
        # Conversation named (`Conversations.version_refusal`); reads are
        # answered as they were.
        if method == "POST" and tail:
            refusal = cv.version_refusal(cid)
            if refusal:
                return refusal

        if method == "POST" and tail == "turns":
            """Record the Turn, then do only what the AUTHOR asked for.

            THE OPERATION IS `posting.post`, which Fluid's command door calls
            too; what each authored action means is said there. This door
            observes the writer, and starts each dispatch the operation hands
            back only once all of it is durable: `dispatch_soon` starts a
            thread and records its own failures, so what is owed is never
            left without either a run or a recorded reason there is none.
            """
            out, later = _posting.post(
                cv, corpus, cid, body, agents=st.agents,
                written_by=lambda: _observed_writer(st, presented))
            for kw in later:
                (_enqueue_dispatch or dispatch_soon)(st, **kw)
            return out

        if tail == "work":
            """THE STATE OF EACH PIECE OF WORK THAT BEGINS HERE. Read-only.

            Computed from the record on every read -- expectations, their
            runs, their delegated children and the decisions raised under
            them -- with each field saying whether it is recorded, computed,
            observed at runtime by this process, or unknown. Runtime
            observation qualifies a run the record already says started; it
            never creates one.
            """
            from mentis.operational.work import conversation_work
            return conversation_work(cv, cid, viewer=one("participant"),
                                     runtime=_runtime_observation(st))

        if tail == "export":
            return {"export": True, "conversation": cid}

        if tail == "governs":
            """What governs work here, and what has only been proposed.

            NO MANAGEMENT SCREEN. What is in force in a Conversation is
            part of that Conversation, so it is answered on the
            Conversation, beside its participants and its topics. The
            answer is computed from the links that were already there.
            """
            return cv.governs(cid)

        if method == "POST" and tail == "instructions":
            """Place durable material at this Conversation, from inside it.

            ONE ACT, NOT A TRIP TO AN ADMIN SURFACE. `instruct_conversation`
            has always created the entry and placed it with `scoped-to` in
            one atomic act; this is the door to it. Writing a rule while
            working should cost about what writing a Turn costs.

            WHO IS ASKING DECIDES WHETHER IT GOVERNS. An owner placing
            material establishes it in the same act -- the human does not
            propose to themselves. Anything else is a candidate: recorded,
            addressable, arguable, and delivered to nobody until somebody
            establishes it. That is `propose`, and it is the same entry
            either way.
            """
            text = (body.get("text") or "").strip()
            if not text:
                return {"error": "an instruction needs something to say"}
            # Placement at a Conversation that does not exist is a dangling
            # claim of applicability, so it is refused rather than written.
            if not corpus.read([cid]):
                return {"error": "no such conversation", "conversation": cid}
            # ESTABLISHING IS THE EXPLICIT ACT, NOT THE DEFAULT. This used
            # to establish unless the caller volunteered `propose`, so any
            # caller that simply did not think about it -- an agent with
            # access to this route -- produced governing material. The
            # default is now the safe direction: written down, governing
            # nothing, until somebody says otherwise.
            propose = not bool(body.get("establish"))
            by, unattributed = _attributed(body, corpus=corpus)
            if unattributed:
                return unattributed
            if propose:
                with corpus.atomic():
                    eid = corpus.write(
                        kind="conversation-instruction",
                        body={"text": text, "about": body.get("about", "")},
                        attributed_to=by,
                        written_by=_observed_writer(st, presented))
                    corpus.write(
                        body={"reason": "proposed for this conversation"},
                        attributed_to=by, written_by=_observed_writer(st, presented),
                        link={"from": eid, "to": cid,
                              "relation": "scoped-to"})
            else:
                eid = cv.instruct_conversation(
                    cid, text, about=body.get("about", ""),
                    attributed_to=by,
                    written_by=_observed_writer(st, presented))
            return {"entry": eid, "governs": not propose,
                    "standing": corpus.stands(eid)}

        if method == "POST" and tail == "participants":
            """Bring a name into this Conversation, and say which one it is.

            BOTH HALVES ALREADY EXISTED. `resolve_participant` returns the
            same durable Participant or opens a first one and never a
            duplicate; `join` records that they take part here. Summoning a
            name nobody has used yet is those two calls, and this is the door
            to them.

            IT IS IDEMPOTENT ON THE ALIAS, which is what makes it safe to call
            from a composer: asking twice for @Bob gets the same Bob, so a
            draft that is written, abandoned and written again does not leave
            two of him in the room.

            AN OPERATION KEY (`op`, with the `author` asking) makes a retry
            whose answer was lost say what the first call said -- `created`
            included, which a second call would otherwise report as false
            (opr-4d9dfcd3cb67). Without one it is what it always was.
            """
            alias = (body.get("alias") or "").strip()
            if not alias.startswith("@"):
                alias = "@" + alias
            if alias == "@":
                return {"error": "a participant needs a name"}

            def bring_in():
                from mentis.conversation.versions import Refused
                existed = cv.find_participant(alias)
                try:
                    pid = cv.resolve_participant(
                        alias, about=body.get("about", ""),
                        written_by=_observed_writer(st, presented))
                except Refused as refused:
                    # A FORMER ALIAS IS POINTED AT THE CURRENT ONE, A RESERVED
                    # ONE IS REFUSED: nobody is minted or joined.
                    return refused.refusal
                if pid not in cv.participants(cid):
                    cv.join(pid, cid)
                return {"participant": pid, "alias": alias, "created": existed is None}
            if not body.get("op"):
                return bring_in()
            by, unattributed = _attributed(body, "author", corpus=corpus)
            if unattributed:
                return unattributed
            return _keyed_door(cv, by, body["op"], {
                "route": "participants", "conversation": cid, "alias": alias,
                "about": body.get("about", "")}, bring_in)

        if method == "POST" and tail == "topics":
            """Open a Topic in this Conversation, and say which one it is.

            THE SEAM ALREADY EXISTED; only the door was missing. A Topic is
            opened by `cv.open_topic`, which is what the fixtures have always
            used. Nothing new is stored and nothing is inferred: a Topic comes
            into being because somebody asked for one by name.

            IDENTITY IS THE ENTRY, NOT THE NAME. The id is returned so the
            caller can attach THAT to a Turn. A composer that kept the string
            and re-matched it later would be inventing a second, weaker notion
            of which Topic this is, and two Topics may legitimately share a
            label.

            AN OPERATION KEY (`op`) MAKES IT SAFE TO REPEAT: the same key and
            request is answered with the Topic it first opened and opens no
            second one, so a composer retrying after a lost answer files under
            one Topic (opr-4d9dfcd3cb67). Without one it opens a Topic each
            time, as it always did.
            """
            name = (body.get("name") or "").strip()
            if not name:
                # An unnamed Topic is not a Topic. Refuse rather than open one
                # called "" that nobody can ever find again.
                return {"error": "a topic needs a name"}
            by, unattributed = _attributed(body, "author", corpus=corpus)
            if unattributed:
                return unattributed
            about = body.get("about", "")

            def open_one():
                tid = cv.open_topic(cid, name, about=about, attributed_to=by,
                                    written_by=_observed_writer(st, presented))
                return {"topic": tid, "name": name}
            if not body.get("op"):
                return open_one()
            return _keyed_door(cv, by, body["op"], {
                "route": "topics", "conversation": cid, "name": name,
                "about": about}, open_one)

        if tail == "origin":
            """Where this Conversation was opened from, resolved now -- or
            `origin: null` for one that was opened from nothing."""
            from mentis.conversation.anchors import origin as _origin
            return {"conversation": cid, "origin": _origin(cv, cid)}

        if tail == "orientation":
            return cv.orientation(cid, one("participant"), topic=one("topic"),
                                  recent=int(one("recent", 6)))

        if tail == "media":
            """THE TURNS OF THIS CONVERSATION THAT CARRY MEDIA.

            Media is a fact about the Conversation, not about how far a reader
            has scrolled: the header says how much of it there is and the panel
            lists it. Both were built from the Turns the flow had in hand, which
            was every Turn -- bounded, a Conversation with 321 attachments said
            it had 12.

            IT NARROWS THE CANDIDATES AND DECIDES NOTHING. What counts as an
            attachment, a returned artifact or a marked representation is said
            once, in `media.ts`, and must not be said a second time here: this
            sends the Turns that could possibly carry one -- a part that is not
            text, something a run returned, or a Turn an operational act names
            -- and the client's own reading of them is unchanged.
            """
            rows = cv.turns(cid)
            # ONLY THE ACTS THAT CAN CARRY MEDIA. "Any act that names a Turn"
            # was 287 of 326 Turns -- the whole Conversation again, by another
            # name. A representation is marked or generated by a `media-` act;
            # anything else reaches Media as a PRODUCT, so `produced` is asked
            # rather than assumed.
            from mentis.operational.products import products_of
            here = corpus.operational(conversation=cid)
            made = products_of(brain, [a["id"] for a in here])
            named = {a["turn"] for a in here
                     if a.get("turn")
                     and (str(a.get("act", "")).startswith("media-")
                          or made.get(a["id"]))}
            # A LEAN VIEW, because this one read spans the whole Conversation.
            # `_turn_view` answers everything a Turn in the flow is drawn with
            # -- every addressee's delivery status, every expectation's state --
            # and none of that is what a media card shows. Asked of a hundred
            # Turns it was half a megabyte and a quarter of a second; what Media
            # needs is who, when, and the parts.
            returning = {}
            for a in here:
                if a["act"] in ("result-returned", "result-recovered") and a.get("turn"):
                    returning.setdefault(a["turn"], []).extend(
                        (a.get("detail") or {}).get("returned_artifacts") or [])
            out = []
            for r in rows:
                entry = r["entry"]
                parts = entry["body"]["parts"]
                if not (r["turn"] in named or returning.get(r["turn"])
                        or any(p.get("type") != "text" for p in parts)):
                    continue
                out.append({
                    "id": r["turn"],
                    "number": r["number"],
                    # WITHOUT THE PROSE. A hundred Turns of text was four
                    # hundred kilobytes of words no media card draws; the Turn's
                    # own prose is read where the Turn is read. Only the parts
                    # that could BE media travel here.
                    "parts": [_artifacts.annotate_part(corpus, p)
                              for p in parts if p.get("type") != "text"],
                    "returned_with": [
                        _artifacts.public(_artifacts.describe(
                            corpus, ref, verify="cached"))
                        for ref in returning.get(r["turn"], ())
                        if not entry.get("deleted")],
                    "author": entry["attributed_to"],
                    "author_alias": cv.alias(entry["attributed_to"]),
                    "written_by": entry["written_by"],
                    "at": entry["recorded_at"],
                    "topics": cv.topics_of(r["turn"], cid),
                    "expectations": [],
                    "addressees": [],
                })
            # AND THE ACTS `mediaOf` READS: the marks and generations, and the
            # acts that produced something. They were taken from the shell's
            # general history read, which was the Conversation's OLDEST three
            # hundred acts -- a mark on a newer Turn was never seen. These are
            # the acts this read already selected the Turns by, so nothing is
            # read twice. LEAN, like the Turns above: only the fields `mediaOf`
            # reads travel -- `detail` only on a media act, and of each product
            # only what says whether its bytes are held and what it is called.
            def lean_product(p):
                b = p.get("body") or {}
                return {"entry": p["entry"], "summary": p.get("summary"),
                        "body": {"content": b.get("content"),
                                 "locator": b.get("locator"),
                                 "payload_type": b.get("payload_type"),
                                 "envelope": {"claimed_name": (
                                     b.get("envelope") or {}).get("claimed_name")}}}
            acts = [{"id": a["id"], "act": a["act"], "at": a["at"],
                     "actor": a["actor"], "turn": a.get("turn"),
                     "conversation": a.get("conversation"),
                     "because": a.get("because"),
                     "caused_by": a.get("caused_by"), "about": a.get("about"),
                     "detail": a["detail"] if media_act else {},
                     "produced": [lean_product(p) for p in made.get(a["id"], [])]}
                    for a in here
                    for media_act in [str(a.get("act", "")).startswith("media-")]
                    if media_act or made.get(a["id"])]
            return {"conversation": cid, "turns": out,
                    "turns_total": len(rows), "carrying": len(out),
                    "acts": acts}

        if tail.startswith("thread/"):
            """ONE THREAD'S REPLIES, WHICH THE FLOW DOES NOT CARRY.

            The Conversation flow renders thread roots; the rail renders one
            thread. They are two reads because they are two questions, and
            because a four-hundred-reply thread must not be the price of
            opening the Conversation it sits in. Opening the thread is the ask.

            THE READ IS UNFOCUSED, because the rail always was: a thread is a
            reply structure, not a topic slice, and both callers already hand
            it the unfocused conversation. Scoping it to a Topic would be a
            new behaviour, not the one being preserved.

            It carries the root Turn itself as well as the replies. The flow is
            bounded now, so the root is not necessarily in hand -- a thread
            reached by a deep link or from a focused flow would otherwise open
            on nothing.
            """
            root = tail.split("/", 1)[1]
            rows = cv.turns(cid)
            chain = _reply_chain(corpus, [r["turn"] for r in rows])
            root_of, _ = _threads_of(rows, chain)
            under = _subtree(rows, chain)
            numbers = {r["turn"]: r["number"] for r in rows}
            if root not in numbers:
                return {"error": f"{root} is not a turn of this conversation",
                        "thread": root}
            if root_of.get(root) != root:
                return {"error": f"{root} is a reply, not a thread root; its "
                                 f"thread is {root_of.get(root)}",
                        "thread": root, "root": root_of.get(root)}
            kids = under.get(root, [])
            in_scope = set(numbers)
            head = next(r for r in rows if r["turn"] == root)

            def placed(r):
                return _placed(_turn_view(st, r["entry"], r["number"]),
                               r["turn"], root_of=root_of, chain=chain,
                               under=under, in_scope=in_scope, numbers=numbers)

            return {
                "conversation": cid, "root": root,
                "turn": placed(head),
                "replies_total": len(kids),
                "replies": [placed(r) for r in kids],
            }

        if not tail:
            # UNDER ITS CURRENT NAME: a renamed Conversation reads as it now does.
            conv = cv.conversation_now(cid) or corpus.read([cid])[0]
            rows = cv.turns(cid)
            links_here = cv.links_here(cid)
            focus = one("topic")
            wanted = (set(x["id"] for x in cv.topic_contributions(focus))
                      if focus else None)
            chain = _reply_chain(corpus, [r["turn"] for r in rows])
            root_of, _ = _threads_of(rows, chain)
            under = _subtree(rows, chain)
            numbers = {r["turn"]: r["number"] for r in rows}
            units, unit = _scope_units(rows, wanted, root_of)
            asked, refusal = _batch_asked(one, units)
            if refusal:
                return refusal
            chosen = units[asked["lo"]:asked["hi"]]
            # WHAT THE SCOPE REACHES, for `parent_in_scope`. The Topic's Turns
            # when one is in force, the Conversation's otherwise -- the same
            # set the flow is drawing from, so the answer is about this read.
            in_scope = wanted if wanted is not None else set(numbers)
            delivered = [
                _placed(_turn_view(st, r["entry"], r["number"]), r["turn"],
                        root_of=root_of, chain=chain, under=under,
                        in_scope=in_scope, numbers=numbers)
                for r in chosen]
            from mentis.conversation.anchors import origin as _origin
            return {
                "id": cid, "name": conv["body"]["name"],
                "about": conv["body"]["about"],
                # OPENED FROM AN ANCHOR, if it was: resolved now, never copied.
                "origin": _origin(cv, cid),
                "participants": [{"participant": p, "alias": cv.alias(p),
                                  **_runtime_default(cv, p, declared)}
                                 for declared in (cv.runtime_defaults_now(),)
                                 for p in cv.participants(cid)],
                "topics": [{"id": t["id"], "name": t["body"]["name"],
                            "about": t["body"]["about"],
                            "turns": len(cv.topic_contributions(t["id"]))}
                           for t in cv.topics(cid)],
                # AN OPTIONAL FIELD THAT NOBODY FILLED IN IS ABSENT, NOT AN
                # ERROR. `about` is a field the Kind DECLARES; nothing requires
                # an instruction to carry one, and the spine never fills a
                # missing key in. This read insisted on it, so the first
                # instruction written without one -- a replacement carrying
                # only the words somebody changed -- took the whole
                # Conversation down with a KeyError. Measured on a fixture
                # Brain, 2026-09-28.
                # WHAT DIRECTS WORK HERE, NOT WHAT IS CALLED AN INSTRUCTION.
                # This listed `cv.instructions`, which asks whether the entry is
                # a `conversation-instruction` -- so a `rule` the owner placed
                # here and established was delivered to every execution in this
                # Conversation, reported by `governs()`, and ABSENT from the
                # list under this heading. The one surface the owner reads a
                # Conversation through disagreed with what the Conversation
                # actually does. It asks `placed_procedural` now, which is what
                # delivery asks, so the two cannot disagree -- and each row says
                # its `kind`, because a reader seeing a rule under this heading
                # is entitled to know it is a rule.
                "instructions": [{"id": i["id"],
                                  "kind": (i.get("definition") or {}).get("name"),
                                  # THE WORDS THAT ACTUALLY GOVERN, by the one
                                  # selection delivery uses. Reading `text`
                                  # alone showed a placed Persona as blank.
                                  "text": content_of(i, *rendering_of(
                                      corpus, (i.get("definition") or {}).get("name"))),
                                  "about": (i["body"] or {}).get("about")}
                                 for i in cv.placed_procedural(cid)],
                # WHAT THE FLOW DRAWS, BOUNDED. Topic first and batch
                # second -- the order `in_view` fixes -- and the batch is
                # taken in the unit the flow renders: threads unfocused,
                # the Topic's Turns when one is in force. See `_scope_units`.
                "turns": delivered,
                "turns_total": len(rows),
                # POSTS FROM ELSEWHERE, SHOWN HERE AS LINKS. Not Turns of this
                # Conversation: each keeps its own number in its own home, and
                # says where that is, who linked it and when.
                # Filtered BEFORE the view is built: `_linked_view` reads the
                # entry, its home and a full turn view per link, and building
                # those only to drop them is the cost a window exists to avoid.
                "linked": [_linked_view(st, x, cid)
                           for x in in_view(links_here, wanted,
                                            key=lambda x: x["link"]["from"])],
                "linked_total": len(links_here),
                "focus_topic": focus,
                "awaiting": cv.awaiting_response(cid),
                # WHAT IS OWED, WHICH IS NOT THE SAME AS WHO WAS ADDRESSED.
                # `awaiting` is descriptive -- somebody was spoken to and has
                # not replied -- and must not become an obligation through UI
                # wording. This is the recorded obligation: what was asked, who
                # carries it, whether anything answered, what it delegated,
                # what failed, and whether nobody is carrying it at all. Every
                # state the interface needs to show is a field here rather
                # than a status this computes.
                # EACH OBLIGATION SAYS WHICH THREAD IT HANGS IN, so the
                # interface can place it without holding every Turn: it used
                # to find the Turn in `turns[]` and silently showed nothing
                # once that was a batch. The aliases ride along for the same
                # reason: the mark reads "<somebody> needs your <thing>", and
                # the name used to be read off a Turn in hand.
                #
                # OUTSTANDING ONLY. This list has to be whole while the flow
                # is a batch -- an obligation on an older Turn must still be
                # marked -- so it is the one part of the read that does not
                # shrink with the batch, and it was 78% of a bounded read: 134
                # full rows of which 119 were already answered. An answered
                # expectation marks nothing and is not owed; it is still read,
                # in full, where one expectation is read -- the Turn's own
                # `expectations`, and `/api/owed`.
                #
                # Every state of the loop still rides on each row, because the
                # interface must be able to say which state a request is in by
                # reading fields rather than inferring one. `latest_activity`
                # is the exception: two thirds of a row, declared nowhere and
                # read by nothing here.
                # `path` is the Turns from the thread's root down to the one
                # the obligation hangs on. A Turn drawn in the flow marks what
                # is owed AT OR UNDER IT; matching on the thread's root instead
                # marked a Turn for an obligation on a sibling branch, which in
                # a focused flow -- where a filed reply stands at top level --
                # is a "needs you" on a post that needs nothing.
                "owed": [
                    dict({k: v for k, v in o.items() if k != "latest_activity"},
                         root=root_of.get(o["turn"], o["turn"]),
                         # The chain was read for this Conversation's Turns;
                         # an obligation on a Turn outside them still starts
                         # its walk from that Turn's own link.
                         path=_ancestry(o["turn"], chain if o["turn"] in numbers
                                        else {**chain, **_reply_chain(
                                            corpus, [o["turn"]])}, numbers),
                         requested_by_alias=cv.alias(o["requested_by"]),
                         expected_of_alias=(cv.alias(o["expected_of"])
                                            if o["expected_of"] else None))
                    for o in cv.expectations(conversation=cid, open_only=True)
                    if not o["response_present"]],
                "failures": cv.failures_in(cid),
                # WHAT THIS READ DELIVERED AND WHAT LIES OUTSIDE IT, counted
                # in the unit this read pages by and in the scope it was asked
                # about. The client renders these; it does not recompute them
                # from collections of its own.
                "batch": {
                    "unit": unit,
                    "shown": len(delivered),
                    "units_total": len(units),
                    "older": asked["lo"],
                    "newer": len(units) - asked["hi"],
                    "first": chosen[0]["number"] if chosen else None,
                    "last": chosen[-1]["number"] if chosen else None,
                    "size": asked["size"],
                    "mode": asked["mode"],
                },
            }

    # ---- anchored interaction ---------------------------------------------
    if path == "/api/anchors" or path.startswith("/api/anchors/"):
        """Anchors, reactions and deep dives: `mentis.conversation.anchors`.

        THIN DOORS. Every rule -- what may be anchored, who may change a
        reaction, what deletion refuses, what a retry key means -- is in the
        service, which the worker surface calls too, so the two cannot
        disagree. A refusal is the service's own words.
        """
        from mentis.conversation import anchors as _anchors
        from mentis.conversation.versions import Refused as _AnchorRefused
        rest = path[len("/api/anchors"):].lstrip("/")
        aid, _, tail = rest.partition("/")
        writer = _observed_writer(st, presented)
        try:
            if method == "POST" and not rest:
                by, unattributed = _attributed(body, "author", corpus=corpus)
                if unattributed:
                    return unattributed
                return _anchors.create_anchor(cv, body, by=by,
                                              written_by=writer)
            if method == "GET" and aid == "from" and tail:
                return _anchors.route_back(cv, tail)
            if method == "GET" and aid and not tail:
                return _anchors.view(cv, aid)
            if method == "GET" and tail == "interactions":
                return _anchors.interactions(cv, aid)
            if method == "POST" and tail in ("reactions", "deep-dives"):
                by, unattributed = _attributed(body, "author", corpus=corpus)
                if unattributed:
                    return unattributed
                if tail == "reactions":
                    return _anchors.react(cv, aid, body, by=by,
                                          written_by=writer)
                return _anchors.deep_dive(cv, aid, body, by=by,
                                          written_by=writer)
        except _AnchorRefused as refused:
            return refused.refusal
        return {"error": f"no anchor route {method} {path}"}

    # ---- timers -----------------------------------------------------------
    if path.startswith("/api/timers/"):
        """A timer block's ledger: `mentis.conversation.timers`.

          GET  /api/timers/<post>/<name>?holder=&part=&tz=&midnight=&utc_offset=
               the holder's timer as it stands now (the owner's by default),
               with "today" from the viewer's local midnight: their IANA zone
               `tz`, else their own `midnight` (ISO-8601 with offset), else
               `utc_offset` (minutes east of UTC)
          POST /api/timers/<post>/<name>/marks
               {action, at?, run?, replaces?, reason?, part?, op?, tz?,
                midnight?, utc_offset?}: one mark, and the state after it
          GET  /api/timers/about/<ref>?holder=&tz=&midnight=&utc_offset=
               the time ONE person (the owner by default) spent on a Topic,
               Conversation or post: their runs across every timer whose
               post names it in about=. Read only; never mixed

        THESE ACT AS THE BRAIN'S OWNER, as the forms routes do: the screen is
        the owner's, so a mark is a PERSON's -- the owner's, in their own
        ledger -- and any `author` in the body is ignored. A person is never
        treated as an agent here. An agent marks only through its `timer`
        tool, on the request its own run carries. Every rule is the
        service's; a refusal is its own words, with `refused: true`.
        """
        from mentis.conversation import timers as _timers
        from mentis.conversation.versions import Refused as _TimerRefused
        from mentis.conversation.owner import _owner
        bits = path[len("/api/timers/"):].split("/")
        src = body if method == "POST" else {}

        def given(key):
            got = (src or {}).get(key) if method == "POST" else one(key)
            return None if got in (None, "") else got

        def number(key, default):
            got = given(key)
            if got is None:
                return default
            try:
                return int(got)
            except (TypeError, ValueError):
                raise _BadRequest(f"{key} is a whole number, not {got!r}")
        zone = {"tz": given("tz"), "midnight": given("midnight"),
                "utc_offset": number("utc_offset", 0)}
        who = _owner(cv)
        if bits[0] == "about":
            if method != "GET" or len(bits) != 2 or not bits[1]:
                raise _BadRequest("time spent is GET /api/timers/about/<ref>")
            holder = one("holder") or who
            if not holder:
                raise _BadRequest("this record names no owner: name whose "
                                  "time to add up, ?holder=<participant>")
            try:
                return {**_timers.time_spent(cv, bits[1], holder, **zone),
                        "you": who}
            except _TimerRefused as refused:
                return {**refused.refusal, "refused": True}
        if len(bits) not in (2, 3) or not all(bits[:2]) \
                or (len(bits) == 3 and bits[2] != "marks"):
            raise _BadRequest("a timer is /api/timers/<post>/<name>, and its "
                              "marks /api/timers/<post>/<name>/marks")
        tpost, tname = bits[0], bits[1]
        part = number("part", 0)
        try:
            if method == "GET" and len(bits) == 2:
                holder = one("holder") or who
                if not holder:
                    raise _BadRequest("this record names no owner: name whose "
                                      "timer to read, ?holder=<participant>")
                return {**_timers.timer_state(cv, tpost, tname, holder=holder,
                                              part=part, **zone),
                        "you": who}
            if method == "POST" and len(bits) == 3:
                if not who:
                    raise _BadRequest("this record names no owner, so whose "
                                      "timer this is cannot be told")
                replaces = src.get("replaces") or []
                if isinstance(replaces, str):
                    replaces = [replaces]
                if not isinstance(replaces, list) or not all(
                        isinstance(x, str) for x in replaces):
                    raise _BadRequest("replaces is a mark id or a list of them")
                got = _timers.mark(
                    cv, tpost, tname, action=src.get("action"), by=who,
                    part=part, at=src.get("at"),
                    run=src.get("run"), replaces=replaces,
                    reason=src.get("reason"),
                    written_by=_observed_writer(st, presented),
                    op=src.get("op"))
                return {**got, "you": who,
                        "state": _timers.timer_state(
                            cv, tpost, tname, holder=who, part=part, **zone)}
        except _TimerRefused as refused:
            return {**refused.refusal, "refused": True}
        raise _BadRequest(f"no timer route {method} {path}")

    # ---- turns ------------------------------------------------------------
    if path == "/api/turns" and method == "GET":
        return _turns_read(st, query)

    if path.startswith("/api/turns/"):
        rest = path[len("/api/turns/"):]
        tid, _, tail = rest.partition("/")

        if tail == "export":
            return {"export": True, "turn": tid}

        if method == "POST" and tail == "address":
            return _address_existing(st, tid, body,
                                     enqueue=_enqueue_dispatch or dispatch_soon)

        if method == "POST" and tail in ("expect", "topics",
                                         "link", "move"):
            # A DELETED TURN IS INERT GOING FORWARD: it is not pointed at
            # anybody, asked of, filed anew or linked anywhere new. Ending a
            # filing or a link it already had gives it no new effect, so
            # `unfile` and `unlink` are not refused here.
            from mentis.conversation.versions import inert_refusal
            refusal = inert_refusal(corpus, tid)
            if refusal:
                return refusal

        if method == "POST" and tail == "topics":
            """File an EXISTING Turn under a Topic of its own Conversation.

            EXPLICIT, AND ONLY WHAT WAS ASKED. Either `topic` names one that
            exists, or `name` opens one in the Turn's Conversation and files
            the Turn under it in the same step -- never both, never a match on
            the label, because two Topics may share one. `by` is required: a
            filing is something somebody did, and the link carries who.

            Nothing is moved. The Turn's `in-conversation` link is untouched;
            filing adds one `about-topic` link, or none if it is already filed
            there. While a filing is IN FORCE a second one writes nothing;
            once it has been un-filed (`/unfile`) filing again writes a new
            link, with its own who and when. Filed, un-filed, filed again:
            three facts, all kept.

            A Turn LINKED into another Conversation may be filed under that
            Conversation's Topics too; see `/link`.
            """
            by = (body.get("by") or "").strip()
            if not by:
                return {"error": "a filing needs `by`: who filed it"}
            topic = (body.get("topic") or "").strip() or None
            name = (body.get("name") or "").strip() or None
            if bool(topic) == bool(name):
                return {"error": "give exactly one of `topic` (an existing "
                                 "Topic's id) or `name` (a new Topic)"}
            conversation = cv.conversation_of(tid)
            if conversation is None:
                raise ValueError("that is not a Turn in any conversation")
            wrote = _observed_writer(st, presented)
            with corpus.atomic():
                if name:
                    topic = cv.open_topic(conversation, name,
                                          attributed_to=by, written_by=wrote)
                existing = cv.filing(tid, topic)
                filing = cv.assign_topic(tid, topic, attributed_to=by,
                                         written_by=wrote)
                # FILING AN EXISTING TURN IS SOMETHING SOMEBODY DID, later,
                # like addressing it: said in operational history as well as
                # by the link. Only when something was written.
                if existing is None:
                    cv.record_act(actor=by, act="turn-filed",
                                  conversation=cv.conversation_of_topic(topic),
                                  turn=tid, about=[topic, filing],
                                  detail={"filing": filing})
            return {"turn": tid, "topic": topic, "filing": filing,
                    "created_topic": bool(name),
                    "already_filed": existing is not None,
                    "topics": cv.topics_of(tid,
                                           cv.conversation_of_topic(topic)),
                    "filings": cv.filings_of(tid)}

        if method == "POST" and tail == "unfile":
            """UN-FILE: end this Turn's filing under one Topic. Append-only.

            A deletion record supersedes the filing link, and an act says who
            did it; the filing itself stays in the record, so History reads
            "filed, then un-filed". Not filed there now: nothing is written,
            and the answer says so.
            """
            by = (body.get("by") or "").strip()
            topic = (body.get("topic") or "").strip()
            if not by or not topic:
                return {"error": "an un-filing needs `by` and `topic`"}
            ended = cv.end_filing(tid, topic, by=by,
                                  because=(body.get("because") or None),
                                  written_by=_observed_writer(st, presented))
            return {"turn": tid, "topic": topic, "unfiled": ended,
                    "was_filed": ended is not None,
                    "topics": cv.topics_of(tid, cv.conversation_of(tid)),
                    "filings": cv.filings_of(tid)}

        if method == "POST" and tail == "move":
            """MOVE this Turn to one Topic: un-file it from the other Topics of
            that Topic's Conversation and file it there, in ONE transaction.

            The same records the separate un-file and file steps write, and
            the same refusals; but a move that fails part-way writes nothing,
            so the post is never left filed under no Topic (review 2, R4). A
            deleted Turn is refused, as filing is: a move files anew.
            """
            by = (body.get("by") or "").strip()
            topic = (body.get("topic") or "").strip()
            if not by or not topic:
                return {"error": "a move needs `by` and `topic`"}
            moved = cv.move_to_topic(tid, topic, by=by,
                                     written_by=_observed_writer(st, presented))
            return {"turn": tid, "topic": topic, **moved,
                    "topics": cv.topics_of(tid, cv.conversation_of_topic(topic)),
                    "filings": cv.filings_of(tid)}

        if method == "POST" and tail == "link":
            """LINK this Turn into ANOTHER Conversation. It is not moved.

            Its `in-conversation` link, number, thread and replies are
            untouched. The other Conversation gets one `linked-into` link,
            and -- optionally, in the same step -- a filing under one of ITS
            Topics: `topic` (an existing one) or `name` (opened there). Linked
            there already: nothing is written for the link.
            """
            by = (body.get("by") or "").strip()
            target = (body.get("conversation") or "").strip()
            if not by or not target:
                return {"error": "a link needs `by` and `conversation`"}
            topic = (body.get("topic") or "").strip() or None
            name = (body.get("name") or "").strip() or None
            if topic and name:
                return {"error": "give at most one of `topic` or `name`"}
            wrote = _observed_writer(st, presented)
            with corpus.atomic():
                link, made = cv.link_into(tid, target, by=by, written_by=wrote)
                if name:
                    topic = cv.open_topic(target, name, attributed_to=by,
                                          written_by=wrote)
                filing = None
                if topic:
                    if cv.conversation_of_topic(topic) != target:
                        raise ValueError("that topic does not organise the "
                                         "conversation it is linked into")
                    existing = cv.filing(tid, topic)
                    filing = cv.assign_topic(tid, topic, attributed_to=by,
                                             written_by=wrote)
                    if existing is None:
                        cv.record_act(actor=by, act="turn-filed",
                                      conversation=target, turn=tid,
                                      about=[topic, filing],
                                      detail={"filing": filing})
            return {"turn": tid, "conversation": target, "link": link,
                    "already_linked": not made, "topic": topic,
                    "filing": filing, "created_topic": bool(name),
                    "linked_into": cv.linked_into(tid),
                    "filings": cv.filings_of(tid)}

        if method == "POST" and tail == "unlink":
            """End the link showing this Turn in another Conversation, and
            its filings there with it. Append-only, as un-filing is."""
            by = (body.get("by") or "").strip()
            target = (body.get("conversation") or "").strip()
            if not by or not target:
                return {"error": "removing a link needs `by` and "
                                 "`conversation`"}
            ended = cv.unlink(tid, target, by=by,
                              because=(body.get("because") or None),
                              written_by=_observed_writer(st, presented))
            return {"turn": tid, "conversation": target, "unlinked": ended,
                    "was_linked": ended is not None,
                    "linked_into": cv.linked_into(tid),
                    "filings": cv.filings_of(tid)}

        if method == "POST" and tail == "expect":
            # `material` NAMES WHAT IS BEING ASKED ABOUT, where the request is
            # about durable material. It is what lets an act on that item know
            # it answered this ask -- see `_answered_asks`. It confers nothing
            # on the material and obliges nothing about it.
            #
            # A NEW ASK ABOUT DELETED MATERIAL IS NEW FORWARD USE of it, named
            # by the caller, so it is refused before anything is recorded.
            from mentis.conversation.versions import inert_refusal
            refusal = inert_refusal(
                corpus, *[str(m) for m in (body.get("material") or ()) if m])
            if refusal:
                return refusal
            eid = cv.expect(tid, of=body["of"], kind=body.get("kind", "result"),
                            by=body["by"], because=body.get("because"),
                            material=body.get("material") or ())
            return {"expectation": eid, "state": cv.expectation_state(eid)}

        if not tail:
            return _turn_detail(st, tid)

    # ---- operational history and ancestry ---------------------------------
    if path == "/api/operational":
        from mentis.operational.products import products_of
        # `act` narrows to one kind of act -- the Brief's Annotations reads
        # only `anchor-created`, Conversation-wide, rather than the newest
        # few hundred acts of every kind. A filter on a read; nothing more.
        acts = corpus.operational(
            conversation=one("conversation"), actor=one("actor"),
            turn=one("turn"), act=one("act"),
            newest_first=one("newest") == "1",
            limit=int(one("limit", 200)))
        # What each act LEFT BEHIND, read from the `produced` Relation only.
        # It rides on the act because that is where a reader needs it, not
        # because anything is stored twice: it is computed on every read.
        made = products_of(brain, [a["id"] for a in acts])
        for a in acts:
            a["produced"] = made.get(a["id"], [])
        # WHERE EACH ACT HAPPENED, said rather than looked up. The surfaces
        # that draw acts print the Turn's `#N` and open its thread, and they
        # used to find both by searching the Conversation's Turns -- which
        # worked only while every Turn was in hand. Two fields on the act
        # answer it directly, for acts on Turns no reader is anywhere near,
        # and they are what let a whole-Conversation skeleton be deleted
        # rather than kept for this one purpose.
        #
        # `turn_topics` is there for the same reason: a Topic narrows the
        # operational history as well as the words, and the narrowing used to
        # be done against the Turns the focused flow had loaded. Bounded, that
        # silently dropped every act on an older Topic Turn. The act states its
        # Turn's Topics, so the filter is a fact about the act rather than an
        # artefact of how far the reader has scrolled.
        #
        # ASKED OF ONE CONVERSATION, IT ANSWERS ABOUT THAT ONE. Topics belong
        # to a Conversation, so only a Conversation-scoped read can be narrowed
        # by one; reading every Topic's contributions for every Conversation
        # any of three hundred acts happened to touch was the unbounded read
        # this work exists to remove, moved to another route. Unscoped,
        # `turn_topics` is absent rather than empty: "nobody asked" and "filed
        # under nothing" are different answers.
        here_conv = one("conversation")
        named = {a["turn"] for a in acts if a.get("turn")}
        if named:
            filed = {}

            def homes_by(chain_for):
                homes = {}
                for conv_id in {a.get("conversation") for a in acts
                                if a.get("conversation")}:
                    rows = cv.turns(conv_id)
                    root_of, _ = _threads_of(rows, chain_for(rows))
                    for r in rows:
                        if r["turn"] in named:
                            homes[r["turn"]] = (
                                r["number"], root_of.get(r["turn"], r["turn"]))
                return homes

            # Each Conversation's chain is read for its Turns, so after them,
            # where the whole-record chain was read once before any of them.
            # Taken only if nothing was written meanwhile; otherwise again,
            # then in the old order (`Corpus.settled`).
            def whole():
                chain = _reply_chain(corpus, None)
                return homes_by(lambda rows: chain)

            homes = corpus.settled(
                lambda: homes_by(lambda rows: _reply_chain(
                    corpus, [r["turn"] for r in rows])), whole)
            if here_conv:
                # Read once per Topic rather than once per act: a Conversation
                # has a handful of Topics and may have thousands of Turns.
                for t in cv.topics(here_conv):
                    for x in cv.topic_contributions(t["id"]):
                        if x["id"] in named:
                            filed.setdefault(x["id"], []).append(t["id"])
            for a in acts:
                n, rt = homes.get(a.get("turn"), (None, None))
                a["turn_number"], a["turn_root"] = n, rt
                if here_conv:
                    a["turn_topics"] = filed.get(a.get("turn"), [])
        return {"operational": acts}

    if path == "/api/history":
        from mentis.operational import graph
        return graph(brain, conversation=one("conversation"))

    if path == "/api/provenance":
        from mentis.operational.products import provenance_of
        return provenance_of(brain, one("entry"))

    if path == "/api/gravity":
        from mentis.operational import deferred, reconsideration
        turn = one("turn")
        # ONE TRUNK WHEN ONE IS NAMED. The inspector asks about a Turn, and
        # is answered from that trunk alone; the whole Brain is listed only
        # when nothing narrower was asked.
        if turn:
            r = reconsideration(brain, turn)
            return {"deferred": r["deferred"], "reconsideration": r}
        return {"deferred": deferred(brain)}

    # ---- governance reads --------------------------------------------------
    #
    # THE ENGINES WERE ALREADY HERE. `seam.history()`, `stands(as_at=)` and
    # `delivery.behavioural_sources` were built, correct, and had no caller at
    # all: the answers existed and nothing could ask for them. These are the
    # doors, and they are reads -- they compute, they count, and they decide
    # nothing. See `mentis.conversation.governance`.

    if path == "/api/governance/history":
        """The supersession chain through one item, oldest first.

        What was written, whether anybody established it or nobody did, where
        it was placed, what ended it and why, and which challenges were made
        and whether each was set aside.
        """
        from mentis.conversation.governance import item_history
        entry = one("entry")
        if not entry or not corpus.read([entry]):
            return {"error": "which item? name an entry this record holds",
                    "entry": entry}
        return item_history(brain, entry)

    if path == "/api/governance/standing":
        """What the record said about an item at a moment, beside what it says
        now. Two answers, never merged: "it did not stand until later" is not
        the same statement as "it stands"."""
        from mentis.conversation.governance import standing_as_at
        entry, as_at = one("entry"), one("as_at")
        if not entry or not corpus.read([entry]):
            return {"error": "which item? name an entry this record holds",
                    "entry": entry}
        if as_at in (None, ""):
            return {"error": "as at when? give a time, as the record stamps "
                             "them", "entry": entry}
        try:
            when = float(as_at)
        except (TypeError, ValueError):
            return {"error": "a time is a number, as the record stamps them",
                    "as_at": as_at}
        return standing_as_at(corpus, entry, when)

    if path == "/api/governance/execution":
        """What ONE execution received, grouped by how it reached it.

        Absent, empty and unknown are three different answers here and the
        route returns whichever is true. See the engine.
        """
        from mentis.conversation.governance import execution_sheet
        ref = one("execution")
        if not ref:
            return {"error": "which execution? name one"}
        return execution_sheet(brain, ref)

    if path == "/api/governance/applies":
        """Which way each standing item can reach an execution at all.

        Any way / Placed / By Persona / When named. Read from placement links
        and the composition vocabulary, never from a Kind name.
        """
        from mentis.conversation.governance import applies
        entries = query.get("entry") or None
        return applies(brain, entries)

    if path == "/api/governance/conditions":
        """How often each named item actually reached an execution, and how.

        From delivery records only. Where none names it, it is UNCOUNTED --
        which is said, and is not a count of zero.
        """
        from mentis.conversation.governance import conditions_for
        entries = query.get("entry") or []
        if not entries:
            return {"error": "which items? name one or more `entry`"}
        return conditions_for(brain, entries)

    if path == "/api/governance/deliveries":
        """Which delivery records named this item, newest first.

        THE OTHER DIRECTION FROM `/api/governance/execution`. That door starts
        at an execution; this one starts at an ITEM, which is what "open the
        latest delivery record for this" needs and what a count cannot give.
        Two `entry` values ask which records carried BOTH -- answered here so
        a caller never has to read every delivery to work it out.
        """
        from mentis.conversation.governance import deliveries_naming
        entries = query.get("entry") or []
        if not entries:
            return {"error": "which items? name one or more `entry`"}
        missing = [e for e in entries if not corpus.read([e])]
        if missing:
            return {"error": "name entries this record holds",
                    "not_held": missing}
        try:
            limit = int(one("limit", 50))
        except (TypeError, ValueError):
            return {"error": "a limit is a number", "limit": one("limit")}
        return deliveries_naming(brain, entries,
                                 conversation=one("conversation"),
                                 limit=max(1, limit))

    if path == "/api/governance/questions":
        """The four historical questions, asked one at a time.

        NEVER A PAGE MODE. Each is a question somebody asked, answered on its
        own, with its own empty answer when the record has nothing to say.
        """
        from mentis.conversation import governance as gov
        asked = one("question")
        conversation = one("conversation")
        if asked == "changed":
            since, until = one("since"), one("until")
            return gov.what_changed(
                brain, conversation=conversation,
                since=float(since) if since else None,
                until=float(until) if until else None)
        if asked == "received":
            return gov.what_executions_received(
                brain, conversation=conversation,
                participant=one("participant"))
        if asked == "used":
            return gov.what_was_used(brain, conversation=conversation)
        if asked == "ended":
            return gov.what_ended(brain, conversation=conversation)
        return {"error": f"no such question {asked!r}",
                "questions": ["changed", "received", "used", "ended"]}

    if path == "/api/governance/arrive" and method == "POST":
        """Record that somebody opened Governance. Append-only, per-person.

        THE LAST-LOOKED TIME IS THE ARRIVAL. There is no mark-as-read here or
        anywhere else, and nothing can be set to a time somebody did not
        actually arrive at.
        """
        from mentis.conversation.governance import arrive
        who = body.get("participant")
        if not who:
            return {"error": "who arrived? name a participant"}
        return {"arrival": arrive(cv, who,
                                  conversation=body.get("conversation")),
                "participant": who,
                "conversation": body.get("conversation")}

    if path == "/api/governance/since":
        """What changed between this person's last two arrivals.

        A catch-up is a PAIR of arrivals and the acts between them. Never
        visited is ABSENT; one arrival bounds nothing, and says so.
        """
        from mentis.conversation.governance import since_last_look
        who = one("participant")
        if not who:
            return {"error": "since whose last look? name a participant"}
        return since_last_look(brain, who, conversation=one("conversation"))

    if path == "/api/governance/disputes":
        """Every challenge to one item, and whether each was set aside.

        Both facts stay true at once: the item was disputed AND it stands.
        """
        from mentis.conversation.governance import disputes_of
        entry = one("entry")
        if not entry or not corpus.read([entry]):
            return {"error": "which item? name an entry this record holds",
                    "entry": entry}
        standing = corpus.stands(entry)
        return {"entry": entry, "disputes": disputes_of(corpus, entry),
                "stands": standing["stands"],
                "state": standing_state(standing),
                "coexist": "a dispute revokes nothing. Disputed and standing "
                           "are two facts, and both can be true."}

    # ---- what a Participant would receive ---------------------------------
    if path == "/api/context":
        """What this Participant would receive, recomposed on every ask.

        EVERY INPUT THE ENGINE TAKES IS AN INPUT HERE. `compose()` has always
        accepted material named for the invocation and text supplied for it
        alone, and this door passed neither -- so changing what is named for a
        Participant, or taking one named item back out, could not be previewed
        at all. Both are repeatable, because the engine takes sequences and a
        preview is built by adding and removing one item at a time.

        BRAIN SCOPE IS NOT WILDCARD SCOPE. There is no placement vocabulary
        meaning "the whole Brain", so at Brain scope only the Persona and
        explicitly named material reach, and `topic` is not passed: a Topic
        organises a Conversation and there is no Conversation here. Inventing
        either would be the applicability engine arriving early.

        NO PERSONA NAMED AND PERSONA EXPLICITLY NONE ARE THE SAME ANSWER HERE,
        because the engine draws no distinction between them: `persona=None` is
        the whole of what it understands. One is not manufactured on the way
        past.
        """
        conversation, persona = one("conversation"), one("persona")
        participant = one("participant")
        behavioural = query.get("behavioural") or ()
        material = query.get("material") or ()
        request = one("request", "")
        # THE WORK, which is what dispatch passes as the question: without it
        # this preview could not show the knowledge channel at all, so what a
        # run would actually receive -- adopted knowledge and relevant
        # experience, with their trailers -- was the one part it could not
        # preview. Absent means nobody asked, exactly as in `compose`.
        work = (one("work") or "").strip() or None
        # `recent` is passed ONLY where the caller gave one. The two scopes
        # keep different defaults for how much orientation is compact enough,
        # and a door that always passed a number would flatten them into one.
        try:
            recent = {"recent": int(one("recent"))} if one("recent") else {}
        except (TypeError, ValueError):
            return {"error": "recent is a number of contributions",
                    "recent": one("recent")}
        if conversation:
            comp = cv.compose(conversation=conversation, participant=participant,
                              persona=persona, topic=one("topic"),
                              behavioural=behavioural, material=material,
                              request=request, question=work, **recent)
        else:
            comp = brain.compose(participant=participant, persona=persona,
                                 behavioural=behavioural, material=material,
                                 request=request, question=work, **recent)
        return {
            "scope": "conversation" if conversation else "brain",
            **({"work": work} if work else {}),
            "components": [{"source_kind": c.source_kind,
                            "source_id": c.source_id, "scope": c.scope,
                            "text": c.text, "why": c.why, "about": c.about,
                            **({"title": c.title} if c.title else {}),
                            **({"also": list(c.also)} if c.also else {}),
                            # THE TIER AND WHAT TRAVELS WITH IT, so the
                            # preview can group Governing / Adopted knowledge
                            # / Relevant experience and show each trailer.
                            "tier": c.tier,
                            **({"trailer": c.trailer} if c.trailer else {})}
                           for c in comp.components],
            "conflicts": [{"about": k.about,
                           "components": [c.source_id or c.source_kind
                                          for c in k.components]}
                          for k in comp.conflicts],
            "withheld": list(comp.withheld),
            "payload_chars": len(comp.payload()),
        }

    if path == "/api/resurrect":
        from mentis.operational import reconstruct
        # A reference where the caller has one -- the interface does, the
        # composer sends ids -- and an alias only where that is all there
        # is. Two deliberate Participants may share a name.
        rec = reconstruct(brain, one("participant") or one("alias"),
                          conversation=one("conversation"))
        return {"who": rec.who, "where": rec.where, "persona": rec.persona,
                "completed": rec.completed, "outstanding": rec.outstanding,
                "sufficient": rec.sufficient, "missing": rec.missing,
                "sources": rec.sources, "rendered": rec.rendered()}

    if path == "/api/entries" and method == "POST":
        """Write an entry of any declared Kind. The generic authoring door.

        WHY GENERIC HERE AND SPECIFIC ELSEWHERE. A Conversation instruction
        has a door of its own because creating it and PLACING it is one
        act, and a Persona has one because `name` and `behaviour` are what
        a Persona means. A rule, a lesson, a decision, a finding -- these
        are entries of a declared Kind and nothing more, so they take the
        generic act rather than each needing a route invented for them.

        THE KIND DECIDES THE FIELDS, and the spine enforces that: a body
        carrying anything the Kind does not declare is refused. Nothing
        here holds a list of Kinds, and `/api/kinds` is how a caller learns
        what one takes.

        `establish` is the owner saying this holds. Without it the entry is
        a candidate: recorded, addressable, arguable, governing nothing.

        `links` AND `report`, BOTH OPTIONAL, SAY WHAT THE ENTRY IS ABOUT. An
        outcome is what happened when something was tried, and on its own it
        cannot say where, of what, or with what evidence: its Kind declares
        three fields and refuses more. `links` writes `in-context` and
        `outcome-of` from it (`_ENTRY_LINKS` says why only those), and
        `report` records one `entry-reported` act about it whose detail is the
        caller's structured record. The entry, its links and its act are
        written together or not at all. The act's writer is the one observed
        for this request, the same as the entry's.
        """
        kind = (body.get("kind") or "").strip()
        fields = body.get("body")
        if not kind or not isinstance(fields, dict):
            return {"error": "an entry needs a kind and a body"}
        if corpus.current_definition(kind) is None:
            return {"error": f"no Kind is defined as {kind!r}",
                    "hint": "ask /api/kinds what this record declares"}
        from mentis.conversation.versions import generic_write_refusal
        refusal = generic_write_refusal(kind)
        if refusal is not None:
            return refusal
        by, unattributed = _attributed(body, corpus=corpus)
        if unattributed:
            return unattributed
        establish = body.get("establish", True)
        # CREATING AND ESTABLISHING IS STILL ESTABLISHING. This door confers
        # standing in one act, so material whose Kind declares that it owes a
        # check which could prove it wrong owes one here exactly as it does at
        # `/establish` -- otherwise the requirement is only ever met by callers
        # who chose to come through a door that asks. Asked of the KIND, because
        # the entry does not exist yet; asked ONLY when this act will establish,
        # because writing a candidate nobody has established settles nothing and
        # is where an unfalsifiable conjecture is allowed to sit.
        #
        # NO REASON IS REQUIRED HERE, deliberately and not as an oversight.
        # `create_and_establish` is "a deliberate human creation" in its own
        # words, not the adjudication of somebody else's proposal, and the
        # reason requirement belongs to the standing-changing acts. The
        # falsifier is a different thing: it follows the Kind property and is
        # information the material does not already carry.
        if establish:
            refusal = _falsifier_refusal_for_kind(corpus, kind, body)
            if refusal is not None:
                return refusal
        # WHAT IT SAYS ABOUT ITSELF, ASKED BEFORE ANYTHING IS WRITTEN. See
        # `_entry_links` and `_entry_report`: a refused link or report leaves
        # no entry behind it, because the entry, its links and its report are
        # one act or none.
        # A REQUIREMENT NO RUNTIME CAN DECLARE IS REFUSED WHERE IT IS WRITTEN,
        # in `delegate`'s words, for the field the Kind's own `form` declares
        # holds Capability names, and its references name what they say they do
        # (`body_refusal`).
        from mentis.conversation import body_refusal
        from mentis.api import capability_names
        refusal = body_refusal(corpus, kind, fields,
                                     capability_names())
        if refusal is not None:
            return refusal
        links, refusal = _entry_links(corpus, body.get("links"))
        if refusal is not None:
            return refusal
        if any(r == "draws-on" for r, _, _ in links):
            refusal = _draws_on_source_refusal(corpus, kind)
            if refusal is not None:
                return refusal
        report, refusal = _entry_report(body.get("report"))
        if refusal is not None:
            return refusal
        # THE LADDER'S PROVENANCE GATE HOLDS AT THIS DOOR TOO. A Kind that
        # declares `requires_basis` is written with what it rests on (`basis`,
        # written exactly as `record_material` writes it), and a Kind whose
        # fields declare a contextual result needs what was tried and where
        # (`outcome-of` and `in-context` in `links`). Both asked of the Kind's
        # current definition, by `ladder_writes`, so no door words it apart.
        from mentis.conversation import ladder_writes as _ladder
        try:
            grounds = _ladder.basis_refs(corpus, kind, body.get("basis"))
            ends = {r: t for r, t, _ in links}
            if _ladder.contextual(corpus, kind):
                _ladder.outcome_refs(corpus, kind, fields, ends.get("outcome-of"),
                                     ends.get("in-context"))
        except ValueError as exc:
            return {"error": str(exc), "kind": kind}
        writer = _observed_writer(st, presented)
        try:
            with corpus.atomic():
                if establish:
                    eid = corpus.create_and_establish(
                        kind=kind, body=fields, attributed_to=by,
                        written_by=writer)
                else:
                    eid = corpus.write(kind=kind, body=fields,
                                       attributed_to=by, written_by=writer)
                based = _ladder.write_grounds(corpus, eid, grounds, by=by,
                                              writer=writer)
                written = []
                for relation, to, link_body in links:
                    written.append({"relation": relation, "to": to,
                                    "link": corpus.write(
                                        body=link_body, attributed_to=by,
                                        written_by=writer,
                                        link={"from": eid, "to": to,
                                              "relation": relation})})
                reported = None
                if report is not None:
                    where = next((w["to"] for w in written
                                  if w["relation"] == "in-context"
                                  and _kind_name(corpus, w["to"])
                                  == "conversation"), None)
                    reported = cv.record_act(
                        actor=by, act=REPORTED_ACT, conversation=where,
                        about=[eid, *(w["to"] for w in written)],
                        detail={"reported": report["name"],
                                "written_by": writer,
                                "links": written,
                                "detail": report["detail"]})
        except ValueError as exc:
            # The Kind's own refusal, passed through in its own words.
            return {"error": str(exc), "kind": kind}
        # DEMANDED, THEREFORE RECORDED. A falsifier asked for and then dropped
        # would be a refusal that asked for nothing. `create_and_establish`
        # takes no such argument and is not being given one -- the falsifier is
        # a fact about this act of establishing, not a field of the material --
        # so it rides on an operational act, which is where `/establish` puts
        # it too. Written only when one was given: a Kind that owes none and a
        # caller who volunteered none leave nothing to record.
        falsifier = (body.get("falsifier") or "").strip() or None
        if establish and falsifier:
            cv.record_act(actor=by, act="material-established", about=[eid],
                          detail={"falsifier": falsifier,
                                  "established": "created directly"})
        return {"entry": eid, "kind": kind, "standing": corpus.stands(eid),
                "written_by": writer,
                **({"links": written} if written else {}),
                **({"basis": based} if based else {}),
                **({"report": reported} if reported else {}),
                **({"falsifier": falsifier} if falsifier else {})}

    if path.startswith("/api/entries/") and method == "POST":
        """The standing acts, on ANY entry. Generic on purpose.

        WHY THIS IS NOT A GOVERNANCE SUBSYSTEM. Establishing, superseding
        and disputing are not rules-specific and never were: they are the
        substrate's own vocabulary, and `stands` has always computed the
        answer from them. A rule, a lesson, a decision and a Persona all
        take the same acts because standing is a property of an entry,
        not of a topic. What differs between Kinds is the AUTHORING -- the
        fields they declare -- and that is handled where those fields are.

        No approval states, no queue, no reviewer role, nothing to look
        anybody up in. Establishing is an act somebody is attributed with.

        EVERY ACT HERE RECORDS THAT IT HAPPENED. Each one writes an
        operational act beside the links it wrote, because "what changed
        here, and why" is a question the record has to be able to answer
        from something other than re-deriving it from link timestamps. The
        reason the person gave rides on the act, in their words.

        AND EVERY ACT ASKS WHETHER IT ANSWERED A REQUEST. An owner who was
        asked to decide something, and then went and did it, has answered;
        being asked again would be the record failing to notice what they
        just did. See `_answered_asks`.
        """
        rest = path[len("/api/entries/"):]
        eid, _, act = rest.partition("/")
        if not corpus.read([eid]):
            return {"error": "the record holds no such entry", "entry": eid}
        by, unattributed = _attributed(body, corpus=corpus)
        if unattributed:
            return unattributed
        because = body.get("because", "")

        if act in ("request-adoption", "adopt", "decline", "withdraw-challenge"):
            from mentis.conversation import ladder_writes as ladder
            try:
                writer = _observed_writer(st, presented)
                context = {"conversation": body.get("conversation")}
                if not context["conversation"]:
                    acts = [a for a in cv.history() if eid in (a.get("about") or [])
                            and a.get("conversation")]
                    context["conversation"] = acts[-1]["conversation"] if acts else None
                if act == "request-adoption":
                    return ladder.request(cv, entry=eid, by=by, because=because,
                        scope=body.get("scope"), replaces=body.get("replaces"),
                        writer=writer, context=context)
                if act == "withdraw-challenge":
                    # THE CHALLENGER'S OWN ACT (owner decision 7): refused for
                    # anyone the `disputes` link is not attributed to.
                    return ladder.withdraw(cv, dispute=body.get("dispute"),
                        because=because, by=by, target=eid, writer=writer,
                        context=context)
                return ladder.owner_act(cv, eid, act, body, by=by, writer=writer, context=context)
            except ValueError as exc:
                return {"error": str(exc), "entry": eid, "act": act}

        if act == "set-aside":
            # SETTING ASIDE IS THE OWNER'S ACT, whatever it targets, recorded
            # or standing (owner decision 7). A challenger who wants to take
            # their own challenge back withdraws it instead.
            from mentis.conversation.owner import _owner
            if by != _owner(cv):
                return {"error": "only the owner may set aside a challenge; the "
                                 "participant who made it may withdraw it "
                                 "(withdraw-challenge)", "entry": eid, "act": act}

        # ------------------------------------------------ edit, delete ---
        # INERT GOING FORWARD. Every act here that would give an entry new
        # standing, make it a replacement, or build on it as support asks
        # first whether its line was deleted -- and whether it is a deletion
        # record, or the link that records one, which cannot be withdrawn to
        # restore the item in place. See `mentis.conversation.versions`.
        #
        # `derive-from` AND `support` ARE AMONG THEM, AT EVERY END. Either one
        # writes a new provenance or support link, and a deleted entry is not
        # new evidence whether it is the material doing the deriving or
        # supporting, a source it was derived from, or what it supports.
        from mentis.conversation import versions as _versions
        # A NEW ENTRY OF A KIND ONLY ITS OWN OPERATION WRITES is not written
        # here either (`versions.generic_write_refusal`).
        if act in ("revise", "edit"):
            refusal = _versions.generic_write_refusal(_kind_name(corpus, eid))
            if refusal:
                return {**refusal, "entry": eid, "act": act}
        if act in ("establish", "supersede", "propose-supersession",
                   "establish-replacement", "dispute", "set-aside",
                   "revise", "derive-from", "support", "place", "draw-on"):
            also = body.get("also_replaces") or ()
            if isinstance(also, str):
                also = [also]
            sources = body.get("from")
            sources = (sources if isinstance(sources, list) else [sources])
            supported = body.get("supports") or body.get("draws_on")
            where = body.get("where")
            refusal = _versions.inert_refusal(
                corpus, eid, body.get("replacement"),
                *[s for s in sources if isinstance(s, str)],
                # Stripped as the `support` branch strips it, so padding the
                # id cannot carry it past this question and into the write.
                supported.strip() if isinstance(supported, str) else None,
                # A NEW PLACEMENT, at either end. Placements a new version
                # carries over from the one it replaces are not written here
                # and are not asked: they already existed, and continue.
                where.strip() if isinstance(where, str) else None,
                *also)
            if refusal:
                return {**refusal, "act": act}
        # NO GENERIC ACT WRITES A CONVERSATION'S NEXT VERSION, at either end,
        # before anything is written; renaming is its own operation. The shape
        # refusal asks it again of every predecessor these acts end.
        if act in ("supersede", "propose-supersession",
                   "establish-replacement", "revise"):
            also = body.get("also_replaces") or ()
            refusal = _versions.conversation_line_refusal(
                corpus, eid, body.get("replacement"),
                *([also] if isinstance(also, str) else also))
            if refusal:
                return {**refusal, "act": act}

        # ------------------------------------- a reason, or a refusal ----
        # EVERY ACT THAT CHANGES WHAT THIS BRAIN DURABLY KNOWS CARRIES A
        # STATED REASON, and is refused without one. `_stated_reason` says
        # why in full, and `_CHANGES_STANDING` says which acts those are and
        # which are deliberately not among them. Asked here, after the
        # attribution refusal and the inert-line refusal, because it is the
        # same sort of question they are -- something the record needs in
        # order to mean anything later, which the server has no honest way to
        # supply -- and because an act on a line somebody deleted is told
        # that first: the deletion is the more fundamental answer, and a
        # caller who supplied a reason would still be refused.
        #
        # A CONSTRAINT ON THE RECORD, NOT A GATE ON THE ACTOR: nobody's
        # permission is asked, no approval step is added, no queue exists and
        # no one is waited on. The act is refused for arriving without a
        # reason, exactly as it is already refused for arriving without an
        # actor.
        if act in _CHANGES_STANDING:
            because, unreasoned = _stated_reason(body, act)
            if unreasoned:
                return unreasoned

        # STANDING IS CONFERRED BY THE OWNER, at every door that confers it --
        # the check `/adopt` makes. This is not an authentication claim (see
        # below: no request here can be told apart from the owner's browser);
        # it refuses an act that EXPLICITLY names somebody else as the one who
        # established, replaced or placed material, which the record would
        # otherwise carry as that participant's act. A record naming no owner
        # has nobody to compare against, and is answered as before.
        # `revise` CONFERS STANDING ONLY WHERE THE KIND HAS ANY: revising a
        # Turn, a note or a Topic's name writes its next current version and
        # gives nobody's words standing, so it is not asked of the owner
        # (Turn ent-697f9731855b, R2).
        if act in _OWNER_CONFERS and (
                act != "revise" or _versions.confers_standing(corpus, eid)):
            from mentis.conversation.owner import _owner
            owner = _owner(cv)
            if owner and by != owner:
                return {"error": f"only the owner may {act.replace('-', ' ')}: "
                                 "it confers standing, and this act names "
                                 f"{by!r}, who is not the owner. Ask for "
                                 "adoption instead (request-adoption)",
                        "entry": eid, "act": act, "attributed_to": by,
                        "owner": owner}

        # NEW WORDS FOR THIS ITEM NAME ONLY REQUIREMENTS A RUNTIME CAN DECLARE,
        # whichever door brings them -- the same answer the generic authoring
        # door gives (`body_refusal`).
        if (act in ("edit", "propose-supersession", "revise")
                and isinstance(body.get("body"), dict)):
            from mentis.conversation import body_refusal
            from mentis.api import capability_names
            refusal = body_refusal(corpus, _kind_name(corpus, eid),
                                         body["body"], capability_names())
            if refusal is not None:
                return {**refusal, "entry": eid, "act": act}

        # ------------- WHY THERE IS NO AUTHORITY GUARD ON THIS DOOR ---------
        # THIS LAYER MAKES NO CLAIM IT CANNOT KEEP, so it makes none here.
        # `establish`, `establish-replacement` and `revise` all confer standing,
        # and a guard that refused them when the request "looked like an agent"
        # stood here and has been removed, because it could never fire in
        # production: a request presenting `X-Mentis-Worker` for any path but
        # `/api/worker` is answered 403 above, before `_routes` is reached at
        # all, and `_routes` has exactly one caller. So the only requests that
        # ever arrive here present no grant, and the guard fired only for
        # in-process calls a test or a demonstration made.
        #
        # THE BOUNDARY THAT ACTUALLY HOLDS IS AT THE WORKER SURFACE. No
        # `/api/worker` operation establishes governing material:
        # `mentis/worker.py` says exactly that in the `_operate` docstring --
        # governed material is written with `write`, never
        # `create_and_establish`, and no argument to that surface could ask for
        # standing. That is a bound on what Mentis HANDS OUT, and it is the only
        # version of the claim that is true.
        #
        # AND A REQUEST PRESENTING NO GRANT IS INDISTINGUISHABLE FROM THE
        # OWNER'S BROWSER. The `_api` transport docstring below already records
        # that as measured: within one OS trust domain there is no in-band
        # mechanism that separates the owner's interface from something the
        # owner's interface started, and the cheaper bypass -- opening the
        # corpus directly, three lines, no header -- is strictly worse because
        # it erases the one honest trace this route leaves. So nothing here
        # pretends to tell the two apart.

        if act == "edit":
            """Write the next version of this item. APPEND-ONLY.

            What it means depends on the Kind's own current definition, and
            `versions.edit` says so in full: material the Kind adjudicates is
            PROPOSED as a new version while the standing one goes on standing
            (approval is establish-replacement); a never-established candidate
            is replaced by a new candidate; material the Kind does not
            adjudicate -- a Turn, a note, a Topic's name -- simply has a new
            current version. The old version is kept in every case, and
            nothing is overwritten.

            A Turn takes `text`; anything else takes `body`, in the fields its
            Kind declares.
            """
            try:
                was = corpus.read([eid])[0]
                if (was.get("definition") or {}).get("name") == "topic":
                    fields = body.get("body") or {}
                    got = cv.edit_topic(
                        eid, by=by, name=fields.get("name"),
                        about=fields.get("about"), because=because or None,
                        written_by=_observed_writer(st, presented))
                else:
                    got = _versions.edit(
                        cv, eid, by=by, fields=body.get("body"),
                        text=body.get("text"), because=because or None,
                        written_by=_observed_writer(st, presented),
                        basis=body.get("basis"))
            except _versions.Refused as refused:
                return refused.refusal
            except ValueError as exc:
                return {"error": str(exc), "entry": eid}
            return {**got, "standing": corpus.stands(got["edited"]),
                    "version_standing": corpus.stands(got["version"]),
                    "versions": _versions.history_view(corpus, eid,
                                                       alias=cv.alias)}

        if act == "delete":
            """End this item's line with a deletion record. ERASES NOTHING.

            A `deletion` entry carrying the reason, and a `supersedes` link
            from it to the current version: the item has no current standing
            or effect from now, every act here refuses to build on it, and
            its versions, acts, links and past uses are all still in the
            record. There is no undelete: its content comes back only by
            being written again, with new provenance.
            """
            try:
                got = _versions.delete(
                    cv, eid, by=by, because=(because or "").strip() or None,
                    written_by=_observed_writer(st, presented))
            except _versions.Refused as refused:
                return refused.refusal
            return got

        if act == "establish":
            # The candidate becomes governing material. One act, recorded,
            # attributed, and reversible only by superseding it.
            #
            # AND WHERE THE KIND ITSELF SAYS ITS MATERIAL OWES A CHECK THAT
            # COULD PROVE IT WRONG, THE ACT NAMES ONE. Read from the Kind's
            # CURRENT definition and declared there, never inferred -- see
            # `_falsifier_refusal`, which also says why absent is not false
            # and why the falsifier rides on this act's own body.
            refusal = _falsifier_refusal(corpus, eid, body)
            if refusal is not None:
                return refusal
            falsifier = (body.get("falsifier") or "").strip() or None
            with corpus.atomic():
                link = corpus.establish(eid, attributed_to=by, reason=because)
                # BESIDE THE REASON, ON THE ACT. Not a new Kind, not a new
                # relation and not a second act: what the owner would accept
                # as proof they were wrong to establish this is a fact about
                # this establishing, and belongs where `because` already is.
                # Recorded whenever it was given, whether or not the Kind
                # required it -- a volunteered check is still a check.
                oid = cv.record_act(actor=by, act="material-established",
                                    about=[eid], because=because or None,
                                    detail={"link": link,
                                            **({"falsifier": falsifier}
                                               if falsifier else {})})
            return {"entry": eid, "established": link, "act": oid,
                    "falsifier": falsifier,
                    "standing": corpus.stands(eid),
                    **_answered_asks(cv, eid, by=by, act="established")}

        if act == "supersede":
            """What replaces it, because ending is replacing here.

            A `supersedes` link needs something to supersede WITH, which is
            the honest shape: material is ended by better material, and the
            record keeps both and which came after.

            ONE SUCCESSOR MAY REPLACE SEVERAL PREDECESSORS, and the record
            says so once per predecessor. `also_replaces` names the others.
            The link is what carries the fact that this replaced that, so a
            successor replacing three things writes three links -- anything
            else would leave two of them ended by nothing nameable, and
            `history()` walking from either of them would find no successor.

            THEY ARE WRITTEN IN ONE ACT. All of them, or none: a record in
            which one predecessor was ended and its sibling was not is a
            state nobody chose, and every refusal below is checked for every
            predecessor before anything at all is written.
            """
            replacement = body.get("replacement")
            got = corpus.read([replacement]) if replacement else []
            if not got:
                return {"error": "superseding needs a replacement entry "
                                 "that exists"}
            also = body.get("also_replaces") or ()
            if isinstance(also, str):
                also = [also]
            # The one in the path first, then the others, each named once.
            predecessors = list(dict.fromkeys([eid, *also]))
            # WHAT REPLACES IT HAS TO BE ABLE TO, AND FOR EVERY ONE OF THEM.
            # Only existence was checked once, so a standing rule could be
            # ended by an unestablished candidate, by material of another
            # Kind, or by itself -- each leaving the old material ended and
            # nothing standing in its place, which is a silent gap rather
            # than a replacement. A second predecessor is owed the same.
            for pred in predecessors:
                refusal = _supersession_refusal(corpus, pred, replacement)
                if refusal is not None:
                    return {**refusal, "predecessors": predecessors}
            links, answered = {}, {"answers": [], "answers_a_request": False}
            with corpus.atomic():
                for pred in predecessors:
                    links[pred] = corpus.write(
                        body={"reason": because or "replaced"},
                        attributed_to=by,
                        link={"from": replacement, "to": pred,
                              "relation": "supersedes"})
                    cv.carry_intake_forward(pred, replacement, by=by)
                oid = cv.record_act(
                    actor=by, act="material-superseded",
                    about=list(predecessors), because=because or None,
                    detail={"replacement": replacement, "links": links})
                for pred in predecessors:
                    answered["answers"] += _answered_asks(
                        cv, pred, by=by, act="superseded")["answers"]
            answered["answers_a_request"] = bool(answered["answers"])
            if answered["answers_a_request"]:
                answered["say"] = "The request to you is answered."
            return {"entry": eid, "superseded_by": replacement,
                    "link": links[eid], "act": oid,
                    "predecessors": predecessors,
                    "links": links,
                    "standing": corpus.stands(eid),
                    "replaced": {p: corpus.stands(p) for p in predecessors},
                    "replacement_standing": corpus.stands(replacement),
                    **answered}

        if act == "propose-supersession":
            """Put something forward as a replacement. It replaces nothing.

            THE FACT THAT WAS MISSING, AND WHY IT IS ITS OWN ONE. A proposed
            replacement does NOT supersede anything. It may say what it
            proposes to replace while EVERY PREDECESSOR GOES ON STANDING;
            several competing proposals may name the same predecessor and all
            of them stay readable; and one proposal may name several
            predecessors. Four candidates can be put up for a post the
            incumbent still holds. Only the owner establishing a successor
            replaces anything, and that is `establish-replacement` below,
            which writes `supersedes` -- a different fact, in its own link.

            TWO SHAPES, BECAUSE THE CANDIDATE MAY OR MAY NOT EXIST YET. Name
            an entry with `replacement`, or hand `body` and it is written as a
            candidate of the predecessor's own Kind. Either way it is a
            CANDIDATE: nothing here establishes anything, and a candidate is
            what reaches nobody.

            THE REFUSALS ARE THE SHAPE ONES ONLY -- not itself, both held,
            same Kind -- and they are `_replacement_shape_refusal`, the
            supersede path's own first three. The two it does not ask are the
            two about ending: a proposal does not need to stand, and a
            predecessor it merely names is not losing its scope to anybody.
            Every predecessor is checked before anything at all is written.

            IT ANSWERS NO ASK. Somebody asked to decide something has not
            decided it by proposing an alternative, and recording that they
            had would close a request nobody answered.
            """
            relation = corpus.proposal_relation()
            if relation is None:
                return {"error": "this record declares no relation that "
                                 "proposes the superseding role, so it cannot "
                                 "say one thing is put forward to replace "
                                 "another",
                        "hint": "tools/add_proposed_successor.py declares it"}
            also = body.get("also_replaces") or ()
            if isinstance(also, str):
                also = [also]
            predecessors = list(dict.fromkeys([eid, *also]))
            fields = body.get("body")
            replacement = body.get("replacement")
            if replacement and isinstance(fields, dict) and fields:
                return {"error": "name a replacement that exists, or give the "
                                 "words for one -- not both", "entry": eid}
            was = corpus.read([eid])[0]
            kind = (was.get("definition") or {}).get("name")
            if not kind:
                return {"error": "that is not an entry of any Kind, so there "
                                 "is nothing to propose a replacement for",
                        "entry": eid}
            writer = _observed_writer(st, presented)
            try:
                with corpus.atomic():
                    if not replacement:
                        if not isinstance(fields, dict) or not fields:
                            raise _Refused({
                                "error": "a proposed replacement is either an "
                                         "entry this record holds or the "
                                         "words for one, in the fields its "
                                         "Kind declares",
                                "entry": eid, "kind": kind})
                        # A NEW ENTRY OF A KIND ONLY ITS OWN OPERATION WRITES
                        # is not written here either, exactly as `revise` and
                        # `edit` refuse it (`versions.generic_write_refusal`):
                        # the candidate would be an answer, a set or a marking
                        # nobody gave, and `establish-replacement` could then
                        # make it stand.
                        closed = _versions.generic_write_refusal(kind)
                        if closed:
                            raise _Refused({**closed, "entry": eid,
                                            "act": act})
                        # WRITTEN, NOT ESTABLISHED. The whole point of the act
                        # is that the successor reaches nobody yet. A NEW ENTRY
                        # all the same, so it rests on something: `basis`, or
                        # what the material it would replace rests on.
                        from mentis.conversation import ladder_writes as _ladder
                        refs, pairs = _ladder.version_grounds(
                            corpus, kind, fields, eid, body.get("basis"))
                        replacement = corpus.write(
                            kind=kind, body=fields, attributed_to=by,
                            written_by=writer)
                        _ladder.write_grounds(corpus, replacement, refs, pairs,
                                              by=by, writer=writer)
                    for pred in predecessors:
                        refusal = _replacement_shape_refusal(
                            corpus, pred, replacement)
                        if refusal is not None:
                            raise _Refused({**refusal, "kind": kind,
                                            "predecessors": predecessors})
                    proposal = corpus.propose_supersession(
                        replacement, predecessors, attributed_to=by,
                        reason=because or "proposed as a replacement",
                        written_by=writer)
                    oid = cv.record_act(
                        actor=by, act="supersession-proposed",
                        about=[*predecessors, replacement],
                        because=because or None,
                        detail={"replacement": replacement,
                                "predecessors": predecessors,
                                "links": proposal["links"],
                                "relation": proposal["relation"]})
            except _Refused as refused:
                return refused.refusal
            except ValueError as exc:
                return {"error": str(exc), "entry": eid, "kind": kind}
            return {
                "entry": eid, "proposed_replacement": replacement,
                "kind": kind, "act": oid,
                "predecessors": predecessors,
                "relation": proposal["relation"],
                "links": proposal["links"],
                "standing": corpus.stands(eid),
                "replacement_standing": corpus.stands(replacement),
                "kept": {p: corpus.stands(p) for p in predecessors},
                "ends": "nothing. Every predecessor named here stands exactly "
                        "as it stood a moment ago, and goes on standing while "
                        "this waits.",
                "reaches": "nobody. It is a candidate: in the record, "
                           "addressable and arguable, governing nothing.",
                "competing": "another proposal may name the same predecessors "
                             "and both stay readable; nothing here is a queue.",
                "answers_a_request": False,
                "not_an_answer": "proposing an alternative is not deciding. "
                                 "Any request to you about this is still open.",
            }

        if act == "establish-replacement":
            """Approve a proposed successor. ONE ACT, and it is the owner's.

            WHAT ONE ACT MEANS HERE, EXACTLY: the successor is established AND
            one `supersedes` link is written per predecessor, together, or
            none of it is. A record in which the successor stands and a
            predecessor it replaced is still standing -- or the reverse -- is a
            state nobody chose. This is the same shape the supersede and revise
            paths already keep, and it uses their refusal,
            `_supersession_refusal`, not a second copy of it.

            WHICH PREDECESSORS. By default EVERY ONE THE PROPOSAL NAMED,
            because that is what was put forward and what is being approved --
            approving a proposal to replace three things and ending one of
            them would leave a proposal half-accepted with nothing saying so.
            Naming `also_replaces` says exactly which instead -- WHICH OF THE
            ONES THE PROPOSAL NAMED, never a predecessor it did not. The gate
            above asked "was this proposed?" of `eid` alone, so a caller could
            hand `also_replaces` a predecessor named by a different proposal,
            or by none, and end it with a `supersedes` link and an act
            stamped `from_proposal`. Every predecessor is now asked the same
            question `eid` is, in the refusal loop below where every
            predecessor is owed every check.

            PLACEMENT IS INHERITED, for the reason the revise path inherits it:
            everywhere the replaced material applied is somewhere the
            replacement has to apply, or ending it leaves that scope governed
            by nothing. The refusal that says so is still applied afterwards.

            THE PROPOSAL LINK IS LEFT ALONE. It said what it said, and it is
            still true that this was proposed before it was established. What
            changes is that a `supersedes` link now exists beside it.
            COMPETING PROPOSALS ARE NOT SWEPT UP EITHER: they named a
            predecessor that has now ended, which is a thing a reader can see
            for themselves, and quietly withdrawing somebody else's proposal
            is not this act.
            """
            replacement = body.get("replacement")
            got = corpus.read([replacement]) if replacement else []
            if not got:
                return {"error": "establishing a replacement needs the "
                                 "proposed successor, and this record holds "
                                 "no such entry",
                        "replacement": replacement, "entry": eid}
            proposed = corpus.proposed_supersessions(replacement)
            named = [r["entry"] for r in
                     (proposed or {}).get("predecessors", {}).get("items", [])]
            if eid not in named:
                return {"error": "nothing in the record says this was "
                                 "proposed as a replacement for that. "
                                 "Superseding material nobody proposed "
                                 "against it is the supersede act, which "
                                 "says so plainly.",
                        "entry": eid, "replacement": replacement,
                        "proposed_to_replace": named}
            # AND IF THE SUCCESSOR OWES A CHECK THAT COULD PROVE IT WRONG, THIS
            # ACT NAMES ONE. Asked of the REPLACEMENT and not of `eid`, because
            # the replacement is the material being established here -- the
            # predecessors are being ended, and ending something asks nothing
            # about whether it could be shown wrong. Same helper, same single
            # source, so approving a proposed successor cannot slip material
            # past a requirement the plain establish door would have applied.
            refusal = _falsifier_refusal(corpus, replacement, body)
            if refusal is not None:
                return {**refusal, "act": act, "entry": eid,
                        "replacement": replacement}
            falsifier = (body.get("falsifier") or "").strip() or None
            also = body.get("also_replaces")
            if isinstance(also, str):
                also = [also]
            if also is None:
                # EVERYTHING IT WAS PUT FORWARD TO REPLACE. `eid` first,
                # because that is where the owner is standing.
                predecessors = list(dict.fromkeys([eid, *named]))
                chosen_by = "the proposal"
            else:
                predecessors = list(dict.fromkeys([eid, *also]))
                chosen_by = "the caller"
            unheld = [p for p in predecessors if not corpus.read([p])]
            if unheld:
                return {"error": "the record holds no such entry",
                        "entry": unheld[0], "predecessors": predecessors}
            # EVERY PREDECESSOR IS ASKED WHETHER ITS LINE WAS DELETED, not
            # only those the request named. The guard above sees `eid`, the
            # replacement and `also_replaces`; predecessors an act takes from
            # a proposal it never saw, so a proposal made BEFORE a deletion
            # could still write a standing successor into the deleted item's
            # own history (review F1b).
            refusal = _versions.inert_refusal(corpus, *predecessors)
            if refusal:
                return {**refusal, "act": act, "predecessors": predecessors}
            from mentis.conversation import placements_now
            placed_at = list(dict.fromkeys(
                w for p in predecessors for w in placements_now(corpus, p)))
            already = set(placements_now(corpus, replacement))
            writer = _observed_writer(st, presented)
            try:
                with corpus.atomic():
                    established = None
                    if not corpus.stands(replacement)["stands"]:
                        established = corpus.establish(
                            replacement, attributed_to=by,
                            written_by=writer,
                            reason=because or "the proposed replacement was "
                                              "accepted")
                    for where in placed_at:
                        if where in already:
                            continue
                        corpus.write(
                            body={"reason": "inherited from the material this "
                                            "replaces"},
                            attributed_to=by, written_by=writer,
                            link={"from": replacement, "to": where,
                                  "relation": "scoped-to"})
                    for pred in predecessors:
                        refusal = _supersession_refusal(
                            corpus, pred, replacement)
                        # AND THE QUESTION THE DOOR ASKED OF `eid`, ASKED OF
                        # EVERY PREDECESSOR. This is the one-act door for
                        # APPROVING A PROPOSAL; ending material nobody put
                        # this replacement forward against is the supersede
                        # act, which says so plainly. Asked after the shape
                        # refusals so that a predecessor which is wrong in
                        # more than one way is still told the oldest reason
                        # first, and asked here rather than at the door so
                        # that one refusal rolls the whole act back the way
                        # every other one does.
                        if refusal is None and pred not in named:
                            refusal = {
                                "error": "nothing in the record says this "
                                         "was proposed as a replacement for "
                                         "that. Superseding material nobody "
                                         "proposed against it is the "
                                         "supersede act, which says so "
                                         "plainly.",
                                "entry": pred,
                                "proposed_to_replace": named}
                        if refusal is not None:
                            raise _Refused({**refusal,
                                            "predecessors": predecessors,
                                            "replacement": replacement})
                    links = {}
                    for pred in predecessors:
                        links[pred] = corpus.write(
                            body={"reason": because
                                  or "the proposed replacement was accepted"},
                            attributed_to=by, written_by=writer,
                            link={"from": replacement, "to": pred,
                                  "relation": "supersedes"})
                        cv.carry_intake_forward(pred, replacement, by=by,
                                                written_by=writer)
                    oid = cv.record_act(
                        actor=by, act="material-superseded",
                        about=[*predecessors, replacement],
                        because=because or None,
                        detail={"replacement": replacement, "links": links,
                                "predecessors": predecessors,
                                "established": established,
                                "placed_at": placed_at,
                                # BESIDE THE REASON, as on the establish door:
                                # a check demanded and then dropped would be a
                                # refusal asking for nothing.
                                **({"falsifier": falsifier}
                                   if falsifier else {}),
                                # TRUE OF EVERY PREDECESSOR NAMED HERE, which
                                # is why the loop above refuses any that no
                                # proposal named: the stamp is a claim about
                                # the whole act, and it used to be written
                                # whatever `also_replaces` contained. What
                                # picked them out of the proposal is a second,
                                # separate fact, so it is recorded separately.
                                "from_proposal": True,
                                "predecessors_chosen_by": chosen_by})
                    answered = {"answers": [], "answers_a_request": False}
                    for pred in predecessors:
                        answered["answers"] += _answered_asks(
                            cv, pred, by=by, act="superseded")["answers"]
            except _Refused as refused:
                # Nothing was written: the transaction rolled back, and the
                # refusal says which predecessor it is about.
                return refused.refusal
            answered["answers_a_request"] = bool(answered["answers"])
            if answered["answers_a_request"]:
                answered["say"] = "The request to you is answered."
            standing = corpus.stands(eid)
            return {"entry": eid, "superseded_by": replacement,
                    "replacement": replacement,
                    "established": established, "act": oid,
                    "link": links[eid], "links": links,
                    "predecessors": predecessors,
                    "predecessors_chosen_by": chosen_by,
                    "placed_at": placed_at,
                    "standing": standing,
                    "state": standing_state(standing),
                    "replaced": {p: corpus.stands(p) for p in predecessors},
                    "replacement_standing": corpus.stands(replacement),
                    "one_act": "the successor was established and every "
                               "predecessor it replaced was ended together. "
                               "Past delivery records that name the old "
                               "material stay exactly as they are.",
                    "kept": "the proposal is still in the record and still "
                            "says it was proposed; any competing proposal is "
                            "untouched and still readable.",
                    **answered}

        if act == "dispute":
            """Reject it, without pretending it never existed.

            `disputes` is an ordinary seeded relation and it confers
            nothing: a disputed candidate still does not stand, and a
            disputed established entry still does, because disagreeing with
            something is not the same as ending it. `stands` reports the
            dispute under its own name and lets the reader decide.

            OFFERED ON ANYTHING, AND GATED BY NOTHING. Not by the Kind, not
            by whether standing is meaningful for it, not by whether the
            material is the sort of thing that can be true or false.
            Disputing a note is disputing a note: the challenge is recorded
            and the note is untouched. "Dissent that needs permission is not
            dissent."

            AND IT CARRIES ITS EVIDENCE. A challenge with nothing in it is
            refused -- it would record that somebody objected and lose the
            only part worth keeping, which is what they said. This is a
            shape refusal, like every other refusal here; it is not a
            judgement about whether the objection is any good.
            """
            said = (because or "").strip()
            objection = body.get("from")
            if not said and not (objection and corpus.read([objection])):
                return {"error": "a dispute says why: a challenge carries its "
                                 "evidence, and an empty challenge records "
                                 "that somebody objected while losing what "
                                 "they said",
                        "entry": eid, "needs": "because"}
            # EVIDENCE, WHERE IT IS NAMED, as the agents' `challenge` writes
            # it: a `supports` link from the objection to each held reference.
            evidence = body.get("evidence") or []
            if (not isinstance(evidence, list)
                    or not all(isinstance(r, str) for r in evidence)):
                return {"error": "evidence must be a list of held references",
                        "entry": eid}
            missing = [r for r in evidence if not corpus.read([r])]
            if missing:
                return {"error": "the record holds no such evidence",
                        "entry": eid, "evidence": missing}
            # A DISPUTE COMES FROM SOMETHING THAT SAYS WHY. The objection is
            # an ordinary note, attributed to whoever made it, and the
            # `disputes` link points from that note at the material. A
            # bare flag would record that somebody objected and lose what
            # they said, which is the part worth keeping.
            with corpus.atomic():
                if not objection or not corpus.read([objection]):
                    objection = corpus.create_and_establish(
                        kind="note", body={"text": said},
                        attributed_to=by)
                link = corpus.write(
                    body={"reason": said or "disputed"},
                    attributed_to=by,
                    link={"from": objection, "to": eid,
                          "relation": "disputes"})
                for ref in dict.fromkeys(evidence):
                    corpus.write(body={"reason": said or "disputed"},
                                 attributed_to=by,
                                 link={"from": objection, "to": ref,
                                       "relation": "supports"})
                oid = cv.record_act(actor=by, act="material-disputed",
                                    about=[eid], because=said or None,
                                    detail={"link": link,
                                            "objection": objection})
            return {"entry": eid, "disputed": link, "objection": objection,
                    "act": oid, "standing": corpus.stands(eid),
                    "revokes": "nothing. The material is where it was and "
                               "says what it said.",
                    **_answered_asks(cv, eid, by=by, act="disputed")}

        if act == "set-aside":
            """A dispute was considered, and the material held.

            NOT A THIRD LINK, AND NOT A SUPERSESSION OF THE DISPUTE. Setting
            a challenge aside is the OPPOSING ACT ON THE SAME AXIS: upheld
            is "I attacked it and it held", which restores the material as
            evidence without erasing anything. So it is a `supports` link
            between the same two objects, naming the dispute it answers, and
            the `disputes` link is left exactly where it is.

            WHICH MEANS BOTH STAY TRUE. The item was disputed AND it stands.
            Collapsing those into one word would lose the challenge, which
            is the thing worth keeping: somebody argued, and the argument is
            still there to read.

            THE SAME EVIDENCE RULE AS THE CHALLENGE. A free dismissal is not
            an answer to an argument, so a reason is required here exactly
            as it is there.
            """
            said = (because or "").strip()
            dispute = body.get("dispute")
            if not said:
                return {"error": "setting a dispute aside says why: it is an "
                                 "answer to an argument, not a dismissal of "
                                 "one", "entry": eid, "needs": "because"}
            got = corpus.read([dispute]) if dispute else []
            link_of = (got[0].get("link") or {}) if got else {}
            if (not got or link_of.get("relation") != "disputes"
                    or link_of.get("to") != eid):
                return {"error": "name the dispute being set aside: a "
                                 "`disputes` link recorded against this "
                                 "entry", "entry": eid, "dispute": dispute}
            # THE SUPPORT IS WRITTEN FROM THE OBJECTION, so the objection is
            # asked too. It is only known once the dispute is read, which is
            # why the guard above could not ask it.
            refusal = _versions.inert_refusal(corpus, link_of["from"])
            if refusal:
                return {**refusal, "act": act}
            from mentis.conversation.governance import disputes_of
            from mentis.conversation.ladder import challenges_of
            back = [c for c in challenges_of(corpus, eid)
                    if c["link"] == dispute and c["resolution"] == "withdrawn"]
            if back:
                return {"error": "that challenge was withdrawn by the "
                                 "participant who made it; there is nothing "
                                 "left to set aside", "entry": eid,
                        "dispute": dispute, "withdrawn": back[0]["withdrawn"]}
            already = [d for d in disputes_of(corpus, eid)
                       if d["link"] == dispute and d["set_aside"]]
            if already:
                return {"error": "that dispute has already been set aside",
                        "entry": eid, "dispute": dispute,
                        "set_aside": already[0]["set_aside"]}
            with corpus.atomic():
                link = corpus.write(
                    body={"reason": said, "sets_aside": dispute},
                    attributed_to=by,
                    link={"from": link_of["from"], "to": eid,
                          "relation": "supports"})
                oid = cv.record_act(actor=by, act="dispute-set-aside",
                                    about=[eid], because=said,
                                    detail={"dispute": dispute,
                                            "link": link})
            standing = corpus.stands(eid)
            return {"entry": eid, "dispute": dispute, "set_aside": link,
                    "act": oid, "standing": standing,
                    "disputes": disputes_of(corpus, eid),
                    "erases": "nothing. The challenge is still recorded and "
                              "still says what it said; what is recorded is "
                              "that it was answered and the material held.",
                    **_answered_asks(cv, eid, by=by, act="dispute set aside")}

        if act == "revise":
            """Revise a proposal and establish the revision, in one act.

            THREE FACTS, ONE ACT, AND NONE OF THEM IS AN EDIT. A new entry of
            the same Kind carrying the revised words; the owner's act
            establishing it; and the record that it replaced what was
            proposed. The proposal is KEPT, exactly as written, and was
            never established -- which `standing_state` already has a word
            for: it was replaced before establishment, so it never held.

            PLACEMENT IS INHERITED, because placement is what makes material
            apply. A revision placed nowhere would leave the Conversation
            the proposal was offered to governed by nothing at all, which is
            the refusal the supersede path already makes; here the revision
            simply takes the placements over, in the same act.

            ONE REVISION MAY REPLACE SEVERAL PREDECESSORS, and `also_replaces`
            names the others -- the same parameter and the same shape as the
            supersede path, because it is the same fact being recorded. The
            supersede path could already do it, but only with a successor that
            already exists and stands; when the owner is WRITING the successor
            this was the only one-act door, and "replace both with one, and
            here are the new words" degraded into two acts. One `supersedes`
            link per predecessor, so each of them records what replaced it and
            `history()` walking from any of them finds the successor.

            PLACEMENT IS INHERITED FROM ALL OF THEM, for the same reason it is
            inherited from one: everywhere the replaced material applied is
            somewhere the replacement has to apply, or ending it leaves that
            scope governed by nothing.

            AND THE REFUSALS ARE THE SUPERSEDE PATH'S OWN, applied to every
            predecessor -- `_supersession_refusal`, not a second copy of it.
            Two of those refusals are about the replacement, which here does
            not exist until the act writes it, so they are checked inside the
            transaction and a refusal rolls the whole thing back: nothing is
            written, the refusal names the predecessor it is about, and no
            record is left in which one predecessor was replaced and its
            sibling was not.
            """
            fields = body.get("body")
            if not isinstance(fields, dict) or not fields:
                return {"error": "a revision needs a body: the revised "
                                 "material, in the fields its Kind declares",
                        "entry": eid}
            was = corpus.read([eid])[0]
            kind = (was.get("definition") or {}).get("name")
            if not kind:
                return {"error": "that is not an entry of any Kind, so there "
                                 "is nothing to revise", "entry": eid}
            also = body.get("also_replaces") or ()
            if isinstance(also, str):
                also = [also]
            # The one in the path first, then the others, each named once.
            predecessors = list(dict.fromkeys([eid, *also]))
            # Existence first and outside the transaction, because it is the
            # one refusal that needs nothing to have been written yet.
            unheld = [p for p in predecessors if not corpus.read([p])]
            if unheld:
                return {"error": "the record holds no such entry",
                        "entry": unheld[0], "predecessors": predecessors}
            # EVERY PREDECESSOR IS ASKED WHETHER ITS LINE WAS DELETED, not
            # only those the request named. The guard above sees `eid`, the
            # replacement and `also_replaces`; predecessors an act takes from
            # a proposal it never saw, so a proposal made BEFORE a deletion
            # could still write a standing successor into the deleted item's
            # own history (review F1b).
            refusal = _versions.inert_refusal(corpus, *predecessors)
            if refusal:
                return {**refusal, "act": act, "predecessors": predecessors}
            # THE REVISION IS ESTABLISHED BY THIS ACT, SO IT OWES WHAT AN
            # ESTABLISH OWES. The revision does not exist yet, so the question
            # is asked of `eid`: a revision is a new entry of the SAME Kind, so
            # what that Kind currently declares is what the revision is held
            # to. Without this, `revise` would be a door that confers standing
            # while skipping the requirement -- the same bypass in a different
            # doorway.
            refusal = _falsifier_refusal(corpus, eid, body)
            if refusal is not None:
                return {**refusal, "act": act, "predecessors": predecessors}
            falsifier = (body.get("falsifier") or "").strip() or None
            from mentis.conversation import placements_now
            placed_at = list(dict.fromkeys(
                w for p in predecessors for w in placements_now(corpus, p)))
            writer = _observed_writer(st, presented)
            from mentis.conversation import ladder_writes as _ladder
            try:
                refs, pairs = _ladder.version_grounds(
                    corpus, kind, fields, eid, body.get("basis"))
            except ValueError as exc:
                return {"error": str(exc), "entry": eid, "act": act}
            try:
                with corpus.atomic():
                    new = corpus.create_and_establish(
                        kind=kind, body=fields, attributed_to=by,
                        written_by=writer)
                    _ladder.write_grounds(corpus, new, refs, pairs, by=by,
                                          writer=writer)
                    for where in placed_at:
                        corpus.write(
                            body={"reason": "inherited from the material "
                                            "this revises"},
                            attributed_to=by, written_by=writer,
                            link={"from": new, "to": where,
                                  "relation": "scoped-to"})
                    for pred in predecessors:
                        refusal = _supersession_refusal(corpus, pred, new)
                        if refusal is not None:
                            raise _Refused({**refusal, "kind": kind,
                                            "predecessors": predecessors})
                    links = {}
                    for pred in predecessors:
                        links[pred] = corpus.write(
                            body={"reason": because
                                  or "revised and established"},
                            attributed_to=by, written_by=writer,
                            link={"from": new, "to": pred,
                                  "relation": "supersedes"})
                        cv.carry_intake_forward(pred, new, by=by,
                                                written_by=writer)
                    oid = cv.record_act(
                        actor=by, act="material-revised",
                        about=[*predecessors, new],
                        because=because or None,
                        detail={"revision": new, "link": links[eid],
                                "links": links,
                                "predecessors": predecessors,
                                "placed_at": placed_at,
                                # BESIDE THE REASON, as on the establish door.
                                **({"falsifier": falsifier}
                                   if falsifier else {})})
                    answered = {"answers": [], "answers_a_request": False}
                    for pred in predecessors:
                        answered["answers"] += _answered_asks(
                            cv, pred, by=by, act="revised")["answers"]
            except _Refused as refused:
                # Nothing was written: the transaction rolled back, and the
                # refusal says which predecessor it is about.
                return refused.refusal
            except ValueError as exc:
                # The Kind's own refusal about its fields, in its own words.
                return {"error": str(exc), "entry": eid, "kind": kind}
            answered["answers_a_request"] = bool(answered["answers"])
            if answered["answers_a_request"]:
                answered["say"] = "The request to you is answered."
            standing = corpus.stands(eid)
            return {"entry": eid, "revision": new, "kind": kind,
                    "link": links[eid], "act": oid, "placed_at": placed_at,
                    "predecessors": predecessors,
                    "links": links,
                    "standing": standing,
                    "state": standing_state(standing),
                    "replaced": {p: corpus.stands(p) for p in predecessors},
                    "revision_standing": corpus.stands(new),
                    "kept": "every proposal it replaced is unchanged and still "
                            "readable; one that was never established never "
                            "held",
                    **answered}

        if act == "derive-from":
            """Record what this was concluded FROM. Changes no standing.

            A DOOR FOR A RELATION THAT ALREADY EXISTED. `derived-from` is a
            seeded relation, declared inert to the engine and meaning
            "concluded from another held object" -- and nothing could write one
            from normal work, so the one fact that makes a conclusion arguable
            was reachable only by a script. Nothing is redeclared here and no
            relation is invented: this is the production door onto the
            vocabulary the seed already carries.

            AND IT WORKS ON MATERIAL THAT DOES NOT STAND, deliberately. A draft
            cites its basis BEFORE anybody establishes it -- that is what makes
            it possible to argue with the draft at all -- so requiring standing
            here would mean the basis could only be recorded after the argument
            it was needed for. Standing is a separate question and this act
            does not touch it: the entry stood or did not before, and does
            after.

            SEVERAL SOURCES, ONE ACT. `from` takes an id or a list of them,
            because material concluded from three observations was concluded
            from three observations, and recording that as three acts would
            lose that they were one derivation.
            """
            said, unreasoned = _stated_reason(body, act)
            if unreasoned:
                return unreasoned
            sources = body.get("from") or []
            if isinstance(sources, str):
                sources = [sources]
            if not isinstance(sources, list) or not sources:
                return {"error": "a derivation names what it was derived "
                                 "from: an entry id, or a list of them, in "
                                 "`from`",
                        "entry": eid, "needs": "from"}
            # Each named end is asked of the record BEFORE anything is written.
            # A `derived-from` link to an id this record does not hold would be
            # a citation of nothing, typographically identical to a real one.
            sources = list(dict.fromkeys(sources))
            unheld = [x for x in sources if not corpus.read([x])]
            if unheld:
                return {"error": "the record holds no such entry, so nothing "
                                 "can be derived from it",
                        "entry": eid, "from": unheld[0]}
            if eid in sources:
                return {"error": "nothing is derived from itself",
                        "entry": eid, "from": eid}
            from mentis.conversation.ladder_writes import cycle_refusal
            try:
                for src in sources:
                    cycle_refusal(corpus, eid, src)
            except ValueError as exc:
                return {"error": str(exc), "entry": eid}
            links = {}
            with corpus.atomic():
                for src in sources:
                    links[src] = corpus.write(
                        body={"reason": said},
                        attributed_to=by,
                        written_by=_observed_writer(st, presented),
                        link={"from": eid, "to": src,
                              "relation": "derived-from"})
                oid = cv.record_act(actor=by, act="material-derived",
                                    about=[eid, *sources], because=said,
                                    detail={"derived": eid,
                                            "from": sources,
                                            "links": links})
            return {"entry": eid, "from": sources, "links": links,
                    "act": oid, "standing": corpus.stands(eid),
                    "changes": "nothing about standing. What stood before "
                               "stands now; what was a candidate is still a "
                               "candidate, and now says what it was concluded "
                               "from."}

        if act == "place":
            """Record that this material applies THERE. Placement, nothing else.

            WHY THIS DOOR HAD TO EXIST FOR ANY OF THIS TO BE A PRODUCTION PATH.
            Placement is the `scoped-to` link, and every writer of one named
            `conversation-instruction` as it created it -- so an owner could
            place an instruction and could NOT place a `rule`, even after
            delivery had stopped asking which Kind it was. The demonstration
            that a placed rule governs work was reaching into the spine to write
            the link by hand, which is not a path anybody has.

            THE TARGET IS AN ID, NOT A CONVERSATION. `scoped-to` means "applies
            there"; nothing in that meaning restricts what "there" is, and
            writing this door against one endpoint type would be the narrow
            mistake again. It is checked for existence and nothing else.

            PLACING IS NOT ESTABLISHING. Material that does not stand may be
            placed -- it governs nothing until it stands, and `governs()`
            reports it as a candidate -- so this confers nothing on its own.
            """
            said, unreasoned = _stated_reason(body, act)
            if unreasoned:
                return unreasoned
            # THE WHOLE BRAIN IS CHOSEN, NEVER DEFAULTED. `whole_brain: true`
            # is the one way to ask for it, and it resolves to the deliberate
            # destination entry (`Conversations.whole_brain`), written the
            # first time anybody places something there. A missing `where` is
            # still refused below: absence never means everywhere.
            brain_wide = body.get("whole_brain") is True
            where = body.get("where")
            if brain_wide and where:
                return {"error": "a placement names one destination: a "
                                 "`where`, or `whole_brain`, not both",
                        "entry": eid}
            if not brain_wide and (not isinstance(where, str)
                                   or not where.strip()):
                return {"error": "a placement names where it applies, in "
                                 "`where`, or `whole_brain: true` for every "
                                 "Conversation and Brain-scope work",
                        "entry": eid, "needs": "where"}
            if not brain_wide:
                where = where.strip()
                if not corpus.read([where]):
                    return {"error": "the record holds no such entry, so "
                                     "nothing can be placed at it",
                            "entry": eid, "where": where}
                brain_wide = cv.is_whole_brain(where)
            # WHAT THE KIND DECLARES ABOUT WHERE IT MAY BE PLACED is enforced
            # here, not only reflected in what the builder offers.
            from mentis.conversation import declared_placement_refusal
            refusal = declared_placement_refusal(
                corpus, eid, None if body.get("whole_brain") is True else where)
            if refusal:
                return refusal
            if brain_wide:
                refusal = _whole_brain_refusal(corpus, eid)
                if refusal:
                    return refusal
            writer = _observed_writer(st, presented)
            return cv.place(eid, where=None if body.get("whole_brain") is True
                            else where,
                            whole_brain=body.get("whole_brain") is True,
                            by=by, because=said, written_by=writer)

        if act == "unplace":
            """End a placement: the normal append-only removal.

            `where` names the Conversation, or `whole_brain: true` the whole
            Brain. Every placement of this material there that nothing has
            ended is ended by a deletion record superseding its link -- the
            way a filing or a link is ended -- and a `placement-ended` act says
            who did it and why. Nothing is erased; the material, its standing
            and its other placements are untouched. Moving a placement is this
            and then `place`, two acts with their own reasons.
            """
            said, unreasoned = _stated_reason(body, act)
            if unreasoned:
                return unreasoned
            if body.get("whole_brain") is True:
                where = cv.whole_brain()
            else:
                where = body.get("where")
                where = where.strip() if isinstance(where, str) else None
                if not where:
                    return {"error": "name the placement to end, in `where`, "
                                     "or `whole_brain: true`",
                            "entry": eid, "needs": "where"}
            ended = (cv.end_placement(eid, where, by=by, because=said,
                                      written_by=_observed_writer(
                                          st, presented))
                     if where else None)
            if ended is None:
                return {"error": "this material is not placed there now, so "
                                 "there is no placement to end",
                        "entry": eid, "where": where}
            return {**ended, "whole_brain": cv.is_whole_brain(where),
                    "standing": corpus.stands(eid)}

        if act == "support":
            """Record that this supports that. Changes no standing.

            THE SAME DOOR FOR THE OTHER SEEDED RELATION. `supports` already
            existed and already meant this; what was missing was a way to write
            one that was not a set-aside.

            AND IT IS NOT A SET-ASIDE, WHICH IS THE ONE THING THIS MUST NOT BE
            MISTAKEN FOR. `governance.disputes_of` recognises a set-aside by a
            `sets_aside` key in a `supports` link's body, so this writes NO SUCH
            KEY -- a plain support has answered no challenge, and a support that
            silently closed one would report a dispute as resolved that nobody
            resolved. Setting a dispute aside is `set-aside`, it names the
            dispute it answers, and it is a different act.

            ON MATERIAL THAT DOES NOT STAND, for the reason `derive-from` is:
            argument comes before adjudication, not after it.
            """
            said, unreasoned = _stated_reason(body, act)
            if unreasoned:
                return unreasoned
            supported = body.get("supports")
            if not isinstance(supported, str) or not supported.strip():
                return {"error": "a support names what it supports, in "
                                 "`supports`",
                        "entry": eid, "needs": "supports"}
            supported = supported.strip()
            if not corpus.read([supported]):
                return {"error": "the record holds no such entry, so nothing "
                                 "can be supported",
                        "entry": eid, "supports": supported}
            if supported == eid:
                return {"error": "nothing supports itself",
                        "entry": eid, "supports": eid}
            with corpus.atomic():
                # NO `sets_aside` KEY. See the docstring: that key is how
                # `disputes_of` recognises an answered challenge, and a plain
                # support has answered none.
                link = corpus.write(
                    body={"reason": said},
                    attributed_to=by,
                    written_by=_observed_writer(st, presented),
                    link={"from": eid, "to": supported,
                          "relation": "supports"})
                oid = cv.record_act(actor=by, act="material-supported",
                                    about=[eid, supported], because=said,
                                    detail={"supporter": eid,
                                            "supported": supported,
                                            "link": link})
            from mentis.conversation.governance import disputes_of
            return {"entry": eid, "supports": supported, "link": link,
                    "act": oid, "standing": corpus.stands(supported),
                    "sets_aside": None,
                    "disputes": disputes_of(corpus, supported),
                    "changes": "nothing about standing, and no dispute. A "
                               "support is an argument, not an adjudication of "
                               "one."}

        if act == "draw-on":
            """Record that this material draws on that entry or held artifact,
            as an example, a reference or a check. Changes no standing.

            THE `support` DOOR'S SHAPE, ONE RELATION OVER: a reason, a target
            the record holds and that was not deleted, and one act beside the
            link. What it adds is the ROLE the target plays and a short LABEL,
            on the link, because delivery lists the target by them instead of
            copying its contents (`Conversations.drawn_on`). A target may be
            an entry or a held artifact (`adm-...`), which a run reads with
            `read_artifact` when the material is delivered to it.

            ON MATERIAL THAT DOES NOT STAND TOO, as `support` is: a Discipline
            is assembled before it is established.
            """
            said, unreasoned = _stated_reason(body, act)
            if unreasoned:
                return unreasoned
            target = body.get("draws_on")
            if not isinstance(target, str) or not target.strip():
                return {"error": "a `draw-on` names what it draws on, in "
                                 "`draws_on`",
                        "entry": eid, "needs": "draws_on"}
            target = target.strip()
            if not corpus.read([target]):
                return {"error": "the record holds no such entry or artifact, "
                                 "so nothing can be drawn on",
                        "entry": eid, "draws_on": target}
            if target == eid:
                return {"error": "nothing draws on itself",
                        "entry": eid, "draws_on": eid}
            link_body, refusal = _draws_on_body(body)
            if refusal:
                return {**refusal, "entry": eid}
            refusal = _draws_on_source_refusal(corpus, _kind_name(corpus, eid))
            if refusal:
                return {**refusal, "entry": eid}
            with corpus.atomic():
                link = corpus.write(
                    body={**link_body, "reason": said},
                    attributed_to=by,
                    written_by=_observed_writer(st, presented),
                    link={"from": eid, "to": target, "relation": "draws-on"})
                oid = cv.record_act(actor=by, act="material-drawn-on",
                                    about=[eid, target], because=said,
                                    detail={"entry": eid, "draws_on": target,
                                            "role": link_body["role"],
                                            "label": link_body["label"],
                                            "link": link})
            return {"entry": eid, "draws_on": target, "link": link,
                    "act": oid, **link_body,
                    "standing": corpus.stands(eid),
                    "changes": "nothing about standing. The target is listed "
                               "by reference where this material is "
                               "delivered, and read only on demand."}

        return {"error": f"no such act {act!r}",
                "acts": ["establish", "supersede", "dispute", "set-aside",
                         "withdraw-challenge", "request-adoption", "adopt",
                         "decline", "revise", "propose-supersession",
                         "establish-replacement", "derive-from", "support",
                         "draw-on", "place", "unplace",
                         "edit", "delete"]}

    if (path.startswith("/api/entries/") and path.endswith("/activities")
            and method == "GET"):
        """WHAT NAMING THIS MATERIAL FOR A REQUEST WOULD SET GOING, READ.

        For material whose Kind's `form` declares an `activities` input (a
        Workflow): its activities with each one's carrier and Disciplines BY
        NAME AND REFERENCE, the decisions reserved to the owner, its default
        carrier and Persona, and what it and its activities' Disciplines
        require of a runtime (`dispatch.requirements_of`, the union selection
        will apply). The Composer's "Use…" says this before anything is sent.
        A read: nothing is written, granted or scheduled.
        """
        from mentis.conversation import (
            PARTICIPANT_INPUT, PERSONA_INPUT, ROW_GROUP, activities_of,
            capability_fields, current_of, fields_with_input)
        from mentis.web.dispatch import requirements_of
        eid = path[len("/api/entries/"):-len("/activities")]
        got = corpus.read([eid])
        if not got:
            return {"entry": eid, "missing": True}
        e = got[0]
        kind = (e.get("definition") or {}).get("name")
        if not fields_with_input(corpus, kind, ROW_GROUP):
            return {"entry": eid, "kind": kind, "activities": None,
                    "why": "this Kind declares no activities"}
        body = e.get("body") or {}

        def named(ref):
            r = corpus.read([ref]) if isinstance(ref, str) and ref else []
            if not r:
                return {"entry": ref, "name": None, "held": False,
                        "stands": False}
            if (r[0].get("definition") or {}).get("name") == "participant":
                # Its CURRENT alias, and whether THAT version stands: a
                # renamed Participant's root is superseded by its new alias,
                # which is a name changing, not somebody ceasing to be.
                from mentis.conversation.versions import presented as _now
                now = _now(corpus, r[0])
                head = (now.get("revision") or {}).get("current") or ref
                return {"entry": ref, "name": now["body"].get("alias"),
                        "held": True, "stands": corpus.stands(head)["stands"]}
            b = r[0].get("body") or {}
            return {"entry": ref, "name": b.get("alias") or b.get("name"),
                    "held": True, "stands": corpus.stands(ref)["stands"]}

        def discipline(ref):
            # THE VERSION THAT WOULD REACH A CHILD NOW (`current_of`), with
            # what the procedure pins and why it does not stand, if it does not.
            cur = current_of(corpus, ref)
            now = corpus.read([cur["entry"]]) if cur["entry"] else []
            dkind = (now[0].get("definition") or {}).get("name") if now else None
            # WHAT IT WOULD REQUIRE, said even when it does not stand, so a
            # requirement that is not counted is not silently dropped.
            needs = sorted({c for f in capability_fields(corpus, dkind)
                            for c in ((now[0].get("body") or {}).get(f) or ())
                            if isinstance(c, str)}) if now else []
            return {**named(cur["entry"] or ref), "pinned": ref,
                    "stands": cur["stands"], "why": cur["why"],
                    "requires": needs,
                    **({"entry": cur["entry"]} if cur["entry"] else {})}

        def first(input_):
            names = fields_with_input(corpus, kind, input_)
            value = body.get(names[0]) if names else None
            return named(value) if value else None

        carrier, persona = first(PARTICIPANT_INPUT), first(PERSONA_INPUT)
        rows = []
        for row in activities_of(corpus, e):
            who = row.get("who") or {}
            rows.append({
                "key": row["key"], "what": row.get("what") or "",
                "who": {"role": who.get("role") or "",
                        "persona": named(who["persona"]) if who.get("persona") else None,
                        "participant": named(who["participant"])
                        if who.get("participant") else None},
                "disciplines": [discipline(d) for d in row.get("disciplines") or ()],
                "done_when": row.get("done_when") or "",
                "coordinates": bool(row.get("coordinates"))})
        return {"entry": eid, "kind": kind, "name": body.get("name") or "",
                "about": body.get("about") or "",
                "stands": corpus.stands(eid)["stands"],
                "carrier": carrier, "persona": persona,
                "activities": rows,
                "decisions": [x for x in body.get("decisions") or ()
                              if isinstance(x, str)],
                "done_when": body.get("done_when") or "",
                "requires": requirements_of(cv, [eid]),
                "coordinates": any(r["coordinates"] for r in rows),
                "note": "read from the record; naming this for a request "
                        "grants nothing and starts nothing by itself"}

    if path.startswith("/api/entries/"):
        eid = path[len("/api/entries/"):]
        got = corpus.read([eid])
        if not got:
            return {"id": eid, "missing": True}
        e = got[0]
        standing = corpus.stands(eid)
        definition = corpus.definition_for(e)
        # TWO DIFFERENT QUESTIONS, TWO DIFFERENT SOURCES, AND NEITHER STANDS IN
        # FOR THE OTHER.
        #
        # `definition_for` above is the version this entry was WRITTEN AGAINST,
        # and everything drawn from it -- fields, meaning, properties -- says
        # what the entry meant, because a later version never reinterprets it.
        #
        # `standing_apt` is not that sort of fact. It says whether the Kind's
        # instances participate in standing AT ALL, which is a fact about the
        # vocabulary now, so it is read from the CURRENT definition. One source,
        # no fallback to a pinned value: an entry written under v1 of its Kind
        # reports the capability v2 declares, while its own fields and meaning
        # stay pinned to v1. Absent means UNKNOWN and is never turned into False.
        current_kind = (corpus.current_definition(e.get("definition", {}).get("name"))
                        if (e.get("definition") or {}).get("name") else None)
        standing_apt = (current_kind or {}).get("body", {}).get("standing_apt")
        from mentis.conversation.governance import proposed_supersessions
        from mentis.operational.products import describe_entry, provenance_of
        props = dict((definition or {}).get("body", {}))
        fields = props.pop("fields", None)
        for k in ("kind", "relation", "inverse", "directed", "substrate_role"):
            props.pop(k, None)
        seen = describe_entry(corpus, eid) or {}
        from mentis.conversation import versions as _versions
        _versions_view = (_versions.history_view(corpus, eid, alias=cv.alias)
                          if _versions.is_node(e) else
                          {"entry": eid, "versions": [], "current": None,
                           "deleted": None})
        _is_deletion = _versions.is_deletion(e)
        from mentis.web.governance_ui import actions as governance_actions
        return {"id": eid, "kind": (e.get("definition") or {}).get("name"),
                "version": (e.get("definition") or {}).get("version"),
                "family": e.get("family"),
                "body": e["body"], "attributed_to": e["attributed_to"],
                "author_alias": cv.alias(e["attributed_to"]),
                # THREE DIFFERENT FACTS, kept apart because they answer
                # different questions: who it is attributed to, what wrote it
                # down, and where the material came from. A reader must be
                # able to tell "Vera says this" from "a claude runtime typed
                # it" from "it came out of the lab".
                "written_by": e["written_by"],
                "origin": e.get("origin"),
                "at": e["recorded_at"],
                "stands": standing["stands"],
                # WHAT THE KIND CAN DO NOW, said as coming from where it does.
                "standing_apt": standing_apt,
                "standing_apt_from": "current-kind-definition",
                "standing_apt_kind_version": (
                    (current_kind or {}).get("definition", {}).get("version")),
                "established_by": standing["established_by"],
                "superseded_by": standing["superseded_by"],
                "incoming": standing["incoming"],
                # TWO FACTS, NEVER ONE. `superseded_by` is what ended it;
                # `proposed` is what is merely put forward -- for it, and by
                # it -- and has ended nothing. A reader distinguishes them
                # here rather than by guessing from a single list. null means
                # this record declares no such relation, which is not "none".
                "proposed": proposed_supersessions(corpus, eid),
                # ITS VERSIONS, AND WHETHER ITS LINE WAS DELETED. Read forward
                # from this entry; `deleted` is null unless a deletion ends it.
                "versions": _versions_view,
                "deleted": _versions.presented(corpus, e).get("deleted"),
                "is_deletion": _is_deletion,
                # WHAT MAY BE OFFERED HERE, by the rules the acts apply.
                "may": _versions.offers(corpus, e),
                "governance_actions": governance_actions(corpus, e),
                "fields": seen.get("fields") or (list(fields) if fields else []),
                "properties": props,
                "meaning": (definition or {}).get("body", {}).get("meaning"),
                "provenance": provenance_of(brain, eid)}

    if path == "/api/presentation" or path.startswith("/api/presentation/"):
        return _presentation_route(st, path, body, method)

    if path == "/api/space":
        """THE WHOLE BRAIN, AS SOMETHING THAT CAN BE DRAWN IN SPACE. A read.

        Every durable Entry with the height its Kind declares, the
        Conversation the record puts it in, and the links between them; see
        `mentis.operational.space`. Admissions only when `material=1`.
        """
        from mentis.operational.space import space
        return space(brain, material=one("material") == "1",
                     cap=int(one("cap", 6000)))

    if path == "/api/space/said":
        """WHAT ONE CHOSEN THING SAYS, a little more than its one line. A read;
        see `mentis.operational.space.said_of`."""
        from mentis.operational.space import said_of
        return said_of(brain, one("entry"))

    if path == "/api/neighborhood":
        from mentis.operational.neighborhood import closure, neighborhood
        if one("closure") == "1":
            return closure(brain, one("entry"), cap=int(one("cap", 60)))
        return neighborhood(brain, one("entry"),
                            limit=int(one("limit", 40)))

    return None


def _presentation_route(st, path, body, method):
    """HOW THE CANVAS LOOKS, kept beside the record (mentis/presentation.py).

    Reads and writes `<corpus>/presentation/` and nothing else: no Entry, no act, no
    Admission is written by any of these, and nothing that forms context, retrieves,
    delivers or governs reads what they keep. A worker grant is refused on them by `_api`,
    like every route that does not name one; the picture routes refuse it themselves.
    """
    root = st.corpus.root
    body = body or {}
    if path == "/api/presentation" and method == "GET":
        return _presentation.read(root)
    if path == "/api/presentation/looks" and method == "POST":
        look, data = _presentation.add_look(
            root, name=body.get("name"), theme=body.get("theme"),
            pictures=body.get("pictures"))
        return {"look": look, "presentation": data}
    if path.startswith("/api/presentation/looks/") and method == "POST":
        look = path[len("/api/presentation/looks/"):]
        return {"presentation": _presentation.change_look(
            root, look, name=body.get("name"), remove=bool(body.get("remove")))}
    if path == "/api/presentation/choice" and method == "POST":
        return {"presentation": _presentation.choose(
            root, conversation=body.get("conversation"), look=body.get("look"))}
    # WORKING SCENES (mentis/working_scenes.py): the figures above the composer. Data
    # only, checked on the way in and on every read; same place, same refusals.
    if path == "/api/presentation/scenes" and method == "GET":
        return _working_scenes.library(root)
    if path == "/api/presentation/scenes" and method == "POST":
        return _working_scenes.add(root, body)
    if path.startswith("/api/presentation/scenes/") and method == "POST":
        return _working_scenes.change(
            root, path[len("/api/presentation/scenes/"):],
            on=body.get("on") if isinstance(body.get("on"), bool) else None,
            remove=bool(body.get("remove")))
    return None


def _is_presentation_picture(path: str) -> bool:
    """`/api/presentation/pictures` (upload) and `/…/<sha>` (serving)."""
    return (path == "/api/presentation/pictures"
            or path.startswith("/api/presentation/pictures/"))


def _is_artifact_route(path: str) -> bool:
    """`/api/artifacts` (staging) and `/api/artifacts/<ref>` (serving)."""
    return path == "/api/artifacts" or path.startswith("/api/artifacts/")


class _Handler(BaseHTTPRequestHandler):
    state: _State = None
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send_response(self, code, message=None):
        """EVERY ANSWER GIVEN WITHOUT READING THE WHOLE BODY ENDS THE CONNECTION.

        This server keeps HTTP/1.1 connections alive, and several refusals
        answer before reading the body (a foreign Host, a missing upload
        header, an oversize upload). Left on the connection, those bytes were
        read as the NEXT request -- a page could put a complete request, with
        any headers it liked, inside a text/plain body and have it executed
        behind a refusal (review F1, measured). So any error closes the
        connection, as does any answer to a request whose body this handler
        does not consume: a GET or OPTIONS that declares one, or any request
        framed by Transfer-Encoding, which nothing here decodes."""
        closing = code >= 400 or self._unconsumed_body()
        if closing:
            self._discard_small_body()
        super().send_response(code, message)
        if closing:
            self.send_header("Connection", "close")
            self.close_connection = True

    def _unconsumed_body(self) -> bool:
        headers = getattr(self, "headers", None)
        if headers is None or not self._framing_ok:
            return True
        if headers.get("Transfer-Encoding"):
            return True
        if self.command in ("POST",):
            return False
        return (headers.get("Content-Length") or "0") != "0"

    #: How much of an unread body is read and thrown away before a refusal.
    DISCARD_MAX = 64 * 1024

    def handle_one_request(self):
        # PER REQUEST, NEVER CARRIED OVER: a refusal sent before the request
        # line or headers are parsed must not act on the previous request's.
        self._framing_ok = False
        self._body_read = False
        self._counted = False
        try:
            super().handle_one_request()
        finally:
            # DRAINING (`_Server`): a request is in flight from its parsed
            # request line until its answer is written.
            if self._counted:
                self.server.leave()

    def parse_request(self):
        """ONE UNAMBIGUOUS FRAMING, or a 400 (re-review R1).

        Python's header parser keeps a name with whitespace in it as a
        different name (`Transfer-Encoding : chunked` is not
        Transfer-Encoding to `headers.get`), takes the first of several
        Content-Lengths, and `int()` accepts `+5` and ` 5 `. Any of those lets
        this server and something in front of it read one request two ways,
        so each is refused."""
        if not super().parse_request():
            return False
        import re
        # A line that is not `Name: value` -- e.g. `Transfer-Encoding : chunked`
        # -- is not kept as a header at all: the parser records a defect and
        # takes it and EVERY LINE AFTER IT as a payload, silently dropping the
        # headers that followed. Any defect or leftover is refused.
        ctype = (self.headers.get("Content-Type") or "").lower()
        defects = getattr(self.headers, "defects", None) or []
        if ctype.startswith("multipart/"):
            defects = [d for d in defects if d.__class__.__name__ not in ("StartBoundaryNotFoundDefect", "MultipartInvariantViolationDefect")]
        if (defects
                or (self.headers.get_payload() or "").strip()
                or any(re.search(r"\s", name) for name in self.headers.keys())):
            self.send_error(400, "a header line is not `Name: value`")
            return False
        lengths = self.headers.get_all("Content-Length") or []
        if len(lengths) > 1:
            self.send_error(400, "more than one Content-Length")
            return False
        if lengths and not re.fullmatch(r"[0-9]+", lengths[0]):
            self.send_error(400, "Content-Length must be digits only")
            return False
        self._framing_ok = True
        # A STOPPING SERVER TAKES NO NEW REQUEST, even on a connection kept
        # alive from before: 503, and the connection closes.
        enter = getattr(self.server, "enter", None)
        if enter is not None:
            if not enter():
                self.send_error(503, "this server is stopping")
                return False
            self._counted = True
        return True

    def _read_body(self, length: int) -> bytes:
        data = self.rfile.read(length) if length > 0 else b""
        self._body_read = True
        return data

    def _discard_small_body(self):
        """READ AND DROP A SMALL UNREAD BODY BEFORE A REFUSAL.

        On Windows, closing a socket with unread bytes in it sends RST, and the
        client can lose the refusal it was just sent (seen once:
        ConnectionAbortedError in test_upload_refusals). So a body of at most
        DISCARD_MAX, declared by a well-formed Content-Length, is read -- with
        a short timeout -- and thrown away. It is never parsed: the connection
        still closes. A larger or unframed body is not read; it closes as
        before, and an RST there is the lesser cost."""
        if self._body_read or not self._framing_ok:
            return
        self._body_read = True
        if self.headers.get("Transfer-Encoding"):
            return
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= self.DISCARD_MAX:
            return
        try:
            self.connection.settimeout(2.0)
            self.rfile.read(length)
        except OSError:
            pass

    def _send(self, code, payload=None, raw=None, ctype="application/json"):
        data = raw if raw is not None else json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # NO Access-Control-Allow-Origin: the interface is served by this
        # server, so it is same-origin and needs none. See CLIENT_HEADER.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _refused_host(self) -> bool:
        """Answer 421 for a Host a rebound DNS name could carry. True if sent."""
        if _host_allowed(self.headers.get("Host")):
            return False
        self._send(421, {"error": f"Host {self.headers.get('Host')!r} is not "
                                  "one this server answers; list it in "
                                  "MENTIS_ALLOWED_HOSTS to allow it",
                         "kind": "PermissionError"})
        return True

    def _missing_client(self, path, method) -> bool:
        """Refuse an owner JSON request without CLIENT_HEADER. True if sent.

        A request presenting a worker grant is left to `_api`, unchanged: it
        already carries a header no cross-origin page can send unpreflighted."""
        from mentis.worker import CAPABILITY_HEADER
        if self.headers.get(CAPABILITY_HEADER):
            return False
        if method == "GET" and path in CLIENT_EXEMPT_GET:
            return False
        if self.headers.get(CLIENT_HEADER) == "1":
            return False
        self._send(403, {"error": f"missing {CLIENT_HEADER}",
                         "kind": "PermissionError"})
        return True

    def do_OPTIONS(self):
        # A PREFLIGHT GRANTS NOTHING: no ACAO, no allowed headers, so a page on
        # another origin cannot send CLIENT_HEADER or a JSON body.
        path = urllib.parse.urlparse(self.path).path
        if _is_artifact_route(path) or _is_presentation_picture(path):
            return self._artifact_send(204, raw=b"")
        self._send(204, raw=b"")

    def do_GET(self):
        if self._refused_host():
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/artifacts/"):
            return self._artifact(
                parsed.path[len("/api/artifacts/"):],
                describe="describe=1" in (parsed.query or "").split("&"))
        if parsed.path.startswith("/api/presentation/pictures/"):
            return self._look_picture(
                parsed.path[len("/api/presentation/pictures/"):])
        # FLUID WORKSPACE (mentis/fluid): its own read-only API, handed off
        # here after the same Host and client checks, before `_api`.
        if parsed.path.startswith("/fluid/api/"):
            if self._missing_client(parsed.path, "GET"):
                return
            from mentis.fluid import handle_get as _fluid_get
            return _fluid_get(self, parsed)
        if parsed.path.startswith("/api/"):
            import re
            m_conv = re.match(r"^/api/conversations/([^/]+)/export$", parsed.path)
            if m_conv:
                return self._export("conversation", urllib.parse.unquote(m_conv.group(1)))
            m_turn = re.match(r"^/api/turns/([^/]+)/export$", parsed.path)
            if m_turn:
                return self._export("turn", urllib.parse.unquote(m_turn.group(1)))
            if self._missing_client(parsed.path, "GET"):
                return
            return self._api(parsed, None, "GET")
        return self._static(parsed.path)

    def _static(self, path):
        """FLUID, the interface, from its build (`apps/fluid-web/dist`).

        Still headless without it: with nothing built, every API answers and
        a page says the interface is not built. One page: an address that is
        not a built file is Fluid's own (`/`, `/fluid?c=...`)."""
        from mentis.conversation.render_check import DIST
        root = DIST.resolve()
        if not (root / "index.html").is_file():
            return self._send(404, {"error": "this Mentis serves its API only "
                                             "(/api/...): Fluid is not built "
                                             "(apps/fluid-web: npm run build)",
                                    "kind": "NotFound"})
        target = (root / urllib.parse.unquote(path).lstrip("/")).resolve()
        if root not in target.parents or not target.is_file()                 or target.name == "render-check.js":
            target = root / "index.html"
        import mimetypes
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return self._send(200, raw=target.read_bytes(), ctype=ctype)

    def do_POST(self):
        if self._refused_host():
            return
        # ONE FRAMING ONLY: a body is its Content-Length. Nothing here decodes
        # chunked bodies, so a request framed any other way is refused (and,
        # like every refusal, closes the connection -- see send_response).
        if self.headers.get("Transfer-Encoding"):
            return self._send(501, {"error": "Transfer-Encoding is not "
                                             "accepted; send a Content-Length"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._send(400, {"error": "Content-Length is not a number"})
        if length < 0:
            return self._send(400, {"error": "a negative Content-Length"})
        parsed = urllib.parse.urlparse(self.path)
        # FLUID (mentis/fluid/commands.py): its own command door, through the
        # same write operations as the routes below; 405 for any other path.
        if parsed.path.startswith("/fluid/api/"):
            from mentis.fluid.commands import handle_post as _fluid_post
            return _fluid_post(self, parsed, length)
        if parsed.path == "/api/artifacts":
            return self._stage()
        if parsed.path == "/api/presentation/pictures":
            return self._look_upload()
        if parsed.path.startswith("/api/exchange/import/"):
            return self._exchange_import(parsed, length)
        raw = self._read_body(length)
        if self._missing_client(parsed.path, "POST"):
            return
        # A LOOK IS CHANGED ONLY BY THIS INTERFACE (kept as it was; CLIENT_HEADER
        # now covers every JSON route, this one included).
        if parsed.path.startswith("/api/presentation") and \
                self.headers.get("X-Mentis-Presentation") != "1":
            return self._send(400, {"error": "missing X-Mentis-Presentation"})
        # A JSON BODY IS JSON BY ITS DECLARED TYPE. text/plain used to be parsed
        # too, which is what let a simple (unpreflighted) request write.
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if raw and ctype.lower() != "application/json":
            return self._send(415, {"error": "a JSON route takes "
                                             "Content-Type: application/json",
                                    "kind": "PermissionError"})
        body = json.loads(raw or b"{}")
        return self._api(parsed, body, "POST")

    # -- artifacts: two routes with their own protections --------------------
    #
    # NOT GATED ON THE BROADER WEB-BOUNDARY REPAIR (ent-7164ce53d6d1, answered:
    # don't gate), and deliberately STRICTER than the JSON routes, which still
    # answer any origin -- that is recorded work of its own. What these two
    # keep, as the measured artifact prototypes established them:
    #
    #   upload  needs `X-Mentis-Upload: 1`, a non-safelisted header, so a
    #           cross-origin page cannot send it without a preflight, and the
    #           preflight here allows only Content-Type. Refuses a worker grant.
    #           A declared, exact Content-Length within the cap, or nothing.
    #   serve   NO Access-Control-Allow-Origin. nosniff; a sandbox CSP with no
    #           script; CORP same-origin; no referrer. Text -- HTML included --
    #           is served as text/plain; an image or PDF only by its own
    #           signature. Only verified bytes are ever sent.
    #
    # EVERY ANSWER on these routes -- refusals, staging, `?describe=1`, the
    # preflight -- carries the serving protections, not only the bytes: a
    # description names a file, its digest and size, and is no more for any
    # origin to read than the file is.

    def _artifact_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "sandbox; default-src 'none'; img-src data:; "
                         "style-src 'unsafe-inline'")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Referrer-Policy", "no-referrer")

    def _artifact_send(self, code, payload=None, raw=None):
        """`_send` for the artifact routes: JSON, never cached, no ACAO."""
        data = raw if raw is not None else json.dumps(payload,
                                                      default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._artifact_headers()
        self.end_headers()
        self.wfile.write(data)

    def _stage(self):
        from mentis.worker import CAPABILITY_HEADER
        send = self._artifact_send
        if self.headers.get(CAPABILITY_HEADER):
            return send(403, {"error": "a worker returns bytes through "
                                       "return_artifact, not here"})
        if self.headers.get("X-Mentis-Upload") != "1":
            return send(400, {"error": "missing X-Mentis-Upload"})
        raw = self.headers.get("Content-Length")
        if raw is None:
            return send(411, {"error": "a Content-Length is required"})
        try:
            length = int(raw)
        except ValueError:
            return send(400, {"error": f"Content-Length {raw!r} is not "
                                       "a number"})
        if length < 0:
            return send(400, {"error": "a negative Content-Length"})
        if length > _artifacts.MAX_BYTES:
            return send(413, {"error": f"{length} bytes is over the "
                                       f"{_artifacts.MAX_BYTES} cap"})
        data = self._read_body(length)
        if len(data) != length:
            return send(400, {"error": f"declared {length} bytes, "
                                       f"received {len(data)}"})
        try:
            out = _artifacts.stage(self.state.corpus.root, data,
                                   self.headers.get("Content-Type"))
        except Exception as exc:                          # noqa: BLE001
            return send(400, {"error": str(exc)})
        return send(200, out)

    def _artifact(self, ref, *, describe=False):
        """The bytes behind a held Admission, or why not, as its own answer:

          404 unknown / 409 not-an-artifact, not-held / 410 purged
          500 held-but-missing, held-but-corrupt / 200 the VERIFIED bytes

        `?describe=1` answers what stands behind the ref -- verified, without
        the bytes -- so the Composer can reference something already held
        without re-sending it, and refuse one that is no longer there.
        """
        from mentis.worker import CAPABILITY_HEADER
        if self.headers.get(CAPABILITY_HEADER):
            return self._artifact_send(
                403, {"error": "a worker grant authorises /api/worker and "
                               "nothing else"})
        if describe:
            d = _artifacts.public(_artifacts.describe(
                self.state.corpus, urllib.parse.unquote(ref)))
            d.pop("source", None)
            return self._artifact_send(200, d)
        d = _artifacts.describe(self.state.corpus, urllib.parse.unquote(ref))
        data = d.pop("_bytes", None)
        if data is None:
            code = {"unknown": 404, "not-an-artifact": 409, "not-held": 409,
                    "purged": 410}.get(d["state"], 500)
            body, ctype, disp = (json.dumps(d, default=str).encode(),
                                 "application/json", None)
        else:
            t = d["treatment"]
            code, body, ctype, disp = 200, data, t["content_type"], \
                t["disposition"]
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self._artifact_headers()
        self.send_header("X-Mentis-Artifact-State", d["state"])
        if data is not None:
            self.send_header("X-Mentis-Artifact-Digest", d["digest"])
            self.send_header("X-Mentis-Artifact-View", d["treatment"]["view"])
            # Immutable: the ref names bytes that never change -- but a purge
            # ends them, so a shared cache is not trusted with them.
            self.send_header("Cache-Control", "private, max-age=3600")
            name = (d.get("name") or d["digest"][:12]).encode(
                "ascii", "replace").decode().replace('"', "").replace(
                "?", "_").replace("\r", "").replace("\n", "")
            self.send_header("Content-Disposition",
                             f'{disp}; filename="{name}"')
        else:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # -- the pictures a look uses (mentis/presentation.py) -------------------
    #
    # The artifact routes' protections, because these are the same kind of
    # thing: bytes a browser sent, served back to a browser. Upload needs
    # `X-Mentis-Upload: 1` and an exact Content-Length within the cap, and the
    # bytes must say they are a picture. Serving sends only verified bytes, with
    # no Access-Control-Allow-Origin, nosniff and CORP same-origin. A picture is
    # named by its hash, so it never changes and may be cached for good.

    def _look_upload(self):
        from mentis.worker import CAPABILITY_HEADER
        send = self._artifact_send
        if self.headers.get(CAPABILITY_HEADER):
            return send(403, {"error": "a worker grant authorises /api/worker "
                                       "and nothing else"})
        if self.headers.get("X-Mentis-Upload") != "1":
            return send(400, {"error": "missing X-Mentis-Upload"})
        raw = self.headers.get("Content-Length")
        if raw is None:
            return send(411, {"error": "a Content-Length is required"})
        try:
            length = int(raw)
        except ValueError:
            return send(400, {"error": f"Content-Length {raw!r} is not a number"})
        if length < 0 or length > _presentation.MAX_PICTURE:
            return send(413, {"error": f"a picture may be at most "
                                       f"{_presentation.MAX_PICTURE} bytes"})
        data = self._read_body(length)
        if len(data) != length:
            return send(400, {"error": f"declared {length} bytes, "
                                       f"received {len(data)}"})
        try:
            sha = _presentation.add_picture(self.state.corpus.root, data)
        except ValueError as exc:
            return send(400, {"error": str(exc)})
        return send(200, {"picture": sha})

    def _look_picture(self, sha):
        from mentis.worker import CAPABILITY_HEADER
        if self.headers.get(CAPABILITY_HEADER):
            return self._artifact_send(
                403, {"error": "a worker grant authorises /api/worker and "
                               "nothing else"})
        got = _presentation.picture(self.state.corpus.root, sha)
        if got is None:
            return self._artifact_send(404, {"error": "no such picture"})
        data, ctype = got
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._artifact_headers()
        self.send_header("Cache-Control", "private, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(data)

    def _export(self, kind: str, eid: str):
        """STREAM AN EXPORT ARCHIVE (conversation or turn) AS A ZIP FILE.

        Packages the closure using `mentis.exchange.export` into a standard
        .zip archive and streams it with Content-Type: application/zip and
        proper Content-Disposition: attachment; filename=...
        """
        import shutil
        import tempfile
        from mentis.exchange import ExchangeRefused
        from mentis.exchange.export import export as exchange_export
        from mentis.worker import CAPABILITY_HEADER

        if self.headers.get(CAPABILITY_HEADER):
            return self._send(
                403, {"error": "a worker grant authorises /api/worker and "
                             "nothing else",
                      "kind": "PermissionError",
                      "asked_for": f"/api/{kind}s/{eid}/export"})

        corpus = self.state.corpus
        try:
            entry = corpus.read([eid])
            if not entry:
                return self._send(404, {"error": f"no such {kind}: {eid}",
                                         "kind": "NotFoundError"})
        except Exception:
            return self._send(404, {"error": f"no such {kind}: {eid}",
                                     "kind": "NotFoundError"})

        filename = f"{kind}-{eid}.zip"
        if kind == "conversation":
            try:
                conv = self.state.cv.conversation_now(eid) or entry[0]
                name = (conv.get("body") or {}).get("name")
                if name:
                    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
                    if safe:
                        filename = f"{safe}-{eid}.zip"
            except Exception:
                pass

        tmpdir = tempfile.mkdtemp()
        try:
            zip_path = os.path.join(tmpdir, "export.zip")
            kw = {"conversation": eid} if kind == "conversation" else {"turn": eid}
            exchange_export(self.state.path, out=zip_path, **kw)
            file_size = os.path.getsize(zip_path)

            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

            with open(zip_path, "rb") as f:
                while chunk := f.read(64 * 1024):
                    self.wfile.write(chunk)
        except ExchangeRefused as exc:
            err_msg = str(exc)
            if "is not in this Brain" in err_msg or "not in this Brain" in err_msg:
                return self._send(404, {"error": err_msg, "kind": "NotFoundError"})
            return self._send(400, {"error": err_msg, "kind": "ExchangeRefused"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            return self._send(500, {"error": str(exc), "kind": type(exc).__name__})
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    def _exchange_import(self, parsed, length):
        if self.headers.get("X-Mentis-Upload") != "1" and self._missing_client(parsed.path, "POST"):
            return
        raw = self._read_body(length)
        from mentis.web.exchange_import import handle_import_request
        code, result = handle_import_request(self.state, parsed.path, self.headers, raw)
        return self._send(code, result)

    def _api(self, parsed, body, method):
        """One place decides what a worker grant is good for: one route.

        THE PREMISE THIS REPLACES. The worker used to be kept away from the
        write routes by not being told the address -- which was never a
        control, because a local process can find a loopback port, and
        because the launcher it runs has the address written in it. Secrecy
        was doing no work. Authorisation does: a grant is admissible on
        `/api/worker` and NOWHERE else, so learning the address stops being
        worth anything.

        Refused here rather than in each route, because a list of routes to
        protect is a list somebody forgets to add to. A route earns a grant
        by being named here; everything else refuses one by existing.

        *** UNSETTLED, AND THE LARGEST OPEN QUESTION ON THIS SURFACE. ***

        THIS GATE IS ONE-SIDED, AND IT ALWAYS HAS BEEN. It says what a request
        PRESENTING A GRANT may reach. It says nothing about a request presenting
        NOTHING, which is unauthenticated and may reach every route here --
        including `/api/entries` with `establish: true`, `/api/personas`,
        `/api/conversations/<id>/instructions`, and the turns route with any
        `author` and any `dispatch`. `_observed_writer` records such a request
        honestly as `unattributed-local-request`, which is the truth and is not
        the same as refusing it.

        WHY THAT IS NOW WORTH WRITING DOWN. It predates the operating loop and
        was the shape of this server from the start: one local process serving a
        local interface, where the interface is the owner. But a dispatched
        worker is ALSO a local process now, and it is handed this server's
        address and its own grant in a file inside its own workspace or home.
        Reaching these routes WITHOUT presenting the grant establishes governed
        material -- measured -- so the bounded door is bypassed rather than
        broken, and no scope check is involved.

        *** AND THIS ROUTE IS NOT THE WORST PATH, WHICH IS THE PART THAT
        MATTERS. *** Two independent challenges, blind to each other, both
        falsified the framing this paragraph used to carry -- that the HTTP
        surface is where the boundary lives. It is not. `worker.boot_command`
        writes into the worker's own configuration file, verbatim, BOTH the
        path of this package AND the path of the corpus:

            import sys; sys.path.insert(0, r'<repo>'); from mentis.worker
            import serve; serve(r'<corpus>', via=..., capability=...)

        With a shell -- which two of three runtimes have by design, so that
        dispatched work can actually be done -- that is a complete recipe. Three
        lines of Python, no HTTP, no grant, no header:

            api.open_corpus(<corpus>).create_and_establish(
                kind='persona', body={...}, attributed_to='human:brian',
                written_by='human')

        Reproduced against a disposable corpus: it stands, and `verify_chain`
        reports intact afterwards. It is STRICTLY WORSE than this route, because
        this route at least stamps `unattributed-local-request` through
        `_observed_writer`. Direct to the spine, the caller writes
        `written_by: 'human'` and the record says the owner typed it. The one
        honest trace the HTTP path leaves is the trace the cheaper path erases.

        SO CLOSING THIS ROUTE WOULD REMOVE THE SECOND-BEST BYPASS AND LEAVE THE
        BEST ONE, and would buy a false sense of closure -- which is why nothing
        here has been changed. Both challenges converged on the same conclusion:
        within one OS trust domain there is no in-band mechanism that separates
        "the owner's interface" from "a thing the owner's interface started".
        Peer-process identity is not the exception it appears to be: process
        lineage is launderable without privilege (`Win32_Process.Create`
        reparents to WmiPrvSE), so it is a speed bump. The only measured real
        boundary is a different OS PRINCIPAL for dispatched work, which is a
        funded piece of work and a decision for a person.

        WHAT IS TRUE, AND IS WHAT THE REST OF THIS MODULE SHOULD BE READ AS
        CLAIMING: nothing PRESENTING a delegated grant can establish governed
        material. Mentis bounds what its interface grants. It does not defend
        the record against code running as the owner, and every `written_by` is
        what this server observed of a request rather than proof of who wrote
        it. Secrecy is not available as an answer here and never was; the
        paragraph above records why.
        """
        from mentis.worker import CAPABILITY_HEADER
        presented = self.headers.get(CAPABILITY_HEADER) or None
        if presented and parsed.path != "/api/worker":
            return self._send(403, {
                "error": "a worker grant authorises the four reads at "
                         "/api/worker and nothing else",
                "kind": "PermissionError", "asked_for": parsed.path})

        query = urllib.parse.parse_qs(parsed.query)
        try:
            # ONE ANSWER PER QUESTION, FOR THIS READ ONLY. `status_of` is asked
            # about the same (Turn, addressee) up to three times in a single read
            # and re-decoded that participant's entire delivery history each
            # time. GET ONLY, DELIBERATELY: a scope spanning a write would answer
            # from before it, so a write is left exactly as it was. See
            # Conversations.reading -- thread-local, and nothing is kept after.
            #
            # A GET ALSO READS BESIDE THE WRITER (R1): it does not wait for
            # another request's write transaction, a 30k-object Sources confirm
            # included. That is safe only because nothing is written on what
            # it read: the store refuses any write inside the scope, and a GET
            # that tried to write (`/api/capacity` records a reading) is
            # answered again from the start outside it, every read under the
            # writer's lock as before R1, and the first answer is discarded --
            # even if the route caught the refusal. See spine/store.py.
            if method == "GET":
                try:
                    with reading_beside_writer(), self.state.cv.reading():
                        result = _routes(self.state, parsed.path, query, body,
                                         method, presented, peer=self.client_address[0])
                except Exception:                 # noqa: BLE001
                    # the refusal itself, or anything after a swallowed one:
                    # that attempt is void and answered again below
                    if not beside_writer_refused():
                        raise
                if beside_writer_refused():
                    with self.state.cv.reading():
                        result = _routes(self.state, parsed.path, query,
                                         body, method, presented, peer=self.client_address[0])
            else:
                result = _routes(self.state, parsed.path, query, body, method,
                                 presented, peer=self.client_address[0])
        except PermissionError as exc:
            return self._send(403, {"error": str(exc),
                                    "kind": "PermissionError"})
        except _BadQuery as exc:
            return self._send(400, {"error": str(exc), "kind": "BadQuery"})
        except Exception as exc:                          # noqa: BLE001
            refused = isinstance(exc, _BadRequest)
            return self._send(400 if method == "POST" or refused else 500,
                              {"error": str(exc), "kind": type(exc).__name__})
        if result is None:
            return self._send(404, {"error": "no such semantic surface"})
        return self._send(200, result)


def start_demo_activity(st):
    """Really start a few executions IN THIS PROCESS, so Activity has live work.

    Live executions are machine-local: a server sees the ones it started. The
    fixture builder is a different process, so without this the Activity
    surface is honestly -- and unhelpfully -- empty. Nothing is faked; these
    are real executions and ending one really ends it.
    """
    cv = st.cv
    personas = {p["body"]["name"]: p["id"]
                for p in st.corpus.entries_of_kind("persona")}
    alias = {p["body"]["alias"]: p["id"] for p in cv.all_participants()}
    named = {c["body"]["name"]: c["id"] for c in cv.all_conversations()}
    started = []
    for who, conversation, persona, runtime in [
            ("@Ada", "Solid electrolytes", "Researcher", "codex"),
            ("@Nadia", "Solid electrolytes", "Researcher", "claude"),
            ("@Elena", "Saltmarsh", "NPC", "claude"),
            ("@Jarvis", None, "Personal Assistant", "claude")]:
        if who not in alias:
            continue
        ex = cv.begin_execution(
            participant=alias[who],
            conversation=named.get(conversation) if conversation else None,
            persona=personas.get(persona), runtime=runtime)
        # An execution working inside a Conversation records its act against
        # the Turn it is working on, which is what makes "what are they
        # working on" answerable from the record rather than from prose. An
        # execution at Brain scope has no Turn and records none -- that case
        # is left exactly as it is, so the interface has to handle an honest
        # gap rather than only the happy path.
        turns = cv.turns(ex.conversation) if ex.conversation else []
        on = turns[-1]["turn"] if turns else None
        cv.record_act(actor=alias[who], act="execution-started",
                      conversation=ex.conversation, turn=on,
                      execution=ex.reference,
                      runtime=runtime, because="started with the demo server")
        started.append(ex.reference)
    return started


def _say_what_is_missing(corpus):
    """Print, loudly, every declaration this Brain's vocabulary does not carry.

    STARTUP CHANGES NOTHING, AND THAT IS THE POINT OF PRINTING. A server that
    silently brought an existing Brain's definitions up to date would be
    rewriting somebody's vocabulary because a process started, with no act, no
    actor and no record of the decision -- and the one thing a vocabulary must
    be is something a person said. So the gap is made IMPOSSIBLE TO MISS
    instead: named here, at the top of the log, with the tool to run, and
    reported by `/api/integrity` for anything reading rather than watching.

    WHY IT IS WORTH SHOUTING ABOUT. A missing `knowing` does not degrade
    anything visibly. The placed procedure still stands, still reads as placed,
    and is simply never delivered -- `withheld` empty, `governs()` empty,
    `propose_material` refusing every Kind. Silence is exactly what the failure
    looks like, so silence here is not an option.
    """
    missing = vocabulary.missing_declarations(corpus)
    if not missing:
        return
    bar = "!" * 72
    print(bar)
    print(f"!! {len(missing)} Kind declaration(s) ARE MISSING FROM THIS BRAIN. "
          f"Production reads them.")
    for row in missing:
        print(f"!!   {row['kind']:26} has no {row['property']!r}  "
              f"(the vocabulary declares {row['vocabulary_declares']!r}; "
              f"current definition is v{row['current_version']})")
    for tool in sorted({row["repair"] for row in missing if row["repair"]}):
        print(f"!! RUN:  python {tool} <brain-path> --write")
    unrepaired = sorted({row["property"] for row in missing
                         if not row["repair"]})
    if unrepaired:
        print(f"!! no migration tool exists yet for: {', '.join(unrepaired)}")
    print("!! Nothing has been changed. Until it is, material of these Kinds "
          "may be delivered by NEITHER channel -- silently.")
    print(bar)


def _say_intake_is_missing(corpus):
    """Warn without seeding or designating anything because a server started."""
    from mentis.bootstrap import baseline
    cv = api.brain(corpus).conversations
    carrier = cv.intake_carrier()
    seeded = baseline.applied(cv) is not None
    if carrier.get("resolved") and seeded:
        return
    print("!" * 72)
    if not seeded:
        print("!! This Brain has no Mentis baseline (owner, @Caretaker, "
              "Personas, rules).")
    if not carrier.get("resolved"):
        print(f"!! Ask Mentis intake does not resolve: {carrier.get('detail')}")
    print('!! New Brain setup: python -m mentis.bootstrap '
          '"<brain-path>" --owner "@your-alias" [--no-tour]')
    print("!! Add --check to see what it would match and write. Existing "
          "material it cannot match safely is refused, never replaced.")
    print("!! Nothing has been seeded or designated by startup.")
    print("!" * 72)


class _Server(ThreadingHTTPServer):
    """The HTTP server, able to stop itself gracefully.

    It counts requests in flight (`_Handler.parse_request` enters,
    `handle_one_request` leaves), and `begin_shutdown` stops taking new
    requests, ends `serve_forever` and waits up to DRAIN_S for those in
    flight to finish. (Mark IV's updater called it through a shutdown
    endpoint, which is gone with the updater.)"""

    DRAIN_S = 60.0

    def __init__(self, *a, **kw):
        import threading
        super().__init__(*a, **kw)
        self._flight = threading.Condition()
        self._in_flight = 0
        self.stopping = False
        self.drained = None         # True/False once draining has ended
        self._stopper = None

    def enter(self) -> bool:
        with self._flight:
            if self.stopping:
                return False
            self._in_flight += 1
            return True

    def leave(self) -> None:
        with self._flight:
            self._in_flight -= 1
            self._flight.notify_all()

    def begin_shutdown(self) -> None:
        import threading
        with self._flight:
            if self.stopping:
                return
            self.stopping = True
        self._stopper = threading.Thread(target=self._stop, daemon=True,
                                         name="mentis-shutdown")
        self._stopper.start()

    def _stop(self) -> None:
        self.shutdown()             # serve_forever returns; no new accepts
        import time as _t
        end = _t.monotonic() + self.DRAIN_S
        with self._flight:
            while self._in_flight > 0 and _t.monotonic() < end:
                self._flight.wait(max(0.0, end - _t.monotonic()))
            self.drained = self._in_flight == 0

    def wait_stopped(self) -> None:
        if self._stopper is not None:
            self._stopper.join()


def mars_command(given: str | None) -> str:
    """The MARS command a server runs agents through: `--mars`, else
    `MENTIS_MARS_COMMAND`, else `mars stdio` (found on PATH by MARS's own
    launcher, not here)."""
    return (given or os.environ.get("MENTIS_MARS_COMMAND") or "mars stdio")


def serve(corpus_path, *, host="127.0.0.1", port=8790, demo_activity=False,
          workspace=None, writable=(), mars=None, execution=None):
    """Serve until stopped (Ctrl-C), then close the store and give up the
    Brain's locks.

    HEADLESS: the HTTP API and `/api/worker`, no interface files. Agents run
    through MARS: `execution` if given, else `MarsExecution(mars_command(mars))`
    constructed lazily by import name (`core.service.mars_execution`), which
    says why no agent can run when MARS is not there."""
    import secrets
    # ONE SERVER PER BRAIN, held by the OS for this process's whole life, so
    # a second server on the same Brain refuses before it opens anything
    # (`mentis.spine.brainlock`).
    from mentis.spine import brainlock, migrations
    from mentis.core.service import mars_execution
    migrations.require_brain(corpus_path)
    token = secrets.token_urlsafe(32)
    lock = brainlock.serve(corpus_path, port=port, token=token)
    command = mars_command(mars)
    try:
        if execution is None:
            execution = mars_execution(command)
        _Handler.state = _State(corpus_path, workspace,
                                answers_at=f"http://{host}:{port}",
                                writable=writable, execution=execution)
    except BaseException:
        # refused to start: nothing is served, so nothing holds the Brain
        brainlock.unserve(corpus_path)
        lock.release()
        raise
    _Handler.serve_lock = lock
    _say_what_is_missing(_Handler.state.corpus)
    _say_intake_is_missing(_Handler.state.corpus)
    # Demo activity really starts executions. Not in the real Brain.
    if demo_activity and _role_at(corpus_path) == _DAY_TO_DAY:
        raise PermissionError(
            "--demo-activity refuses to run against the real day-to-day "
            "Brain at %s" % corpus_path)
    if demo_activity:
        n = len(start_demo_activity(_Handler.state))
        print(f"started {n} live executions in this process")
    httpd = _Server((host, port), _Handler)
    _identity.serving()
    print(f"Mentis on http://{host}:{port}   corpus={corpus_path}   "
          f"workspace={_Handler.state.workspace}")
    why = getattr(execution, "why", None)
    print(f"agents: MARS ({command})" if not why else f"agents: {why}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
    _Handler.state.agents.close()
    # The store's clean close checkpoints the WAL (TRUNCATE) and gives up the
    # OPEN lock; then this server's claim and the SERVE lock.
    _Handler.state.corpus.close()
    brainlock.unserve(corpus_path)
    lock.release()
    _Handler.serve_lock = None
    out = {"stopped": True}
    print(f"Mentis stopped: {out}", flush=True)
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="Serve Mentis headless: its HTTP API and /api/worker.")
    ap.add_argument("corpus", help="the Brain directory")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--workspace", default=None,
                    help="the directory a dispatched agent works in when its "
                         "request declares no repository directory of its "
                         "own. Defaults to the current directory.")
    ap.add_argument("--mars", default=None,
                    help="the command that starts MARS's ACP interface. "
                         "Defaults to $MENTIS_MARS_COMMAND, else 'mars stdio'.")
    ap.add_argument("--writable-root", action="append", default=[],
                    help="a directory every dispatched run may write; "
                         "repeatable. Recorded for the run's grant.")
    ap.add_argument("--demo-activity", action="store_true",
                    help="really start a few executions in this process so the "
                         "Activity surface has live work to show")
    args = ap.parse_args(argv)
    from mentis.spine.brainlock import BrainBusy
    from mentis.spine.migrations import BrainMissing, BrainNotWritable
    try:
        serve(os.path.abspath(args.corpus), host=args.host, port=args.port,
              demo_activity=args.demo_activity, workspace=args.workspace,
              writable=tuple(args.writable_root), mars=args.mars)
    except (BrainMissing, BrainNotWritable, BrainBusy) as exc:
        # REFUSED TO START, said in words, and the exit status says so too
        print(f"Mentis refused to start: {exc}", file=sys.stderr)
        raise SystemExit(3)
    # STOPPED: the Brain is closed, so the process ends now rather than
    # waiting on dispatch threads that would only find it closed.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
