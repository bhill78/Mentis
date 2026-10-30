"""What state one piece of work is in, reconstructed and never stored.

A TRUNK is a request -- an expectation that is not itself a decision and was
not handed down as somebody else's delegated child -- together with everything
its causal chain holds: its runs, the children it delegated, the decisions
raised under it. Its status is COMPUTED here from facts the record already
keeps. Nothing is written, nothing is cached, and there is no status field
anywhere that this reads back: if the record changes, the answer changes.

EVERY FIELD SAYS WHERE IT CAME FROM. One of four sources, and nothing is shown
stronger than its source:

    recorded   an act in the record says exactly this
    computed   derived from recorded acts by a rule stated here
    runtime    what THIS server process observes now; not durable, and a
               restart forgets it
    unknown    the record cannot say; the reason travels with it

WHAT THIS REFUSES TO SAY, because nothing recorded supports it: progressing,
stuck, active recently, done, adequate. A run with no end recorded is "started,
no end recorded" -- whether it is thinking or dead is not in the record, and
the age of the last act is an age, not a verdict. A result returned is
returned, not accepted. `work-resumed` is resumption, not satisfaction. And a
proposal, or somebody having been addressed, is never something the viewer
owes: only an expectation whose current carrier IS the viewer is.

Built on the Conversation seam only.
"""

from __future__ import annotations

RECORDED, COMPUTED, RUNTIME, UNKNOWN = "recorded", "computed", "runtime", "unknown"

#: Instance liveness values that mean a run is in this process now. Read from
#: the runtime layer's own vocabulary; FINISHED, FAILED, GONE and UNKNOWN are
#: not running.
_LIVE = frozenset({"starting", "alive", "busy"})

#: How many children are itemised before the roll-up says how many it left out.
CHILDREN_SHOWN = 8

from mentis.conversation import ASKED_UNDER_WORK, closed_starts

STARTED, RETURNED, FAILED, RECOVERED = (
    "execution-started", "result-returned", "delivery-failed", "result-recovered")
#: Every act that ends a run. RECOVERED ends it as surely as the other two;
#: what differs is that nothing in Mentis saw it end.
ENDS = (RETURNED, FAILED, RECOVERED)


def _f(value, source, why=None, **extra) -> dict:
    out = {"value": value, "source": source}
    if why:
        out["why"] = why
    out.update(extra)
    return out


def _alias(cv, pid):
    return cv.alias(pid) if pid else None


def _delegated_children(cv, expectation) -> set:
    """Expectations handed down from this one by a recorded delegation."""
    return {a["about"][0] for a in cv.history(caused_by=expectation)
            if a["act"] == "work-delegated" and a["about"]}


def is_trunk(cv, act) -> bool:
    """Whether this expectation heads its own piece of work.

    Not a decision or an input (those are asked OF somebody under a piece of
    work, and are shown where they were asked). Not a child somebody
    delegated -- its parent's roll-up carries it -- unless it has delegated work of its own, which makes
    it a trunk in its own right.
    """
    if act["act"] != "expectation-recorded":
        return False
    if (act.get("detail") or {}).get("expects") in ASKED_UNDER_WORK:
        return False
    parent = act.get("caused_by")
    if parent and act["id"] in _delegated_children(cv, parent):
        return bool(_delegated_children(cv, act["id"]))
    return True


class _Seq:
    """The record's own write order (`seq`) for any act, looked up by id.

    EVERY "latest" in this module sorts by it, so two acts written in one tick
    of the clock -- or a later act stamped earlier by a clock step -- are
    ordered as they were written. It covers every act, wherever it was
    recorded: an earlier version used positions within one Conversation and
    put anything recorded outside it last, which inverted the order."""

    def __init__(self, cv):
        self._cv, self._seq = cv, {}

    def prime(self, acts):
        want = [a["id"] for a in acts if a and a["id"] not in self._seq]
        if want:
            # through the Conversation, so a reading that already read these
            # acts' write order answers it from there (`_write_order`)
            self._seq.update(self._cv._write_order(want))
        return self

    def key(self, a):
        if a["id"] not in self._seq:
            self.prime([a])
        # an act the store does not hold cannot be placed; it sorts first,
        # so it never displaces an act the record does place
        return (self._seq.get(a["id"], -1), a["at"])


def _pos(order):
    """Sort key over write order (see `_Seq`)."""
    return order.key


def _persona(cv, expectation, order):
    """The Persona the record names for whoever carries this, or None.

    Read from the acts that put a carrier on it -- an assignment or the
    delegation that created it -- and never inferred from a Participant, a
    runtime or a name. None is shown as "no Persona".
    """
    # AN ASSIGNMENT THAT NAMES NOBODY PUT NO CARRIER ON IT: a Workflow change
    # (`workflow_change`) is recorded that way, and must not read as a
    # reassignment with no Persona.
    acts = [a for a in cv.history(caused_by=expectation)
            if a["act"] == "expectation-assigned" and a.get("about")]
    exp = cv._act(expectation)
    if exp and exp.get("caused_by"):
        acts += [a for a in cv.history(caused_by=exp["caused_by"])
                 if a["act"] == "work-delegated"
                 and expectation in (a["about"] or ())]
    acts.sort(key=_pos(order))
    # THE LATEST ACT THAT PUT A CARRIER ON IT DECIDES, including when it named
    # no Persona: a reassignment without one is "no Persona", never the
    # previous carrier's Persona carried over.
    return (acts[-1].get("detail") or {}).get("persona") if acts else None


def _activity(cv, expectation, order):
    """The Workflow activity the record says this work is for, or None.

    The newest assignment that names one (a pick-up of discovered work says
    it there), else the request's own record (a delegation says it there).
    """
    acts = sorted((a for a in cv.history(caused_by=expectation)
                   if a["act"] == "expectation-assigned"
                   and "activity" in (a.get("detail") or {})),
                  key=_pos(order))
    if acts:
        return acts[-1]["detail"]["activity"]
    return ((cv._act(expectation) or {}).get("detail") or {}).get("activity")


def _named(cv, ref):
    """What a reference is called, for a reader; None when not held."""
    got = cv.corpus.read([ref]) if isinstance(ref, str) and ref else []
    if not got:
        return None
    if (got[0].get("definition") or {}).get("name") == "participant":
        return cv.alias(ref)                  # its CURRENT alias
    body = got[0].get("body") or {}
    return body.get("alias") or body.get("name") or None


def _discipline(cv, ref):
    """An activity's Discipline as it would reach a child now: the current
    version of what the procedure pins, by name, and why not if it does not
    stand."""
    from mentis.conversation import current_of
    cur = current_of(cv.corpus, ref)
    return {"entry": cur["entry"] or ref, "name": _named(cv, cur["entry"] or ref),
            "stands": cur["stands"], "why": cur["why"],
            **({"pinned": ref} if cur["entry"] != ref else {})}


def _workflows(cv, expectation, exp, persona, kids, decisions, order):
    """Each Workflow governing this request, its activities with the children
    whose recorded `activity` names them, and the decisions asked under it.

    COMPUTED FROM THE RECORD AND NOTHING ELSE. Which Workflows govern is the
    question dispatch asks (`Conversations.governing_now`, over what the
    request names, `governed_named`); a child belongs to an activity because
    its delegation said so, matched against this version of the Workflow or
    any earlier one in its line; an activity no child names says "nothing
    delegated for it" -- which is all the record can say, since an activity
    the carrier does itself is never delegated. There is no current activity, no next one and no stored position:
    which activities have work, and in what state, is all this says.
    """
    from mentis.conversation import (ROW_GROUP, activities_of,
                                     fields_with_input)
    from mentis.conversation.versions import flow_text
    conversation = exp.get("conversation")
    memo = order.__dict__.setdefault("_governing", {})
    key = (conversation, persona)
    if key not in memo:
        memo[key] = cv.governing_now(conversation, (), persona)
    named = [e for e in cv.governed_named(expectation)
             if cv.corpus.read([e]) and cv.corpus.stands(e)["stands"]]
    # WORKFLOWS THE REQUEST WAS GOVERNED BY BEFORE A CHANGE
    # (`workflow_change`): kept here while children were delegated under
    # their activities, so a change never hides work already handed out.
    # Marked `former`; one with no child under it is not shown.
    earlier = _earlier_workflows(cv, expectation, exp)
    ids = list(dict.fromkeys([*named, *sorted(memo[key]), *earlier]))
    out = []
    # The same governing material and the same Kinds are asked about for
    # every trunk in a Conversation; once per reading (`Conversations._recall`)
    # rather than once per trunk, and exactly the same reads outside one.
    for e in cv._recall(("read", tuple(ids)), lambda: cv.corpus.read(ids)):
        kind = (e.get("definition") or {}).get("name")
        if not cv._recall(("fields_with_input", kind, ROW_GROUP),
                          lambda: fields_with_input(cv.corpus, kind,
                                                    ROW_GROUP)):
            continue
        line = set(cv.corpus.history(e["id"]) or ()) | {e["id"]}
        mine = [k for k in kids if k.get("activity")
                and k["activity"].split("#")[0] in line]
        former = e["id"] in earlier and e["id"] not in named \
            and e["id"] not in memo[key]
        if former and not mine:
            continue
        body = e.get("body") or {}
        rows = []
        for row in activities_of(cv.corpus, e):
            on = [{"expectation": k["expectation"],
                   "carrier_alias": k["carrier_alias"], "state": k["state"],
                   "source": k["source"], "number": k["number"],
                   "turn": k["turn"]}
                  for k in mine if k["activity"].split("#", 1)[1] == row["key"]]
            who = row.get("who") or {}
            rows.append({
                "key": row["key"], "what": row.get("what") or "",
                "who": {**who,
                        **({"persona_name": _named(cv, who["persona"])}
                           if who.get("persona") else {}),
                        **({"participant_alias": _named(cv, who["participant"])}
                           if who.get("participant") else {})},
                "disciplines": [_discipline(cv, d)
                                for d in row.get("disciplines") or ()],
                "done_when": row.get("done_when") or "",
                "coordinates": bool(row.get("coordinates")),
                "children": on,
                "said": None if on else "nothing delegated for it"})
        asked = []
        for d in decisions:
            a = cv._act(d["expectation"]) or {}
            # A QUESTION OF A DECISION FORM (P7/P9) carries its own words,
            # and is on the form's post -- or none yet.
            question = (a.get("detail") or {}).get("question")
            turn = cv.asked_on(a) if a else None
            got = cv.corpus.read([turn]) if turn and not question else []
            asked.append({
                "expectation": d["expectation"], "answered": d["answered"],
                "owed_by_alias": _alias(cv, d["owed_by"]), "turn": turn,
                "number": cv.turn_number(turn) if turn else None,
                "text": (question[:200] if question else
                         flow_text((got[0].get("body") or {}).get("parts"))[:200]
                         if got else "")})
        out.append({
            "entry": e["id"], "name": body.get("name") or "",
            "about": body.get("about") or "",
            "activities": rows,
            "decisions": [x for x in body.get("decisions") or ()
                          if isinstance(x, str)],
            "asked": asked,
            "done_when": body.get("done_when") or "",
            "elsewhere": len([k for k in kids if k not in mine]),
            **({"former": True} if former else {})})
    return out


def _earlier_workflows(cv, expectation, exp) -> list[str]:
    """Workflows this request named before its latest Workflow change: what
    it was asked with and what each change replaced. Read from the record."""
    from mentis.conversation.workflow_change import CHANGE, workflows_of
    out = list(workflows_of(cv, (exp.get("detail") or {}).get("governed")
                            or ()))
    for a in cv.history(caused_by=expectation):
        if a["act"] == "expectation-assigned" and CHANGE in (a.get("detail")
                                                              or {}):
            out += [w for w in a["detail"][CHANGE].get("from") or ()]
    current = set(cv.governed_named(expectation))
    return [w for w in dict.fromkeys(out) if w not in current]


def _order(cv, conversation=None) -> "_Seq":
    """A write-order lookup (see `_Seq`). `conversation` is not needed any
    more and is accepted so older callers keep working."""
    return _Seq(cv)


def _runs(own, runtime, order):
    """Runs of this request: which are open by the record, and what this
    process observes of them now."""
    pos = _pos(order)
    started = [a for a in own if a["act"] == STARTED and a.get("execution")]
    ends = [a for a in own
            if a["act"] in ENDS and a.get("execution")]
    last_end = max(ends, key=pos) if ends else None
    # A RUN STARTED BEFORE A LATER RUN ENDED IS SUPERSEDED, not open: an
    # orphaned earlier start (its process died, nothing recorded its end) must
    # not hide that a later run returned. It is kept, as `orphaned`.
    # ENDED BY ITS OWN START, not by execution id (see `closed_starts`).
    done = closed_starts(started + ends, pos)
    unended = [a for a in started if a["id"] not in done]
    instances = runtime.get("instances")
    live = (lambda a: instances.get(a["execution"]) in _LIVE) \
        if instances is not None else (lambda a: False)
    # ...UNLESS THIS PROCESS OBSERVES IT RUNNING. An observed run is open
    # whatever ended around it: overlapping runs of one request are rare, but
    # filing a live one as orphaned would hide the one thing that is moving.
    open_ = [a for a in unended
             if last_end is None or pos(a) > pos(last_end) or live(a)]
    orphaned = [a for a in unended if a not in open_]
    observed = None
    if instances is not None:
        observed = [a["execution"] for a in open_ if live(a)]
    return open_, orphaned, observed


def _child_view(cv, expectation, runtime, order=None):
    """A child's state as it may be SHOWN, with its source.

    `_child_state` is the record's own word and drives `waiting_on` and
    `claim_resumption`; it is not changed. But it calls a child "running"
    whenever a run is recorded as started and not ended -- which is also what
    a run whose process died looks like. So here "running" is said only when
    this process observes the run; otherwise it is "started-no-end", recorded.
    """
    c = cv._child_state(expectation)
    view = {"last_end": None, "hold": None}
    if c["state"] == "not-ended":
        return c, c["state"], RECORDED, view
    # `_child_state` orders by `at` and calls a child running whenever some
    # start has no end. What is SHOWN is re-derived from the runs in write
    # order; its word stays beside it as `record_state`.
    own = cv._own_acts(expectation)
    order.prime(own)
    ends = [a for a in own if a["act"] in ENDS]
    last = max(ends, key=_pos(order)) if ends else None
    view["last_end"] = last
    if c["state"] != "running":
        return c, (_ended_word(last) if last else c["state"]), RECORDED, view
    open_, orphaned, observed = _runs(own, runtime, order)
    if observed:
        return c, "running", RUNTIME, view
    # an in-process handle that NAMES this child is also an observation
    if any(e.for_expectation == expectation for e in cv.active_executions()):
        return c, "running", RUNTIME, view
    if open_:
        return c, "started-no-end", RECORDED, view
    # The record calls it running, and nothing open or observed says so. WHY
    # the record says it decides what can be said about resuming:
    #   orphan          a start with no end, before a later end
    #   unnamed-handle  a live execution of its carrier in this Conversation
    #                   that names no request (`expectation_state`'s third
    #                   source); nothing in the runs is open
    view["hold"] = "orphan" if orphaned else "unnamed-handle"
    return c, (_ended_word(last) if last else "not-ended"), RECORDED, view


def _ended_word(last) -> str:
    """How a run's end act says it ended, in `_child_state`'s own words."""
    if last["act"] == RETURNED:
        return "returned"
    if last["act"] == RECOVERED:
        return "recovered"
    d = last.get("detail") or {}
    return d.get("terminal") or ("failed-before-start"
                                 if d.get("before_execution_started")
                                 else "failed")


def trunk_status(cv, expectation, *, viewer=None, runtime=None, now=None,
                 order=None) -> dict:
    """STATE, CARRIER, CHILDREN, YOU OWE, NEXT and LAST RECORDED ACT for one
    piece of work, each with its source.

    `viewer` is the Participant asking. None means nobody said who is looking,
    and then what they owe is UNKNOWN rather than nothing.

    `runtime` is `{"instances": {execution_id: liveness}}` as this process
    observes it, or `{"instances": None, "why_not": ...}` when it could not be
    asked. It is the only non-durable input, and it only ever qualifies a run
    the record already says was started.
    """
    runtime = runtime or {"instances": None,
                          "why_not": "no runtime observation was supplied"}
    s = cv.expectation_state(expectation)
    exp = cv._act(expectation)
    own = cv._own_acts(expectation)
    if not isinstance(order, _Seq):
        order = _Seq(cv)
    everything = [exp] + cv._descendants(expectation)
    order.prime(everything)
    carrier = s["expected_of"]
    carrier_alias = _alias(cv, carrier)

    # -- children ----------------------------------------------------------
    waiting = cv.waiting_on(expectation)
    required = {c["expectation"] for c in waiting["required"]}
    kids = []
    for d in s["delegations"]:
        if not d["expectation"]:
            continue
        c, shown_state, source, view = _child_view(cv, d["expectation"],
                                                   runtime, order)
        shown_end = view["last_end"]
        child_exp = cv._act(d["expectation"])
        kids.append({
            "expectation": c["expectation"],
            "carrier": c["carrier"], "carrier_alias": _alias(cv, c["carrier"]),
            "persona": _persona(cv, d["expectation"], order),
            # WHICH WORKFLOW ACTIVITY THE DELEGATION SAID THIS IS FOR, as
            # recorded; None where it named none. A label, never a position.
            "activity": _activity(cv, d["expectation"], order),
            "state": shown_state,
            "source": source,
            # the record's own word, which `claim_resumption` reads
            "record_state": c["state"],
            "required": c["expectation"] in required,
            "turn": child_exp["turn"] if child_exp else None,
            "number": (cv.turn_number(child_exp["turn"])
                       if child_exp and child_exp.get("turn") else None),
            # FROM THE SAME RUN AS THE SHOWN STATE: the end act that write
            # order picked, not `_child_state`'s (which orders by `at`)
            "ended_at": shown_end["at"] if shown_end else c["ended_at"],
            "because": (shown_end.get("because") if shown_end
                        else c["because"]),
            # why the record still holds it, if it does and nothing open
            # or observed says so: "orphan" or "unnamed-handle"
            "hold": view["hold"],
            # the child's newest act, its own record included: a hold is
            # measured from here
            "last_act_key": max(order.key(a) for a in
                                [child_exp] + cv._own_acts(d["expectation"])
                                if a),
            "claimed_met": bool(c["claimed_met_by"]),
        })
    counts, count_sources = {}, {}
    for k in kids:
        counts[k["state"]] = counts.get(k["state"], 0) + 1
        count_sources[k["state"]] = k["source"]

    # -- what the viewer owes, anywhere under this work ---------------------
    owed_rows = []
    if viewer is not None:
        for a in everything:
            if a["act"] != "expectation-recorded":
                continue
            st = s if a["id"] == expectation else cv.expectation_state(a["id"])
            if st["expected_of"] != viewer or st["response_present"]:
                continue
            owed_rows.append({
                "expectation": a["id"], "expects": st["expects"],
                "turn": a["turn"],
                "number": cv.turn_number(a["turn"]) if a["turn"] else None,
                "conversation": a["conversation"],
                "asked_by": st["requested_by"],
                "asked_by_alias": _alias(cv, st["requested_by"]),
                "because": st["because"],
                "options": len(st["options"] or ()),
                "at": a["at"]})
    you_owe = (_f(None, UNKNOWN, "nobody said who is looking, so what they "
                                 "owe cannot be said")
               if viewer is None else
               _f(owed_rows, COMPUTED,
                  "expectations under this work whose current carrier is you "
                  "and that nobody has answered"))

    # -- runs ---------------------------------------------------------------
    pos = _pos(order)
    open_runs, orphaned_runs, observed = _runs(own, runtime, order)
    starts = [a for a in own if a["act"] == STARTED]
    last_run = max(starts, key=pos) if starts else None
    # THE RUNTIME SHOWN UNDER THE CARRIER IS THAT CARRIER'S. After a
    # reassignment the previous carrier's last run says nothing about who
    # carries it now.
    carrier_runs = [a for a in starts if a["actor"] == carrier]
    carrier_run = (max(carrier_runs, key=pos) if carrier_runs else None)
    ends = [a for a in own if a["act"] in ENDS]
    last_end = max(ends, key=pos) if ends else None
    resumed = [a for a in own if a["act"] == "work-resumed"]
    last_resumed = max(resumed, key=pos) if resumed else None

    # -- continuations: this work running under another request ------------
    # A CONTINUATION IS THIS WORK RUNNING (`continuations_of`), and while it
    # runs, or is dispatched and not yet started (`continuation_pending`),
    # `claim_resumption` resumes nothing here. Read from the same two
    # questions, so the status cannot promise a resume that will not happen.
    continuations = []
    for c in cv.continuations_of(expectation):
        cs = cv.expectation_state(c)
        ca = cv._act(c)
        if cs["live_execution"]:
            word = "running"
        elif cv.continuation_pending(c):
            word = "dispatched"
        else:
            word = cv._child_state(c)["state"]
        continuations.append({
            "expectation": c, "state": word,
            "carrier": cs["expected_of"],
            "carrier_alias": _alias(cv, cs["expected_of"]),
            "number": (cv.turn_number(ca["turn"])
                       if ca and ca.get("turn") else None)})
    continuing = [c for c in continuations
                  if c["state"] in ("running", "dispatched")]

    def _continuation_name(c):
        return ("its continuation"
                + (f" (Turn #{c['number']})" if c["number"] else "")
                + (f", carried by {c['carrier_alias']}"
                   if c["carrier_alias"] else ""))

    # by the RECORD's word, because that is what `claim_resumption` reads
    held = [k for k in kids if k["required"]
            and k["record_state"] in ("running", "not-ended")]
    # ...but only those the runs also show as not ended are WAITED ON. A child
    # the record still counts as running only because an earlier run of it has
    # no end -- while a later run ended -- has come back; it is not awaited,
    # and it will nonetheless keep `claim_resumption` from firing.
    # A CHILD THE RECORD HOLDS WITH NOTHING OPEN OR OBSERVED TO SHOW FOR IT
    # (an orphaned run, or an unnamed live execution of its carrier) keeps
    # `claim_resumption` from firing whatever else happens. It is not waited
    # on, and while it holds, no resumption is promised for anybody.
    holding = [k for k in held if k["hold"]]
    # still out by what its runs show, held or not: a hold removes the
    # PROMISE of resumption, never the fact that the child is not back
    outstanding_children = [k for k in held if k["state"] in
                            ("running", "started-no-end", "not-ended")]
    # "Not resumed" only while NOTHING of the parent's has run or resumed
    # since the holding child's last act: once the parent runs, is resumed,
    # returns or fails, that is its state, and it shows.
    since = max((k["last_act_key"] for k in holding
                 if k["last_act_key"] is not None), default=None)
    parent_moved = since is not None and any(
        order.key(a) > since for a in own
        if a["act"] in (STARTED, "work-resumed", *ENDS))
    # "Not resumed" is about a child that has COME BACK and still holds the
    # parent; one that is still out is "waiting on a child"
    held_by_orphan = [] if parent_moved else [
        k for k in holding if k not in outstanding_children]

    def _hold_reason(ks):
        causes = sorted({k["hold"] for k in ks})
        names = " and ".join(sorted({k["carrier_alias"] or "a child"
                                     for k in ks}))
        out = []
        if "orphan" in causes:
            out.append(f"the record still counts an earlier run of {names} "
                       f"as open (no end recorded)")
        if "unnamed-handle" in causes:
            out.append(f"the record counts {names} as running because a live "
                       f"execution of theirs in this Conversation names no "
                       f"request")
        return "; ".join(out)
    # A RECOVERED CHILD HOLDS THIS WORK: nothing ending resumes it until
    # somebody continues it. The SAME rule `claim_resumption` refuses on, read
    # from the same place, so the status cannot promise what will not happen.
    by_recovery = cv.recovery_hold(expectation, waiting=waiting, own=own)
    recovered_names = " and ".join(sorted(
        {_alias(cv, c["carrier"]) or "a child" for c in by_recovery}))
    # AN INTERRUPTED CHILD OR AWAITED RUN HOLDS IT THE SAME WAY, by the same
    # rule `claim_resumption` refuses on. This work's own interrupted run is
    # shown by its own last end, not here.
    by_interruption = [c for c in cv.interruption_hold(
        expectation, waiting=waiting, own=own)
        if c["expectation"] != expectation]
    interrupted_names = " and ".join(sorted(
        {_alias(cv, c.get("carrier")) or "a child" for c in by_interruption}))
    held_by_person = " and ".join(
        ([f"the result of {recovered_names} came back by recovery"]
         if by_recovery else [])
        + ([f"the run of {interrupted_names} was interrupted"]
           if by_interruption else []))
    # DECISIONS THIS WORK ASKED DIRECTLY, still unanswered, whoever owes them:
    # these hold `claim_resumption` exactly as outstanding children do.
    open_decisions = [d for d in waiting["decisions"] if not d["answered"]]
    others_decisions = [d for d in open_decisions if d["owed_by"] != viewer]
    # OTHER WORK IT DECLARED IT WAITS ON (`await_work`), not yet ended:
    # these hold `claim_resumption` exactly as outstanding children do.
    awaits = []
    for w in waiting["awaited"]:
        a = cv._act(w["expectation"])
        awaits.append({
            **w, "carrier_alias": _alias(cv, w["carrier"]),
            "claimed_by_alias": [_alias(cv, c) for c in w["claimed_by"]],
            "number": (cv.turn_number(a["turn"])
                       if a and a.get("turn") else None)})
    open_awaits = [w for w in awaits if not w["ended"]]

    def _work_name(w):
        return ((w["carrier_alias"] or "unassigned") + "'s work"
                + (f" (Turn #{w['number']})" if w["number"] else ""))

    # -- state: the first of these the record supports --------------------
    if s["satisfied_by"]:
        claimers = sorted({a["actor"] for a in own
                           if a["act"] == "expectation-met"})
        state = _f("claimed-met", RECORDED,
                   "somebody recorded that this is met. That is their claim, "
                   "not a check of the work",
                   label="Claimed met" + (
                       " by " + ", ".join(_alias(cv, c) for c in claimers)
                       if claimers else ""))
    elif open_runs and observed:
        state = _f("running", RUNTIME,
                   "a run recorded as started has no end recorded, and this "
                   "server observes it in progress now",
                   label="Running")
    elif open_runs:
        state = _f("started-no-end", RECORDED,
                   "a run was recorded as started and nothing has recorded "
                   "its end. " + (
                       "This server does not observe it running, which may "
                       "only mean another process started it"
                       if observed is not None else
                       "What is running could not be asked: "
                       + str(runtime.get("why_not"))),
                   label="Started · no end recorded")
    elif continuing:
        c = continuing[0]
        state = _f("continuing", COMPUTED,
                   _continuation_name(c) + " is "
                   + ("running" if c["state"] == "running" else
                      "dispatched and has not started")
                   + ". That is this work running, so it is held by it: "
                   "nothing that ends here meanwhile resumes it, and the "
                   "continuation runs on what came back",
                   label=("Held by its continuation · running"
                          if c["state"] == "running" else
                          "Held by its continuation · dispatched, not "
                          "started"))
    elif owed_rows:
        decision = any(r["expects"] == "decision" for r in owed_rows)
        state = _f("waiting-on-you", COMPUTED,
                   "an expectation under this work is carried by you and "
                   "unanswered",
                   label="Waiting on your decision" if decision
                   else "Waiting on you")
    elif others_decisions:
        who = sorted({_alias(cv, d["owed_by"]) or "nobody"
                      for d in others_decisions})
        state = _f("waiting-on-decision", COMPUTED,
                   "a decision this work asked is unanswered, and it is not "
                   "yours",
                   label="Waiting on " + " and ".join(
                       f"{w}'s decision" for w in who))
    elif outstanding_children:
        state = _f("waiting-on-child", COMPUTED,
                   "a child this work declared it needs back has not ended",
                   label="Waiting on "
                   + ("a child" if len(outstanding_children) == 1
                      else f"{len(outstanding_children)} children"))
    elif open_awaits:
        state = _f("waiting-on-work", COMPUTED,
                   "other work this work declared it waits on has not "
                   "ended: not claimed met, nor -- for delegated work -- "
                   "had its run end",
                   label="Waiting on "
                   + (_work_name(open_awaits[0]) if len(open_awaits) == 1
                      else f"{len(open_awaits)} other pieces of work"))
    elif held_by_orphan:
        orphan = any(k["hold"] == "orphan" for k in held_by_orphan)
        state = _f("not-resumed", COMPUTED,
                   "no child it needs back is still out, but "
                   + _hold_reason(held_by_orphan)
                   + ", so resumption does not happen by itself, and nothing "
                   "of this work has run or resumed since",
                   label=("Not resumed · an earlier child run has no end "
                          "recorded" if orphan else
                          "Not resumed · a child is held by an unnamed run"))
    elif s["unassigned"]:
        state = _f("unassigned", RECORDED,
                   "owed, and no act assigns anybody to carry it",
                   label="Unassigned")
    elif (by_recovery or by_interruption) and not open_decisions:
        state = _f("resumable-not-resumed", COMPUTED,
                   "nothing it waits on is outstanding, and "
                   f"{held_by_person} after this work last started or "
                   "resumed. A recovered result or an interrupted run "
                   "resumes no work, whatever else ends here, until somebody "
                   "continues it",
                   label="Resumable · not resumed")
    elif last_resumed and (last_run is None
                           or pos(last_resumed) > pos(last_run)):
        state = _f("resumed-no-run", RECORDED,
                   "resumption was recorded and no run has been recorded "
                   "since. Resumed is not satisfied",
                   label="Resumed · no run since")
    elif last_end and last_end["act"] == FAILED:
        state = _f("failed", RECORDED,
                   last_end.get("because") or "its last run failed",
                   label="Failed")
    elif last_end and last_end["act"] == RECOVERED:
        # ONLY WHAT THE RECORD HOLDS. That nothing observed the end, who
        # recorded the recovery, and that the server read the final message
        # from the runtime's transcript are recorded; WHY the end was lost is
        # the recoverer's account and is attributed to them, not asserted.
        state = _f("recovered", RECORDED,
                   "nothing in Mentis observed its last run end. "
                   + (_alias(cv, last_end["actor"]) or "Somebody")
                   + " recorded it as recovered, and the server read the "
                   "run's final message from the runtime's transcript when "
                   "that was recorded"
                   + (f" ({_alias(cv, last_end['actor']) or 'their'} account "
                      f"of why: {last_end['because']})"
                      if last_end.get("because") else "")
                   + ". Recovered is not the same as adequate",
                   label="Recovered · end not observed")
    elif last_end:
        state = _f("returned", RECORDED,
                   "its last run returned a result. Returned is not "
                   "the same as adequate",
                   label="Returned")
    elif s["response_present"]:
        state = _f("replied", RECORDED,
                   "the carrier replied; nothing claims it is met",
                   label="Replied")
    else:
        state = _f("owed", RECORDED,
                   "recorded as owed; nothing has started for it",
                   label="Owed · nothing started")

    # -- next: only a transition this code can name -----------------------
    v = state["value"]
    names = sorted({k["carrier_alias"] or "an unassigned child"
                    for k in outstanding_children})
    returns = (" and ".join(names) + " "
               + ("returns" if len(outstanding_children) == 1 else "return"))
    deciders = sorted({"you" if d["owed_by"] == viewer
                       else (_alias(cv, d["owed_by"]) or "nobody")
                       for d in open_decisions})
    rule = ("work resumes, by `claim_resumption`, when a child it needs back "
            "ends or other work it awaits ends -- claimed met, or, for work "
            "delegated to be handed back, its run ending -- and nothing it "
            "declared is outstanding -- children, awaited work or decisions. "
            "Answering a decision alone resumes nothing")
    waiting_states = ("waiting-on-you", "waiting-on-decision",
                      "waiting-on-child", "waiting-on-work")

    def _ends(w):
        # what ends the wait on this piece of awaited work, by `awaited_state`
        detail = (cv._act(w["expectation"]) or {}).get("detail") or {}
        return " hands back" if detail.get("returns_to") else " is claimed met"

    def _awaited_end(ws):
        return " and ".join(_work_name(w) + _ends(w) for w in ws)
    # what else must happen besides the headline, said so no promise is short
    also = (" once " + _awaited_end(open_awaits) if open_awaits else "")
    if holding and v in waiting_states:
        # NOTHING IS PROMISED WHILE A HOLD EXISTS: whatever else returns or is
        # answered, `claim_resumption` still counts the held child as live.
        nxt = _f(None, UNKNOWN,
                 _hold_reason(holding) + ", so this work will not resume by "
                 "itself even when "
                 + ("everything else it waits for ends" if (
                     outstanding_children or open_decisions or open_awaits)
                    else "nothing else is outstanding")
                 + "; continuing it is somebody's act")
    elif (by_recovery or by_interruption) and v in waiting_states:
        # NOR WHILE A RECOVERED RESULT OR AN INTERRUPTED RUN HOLDS IT:
        # `claim_resumption` refuses.
        nxt = _f(None, UNKNOWN,
                 f"{held_by_person} after "
                 "this work last started or resumed, so it will not resume by "
                 "itself even when everything else it waits for ends; "
                 "continuing it is somebody's act")
    elif v in waiting_states:
        if outstanding_children and open_decisions:
            # BOTH HOLD IT. A child returning while a decision is still open
            # resumes nothing, so neither is promised alone.
            verb = ("answer" if len(deciders) > 1 or deciders == ["you"]
                    else "answers")
            nxt = _f(f"Resumes when {returns}, once "
                     + " and ".join(deciders) + f" {verb} the decision asked"
                     + (("," + also) if also else ""),
                     COMPUTED, rule)
        elif outstanding_children:
            nxt = _f(f"Resumes when {returns}" + also, COMPUTED, rule)
        elif v == "waiting-on-work":
            nxt = _f("Resumes when " + _awaited_end(open_awaits) + (
                         ", once " + " and ".join(deciders)
                         + (" answer" if len(deciders) > 1
                            or deciders == ["you"] else " answers")
                         + " the decision asked"
                         if open_decisions else ""),
                     COMPUTED,
                     rule + ". A run of other awaited work ending is not it "
                            "being claimed met, and resumes nothing; a run of "
                            "awaited delegated work ending -- even to pause "
                            "for its own children -- ends the wait, unless it "
                            "was recovered or interrupted, which holds it "
                            "for somebody to continue")
        elif v == "waiting-on-you":
            nxt = _f("Waiting for your decision" if state["label"].endswith(
                         "decision") else "Waiting for your answer", COMPUTED,
                     "nothing under this work moves on that until you answer "
                     "it; answering records, and only Decide + continue "
                     "hands the work back")
        else:
            nxt = _f("Waiting for " + " and ".join(
                         f"{w}'s decision" for w in deciders), COMPUTED,
                     "a decision this work asked is unanswered; answering it "
                     "alone resumes nothing unless a child it needs back "
                     "also ends")
    elif v == "running":
        nxt = _f(f"{carrier_alias or 'The run'} records a result or a failure "
                 "when this run ends", COMPUTED,
                 "every run this server started ends in one of those two acts")
    elif v == "continuing":
        c = continuing[0]
        who = c["carrier_alias"] or "The continuation"
        nxt = _f((f"{who} records a result or a failure when the "
                  "continuation's run ends"
                  if c["state"] == "running" else
                  f"The continuation's run starts for {who}, or, if this "
                  "server stops first, the next server start closes it as "
                  "dispatch-lost"),
                 COMPUTED,
                 "while a continuation runs or is dispatched, nothing ending "
                 "here resumes this work; after it ends, this work resumes by "
                 "`claim_resumption` when something it waits on ends after "
                 "the continuation started and nothing it declared is "
                 "outstanding")
    else:
        why = {
            "started-no-end": "nothing this server observes will end that "
                              "run, so what is recorded next cannot be said",
            "unassigned": "nobody carries it; it waits for a carrier to be "
                          "designated, which is a person's act",
            "resumed-no-run": "resumption was recorded but no run followed",
            "claimed-met": "nothing further is scheduled in the record",
            "returned": "nothing further is scheduled in the record; "
                        "whether the result is adequate is a judgement",
            "recovered": "nothing further is scheduled in the record; "
                         "whether the result is adequate is a judgement",
            "failed": "nothing in the record schedules a retry",
            "replied": "nothing further is scheduled in the record",
            "owed": "nothing has been dispatched for it",
            "resumable-not-resumed": "a recovered result or an interrupted "
                                     "run resumes nothing; continuing this "
                                     "work is somebody's act",
            "not-resumed": (_hold_reason(holding) if holding else
                            "a child is held") + ", so the record will not "
                           "resume it by itself; continuing it is "
                           "somebody's act",
        }.get(v, "the record does not say")
        nxt = _f(None, UNKNOWN, why)

    # -- last recorded act -------------------------------------------------
    last = max(everything, key=pos)
    last_act = _f({"at": last["at"], "act": last["act"],
                   "actor": last["actor"], "actor_alias": _alias(cv, last["actor"]),
                   "id": last["id"]}, RECORDED,
                  "the newest act anywhere under this work. Its age is an "
                  "age, not a measure of progress")

    # -- carrier: Participant, Persona and runtime kept apart --------------
    assigned = s["assigned"]
    persona = _persona(cv, expectation, order)
    live_runtime = None
    if open_runs:
        live_runtime = _f(
            {"observed": observed,
             "liveness": {a["execution"]: runtime["instances"].get(
                 a["execution"], "not observed")
                 for a in open_runs} if runtime.get("instances") is not None
             else None},
            RUNTIME if runtime.get("instances") is not None else UNKNOWN,
            None if runtime.get("instances") is not None
            else runtime.get("why_not"))
    carrier_f = _f(
        {"participant": carrier, "alias": carrier_alias,
         "assigned_by": assigned["by"],
         "assigned_by_alias": _alias(cv, assigned["by"]),
         "by_assignment_act": bool(assigned["assignment"])},
        RECORDED if carrier else COMPUTED,
        None if carrier else "no act assigns anybody to carry this",
        persona=_f(persona, RECORDED if persona else UNKNOWN,
                   None if persona else "no act names a Persona for this "
                                        "carrier; none is inferred"),
        runtime=_f(carrier_run.get("runtime") if carrier_run else None,
                   RECORDED if carrier_run else UNKNOWN,
                   None if carrier_run else (
                       "no run of this work by its current carrier is recorded"
                       + ("; an earlier carrier's run is" if last_run else "")),
                   execution=carrier_run.get("execution") if carrier_run else None,
                   at=carrier_run["at"] if carrier_run else None),
        live=live_runtime,
        orphaned=[{"execution": a["execution"], "at": a["at"]}
                  for a in orphaned_runs])

    shown = sorted(kids, key=lambda k: (not k["required"], k["number"] or 0))
    # ONE BLOCK THAT CANNOT BE READ DOES NOT MAKE THE WHOLE TRUNK UNKNOWN:
    # the rest of the status stands on its own, and this says why it is not.
    try:
        workflow = _f(_workflows(cv, expectation, exp, persona, kids,
                                 waiting["decisions"], order), COMPUTED,
                      "computed from the record on every read: each activity "
                      "of a Workflow governing this request, with the "
                      "delegations that named it and their states, and the "
                      "decisions asked under the work. Nothing is stored and "
                      "nothing here moves the work on")
    except Exception as exc:                              # noqa: BLE001
        workflow = _f([], UNKNOWN, f"the Workflow progress could not be read: "
                                   f"{type(exc).__name__}: {exc}")
    return {
        "expectation": expectation,
        "turn": exp["turn"],
        "number": cv.turn_number(exp["turn"]) if exp.get("turn") else None,
        "conversation": exp["conversation"],
        "expects": s["expects"],
        "requested_by": s["requested_by"],
        "requested_by_alias": _alias(cv, s["requested_by"]),
        "state": state,
        "carrier": carrier_f,
        "children": _f({"counts": counts, "count_sources": count_sources,
                        "total": len(kids),
                        "items": shown[:CHILDREN_SHOWN],
                        "omitted": max(0, len(kids) - CHILDREN_SHOWN),
                        "decisions": [
                            {**d, "owed_by_alias": _alias(cv, d["owed_by"])}
                            for d in waiting["decisions"]],
                        # other work it declared it waits on, and whether
                        # each is claimed met, or has ended, yet
                        "awaits": awaits,
                        # the requests that continue it, and how each stands:
                        # running, dispatched, or how its last run ended
                        "continuations": continuations},
                       COMPUTED,
                       "each count says its source: running is observed by "
                       "this server now (runtime); started-no-end, not-ended, "
                       "returned, recovered and failed are the record's"),
        "you_owe": you_owe,
        "next": nxt,
        "last_act": last_act,
        "workflow": workflow,
    }


def _unreadable(cv, act, exc) -> dict:
    """A trunk whose status could not be computed, said as exactly that."""
    why = f"this work's status could not be read: {type(exc).__name__}: {exc}"
    u = _f(None, UNKNOWN, why)
    return {
        "expectation": act["id"], "turn": act.get("turn"),
        "number": cv.turn_number(act["turn"]) if act.get("turn") else None,
        "conversation": act.get("conversation"),
        "expects": (act.get("detail") or {}).get("expects"),
        "requested_by": act.get("actor"),
        "requested_by_alias": _alias(cv, act.get("actor")),
        "state": _f("unreadable", UNKNOWN, why, label="UNKNOWN · could not be read"),
        "carrier": _f({"participant": None, "alias": None, "assigned_by": None,
                       "assigned_by_alias": None, "by_assignment_act": False},
                      UNKNOWN, why, persona=_f(None, UNKNOWN, why),
                      runtime=_f(None, UNKNOWN, why, execution=None, at=None),
                      live=None, orphaned=[]),
        "children": _f({"counts": {}, "count_sources": {}, "total": 0,
                        "items": [], "omitted": 0, "decisions": [],
                        "awaits": [], "continuations": []},
                       UNKNOWN, why),
        "you_owe": u, "next": u,
        "workflow": _f([], UNKNOWN, why),
        "last_act": _f({"at": act["at"], "act": act["act"],
                        "actor": act["actor"],
                        "actor_alias": _alias(cv, act["actor"]),
                        "id": act["id"]}, RECORDED,
                       "the request itself; nothing under it could be read"),
    }


def conversation_work(cv, conversation, *, viewer=None, runtime=None) -> dict:
    """Every trunk that begins in this Conversation, with its status."""
    rows = cv.history(conversation=conversation, act="expectation-recorded")
    # EVERY TREE THIS VIEW WALKS, READ A LEVEL AT A TIME BEFORE ANY OF IT IS
    # WALKED. Each trunk's status asks, node by node, what every act under it
    # caused -- its runs, its children's runs, its decisions -- and whether a
    # request is a trunk at all is asked of its parent: one statement per
    # node, ~19,000 for one large Conversation on the live Brain (R3). Inside
    # a `reading()` scope this settles those answers for the whole forest in a
    # few statements; the walks below then ask exactly what they asked before
    # and are answered from it. Outside one it does nothing.
    cv._prefetch_lineage([a["id"] for a in rows]
                         + [a["caused_by"] for a in rows], acts=rows)
    order = _Seq(cv)
    items = []
    for a in rows:
        if not is_trunk(cv, a):
            continue
        # ONE TRUNK THAT CANNOT BE READ DOES NOT FAIL THE CONVERSATION. It is
        # returned with every field UNKNOWN and the reason, beside the rest.
        try:
            items.append(trunk_status(cv, a["id"], viewer=viewer,
                                      runtime=runtime, order=order))
        except Exception as exc:                          # noqa: BLE001
            items.append(_unreadable(cv, a, exc))
    return {"conversation": conversation, "viewer": viewer,
            "runtime_why_not": (runtime or {}).get("why_not"),
            "items": items,
            "note": "computed from the record on every read. Sources: recorded, "
                    "computed, runtime (this process, now) or unknown."}


def owed_by(cv, participant, *, limit=10) -> dict:
    """What this Participant owes, across the Brain: expectations whose current
    carrier is them and that nobody has answered.

    NOT who was addressed. Being spoken to is a fact about a Turn; owing is an
    expectation recorded of somebody. Bounded, and never silently.
    """
    rows, names = [], {}

    def name(cid):
        if cid and cid not in names:
            names[cid] = cv.conversation_name(cid)
        return names.get(cid)

    for st in cv.expectations(of=participant):
        if st["response_present"]:
            continue
        rows.append({
            "expectation": st["expectation"], "expects": st["expects"],
            "conversation": st["conversation"],
            "conversation_name": name(st["conversation"]),
            "turn": st["turn"],
            "number": cv.turn_number(st["turn"]) if st["turn"] else None,
            "asked_by": st["requested_by"],
            "asked_by_alias": _alias(cv, st["requested_by"]),
            "because": st["because"],
            "options": len(st["options"] or ()),
            "at": cv._act(st["expectation"])["at"],
            # A QUESTION OF A DECISION FORM (P7) is answered only by a reply
            # naming it, at its form; a card offering a plain reply must
            # know that. Its own words are the question, not the post's.
            "form": st.get("form"),
            "question": st.get("question"),
        })
    rows.sort(key=lambda r: -r["at"])
    limit = max(0, int(limit))
    return {"participant": participant, "owed": rows[:limit],
            "total": len(rows), "omitted": max(0, len(rows) - limit),
            "note": "expectations of this participant that nobody has "
                    "answered. Being addressed is not owing."}
