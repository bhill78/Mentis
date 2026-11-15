"""Notice consequential work history at a run ending or recorded outcome.

`signals` reads four bounded candidate shapes: possible scope divergence,
repeated short outcome claims, recurring failures, and challenged governing
material. These are evidence for an evaluator, never semantic verdicts.
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
           "contested-basis")

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
    """Find possible differences between intent, commitments and execution.

    Pursued discoveries retain the existing owner-selection/Task Gravity gates.
    Delegated work after a completion claim and work touching explicit original
    exclusions are candidates even before a first met claim. Owner follow-up
    text is passed for judgement; only explicit linkage clears its own child.
    Questions, deferred discoveries and sanctioned governance proposals remain
    context rather than signals. No lexical match proves a scope violation.
    """
    from mentis.conversation import KNOWING_HOW
    from mentis.conversation.workflow_change import CHANGE
    from mentis.operational import (completion, discovery, follow_up_label,
                                    follow_up_of, owner_decided,
                                    owner_selected, pursuit_permitted)
    fired, ruled_out = [], []
    where = discovery(cv, expectation)
    allowed = follow_up_of(cv, where["origin"])

    followups = cv.follow_ups(expectation)
    objective = _said(cv, expectation)
    exclusions = re.findall(
        r"(?:\bno\b|\bnever\b|\bdo not\b|\bexclude[sd]?\b)"
        r"[^.;\n]+", objective, flags=re.I)

    def touches_exclusion(words):
        # Shared content in an EXCLUSION is evidence of possible divergence,
        # unlike overlap with the positive objective. It is not a verdict.
        from mentis.conversation.knowledge import tokens_of
        return any(any(len(t) >= 5 and t[:6] in words.lower()
                       for t in tokens_of(clause)
                       if t not in {"without", "never", "exclude", "excludes"})
                   for clause in exclusions)

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
        if not started:
            continue
        after = [a["id"] for a in (cv._children(child) + cv._children(under))
                 if a["id"] in started and committed and a["at"] > committed["at"]]
        if not after and not touches_exclusion(_said(cv, child)):
            continue
        # Only explicit linkage authorizes this child. An owner follow-up on
        # another subject cannot clear it. Even similar words are not a grant.
        authorized = next((f for f in followups
                           if (f.get("detail") or {}).get("request") in (child, under)), None)
        if authorized:
            ruled_out.append({"signal": "scope-expansion", "ref": child,
                              "reason": "owner-authorized",
                              "because": "work explicitly under the owner's follow-up"})
            continue
        fired.append({
            "signal": "scope-expansion", "reading": "deviation",
            "evidence": [child, *([committed["id"]] if after else []),
                         *(after or started)[:3]],
            "because": ("more work was handed out after this request was claimed complete"
                        if after else
                        "executed work overlaps an explicit exclusion in the original objective")
                       + f": {said!r}. Compare intent and execution; this is a potential "
                         "deviation, not a conclusion. Owner follow-ups are context below; "
                         "decide whether any actually authorizes this work."})

    # Work can expand on the trunk without any delegated child. Ignore repeated
    # restatements of the same outcome through the evidence digest, below.
    latest = completion.latest_claim(cv, expectation)
    if latest and touches_exclusion((latest.get("detail") or {}).get("summary", "")):
        summary = (latest.get("detail") or {}).get("summary", "")
        # A restatement of an exclusion is not evidence of performing it.
        positive = re.sub(r"(?:\bno\b|\bnever\b|\bnothing\b|\bdo not\b|\bwithout\b)"
                          r"[^.;\n]+", "", summary, flags=re.I)
        if touches_exclusion(positive):
            fired.append({"signal": "scope-expansion", "reading": "deviation",
                          "evidence": [latest["id"]],
                          "identity": {"outcome": positive.strip()},
                          "because": "the outcome describes work overlapping an explicit "
                                     f"exclusion: {_clip(summary, 400)!r}; compare it with "
                                     "the original objective and owner authorization"})

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
             "evidence": [a["id"] for a in short[-4:]],
             "because": (f"this request was claimed short of met "
                         f"{len(short)} times and then met -- what the "
                         f"corrections changed is what worked"
                         if met else
                         f"this request has been claimed short of met "
                         f"{len(short)} times; the first correction did not "
                         f"settle it")}], []


def _failure(cv, expectation) -> tuple[list[dict], list[dict]]:
    """Recurring failures, from outcome claims or recorded runtime endings.

    Runtime endings belong either to the request (before start) or to one of
    its execution-started acts (after start); neither requires an agent claim.

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
    own = cv._children(expectation)
    # A selection failure belongs directly to the request; a runtime failure
    # belongs to the execution-started act that the request caused. Read both
    # recorded shapes, without walking into delegated work or other requests.
    endings = [*own, *(ended for began in own
                      if began["act"] == "execution-started"
                      for ended in cv._children(began["id"]))]
    failures = [a for a in endings
                if a["act"] in ("delivery-failed", "failed-before-start")]
    # The two lineages interleave, and timestamps can tie. Use the record's
    # append order both for the newest failure and for the recovery boundary.
    order = cv._write_order([a["id"] for a in failures]
                            + ([latest["id"]] if latest else []))
    failures.sort(key=lambda a: order[a["id"]])
    # Actual failed attempts count even if no agent ever got to claim an
    # outcome. A later successful claim ends that failure episode.
    if latest and (latest["detail"] or {}).get("result") == "met":
        failures = [a for a in failures if order[a["id"]] > order[latest["id"]]]
        if not failures:
            return [], []
    if failures and (latest is None or order[failures[-1]["id"]] > order[latest["id"]]):
        current = failures[-1]
        said = _clip(current.get("because") or "", 400)
        evidence = [a["id"] for a in failures[-4:]]
        identity = evidence
    elif latest:
        current = latest
        said = _clip((latest["detail"] or {}).get("summary") or "", 400)
        evidence = [latest["id"]]
        # Repeating an unchanged report is the same evidence. Actual runtime
        # attempts above have their own recorded event ids.
        previous_met = next((a["id"] for a in reversed(completion.claims_of(cv, expectation))
                             if a["at"] < latest["at"]
                             and (a["detail"] or {}).get("result") == "met"), None)
        identity = {"result": (latest["detail"] or {}).get("result"),
                    "summary": (latest["detail"] or {}).get("summary"),
                    "since_recovery": previous_met}
    else:
        return [], []
    if not said:
        return [], []
    prior = [r for r in recorded_matching(cv.corpus, said)][:PRIOR_OUTCOMES]
    if not prior and len(failures) < CORRECTIONS:
        return [], [{"signal": "repeated-failure", "ref": current["id"],
                     "reason": "first-of-its-kind",
                     "because": "no repeated execution failures or overlapping recorded experience"}]
    return [{"signal": "repeated-failure", "reading": "deviation",
             "evidence": [*evidence, *[r["entry"] for r in prior]],
             "identity": {"ending": identity, "prior": [r["entry"] for r in prior]},
             "because": f"{len(failures)} recorded execution failure(s) and "
                        f"{len(prior)} recorded item(s) overlap how this ended: {said!r}; "
                        "investigate whether the same failure is recurring"}], []


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
            "identity": [eid, *sorted(c["objection"] for c in open_ones
                                       if c.get("objection"))],
            "evidence": [eid, *[c["objection"] for c in open_ones[:3]
                                if c.get("objection")]],
            "because": f"material governing this work ({eid}) has "
                       f"{len(open_ones)} open challenge(s) and {supplied}; "
                       f"investigate its effect rather than assuming reliance"})
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

def compose(cv, expectation, noticed, *, ruled_out=()) -> str:
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
    ]
    for signal in noticed:
        lines += [f"## What was noticed: {signal['signal']} "
                  f"({signal.get('reading') or 'deviation'})", signal["because"],
                  "Evidence (ent- entries: resolve; opr- acts: history in the "
                  "Conversation below, locating the act and its Turn; resolve "
                  "that Turn for provenance before record_material):"]
        for ref in signal.get("evidence", ()):
            act = cv._act(ref) if ref.startswith("opr-") else None
            lines += [f"  - {ref}" + (f" (Turn: {act['turn']})"
                                      if act and act.get("turn") else "")]
    followups = cv.follow_ups(expectation)
    if followups:
        lines += ["", "Owner follow-ups (check what each actually authorizes):"]
        for act in followups:
            ref = (act.get("detail") or {}).get("request")
            lines += [f"  - {ref}: {_clip(_said(cv, ref), 600)}"]
    if ruled_out:
        lines += ["", "Context already considered:"]
        lines += [f"  - {r['reason']}: {r['because']}" for r in ruled_out]
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
    """Stable identity of this evidence, never a whole category per request."""
    identity = signal.get("identity", sorted(set(signal.get("evidence") or ())))
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return f"learning:{signal['signal']}:{signal.get('reading') or 'deviation'}:{digest}"


def _already(cv, expectation, signal) -> dict | None:
    from mentis import opkeys
    return opkeys.find(cv.corpus, expectation, _key_name(signal))


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
                    "ruled_out": [r for r in ruled_out
                                  if r.get("signal") == signal["signal"]]})
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
                                       "why": "already evaluated this evidence"})
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
