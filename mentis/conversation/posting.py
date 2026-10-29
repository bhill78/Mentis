"""Writing a post: the domain-level write operations every door uses.

ONE OPERATION, SEVERAL DOORS. Production's `POST /api/conversations/<id>/turns`
and Fluid's `POST /fluid/api/posts` both write a post by calling `post` here,
and both address an existing post by calling `address`. Neither calls the
other's HTTP route. Each door parses its own request, decides who the writer
observably is, calls the operation, shapes its own answer and starts the
dispatches the operation hands back -- after the operation has committed.

WHAT MOVED HERE, UNCHANGED (Fluid stage F2, Part A). The body of the turns
route and the helpers only it used, out of `mentis/web/__init__.py`: op-key
idempotency, the intake and inert refusals, continuation, choice and
withdrawal checks, anchor checks, staged artifact submissions, `say`, Topic
filing, `turn-said`, what each dispatch owes (`owe`), Ask Mentis
(`ask_mentis`), and the order of all of it inside one transaction. The words
of every refusal and every response are the ones the route gave.

WHAT THE OPERATIONS RETURN is `(answer, dispatches)`: the answer the route
always gave -- a refusal is an answer with `error` in it, and so is a replayed
operation key -- and the keyword arguments of each dispatch to start once the
record is durable. A refusal or a replay starts nothing, so its list is empty.
Starting them is the caller's (`mentis.web.dispatch.dispatch_soon`), because
when a run starts is a property of the server, not of the record.
"""
from __future__ import annotations

import os

from mentis.conversation import text as text_part

#: THE THREE AUTHORED ACTIONS. Vocabulary, not a state machine: nothing
#: branches on these beyond the one intake rule, and a Turn carrying none
#: behaves exactly as Turns did before they existed.
RECORD_ONLY = "record-only"
ASK_MENTIS = "ask-mentis"
ASK_PARTICIPANT = "ask-participant"
INTAKE_ACTIONS = (RECORD_ONLY, ASK_MENTIS, ASK_PARTICIPANT)

#: WHAT CARRYING AN UNADDRESSED REQUEST ACTUALLY NEEDS OF A RUNTIME, as declared
#: capabilities rather than as prose about runtimes. It organises through the
#: Mentis tools, so being able to CALL them is a hard requirement -- an execution
#: that cannot reach them can neither read the record nor delegate, and would
#: report an apology instead. Writing is NOT here: most requests need none, and
#: requiring it would rule out runtimes for work that never touches a file.
INTAKE_REQUIRES = ("call_mentis_tools",)


# -- the post -----------------------------------------------------------------

def post(cv, corpus, cid, body, *, agents=None, written_by) -> tuple[dict, list]:
    """Record the Turn, then do only what the AUTHOR asked for.

    THE ONE THING DECIDED MECHANICALLY is which of three authored
    actions this was, and each has exactly one consequence:

      record-only        the Turn. Nothing else, ever.
      ask-participant    an expectation of them, and a dispatch.
      ask-mentis         an expectation owed to the author, assigned to
                         whoever is designated to carry unaddressed
                         requests, and a dispatch of them.

    NOTHING IS INFERRED FROM PROSE, from ancestry, or from a mention.
    No classifier reads the text; no reply resumes anybody because a
    reply exists. The action is a field the author set, and a Turn that
    carries none behaves exactly as it did before this existed -- which
    is what keeps every Turn already in the record meaning what it meant
    when it was written.

    `written_by` is called once, where the route used to observe the writer:
    after every refusal that needs no write, before staged bytes are checked.
    `agents` is the agent service each dispatch's runtime is judged by.
    """
    from mentis import artifacts as _artifacts
    from mentis.conversation import anchors as _anchors
    from mentis.conversation.versions import Refused as _AnchorRefused
    # A RETRY OF THE SAME TURN IS THE SAME TURN. `op` is the author's
    # operation key: the same key and request returns the response the
    # first request gave and writes and dispatches nothing again; the
    # same key with a different request is refused; a new key is a new
    # Turn.
    #
    # ASKED BEFORE ANY INTAKE CHECK, found by review. A completed
    # operation is answered with what it came to even if what it named
    # has since been deleted, a choice has stopped matching or a plan
    # has moved on: replaying writes nothing, so it is not new use.
    # A fresh key gets no such answer and goes through every check
    # below, which is where new use of deleted material is refused.
    op = body.get("op")
    keyed_request = {"route": "turn", "conversation": cid,
                     **{k: body.get(k) for k in (
                         "parts", "text", "replies_to", "addressed_to",
                         "action", "dispatch", "chose", "topics",
                         "because", "requires", "ask_mentis",
                         "governed")}}
    if op and body.get("author"):
        try:
            prior = _anchors.prior_outcome(cv, body["author"], op,
                                           keyed_request)
        except _AnchorRefused as refused:
            return refused.refusal, []
        if prior is not None:
            return prior, []

    # A POST IS NEVER HOMED ON A CONVERSATION'S LATER VERSION: refused, with
    # the Conversation it is a version of named, before anything is written
    # or dispatched (`Conversations.version_refusal`). `say` asks it again.
    refusal = cv.version_refusal(cid)
    if refusal:
        return refusal, []

    action = (body.get("action") or "").strip() or None
    if action and action not in INTAKE_ACTIONS:
        return {"error": f"unknown action {action!r}",
                "actions": sorted(INTAKE_ACTIONS)}, []

    # WHAT EACH DISPATCH CONTINUES, DECIDED BEFORE ANYTHING IS WRITTEN,
    # so an ambiguity refuses the whole Turn rather than leaving half of
    # it recorded. Nothing here is inferred from prose: it is read from
    # the reply the author made and the record of the work it answers.
    plans = []
    # WHAT GOVERNS AN ASK-MENTIS REQUEST is checked exactly as a
    # spec's `governed` is below, and before anything is written: a
    # reference the record does not hold, or deleted material, refuses
    # the whole Turn. It is a list or absent; anything else is refused
    # rather than read as either.
    if action == ASK_MENTIS and body.get("governed") is not None:
        named = body.get("governed")
        if not isinstance(named, list):
            return {"error": "governed is a list of entry ids, or "
                             "absent", "governed": named}, []
        unheld = [str(g) for g in named
                  if g and not corpus.read([str(g)])]
        if unheld:
            return {"error": f"{unheld} name nothing this record "
                             f"holds, so they could not govern the "
                             f"work", "governed": unheld}, []
        from mentis.conversation.versions import inert_refusal
        refusal = inert_refusal(corpus, *[str(g) for g in named if g])
        if refusal:
            return {**refusal, "governed": [refusal["entry"]]}, []
    if action != RECORD_ONLY:
        for spec in body.get("dispatch", ()):
            # A reach that is not one of the two words is refused,
            # never read as the wider one (found by review).
            if spec.get("reach") not in (None, "work", "conversation"):
                return {"error": f"reach is 'work' or 'conversation', "
                                 f"not {spec.get('reach')!r}"}, []
            # A LIST OR ABSENT, as for Ask Mentis above: a string was
            # iterated a character at a time (found by review).
            if spec.get("governed") is not None and not isinstance(
                    spec.get("governed"), list):
                return {"error": "governed is a list of entry ids, or "
                                 "absent", "governed": spec["governed"]}, []
            # A GOVERNED REFERENCE THE RECORD DOES NOT HOLD IS A
            # MISTAKE WORTH SAYING NOW. Refused whole, like the two
            # checks either side of it, so the Turn is never recorded
            # naming material that could never arrive. `delegate`
            # already checked this on the worker's side and this route
            # did not, which is how an unknown id reached composition.
            # ONLY EXISTENCE: whether it STANDS is the composer's
            # question, asked when the run happens and not now.
            unheld = [str(g) for g in (spec.get("governed") or ())
                      if g and not corpus.read([str(g)])]
            if unheld:
                return {"error": f"{unheld} name nothing this record "
                                 f"holds, so they could not govern "
                                 f"the work", "governed": unheld}, []
            # NOR IS DELETED MATERIAL NAMED AS GOVERNING NEW WORK:
            # naming it is new forward use, whatever composition would
            # later make of it. The same answer `delegate` gives.
            from mentis.conversation.versions import inert_refusal
            refusal = inert_refusal(
                corpus, *[str(g) for g in (spec.get("governed") or ())
                          if g])
            if refusal:
                return {**refusal, "governed": [refusal["entry"]]}, []
            plan = continuation(cv, spec, author=body["author"],
                                replying_to=body.get("replies_to"))
            if "error" in plan:
                return plan, []
            # A REPOSITORY IS DECLARED, NEVER INFERRED. The author
            # names the directory the work runs in (`path`, absolute;
            # `dispatch.declared_workspace`); nothing reads that out of
            # the work's words. Mentis makes no worktree: Git is the
            # author's and the agent's. A Mark IV `base` is still
            # recorded as said, and names no directory.
            repo = spec.get("repository")
            if repo is not None:
                path = (repo.get("path") if isinstance(repo, dict)
                        else repo if isinstance(repo, str) else None)
                base = (repo.get("base") if isinstance(repo, dict)
                        else None)
                if isinstance(path, str) and path.strip():
                    if not os.path.isabs(path.strip()):
                        return {"error": "a repository is an absolute "
                                         "directory: {\"repository\": "
                                         "{\"path\": \"<directory>\"}}"}, []
                    plan = {**plan, "repository": {
                        "path": os.path.normpath(path.strip())}}
                elif isinstance(base, str) and base.strip():
                    plan = {**plan, "repository": {"base": base.strip()}}
                else:
                    return {"error": "a repository request names its "
                                     "directory: {\"repository\": "
                                     "{\"path\": \"<directory>\"}}"}, []
            # FOLLOW-UP PERMISSION IS THE AUTHOR'S, on this request:
            # ask afterward (absent), {"depth": N} or "unrestricted".
            # It carries through the work's follow-ups
            # (`operational.pursuit_permitted`); refused in words when
            # it is not one of those, never read as a wider one.
            if spec.get("follow_up") is not None:
                # IT BELONGS TO THE ORIGINAL REQUEST. A reply that
                # continues earlier work carries that work's
                # permission; one set here would be stored and never
                # read, so it is refused in words instead.
                if plan.get("continues"):
                    return {"error": "follow-up permission belongs to "
                                     "the original request; this "
                                     "continues earlier work, which "
                                     "keeps the permission it was "
                                     "asked with"}, []
                from mentis.operational import follow_up_value
                try:
                    plan = {**plan, "follow_up":
                            follow_up_value(spec["follow_up"])}
                except ValueError as exc:
                    return {"error": str(exc)}, []
            # RUN CONSENT IS THE AUTHOR'S TOO, on this request: which of the
            # work's operations proceed without asking (docs/run-consent.md).
            # Validated here -- workspaces that exist, no Brain, no
            # credentials -- and refused in words otherwise. An agent's
            # consent only narrows what its request inherits
            # (`operational.consent`), so this grants nobody anything.
            if spec.get("consent") is not None:
                if plan.get("continues"):
                    return {"error": "run consent belongs to the request it "
                                     "was given on; this continues earlier "
                                     "work, which keeps its consent -- change "
                                     "it on the run instead"}, []
                from mentis.operational.consent import consent_value
                try:
                    value = consent_value(spec["consent"])
                except ValueError as exc:
                    return {"error": str(exc)}, []
                if value is not None:
                    plan = {**plan, "consent": value}
                else:
                    # "ask", SAID, IS KEPT: under a wider consent it narrows
                    # (`of_request`); with nothing above it, it is the default.
                    plan = {**plan, "consent": {"mode": "ask"}}
            plans.append(plan)

    # A CHOSEN OPTION IS A FACT THE AUTHOR SET, checked against what
    # was actually offered before anything is written. It answers the
    # ask it names and nothing else -- it records no material and
    # establishes nothing -- and it is never read out of the reply's
    # prose. Refused whole when it does not match, so a Turn is never
    # recorded claiming a choice that was not on offer.
    chose = None
    if body.get("chose") is not None:
        chose = chosen(cv, corpus, body.get("chose"),
                       replies_to=body.get("replies_to"))
        if "error" in chose:
            return chose, []
    # A WITHDRAWAL IS THE OWNER'S REPLY SAYING WHY, plus the act that
    # closes the decision. Checked whole before anything is written:
    # theirs to make, still open, a reason given -- and it only
    # records, so a withdrawal never also starts or continues work.
    withdrawing = bool(chose and chose.get("withdraw"))
    reason = None
    if withdrawing:
        if (action not in (None, RECORD_ONLY) or body.get("dispatch")
                or body.get("ask_mentis")):
            return {"error": "a withdrawal records only; it starts "
                             "and continues no work",
                    "expectation": chose["expectation"]}, []
        reason = " ".join(
            p.get("text") or "" for p in (
                body.get("parts")
                or [text_part(body.get("text", ""))])
            if isinstance(p, dict) and p.get("type") == "text").strip()
        refused = withdrawal_refusal(cv, chose["expectation"],
                                     author=body.get("author"), reason=reason)
        if refused:
            return refused, []
    # A RECONSIDERATION IS DECIDED BY THE PERSON IT WAS ASKED OF, for
    # the findings it offered, and is checked before anything is
    # written. The choice is the structured `chose`; prose decides
    # nothing (an answer in the owner's own words is recorded as their
    # answer and selects nothing).
    from mentis.operational import (reconsideration_choices,
                                    resolve_reconsideration_decision)
    reconsidering = bool(chose and not withdrawing and (cv._act(
        chose["expectation"])["detail"] or {}).get("reconsideration"))
    # AN ANSWER TO ONE QUESTION OF A DECISION FORM (P7): by the person it
    # was asked of, while it is open, and -- in their own words -- with
    # words. Checked before anything is written and again under the lock.
    # The reply and its `turn-said` are recorded exactly as any answer's;
    # the `decision-answered` beside them is what closes that one question.
    answering = bool(chose and not withdrawing and (cv._act(
        chose["expectation"])["detail"] or {}).get("form"))
    said_text = " ".join(
        p.get("text") or "" for p in (
            body.get("parts") or [text_part(body.get("text", ""))])
        if isinstance(p, dict) and p.get("type") == "text").strip()
    if answering:
        refused = form_answer_refusal(cv, chose, author=body.get("author"),
                                      text=said_text)
        if refused:
            return refused, []
    if reconsidering:
        checked = reconsideration_choices(
            cv, chose["expectation"], actor=body["author"],
            chose=chose)
        if "error" in checked:
            return checked, []

    parts = body.get("parts") or [text_part(body.get("text", ""))]
    # NOTHING NEW IS BUILT ON A DELETED TURN. Replying to it, or
    # naming it as a structured reference -- which is what hands a
    # run the artifacts it held -- would use it as new provenance.
    from mentis.conversation.versions import inert_refusal
    refusal = inert_refusal(
        corpus, body.get("replies_to"),
        *[p.get("ref") for p in parts if isinstance(p, dict)
          and p.get("type") == "turn"])
    if refusal:
        return refusal, []
    # AN OBJECT REFERENCE NAMES ONE OBJECT IN A POST THAT STANDS, at a
    # version where that object is, by the same key (`objectref`). Asked
    # before anything is written; refused in words.
    from mentis.conversation import objectref
    refusal = objectref.refusal(corpus, parts)
    if refusal:
        return refusal, []
    # AN ANCHORED REPLY IS AN ORDINARY TURN, and the rule for its one
    # anchor part is `anchors.check_parts` -- asked here so a refusal
    # is an answer before anything is written, and asked again by
    # `say` itself, which is where every Turn is written.
    try:
        _anchors.check_parts(cv, cid, parts, body.get("replies_to"))
    except _AnchorRefused as refused:
        return refused.refusal, []
    # STAGED BYTES BECOME SUBMISSIONS HERE, AND ONLY HERE: the
    # Admission, the artifact-submitted act and the Turn naming it are
    # one transaction. A staged ref whose bytes never arrived is
    # refused before anything is written.
    writer = written_by()
    _artifacts.staged_parts(corpus, parts)
    # ONE TRANSACTION FOR EVERYTHING THE REQUEST RECORDS -- the Turn,
    # its Topics, `turn-said`, what is owed and the authority granted,
    # and last of all the operation key -- so a request that fails
    # partway leaves nothing behind, and above all no key that would
    # answer its retry as a success (found by review: an unknown Topic
    # left the Turn and the key written and nothing dispatched). The
    # dispatches are collected here and started after it commits.
    later = []
    try:
        with corpus.atomic():
            if op:
                # Asked again under the write lock, so two racing
                # requests with one key cannot both miss it.
                prior = _anchors.prior_outcome(cv, body["author"], op,
                                               keyed_request)
                if prior is not None:
                    return prior, []
            # Asked again under the lock too: an answer or another
            # withdrawal written meanwhile closes it first.
            if withdrawing:
                refused = withdrawal_refusal(
                    cv, chose["expectation"],
                    author=body["author"], reason=reason)
                if refused:
                    raise _AnchorRefused(refused)
            if answering:
                refused = form_answer_refusal(
                    cv, chose, author=body["author"], text=said_text)
                if refused:
                    raise _AnchorRefused(refused)
            parts, submitted = _artifacts.submit_staged(
                corpus, cv, parts, author=body["author"],
                conversation=cid, written_by=writer)
            new = cv.say(cid, body["author"], parts,
                         addressed_to=body.get("addressed_to", ()),
                         replies_to=body.get("replies_to"),
                         written_by=writer)
            _artifacts.record_submissions(
                corpus, cv, submitted, author=body["author"],
                conversation=cid, turn=new, written_by=writer)
            for t in body.get("topics", ()):
                cv.assign_topic(new, t)
            cv.record_act(
                actor=body["author"], act="turn-said",
                conversation=cid, turn=new,
                because=body.get("because"),
                # WHICH ACTION THE AUTHOR CHOSE, kept durably beside
                # the Turn. Without it, "was this meant as work?" is
                # answerable only by re-reading the prose later, which
                # is the inference this whole design refuses.
                detail={**({"action": action} if action else {}),
                        **({"chose": chose} if chose else {})}
                or None)
            # THE CLOSURE IS ITS OWN ACT, the house pattern for
            # closing an ask (`_answered_asks`): the decision's
            # `expectation-met`, by the owner, with their reason and
            # the reply that gave it. Nothing already recorded -- the
            # question, the decision, its options -- is touched.
            withdrawn = None
            if withdrawing:
                asked = cv._act(chose["expectation"])
                withdrawn = cv.record_act(
                    actor=body["author"], act="expectation-met",
                    conversation=asked["conversation"],
                    turn=cv.asked_on(asked),
                    caused_by=chose["expectation"], about=[new],
                    because=reason,
                    detail={"withdrawn": True, "reply": new})
            answered = None
            if answering:
                from mentis.conversation import DECISION_ANSWERED
                asked = cv._act(chose["expectation"])
                answered = cv.record_act(
                    actor=body["author"], act=DECISION_ANSWERED,
                    conversation=asked["conversation"],
                    turn=cv.asked_on(asked),
                    caused_by=chose["expectation"], about=[new],
                    because="answered by the person it was asked of",
                    detail={"reply": new,
                            **{k: chose[k] for k in ("option", "label",
                                                     "words")
                               if k in chose}})
            # THE OWNER'S CHOICE FOR EACH FINDING, recorded once, and
            # what they chose to pursue carried and started. A choice
            # made otherwise in the meantime refuses this whole
            # request. Pursuing is what the chosen option says it
            # does, so it starts work even when the reply itself only
            # records: the owner's choice is the instruction, not the
            # note beside it.
            # THE OWNER'S ANSWER TO A RECOVERY QUESTION: a request that
            # ended with nothing reported twice is retried (dispatched
            # again) or parked, as they chose (`dispatch.retry_if_chosen`).
            if chose and not withdrawing and chose.get("option") is not None:
                from mentis.web.dispatch import retry_if_chosen
                later.extend(retry_if_chosen(cv, chose, by=body["author"],
                                             turn=new))
            reconsidered = None
            if reconsidering:
                reconsidered = resolve_reconsideration_decision(
                    cv, chose["expectation"], chose=chose,
                    actor=body["author"], turn=new)
                if "error" in reconsidered:
                    raise _AnchorRefused(reconsidered)
                if not reconsidered["repeat"]:
                    reconsidered["started"] = pursue_chosen(
                        cv, reconsidered["pursued"],
                        by=body["author"],
                        decision=chose["expectation"],
                        enqueue=lambda **kw: later.append(kw))

            # THE TURN IS DURABLE BEFORE ANYTHING IS DISPATCHED, and it
            # stays durable whether or not a runtime ever answers.
            # Saying something to somebody is the record; a dispatch
            # is a consequence of it.
            #
            # RECORD ONLY STOPS HERE, and it stops here EXPLICITLY
            # rather than by there being nothing left to do. A note is
            # not an instruction and must never cost a runtime, so
            # anything a caller also sent is refused rather than
            # quietly honoured.
            if action == RECORD_ONLY:
                # `governed` names what governs WORK, and nothing
                # here is work: refused in words like the others.
                ignored = ([k for k in ("dispatch", "ask_mentis")
                            if body.get(k)]
                           + (["governed"]
                              if body.get("governed") is not None
                              else []))
                out = {"turn": new, "number": cv.turn_number(new),
                       "action": action, "dispatched": 0,
                       "expectations": [],
                       "nothing_is_owed": True,
                       **({"refused": ignored,
                           "why": "record only records; it never "
                                  "dispatches"}
                          if ignored else {})}
            else:
                owed = []
                # Only an addressee the composer marked for execution
                # is run. An ordinary `@` mention addresses a person or
                # an agent WITHOUT asking for work, and the difference
                # has to come from the owner -- inferring "they meant
                # to dispatch" from a mention would make every mention
                # spend a runtime.
                authority = {}
                for spec, plan in zip(body.get("dispatch", ()), plans):
                    exp = owe(cv, turn=new, spec=spec, plan=plan,
                              body=body, svc=agents)
                    owed.append(exp)
                    authority[exp] = plan
                    later.append(dict(
                        conversation=cid, turn=new,
                        participant=spec["participant"],
                        work=spec.get("work") or body.get("text", ""),
                        runtime=spec.get("runtime"),
                        model=spec.get("model"),
                        effort=spec.get("effort"),
                        # WHAT `owe` RESOLVED AND RECORDED: the Persona
                        # chosen, the designated one, or none.
                        persona=recorded_persona(cv, exp),
                        new_instance=bool(spec.get("new_instance")),
                        difficulty=spec.get("difficulty") or "ordinary",
                        requires=spec.get("requires") or (),
                        expectation=exp,
                        because="the author addressed this work to "
                                "them here",
                        **({"deadline_s": spec["deadline_s"]}
                           if "deadline_s" in spec else {})))

                out = {"turn": new, "number": cv.turn_number(new),
                       "action": action,
                       "dispatched": len(body.get("dispatch", ())),
                       "expectations": owed, "authority": authority}
                if action == ASK_MENTIS:
                    out.update(ask_mentis(
                        cv, conversation=cid, turn=new,
                        author=body["author"],
                        work=body.get("text") or "",
                        because=body.get("because"),
                        requires=body.get("requires") or (),
                        governed=body.get("governed"),
                        enqueue=lambda **kw: later.append(kw)))
            if reconsidered:
                out["reconsidered"] = reconsidered
            if withdrawn:
                out["withdrawn"] = {"expectation": chose["expectation"],
                                    "act": withdrawn}
            if answered:
                out["answered"] = {"expectation": chose["expectation"],
                                   "act": answered}
            # THE LAST QUESTION OF A FORM CLOSING RESUMES THE WORK THAT
            # ASKED IT, once, through the one resumption path. Claimed
            # inside this transaction, after anything this reply itself
            # continues was owed -- so a reply that also continues the work
            # is that work running, and does not resume it a second time.
            if answered or (withdrawn and (cv._act(chose["expectation"])[
                    "detail"] or {}).get("form")):
                resumed = resume_closed_form(
                    cv, chose["expectation"],
                    enqueue=lambda **kw: later.append(kw))
                if resumed:
                    out["resumed"] = resumed
            # THE KEY ANSWERS FOR THE WHOLE REQUEST, so it is written
            # last, beside everything it answers for, and a retry is
            # given back exactly the response this one gives.
            if op:
                _anchors.record_outcome(cv, body["author"], op,
                                        keyed_request, out,
                                        conversation=cid)
    except _AnchorRefused as refused:
        return refused.refusal, []
    # STARTED ONLY ONCE ALL OF IT IS DURABLE, by the caller. `dispatch_soon`
    # starts a thread and records its own failures, so what is owed is never
    # left without either a run or a recorded reason there is none.
    return out, later


# -- addressing an existing post ------------------------------------------------

def address(cv, corpus, tid, body, *, by, agents) -> tuple[dict, list]:
    """Record late addressing; an explicit ask also owes and dispatches work.

    `by` is who the record will say did it, already checked by the door
    (`mentis.web._attributed`). `agents` is the agent service: asking for work
    with none attached is refused before anything is written."""
    from mentis.conversation import anchors
    from mentis.conversation.versions import (Refused, flow_text,
                                              inert_refusal, presented)

    action = body.get("action") or RECORD_ONLY
    if action not in (RECORD_ONLY, ASK_PARTICIPANT):
        return {"error": "address action is record-only or ask-participant"}, []
    op = body.get("op")
    if action == ASK_PARTICIPANT and not op:
        return {"error": "sending an existing turn needs an operation key"}, []
    request = {"route": "address", "turn": tid,
               **{k: body.get(k) for k in ("participant", "because", "action")}}
    try:
        with corpus.atomic():
            if op:
                prior = anchors.prior_outcome(cv, by, op, request)
                if prior is not None:
                    return prior, []
            refusal = inert_refusal(corpus, tid, body.get("participant"))
            if refusal:
                return refusal, []
            cid = cv.conversation_of(tid)
            entries = corpus.read([tid])
            if not cid or not entries or not cv._is(entries[0], "contribution"):
                return {"error": "that is not a turn in a conversation"}, []
            participant = body.get("participant")
            people = corpus.read([participant]) if isinstance(participant, str) else []
            if not people or not cv._is(people[0], "participant"):
                return {"error": "addressing needs a known participant"}, []
            if action == ASK_PARTICIPANT and agents is None:
                return {"error": "no agent service is attached to this server"}, []
            act = cv.address_turn(tid, participant, by=by,
                                  because=body.get("because"))
            out = {"operational_act": act, "addressees": cv.addressees_of(tid),
                   "dispatched": 0}
            if action == ASK_PARTICIPANT:
                entry = presented(corpus, entries[0])
                work = flow_text(entry["body"].get("parts"))
                if body.get("because"):
                    work += "\n\nRequest from the sender:\n" + body["because"]
                plan = continuation(cv, {"participant": participant},
                                    author=by, replying_to=None)
                exp = owe(cv, turn=tid, spec={"participant": participant},
                          plan=plan, body={"author": by,
                                           "because": body.get("because")},
                          svc=agents)
                out.update(dispatched=1, expectation=exp)
            if op:
                anchors.record_outcome(cv, by, op, request, out,
                                       conversation=cid)
    except Refused as refused:
        return refused.refusal, []
    if action == ASK_PARTICIPANT:
        return out, [dict(
            conversation=cid, turn=tid, participant=participant,
            work=work, expectation=exp, persona=recorded_persona(cv, exp),
            because="the sender asked this participant to act on an existing turn")]
    return out, []


# -- what the operations are made of -------------------------------------------

def chosen(cv, corpus, chose, *, replies_to) -> dict:
    """Which offered alternative a reply chose, or why that cannot be said.

    Read from the expectation's own recorded options and nothing else: the
    reply must answer the Turn that asked, and the option must be one that
    Turn's decision actually carried, at that position and with that label.
    """
    if not isinstance(chose, dict):
        return {"error": "a choice names the expectation and the option"}
    exp_id, index = chose.get("expectation"), chose.get("option")
    rows = [a for a in corpus.operational()
            if a["id"] == exp_id and a["act"] == "expectation-recorded"]
    if not rows:
        return {"error": "there is no such decision to choose an answer to",
                "expectation": exp_id}
    exp = rows[0]
    # WHERE IT WAS ASKED, which the reply must answer: the decision's own
    # Turn, or for a question of a decision form the form's post -- None
    # while the form is on no post yet, when the answer is a reply to
    # nothing (P7). For every decision asked as its own Turn this is
    # `exp["turn"]`, exactly as before.
    asked_in = cv.asked_on(exp)
    form = (exp.get("detail") or {}).get("form")
    # WITHDRAWING IS THE OTHER THING A REPLY TO A DECISION CAN SAY: that it is
    # closed without an answer. It names no option, so it needs none to have
    # been offered; who may say it, and whether it is still open, is
    # `withdrawal_refusal`'s to check.
    if chose.get("withdraw") is not None:
        if chose.get("withdraw") is not True:
            return {"error": "withdraw is true, or absent",
                    "expectation": exp_id}
        if any(chose.get(k) is not None
               for k in ("option", "label", "selections")):
            return {"error": "a withdrawal chooses no option",
                    "expectation": exp_id}
        # a decision, or input somebody was asked for (`request_input`)
        from mentis.conversation import ASKED_UNDER_WORK
        if (exp.get("detail") or {}).get("expects") not in ASKED_UNDER_WORK:
            return {"error": "only a decision can be withdrawn, or input "
                             "you were asked for",
                    "expectation": exp_id}
        if replies_to != asked_in:
            return {"error": "a withdrawal answers the Turn that asked for "
                             "the decision",
                    "expectation": exp_id, "asked_in": asked_in}
        return {"expectation": exp_id, "withdraw": True}
    options = (exp.get("detail") or {}).get("options")
    # A QUESTION OF A DECISION FORM IS ANSWERED BY NAMING IT: with one of its
    # options, or with no option at all, in the owner's own words (the
    # reply's text). That is the only way it is answered (P7).
    if form and chose.get("option") is None and chose.get("label") is None:
        if chose.get("selections") is not None:
            return {"error": "that decision offered no findings to choose "
                             "for", "expectation": exp_id}
        if replies_to != asked_in:
            return {"error": "an answer answers the post that asked for it",
                    "expectation": exp_id, "asked_in": asked_in}
        return {"expectation": exp_id, "words": True}
    if not options:
        return {"error": "that decision offered no options, so there is "
                         "nothing to choose; answer it in your own words",
                "expectation": exp_id}
    if replies_to != asked_in:
        return {"error": "a choice answers the Turn that asked for it",
                "expectation": exp_id, "asked_in": asked_in}
    if not isinstance(index, int) or isinstance(index, bool) \
            or not 0 <= index < len(options):
        return {"error": "that is not one of the options offered",
                "offered": len(options)}
    label = options[index]["label"]
    if chose.get("label") is not None and chose.get("label") != label:
        return {"error": "the option at that position is not the one named",
                "offered": label}
    # WHAT THE OWNER CHOSE FOR EACH FINDING, where the option asks for that.
    # Only a reconsideration offers findings; whose they are and which were
    # offered is checked against it (`reconsideration_choices`).
    if chose.get("selections") is not None:
        if not (exp.get("detail") or {}).get("reconsideration"):
            return {"error": "that decision offered no findings to choose "
                             "for", "expectation": exp_id}
        return {"expectation": exp_id, "option": index, "label": label,
                "selections": chose["selections"]}
    return {"expectation": exp_id, "option": index, "label": label}


def withdrawal_refusal(cv, exp_id, *, author, reason) -> dict | None:
    """Why this author may not withdraw this decision now, or None.

    ONLY THE PERSON IT WAS ASKED OF, ONLY WHILE IT IS OPEN, AND ONLY WITH A
    REASON. Read from the expectation's own state; asked before anything is
    written and again under the write lock.
    """
    st = cv.expectation_state(exp_id)
    if not author or author != st["expected_of"]:
        return {"error": "only the person this decision was asked of can "
                         "withdraw it", "expectation": exp_id,
                "asked_of": st["expected_of"]}
    if st["response_present"]:
        return {"error": "this decision is already closed, so there is "
                         "nothing to withdraw", "expectation": exp_id,
                **({"withdrawn": st["withdrawn"]["act"]}
                   if st["withdrawn"] else {})}
    if not (reason or "").strip():
        return {"error": "withdrawing needs a reason: say why in your reply",
                "expectation": exp_id}
    return None


def form_answer_refusal(cv, chose, *, author, text) -> dict | None:
    """Why this author may not answer this question of a decision form now,
    or None. The person it was asked of, while it is open; in their own
    words only with words."""
    exp_id = chose["expectation"]
    st = cv.expectation_state(exp_id)
    if not author or author != st["expected_of"]:
        return {"error": "only the person this decision was asked of can "
                         "answer it", "expectation": exp_id,
                "asked_of": st["expected_of"]}
    if st.get("lapsed"):
        # A LATE ANSWER TO A RUN'S PERMISSION QUESTION reaches no run: the
        # wait that would have taken it is over. Refused, so nothing is
        # recorded as allowed for work that can no longer use it.
        return {"error": "this question is no longer asked: "
                         + (st["lapsed"].get("because") or "its run no "
                            "longer waits for an answer")
                         .removeprefix("no longer asked: "),
                "expectation": exp_id, "lapsed": st["lapsed"]["act"]}
    if st["response_present"]:
        return {"error": "this question is already closed, so it cannot be "
                         "answered again", "expectation": exp_id,
                **({"answered": st["answer"]["reply"]} if st.get("answer")
                   else {}),
                **({"withdrawn": st["withdrawn"]["act"]}
                   if st["withdrawn"] else {})}
    if chose.get("words") and not (text or "").strip():
        return {"error": "an answer in your own words needs the words: say "
                         "it in your reply, or choose one of the options",
                "expectation": exp_id}
    return None


def resume_closed_form(cv, exp_id, *, enqueue) -> list[str]:
    """If this question's decision form is now closed -- every question
    answered or withdrawn -- resume the work that asked it, once
    (`claim_resumption`, whose own act is its guard). Its dispatch is
    handed to `enqueue`, to start once everything is durable. Returns the
    `work-resumed` acts written: none while a question is open."""
    exp = cv._act(exp_id)
    fid = (exp.get("detail") or {}).get("form") if exp else None
    form = cv.decision_form(fid) if fid else None
    if not form or not form["closed"] or not form["request"]:
        return []
    act = cv.claim_resumption(form["request"], event={
        "kind": "decision-form-closed", "form": fid, "expectation": exp_id})
    if act is None:
        return []
    from mentis.web.dispatch import resume_dispatch
    enqueue(**resume_dispatch(cv, form["request"], act))
    return [act]


def pursue_chosen(cv, findings, *, by, decision, enqueue) -> list[dict]:
    """The owner chose to pursue these findings: each is carried and started.

    AS ITSELF AND AS ITS OWN WORK. The finding is assigned where it stands --
    the same expectation, Turn and discovery -- to the carrier designated for
    requests addressed to nobody, and dispatched as any such request is. It is
    its own trunk (`operational.trunk_of` stops at a finding), so it finishes,
    and is reconsidered, on its own; nothing ties it to the work it was found
    under unless somebody declares a wait. Assigned only while nobody carries
    it, inside the caller's transaction, so it is started once. With nobody
    designated it stays chosen and unassigned, for whoever coordinates.
    """
    from mentis.operational import _said
    designated = cv.intake_carrier()
    out = []
    for f in findings:
        if cv.assigned_carrier(f)["carrier"] is not None:
            continue
        if not designated["resolved"]:
            out.append({"expectation": f, "assigned": False,
                        "why_not": designated["detail"]})
            continue
        exp = cv._act(f)
        carrier, persona = designated["participant"], designated["persona"]
        if carrier not in cv.participants(exp["conversation"]):
            cv.join(carrier, exp["conversation"], attributed_to=by)
        cv.assign(f, carrier, by=by,
                  because="the owner chose to pursue this finding",
                  detail={"designation": designated["designation"],
                          "persona": persona, "chosen_in": decision})
        enqueue(conversation=exp["conversation"], turn=exp["turn"],
                participant=carrier, persona=persona,
                work=_said(cv, f) or "the finding this Turn records",
                requires=tuple(dict.fromkeys(
                    (*INTAKE_REQUIRES, *(exp["detail"].get("requires") or ())))),
                expectation=f, because="the owner chose to pursue this finding")
        out.append({"expectation": f, "assigned": True, "carrier": carrier})
    return out


def ask_mentis(cv, *, conversation, turn, author, work, because=None,
               requires=(), governed=None, enqueue) -> dict:
    """Record what is owed, then assign and dispatch it -- in that order.

    THE ORDER IS THE DESIGN. The expectation is written FIRST and UNASSIGNED, so
    a request survives everything that can go wrong after it: no designation, no
    eligible runtime, a summon that throws. In every one of those the record
    still says something is owed, to whom it is owed, and why nobody is carrying
    it. Nothing here can leave a request invisible.

    AND NOTHING HERE IS A DECISION ABOUT THE WORK. It resolves one designation
    and dispatches it. What to do with the request -- answer it, continue with
    somebody, give it a Topic, delegate it, assemble two people -- is judgment
    the carrier exercises while carrying it, under its own governed Persona. This
    function has no opinion about any of that, and adding one would be the
    workflow engine the whole design refuses.

    THE SECOND HALF IS `carry_unaddressed`, shared with `resume_intake`, so a
    request intake could not assign is carried later by exactly the code that
    would have carried it then.

    `governed` IS WHAT THE OWNER SAID GOVERNS THIS WORK, by reference, exactly
    as an ask-participant spec carries it: recorded on the request, so the
    carrier's run -- first, resumed, or carried late by `resume_intake` -- is
    composed against what stands when it runs (`dispatch._governed_for`).
    PRESENT MEANS ANSWERED: `[]` says nothing governs this work, and None says
    nothing was said. Existence and deletion are checked by `post` before
    anything is written, as they are for a spec.

    `enqueue` is handed the dispatch; `post` collects it and its caller starts
    it once the Turn's transaction commits.
    """
    # ADDED TO, NEVER REPLACED. This was `requires or INTAKE_REQUIRES`, so a
    # request naming any requirement of its own REPLACED the hard one -- and a
    # carrier could be dispatched to a runtime that cannot call the Mentis tools
    # at all, which is the one thing carrying an unaddressed request cannot do
    # without. Found by both reviewers.
    asked = tuple(dict.fromkeys(tuple(INTAKE_REQUIRES) + tuple(requires or ())))
    expectation = cv.expect(
        turn, of=None, kind="result", by=author, because=because,
        requires=asked,
        detail=({"governed": [str(g) for g in governed if g]}
                if governed is not None else None))
    out = {"expectation": expectation, "expectations": [expectation]}

    designated = cv.intake_carrier()
    if not designated["resolved"]:
        # UNRESOLVED IS RECORDED, NOT GUESSED AT. Not the first Participant, not
        # the most recently active, not the newest designation of several: each
        # of those would be Mentis making a choice the owner has not made. The
        # expectation stays owed and visible with the reason attached, and
        # `resume_intake` carries it once a designation resolves.
        act = cv.record_act(
            actor=author, act="assignment-unresolved", conversation=conversation,
            turn=turn, caused_by=expectation,
            because=designated["detail"],
            detail={"reason": designated["reason"],
                    "candidates": designated.get("candidates") or []})
        out.update({"assigned": False, "why_not": designated["detail"],
                    "reason": designated["reason"], "act": act,
                    "unresolved": True})
        return out

    out.update(carry_unaddressed(
        cv, designated, conversation=conversation, turn=turn, author=author,
        expectation=expectation, work=work, requires=asked, enqueue=enqueue))
    return out


def carry_unaddressed(cv, designated, *, conversation, turn, author,
                      expectation, work, requires, enqueue,
                      assign_detail=None) -> dict:
    """Assign an unassigned request to the designated carrier, and dispatch it.

    THE REMAINING HALF OF `ask_mentis`, and the only copy of it: called with
    the expectation recorded and `designated` resolved, when a request is
    posted and again by `resume_intake` for one intake could not assign then.
    Writes only; `enqueue` is handed the dispatch and decides when it starts.
    """
    carrier, persona = designated["participant"], designated["persona"]
    # Joining is idempotent, so a brand-new Conversation needs no setting up:
    # this is the whole of what "works in a Conversation with no prior carrier
    # configuration" required.
    if carrier not in cv.participants(conversation):
        cv.join(carrier, conversation, attributed_to=author)
    assignment = cv.assign(
        expectation, carrier, by=author,
        because=f"designated to carry requests addressed to nobody "
                f"({designated['designation']})",
        detail={"designation": designated["designation"], "persona": persona,
                **(assign_detail or {})})

    # WHAT THIS REQUEST MAY ORGANISE, RECORDED AS A FACT ABOUT THE REQUEST. It
    # used to ride only on the grant this dispatch minted, which died with the
    # run -- so continuing the same work later reached a Participant with no
    # authority at all. It belongs to THIS request: not to the Participant, not
    # to its Persona, and not to anybody it delegates to. Superseding the
    # designation that chose the carrier affects the NEXT assignment, not this.
    # Organising operations and authority to coordinate (`worker.AUTHORITY`),
    # never the `delegate` capability every run holds anyway.
    from mentis.worker import AUTHORITY
    cv.grant_authority(
        expectation, AUTHORITY, by=author, source="unaddressed-request",
        origin=designated["designation"],
        because="carries a request addressed to nobody, which is organising "
                "work")
    enqueue(conversation=conversation, turn=turn, participant=carrier,
            work=work, persona=persona, requires=requires,
            expectation=expectation,
            because="assigned as the carrier designated for unaddressed "
                    "requests")
    return {"assigned": True, "carrier": carrier,
            "alias": designated["alias"], "persona": persona,
            "designation": designated["designation"],
            "assignment": assignment}


def continued_request(cv, replying_to, carrier) -> str | None:
    """The request whose result this reply answers, when that result was the
    SAME carrier's -- so continuing somebody's work keeps the runtime it was
    bound to. Read from the record (the result's run and what it carried),
    never from names. None when the reply answers anything else."""
    if not replying_to:
        return None
    for a in cv.history(turn=replying_to):
        if a["act"] != "result-returned" or a["actor"] != carrier:
            continue
        try:
            started = cv._act(a["caused_by"]) if a.get("caused_by") else None
        except Exception:                                # noqa: BLE001
            started = None
        if started and started.get("caused_by"):
            return started["caused_by"]
    return None


#: What a dispatch spec says to choose explicitly no Persona. Absent or null
#: is "nothing chosen" and is a different answer.
NO_PERSONA = "none"


def addressed_persona(cv, spec, *, by_owner: bool = True) -> dict:
    """Which Persona a directly addressed Participant works as, and why.

    OWNER RULING 2026-10-29: directly addressing a participant uses its
    designated Persona unless the owner explicitly selects another, for every
    participant. So `persona` in a dispatch spec is read as:

      absent or null -> the Participant's designated Persona
                        (`Conversations.designated_persona`), `persona_from`
                        "designation" or "intake"; when none resolves, no
                        Persona, "unresolved", with `persona_why`;
      "none"         -> explicitly no Persona, "none-chosen";
      a Persona id   -> that Persona, "chosen".

    Returned as the keys recorded on the request: `persona` (None for none)
    and `persona_from`, plus `persona_why` when unresolved. Resolved once, in
    `owe`; resume, retry and intake never come here.
    """
    chosen = spec.get("persona")
    if isinstance(chosen, str):
        chosen = chosen.strip() or None
    if chosen == NO_PERSONA:
        return {"persona": None, "persona_from": "none-chosen"}
    if chosen:
        return {"persona": chosen, "persona_from": "chosen"}
    # THE OWNER'S ADDRESSING ONLY: the ruling is about what the owner does
    # when they address someone. A post by anyone else dispatches as before,
    # with no Persona it did not name (found by the independent review).
    if not by_owner:
        return {}
    got = cv.designated_persona(spec["participant"])
    if got["resolved"]:
        return {"persona": got["persona"], "persona_from": got["source"]}
    return {"persona": None, "persona_from": "unresolved",
            "persona_why": got["why"]}


def recorded_persona(cv, expectation) -> str | None:
    """The Persona `owe` recorded on this request, or None."""
    return ((cv._act(expectation) or {}).get("detail") or {}).get("persona")


def owe(cv, *, turn, spec, plan, body, svc=None) -> str:
    """Record what one dispatch of an owner's Turn owes, and the authority
    it carries. Writes only; the dispatch itself is the caller's, after
    the Turn's transaction commits."""
    # WHAT IS OWED IS RECORDED BEFORE ANYTHING IS ATTEMPTED. It used
    # to be dispatched with no expectation at all, so a run that
    # never started left nothing saying anybody was waiting.
    #
    # AND WHICH RUNTIME IT IS BOUND TO, ON THE REQUEST ITSELF. It used to
    # travel only in the dispatch arguments, so the first run honoured it and
    # a resumed run -- which reads the record -- did not. A runtime the owner
    # chose, the runtime of the same carrier's work this continues, or the
    # Participant's declared default: resolved once, here, and recorded.
    from mentis.web.dispatch import (constraint_of, resolve_runtime,
                                     runtime_judge)
    from mentis.web.quota import quota_holds
    binding = resolve_runtime(
        cv, participant=spec["participant"], named=spec.get("runtime"),
        continues=(plan.get("continues")
                   or continued_request(cv, body.get("replies_to"),
                                        spec["participant"])),
        # A DECLARED DEFAULT IS A PREFERENCE: recorded on the request only
        # when its runtime could take the work now. See `resolve_runtime`.
        judge=runtime_judge(svc, requires=spec.get("requires") or (),
                            model=spec.get("model"),
                            holds=lambda: quota_holds(cv)))
    constraints = constraint_of(binding, supplied_by=body["author"],
                                basis=turn, model=spec.get("model"),
                                effort=spec.get("effort"),
                                requires=spec.get("requires") or ())
    # AND WHICH PERSONA IT IS WORN AS, resolved once, here, beside the
    # runtime and for the same reason: what the dispatch and every later
    # reader see is what the request recorded (`addressed_persona`).
    from mentis.conversation.owner import _owner
    worn = addressed_persona(cv, spec, by_owner=body.get("author") == _owner(cv))
    exp = cv.expect(turn, of=spec["participant"],
                    kind=spec.get("expects") or "result",
                    by=body["author"],
                    because=body.get("because"),
                    caused_by=plan["continues"],
                    requires=spec.get("requires") or (),
                    detail=({**worn,
                             **({"repository": plan["repository"]}
                                if plan.get("repository") else {}),
                             **({"follow_up": plan["follow_up"]}
                                if plan.get("follow_up") not in (None, "ask")
                                else {}),
                             **({"consent": plan["consent"]}
                                if plan.get("consent") else {}),
                             **({"constraints": constraints}
                                if constraints else {}),
                             # BOUNDED BY THE OWNER: the run reads
                             # what it was asked with, not the
                             # Conversation (artifacts.reach_of)
                             **({"reach": "work"}
                                if spec.get("reach") == "work"
                                else {}),
                             # WHAT THE OWNER SAID GOVERNS THIS
                             # WORK, by reference, on the request
                             # itself -- so every run of it, first
                             # or resumed, is composed against what
                             # stands at that moment.
                             #
                             # WHERE EACH QUESTION IS ASKED, said
                             # as it actually is. EXISTENCE is
                             # checked at `post`'s intake, with the
                             # other per-spec refusals: a reference
                             # the record does not hold refuses the
                             # whole Turn rather than being
                             # recorded. STANDING is not asked here
                             # at all -- the composer asks it at
                             # delivery and withholds a superseded
                             # or unestablished item with the
                             # reason, which is what keeps a run
                             # composed against what stands when it
                             # runs instead of when it was asked
                             # for.
                             #
                             # PRESENT MEANS THE OWNER ANSWERED,
                             # and `[]` is the answer that nothing
                             # governs this work. Truthiness here
                             # collapsed that into having said
                             # nothing, so no caller on this route
                             # could ever clear what applied.
                             **({"governed": [
                                 str(g) for g in
                                 (spec.get("governed") or ()) if g]}
                                if spec.get("governed") is not None
                                else {})}
                            or None))
    if spec.get("restricted"):
        # PRIVATE WORK: what it returns is reached by its own
        # lineage only, never by others through the Conversation.
        from mentis.artifacts import restrict as _restrict
        _restrict(
            cv, exp, by=body["author"],
            because=spec.get("restricted_because")
            or "restricted by the person who asked for it")
    if plan["operations"] is not None:
        cv.grant_authority(exp, plan["operations"],
                           by=body["author"], source=plan["source"],
                           origin=plan["continues"],
                           because=plan["because"])
    return exp


def continuation(cv, spec, *, author, replying_to) -> dict:
    """What one dispatch continues, and what it may therefore organise.

    AUTHORITY FOLLOWS THE WORK, AND ONLY EXPLICIT LINEAGE. A reply by the person
    who made an open, authorised request, dispatching the Participant carrying
    it, continues it -- and inherits exactly what it may organise. Anything
    else is ordinary work: new work to the same Participant, a reply to work
    that was never authorised, a reply to finished work.

    TWO CANDIDATES IS A QUESTION, NOT A GUESS. It is refused before anything is
    written, and says which, so the author can reply to the one they mean.

    `authority` on the spec is the author's explicit override: it grants, narrows
    (to nothing, with an empty list) or broadens, and it settles an ambiguity.
    `continues` names one of the candidates this reply offered.
    """
    from mentis.worker import AUTHORITY, COORDINATE, HANDS_OFF
    who = spec["participant"]
    candidates = (cv.continuation_candidates(replying_to, requester=author,
                                             carrier=who)
                  if replying_to else [])
    explicit = spec.get("authority")
    # "MAY COORDINATE THIS WORK": the author's one gesture, granting THIS
    # request the organising set and `coordinate` (`worker.AUTHORITY`). The
    # interface never names individual operations; the record still says
    # exactly which ones the grant contained.
    if spec.get("coordinate") and explicit is None:
        explicit = list(AUTHORITY)
    if explicit is not None:
        if not isinstance(explicit, list):
            return {"error": "authority is a list of what this work may "
                             "organise",
                    "organising": list(AUTHORITY)}
        # `delegate` IS A CAPABILITY EVERY RUN HOLDS, NOT AUTHORITY (owner
        # ruling ent-94edb8bc6342), so it is refused by name rather than as
        # merely unknown: what was meant by it is `coordinate`.
        capability = [o for o in explicit if o in HANDS_OFF]
        if capability:
            return {"error": f"{capability} is not authority: every run can "
                             f"hand on the work it carries, with its runtime, "
                             f"model, effort and participant. To let this "
                             f"work organise work beyond what it carries -- "
                             f"pick up discovered work -- name "
                             f"{COORDINATE!r}",
                    "organising": list(AUTHORITY)}
        unknown = [o for o in explicit if o not in AUTHORITY]
        if unknown:
            return {"error": f"authority names operations that are not "
                             f"organising operations: {unknown}",
                    "organising": list(AUTHORITY)}
    chosen_one = None
    if spec.get("continues"):
        chosen_one = next((c for c in candidates
                           if c["expectation"] == spec["continues"]), None)
        if chosen_one is None:
            return {"error": "that is not open, authorised work this reply "
                             "continues"}
    elif len(candidates) == 1:
        chosen_one = candidates[0]
    elif len(candidates) > 1 and explicit is None:
        return {"error": "this reply could continue more than one piece of "
                         "organising work ("
                         + ", ".join(f"#{c['number']}" for c in candidates)
                         + "). Reply to the Turn of the one you mean, or say "
                           "what it may organise.",
                "ambiguous_continuation": candidates}

    if explicit is not None:
        return {"continues": chosen_one["expectation"] if chosen_one else None,
                "operations": sorted(set(explicit)), "source": "explicit",
                "because": ("the author granted this work coordination"
                            if spec.get("coordinate") else
                            "the author said what this work may organise")}
    if chosen_one is not None:
        return {"continues": chosen_one["expectation"],
                "operations": chosen_one["operations"], "source": "continuation",
                "because": f"continues the author's "
                           f"{'authorised ' if chosen_one['operations'] else ''}"
                           f"request at #{chosen_one['number']}"}
    return {"continues": None, "operations": None, "source": None,
            "because": "no authorised work is being continued"}
