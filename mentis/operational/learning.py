"""Noticing that work went in a way worth understanding, at the moment it ends.

THE GAP THIS CLOSES. Both halves of the epistemic ladder already work when
somebody REMEMBERS to use them: `record_material`, `propose_material` and
`request_adoption` let an owner or an agent write down what work taught them,
with basis, provenance, contestation and owner-only adoption. Nothing reads work
history BACK. A request that drifted from its objective, a part corrected three
times, the same failure recurring on another request, material a run relied on
while a challenge stood open -- each of those is in the record, and nothing ever
looked. So learning happened exactly when an agent's own prose happened to
prompt it, which is to say unreliably.

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT. One read of the record at the two
moments a piece of work actually ends -- a dispatched run finishing
(`web.dispatch`) and a request's outcome being recorded (`worker` `record_outcome`)
-- asking four named questions of it. Nothing polls, nothing wakes on its own,
nothing is kept warm, and nothing here runs between those two moments. No signal
true is the ordinary answer and it writes NOTHING: no note, no artifact, no
interruption. It is not a monitor, a scheduler, a retry or a reflection
requirement, and it is none of the machinery `AGENTS.md` rules out.

AND IT REACHES NO CONCLUSION. When a signal does fire it composes the evidence
and asks an agent, through the ordinary request-and-dispatch path, to look at it.
Which epistemic Kind fits -- or that nothing here is worth preserving -- stays
the agent's judgement, written through the existing `record_material` door with
the existing `requires_basis` gate in front of it. Adoption stays the owner's
(`ladder_writes.owner_act`). This file writes no propositional material at all.

THE FOUR SIGNALS, AND WHY THEY ARE READ THIS WAY. The owner's requirement is
that follow-ups, generations, corrections and discovered work are CONTEXTUAL
EVIDENCE and never proof on their own, so each signal is a difference between
what was authorized and what happened, read from acts that already say which:

  scope-expansion     discovered work PURSUED past the owner's Task Gravity
                      (`pursuit_permitted`) and not chosen by them
                      (`owner_selected`). A finding recorded and left for
                      another task is the OPPOSITE of scope creep and is ruled
                      out by name; so is a follow-up the owner themselves
                      handed to the work, and so is work inside the permission
                      they gave.
  repeated-correction The same request claimed short of met `CORRECTIONS` times
                      or more. Where it then ended met, the reading is
                      ADAPTATION -- what eventually worked -- not failure.
  repeated-failure    This request ended short of met and the record already
                      holds recorded material whose words overlap the same
                      failure (`knowledge.recorded_matching`). Keyed per
                      request, so the same problem recurring on a DIFFERENT
                      request is noticed again rather than deduplicated away.
  contested-basis     Material that governs this work has an open challenge
                      (`ladder.open_challenges`): it was relied on while
                      somebody disputed it.

EVERY BOUND, STATED. What starts it: a dispatched run ending, or an outcome being
recorded -- never anything else, and never a timer. It opens at most
`MOST_PER_CALL` evaluation per call. One evaluation per (request, signal) EVER,
keyed through `mentis.opkeys`'s own mechanism, so a resume-and-return cycle over
the same request cannot reopen it. An evaluation is never opened on an evaluation
(`is_evaluation`), which is what stops a chain of them. A restarted run is passed
over: its work has not ended. Nothing it cannot do blocks the work it was
triggered by -- every failure here is caught and said in what it returns.

Tests: `tests/test_epistemic_learning.py`.
"""

from __future__ import annotations

import traceback

from mentis.conversation import text as text_part

#: THE WHOLE LIST, NAMED. Recognition fires on these and nothing else: a short
#: list that can be argued with, rather than a judgement about work in general.
SIGNALS = ("scope-expansion", "repeated-correction", "repeated-failure",
           "contested-basis")

#: AT MOST ONE EVALUATION PER CALL. Two signals on one ending are two readings
#: of the same evidence, and asking twice would double the cost to say the same
#: thing. The others are named in what this returns, and each is still keyed
#: separately, so a later ending may open one of them.
MOST_PER_CALL = 1

#: THE Nth CLAIM SHORT OF MET THAT MAKES IT "REPEATED". Two: one correction is
#: ordinary work, a second says the first did not settle it.
CORRECTIONS = 2

#: HOW MUCH RELATED HISTORY THE BRIEF CARRIES. A bound on the read, not a
#: budget to fill: what is left out is left out, and the brief says the bound.
PRIOR_OUTCOMES = 3

#: HOW FAR DOWN THE WORK TREE SCOPE IS READ, and how many nodes at most. The
#: tree under one request is small; these keep an unexpected one from making
#: this read expensive at the end of every run.
TREE_DEPTH = 3
TREE_NODES = 40

#: The act that says an evaluation was opened, and what it was opened on.
OPENED = "learning-evaluation-opened"

#: What marks an evaluation request as one, in its own `detail`. Read by
#: `is_evaluation`, which is the guard that keeps evaluations from evaluating
#: each other.
MARK = "learning_evaluation"

#: WHAT THE EVALUATING RUN IS TOLD IT MAY AND MAY NOT DO. In the brief, because
#: the brief is the whole of what it is asked; it grants nothing, and every one
#: of these limits is enforced where it already was.
ASKED = (
    "Look at the evidence below and decide ONE of two things, then record it.\n"
    "  * Nothing here is worth preserving -- ordinary work, or a difference "
    "already accounted for. Say so in the outcome, and record no material.\n"
    "  * Something is. Then record it with `record_material`, choosing the "
    "Kind that fits WHAT THE EVIDENCE SUPPORTS -- an `observation` or "
    "`finding` for what was seen, a `hypothesis` (with its falsifier) where "
    "the cause is not established, a `lesson` where it is, a `problem` for a "
    "difficulty itself -- with the real references below as its `basis`. Do "
    "not force it into a lesson or a rule.\n"
    "A preventive measure that would BIND future work is a `rule`, and a rule "
    "is the owner's to establish: record it and ask with `request_adoption`. "
    "Never establish or adopt anything yourself.\n"
    "If the evidence does not support a claim, say that instead of making one. "
    "Recording nothing is a complete answer to this request."
)


# -- what this is asked about, and what it never asks about -------------------

def is_evaluation(cv, expectation) -> bool:
    """Is this request itself a learning evaluation?

    THE LOOP GUARD, AND THE ONLY ONE NEEDED. An evaluation is dispatched like
    any other work, so its run ends at the same chokepoint that opened it and
    its outcome is recorded through the same door. Without this, each
    evaluation would be evaluated, and so would that one.
    """
    try:
        exp = cv._act(expectation) if expectation else None
    except Exception:                                         # noqa: BLE001
        return False
    return bool(exp and (exp.get("detail") or {}).get(MARK))


def _said(cv, expectation) -> str:
    """The words of a request: its Turn's text, else the reason recorded on it."""
    from mentis.operational import finding_words
    try:
        return (finding_words(cv, expectation) or "").strip()
    except Exception:                                         # noqa: BLE001
        return ""


def _clip(words, limit=600) -> str:
    said = " ".join((words or "").split())
    return said if len(said) <= limit else said[:limit].rsplit(" ", 1)[0] + " ..."


def _kind_knows(cv, eid) -> str | None:
    """Which ladder this entry's Kind is on now (`knowing_of`), or None for an
    entry the record does not hold. One source, no fallback, as everywhere."""
    from mentis.conversation import knowing_of
    try:
        got = cv.corpus.read([eid])
    except Exception:                                         # noqa: BLE001
        return None
    if not got:
        return None
    return knowing_of(cv.corpus, cv._kind_of(got[0]))


def _requests_under(cv, expectation) -> list[tuple[str, str]]:
    """The requests recorded under this one as (request, the one it is under),
    breadth-first, bounded.

    `TREE_DEPTH` and `TREE_NODES`, because this runs at the end of every run
    and the cost of one read there is paid by every piece of work.
    """
    out, frontier, seen = [], [expectation], {expectation}
    for _ in range(TREE_DEPTH):
        nxt = []
        for node in frontier:
            for a in cv._children(node):
                if (a["act"] != "expectation-recorded" or a["id"] in seen
                        or len(out) >= TREE_NODES):
                    continue
                # THIS MECHANISM'S OWN WORK IS NOT THE WORK IT READS. An
                # evaluation is recorded under the request it is about, so
                # without this it would be read as a further piece of work
                # handed out under it -- the mechanism reporting itself as a
                # difference, once per evaluation, for ever.
                if (a["detail"] or {}).get(MARK):
                    continue
                seen.add(a["id"])
                out.append((a["id"], node))
                nxt.append(a["id"])
        frontier = nxt
        if not frontier or len(out) >= TREE_NODES:
            break
    return out


def _executed(cv, child, under) -> list[str]:
    """The acts saying this request was actually taken on: handed out
    (`work-delegated`, recorded under the request it was handed out from),
    assigned to somebody, run, or claimed.

    WHY HANDING OUT COUNTS. A piece of work delegated and waiting for its
    runtime is work the request committed to; the difference between
    authorized intent and execution is already made at the moment it is
    handed out, and waiting for a run to start would make the same reading
    depend on timing.
    """
    own = [a["id"] for a in cv._children(child)
           if a["act"] in ("expectation-assigned", "execution-started",
                           "outcome-claimed")]
    handed = [a["id"] for a in cv._children(under)
              if a["act"] == "work-delegated" and child in (a["about"] or ())]
    return own + handed


# -- the four questions -------------------------------------------------------

#: WHAT A CHILD REQUEST ASKS FOR THAT IS NOT WORK: a question put to somebody.
#: Answering one changes nothing about the objective, so neither limb below
#: reads one as execution.
_NOT_WORK = ("clarification", "decision", "input")


#: THE ACTS THAT MOVE A BOUNDARY rather than add to the record beside it.
#: Recording or proposing NEW material under a request is the encouraged thing
#: to do and is never read as expansion; replacing or rewording material that
#: already governs is a different act, and it is the one this asks about.
_MOVED = ("supersession-proposed", "material-revised", "material-superseded")


def _scope(cv, expectation) -> tuple[list[dict], list[dict]]:
    """Execution that differs from the authorized objective, and everything
    this read looked at and ruled out, by name.

    WHY NOT WORD OVERLAP, WHICH IS WHAT THIS TRIED FIRST AND IS WRITTEN DOWN
    HERE BECAUSE IT IS THE INTERESTING PART. Comparing a child's words with the
    request's (`knowledge.meets`) looked exactly right and is wrong, measured on
    the conversation-management release's own texts: the objective said
    "Archive, Unarchive, Trash, Restore ... No permanent-deletion code or
    route", and the work that expanded past it said "permanently delete a
    Conversation in Trash". They overlap on `conversation`, `trash`,
    `permanent` and `deletion` -- strongly, because expansion is almost always
    ON THE SAME SUBJECT. Overlap can say whether two statements are about the
    same thing; it cannot tell doing the objective from doing the thing the
    objective excluded, because that turns on what the words MEAN. That
    judgement is the evaluating agent's, and it is why the brief carries both
    texts instead of a verdict.

    SO THE TWO LIMBS ARE EXACT FACTS, each a difference the owner names --
    between authorized intent, actual execution, COMMITMENTS and outcomes:

      WORK AFTER THE COMMITMENT. The request was claimed complete
      (`completion.claims_of`), and then more work was handed out under it and
      taken on. The claim is what the work said it came to; work after it says
      it did not end there. This is the release shape: shipped and bounded on
      one day, and growing on the next.

      DISCOVERED WORK PURSUED PAST THE OWNER'S PERMISSION. A finding is only
      expansion when somebody WENT AND DID IT and the owner neither chose it
      (`owner_selected`) nor gave Task Gravity covering it at its generation
      (`pursuit_permitted`).

    AND THE RULINGS MATTER AS MUCH AS THE SIGNAL. A finding recorded and left
    alone is scope MANAGEMENT; a follow-up the owner handed to the work, or
    their own later word, is an authorized change and clears work done after
    it; work inside the permission they gave is work within authorization; a
    question asked of somebody is not execution at all. Each comes back as a
    `ruled_out` row with its reason, so the evaluating agent is not left to
    re-derive it and a contrasting case can be shown to have been SEEN and not
    flagged.
    """
    from mentis.conversation import KNOWING_HOW
    from mentis.conversation.workflow_change import CHANGE
    from mentis.operational import (completion, discovery, follow_up_label,
                                    follow_up_of, owner_decided,
                                    owner_selected, pursuit_permitted)
    fired, ruled_out = [], []
    where = discovery(cv, expectation)
    allowed = follow_up_of(cv, where["origin"])

    # -- the owner's own later word, which authorizes what follows it --------
    # TWO SHAPES IT HAS, AND BOTH CLEAR WHAT CAME AFTER IT. A follow-up handed
    # to the work while it is open (`attach_follow_up`) is the owner asking for
    # more under the same objective; a reply of theirs carried as a later
    # request (`threads.owner_replied_later`, the same read the work view uses
    # to tell a later round from a fresh pending choice) is the owner
    # continuing work already claimed. Neither is drift.
    from mentis.conversation import threads
    from mentis.operational.work_overview import owner_of
    for a in cv.follow_ups(expectation):
        ruled_out.append({
            "signal": "scope-expansion", "ref": a["id"],
            "reason": "owner-authorized",
            "because": f"the owner handed this follow-up to the work "
                       f"themselves, so what it asks for -- and what was done "
                       f"under it -- is authorized: "
                       f"{_clip(_said(cv, (a['detail'] or {}).get('request')), 200)!r}"})
    reopened = None
    try:
        reopened = threads.owner_replied_later(cv, expectation, owner_of(cv))
    except Exception:                                         # noqa: BLE001
        reopened = None

    # -- limb 1: work handed out after the request was claimed complete ------
    claims = completion.claims_of(cv, expectation)
    committed = next((a for a in claims
                      if (a["detail"] or {}).get("result") == "met"), None)
    for child, under in _requests_under(cv, expectation):
        act = cv._act(child) or {}
        expects = (act.get("detail") or {}).get("expects")
        said = _clip(_said(cv, child), 200)
        if expects in _NOT_WORK:
            ruled_out.append({
                "signal": "scope-expansion", "ref": child,
                "reason": "clarification",
                "because": f"a {expects} asked of somebody, not work done "
                           f"under this request: {said!r}"})
            continue
        started = _executed(cv, child, under)
        if cv.is_finding(child):
            # -- limb 2: discovered work pursued past permission ----------
            if not started:
                ruled_out.append({
                    "signal": "scope-expansion", "ref": child,
                    "reason": "deferred",
                    "because": f"found and left for another bounded task, not "
                               f"pursued here: {said!r}"})
                continue
            chosen = owner_selected(cv, child)
            if chosen:
                ruled_out.append({
                    "signal": "scope-expansion", "ref": child,
                    "reason": "owner-authorized",
                    "because": f"the owner chose to pursue this "
                               f"({chosen['id']}): {said!r}"})
                continue
            permitted = pursuit_permitted(cv, child)
            if permitted:
                ruled_out.append({
                    "signal": "scope-expansion", "ref": child,
                    "reason": "within-authorization",
                    "because": f"generation {permitted['generation']} of "
                               f"discovered work, inside the permission on "
                               f"this request "
                               f"({follow_up_label(permitted['follow_up'])}): "
                               f"{said!r}"})
                continue
            ruled = owner_decided(cv, child)
            fired.append({
                "signal": "scope-expansion", "reading": "deviation",
                "evidence": [child, *started[:4]],
                "because": f"discovered work was pursued under this request "
                           f"that the owner did not choose and their "
                           f"permission on it does not cover "
                           f"({follow_up_label(allowed)}, this finding at "
                           f"generation {discovery(cv, child)['generation']}): "
                           f"{said!r}"
                           + (f" The owner had it {ruled}." if ruled else "")})
            continue
        if committed is None or not started:
            continue
        after = [a["id"] for a in (cv._children(child) + cv._children(under))
                 if a["id"] in started and a["at"] > committed["at"]]
        if not after:
            continue
        if reopened:
            ruled_out.append({
                "signal": "scope-expansion", "ref": child,
                "reason": "owner-authorized",
                "because": f"handed out after this request was claimed "
                           f"complete, and the owner has since replied in this "
                           f"line of work, carried as {reopened['request']}: "
                           f"{said!r}"})
            continue
        if cv.follow_ups(expectation):
            ruled_out.append({
                "signal": "scope-expansion", "ref": child,
                "reason": "owner-authorized",
                "because": f"handed out after this request was claimed "
                           f"complete, under a follow-up the owner handed to "
                           f"this work: {said!r}"})
            continue
        fired.append({
            "signal": "scope-expansion", "reading": "deviation",
            "evidence": [child, committed["id"], *after[:3]],
            "because": f"this request was claimed {('met')!r} "
                       f"({committed['id']}: "
                       f"{_clip((committed['detail'] or {}).get('summary'), 200)!r}) "
                       f"and then more work was handed out under it and taken "
                       f"on: {said!r}"})

    # -- what the work did about its own governance, as CONTEXT ---------------
    # NOT A SIGNAL, AND THIS IS THE SECOND THING TRIED AND REJECTED HERE.
    # Changing the Workflow under a request (`change_workflow`), proposing a
    # revision of what a run was told, or proposing a supersession all LOOK
    # like the boundary moving to fit the work -- and every one of them is a
    # SANCTIONED, recorded, reasoned act that the system asks for by name:
    # `change_workflow` exists "when what the work turned out to be no longer
    # fits" its Workflow, and proposing beats acting unilaterally. Firing on
    # them would flag correct behaviour every time it happened, which is the
    # indiscriminate record creation the owner excluded -- and it did: it
    # perturbed four existing workflow-change tests by dispatching an
    # evaluation off their own correct act. So they are carried as context an
    # evaluation can read when something else fires, and they fire nothing.
    for a in cv.history(caused_by=expectation):
        changed = (a["detail"] or {}).get(CHANGE) \
            if a["act"] == "expectation-assigned" else None
        if changed:
            ruled_out.append({
                "signal": "scope-expansion", "ref": a["id"],
                "reason": "adapted-and-recorded",
                "because": f"the carrier changed the Workflow governing this "
                           f"request, with its reason and evidence, rather "
                           f"than working outside it: "
                           f"{_clip(a.get('because'), 200)!r}"})
            continue
        if a["act"] not in _MOVED:
            continue
        procedural = [eid for eid in (a["about"] or ())
                      if _kind_knows(cv, eid) == KNOWING_HOW]
        if procedural:
            ruled_out.append({
                "signal": "scope-expansion", "ref": a["id"],
                "reason": "adapted-and-recorded",
                "because": f"governing material was {a['act']} under this work "
                           f"({', '.join(procedural)}) -- put forward, not "
                           f"acted on: {_clip(a.get('because'), 200)!r}"})
    return fired, ruled_out


def _corrections(cv, expectation) -> tuple[list[dict], list[dict]]:
    """The same request claimed short of met more than once -- and whether it
    then got there.

    RECOGNISING WHAT WORKED, NOT ONLY WHAT DID NOT. The owner's requirement is
    that a consequential successful adaptation is as much worth preserving as
    a failure. It is the same evidence: a part corrected twice and then met
    says something about what the corrections changed, and the brief asks the
    question that way round. One correction fires nothing: ordinary work.
    """
    from mentis.operational import completion
    claims = completion.claims_of(cv, expectation)
    short = [a for a in claims if (a["detail"] or {}).get("result") != "met"]
    if len(short) < CORRECTIONS:
        if short:
            return [], [{"signal": "repeated-correction", "ref": short[-1]["id"],
                         "reason": "single-correction",
                         "because": f"claimed short of met {len(short)} time(s); "
                                    f"{CORRECTIONS} is where it is read as "
                                    f"repeated"}]
        return [], []
    met = bool(claims) and (claims[-1]["detail"] or {}).get("result") == "met"
    return [{"signal": "repeated-correction",
             "reading": "adaptation" if met else "deviation",
             "evidence": [a["id"] for a in short[-4:]],
             "because": (f"this request was claimed short of met "
                         f"{len(short)} times and then met -- what the "
                         f"corrections changed is what worked"
                         if met else
                         f"this request has been claimed short of met "
                         f"{len(short)} times; the first correction did not "
                         f"settle it")}], []


def _failure(cv, expectation) -> tuple[list[dict], list[dict]]:
    """This request ended short of met, and the record already holds recorded
    material about the same failure.

    MATERIAL, NOT A VERDICT. `recorded_matching` is the same overlap read
    delivery uses for Relevant experience, and what it finds is handed over as
    candidates to weigh -- never as a cause, and never as proof the two are the
    same problem. Adopted material is deliberately not read here: this asks
    whether the record has SEEN this before, and what stands is already in
    front of every run.
    """
    from mentis.conversation.knowledge import recorded_matching
    from mentis.operational import completion
    latest = completion.latest_claim(cv, expectation)
    if latest is None:
        return [], []
    detail = latest["detail"] or {}
    if detail.get("result") == "met":
        return [], []
    said = _clip(detail.get("summary") or "", 400)
    if not said:
        return [], []
    prior = [r for r in recorded_matching(cv.corpus, said)][:PRIOR_OUTCOMES]
    if not prior:
        return [], [{"signal": "repeated-failure", "ref": latest["id"],
                     "reason": "first-of-its-kind",
                     "because": "nothing recorded overlaps how this ended, so "
                                "there is no recurrence to read"}]
    return [{"signal": "repeated-failure", "reading": "deviation",
             "evidence": [latest["id"], *[r["entry"] for r in prior]],
             "because": f"this request ended {detail.get('result')!r} and "
                        f"{len(prior)} recorded item(s) overlap how it ended "
                        f"({', '.join(r['entry'] for r in prior)}); the same "
                        f"failure may be recurring"}], []


def _contested(cv, expectation) -> tuple[list[dict], list[dict]]:
    """Material that governs this work with an open challenge on it.

    RELIED ON WHILE DISPUTED. `governed_named` is what the record says governs
    this request; `open_challenges` is the Ladder's own read of a `disputes`
    link nobody withdrew or set aside. A challenge raised and answered is not
    one.
    """
    from mentis.conversation import ladder
    fired, ruled_out = [], []
    try:
        governing = cv.governed_named(expectation)
    except Exception:                                         # noqa: BLE001
        return [], []
    for eid in governing:
        open_ones = ladder.open_challenges(cv.corpus, eid)
        if not open_ones:
            continue
        fired.append({
            "signal": "contested-basis", "reading": "deviation",
            "evidence": [eid, *[c["objection"] for c in open_ones[:3]
                                if c.get("objection")]],
            "because": f"material governing this work ({eid}) has "
                       f"{len(open_ones)} open challenge(s): it was relied on "
                       f"while somebody disputed it"})
    return fired, ruled_out


def signals(cv, expectation) -> dict:
    """What the four questions say about this request, right now.

    READ-ONLY, AND NEVER RAISES. One question failing to read must not take the
    others with it, and none of them may take the run's own ending with it: a
    question that could not be answered is said in `unread` rather than
    swallowed or thrown.
    """
    fired, ruled_out, unread = [], [], []
    for name, ask in (("scope-expansion", _scope),
                      ("repeated-correction", _corrections),
                      ("repeated-failure", _failure),
                      ("contested-basis", _contested)):
        try:
            got, ruled = ask(cv, expectation)
        except Exception as exc:                              # noqa: BLE001
            traceback.print_exc()
            unread.append({"signal": name,
                           "why": f"{type(exc).__name__}: {exc}"})
            continue
        fired.extend(got)
        ruled_out.extend(ruled)
    return {"fired": fired, "ruled_out": ruled_out, "unread": unread}


# -- the evidence an evaluation is given --------------------------------------

def compose(cv, expectation, signal, *, ruled_out=()) -> str:
    """The bounded brief one evaluation is asked on: the original objective,
    what actually happened, what was ruled out, and what it may record.

    EVERY PART OF IT IS FROM THE RECORD, and the expected answer is nowhere in
    it. The signal says what difference was noticed and names its evidence by
    reference; it does not say what the lesson is, which Kind to use, or that
    there is one.
    """
    from mentis.operational import discovery, follow_up_label, follow_up_of
    exp = cv._act(expectation) or {}
    where = discovery(cv, expectation)
    lines = [
        "A learning evaluation, opened by the record when this work ended. "
        "It is bounded: read the evidence, answer, record the outcome.",
        "",
        f"## The request ({expectation})",
        _clip(_said(cv, where["origin"] or expectation), 1200) or "(no words)",
        "",
        f"Authorized scope: "
        f"{follow_up_label(follow_up_of(cv, where['origin']))}; "
        f"this work is generation {where['generation']} from that objective.",
        "",
        f"## What was noticed: {signal['signal']} "
        f"({signal.get('reading') or 'deviation'})",
        signal["because"],
        "",
        "Evidence, by reference (read each with `resolve`; the work's own "
        "history with `history`):",
    ]
    lines += [f"  - {ref}" for ref in (signal.get("evidence") or ())]
    mine = [r for r in ruled_out if r.get("signal") == signal["signal"]]
    if mine:
        lines += ["",
                  "Already looked at and NOT counted as a difference "
                  "(do not re-litigate these):"]
        lines += [f"  - {r['reason']}: {r['because']}" for r in mine]
    if exp.get("conversation"):
        lines += ["", f"Conversation: {exp['conversation']}"]
    lines += ["", "## What is asked", ASKED]
    return "\n".join(lines)


# -- opening one, and asking somebody ------------------------------------------

def _carrier(cv, expectation) -> str | None:
    """Who is asked: whoever carries the work, else whoever recorded it.

    ITS OWN CARRIER, FOR A REASON. This is the record-outcome-and-learning step
    of the work that just ended, so the agent that did the work is the one with
    the context to say what it taught -- and attributing the ask to anybody else
    would put words in their mouth.
    """
    try:
        who = cv.assigned_carrier(expectation).get("carrier")
    except Exception:                                         # noqa: BLE001
        who = None
    if who:
        return who
    return (cv._act(expectation) or {}).get("actor")


def _key_name(signal) -> str:
    """The key one evaluation is remembered under: the signal AND ITS READING.

    THE READING IS PART OF WHAT THE EVENT IS, which is why it is in the key.
    A request corrected twice is one event; the same request corrected twice
    AND THEN MET is a different one -- the first is a difficulty, the second is
    what resolved it, and the owner asked for consequential successful
    adaptations to be recognised as well as failures. Keyed by the signal
    alone, the adaptation would be answered with the failure's evaluation and
    never looked at.
    """
    return f"learning:{signal['signal']}:{signal.get('reading') or 'deviation'}"


def _already(cv, expectation, signal) -> dict | None:
    """The keyed act saying this (request, signal, reading) was already
    evaluated.

    `mentis.opkeys`'s OWN MECHANISM, unchanged: one indexed equality on
    `caused_by`, no new storage and no new Kind. Keyed by the REQUEST, never by
    the signal alone, so the same problem on another request is noticed again
    -- the owner's "deduplicate identical events, not entire categories of
    signals".
    """
    from mentis import opkeys
    return opkeys.find(cv.corpus, expectation, _key_name(signal))


def _open(cv, expectation, signal, *, ruled_out, trigger, execution=None):
    """Record one evaluation: the brief as a post, a request for it, the act
    that says it was opened, and its key -- in ONE transaction.

    ALL OF IT OR NONE OF IT. A brief with no request would be a note nobody
    answers, and a key with no request would stop the evaluation ever being
    opened. `expects="result"` and no `returns_to`, so it is work in the
    record that NOTHING WAITS ON: `waiting_on` counts only children that
    return to their parent, so this neither holds the request it came from nor
    resumes it.
    """
    from mentis import opkeys
    exp = cv._act(expectation) or {}
    who = _carrier(cv, expectation)
    if not who:
        return None
    conversation = exp.get("conversation")
    words = compose(cv, expectation, signal, ruled_out=ruled_out)
    with cv.corpus.atomic():
        if _already(cv, expectation, signal):
            return None
        turn = cv.say(conversation, who, [text_part(words)],
                      replies_to=exp.get("turn"))
        asked = cv.expect(
            turn, of=who, kind="result", by=who,
            because=f"learning evaluation: {signal['signal']} noticed on "
                    f"{expectation}",
            caused_by=expectation,
            detail={MARK: True, "signal": signal["signal"],
                    "reading": signal.get("reading") or "deviation",
                    "evidence": list(signal.get("evidence") or ()),
                    "trigger": trigger,
                    # CLOSED THE WAY ITS PARENT IS. A request a hand-started
                    # session recorded is closed with `record_outcome` by a
                    # session; one a dispatched run carries is answered by its
                    # run. Inherited rather than chosen, so the evaluation is
                    # finishable by whoever can finish the work it came from.
                    **({"manual_session": True}
                       if (exp.get("detail") or {}).get("manual_session")
                       else {}),
                    **({"session_execution": execution}
                       if (exp.get("detail") or {}).get("manual_session")
                       and execution else {}),
                    **({"persona": (exp.get("detail") or {})["persona"]}
                       if (exp.get("detail") or {}).get("persona") else {})})
        act = cv.record_act(
            actor=who, act=OPENED, conversation=conversation, turn=turn,
            execution=execution, caused_by=expectation,
            about=[asked, *list(signal.get("evidence") or ())[:6]],
            because=signal["because"],
            detail={"signal": signal["signal"],
                    "reading": signal.get("reading") or "deviation",
                    "trigger": trigger, "evaluation": asked,
                    "evidence": list(signal.get("evidence") or ()),
                    "ruled_out": [r for r in ruled_out
                                  if r.get("signal") == signal["signal"]]})
        opkeys.remember(cv, expectation, _key_name(signal),
                        {"route": "learning", "op": "evaluate",
                         "args": {"expectation": expectation,
                                  "signal": signal["signal"]}},
                        {"evaluation": asked, "act": act, "turn": turn},
                        actor=who, execution=execution,
                        conversation=conversation)
    return {"signal": signal["signal"],
            "reading": signal.get("reading") or "deviation",
            "evaluation": asked, "act": act, "turn": turn,
            "carrier": who, "conversation": conversation,
            "work": words,
            "persona": (exp.get("detail") or {}).get("persona"),
            "evidence": list(signal.get("evidence") or ())}


def consider(cv, expectation, *, trigger, execution=None) -> dict:
    """Ask the four questions about this request's ending, and open at most one
    evaluation. Returns what it looked at and what it did.

    `dispatches` IS HOW THE EVALUATION ACTUALLY RUNS: each entry is a complete
    set of `dispatch_soon` keywords, handed to the existing seam by the caller
    -- the door's own `dispatches` key for an outcome, `dispatch_soon` for a
    run that just ended. Nothing here starts an agent; Mentis does not run
    agents.

    NOTHING IS WRITTEN WHERE NOTHING FIRED. The ordinary ending reaches the
    first return below, with `evaluated: False` and the reason, having written
    nothing at all.
    """
    out = {"request": expectation, "trigger": trigger, "evaluated": False,
           "fired": [], "ruled_out": [], "unread": [], "opened": [],
           "deduped": [], "dispatches": []}
    try:
        if not expectation:
            return {**out, "why": "no request: nothing to read work history for"}
        if is_evaluation(cv, expectation):
            return {**out, "why": "this request IS a learning evaluation; one "
                                  "is never opened on another"}
        got = signals(cv, expectation)
        out.update(fired=got["fired"], ruled_out=got["ruled_out"],
                   unread=got["unread"])
        if not got["fired"]:
            return {**out, "why": "no signal: nothing in this ending differs "
                                  "from what was authorized"}
        for signal in got["fired"]:
            if len(out["opened"]) >= MOST_PER_CALL:
                out["deduped"].append({"signal": signal["signal"],
                                       "why": f"at most {MOST_PER_CALL} "
                                              f"evaluation per ending; this "
                                              f"signal keeps its key and may "
                                              f"open on a later ending"})
                continue
            prior = _already(cv, expectation, signal)
            if prior:
                out["deduped"].append({
                    "signal": signal["signal"], "key": prior["id"],
                    "why": "already evaluated for this request and signal"})
                continue
            made = _open(cv, expectation, signal,
                         ruled_out=got["ruled_out"], trigger=trigger,
                         execution=execution)
            if made is None:
                out["deduped"].append({
                    "signal": signal["signal"],
                    "why": "nobody carries or recorded this request, so there "
                           "is nobody to ask; nothing was written"})
                continue
            out["opened"].append({k: v for k, v in made.items()
                                  if k != "work"})
            out["dispatches"].append(dict(
                conversation=made["conversation"], turn=made["turn"],
                participant=made["carrier"], work=made["work"],
                persona=made["persona"], expectation=made["evaluation"],
                because=f"learning evaluation opened by {made['act']}: "
                        f"{signal['signal']} noticed when work ended"))
        out["evaluated"] = bool(out["opened"])
        return out
    except Exception as exc:                                  # noqa: BLE001
        # AN OPTIONAL EVALUATION NEVER BREAKS THE WORK IT WAS TRIGGERED BY
        # (the owner's requirement 5). Said in the answer and printed, so a
        # failure here is visible rather than silent.
        traceback.print_exc()
        return {**out, "failed": f"{type(exc).__name__}: {exc}",
                "why": "the learning evaluation could not be made; the work "
                       "it was triggered by is unaffected"}


# -- the two chokepoints -------------------------------------------------------

def after_run(st, expectation, *, execution=None, restarted=False,
              start=None) -> dict:
    """A dispatched run has ended (`web.dispatch`'s `finally`). Hook A.

    A RESTARTED RUN IS PASSED OVER, DELIBERATELY. `restart_if_asked` restarts a
    run whose compiled permission rules went stale, and this file's own
    chokepoint sits beside the comment that says why: "Its work has NOT ended
    -- restarted or held -- so nothing waiting on it resumes". That is the
    owner's "interrupted or cancelled" lifecycle case, and it is a PAUSE. The
    record at a pause is half of the work: a signal read there could be one
    the continuation resolves, and the key would then be spent -- the real
    ending would find it already evaluated and say nothing. So the evaluation
    waits for the ending that is one, which is the continuation's.

    A run with no `expectation` is passed over too: there is no request whose
    objective, authorization or history could be read.
    """
    if restarted:
        return {"considered": False, "request": expectation,
                "why": "the run was restarted or held, so its work has not "
                       "ended; the evaluation waits for an ending"}
    got = consider(st.cv, expectation, trigger="run-ended", execution=execution)
    if start is None:
        from mentis.web.dispatch import dispatch_soon
        start = dispatch_soon
    for kw in got.get("dispatches") or ():
        try:
            start(st, **kw)
        except Exception:                                     # noqa: BLE001
            traceback.print_exc()
    return {"considered": True, **got}


def after_outcome(cv, expectation, *, execution=None) -> dict:
    """A request's outcome has been recorded (`worker` `record_outcome`). Hook B.

    CALLED AFTER THAT WRITE HAS COMMITTED, NEVER INSIDE IT. The outcome, its
    claim and its remaining work are the work's own result and must not be able
    to roll back because an optional evaluation failed. Its `dispatches` go
    back in the operation's answer, which the door starts after the operation
    -- and which a replayed `op_key` never starts again (`opkeys._NOT_REPLAYED`).
    """
    return consider(cv, expectation, trigger="outcome-recorded",
                    execution=execution)
