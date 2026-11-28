"""Notice consequential work history at a run ending or recorded outcome.

`signals` reads five bounded candidate shapes: possible scope divergence,
repeated short outcome claims, recurring failures, challenged governing
material, and a recurrence of exactly what adopted material was meant to
prevent. These are evidence for an evaluator, never semantic verdicts.
Ordinary endings write nothing. `consider` aggregates every fresh signal into
one ordinary evaluation request and records a key for each signal's stable
evidence identity in the same transaction. Unchanged evidence is not asked
again; new evidence on the same request is eligible.

At most one evaluation opens per ending, never on another evaluation or a
restarted run. Related request traversal is limited to TREE_DEPTH/TREE_NODES;
displayed prior material to PRIOR_OUTCOMES. These bound returned context, not
every underlying database read. Nothing polls, retries or starts an agent here.
The caller hands the committed evaluation to the existing dispatch seam.

Learning writes own a transaction after the ordinary outcome and its operation
key commit. Exceptions are caught outside learning's transaction so they roll
back all evaluation writes and keys together and cannot undo ordinary work.
No propositional material or adoption is written here: the evaluator chooses
an existing Kind (or records nothing) through the ordinary worker door.
"""

from __future__ import annotations

import hashlib
import json
import re
import traceback

from mentis.conversation import text as text_part

#: THE WHOLE LIST, NAMED. Recognition fires on these and nothing else: a short
#: list that can be argued with, rather than a judgement about work in general.
SIGNALS = ("scope-expansion", "repeated-correction", "repeated-failure",
           "contested-basis", "adoption-effectiveness")

#: All fresh signals share one evaluation and are keyed atomically together.
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

#: WHAT KIND OF EVIDENCE A SIGNAL RESTS ON, said on every signal (`basis`).
#: `observed`: the record holds the event itself -- an act, a claim, a link.
#: `suspected`: the record holds something that may indicate it, and the
#: evaluation is asked whether it does. Never a score, and never a verdict:
#: an observed event is still the evaluator's to weigh.
OBSERVED = "observed"
SUSPECTED = "suspected"

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
    "Answer one of two ways, then record the outcome.\n"
    "  * Nothing here is worth preserving -- ordinary work, or a difference "
    "already accounted for. Say so, and record no material. That is a "
    "complete answer.\n"
    "  * Something is. Record it with `record_material`, with the Kind the "
    "evidence supports -- an `observation` or `finding` for what was seen, a "
    "`hypothesis` (with its falsifier) where the cause is not established, a "
    "`lesson` where it is, a `problem` for a difficulty itself -- and the "
    "references above as its `basis`.\n"
    "A measure that would BIND future work is a `rule`, and the owner's to "
    "establish: record it and ask with `request_adoption`. Never establish "
    "or adopt anything yourself. If the evidence does not support a claim, "
    "say that instead of making one."
)

#: WHY EACH EVENT MIGHT MATTER, AND THE ONE QUESTION ASKED ABOUT IT. Per
#: signal, said once in the brief: the event itself is the signal's own
#: `because`, from the record.
ABOUT = {
    "scope-expansion": (
        "Work done under a request without the authorization the record "
        "shows for it may be work nobody asked for.",
        "Was this work authorized in a way the record shows, or necessary to "
        "the request? If neither, what about how it came to be done is worth "
        "preserving?"),
    "repeated-failure": (
        "One request failing to run more than once may have a single cause "
        "worth knowing before the next attempt.",
        "Do these failures share a cause, and is that cause established by "
        "the evidence or only suspected?"),
    "repeated-correction": (
        "A request corrected more than once says the first correction did "
        "not settle it -- or, where it was then met, that something the "
        "corrections changed worked.",
        "What did the corrections change, and is that worth preserving?"),
    "contested-basis": (
        "Work governed by material that stands challenged may have relied "
        "on something in doubt.",
        "Did the challenged material affect this work? Delivery is not "
        "reliance."),
    "adoption-effectiveness": (
        "Whether adopted guidance helped the work it reached is how the "
        "record learns what its guidance is worth.",
        "Did the adopted item help here, fail to, or does the evidence not "
        "say?"),
}


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


def _authorisers(cv, expectation) -> set:
    """Who may add to this request: whoever asked for it, and whoever asked
    for the work it was delegated under. Read from the record, never from
    words."""
    who, node, seen = set(), expectation, set()
    while node and node not in seen and len(seen) <= TREE_NODES:
        seen.add(node)
        act = cv._act(node) or {}
        if act.get("act") == "expectation-recorded" and act.get("actor"):
            who.add(act["actor"])
        node = act.get("caused_by")
    # NEVER WHOEVER IS DOING THE WORK. A hand-started session records the
    # request it then carries; its own later acts are not the owner's.
    return who - _doing(cv, expectation) - {None}


def _doing(cv, expectation) -> set:
    """Who carries this request: whoever ran it or claimed it, and whoever it
    was assigned TO. An assignment's actor is the person who assigned it --
    the owner, on the ordinary path -- and is not doing the work."""
    doing = set()
    for a in cv._children(expectation):
        if a["act"] in ("execution-started", "outcome-claimed"):
            doing.add(a.get("actor"))
        elif a["act"] == "expectation-assigned":
            doing.update((a.get("about") or ())[:1])
    try:
        doing.add(cv.assigned_carrier(expectation).get("carrier"))
    except Exception:                                         # noqa: BLE001
        pass
    return doing - {None}


def _owner_acts(cv, expectation) -> list[dict]:
    """What the people this request answers to DID on it, as recorded acts:

      * a follow-up of theirs handed to it (`follow-up-attached`, where the
        request handed over is one THEY recorded);
      * their answer to a decision asked under it (`decision-answered`, by
        them) -- the approval a claim asks for is one of these, and "Revise"
        is an instruction to do more. Withdrawing a question is not an
        answer to it, and is not one of these;
      * further work they recorded under it themselves;
      * their assigning it (`expectation-assigned`, by them), to whoever.

    WHICH ANSWER IT WAS IS NOT READ. Whether what followed is what they
    asked for is a judgement about words, and this makes none: it says only
    that they acted on the request after it was claimed met, so the claim
    was no longer the last word on it.

    STRUCTURE, NOT WORDS. Each is an act on this request's own lineage by the
    person it answers to. Nothing here reads what they said, and a post
    somewhere else in the Conversation is not one of these.
    """
    who = _authorisers(cv, expectation)
    out = []
    for a in cv._children(expectation):
        if a["act"] == "follow-up-attached":
            asked = cv._act((a["detail"] or {}).get("request")) or {}
            if asked.get("actor") in who:
                out.append(a)
        elif a["act"] == "expectation-assigned":
            # THEIR ASSIGNING IT, to the same carrier or another: the actor of
            # an assignment is whoever assigned (`_doing`). Handing a request
            # claimed met to somebody is acting on it. Found by the second
            # independent review.
            if a.get("actor") in who:
                out.append(a)
        elif a["act"] == "expectation-recorded" and not (a["detail"] or {}).get(MARK):
            if a.get("actor") in who:
                out.append(a)
            if (a["detail"] or {}).get("expects") == "decision":
                out.extend(r for r in cv._children(a["id"])
                           if r["act"] == "decision-answered"
                           and r.get("actor") in who)
    return out


def _scope(cv, expectation) -> tuple[list[dict], list[dict]]:
    """Scope events the record itself shows. Two, and both are facts:

      * discovered work pursued past its Task Gravity permission, with no
        owner choice to pursue it;
      * work handed out after this request was claimed met, with nothing
        from the person it answers to in between.

    NO READING OF WORDS. An earlier version also fired when a word of an
    exclusion in the request ("do not ...", "no ...") appeared in a child's
    text or in the outcome. On TEST that produced 133 of 137 scope signals,
    including delegations the same request had ordered: the wording of a
    prohibition is not evidence that the prohibited thing happened (owner,
    2026-11-17). Authority is enforced at the door, where it always was; this
    reads only what the lineage, the permission and the claims record.

    A LATER INSTRUCTION FROM THE OWNER IS READ. Work handed out after a met
    claim is a signal only when no act of theirs on this request lies between
    the claim and the hand-out (`_owner_acts`). Their answering "Revise" to
    the approval that claim asked for, and work handed out a minute later, is
    the request continuing as they said -- not work after completion.

    Questions, deferred discoveries and sanctioned governance proposals stay
    context rather than signals.
    """
    from mentis.conversation import KNOWING_HOW
    from mentis.conversation.workflow_change import CHANGE
    from mentis.operational import (completion, discovery, follow_up_label,
                                    follow_up_for, owner_decided,
                                    owner_selected, pursuit_permitted)
    fired, ruled_out = [], []
    where = discovery(cv, expectation)
    allowed = follow_up_for(cv, expectation)

    met_claims = [a for a in completion.claims_of(cv, expectation)
                  if (a["detail"] or {}).get("result") == "met"]
    owner_acts = _owner_acts(cv, expectation) if met_claims else []
    who = _authorisers(cv, expectation) if met_claims else set()
    doing = _doing(cv, expectation) if met_claims else set()
    children = _requests_under(cv, expectation)
    parent = dict(children)

    def own_trunk_between(child):
        """Is this child under discovered work? A finding is the root of its
        own work -- chosen by the owner or pursued within permission, which
        the limb above reads -- and what is handed out under it is that
        work's, not this request's."""
        node = parent.get(child)
        while node and node != expectation:
            if cv.is_finding(node):
                return True
            node = parent.get(node)
        return False
    order = cv._write_order([c for c, _ in children]
                            + [a["id"] for a in met_claims]
                            + [a["id"] for a in owner_acts])

    def at(ref):
        return order.get(ref, -1)

    for child, under in children:
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
            # -- discovered work pursued past permission --------------------
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
                "basis": OBSERVED, "subject": ["finding-pursued", child],
                "evidence": [child, *started[:4]],
                "because": f"discovered work was pursued under this request "
                           f"that the owner did not choose and their "
                           f"permission on it does not cover "
                           f"({follow_up_label(allowed)}, this finding at "
                           f"generation {discovery(cv, child)['generation']}): "
                           f"{said!r}"
                           + (f" The owner had it {ruled}." if ruled else "")})
            continue
        # -- work handed out after the request was claimed met --------------
        if not started:
            continue
        if under != expectation and (own_trunk_between(child)
                                     or act.get("actor") not in doing):
            # WORK UNDER A CHILD IS THAT CHILD'S, with one exception: whoever
            # carries THIS request handing work out under one of its children
            # after claiming this request met. Parking it one level down does
            # not make it the child's own.
            continue
        before = [c for c in met_claims if at(c["id"]) < at(child)]
        if not before:
            continue
        claim = before[-1]
        if act.get("actor") in who:
            ruled_out.append({"signal": "scope-expansion", "ref": child,
                              "reason": "owner-authorized",
                              "because": "recorded under this request by the "
                                         f"person it answers to: {said!r}"})
            continue
        between = [a for a in owner_acts
                   if at(claim["id"]) < at(a["id"]) < at(child)]
        if between:
            ruled_out.append({
                "signal": "scope-expansion", "ref": child,
                "reason": "owner-authorized",
                "because": f"handed out after the met claim {claim['id']}, "
                           f"and after the person this request answers to "
                           f"acted on it ({between[-1]['act']} "
                           f"{between[-1]['id']}): {said!r}"})
            continue
        fired.append({
            "signal": "scope-expansion", "reading": "deviation",
            "basis": OBSERVED, "subject": ["after-met", child],
            "evidence": [child, claim["id"], *started[:3]],
            "because": f"work was handed out under this request after it was "
                       f"claimed complete (met claim {claim['id']}), and nothing from the "
                       f"person it answers to is recorded on it in between: "
                       f"{said!r}"
                       + ("" if who else
                          " This request was recorded by the session that "
                          "carries it, so what its owner told that session "
                          "directly is not in the record; weigh that.")})

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
    """The same request claimed `not-met` more than once -- and whether it
    then got there.

    A CORRECTION IS A CLAIM THAT SOMETHING WAS WRONG, NOT MERELY UNFINISHED.
    `partly` is ordinary progress -- continuing, planned work with a
    recorded continuation, or work that stopped short with none -- and is
    not evidence of a fix-and-retry cycle on its own. Only `not-met` says
    the request was actually claimed short of meeting its objective, which
    is what a correction corrects. Counting `partly` here would fire on
    ordinary planned-progress reports and on abandoned work or waits that
    were never claimed wrong.

    RECOGNISING WHAT WORKED, NOT ONLY WHAT DID NOT. The owner's requirement is
    that a consequential successful adaptation is as much worth preserving as
    a failure. It is the same evidence: a part corrected twice and then met
    says something about what the corrections changed, and the brief asks the
    question that way round. One correction fires nothing: ordinary work.
    """
    from mentis.operational import completion
    claims = completion.claims_of(cv, expectation)
    short = [a for a in claims if (a["detail"] or {}).get("result") == "not-met"]
    if len(short) < CORRECTIONS:
        if short:
            return [], [{"signal": "repeated-correction", "ref": short[-1]["id"],
                         "reason": "single-correction",
                         "because": f"claimed not-met {len(short)} time(s); "
                                    f"{CORRECTIONS} is where it is read as "
                                    f"repeated"}]
        return [], []
    met = bool(claims) and (claims[-1]["detail"] or {}).get("result") == "met"
    return [{"signal": "repeated-correction",
             "reading": "adaptation" if met else "deviation",
             "basis": OBSERVED,
             "evidence": [a["id"] for a in short[-4:]],
             "because": (f"this request was claimed short of met "
                         f"{len(short)} times and then met -- what the "
                         f"corrections changed is what worked"
                         if met else
                         f"this request has been claimed short of met "
                         f"{len(short)} times; the first correction did not "
                         f"settle it")}], []


#: HOW A RUN ENDED THAT IS NOT A FAILURE OF IT, in `evidence.failure_class`'s
#: words: somebody stopped it, or the server it ran under was restarted. A
#: stop is a decision and a restart is a deploy; neither says the work failed.
_STOPPED = ("cancelled", "interrupted")


def _failed_runs(cv, expectation) -> list[dict]:
    """This request's own failed attempts, in the order recorded.

    ITS OWN LINEAGE AND NOTHING ELSE. A failure before a run started is
    recorded under the request; one after a run started is recorded under
    that run's `execution-started` act. Delegated work, other requests and
    other Conversations are not read.
    """
    from mentis.evidence import failure_class
    own = cv._children(expectation)
    endings = [*own, *(ended for began in own
                      if began["act"] == "execution-started"
                      for ended in cv._children(began["id"]))]
    failures = [a for a in endings
                if a["act"] == "delivery-failed"
                and failure_class(a) not in _STOPPED]
    order = cv._write_order([a["id"] for a in failures])
    return sorted(failures, key=lambda a: order[a["id"]])


def _evaluations_of(cv, expectation, signal) -> list[dict]:
    """Evaluations already opened on this request for this signal, oldest
    first: the request each one is, with what it was shown."""
    got = [a for a in cv._children(expectation)
           if a["act"] == "expectation-recorded"
           and (a["detail"] or {}).get(MARK)
           and any(s.get("signal") == signal
                   for s in (a["detail"] or {}).get("signals") or ())]
    order = cv._write_order([a["id"] for a in got])
    return sorted(got, key=lambda a: order[a["id"]])


def _answered(cv, evaluation) -> bool:
    try:
        st = cv.expectation_state(evaluation)
    except Exception:                                         # noqa: BLE001
        return False
    return bool(st.get("response_present") or st.get("satisfied_by")
                or st.get("withdrawn"))


def _failure(cv, expectation) -> tuple[list[dict], list[dict]]:
    """The same request failing to run, again: recorded failed attempts on its
    own lineage, at least `CORRECTIONS` of them since it was last claimed met.

    FAILED RUNS, NOT WORDS ABOUT THEM. An earlier version treated any latest
    claim short of met -- a `partly` progress report included -- as "how this
    ended", and looked its summary up by shared words against every unadopted
    entry in the Brain. On TEST 77 of 85 signals had no recorded failure at
    all, most "prior" items came from other Conversations, and material that
    earlier evaluations had recorded -- dismissals included -- was found by
    the same lookup and cited as prior failure (owner, 2026-11-17). So:

      * a claim is never a failure here. `partly` is progress; `not-met`
        twice is `_corrections`' question, not this one;
      * nothing outside this request's own runs is read, so no other
        Conversation, no similar wording, and nothing an evaluation wrote
        can be evidence;
      * a run somebody stopped, or that a server restart interrupted, is
        not a failed run;
      * one failure is not a recurrence.

    ONE EVALUATION PER RECURRENCE. Failures an earlier evaluation of this
    request was already shown are not shown again. Another is opened only
    when that one has been answered and `CORRECTIONS` further failures have
    been recorded since -- new evidence, not the same evidence restated.
    """
    from mentis.operational import completion
    failures = _failed_runs(cv, expectation)
    if not failures:
        return [], []
    latest = completion.latest_claim(cv, expectation)
    met = [a for a in completion.claims_of(cv, expectation)
           if (a["detail"] or {}).get("result") == "met"]
    order = cv._write_order([a["id"] for a in failures]
                            + [a["id"] for a in met])
    if met:
        # A later met claim ends that episode: the work got there.
        failures = [a for a in failures
                    if order[a["id"]] > order[met[-1]["id"]]]
    if not failures:
        return [], []
    prior = _evaluations_of(cv, expectation, "repeated-failure")
    # EVERYTHING AN EARLIER EVALUATION COUNTED, not only the few it listed as
    # evidence: otherwise the ones it did not list look new for ever.
    shown = {ref for ev in prior
             for ref in ((ev["detail"] or {}).get("evidence") or ())}
    shown |= {ref for ev in prior
              for was in (ev["detail"] or {}).get("signals") or ()
              for ref in was.get("counted") or ()}
    fresh = [a for a in failures if a["id"] not in shown]
    again = bool(prior) and any(a["id"] in shown for a in failures)
    if again:
        last = prior[-1]
        if not _answered(cv, last["id"]):
            return [], [{"signal": "repeated-failure", "ref": last["id"],
                         "reason": "being-evaluated",
                         "because": "an evaluation of this request's failures "
                                    "is open; further failures wait for its "
                                    "answer"}]
        if len(fresh) < CORRECTIONS:
            return [], [{"signal": "repeated-failure", "ref": last["id"],
                         "reason": "already-evaluated",
                         "because": f"{len(fresh)} failure(s) since the last "
                                    f"evaluation of them ({last['id']}); "
                                    f"{CORRECTIONS} is a recurrence"}]
    counted = fresh if again else failures
    if len(counted) < CORRECTIONS:
        return [], [{"signal": "repeated-failure", "ref": counted[-1]["id"],
                     "reason": "first-of-its-kind",
                     "because": "one recorded failed attempt; a second on "
                                "this request is a recurrence"}]
    said = _clip(counted[-1].get("because") or "", 400)
    return [{"signal": "repeated-failure", "reading": "deviation",
             "basis": OBSERVED, "subject": ["failed-runs", counted[0]["id"]],
             "evidence": [a["id"] for a in counted[-4:]],
             "counted": [a["id"] for a in counted],
             "because": f"{len(counted)} attempts at this request are "
                        f"recorded as failed"
                        + (f" since the evaluation {prior[-1]['id']}"
                           if again else "")
                        + f"; the latest: {said!r}"}], []


def _contested(cv, expectation) -> tuple[list[dict], list[dict]]:
    """Open challenges on delivered governance, or on current brief
    governance for a hand-started session. Delivery/availability does not prove
    that the material was followed; the evaluator investigates that question.
    """
    from mentis.conversation import ladder
    from mentis.conversation import (GOVERNING_PREFIXES, GOVERNING_SCOPES,
                                     WHOLE_BRAIN_SCOPE)
    fired, ruled_out = [], []
    exp = cv._act(expectation) or {}
    participants = {_carrier(cv, expectation)} | {
        a["actor"] for a in cv._children(expectation) if a["act"] == "execution-started"}
    governing = set()
    delivered = False
    for participant in participants - {None}:
        for delivery in cv.corpus.deliveries(participant=participant):
            rows = [row for row in delivery.get("behavioural_sources", ())
                    if row.get("for_expectation") == expectation]
            delivered = delivered or bool(rows)
            governing.update(row["source_id"] for row in rows
                             if row.get("supplied_as") == "governance"
                             and row.get("source_id")
                             and not row.get("source_kind", "").endswith("orientation")
                             and (row.get("scope") in GOVERNING_SCOPES
                                  or row.get("scope") == WHOLE_BRAIN_SCOPE
                                  or row.get("scope", "").startswith(GOVERNING_PREFIXES)))
    supplied = "was delivered to this work"
    if not delivered:
        # Hand-started and older sessions have no request-tagged delivery. Use
        # the actual brief composition and label availability, not reliance.
        detail = exp.get("detail") or {}
        persona = next(((a.get("detail") or {}).get("persona")
                        for a in sorted(cv.history(caused_by=expectation),
                                        key=lambda a: a["at"], reverse=True)
                        if a["act"] == "expectation-assigned"
                        and "persona" in (a.get("detail") or {})),
                       detail.get("persona"))
        comp = cv.compose(conversation=exp.get("conversation"),
                          participant=_carrier(cv, expectation), persona=persona,
                          behavioural=cv.governed_named(expectation),
                          carrying=expectation, question=_said(cv, expectation))
        governing.update(comp.governing_ids())
        supplied = "is supplied by this work's current brief (actual use unverified)"
    for eid in sorted(governing):
        open_ones = ladder.open_challenges(cv.corpus, eid)
        if not open_ones:
            continue
        fired.append({
            "signal": "contested-basis", "reading": "deviation",
            "basis": OBSERVED,
            "identity": [eid, *sorted(c["objection"] for c in open_ones
                                       if c.get("objection"))],
            "evidence": [eid, *[c["objection"] for c in open_ones[:3]
                                if c.get("objection")]],
            "because": f"material governing this work ({eid}) has "
                       f"{len(open_ones)} open challenge(s) and {supplied}; "
                       f"investigate its effect rather than assuming reliance"})
    return fired, ruled_out


#: WHAT AN EFFECTIVENESS VERDICT SAYS, in the words `ladder.usage` already
#: counts (`worked`, `failed`; anything else is `other`). Not a score: one
#: outcome, of one adopted item, in one piece of work.
VERDICTS = ("worked", "failed", "inconclusive")

_ENTRY_ID = re.compile(r"\bent-[0-9a-f]{12}\b")


def _adopted_before(cv, eid, at) -> bool:
    """Was `eid` standing, by an establishing link recorded before `at`?"""
    standing = cv.corpus.stands(eid)
    if not standing["stands"]:
        return False
    established = [l for l in cv.corpus.links(to=eid)
                   if l["id"] in standing["established_by"]]
    return bool(established) and min(l["recorded_at"] for l in established) < at


def _delivered_here(cv, expectation, eid) -> list[str]:
    """Delivery records that say `eid` was given to a run of THIS request.

    DELIVERY IS NOT APPLICATION. This says the boundary handed it over, by
    the record the boundary wrote (`for_expectation` on the source); it says
    nothing about whether the run read it, let alone acted on it.
    """
    who = _carrier(cv, expectation)
    rows = cv.corpus.deliveries(participant=who) if who else []
    out = []
    for d in rows:
        for s in d.get("behavioural_sources") or ():
            if (s.get("source_id") == eid
                    and s.get("for_expectation") == expectation):
                out.append(d.get("id") or d.get("execution"))
                break
    return out


def _named_by_work(cv, expectation) -> set:
    """Entries the work ITSELF names: in its claims' summaries and evidence,
    and in the words of the Turns those claims answer with.

    OBSERVED APPLICATION EVIDENCE, AND ONLY THAT. A run that names the item
    says it used it; it is still the evaluator's to weigh whether it did.
    Silence is not evidence it was ignored.
    """
    from mentis.operational import completion
    named = set()
    for c in completion.claims_of(cv, expectation):
        d = c.get("detail") or {}
        said = " ".join([str(d.get("summary") or ""),
                         *[str(e) for e in (d.get("evidence") or ())],
                         _said(cv, d.get("reply_turn")) if d.get("reply_turn") else ""])
        named.update(_ENTRY_ID.findall(said))
    return named


def _facts(cv, expectation, eid, named) -> dict:
    return {"lesson": eid, "delivered": _delivered_here(cv, expectation, eid),
            "named": eid in named}


def _facts_words(f) -> str:
    return ("delivery: " + (f"{len(f['delivered'])} delivery record(s) say it "
                            f"was given to this work's run"
                            if f["delivered"] else
                            "no delivery record says it was given to this work")
            + "; application: " + ("the work's own claim or reply names it"
                                   if f["named"] else
                                   "nothing in the work's claims or replies "
                                   "names it")
            + " -- delivery is not application, and silence is not proof "
              "it was ignored")


def _adopted(cv, expectation) -> tuple[list[dict], list[dict]]:
    """Owner requirement 7: whether adopted guidance helped the work it
    reached, or failed to keep this ending from happening.

    STANDING MATERIAL, READ HERE AND NOWHERE ELSE IN THIS FILE. `_failure`
    reads `recorded_matching` -- unadopted candidates -- on purpose; this asks
    about material the owner already ADOPTED before this ending.

    TWO READINGS, BOTH EVIDENCE TO WEIGH AND NEITHER A VERDICT:
      * `ineffective` -- the ending is short of met and its own words overlap
        adopted material (`considered`): did the guidance reach this work,
        was it followed, or did it miss this case?
      * `applied` -- the ending is met, an adopted item was DELIVERED to this
        work's run, and the work's own claim or reply NAMES it: did it help?
        Only on that observed evidence, never on delivery alone, so ordinary
        successful runs open nothing.
    Each signal names the item it is about (`lesson`), the Turn its verdict is
    in the context of, and the facts the record holds -- delivered or not,
    named by the work or not -- so the evaluator weighs delivery, application
    and effectiveness apart. The verdict is the evaluator's, recorded as an
    `outcome` OF the item (`verdicts_missing` holds the evaluation open until
    it is).
    """
    from mentis.conversation.knowledge import considered
    from mentis.operational import completion
    latest = completion.latest_claim(cv, expectation)
    if not latest:
        return [], []
    result = (latest.get("detail") or {}).get("result")
    named = _named_by_work(cv, expectation)
    context = latest.get("turn")
    fired = []
    if result == "met":
        for eid in sorted(named):
            if not _adopted_before(cv, eid, latest["at"]):
                continue
            f = _facts(cv, expectation, eid, named)
            if not f["delivered"]:
                continue
            fired.append({
                "signal": "adoption-effectiveness", "reading": "applied",
                "basis": OBSERVED,
                "lesson": eid, "context": context, "facts": f,
                "identity": [eid, latest["id"]],
                "evidence": [eid, latest["id"]],
                "because": f"adopted material ({eid}) was delivered to this "
                           f"work, the work names it, and the work was "
                           f"claimed met; weigh whether applying it helped. "
                           + _facts_words(f)})
        return fired, []
    said = _clip((latest.get("detail") or {}).get("summary") or "", 400)
    if not said:
        return [], []
    for row in considered(cv.corpus, said):
        eid = row["entry"]
        if not _adopted_before(cv, eid, latest["at"]):
            continue
        f = _facts(cv, expectation, eid, named)
        fired.append({
            "signal": "adoption-effectiveness", "reading": "ineffective",
            # WORDS IN COMMON, not an event: the ending's summary overlaps
            # the adopted item. Said as what it is.
            "basis": SUSPECTED,
            "lesson": eid, "context": context, "facts": f,
            "identity": [eid, latest["id"]],
            "evidence": [eid, latest["id"]],
            "because": f"adopted material ({eid}) speaks to exactly what "
                       f"this ending reports, and was already adopted "
                       f"before this ending happened: {said!r}; weigh "
                       f"whether the guidance reached this work, was "
                       f"followed, or missed this case -- overlap is not "
                       f"proof it was ignored. " + _facts_words(f)})
    return fired, []


def evaluated_items(cv, evaluation) -> list[dict]:
    """The adopted items an effectiveness evaluation was opened about, with
    the Turn its verdict is in the context of. [] for any other request."""
    exp = cv._act(evaluation) if evaluation else None
    detail = (exp or {}).get("detail") or {}
    if not detail.get(MARK):
        return []
    return [{"lesson": s["lesson"], "context": s.get("context")}
            for s in detail.get("signals") or ()
            if s.get("signal") == "adoption-effectiveness" and s.get("lesson")]


def verdicts_missing(cv, evaluation) -> list[str]:
    """Items an effectiveness evaluation has not yet recorded its verdict on:
    no `outcome` OF the item recorded since the evaluation was opened.

    THE ASSOCIATION IS THE RECORD'S, NOT THE AGENT'S MEMORY. Reconciliation
    holds the evaluation's claim of met pending on this (completion `_rules`),
    so an effectiveness evaluation is never recorded met without its verdict
    linked to the exact item it evaluated -- a visible pending state, never a
    silent gap. Which verdict, and whether the item was applied, stays the
    evaluator's."""
    items = evaluated_items(cv, evaluation)
    if not items:
        return []
    from mentis.conversation import ladder
    opened = (cv._act(evaluation) or {}).get("at") or 0
    missing = []
    for item in items:
        if not any((o.get("recorded_at") or 0) >= opened
                   for o in ladder.outcomes_of(cv.corpus, item["lesson"])):
            missing.append(item["lesson"])
    return list(dict.fromkeys(missing))


def _chronology(cv, expectation) -> list[str]:
    """The request's claims and state changes IN RECORD ORDER, bounded.

    A REQUEST RECORDED MET STAYS MET (`expectation-met` is terminal; later
    findings are linked, nothing is reopened), so a later claim is history
    beside it, not a correction of it. Shown in the order written, because
    the newest claim alone reads like the current state and is not.
    """
    own = [a for a in cv._own_acts(expectation)
           if a["act"] in ("outcome-claimed", "expectation-met",
                           "outcome-pending")]
    if not own:
        return []
    order = cv._write_order([a["id"] for a in own])
    own.sort(key=lambda a: order.get(a["id"], -1))
    lines = ["", "## This request's claims and state, in record order "
                 "(a request recorded met stays met; a later claim is "
                 "history beside it and reopens nothing)"]
    shown = own[-10:]
    if len(own) > len(shown):
        lines.append(f"  ({len(own) - len(shown)} earlier not shown)")
    for n, a in enumerate(shown, start=1):
        d = a.get("detail") or {}
        try:
            who = cv.alias(a["actor"]) if a.get("actor") else "?"
        except Exception:                                     # noqa: BLE001
            who = a.get("actor") or "?"
        if a["act"] == "outcome-claimed":
            what = (f"claim {d.get('result')} by {who}: "
                    f"{_clip(d.get('summary') or '', 160)}")
        elif a["act"] == "expectation-met":
            what = f"recorded MET (from claim {d.get('reconciled_from')})"
        else:
            what = f"claim held pending: {'; '.join(d.get('reasons') or ())}"
        lines.append(f"  {n}. {a['id']} {what}")
    return lines


def signals(cv, expectation) -> dict:
    """What the five questions say about this request, right now.

    READ-ONLY, AND NEVER RAISES. One question failing to read must not take the
    others with it, and none of them may take the run's own ending with it: a
    question that could not be answered is said in `unread` rather than
    swallowed or thrown.
    """
    fired, ruled_out, unread = [], [], []
    for name, ask in (("scope-expansion", _scope),
                      ("repeated-correction", _corrections),
                      ("repeated-failure", _failure),
                      ("contested-basis", _contested),
                      ("adoption-effectiveness", _adopted)):
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

def compose(cv, expectation, noticed, *, ruled_out=()) -> str:
    """The brief one evaluation is asked on: what happened, why it might
    matter, the evidence, and the question.

    EVERY PART OF IT IS FROM THE RECORD, and the expected answer is nowhere in
    it. The signal says what event was noticed and names its evidence by
    reference; it does not say what the lesson is, which Kind to use, or that
    there is one.

    SHORT, AND NOTHING WITHHELD. What was read and set aside as ordinary
    (`ruled_out`) is kept on the opening act, where it can be read, and is not
    repeated here: on TEST it was a sixth of every brief and mostly unrelated
    deferred findings, and the evaluating run fetched its evidence through
    `resolve` and `history` regardless. The request is quoted once, clipped,
    with its reference; the claims are listed only for the signals that are
    about claims or attempts.
    """
    from mentis.operational import discovery, follow_up_for, follow_up_label
    exp = cv._act(expectation) or {}
    where = discovery(cv, expectation)
    lines = [
        "A learning evaluation, opened by the record when this work ended. "
        "It is bounded: read the evidence, answer, record the outcome.",
    ]
    for signal in noticed:
        why, question = ABOUT.get(signal["signal"], ("", ""))
        basis = signal.get("basis") or SUSPECTED
        lines += ["",
                  f"## What happened: {signal['signal']} "
                  f"({signal.get('reading') or 'deviation'}; "
                  + ("observed in the record" if basis == OBSERVED else
                     "suspected, not observed") + ")",
                  signal["because"]]
        if why:
            lines += ["", "Why it might matter: " + why]
        lines += ["", "Evidence:"]
        for ref in signal.get("evidence", ()):
            act = cv._act(ref) if ref.startswith("opr-") else None
            lines += [f"  - {ref}" + (f" (Turn: {act['turn']})"
                                      if act and act.get("turn") else "")]
        if question:
            lines += ["", "The question: " + question]
    lines += ["",
              "Resolve `ent-` entries; find `opr-` acts with `history` in the "
              "Conversation"
              + (f" {exp['conversation']}" if exp.get("conversation") else "")
              + ", and resolve an act's Turn before using it as a basis.",
              "",
              f"## The request ({expectation}; "
              f"{follow_up_label(follow_up_for(cv, expectation))}; "
              f"generation {where['generation']})",
              _clip(_said(cv, where["origin"] or expectation), 500)
              or "(no words)"]
    if any(x.get("signal") == "scope-expansion" for x in noticed):
        followups = cv.follow_ups(expectation)
        if followups:
            lines += ["", "Owner follow-ups handed to this request:"]
            for act in followups:
                ref = (act.get("detail") or {}).get("request")
                lines += [f"  - {ref}: {_clip(_said(cv, ref), 200)}"]
    if ruled_out:
        lines += ["", f"{len(ruled_out)} other thing(s) under this request "
                      "were read and set aside as ordinary; they are listed "
                      "on this evaluation's opening act (`ruled_out`)."]
    if any(x.get("signal") in ("repeated-correction", "repeated-failure",
                               "adoption-effectiveness") for x in noticed):
        lines += _chronology(cv, expectation)
    items = [x for x in noticed if x.get("signal") == "adoption-effectiveness"
             and x.get("lesson")]
    if items:
        lines += ["", "## The effectiveness verdict (required for each item "
                      "below; this evaluation stays pending until it is "
                      "recorded)",
                  "For EACH adopted item, record one `outcome` OF it with "
                  "`record_material`: kind \"outcome\", outcome_of the item, "
                  "in_context the Turn named, basis the evidence you relied "
                  "on, and body {text, result, attempted}. `result` is "
                  "`worked` (it helped), `failed` (it did not help, or did "
                  "not prevent this) or `inconclusive`. `attempted` is true "
                  "ONLY if the evidence shows the work actually applied it -- "
                  "a delivery record shows it was given, not that it was "
                  "used. Say in `text` what the evidence does and does not "
                  "show. This records what happened once and changes no "
                  "standing; a challenge to the item itself is a separate "
                  "act, and yours to make only if the evidence argues it."]
        for x in items:
            lines += [f"  - {x['lesson']}: in_context "
                      f"{x.get('context') or '(the ending Turn)'}"]
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
    """Stable identity of this event, never a whole category per request.

    THE SUBJECT, WHERE THE SIGNAL NAMES ONE: the child it is about and what
    kind of event, or the first failure of a recurrence. Evidence grows as a
    child gains acts -- on TEST the same delegation was evaluated twice 34
    times for that reason -- and the subject does not."""
    identity = signal.get("subject") or signal.get(
        "identity", sorted(set(signal.get("evidence") or ())))
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return f"learning:{signal['signal']}:{signal.get('reading') or 'deviation'}:{digest}"


#: How evaluations opened before signals named their subject said which
#: event they were about: by these words. Read so that what was already
#: evaluated then is not evaluated again now, and for nothing else.
_LEGACY = {"after-met": "more work was handed out after this request was "
                        "claimed complete",
           "finding-pursued": "discovered work was pursued under this request"}


def _previously(cv, expectation, signal) -> dict | None:
    """The evaluation already opened on this request about this same event,
    or None. Whatever it concluded, an unchanged event is not asked again: a
    dismissal is an answer, and what an evaluation wrote is never evidence
    of the event it was asked about."""
    subject = signal.get("subject")
    if not subject:
        return None
    for ev in reversed(_evaluations_of(cv, expectation, signal["signal"])):
        for was in (ev["detail"] or {}).get("signals") or ():
            if was.get("signal") != signal["signal"]:
                continue
            if was.get("subject") == list(subject):
                return ev
            words = _LEGACY.get(subject[0])
            if (not was.get("subject") and words
                    and (was.get("evidence") or [None])[0] == subject[1]
                    and (was.get("because") or "").startswith(words)):
                return ev
    return None


def _already(cv, expectation, signal) -> dict | None:
    from mentis import opkeys
    return (opkeys.find(cv.corpus, expectation, _key_name(signal))
            or _previously(cv, expectation, signal))


def _open(cv, expectation, noticed, *, ruled_out, trigger, execution=None):
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
    with cv.corpus.atomic():
        noticed = [s for s in noticed if not _already(cv, expectation, s)]
        if not noticed:
            return None
        signal = {**noticed[0], "signals": noticed,
                  "evidence": list(dict.fromkeys(ref for s in noticed for ref in s.get("evidence", ()))),
                  "because": "\n".join(s["because"] for s in noticed)}
        words = compose(cv, expectation, noticed, ruled_out=ruled_out)
        turn = cv.say(conversation, who, [text_part(words)],
                      replies_to=exp.get("turn"))
        asked = cv.expect(
            turn, of=who, kind="result", by=who,
            because=f"learning evaluation: {signal['signal']} noticed on "
                    f"{expectation}",
            caused_by=expectation,
            detail={MARK: True, "signals": noticed, "signal": signal["signal"],
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
            detail={"signals": noticed, "signal": signal["signal"],
                    "reading": signal.get("reading") or "deviation",
                    "trigger": trigger, "evaluation": asked,
                    "evidence": list(signal.get("evidence") or ()),
                    "ruled_out": list(ruled_out)})
        for item in noticed:
            opkeys.remember(cv, expectation, _key_name(item),
                            {"route": "learning", "op": "evaluate",
                             "args": {"expectation": expectation, "signal": item}},
                            {"evaluation": asked, "act": act, "turn": turn},
                            actor=who, execution=execution, conversation=conversation)
    return {"signals": noticed, "signal": signal["signal"],
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
        fresh = []
        for signal in got["fired"]:
            prior = _already(cv, expectation, signal)
            if prior:
                out["deduped"].append({"signal": signal["signal"], "key": prior["id"],
                                       "why": "already evaluated this event"})
            else:
                fresh.append(signal)
        if fresh:
            made = _open(cv, expectation, fresh, ruled_out=got["ruled_out"],
                         trigger=trigger, execution=execution)
            if made:
                out["opened"].append({k: v for k, v in made.items() if k != "work"})
                out["dispatches"].append(dict(
                    conversation=made["conversation"], turn=made["turn"],
                    participant=made["carrier"], work=made["work"],
                    persona=made["persona"], expectation=made["evaluation"],
                    because=f"learning evaluation opened by {made['act']}"))
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
