"""The owner addresses somebody, and somebody actually answers.

HEADLESS: a run is one `RunSpec` handed to MARS through `mentis.execution`
(`agents_perform` builds it: the composed prompt, the one `mentis` MCP server
under this run's grant, the workspace, the bound runtime). Mentis creates no
worktree, commits nothing and parks nothing: Git belongs to whoever asked for
the work and to the agent. The workspace is the request's declared repository
directory if it has one (`declared_workspace`), else the server's.

WHAT WAS MISSING, EXACTLY. Both halves of this already existed and neither
knew about the other. `mentis/core/service.py` can discover runtimes, resolve
an address against live instances, summon, and run an agent
(`agents_perform` -> `Execution.perform`).
`mentis/conversation` can record a Turn, an operational act and a reply. The
POST that creates a Turn wrote three rows and returned. Nothing in between.

So this is the in-between, and it is deliberately small: a Participant is
mapped to an `Address`, a `Selection` is made, an instance is summoned or
reused, the work is performed, and what came back becomes a reply Turn. Every
one of those calls already existed. Nothing here is an orchestrator, there is
no queue, no scheduler and no second source of truth.

WHAT THIS DELIBERATELY DOES NOT DO, because each is a real subsystem rather
than a connection, and building one to make a demo work would be the wrong
trade:

  * It does not watch a run. `RunResult.raw_events` carries the whole event
    stream and nothing consumes it. Acts are recorded at the START and the
    END of a run, so the spine shows that work began and that it returned —
    not what happened in between.
  * It does not unify the two stores. `MentisService` keeps instances in its
    own append-only corpus; the Conversation lives in the spine. The reply
    and the acts land in the spine, which is what the interface reads. The
    instance records do not, so the Activity surface still cannot see these
    runs, and it should not pretend to.
  * It does not KEEP anything alive for continuity. No process outlives a
    perform -- measured on all three runtimes -- and none is held open.
    Continuity across a restart is the runtime's own session, adopted only
    after the runtime confirms it still has it, and otherwise the durable
    record is what a fresh execution is reconstructed from.
  * It never writes a `produced` link. Production is a claim about what work
    brought into being, and nothing here can establish one: what a runtime
    SAYS it did is not evidence. If real work produces a durable object,
    a person or a later act records that.

HONESTY UNDER FAILURE. A run that fails records that it failed, in the
record's own words, and posts no reply. There is no fabricated answer and no
silent swallow: `terminal` and `exit_code` are written as they came back.
"""

from __future__ import annotations

import re
import threading
import time
import traceback

import os

from mentis import artifacts as _artifacts
from mentis.api.types import Address
from mentis.conversation import text as text_part
from mentis.conversation.renderers import RENDERER_BRIEF
from mentis.conversation import render_check as _render_check
from mentis.core import routing as _routing
from mentis.web.quota import quota_holds


#: What separates the sections of a prompt, so the task, the governance and
#: the reply format cannot be mistaken for one another by whatever reads them.
#: The prompt OPENS with the task and CLOSES by pointing back at it (see
#: `_task_block` and `_closing_block`); governance and orientation sit between.
SPLIT = """

---

"""

#: The renderer brief's own heading, so "# Your task" is the only task heading.
REPLY_HEADING = "# How to write your reply"

#: Checklist-shaped lines in the work text that the closing block restates.
_CHECK_LINE = re.compile(r"^\s*[-*] \[[ xX]\] ")
_FENCE = re.compile(r"^\s*```\s*checklist\b")


def _task_block(work: str, done_when: str | None, replying: str = "") -> str:
    """THE OPENING OF EVERY PROMPT: the work exactly as its delegator wrote it,
    and the step's "Done when" when it has one, before any governance.

    AND, FOR A REQUEST ASKED AS A REPLY, THE POST IT REPLIES TO (`replying`,
    `threads.reply_target_block`): which post "this" means and the work it
    belongs to, under the work and never mixed into it."""
    block = "# Your task\n\n" + work.strip("\n")
    if replying:
        block += "\n\n" + replying.strip("\n")
    if done_when:
        block += f"\n\nDone when: {done_when}"
    return block


def _closing_block(work: str, done_when: str | None) -> str:
    """THE END OF EVERY PROMPT: what to check before returning. Restates the
    checklist items found in the work text and the step's "Done when" (not the
    whole task); with none, one line pointing back at "# Your task"."""
    items: list[str] = []
    fenced = False
    for line in work.splitlines():
        if fenced:
            if line.strip().startswith("```"):
                fenced = False
            elif line.strip():
                items.append(line.strip())
        elif _FENCE.match(line):
            fenced = True
        elif _CHECK_LINE.match(line):
            items.append(line.strip())
    lines = ["# Before you return", ""]
    if items or done_when:
        lines.append("Check each of these against what you did, and say which "
                     "are met and which are not:")
        if done_when:
            lines.append(f"Done when: {done_when}")
        shown = items[:10]
        lines.extend(shown)
        if len(items) > len(shown):
            lines.append(f"(and {len(items) - len(shown)} more under "
                         f"\"# Your task\")")
    else:
        lines.append("Re-read \"# Your task\" at the top and confirm you did "
                     "what it asks.")
    # HOW TO CLAIM AN OUTCOME, told to every run whatever its scope: the
    # block ending its final reply is its claim (`operational.completion`).
    from mentis.operational.completion import CLOSING_INSTRUCTION
    lines += ["", CLOSING_INSTRUCTION]
    return "\n".join(lines)


#: What an owner asking for work looks like as an act. These are ordinary act
#: names in the same vocabulary the rest of the record uses; nothing branches
#: on them.
STARTED = "execution-started"
RETURNED = "result-returned"
FAILED = "delivery-failed"

#: WHERE WORK NAMES THE GOVERNED MATERIAL THAT APPLIES TO IT. One key, in the
#: free-form `detail` the assignment acts already carry -- the same place and
#: the same way `persona` is carried. REFERENCES, never prose: what the ids
#: mean is read from the record at delivery, so material superseded between
#: the assignment and the run is not delivered out of a stale copy.
GOVERNED = "governed"


#: A REVIEWER'S VERDICT, as an act on the review request (`record_verdict`):
#: `detail.verdict` is pass | block | incomplete, with the commit it judged,
#: the capabilities it lacked (`lacks`) and a summary. Read by the work view,
#: so the name is fixed.
REVIEW_VERDICT = "review-verdict"
#: The same request sent to another runtime because its run could not do the
#: work where it ran, and the record that it was not. Written by Mark IV's
#: recovery heuristics, which are gone; still READ (`recorded_runtime`,
#: `recorded_requires`, `_not_reassigned`), because records carry them.
WORK_REASSIGNED = "work-reassigned"
WORK_NOT_REASSIGNED = "work-not-reassigned"

#: WHAT A BRIEF HAS TO SAY FOR ITS WORK TO NEED A UI BUILD AND A BROWSER.
#: Deliberately narrow, because a requirement narrows the field and a false
#: one sends work away from a runtime that could have done it: Playwright,
#: browser tests, `npm run build`, building the UI, the render check. Nothing
#: else in a brief is read.
_NEEDS_UI = re.compile(
    r"playwright|\bbrowser[- ]?tests?\b|\bnpm\s+run\s+build\b"
    r"|\bbuild(?:ing)?\s+the\s+(?:web\s+)?ui\b|\bui\s+build\b"
    r"|\brender[-_ ]check\b", re.IGNORECASE)


def inferred_requires(work) -> list[str]:
    """The capabilities a delegated brief itself says its work needs.

    ONE RULE: a brief that mentions running Playwright or browser tests, a UI
    build (`npm run build`, "build the UI") or the render check needs
    `build_ui` and `drive_browser`. Measured: Codex's Windows sandbox cannot
    build the UI (vite and the render check read ancestor directories and get
    "Access denied") or launch a browser, and every Codex review of UI work
    came back incomplete. Applied where work is delegated (`delegate`) and
    recorded there as inferred, so selection reads it from the request and
    anybody can see why the work went where it went. It only narrows."""
    if not isinstance(work, str) or not _NEEDS_UI.search(work):
        return []
    from mentis.api.types import Capability
    return [Capability.BUILD_UI.value, Capability.DRIVE_BROWSER.value]


def recorded_requires(cv, expectation) -> list[str]:
    """What the request itself records that its work needs: `requires` on
    its own record, and what a reassignment added (`to_requires`). Every run
    of the request reads these, so a resumed or retried run is held to what
    the first was."""
    if not expectation:
        return []
    try:
        own = cv._act(expectation)
    except Exception:                                    # noqa: BLE001
        return []
    if not own:
        return []
    out = list((own.get("detail") or {}).get("requires") or ())
    for a in cv.history(caused_by=expectation):
        if a["act"] == WORK_REASSIGNED:
            out += list((a.get("detail") or {}).get("to_requires") or ())
    return list(dict.fromkeys(str(r) for r in out if r))


#: WHICH ACT RESTATES WHAT APPLIES. The same one the Persona lookup in
#: `_resume` reads, and deliberately only that one: an independent review found
#: this accepting the key off ANY act caused by the request, so a later act that
#: happened to carry it would have restated governance without assigning
#: anything. Assigning work is the act that says what it is carried under.
ASSIGNING = "expectation-assigned"


def _governed_for(cv, expectation) -> list[str]:
    """Which governed material this request names. References only.

    THE NEWEST ASSIGNMENT WINS, AND IT IS READ FROM THE RECORD RATHER THAN
    PASSED ALONG. Reassignment and pick-up write an assigning act under the
    request, so the latest one naming material is the current answer, and the
    request's own record is the answer when no assignment restates it. Reading
    it here is also what makes a RESUMED run carry what the first run carried:
    the resume path recovers `persona` from this same history for exactly that
    reason, and nothing had to be added there for this.

    ABSENT AND EMPTY ARE TWO DIFFERENT ANSWERS, which is why this asks whether
    the key is PRESENT and never whether it is truthy. An assignment that names
    `[]` is somebody saying nothing governs this work any more; truthiness read
    that as having said nothing at all and fell through to the earlier
    statement, so what applied could be added to and never cleared. Found by
    independent review, reproduced, and the distinction the record makes
    everywhere else.

    WHAT THIS DELIBERATELY DOES NOT DO. It does not resolve the references, ask
    whether they stand, substitute a successor for superseded material, filter
    by Kind, or infer anything nobody named. `compose` is authoritative at
    delivery and standing-checks each id independently, withholding with a
    stated reason; a second opinion here could only disagree with it. Nor does
    it guess: a request naming nothing gets nothing, and a dispatch carrying no
    request is not work and names nothing.
    """
    # THE READ ITSELF LIVES ON THE CONVERSATION SEAM (`governed_named`), so
    # the work status asks the very same question of the record.
    return cv.governed_named(expectation)


def governing_ids(cv, conversation: str | None, named=(),
                  persona: str | None = None) -> set[str]:
    """Every piece of governing material this work would be delivered and
    that stands now: placed here, placed on the whole Brain, named for the
    work, and carried by the Persona it is done as.

    ONE ANSWER FOR TWO QUESTIONS THAT MUST NOT DISAGREE: which session may be
    reused (`_governing_fingerprint`) and which runtime may run it at all
    (`requirements_of`). Asked of `stands`, as composition asks it. A Persona
    that does not stand carries nothing, so nothing it carries counts.
    """
    return cv.governing_now(conversation, named, persona)


def delivered_in_full(cv, conversation, ids, *, named=(), persona=None) -> set[str]:
    """The governing material this work is given IN FULL: named for it, carried
    by its Persona, or placed here or on the whole Brain without a lesser
    delivery level.

    WHY REQUIREMENTS ARE READ FROM THESE ONLY. Material placed conditionally or
    by reference (Governance Condensation) reaches the run as a pointer it may
    never follow -- a Workflow placed by reference is not this work's
    procedure until somebody names it. Letting such a pointer exclude runtimes
    would make a placement the owner chose to keep light decide where all work
    in a Conversation may run (found in the integrated verification: a
    conditionally placed Discipline left no runtime eligible for any post).
    """
    full = set(named or ())
    if persona:
        full |= {e["id"] for e in cv.persona_carried(persona)}
    from mentis.conversation import WHOLE_BRAIN_SCOPE
    for eid in ids:
        if eid in full:
            continue
        levels = [d for d in (cv.placement_delivery(eid, conversation) if conversation else None,
                              cv.placement_delivery(eid, WHOLE_BRAIN_SCOPE))
                  if d is not None]
        placed = bool(cv._links_now("scoped-to", frm=eid))
        if not placed or not levels or any(
                (d.get("delivery") or "full") == "full" for d in levels):
            full.add(eid)
    return {e for e in ids if e in full}


def full_requires(cv, conversation, *, governed=(), persona=None, requires=()) -> tuple:
    """Everything a run of this work will require of a runtime: what was stated,
    plus what the governing material it will carry in full requires -- the
    expression `_dispatch` uses, less what is recorded on the request afterwards
    (`recorded_requires`, which at posting and delegation is the stated part), so
    a judge there agrees with the dispatch (found by the independent review). A requirement
    that cannot be read is the run's to refuse at dispatch; it adds nothing here."""
    out = list(requires or ())
    named = list(governed or ())
    try:
        out += list(requirements_of(cv, delivered_in_full(
            cv, conversation, governing_ids(cv, conversation, named, persona),
            named=named, persona=persona)))
    except Exception:                                     # noqa: BLE001
        pass
    return tuple(dict.fromkeys(out))


def requirements_of(cv, ids) -> dict[str, list[str]]:
    """What the governing material this work carries requires of a runtime:
    capability -> the entries that require it.

    READ FROM EACH KIND'S OWN DECLARATION (`capability_fields`): the fields its
    `form` says hold Capability names, so no field name is special here. This
    can only NARROW selection -- material that requires something a runtime
    lacks makes that runtime ineligible -- and it never grants anything.
    """
    from mentis.conversation import activities_of, capability_fields, current_of
    out: dict[str, list[str]] = {}
    held = cv._c.read(sorted(ids))
    # AND WHAT THE ACTIVITIES OF GOVERNING MATERIAL NAME. A Workflow's
    # activities hand their Disciplines to the work delegated under it, so
    # what those require is required of the request that carries it: a
    # runtime that could carry the Workflow and none of its activities is not
    # selected. Only Disciplines that stand -- the ones that would reach
    # anybody -- and recorded against the Discipline that requires it. A
    # Discipline revised since the procedure named it counts as its CURRENT
    # version (`current_of`), which is what the carrier is told to hand on.
    named = list(dict.fromkeys(
        c["entry"] for e in held for row in activities_of(cv._c, e)
        for c in (current_of(cv._c, d) for d in row.get("disciplines") or ()
                  if isinstance(d, str))
        if c["entry"] and c["stands"] and c["entry"] not in ids))
    for e in held + cv._c.read(named):
        kind = (e.get("definition") or {}).get("name")
        for field_name in capability_fields(cv._c, kind):
            for cap in (e.get("body") or {}).get(field_name) or ():
                if isinstance(cap, str) and e["id"] not in out.get(cap, []):
                    out.setdefault(cap, []).append(e["id"])
    return out


def _governing_fingerprint(cv, conversation: str, named=(),
                           persona: str | None = None) -> str:
    """What governs here, as a short stable tag. Not a version number.

    Of the material itself, so it says nothing about when anything
    changed and everything about what is in force. Ten hex characters is
    enough to tell two sets apart and short enough to read in a record.

    AND MATERIAL NAMED FOR THE WORK COUNTS, because it is told to the session
    too. This read only ever asked what was PLACED, which was the whole answer
    while placement was the only way material reached a run. Once work could
    name material, superseding a named Rule withheld it from the next payload
    and REUSED the session that had already been told it -- the exact failure
    the comment in `address_for` describes, reintroduced by a channel that
    comment did not know about. Found by independent review and reproduced.

    THE STANDING SUBSET, because that is what would be delivered. A named
    reference that no longer stands, or that the record does not hold, is not
    part of what governs and changing it must change the tag. Asked of
    `stands`, which is the same question composition asks.

    AND WHAT THE PERSONA CARRIES, for the same reason again: a Discipline
    placed on the Persona is told to the session, so placing, replacing or
    ending one must not reuse a session that heard the old set.
    """
    import hashlib
    holding = governing_ids(cv, conversation, named, persona)
    return hashlib.sha256(
        "|".join(sorted(holding)).encode("utf-8")).hexdigest()[:10]


def address_for(cv, participant: str, *, runtime: str | None = None,
                persona: str | None = None,
                conversation: str | None = None, governed=()) -> Address:
    """A durable Participant, said the way the agent world names one.

    THE MAPPER THAT DID NOT EXIST. A Turn's `addressed_to` holds Participant
    entry ids; `agents_resolve` and `agents_summon` take an `Address` of
    name/runtime/persona. Nothing joined them. The name is the Participant's
    own alias with its sigil removed, and `runtime`/`persona` are carried
    through ONLY when the owner actually chose them -- an Address with
    `runtime=None` is a different binding from one naming a runtime, and
    collapsing the two would invent a choice the owner did not make.

    THE CONVERSATION IS PART OF THE BINDING, and it has to be. A runtime
    session carries what was said in it. Continuing one Conversation's
    session for work in an unrelated Conversation would hand an agent
    somebody else's context and call it continuity, which is worse than
    starting fresh -- and `context` is the field this Address already has
    for exactly that. Work at Brain scope names no Conversation and so
    binds to none.
    """
    context = conversation or None
    if conversation:
        # WHAT THE SESSION WAS TOLD IS PART OF THE BINDING, because a model
        # cannot be un-told something. Composition withholds superseded
        # material from the next payload, but a REUSED session still has the
        # old instruction in its context and will still act on it -- so
        # `fresh work receives the current material` was true of the payload
        # and false of the execution.
        #
        # A session that was told different things is a different binding.
        # Changing what governs here therefore stops matching the sessions
        # that were told the old thing, and the next dispatch starts one
        # that has only ever heard the current material. Reverting the
        # material matches them again, because the fingerprint is of what
        # governs and not of when it changed.
        # `governed` IS PART OF WHAT THE SESSION WAS TOLD, for the reason the
        # paragraph above gives. It is not a second binding dimension: the same
        # tag, over the same question, asked of both channels that reach a run.
        context = conversation + "#" + _governing_fingerprint(cv, conversation,
                                                              governed,
                                                              persona)
    return Address(name=cv.alias(participant).lstrip("@"),
                   runtime=runtime or None, persona=persona or None,
                   context=context)


def _wrote_it(instance) -> str:
    """What actually typed the reply, as far as is known.

    FOUND BY REVIEW. The runtime here used to be the one SELECTED, not
    the one that ran: a reused instance running on codex had its reply
    and its acts attributed to claude, because the selection had chosen
    claude for work that never went there. And the comment promised the
    session `where one is known` while writing the local instance id
    instead. Both are now what they say they are.
    """
    tail = instance.session_ref or instance.instance_id
    return f"{instance.runtime}/{tail[:8]}"


def _already_answered(cv, *, execution, request_turn, since):
    """The Turn THIS RUN already said in answer to this request, or None.

    THE OWNERSHIP RULE, READ FROM THE RECORD. One execution may produce one
    substantive conversational answer to the request it carries. `respond` owns
    that answer when it was used for this request; this completion boundary is
    the FALLBACK, for runs that never used it. Deciding which case this is must
    not involve reading the words -- the two answers in the record are worded
    differently and say slightly different things, so any comparison of prose
    would be a guess dressed as a rule.

    WHAT COUNTS AS EVIDENCE: an act on THIS execution, naming a Turn, whose
    `answers_turn` is the request's own Turn. `respond` records that for every
    response it writes, claimed or not. The execution is part of the test
    because a reply another run left on the same request is not this run's
    answer; the request is part of it because a run may answer several distinct
    requests and each is owed its own.

    ONLY A RECORDED ANSWER, never a reply merely found nearby. A contribution
    that happens to reply to the same Turn could be anybody's. Both `respond`
    and the fallback record the act that says this execution answered.

    AND ONLY THIS RUN'S, WHICH IS WHY `since` IS NOT OPTIONAL. An execution is
    an INSTANCE, not a run: `_resume` re-dispatches the SAME expectation and the
    SAME Turn to the same carrier when a delegated child ends, and the instance
    is reused, so a second run shares both halves of the key. Seventeen of the
    317 (execution, turn) pairs in the record have started more than once, one
    of them ten times. Without the bound, run two of a resumed request reads run
    one's answer -- typically an interim `I have delegated this` -- as its own,
    and the real result never becomes a Turn at all. That is a WORSE failure
    than the duplication this check exists to stop: a duplicate is noise, and
    this would be silence. `since` is this run's own `execution-started` act, so
    only what was written after this run began can answer for it.
    """
    candidates = [a for a in cv.corpus.operational(execution=execution)
                  if a.get("turn")
                  and (a.get("detail") or {}).get("answers_turn") == request_turn]
    if not candidates:
        return None
    order = cv.corpus.operational_order([since] + [a["id"] for a in candidates])
    began = order.get(since)
    if began is None:
        # The run's own start is not in the record. Nothing can be said to have
        # come after it, so nothing is treated as this run's answer.
        return None
    for a in candidates:
        if order.get(a["id"], -1) > began:
            return a["turn"]
    return None


def _respond_unclaimed(cv, execution, reply_turn) -> dict | None:
    """`outcome_unclaimed` from the `turn-said` act `respond` wrote for this
    reply, or None."""
    for a in cv.corpus.operational(execution=execution):
        if a.get("act") == "turn-said" and a.get("turn") == reply_turn:
            got = (a.get("detail") or {}).get("outcome_unclaimed")
            if isinstance(got, dict):
                return got
    return None


def _started_act(cv, participant, conversation, turn, instance, selection,
                 svc, before, new_instance, runtime, model, effort,
                 expectation=None, because=None, authority=None,
                 binding=None, requires=(), requires_from=None,
                 persona=None, routed=None, provenance=None,
                 timing=None, session_note=None, execution_mode=None,
                 work_requirements=None) -> str:
    """The act that says work began here, and on what continuity.

    `caused_by` IS THE EXPECTATION, AND IT USED TO BE NOTHING AT ALL. Without
    it a run hung off no request: nothing could ask what this execution was
    for, and a delegated run had no path back to the work it came from, so the
    lineage ended at whichever act happened to be nearest in time. It is what
    makes the whole chain readable, including across a Topic or Conversation
    boundary -- causality is not scoped by where something happened.

    AND `because` IS NO LONGER A SENTENCE THAT IS SOMETIMES FALSE. It read "the
    owner addressed this work here" on EVERY dispatch, which is untrue of a run
    started to carry an unaddressed request, and untrue again of a specialist
    somebody delegated to. A caller that knows why says so.
    """
    return cv.record_act(
        actor=participant, act=STARTED, conversation=conversation, turn=turn,
        execution=instance.instance_id, runtime=instance.runtime,
        caused_by=expectation,
        because=because or "this work was dispatched here",
        detail={"instance": instance.instance_id,
                # WHERE IT WORKS, which run consent counts as approved for
                # the request the owner gave it on (`operational.consent`).
                **({"workspace": instance.workspace}
                   if getattr(instance, "workspace", None) else {}),
                # WHO THIS RUN ACTED AS. The Persona was composed into what the
                # run was told, and nothing recorded it: a post addressed with a
                # Persona ran as it and its run could not say so afterwards
                # (found in the integrated browser check). Read by
                # `operational.runs.asked_with`.
                **({"persona": persona} if persona else {}),
                # WHAT THIS RUN WAS ALLOWED TO DO, AND WHY, AS PROVENANCE. The
                # grant itself is machine-local and dies with the run, so
                # without this the record could say what a run did and never
                # what it was permitted. Read from the work's own record at
                # dispatch; never reconstructed later from a Persona or runtime.
                "authority": authority,
                "reused": bool(before.get("would_reuse")) and not new_instance,
                # WHAT CONTINUITY ACTUALLY HAPPENED, in the words of the
                # thing that decided it: resumed a verified session, adopted
                # one across a restart, or started fresh and why. A run that
                # could not continue says so here rather than looking the
                # same as one that never had a session to continue.
                "continuity": [*svc.summon_notes_here(),
                               *([session_note] if session_note else [])],
                "requested_runtime": runtime,
                "requested_model": model,
                # WHAT FOUNDATION SELECTED, beside what was asked for. The two
                # differ whenever nothing was asked and the catalogue decided,
                # and neither is what ran -- that is observed on the result.
                "selected_model": selection.model,
                "requested_effort": effort,
                "selected_effort": selection.requested_effort,
                # THE CONCRETE MODEL THIS RUN WILL USE, where it is known: what
                # the quota holds read back, for this run's failure or success.
                "effective_model": instance.requested_model
                or (selection.inputs or {}).get("effective_model"),
                # WHERE EACH FIELD CAME FROM AND HOW IT BINDS, field by field
                # (`field_provenance`), and what the work needed of it: its
                # tier, what decided the tier, and whether it could be met.
                **({"field_sources": {f: r["source"]
                                      for f, r in provenance.items()},
                    "field_binding": provenance} if provenance else {}),
                **({"routing": routed} if routed else {}),
                # WHAT THE WORK REQUIRED AND HOW EACH CANDIDATE WAS JUDGED
                # (contract sections 2 and 4), beside the old fields, which
                # stay: `requirements` as its request recorded them (or as an
                # older record's routing implies them), and `selection` --
                # the need, every candidate with its verdict and outcome, and
                # any recommendation said but not acted on.
                **({"requirements": work_requirements}
                   if work_requirements else {}),
                **({"selection": (selection.inputs or {})["selection"]}
                   if (selection.inputs or {}).get("selection") else {}),
                # WHO SERVES THE MODEL, AS ITS OWN FACT. It was already computed
                # at launch to decide whether to pass `--oss --local-provider`,
                # and then thrown away -- so a local run recorded `runtime:
                # codex` and nothing at all about Ollama, and the interface had
                # no way to say "llama3.2 via Ollama, harnessed by Codex". It is
                # four facts and the record now keeps four: Participant,
                # harness, provider, model.
                #
                # None means the runtime serves the model itself, which is the
                # ordinary hosted case and a real answer. It is never guessed
                # from the slug -- the catalogue is asked.
                "provider": svc.provider_of(selection.runtime, selection.model),
                # WHETHER ANYBODY CHOSE, which is what separates "I asked for
                # this" from "Mentis picked it". The interface must be able to
                # say which, and neither is inferable from the values alone.
                "runtime_chosen_by_caller": bool(runtime),
                # WHERE THE RUNTIME CAME FROM: named, the request's own
                # binding, continued work, the Participant's declared default,
                # or auto. Beside `runtime_chosen_by_caller`, which only says
                # whether one was in force, so "Codex because I chose it" and
                # "Codex because @Codex's default is Codex" stay different.
                "runtime_source": (binding or {}).get("source"),
                "runtime_binding": (binding or {}).get("act")
                or (binding or {}).get("declaration"),
                "model_chosen_by_caller": bool(model),
                # WHAT THE WORK REQUIRED OF THE RUNTIME, and which governing
                # material asked for which part of it. Absent where nothing was
                # required, as it always was.
                **({"requires": list(requires)} if requires else {}),
                **({"requires_from": requires_from} if requires_from else {}),
                "selected_runtime": selection.runtime,
                "selection_inputs": selection.inputs,
                "selection_because": " · ".join(selection.because)
                if isinstance(selection.because, (list, tuple))
                else str(selection.because),
                # WHERE THE TIME WENT BEFORE THE START (WS-P): trigger,
                # each step before selection, selection, this act.
                **({"timing": timing} if timing else {}),
                # THE EXECUTION MODE THIS RUN EXECUTES IN (`execution.mode`): what the
                # owner selected for the request, or the runtime's default, with the
                # runtime's mechanism and the acknowledgement it carried. What MARS
                # applied is on the run's end (`consent_applied.execution_mode`).
                **({"execution_mode": execution_mode} if execution_mode else {})})

def authority_for(cv, expectation) -> dict:
    """What a run carrying this request may do, from the request's own record.

    The shape recorded at execution start: the scope, every operation the run
    is permitted, what the request was granted -- its organising operations
    and `coordinate` -- and where that came from.

    `organising` IS WHAT THE RUN'S GRANT CARRIES as its `operations`, so it
    keeps COORDINATE: `worker.may_coordinate` reads it there. It is the
    grant as `authority_of` reads it -- the one place a grant from before
    `coordinate` existed is read as one -- and nothing here maps any name.
    """
    from mentis.worker import AUTHORITY, permitted
    got = cv.authority_of(expectation)
    organising = [o for o in AUTHORITY if o in got["operations"]]
    scope = "organising" if organising else "worker"
    return {"scope": scope,
            "permitted": list(permitted(scope, organising)),
            "organising": organising,
            "source": got["source"], "origin": got["origin"],
            "granted_by_act": got["act"], "because": got["because"],
            **({"unresolved": got["unresolved"]} if got.get("unresolved")
               else {})}


#: THE ACT THAT BINDS A REQUEST TO A RUNTIME when nothing recorded one with
#: the request itself: a participant's declared default resolved at first run,
#: or a runtime a caller named on a path that records no constraint. Written
#: once, before selection, so every later run of the same request -- resumed,
#: retried, continued -- reads the same answer instead of deciding again.
RUNTIME_BOUND = "runtime-bound"


class RuntimeConflict(ValueError):
    """A run was asked for on one runtime while its request is bound to
    another. Refused: running either would substitute one for the other."""


def recorded_runtime(cv, expectation) -> dict | None:
    """The runtime this request is already bound to, or None.

    TWO PLACES, ONE ANSWER. A constraint recorded with the request itself --
    the owner's dispatch, a delegation -- or, failing that, a `runtime-bound`
    act written when the request first ran. Nothing here reads a Participant's
    name, and nothing reads what ran last: what binds is what was decided.

    THE RUNTIME AND NOTHING ELSE (owner ruling, Mentis Setup Installation /
    Updates #14: "The binding guarantee is runtime only"). A request may also
    record the model and effort it was asked with; they describe that request
    and are NOT returned here, so work CONTINUING it inherits only the runtime
    and selects its own. Another run of the SAME request reads them from
    `execution_scope`, because they are still that request's.
    """
    if not expectation:
        return None
    try:
        own = cv._act(expectation)
    except Exception:                                    # noqa: BLE001
        return None
    if not own:
        return None
    # A REASSIGNMENT IS THE LATEST DECISION ABOUT WHERE THIS RUNS: written
    # only after a run here could not do the work, and never over a runtime
    # somebody chose (Mark IV's recovery, read from records that carry it).
    acts = cv.history(caused_by=expectation)
    # THE OWNER'S RETRY RELEASES A REASSIGNMENT: they chose "any runtime"
    # (`retry_if_chosen`), so a move made before it no longer binds.
    retried = [a["at"] for a in acts if a["act"] == WORK_RETRIED]
    since = max(retried) if retried else None
    moved = [a for a in acts
             if a["act"] == WORK_REASSIGNED
             and (a.get("detail") or {}).get("to_runtime")
             and (since is None or a["at"] > since)]
    if moved:
        latest = max(moved, key=lambda a: a["at"])
        return {"runtime": latest["detail"]["to_runtime"],
                "source": "reassigned", "act": latest["id"]}
    said = execution_scope(cv, expectation)["constraints"]
    if said.get("runtime"):
        return {"runtime": said["runtime"],
                "source": said.get("source") or "named", "act": expectation}
    bound = [a for a in cv.history(caused_by=expectation)
             if a["act"] == RUNTIME_BOUND
             and expectation in (a.get("about") or ())
             and (a.get("detail") or {}).get("runtime")]
    if bound:
        latest = max(bound, key=lambda a: a["at"])
        d = latest["detail"]
        return {"runtime": d["runtime"], "source": d.get("source"),
                "act": latest["id"]}
    return None


def runtime_judge(svc, *, requires=(), model=None, holds=None, tier=None):
    """What a Participant's declared default is judged by before it binds: a
    callable answering None when that runtime could take this work now, or
    why not -- absent, ineligible for `requires`, or exhausted by its own
    report or by a known quota failure (`holds`, `quota.quota_holds`). None
    when no agent service is here to ask, and then the default binds as
    declared, as it always did. A judgement that cannot be made is not a
    refusal: the default stands.

    `holds` is the holds themselves or a callable giving them, read only
    when a default is actually judged (most requests declare none). `tier` is
    what the work needs: a default with nothing adequate for it does not bind."""
    usable = getattr(svc, "execution_usable", None)
    if usable is None:
        return None

    def judge(runtime):
        try:
            held = holds() if callable(holds) else holds
            return usable(runtime, tuple(requires or ()), model, holds=held,
                          **({"tier": tier} if tier else {}))
        except Exception:                                 # noqa: BLE001
            return None
    return judge


def execution_scope(cv, expectation) -> dict:
    """What THIS request was asked to run with: `{"constraints", "routing"}`.

    The latest pick-up's, for discovered work somebody picked up, because the
    discovered request's own record is never rewritten (as `declared` reads a
    repository); else its own. Read by every run of the request, so a resumed
    or retried one is held to what the first was. A request that continues this
    one is a different request and reads nothing here: it keeps only the
    runtime, through `recorded_runtime` (owner ruling, #14)."""
    own = cv._act(expectation) if expectation else None
    if not own:
        return {"constraints": {}, "routing": {}}
    mine = own.get("detail") or {}
    picked = [a["detail"] for a in cv.history(caused_by=expectation)
              if a["act"] == ASSIGNING and (a["detail"] or {}).get("picked_up_under")]
    latest = picked[-1] if picked else {}
    return {"constraints": latest.get("constraints") or mine.get("constraints") or {},
            "routing": latest.get("routing") or mine.get("routing") or {}}


def activity_signals(cv, label) -> dict:
    """What one Workflow activity says about the work it is for, at the current
    version of the Workflow: `default_tier`, and `authority_sensitive` if so."""
    if not isinstance(label, str) or label.count("#") != 1:
        return {}
    from mentis.conversation import activities_of, current_of
    ref, key = (x.strip() for x in label.split("#"))
    now = current_of(cv._c, ref)
    got = cv._c.read([now["entry"]]) if now["entry"] else []
    row = next((r for r in activities_of(cv._c, got[0] if got else None)
                if r.get("key") == key), {})
    return {**({"default_tier": row["default_tier"]}
               if row.get("default_tier") in _routing.TIERS else {}),
            **({"authority_sensitive": True}
               if row.get("authority_sensitive") is True else {})}


def routing_inputs(cv, *, difficulty=None, authority_sensitive=False,
                   advisory_tier=None, advisory_by=None, activity=None,
                   persona=None, repository=None, workflow_tier=None,
                   inherited_tier=None, inherited_from=None,
                   requirements=None) -> dict | None:
    """The tier this work needs and everything that decided it, in the shape a
    request records and a run reports; None when nothing says anything.

    `requirements` (`work_requirements`): the work's requirements, recorded as
    `routing.requirements`; the tier is then the legacy reading of what they
    need (`requirements.need`, review and authority forced, the Workflow's
    default and an advisory tier as floors), and every old field is still
    written so older readers keep working.

    NOTHING IS INFERRED FROM WORDS: only these structured inputs count, and
    `ordinary`, what older paths send as a difficulty, is not one of them. REVIEW
    is the Persona `review_signal_of` reads, or a declared `review_of` even
    without one. `inherited_tier` is what `inherited_routing` read from the
    work this continues, kept with `inherited_from` whether or not it decided."""
    signals = activity_signals(cv, activity)
    workflow = workflow_tier or signals.get("default_tier")
    authority = bool(authority_sensitive or signals.get("authority_sensitive"))
    reviewed = (repository.get("review_of") if isinstance(repository, dict)
                else None)
    review = bool(reviewed) or review_signal_of(cv, persona, repository)[0]
    named = difficulty if difficulty in _routing.DIFFICULTY_TIER else None
    if isinstance(requirements, dict):
        from mentis.core import requirements as R
        need_ = need_of({"review": review, "authority_sensitive": authority,
                         "workflow_default_tier": workflow,
                         "advisory_tier": advisory_tier,
                         "requirements": requirements})
        tier, sources = ((None, []) if need_["soft"] and not need_["open"]
                         else (R.tier_of(need_), R.tier_sources(need_)))
        # THE OLD FIELD FOR WHAT WAS INHERITED, for readers that know only it.
        took = [requirements.get(k) or {} for k in ("solution", "reasoning")]
        if not inherited_tier and any(t.get("source") == "inherited" for t in took):
            inherited_tier = R.tier_of(R.need(
                {k: requirements.get(k) for k in ("solution", "reasoning")}))
            inherited_from = list(dict.fromkeys(
                x for t in took for x in t.get("from") or ()))
    else:
        tier, sources = _routing.required_tier(
            difficulty=difficulty, authority_sensitive=authority, review=review,
            workflow_tier=workflow, advisory_tier=advisory_tier,
            inherited_tier=inherited_tier)
    inherited = inherited_tier if inherited_tier in _routing.TIERS else None
    if not (tier or named or isinstance(requirements, dict)):
        return None
    return {"required_tier": tier, "target_effort": _routing.TARGET_EFFORT.get(tier),
            "tier_sources": sources,
            **({"difficulty": named} if named else {}),
            **({"authority_sensitive": True} if authority else {}),
            **({"review": True} if review else {}),
            **({"review_of": reviewed} if reviewed else {}),
            **({"workflow_default_tier": workflow} if workflow else {}),
            **({"advisory_tier": advisory_tier} if advisory_tier else {}),
            **({"advisory_by": advisory_by} if advisory_tier and advisory_by else {}),
            **({"inherited_tier": inherited,
                "inherited_from": list(inherited_from or ())}
               if inherited else {}),
            **({"requirements": requirements}
               if isinstance(requirements, dict) else {})}


def inherited_routing(cv, *, parent=None, participant=None, activity=None,
                      references=()) -> tuple:
    """(the highest tier declared for the work a hand-off continues, or None,
    the requests it was read from).

    A CORRECTION KEEPS THE TIER OF WHAT IT CORRECTS (Quiet Chat, 2026-11-06:
    corrections of complex work, handed on with no difficulty and a runtime
    named, ran at that runtime's coding-tier model). What it continues, read
    from the record and never from words: the requests answered by the Turns
    in `references` (a run's `result-returned` on that Turn), and the earlier
    delegations under the same `parent` to the same `participant` for the same
    activity (Workflow and key). What each declared: a difficulty, an advisory tier, or a
    tier it inherited itself; never review or authority, which force their
    own tier and say nothing about the work's difficulty."""
    seen = continued_requests(cv, parent=parent, participant=participant,
                              activity=activity, references=references)
    best, sources = None, []
    for exp in dict.fromkeys(seen):
        stored = execution_scope(cv, exp)["routing"]
        tiers = [t for t in (_routing.DIFFICULTY_TIER.get(stored.get("difficulty")),
                             stored.get("advisory_tier"),
                             stored.get("inherited_tier"))
                 if t in _routing.TIERS]
        if not tiers:
            continue
        top = max(tiers, key=_routing.tier_rank)
        if best is None or _routing.tier_rank(top) > _routing.tier_rank(best):
            best, sources = top, [exp]
        elif top == best:
            sources.append(exp)
    return best, sources


def _returned_requests(cv, turn) -> list[str]:
    """The requests whose results were returned on this Turn (a run's
    `result-returned` on it), in record order."""
    out = []
    for a in cv.history(turn=turn):
        if a["act"] != RETURNED or not a.get("caused_by"):
            continue
        start = cv._act(a["caused_by"]) or {}
        exp = start.get("caused_by")
        if start.get("act") == STARTED and exp:
            out.append(exp)
    return out


def _is_work_request(act) -> bool:
    """A recorded request for work: not a decision asked of somebody."""
    return (bool(act) and act.get("act") == "expectation-recorded"
            and (act.get("detail") or {}).get("expects") != "decision")


def _recorded_requests(cv, turn) -> list[str]:
    """The requests for work recorded ON this Turn: a delegation Turn's, an
    owner's request Turn's. Never a decision asked on it."""
    try:
        return [a["id"] for a in cv.history(turn=turn) if _is_work_request(a)]
    except Exception:                                     # noqa: BLE001
        return []


def _answered_requests(cv, turn) -> list[str]:
    """The requests this Turn was POSTED AS AN ANSWER TO: its `turn-said`
    act is caused by the request (a run's reply to the work it carries)."""
    out = []
    try:
        acts = cv.history(turn=turn)
    except Exception:                                     # noqa: BLE001
        return out
    for a in acts:
        if a["act"] == "turn-said" and a.get("caused_by") \
                and _is_work_request(cv._act(a["caused_by"])):
            out.append(a["caused_by"])
    return out


def _work_on_turn(cv, turn) -> list[tuple[str, str]]:
    """The work a Turn NAMES, read from the record, as (request, how): a result
    returned on it, a request recorded on it, or a request it answers."""
    out = []
    for how, got in (("a result was returned on", _returned_requests(cv, turn)),
                     ("it answers", _answered_requests(cv, turn)),
                     ("it was requested on", _recorded_requests(cv, turn))):
        out += [(exp, how) for exp in got]
    return out


def _replied_to(cv, turn) -> list[str]:
    """The Turns this Turn replies to (its `replies-to` links)."""
    from mentis.conversation import REPLIES_TO
    try:
        return [e["link"]["to"] for e in cv._c.links(relation=REPLIES_TO,
                                                      frm=turn)
                if (e.get("link") or {}).get("to")]
    except Exception:                                     # noqa: BLE001
        return []


def _conversation_of_request(cv, exp) -> str | None:
    """The Conversation a request belongs to: its act's, else its Turn's."""
    try:
        act = cv._act(exp) or {}
        return act.get("conversation") or (
            cv.conversation_of(act["turn"]) if act.get("turn") else None)
    except Exception:                                     # noqa: BLE001
        return None


def continuation_found(cv, *, parent=None, participant=None, activity=None,
                       references=(), conversation=None) -> list[tuple[str, str]]:
    """The requests a piece of work CONTINUES, read from the record and never
    from words, each with how it was found: `[(request, words)]`.

    * A Turn in `references`, or the Turn it REPLIES TO, names work: a result
      was returned on it, a request was recorded on it (a delegation Turn, an
      owner's request Turn), or it was posted as an answer to a request.
    * The Turn that started `parent` (the request this work is delegated
      under), when it replies to a Turn that names work: so a delegation
      continues what the owner's reply was about without the delegator passing
      references (owner, round 2, 2026-11-12: round 2 of the composer mockups
      was delegated with no lineage to round 1).
    * The earlier delegations under the same `parent` to the same
      `participant` for the same activity (Workflow and key).

    BOUNDED: one reply hop from each referenced Turn and from the parent's
    trigger Turn; chains are never followed. The parent itself is never
    something its own delegation continues (the work is part of it), and
    work in another Conversation than `conversation` (else the parent's) is
    never continued: a reference to it stays a reference."""
    seen: list[tuple[str, str]] = []
    for ref in references or ():
        seen += [(exp, f"{how} {ref}, which this references")
                 for exp, how in _work_on_turn(cv, ref)]
        for to in _replied_to(cv, ref):
            seen += [(exp, f"{how} {to}, which {ref} replies to")
                     for exp, how in _work_on_turn(cv, to)]
    if parent:
        trigger = (cv._act(parent) or {}).get("turn")
        for to in (_replied_to(cv, trigger) if trigger else ()):
            seen += [(exp, f"{how} {to}, which {trigger} (the Turn that "
                           f"started {parent}) replies to")
                     for exp, how in _work_on_turn(cv, to)]

    # THE WHOLE LABEL, Workflow and key: `implement` of another Workflow is
    # other work (found by the final review).
    def _label(said):
        return ("#".join(x.strip() for x in said.split("#"))
                if isinstance(said, str) and said.count("#") == 1 else None)
    mine = _label(activity)
    if parent and participant and mine:
        for a in cv.history(caused_by=parent):
            d = a.get("detail") or {}
            if (a["act"] == "work-delegated" and a.get("about")
                    and d.get("participant") == participant
                    and _label(d.get("activity")) == mine):
                seen.append((a["about"][0], f"delegated earlier under {parent} "
                                            f"to the same participant for "
                                            f"{mine}"))
    # WITHIN ONE CONVERSATION (review, round 2): work in another Conversation
    # is never continued automatically -- a reference to it stays a
    # reference. The Conversation is the one given, else the parent's.
    where = conversation or (_conversation_of_request(cv, parent)
                             if parent else None)
    out: dict = {}
    for exp, how in seen:
        if not exp or exp == parent or exp in out:
            continue
        if where and _conversation_of_request(cv, exp) not in (None, where):
            continue
        out[exp] = how
    return list(out.items())


def continued_requests(cv, *, parent=None, participant=None, activity=None,
                       references=(), conversation=None) -> list[str]:
    """The requests a piece of work CONTINUES (`continuation_found`), ids
    only."""
    return [exp for exp, _ in continuation_found(
        cv, parent=parent, participant=participant, activity=activity,
        references=references, conversation=conversation)]


def _exists(cv, ref) -> bool:
    try:
        return bool(cv._act(ref)) or bool(cv._c.read([ref]))
    except Exception:                                     # noqa: BLE001
        return False


def requests_of_ref(cv, ref) -> list[str]:
    """The requests a `relation_ref` names: a request itself; the request an
    execution's start, or a returned result, was for; the requests whose
    results were returned on a Turn, that a Turn answers, or that a Turn
    recorded. [] when it names none of these (an artifact, a decision)."""
    try:
        act = cv._act(ref)
    except Exception:                                     # noqa: BLE001
        act = None
    if act:
        name = act.get("act")
        if name == "expectation-recorded":
            return [ref]
        if name == STARTED and act.get("caused_by"):
            return [act["caused_by"]]
        if name == RETURNED and act.get("caused_by"):
            start = cv._act(act["caused_by"]) or {}
            return [start["caused_by"]] if start.get("caused_by") else []
        return []
    got = _returned_requests(cv, ref)
    if got:
        return got
    got = _answered_requests(cv, ref)
    if got:
        return got
    try:
        return [a["id"] for a in cv.history(turn=ref)
                if a["act"] == "expectation-recorded"]
    except Exception:                                     # noqa: BLE001
        return []


def owner_approval(cv, ref) -> dict | None:
    """The owner approval `ref` names, as the record holds it, or None:
    `{"ref", "by", "why"}`. An approval is the OWNER's act, never an agent's:

    * `owner_decision` -- an owner decision the owner answered: the
      `decision-answered` act, or the decision question it answers;
    * `owner_verdict` -- the owner's verdict accepting a result
      (`/api/requests/<id>/verdict`): the `result-verdict` act, the request
      whose latest owner verdict accepts it, or the result it accepted;
    * `owner_turn` -- a Turn the owner wrote (the delegator cites the owner's
      words as the approval; recorded as such).

    A design result, or anybody else's post, is not an approval."""
    from mentis.conversation.owner import _owner
    from mentis.evidence import RESULT_VERDICT
    try:
        owner = _owner(cv)
    except Exception:                                     # noqa: BLE001
        owner = None
    if not owner or not ref:
        return None
    try:
        act = cv._act(ref)
    except Exception:                                     # noqa: BLE001
        act = None
    if act:
        name, d = act.get("act"), act.get("detail") or {}
        if name == "decision-answered" and act.get("actor") == owner:
            return {"ref": ref, "by": "owner_decision",
                    "why": f"the owner answered decision {act.get('caused_by')}"}
        if name == RESULT_VERDICT and act.get("actor") == owner:
            return ({"ref": ref, "by": "owner_verdict",
                     "why": "the owner's verdict accepts the result"}
                    if d.get("verdict") == "accepted" else None)
        if name == "expectation-recorded" and d.get("expects") == "decision":
            answered = [a for a in cv.history(caused_by=ref)
                        if a["act"] == "decision-answered"
                        and a.get("actor") == owner]
            return ({"ref": ref, "by": "owner_decision",
                     "why": f"the owner answered it ({answered[-1]['id']})"}
                    if answered else None)
        # A REQUEST, OR A RESULT: the owner's latest verdict on its request.
        about = requests_of_ref(cv, ref)
        if not about:
            return None
        verdicts = [a for a in cv.history(act=RESULT_VERDICT)
                    if a.get("actor") == owner
                    and set(a.get("about") or ()) & set(about)
                    and (name == "expectation-recorded"
                         or (a.get("detail") or {}).get("result") in (None, ref))]
        if verdicts and (verdicts[-1].get("detail") or {}).get("verdict") \
                == "accepted":
            return {"ref": ref, "by": "owner_verdict",
                    "why": f"the owner's verdict {verdicts[-1]['id']} accepts it"}
        return None
    try:
        got = cv._c.read([ref])
    except Exception:                                     # noqa: BLE001
        got = []
    if got and got[0].get("attributed_to") == owner:
        try:
            is_turn = cv._is_kind(ref, "contribution")
        except Exception:                                 # noqa: BLE001
            is_turn = False
        if is_turn:
            return {"ref": ref, "by": "owner_turn",
                    "why": "a Turn the owner wrote, cited as the approval"}
    return None


def inherited_requirements(cv, requests) -> dict | None:
    """What the work these requests carried DEMANDED, for a continuation to
    inherit: `{"solution", "reasoning", "from"}`, the most demanding field by
    field, or None where none said anything. From each request's recorded
    `routing.requirements`, or, for a request recorded before requirements
    existed, `requirements.from_routing`; an advisory tier it was given counts
    as its floor, as `inherited_routing` always read it. Never a model or an
    effort."""
    from mentis.core import requirements as R
    demands, sources = [], []
    for exp in dict.fromkeys(requests or ()):
        stored = execution_scope(cv, exp)["routing"]
        req = (stored["requirements"]
               if isinstance(stored.get("requirements"), dict)
               else R.from_routing(stored))
        got = [R.demand(req)] if req else []
        floor = R.TIER_NEED.get(stored.get("advisory_tier"))
        if floor:
            got.append({"solution": floor[0], "reasoning": floor[1]})
        top = R.strongest(got)
        if top["solution"] or top["reasoning"]:
            demands.append(top)
            sources.append(exp)
    if not demands:
        return None
    return {**R.strongest(demands), "from": sources}


def work_requirements(cv, *, solution=None, reasoning=None, difficulty=None,
                      relation=None, relation_ref=None, exploratory=None,
                      done_when=None, requires=(), parent=None,
                      participant=None, activity=None, references=(),
                      continues=(), scope=None, conversation=None) -> tuple:
    """(the work's requirements, or None when nothing at all was said or
    inherited; warnings for whoever stated them; the requests it continues or
    revises) -- `requirements.derive` over what the record says this work
    continues.

    `continues`/`revises` inherit from what `relation_ref` names, or, with no
    ref, from what the record says this continues (`continuation_found`, and
    the requests in `continues` a caller already found). `implements` must
    name something the record holds, and takes its own requirements only when
    that is an owner approval (`owner_approval`); otherwise it keeps the
    requirements of the work it names and of what the record says it
    continues. `verifies` and `new` inherit nothing; a stated `new` where the
    record shows a continuation is recorded as overriding it. Never a model
    or an effort. Raises `requirements.Invalid` in words a caller can act
    on."""
    from mentis.core import requirements as R
    said = R.check(solution=solution, reasoning=reasoning, relation=relation,
                   relation_ref=relation_ref, exploratory=exploratory,
                   done_when=done_when, scope=scope)
    unknown = [r for r in said["relation_ref"] if not _exists(cv, r)]
    if unknown:
        raise R.Invalid(f"relation_ref {unknown} names nothing this record "
                        f"holds; give the id of the request, returned result "
                        f"or approved artifact/decision it relates to")
    found = dict(
        [(c, "the request this reply continues") for c in continues or () if c]
        + [(e, how) for e, how in continuation_found(
            cv, parent=parent, participant=participant, activity=activity,
            references=references, conversation=conversation) if e])
    found = {e: how for e, how in found.items() if e != parent}
    detected = list(found)
    words = [f"{e}: {how}" for e, how in found.items()]
    rel = said["relation"]
    approval = None
    detected_said = None
    if rel in R.INHERITING:
        named = [x for r in said["relation_ref"] for x in requests_of_ref(cv, r)]
        prior = list(dict.fromkeys(named if said["relation_ref"] else detected))
        continuation = None
    elif rel == "implements":
        approval = next((a for a in (owner_approval(cv, r)
                                     for r in said["relation_ref"]) if a), None)
        if approval:
            prior, continuation = [], None
            if detected:
                detected_said = {"value": "continues", "ref": detected,
                                 "found": words}
        else:
            # NOT APPROVED BY THE OWNER, SO NOT A LEGITIMATE LOWERING: it keeps
            # what the work it names (and what it continues) required.
            named = [x for r in said["relation_ref"]
                     for x in requests_of_ref(cv, r)]
            prior = list(dict.fromkeys(named + detected))
            continuation = None
    elif rel:
        prior, continuation = [], None
        if detected:
            detected_said = {"value": "continues", "ref": detected,
                             "found": words}
    else:
        prior = detected
        continuation = ({"value": "continues", "ref": detected, "found": words}
                        if detected else None)
    inherited = inherited_requirements(cv, prior) if prior else None
    req, warnings = R.derive(
        solution=said["solution"], reasoning=said["reasoning"],
        difficulty=difficulty, relation=rel, relation_ref=said["relation_ref"],
        exploratory=said["exploratory"], done_when=said["done_when"],
        requires=requires, scope=said["scope"], continuation=continuation,
        inherited=inherited, approval=approval, detected=detected_said)
    if req["relation"]["value"] in R.INHERITING and not req["relation"]["ref"]:
        req["relation"]["ref"] = list(prior)
    if rel in R.INHERITING and not prior:
        warnings.append(f"relation {rel!r} was stated, and nothing in the record "
                        f"says what this {rel}, so nothing is inherited. Give "
                        f"relation_ref: the request or returned result it {rel}")
    said_any = any(req[k]["source"] != "default"
                   for k in ("solution", "reasoning", "relation", "exploratory",
                             "scope"))
    return (req if said_any else None), warnings, prior


def need_of(routed, req=None) -> dict:
    """What a run of this request needs of a model (`requirements.need`):
    from the requirements it recorded, with review and authority-sensitive
    work forced and the Workflow's default and an advisory tier as floors; or,
    for a request recorded before requirements existed, exactly the tier it
    resolves to, as it always ran."""
    from mentis.core import requirements as R
    routed = routed or {}
    forced = [s for s in ("review", "authority_sensitive") if routed.get(s)]
    if isinstance(routed.get("requirements"), dict) or (req and not routed):
        return R.need(req if req is not None else routed["requirements"],
                      forced=forced,
                      floors=[("workflow_default",
                               routed.get("workflow_default_tier")),
                              ("advisory", routed.get("advisory_tier"))])
    tier = routed.get("required_tier") or _routing.DEFAULT_TIER
    sources = list(routed.get("tier_sources") or ["default"])
    got = R.need_of_tier(tier)
    return {**got, "soft": "default" in sources, "sources": sources}


def standing_of(cv) -> list:
    """The owner's standing suitability for this record, read here (selection
    never reads the record itself); the legacy table alone if it cannot be."""
    from mentis.core import selection as _sel
    try:
        return _sel.standing(cv)
    except Exception:                                     # noqa: BLE001
        return _sel.standing(None)


def _req_from_routing(routed):
    from mentis.core import requirements as R
    return R.from_routing(routed) if routed else None


def _selection_kwargs(svc, **kw) -> dict:
    """The requirement-aware arguments, for an agent service that takes them
    (a test double written before them may not)."""
    import inspect
    try:
        params = inspect.signature(svc.execution_select).parameters
    except (TypeError, ValueError):
        return kw
    if any(p.kind is p.VAR_KEYWORD for p in params.values()):
        return kw
    return {k: v for k, v in kw.items() if k in params}


def routing_now(cv, expectation, *, persona=None, difficulty=None) -> dict | None:
    """`routing_inputs` for a run of this request: from what the request
    recorded, so a resumed run keeps the first one's floor. A request recorded
    before any of this still reads its Persona, repository and activity.
    A RESUMED RUN KEEPS ITS REQUIREMENTS: what the request recorded
    (`routing.requirements`) is read back, never derived again."""
    stored = execution_scope(cv, expectation)["routing"]
    return routing_inputs(
        cv, difficulty=stored.get("difficulty") or difficulty,
        authority_sensitive=stored.get("authority_sensitive"),
        advisory_tier=stored.get("advisory_tier"),
        advisory_by=stored.get("advisory_by"),
        activity=cv.activity_named(expectation), persona=persona,
        repository=declared(cv, expectation),
        workflow_tier=stored.get("workflow_default_tier"),
        inherited_tier=stored.get("inherited_tier"),
        inherited_from=stored.get("inherited_from"),
        requirements=(stored["requirements"]
                      if isinstance(stored.get("requirements"), dict) else None))


def field_sources_of(runtime_source, *, runtime=None, model=None, effort=None) -> dict:
    """`field_sources` for what a request names: one source per field it fixes.
    A model or effort is only ever named; only a runtime has other sources."""
    return {**({"runtime": runtime_source or "named"} if runtime else {}),
            **({"model": "named"} if model else {}),
            **({"effort": "named"} if effort else {})}


#: How each kind of recorded runtime binds, other than being named for the work.
_RUNTIME_BINDS = {"participant-default": "preference",
                  "continued": "continued-bound",
                  "reassigned": "reassigned-bound"}


def field_provenance(cv, said, binding, *, model, effort, selection,
                     routed=None) -> dict:
    """Where a run's runtime, model and effort each came from and how each binds:
    `{field: {"source", "binding", "basis"?, "supplied_by"?}}`.

    OWNER-BOUND IS CLAIMED, FIELD BY FIELD. `owner-bound_claimed` only where that
    field's source is `named` and that field's own basis is a Turn the owner
    wrote: the code does not read the Turn's wording, so it is a claim, with who
    supplied it and the basis there to inspect. Every other named field is
    `carrier-bound`. A request recorded before field sources existed says neither,
    so it reads carrier-bound whoever posted it: the cautious error, changing no
    behaviour. A field the tier filled is `advisory` when an advisory tier decided
    it, `routed` otherwise; `automatic` is the capacity ranking's."""
    from mentis.conversation.owner import _owner
    sources = said.get("field_sources")
    bases = said.get("constraint_bases") or {}
    tiered = ("advisory" if "advisory" in ((routed or {}).get("tier_sources") or ())
              else "routed")

    def named(field):
        basis = bases.get(field) or (said.get("basis") if field == "runtime" else None)
        owned = False
        if isinstance(sources, dict) and sources.get(field) == "named" \
                and bases.get(field):
            got = cv._c.read([bases[field]])
            owner = _owner(cv)
            owned = bool(got and owner and got[0].get("attributed_to") == owner)
        return {"source": "named",
                "binding": "owner-bound_claimed" if owned else "carrier-bound",
                **({"basis": basis} if basis else {}),
                **({"supplied_by": said["supplied_by"]}
                   if said.get("supplied_by") else {})}

    def chosen(value, by_tier):
        if not value:
            return {"source": "runtime-default", "binding": None}
        return ({"source": "tier", "binding": tiered} if by_tier
                else {"source": "automatic", "binding": "automatic"})

    tier_met = bool(((selection.inputs or {}).get("routing") or {}).get("selected_tier"))
    if binding.get("runtime"):
        source = binding.get("source") or "named"
        runtime = (named("runtime") if source == "named" else
                   {"source": source,
                    "binding": _RUNTIME_BINDS.get(source, "carrier-bound"),
                    **({"basis": binding["act"]} if binding.get("act") else {}),
                    **({"declaration": binding["declaration"]}
                       if binding.get("declaration") else {}),
                    **({"continues": binding["continues"]}
                       if binding.get("continues") else {})})
    else:
        runtime = chosen(selection.runtime, tier_met)
    return {"runtime": runtime,
            "model": named("model") if model else chosen(selection.model, True),
            "effort": named("effort") if effort
            else chosen(selection.requested_effort, True)}


def option_failure(evidence, sources) -> str | None:
    """What a run's failure says about the catalogue, or None.

    ONLY WHAT MARS STRUCTURED, AND ONLY AN OPTION NOBODY NAMED. `option` is MARS
    saying a requested model or effort is not offered; no message is ever read for
    this. Where the tier chose that option the catalogue moved under a selection
    that read it. A named one failing is a wrong or retired name, not a change in
    the catalogue, and stays an ordinary failure with its evidence."""
    option = (evidence or {}).get("option")
    if option not in ("model", "effort") or (sources or {}).get(option) != "tier":
        return None
    return f"{option}_unavailable/catalogue_changed"


def declared(cv, expectation) -> dict | str | None:
    """The request's repository declaration, or None: repository access is
    never inferred from the work's words.

    Its own record, when it was made with one; or, for discovered work
    somebody PICKED UP, the latest pick-up -- the assigning act, because the
    discovered request's own record is never rewritten. (Moved from Mark IV's
    `worktrees.declared`, which read the same two places.)
    """
    if not expectation:
        return None
    exp = cv._act(expectation)
    if exp is None or exp["act"] != "expectation-recorded":
        return None
    picked = [a for a in cv.history(caused_by=expectation)
              if a["act"] == "expectation-assigned"
              and (a["detail"] or {}).get("picked_up_under")]
    if picked:
        return (picked[-1]["detail"] or {}).get("repository")
    return (exp.get("detail") or {}).get("repository")


class WorkspaceRefused(ValueError):
    """A request declared a repository directory that cannot be worked in."""


def declared_workspace(cv, expectation) -> str | None:
    """The directory this request declared as its repository, or None.

    A declaration names a directory as a string or as `{"path": ...}`. One
    that names none -- Mark IV's `true`, `{"base": <branch>}`, a review --
    declares no directory, and the run works in the server's workspace. A
    directory that is named and does not exist is refused, in words, rather
    than quietly replaced by another.
    """
    decl = declared(cv, expectation)
    where = (decl if isinstance(decl, str)
             else decl.get("path") if isinstance(decl, dict) else None)
    if not where:
        return None
    if not os.path.isabs(where) or not os.path.isdir(where):
        raise WorkspaceRefused(
            f"this request declares the repository directory {where!r}, which "
            f"is not an existing absolute directory on this machine")
    return os.path.normpath(where)


def review_signal(cv, expectation, persona) -> tuple[bool, str | None, str]:
    """Whether this run is review work, the runtime the reviewed work ran on
    if its lineage says, and how that was established.

    REVIEW IS WHAT THE RUN WEARS OR DECLARES: a Persona whose established name
    says review ("Reviewer", "Independent Reviewer"), or a request declared as
    reviewing another (`repository: {"review_of": <request>}`), whatever it
    wears. Never the Participant's alias, and never a binding: the same
    Participant doing other work selects as ordinary, and a Reviewer reviewing
    work whose author is unknown avoids nothing.

    THE AUTHOR IS READ FROM LINEAGE, not guessed: `review_of` names the
    request, and that request's latest run says which runtime authored it.
    """
    decl = declared(cv, expectation) if expectation else None
    return review_signal_of(cv, persona, decl)


def _persona_name(cv, persona) -> str:
    """The established name of a Persona, or "" for none."""
    if not persona:
        return ""
    try:
        got = cv._c.read([persona])
    except Exception:                                     # noqa: BLE001
        got = []
    return str(((got[0].get("body") or {}).get("name") or "")) if got else ""


def review_signal_of(cv, persona, repository) -> tuple[bool, str | None, str]:
    """`review_signal` for work whose request is not recorded yet: the
    Persona it will wear and the repository declaration it will carry
    (`{"review_of": <request>}` for a review). The same answer, read the same
    way, so a request and its run cannot disagree about whether it is review
    or whose runtime it would avoid."""
    name = _persona_name(cv, persona)
    worn = "review" in name.lower()
    author = (repository["review_of"] if isinstance(repository, dict)
              and isinstance(repository.get("review_of"), str)
              and repository["review_of"] else None)
    if not (worn or author):
        return False, None, ""
    label = name if worn else "declared review_of"
    runs = ([a for a in cv.history(caused_by=author)
             if a["act"] == "execution-started" and a.get("runtime")]
            if author else [])
    if not runs:
        return True, None, (
            f"review work ({label}); the reviewed work's runtime is not known "
            f"from its lineage, so no runtime was avoided")
    ran = max(runs, key=lambda a: a["at"])["runtime"]
    return True, ran, f"review work ({label}) of {author}, which ran on {ran}"


def yields_to(cv, persona, author) -> str | None:
    """The reviewed work's runtime as `yield_to_review` should read it. A
    default gives way on a review Persona or on a `review_of` wearing none; a
    Persona that does not say review (a Builder extending the work it names)
    keeps its Participant's default, and only selection avoids the author."""
    if persona and "review" not in _persona_name(cv, persona).lower():
        return None
    return author


def yield_to_review(binding, author) -> dict:
    """The binding after review separation is asked of it.

    A PARTICIPANT'S DEFAULT GIVES WAY TO INDEPENDENT REVIEW (owner ruling,
    2026-10-29). When the work is review and its runtime is fixed ONLY by the
    Participant's declared default -- resolved now, or recorded earlier as
    `participant-default` -- and that default is the runtime the reviewed
    work ran on, the default yields: the runtime is left unbound, so
    selection runs with the author's runtime avoided, and `yielded` says why.
    Asked before anything is recorded from the binding, so no record says the
    work was bound to the default it gave way to.

    Anything else is returned unchanged. A runtime that was named, continued,
    reassigned, or carried by a legacy constraint with no source (read as
    named) stays fixed; `review_conflict` says when that defeats separation.
    """
    if (not author or not binding.get("runtime")
            or binding.get("source") != "participant-default"
            or binding["runtime"] != author):
        return binding
    return {"runtime": None, "source": "auto",
            **({"declaration": binding["declaration"]}
               if binding.get("declaration") else {}),
            "preferred": author,
            "yielded": (f"the participant's default {author} yields: the "
                        f"reviewed work ran on {author}")}


def review_conflict(binding, author) -> str | None:
    """Words disclosing that a runtime which stays fixed is the reviewed
    work's own runtime, or None. Said on the record and to whoever delegated
    the review, never resolved by substituting another runtime."""
    rt = binding.get("runtime")
    if not author or not rt or rt != author:
        return None
    return (f"runtime {rt} is fixed ({binding.get('source') or 'named'}) and "
            f"is the runtime the reviewed work ran on, so this review is not "
            f"independent by runtime")


def resolve_runtime(cv, *, participant, expectation=None, named=None,
                    continues=None, judge=None) -> dict:
    """Which runtime this work runs on, and on what basis. One function,
    because recording a request and running it must not be able to disagree.

    IN THIS ORDER, and the first answer binds:
      * `named` -- a runtime the caller chose for this work;
      * what the request is already bound to (`recorded_runtime`);
      * `continues` -- the request this one continues, when the same carrier
        is carrying it on, so continuing work does not quietly lose its
        runtime;
      * the Participant's DECLARED default (`runtime_default_of`) -- a
        person's declaration, never the alias. A PREFERENCE (owner ruling,
        capacity-aware selection): given a `judge` (`runtime_judge`), it
        binds only when that runtime could take the work now; otherwise
        this is runtime-auto, carrying `preferred` and why it was
        `declined`. Once it binds, it binds as before;
      * otherwise runtime-auto: selection's ordinary rule, said as such.

    A NAMED RUNTIME THAT DISAGREES WITH THE BINDING IS REFUSED, not obeyed and
    not ignored: either answer would run the work somewhere it was not bound.
    """
    recorded = recorded_runtime(cv, expectation)
    if named:
        if recorded and recorded["runtime"] != named:
            raise RuntimeConflict(
                f"this request is bound to runtime {recorded['runtime']!r} "
                f"({recorded['source']}); refusing to run it on {named!r}")
        return recorded or {"runtime": named, "source": "named"}
    if recorded:
        # A DEFAULT RECORDED EARLIER IS STILL A PREFERENCE: judged again, so a
        # request whose default runtime has since hit its quota is not run there
        # again (found by the independent review). Named, continued and
        # reassigned bindings stay fixed.
        if recorded.get("source") == "participant-default" and judge:
            declined = judge(recorded["runtime"])
            if declined:
                return {"runtime": None, "source": "auto",
                        "preferred": recorded["runtime"], "declined": declined,
                        **({"declaration": recorded["declaration"]}
                           if recorded.get("declaration") else {})}
        return recorded
    inherited = recorded_runtime(cv, continues) if continues else None
    if inherited:
        return {**inherited, "source": "continued", "act": None,
                "continues": continues}
    declared = cv.runtime_default_of(participant) if participant else None
    if declared and declared["runtime"]:
        declined = judge(declared["runtime"]) if judge else None
        if not declined:
            return {"runtime": declared["runtime"],
                    "source": "participant-default",
                    "declaration": declared["declaration"]}
        return {"runtime": None, "source": "auto",
                "declaration": declared["declaration"],
                "preferred": declared["runtime"], "declined": declined}
    return {"runtime": None,
            "source": "declared-auto" if declared else "auto",
            **({"declaration": declared["declaration"]} if declared else {})}


def constraint_of(binding, *, supplied_by, basis=None, model=None,
                  effort=None, requires=()) -> dict | None:
    """The `constraints` a request records for this binding, or None when
    nothing is constrained. The same shape `delegate` already writes.

    `model` and `effort` are only what THIS request was asked with. They are
    recorded as said, and never taken from the binding: the binding is the
    runtime alone (see `recorded_runtime`). `source` is the runtime's; the
    per-field record (`field_sources`, `constraint_bases`) is the same one
    `delegate` writes, and `basis` cites what named each field, so a default
    resolved here is not read as chosen on this Turn."""
    if not (binding.get("runtime") or model or effort):
        return None
    sources = field_sources_of(binding["source"], runtime=binding.get("runtime"),
                               model=model, effort=effort)
    return {"runtime": binding.get("runtime"), "model": model,
            "effort": effort, "requires": list(requires or ()),
            "supplied_by": supplied_by, "basis": basis,
            "source": binding["source"],
            "field_sources": sources,
            **({"constraint_bases": {f: basis for f, s in sources.items()
                                     if s == "named"}} if basis else {}),
            **({"declaration": binding["declaration"]}
               if binding.get("declaration") else {}),
            **({"continues": binding["continues"]}
               if binding.get("continues") else {})}


class RequestWithdrawn(Exception):
    """A run was asked for on a request that has been withdrawn. Refused:
    withdrawing says the work is off (owner decision, ent-750df9aa168c)."""


def withdrawal_of(cv, expectation) -> dict | None:
    """The act that withdrew this request, or None.

    BY ANYBODY, which is why this does not read `expectation_state`: its
    `withdrawn` is only its current carrier's, and a request the owner takes
    back from the agent carrying it is withdrawn all the same. Only a withdrawal
    counts. A request met or lapsed is not ruled on here, and nor is one whose
    Turn was deleted (`versions`): those are undecided.
    """
    if not expectation:
        return None
    return next((a for a in cv.history(caused_by=expectation)
                 if a["act"] == "expectation-met"
                 and (a["detail"] or {}).get("withdrawn")), None)


def _refuse_withdrawn(cv, gone, *, participant, conversation, turn, expectation,
                      requested) -> dict:
    """Refuse a start on a withdrawn request, in the record and to the caller.

    NOT SILENT, AND NOTHING NEW TO READ: a `delivery-failed` on the request like
    every failure before a start, saying who withdrew it and why. The post shows
    it as the request's failure, the work view as a run that failed before it
    started, and what was waiting on this request hears how it ended. The request
    stays closed by its withdrawal. Nothing is retried.
    """
    said = (gone.get("because") or "").strip()
    why = (f"no run was started: {cv.alias(gone['actor'])} withdrew this "
           f"request" + (f" ({said})" if said else ""))
    act = _failed_before_start(
        cv, participant=participant, conversation=conversation, turn=turn,
        expectation=expectation, stage="request-withdrawn",
        exc=RequestWithdrawn(why), requested=requested,
        withdrawal=gone["id"])
    return {"ok": False, "why": why, "failed_act": act,
            "before_execution_started": True, "withdrawal": gone["id"]}


def _failed_before_start(cv, *, participant, conversation, turn, expectation,
                         stage, exc, requested, withdrawal=None) -> str:
    """Record a failure that happened before anything ran.

    WHY THIS EXISTS. Selection, resolution and summoning all sit before the
    first recorded act, and every one of them can fail: a runtime absent, a
    requirement nothing declares, a workspace that will not open. All of it used
    to raise out of a daemon thread into a printed traceback, so the request
    stayed owed with NOTHING in the record saying why nobody was coming. That is
    the worst shape a failure can have -- indistinguishable from work still in
    progress.

    No execution and no delivery is named, because none happened. What is named
    is the expectation, so the failure is findable from the request it belongs
    to rather than only in a log.
    """
    return cv.record_act(
        actor=participant, act=FAILED, conversation=conversation, turn=turn,
        caused_by=expectation,
        because=f"{type(exc).__name__}: {exc}",
        detail={"stage": stage, "before_execution_started": True,
                "requested": dict(requested),
                **({"withdrawal": withdrawal} if withdrawal else {}),
                "traceback": traceback.format_exc()[-600:]})


#: RUNS WHOSE WAITER IS IN THIS PROCESS NOW, by their `execution-started` act.
#: From the moment the start is recorded until `dispatch` has finished writing
#: its end -- which is later than the instance stops being busy, so an
#: instance's liveness alone cannot say whether a waiter is still about to
#: write. `result-recovered` refuses any run named here: its end is not lost.
IN_FLIGHT: set = set()
_here = threading.local()


class _Clock:
    """A dispatch's timing spans (WS-P, `detail.timing`): the contract's
    named instants, plus `steps`, each step before selection and between the
    start and the perform, so a slow segment can be attributed. Epoch
    seconds; one `time.time()` per mark."""

    def __init__(self, triggered_at: float | None) -> None:
        now = time.time()
        self.spans: dict = {"triggered_at": triggered_at or now,
                            "dispatch_began": now, "steps": {}}

    def mark(self, name: str) -> None:
        self.spans[name] = time.time()

    def step(self, name: str) -> None:
        self.spans["steps"][name] = time.time()

    def record(self) -> dict:
        return {**self.spans, "steps": dict(self.spans["steps"])}


def _redact_call(call):
    from mentis.redaction import redact_call
    return redact_call(call)


def dispatch(st, **kw) -> dict:
    """Run one dispatch, then ask whether its ending lets waiting work resume.

    The check runs however the run ended -- a result, a failure, a refusal
    before anything started, or an exception -- because each of those ends the
    wait on this child, and none of them says the child's work was adequate.
    """
    try:
        return _dispatch(st, **kw)
    finally:
        began = getattr(_here, "started", None)
        if began:
            IN_FLIGHT.discard(began)
            _here.started = None
            # THE RUN'S LEASES END WITH IT (`operational.leases`, WS-L).
            # Never raises; an end hook that failed still ends them by reading.
            from mentis.operational import leases as _leases
            _leases.end_run(getattr(st, "cv", None), began)
        # A RUN STOPPED BECAUSE ITS COMPILED PERMISSION RULES WENT STALE (the
        # owner narrowed its consent) continues in a fresh session, with the
        # context it was dispatched with (`compiled_runs`, WS-A). Its work has
        # not ended -- restarted or held -- so nothing waiting on it resumes,
        # and no claim it was holding is reconciled over it.
        restarted = None
        if began:
            try:
                from mentis.web import compiled_runs
                restarted = compiled_runs.restart_if_asked(st, began, dispatched=kw)
            except Exception:                             # noqa: BLE001
                traceback.print_exc()
        # A CLAIM OF MET THIS RUN'S ENDING WAS HOLDING (`completion`, rule
        # 3): the work it was delegated under, or that awaits it, claimed
        # met and was waiting only for this to end. Reconciled BEFORE
        # resumption is asked, so work recorded met now is not run again
        # (`claim_resumption` passes over met work); work still held is
        # resumed exactly as before.
        if not restarted:
            if kw.get("expectation"):
                from mentis.operational import completion as _completion
                _completion.reconcile_held_by_quietly(st.cv, kw["expectation"])
            resume_if_ready(st, kw.get("expectation"))


def resume_if_ready(st, expectation) -> list[str]:
    """Resume whatever was waiting on this run, if it no longer waits on
    anything. Returns the `work-resumed` acts written, usually none.

    THREE KINDS OF CANDIDATE. The work this run's request was raised under
    -- a child finishing may end its parent's wait -- and the request itself,
    because a child that finished while its parent was still running was
    refused then for exactly that reason, and the parent's own run ending is
    the moment that refusal stops applying. And any work that declared it
    waits on this request (`await_work`): this run may have claimed it met or
    left it stopped, and nothing else will ever say so to what was waiting.
    A candidate that does not resume may have stopped by this run ending, with
    no run of its own to say so, so what waits on it is asked in turn, and the
    request it continues, which is the same work; one that resumed is about to
    run and has not stopped. None is a poll or a queue:
    this is the end of a run that already happened, asking one question of the
    record.

    WHAT RESUMES IS THE SAME WORK. The parent expectation, dispatched to
    whoever carries it NOW, under the authority recorded for it. Nothing is
    minted, and nothing is read from the child, a Persona or the session.
    """
    if not expectation:
        return []
    cv = st.cv
    made = []
    try:
        own = cv._act(expectation)
    except Exception:
        return []
    if own is None:
        return []
    try:
        waiters = cv.awaited_by(expectation)
    except Exception as exc:                              # noqa: BLE001
        # LOSING EVERY WAITER AT ONCE IS NOT THE SAME AS LOSING ONE. The
        # per-candidate `except` below drops a single resumption; this one
        # drops the whole set, and because nothing polls, each of them waits
        # for a wake-up that will now never come. A printed traceback in a
        # dispatch thread is the failure shape this file already names as the
        # worst: the work stayed owed with nothing in the record saying why
        # nobody was coming. So it is said in the record as well.
        traceback.print_exc()
        waiters = []
        try:
            cv.record_act(
                actor=own.get("actor"),
                act="problem-noticed", conversation=own.get("conversation"),
                turn=own.get("turn"), caused_by=expectation,
                because="reading which work awaited this one failed, so any "
                        "work waiting on it was not resumed and nothing will "
                        "retry: continuing it is somebody's act",
                detail={"error": f"{type(exc).__name__}: {exc}",
                        "awaited_expectation": expectation})
        except Exception:                                 # noqa: BLE001
            traceback.print_exc()
    # NOTHING IS SENT ELSEWHERE HERE. Continuing work on another agent is
    # somebody's act -- re-addressing the request, `continues`, `delegate` --
    # never a heuristic at the end of a run.
    candidates = [(own.get("caused_by"), "child-ended", expectation),
                  (expectation, "own-run-ended", expectation),
                  *((w, "awaited-run-ended", expectation) for w in waiters)]
    asked = set()
    while candidates:
        parent, event, ended = candidates.pop(0)
        if not parent or parent in asked:
            continue
        asked.add(parent)
        try:
            act = cv.claim_resumption(parent, event={"kind": event,
                                                    "expectation": ended})
        except Exception:
            traceback.print_exc()
            continue
        if act is None:
            try:
                if cv._stopped(parent):
                    candidates += [(w, "awaited-run-ended", parent)
                                   for w in cv.awaited_by(parent)]
                    over = (cv._act(parent) or {}).get("caused_by")
                    if over and parent in cv.continuations_of(over):
                        candidates.append((over, "child-ended", parent))
            except Exception:
                traceback.print_exc()
            continue
        made.append(act)
        _resume(st, parent, act)
    # A RUN ENDING IS ALSO WHEN A TRUNK CAN BECOME FINISHED: its carrier
    # claimed it met in this run, or this was the last thing it waited on.
    # The owner is then asked, once, about what was found along the way.
    try:
        from mentis.operational import reconsider_after
        reconsider_after(st.brain, expectation)
    except Exception:
        traceback.print_exc()
    return made


#: The owner chose to leave a request where it stopped (`retry_if_chosen`).
#: Stage reads it as parked.
WORK_PARKED = "work-parked"
#: The `detail.recovery` of a question asking the owner whether to retry or
#: park a request whose runs ended with nothing reported. Mark IV asked it
#: from its recovery heuristics, which are gone; a question already in the
#: record is still answered by `retry_if_chosen`.
EMPTY_RUN_REVIEW = "empty-run"
EMPTY_RUN_OPTIONS = [
    {"label": "retry",
     "consequence": "the same request is dispatched to its carrier again, "
                    "with the model and effort it was asked with, on the "
                    "runtime its binding or its carrier's default names, or "
                    "else the one selection picks"},
    {"label": "park",
     "consequence": "it stays where it stopped, read as parked, until you "
                    "say to continue"},
]


#: The owner chose to retry a request that had ended with nothing reported
#: (`retry_if_chosen`); the request is dispatched again, unbound.
WORK_RETRIED = "work-retried"


def retry_if_chosen(cv, chose, *, by, turn) -> list[dict]:
    """What the owner's answer to an empty-run question starts: the dispatch
    of the same request to its carrier again (option 0, `work-retried`), or
    nothing, with the request recorded parked (option 1, `work-parked`).
    Any other question, a withdrawal, an answer by anybody but the person
    asked, or a question already acted on starts nothing. Returned as the
    keyword arguments of the dispatch, for the caller to start once the
    answering Turn is durable (`posting.post`).

    THE REQUEST'S OWN CONSTRAINTS TRAVEL WITH THE RETRY: the model and effort
    it was asked with are sent again (found by review: a retry dropped them,
    which Mark IV's recovery also refused to do), as `_dispatch` would read them
    anyway. The runtime is whatever `recorded_runtime` says once the
    reassignment is released.
    """
    if not isinstance(chose, dict) or chose.get("withdraw")             or chose.get("option") is None:
        return []
    asked = cv._act(chose.get("expectation"))
    d = (asked or {}).get("detail") or {}
    if asked is None or d.get("recovery") != EMPTY_RUN_REVIEW:
        return []
    # ONLY THE PERSON IT WAS ASKED OF (found by review: anybody's reply
    # choosing "retry" dispatched the work).
    if cv.expectation_state(asked["id"])["expected_of"] != by:
        return []
    child = d.get("retry_of")
    exp = cv._act(child) if child else None
    if exp is None:
        return []
    # ONCE PER QUESTION (found by review: choosing "retry" twice dispatched
    # twice).
    if any(a["act"] in (WORK_RETRIED, WORK_PARKED)
           and (a.get("detail") or {}).get("asked") == asked["id"]
           for a in cv.history(caused_by=child)):
        return []
    if int(chose["option"]) != 0:
        cv.record_act(actor=by, act=WORK_PARKED,
                      conversation=exp["conversation"], turn=exp["turn"],
                      caused_by=child, about=[child],
                      because="the owner chose to park it after its runs "
                              "ended with nothing reported",
                      detail={"asked": asked["id"], "reply": turn})
        return []
    carrier = d.get("carrier") or cv.assigned_carrier(child)["carrier"]
    if not carrier:
        return []
    requires = recorded_requires(cv, child)
    said = execution_scope(cv, child)["constraints"]
    act = cv.record_act(actor=by, act=WORK_RETRIED,
                        conversation=exp["conversation"], turn=exp["turn"],
                        caused_by=child, about=[child],
                        because="the owner chose to retry it after its runs "
                                "ended with nothing reported",
                        detail={"asked": asked["id"], "reply": turn,
                                "to_requires": list(requires),
                                "model": said.get("model"),
                                "effort": said.get("effort")})
    from mentis.conversation.versions import flow_text
    got = cv._c.read([exp["turn"]])
    words = flow_text(got[0]["body"].get("parts")) if got else ""
    persona = next((a["detail"].get("persona") for a in sorted(
        cv.history(caused_by=child), key=lambda a: a["at"], reverse=True)
        if a["act"] == ASSIGNING and (a.get("detail") or {}).get("persona")),
        None) or delegated_persona(cv, child) \
        or ((cv._act(child) or {}).get("detail") or {}).get("persona") \
        or started_persona(cv, child, carrier)
    # (a delegated child keeps its step's Persona; a directly addressed
    # request keeps the one it recorded -- designated or chosen -- found by
    # the independent review: a retry ran as nobody)
    return [dict(
        conversation=exp["conversation"], turn=exp["turn"],
        participant=carrier, persona=persona, expectation=child,
        requires=tuple(requires),
        model=said.get("model"), effort=said.get("effort"),
        work=(f"The owner chose to retry this work ({act}) after its runs "
              f"ended with nothing reported. Do the work as asked, and end "
              f"your run with a written report.\n\n{words}"),
        # matched against the request's words, not the retry's preamble
        question=words or None,
        because=f"retried by the owner's choice {asked['id']}")]


def _not_reassigned(cv, child) -> list[str]:
    """The `blocked: ...` line for a child whose latest end could not be
    sent elsewhere (a `work-not-reassigned` act in the record), or nothing."""
    try:
        acts = cv.history(caused_by=child)
    except Exception:                                     # noqa: BLE001
        return []
    gone = [a for a in acts if a["act"] == WORK_NOT_REASSIGNED]
    if not gone:
        return []
    latest = max(gone, key=lambda a: a["at"])
    if any(a["act"] == WORK_REASSIGNED and a["at"] > latest["at"]
           for a in acts):
        return []
    from mentis.conversation import RUN_ENDS
    ends = [a for a in cv._own_acts(child) if a["act"] in RUN_ENDS]
    if not ends or max(ends, key=lambda a: a["at"])["id"] != (
            latest.get("detail") or {}).get("ended_by"):
        return []                       # about an earlier end, not this one
    line = (latest.get("detail") or {}).get("line")
    return [line] if line else []


def _resume(st, parent, resumed_act):
    """Dispatch the SAME parent expectation, telling its carrier what ended."""
    import mentis.web as web            # the one door every dispatch uses
    web.dispatch_soon(st, **resume_dispatch(st.cv, parent, resumed_act))


def started_persona(cv, expectation, carrier) -> str | None:
    """The Persona this carrier's latest run of this request was started
    with, or None. A Persona the owner chose when posting is recorded only on
    the run's `execution-started` act (`address_for` carries it, no assignment
    act does), so a carrier resumed after its children returned came back
    wearing none -- found by dispatching for real (2026-10-29). Carrying it on
    is carrying the owner's own choice, not making one."""
    runs = [a for a in cv.history(caused_by=expectation)
            if a["act"] == STARTED and a.get("actor") == carrier
            and (a.get("detail") or {}).get("persona")]
    return max(runs, key=lambda a: a["at"])["detail"]["persona"] if runs else None


def delegated_persona(cv, expectation) -> str | None:
    """The Persona the delegation of this request recorded, or None.

    A delegated child's Persona is recorded on its `work-delegated` act, not
    on an assigning act: `delegate` writes no `expectation-assigned` for a new
    child, and a pick-up's assignment does not carry it. So a resumed child
    whose Persona was read only from assignments came back wearing none --
    and with delegation by activity giving children their step's Persona
    (owner ruling 2026-10-29), that would drop it exactly when the child
    resumes. Read from the delegating act(s): the one under the request that
    caused it, and under any request that picked it up. The newest wins.
    """
    exp = cv._act(expectation)
    if exp is None:
        return None
    under = [exp.get("caused_by")] + [
        (a.get("detail") or {}).get("picked_up_under")
        for a in cv.history(caused_by=expectation)
        if a["act"] == ASSIGNING]
    acts = [a for u in dict.fromkeys(x for x in under if x)
            for a in cv.history(caused_by=u)
            if a["act"] == "work-delegated"
            and expectation in (a.get("about") or ())]
    return next((a["detail"].get("persona") for a in sorted(
        acts, key=lambda a: a["at"], reverse=True)
        if (a.get("detail") or {}).get("persona")), None)


def request_words(cv, expectation, *, limit: int | None = None) -> str:
    """The words of the post this request was asked on (`flow_text` of its
    Turn), or "" when there is none to read. What a resume or a retry is
    matched against (`_dispatch`'s `question`).

    AS MENTIS SHOWS THE POST NOW (review M4, `versions.presented`): an edited
    post's current words, nothing for a deleted one. `limit` cuts the words."""
    from mentis.conversation.versions import flow_text, presented
    exp = cv._act(expectation) if expectation else None
    if not exp or not exp.get("turn"):
        return ""
    try:
        got = cv._c.read([exp["turn"]])
        entry = presented(cv._c, got[0]) if got else None
    except Exception:                                     # noqa: BLE001
        return ""
    if not entry or entry.get("deleted"):
        return ""
    words = flow_text((entry.get("body") or {}).get("parts"))
    return words[:limit] if limit is not None else words


def _references_on(cv, exp) -> list[str]:
    """The posts one request's delegation referenced: its latest pick-up's,
    for discovered work somebody picked up, else its own record's (as
    `declared` reads a repository)."""
    picked = [a for a in cv.history(caused_by=exp["id"])
              if a["act"] == "expectation-assigned"
              and (a["detail"] or {}).get("picked_up_under")]
    if picked:
        return list((picked[-1]["detail"] or {}).get("references") or ())
    return list((exp.get("detail") or {}).get("references") or ())


def referenced_posts(cv, expectation) -> list[dict]:
    """The posts a DELEGATED run's work answers to, as they now read.

    THE ORIGINAL REQUEST FIRST -- the top of the lineage (`operational.
    discovery`) -- then the posts delegations on the way down referenced
    (`delegate`'s `references`), the furthest ancestor's first, each once. So
    a child of a child is told what its parent was told without the parent
    copying it on. Nothing for work a person asked for directly: its own post
    is its work.

    A FINDING STARTS ITS OWN PART. Discovered work picked up is told the
    original request and what its own pick-up referenced, never what was
    referenced for the work it was found under: that was about another part
    (found by independent review).

    REFERENCES, NOT COPIES (owner, 2026-10-30, from opr-49e8e40d7fa2). Each is
    its number, author, time, Conversation and opening words; the run reads
    it with `resolve`, which gives it as it now stands. Read from the record
    on every run of the request, so a resumed or retried run is told the
    same posts."""
    from mentis.artifacts import _delegation
    from mentis.conversation.versions import flow_text, presented
    exp = cv._act(expectation) if expectation else None
    if (not exp or exp["act"] != "expectation-recorded"
            or _delegation(cv, exp) is None):
        return []
    chain, cur, seen, collecting = [], exp, set(), True
    while (cur is not None and cur["act"] == "expectation-recorded"
           and cur["id"] not in seen):
        seen.add(cur["id"])
        chain.append((cur, collecting))
        if cv.is_finding(cur["id"]):
            collecting = False
        cur = cv._act(cur["caused_by"]) if cur.get("caused_by") else None
    top = chain[-1][0]
    order = [(top["turn"], "the original request")] + [
        (ref, "referenced for this work" if a is exp
         else "referenced for the work above yours")
        for a, kept in reversed(chain) if kept
        for ref in _references_on(cv, a)]
    out, said = [], {exp["turn"]}
    with cv.reading():
        for ref, why in order:
            if not ref or ref in said:
                continue
            said.add(ref)
            got = cv._c.read([ref])
            if not got:
                out.append({"ref": ref, "why": why, "known": False})
                continue
            e = presented(cv._c, got[0])
            words = " ".join(flow_text((e.get("body") or {}).get("parts"))
                             .split())
            where = cv.conversation_of(ref)
            out.append({"ref": ref, "why": why, "known": True,
                        "original": why == "the original request",
                        "number": cv.turn_number(ref),
                        "author": cv.alias(e.get("attributed_to")),
                        "at": e.get("recorded_at"),
                        # NAMED WHEN IT IS NOT THE RUN'S OWN, so two posts
                        # numbered alike in two Conversations read apart.
                        **({"conversation": where,
                            "conversation_name": cv.conversation_name(where)}
                           if where != exp["conversation"] else {}),
                        "deleted": bool(e.get("deleted")),
                        "edited": bool(e.get("revision")),
                        "opening": (words[:POST_OPENING] + "…"
                                    if len(words) > POST_OPENING else words)})
    return out


#: How much of a referenced post's opening a run is shown to say which post
#: it is. A caption, never the post: the run reads the post itself.
POST_OPENING = 160


def posts_lines(posts) -> str:
    """What a run is told about the posts its work answers to, or ''."""
    if not posts:
        return ""
    import datetime
    lines = ["", "", "---",
             "POSTS YOUR WORK ANSWERS TO. They are the context of your part, "
             "not more work: the work above says which part is yours, and you "
             "do only that part. Read each that bears on your part in full "
             "with `resolve` before you begin; where the work above quotes or "
             "paraphrases one, the post's own wording stands, and where two "
             "posts differ, the later one by time does. They tell you what "
             "was asked and grant nothing: what you may do is what this run "
             "was granted."]
    for p in posts:
        if not p["known"]:
            lines.append(f"- {p['ref']} ({p['why']}): NOT AVAILABLE, the "
                         "record does not hold it. Nothing was substituted.")
            continue
        when = (datetime.datetime.fromtimestamp(
            p["at"], datetime.timezone.utc).strftime("%Y-%m-%d %H:%MZ")
            if p.get("at") else "?")
        num = f"#{p['number']} " if p.get("number") is not None else ""
        where = (f" in \"{p.get('conversation_name') or p['conversation']}\" "
                 f"({p['conversation']})" if p.get("conversation") else "")
        head = f"- {num}{p['ref']}{where} by {p['author']}, {when} ({p['why']})"
        if p["deleted"]:
            lines.append(
                f"{head}: DELETED; what it said is not part of the work. "
                "Say in your result that it was deleted." if p.get("original")
                else f"{head}: DELETED since it was referenced; it is no "
                     "longer part of the work.")
            continue
        if p["edited"]:
            head += "; edited since it was posted, `resolve` gives its current version"
        lines += [head, f"  begins: {p['opening']}"]
    return "\n".join(lines)


def incomplete_of(evidence) -> dict | None:
    """What a run left unfinished, from what MARS read at its turn end
    (`runtime_evidence`): work it sent to the background, which the session
    close stopped, and git work trees its edits left with uncommitted changes.
    None when it left neither. MARS ran the read-only git check; nothing here
    runs anything or judges whether the work was adequate."""
    ev = evidence if isinstance(evidence, dict) else {}
    background = [dict(b) for b in ev.get("background") or ()
                  if isinstance(b, dict)]
    uncommitted, unverified = [], []
    for w in ev.get("workspace") or ():
        if not isinstance(w, dict):
            continue
        # UNKNOWN IS NOT CLEAN: a tree this run edited whose check failed, or
        # a probe MARS cut short, is said as unverified, not read as clean.
        if w.get("truncated_probe"):
            unverified.append({"why": f"MARS stopped checking work trees "
                                      f"({w.get('reason') or 'limit'})"})
            continue
        if w.get("error") and w.get("edited"):
            unverified.append({"root": w.get("root"), "why": str(w["error"])})
            continue
        if not (w.get("root") and w.get("dirty")):
            continue
        # ONLY WHAT THIS RUN EDITED, where MARS says which files those were
        # (`edited`, relative to the root): a file somebody else left dirty
        # or untracked does not make this return incomplete. Without
        # `edited`, which files the run touched is unknown, so every dirty
        # line counts. The full list stays in `runtime_evidence`.
        edited = w.get("edited")
        dirty = (list(w["dirty"]) if not isinstance(edited, list) else
                 [line for line in w["dirty"] if _edited_line(line, edited)])
        if not dirty and edited and w.get("truncated"):
            # MARS cut the list, so the edited files may be past the cut:
            # unknown is not clean.
            dirty = list(w["dirty"])
        if dirty:
            uncommitted.append({"root": w["root"], "head": w.get("head"),
                                "dirty": dirty,
                                **({"truncated": True} if w.get("truncated")
                                   else {})})
    if not (background or uncommitted or unverified):
        return None
    return {"background": background, "uncommitted": uncommitted,
            **({"unverified": unverified} if unverified else {})}


def _porcelain_paths(line: str) -> list[str]:
    """The path(s) of one `git status --porcelain` line: both sides of a
    rename or copy, unquoted, in forward slashes."""
    rest = str(line)[3:]
    sides = rest.split(" -> ") if " -> " in rest else [rest]
    return [s.strip().strip('"').replace("\\", "/") for s in sides if s.strip()]


def _edited_line(line: str, edited) -> bool:
    """Whether a porcelain line is about a file this run edited. An untracked
    directory (`?? dir/`) counts when an edited file is inside it."""
    names = [str(e).replace("\\", "/") for e in edited]
    fold = (str.casefold if os.name == "nt" else str)   # Windows paths ignore case
    return any(fold(p) == fold(e) or (p.endswith("/") and fold(e).startswith(fold(p)))
               for p in _porcelain_paths(line) for e in names)


def incomplete_words(incomplete) -> list[str]:
    """An incomplete return, one line per thing left unfinished."""
    lines = []
    for u in (incomplete or {}).get("uncommitted") or ():
        n = len(u.get("dirty") or ())
        count = (f"at least {n} files" if u.get("truncated")
                 else f"{n} file" if n == 1 else f"{n} files")
        lines.append(f"returned INCOMPLETE: uncommitted changes in "
                     f"{u['root']} ({count})")
    for u in (incomplete or {}).get("unverified") or ():
        where = f" in {u['root']}" if u.get("root") else ""
        lines.append(f"returned UNVERIFIED: whether its changes{where} are "
                     f"committed could not be checked ({u['why']})")
    background = (incomplete or {}).get("background") or ()
    if background:
        titles = ", ".join(str(b.get("title") or b.get("backgroundTaskId"))
                           for b in background)
        lines.append("returned INCOMPLETE: sent work to the background, which "
                     f"was stopped when its run ended ({titles})")
    return lines


def latest_incomplete(cv, expectation) -> dict | None:
    """`incomplete` of this request's latest run end, when that end is a
    return recorded as incomplete; None otherwise (running, failed, clean)."""
    try:
        s = cv._child_state(expectation)
        end = cv._act(s["ended_by"]) if s["state"] == "returned" else None
    except Exception:                                     # noqa: BLE001
        return None
    detail = (end or {}).get("detail") or {}
    return detail.get("incomplete") if detail.get("returned_incomplete") else None


def review_readiness(cv, persona, repository, parent) -> list[str]:
    """Warnings for a review delegated over work whose latest return was
    incomplete: the reviewed request itself and each child it delegated.

    A WARNING, NOT A REFUSAL. The carrier decides whether to review anyway;
    this only says, from the record, that what would be reviewed is not all
    committed or was cut off. Empty when the delegation is not review work
    (`review_signal_of`) or nothing reviewed returned incomplete."""
    is_review, _, _ = review_signal_of(cv, persona, repository)
    if not is_review:
        return []
    reviewed = (repository.get("review_of") if isinstance(repository, dict)
                else None) or parent
    if not reviewed:
        return []
    try:
        required = cv.waiting_on(reviewed)["required"]
    except Exception:                                     # noqa: BLE001
        required = []
    # ONLY EACH PARTICIPANT'S LATEST RETURN, per activity: a dirty return
    # that a later delegation to the same participant for the same step
    # finished is superseded, and is not held against the work forever.
    latest = {}
    for c in required:
        if c["state"] != "returned" or not c.get("ended_at"):
            continue
        key = (c["carrier"], cv.activity_named(c["expectation"]))
        if key not in latest or c["ended_at"] > latest[key]["ended_at"]:
            latest[key] = c
    kids = [c["expectation"] for c in latest.values()]
    out = []
    for e in dict.fromkeys([reviewed, *kids]):
        incomplete = latest_incomplete(cv, e)
        if not incomplete:
            continue
        carrier = cv.expectation_state(e)["expected_of"]
        who = (cv.alias(carrier) if carrier else None) or "its carrier"
        out.append(f"{who} ({e}) " + "; ".join(incomplete_words(incomplete))
                   + ". That work is not review-ready: a review now would not "
                     "see all of it. Have it finished and committed first, or "
                     "say in the review that it is incomplete")
    return out


def resume_dispatch(cv, parent, resumed_act) -> dict:
    """What `_resume` dispatches, as the keyword arguments of the dispatch:
    for a caller that starts its dispatches itself once its own write is
    durable (`posting.post`, when a decision form closes)."""
    act = cv._act(resumed_act)
    exp = cv._act(parent)
    still = act["detail"].get("outstanding") or []
    asked = act["detail"].get("open_questions") or []
    told = act["detail"].get("follow_ups") or []
    lines = ["Resuming the work you were carrying. "
             + ("The owner gave a follow-up on this work (below): it is "
                "their latest word on it. "
                if told else "")
             + ("Other things this work waits on are still outstanding "
                "(below). Work still running returns to you as it ends and is "
                "not to be handed out again. "
                if still and told and not act["detail"].get("alone") else
                "Work you delegated to be acted on alone has returned; other "
                "things this work waits on are still outstanding (below). "
                "Work still running returns to you as it ends and is not to "
                "be handed out again. "
                if still else
                "" if told else
                "Nothing it was waiting on is outstanding but the questions "
                "listed as open. " if asked else
                "Nothing it was waiting on is outstanding. ")
             + "Nothing below says any of it was adequate; that is yours "
             "to judge -- retry, reroute, change the plan, ask, or stop."]
    for item in act["detail"].get("detached_reports", []):
        report = item["report"]
        lines.append(
            f"Detached operation {item['operation']} reported {report['detail']['result']}. "
            f"Reconcile originating request {parent}, not a newer post's request. "
            f"Report {report['id']}, result post {report['turn']}, "
            f"arming post {item['arming_post']}. "
            f"Summary: {report['detail']['summary']} "
            f"Evidence: {', '.join(report['detail']['evidence'])}")
    if asked:
        # AN OPEN QUESTION IS STILL ITS ASKER'S TO ANSWER. Work it does not
        # decide goes on; what it decides waits for the answer. One asked on
        # a form resumes this work again when the form closes
        # (`resume_closed_form`); one asked as its own Turn does not.
        formed = all(d.get("form") for d in act["detail"]["decisions"]
                     if d["expectation"] in asked)
        lines.append("A question you asked is still open. Carry on with work "
                     "it does not decide; do nothing that needs its answer. "
                     + ("The answer resumes this work again." if formed else
                        "Read its answer before acting on what it decides."))
    # THE OWNER'S FOLLOW-UPS, in their own words, earliest first: handed to
    # this work by the carrier of the request they were asked as.
    for fid in told:
        f = cv._act(fid)
        if not f:
            continue
        req = (f["detail"] or {}).get("request")
        number = cv.turn_number(f["turn"]) if f.get("turn") else None
        lines.append(f"- the owner's follow-up"
                     + (f" #{number}" if number else "")
                     + f" (request {req}, Turn {f['turn']}):")
        lines += [f"  {line}" for line in
                  (request_words(cv, req) or "").splitlines() or [""]]
    for c in act["detail"]["required"]:
        who = cv.alias(c["carrier"]) if c["carrier"] else "nobody"
        lines.append(f"- {who}: {c['state']}"
                     + (f" ({c['because']})" if c["state"] != "returned"
                        and c["because"] else "")
                     + (f"; reply {', '.join(c['replies'])}" if c["replies"]
                        else "")
                     + (f"; returned artifacts {', '.join(c['returned_artifacts'])}"
                        " (read them with read_artifact; hand them on with "
                        "delegate's `artifacts`)"
                        if c.get("returned_artifacts") else "")
                     + "".join(f"; {line}" for line in
                               _not_reassigned(cv, c["expectation"])))
        # WHAT IT LEFT UNFINISHED, as MARS read it when that run ended.
        if c["state"] == "returned":
            lines += [f"  {line}" for line in
                      incomplete_words(latest_incomplete(cv, c["expectation"]))]
    # THE DECISIONS ITS CHILDREN RAISED: each question, and the owner's
    # answer, or that it is still open.
    for d in act["detail"].get("child_decisions") or ():
        who = (cv.alias(d["carrier"]) if d.get("carrier") else None) \
            or d["asked_by"]
        a, w = d.get("answer"), d.get("withdrawn")
        lines.append(
            f"- decision {who} asked ({d['expectation']}): {d['question']} -- "
            + (f"answered: chose {a['label']!r} (reply {a['reply']})"
               if a and a.get("label") is not None else
               f"answered in their own words (reply {a['reply']}); read it"
               if a else
               f"withdrawn: {w.get('because') or 'no reason given'}"
               if isinstance(w, dict) else "still open"))
    for d in act["detail"]["decisions"]:
        if d.get("form"):
            continue                    # said with its form, below
        lines.append(f"- decision {d['expectation']}: "
                     + ("answered " + ", ".join(d["answers"]) if d["answered"]
                        else "unanswered"))
    # A DECISION FORM IT ASKED (P7): each question, and what the owner chose
    # or wrote for it, by the reply that answered it.
    for fid in act["detail"].get("forms") or ():
        form = cv.decision_form(fid)
        if not form:
            continue
        lines.append(f"- decision form {fid}"
                     + (f" on post {form['post']}" if form["post"] else "")
                     + ": every question is closed")
        for q in form["questions"]:
            a, w = q["answer"], q["withdrawn"]
            lines.append(
                f"  - {q['question']} ({q['expectation']}): "
                + (f"chose {a['label']!r} (reply {a['reply']})"
                   if a and a.get("label") is not None else
                   f"answered in their own words (reply {a['reply']}); "
                   f"read it" if a else
                   f"withdrawn: {w.get('because') or 'no reason given'}"
                   if w else "open"))
    # A DECISION FORM IT ASKED THAT IS STILL OPEN: each question, by its
    # words, and which are answered so far. Not handed over: its closing
    # resumes this work with it.
    for fid in dict.fromkeys(d["form"] for d in act["detail"]["decisions"]
                             if d.get("form") and d["expectation"] in asked):
        form = cv.decision_form(fid)
        if not form:
            continue
        lines.append(f"- decision form {fid}"
                     + (f" on post {form['post']}" if form["post"] else "")
                     + ": still open")
        for q in form["questions"]:
            a = q["answer"]
            lines.append(f"  - {q['question']} ({q['expectation']}): "
                         + (f"chose {a['label']!r}"
                            if a and a.get("label") is not None else
                            "answered in their own words" if a else
                            "withdrawn" if q["withdrawn"] else "open"))
    # INPUT IT WAITED FOR (`request_input`): the revision the owner marked
    # ready, by its entries, and the values in it -- what this run is given
    # is named in the `work-resumed` act, not only in these words.
    from mentis.web import inputs as _inputs
    for i in act["detail"].get("inputs") or ():
        if i.get("withdrawn"):
            lines.append(f"- input {i['expectation']} on response set "
                         f"{i['set']}: withdrawn by the person asked, "
                         "nothing marked ready")
            continue
        lines.append(f"- input {i['expectation']} on response set "
                     f"{i['set']}: marked ready ({i['marked_ready']}), "
                     f"covering answers {', '.join(i['answers']) or 'none'}")
        lines += ["  " + line for line in _inputs.given_words(
            cv, i["answers"])]
        # and the own words and interpretations, by the entries it recorded
        lines += ["  " + line for line in _inputs.resumed_words(cv, i)]
        if i.get("handover_not_read"):
            lines.append("  own words and interpretations could not be read "
                         f"({i['handover_not_read']}): resolve the set")
    from mentis.artifacts import awaited_returns
    readable = {}
    for r in awaited_returns(cv.corpus, cv, parent):
        readable.setdefault(r["awaited"], []).append(r["ref"])
    for w in act["detail"].get("awaited") or ():
        by = ", ".join(cv.alias(c) or c for c in w["claimed_by"]) or "nobody"
        left = readable.get(w["expectation"]) or []
        kept = len(w.get("returned_artifacts") or []) - len(left)
        lines.append(f"- other work you were waiting on, {w['expectation']}: "
                     + (f"claimed met by {by} ({', '.join(w['met_by'])}); "
                        "read what answered it before relying on it"
                        if w["met"] else
                        "it was WITHDRAWN, not finished; read anything it left "
                        "before relying on it, and if more is needed that is "
                        "yours to arrange"
                        if w.get("withdrawn") and w.get("ended") else
                        f"it STOPPED without being finished: its last run "
                        f"{w['returned']}, nobody claimed it met and nothing "
                        "it declared would start it again. What it left may be "
                        "partial; "
                        "read it before relying on it, and if more is needed "
                        "that is yours to arrange"
                        if w.get("stopped") else
                        f"delegated work that PAUSED, not finished: its run "
                        f"{w['returned']} while it still waits on "
                        f"{', '.join(w['paused'])}, and it runs again when "
                        "that comes back. Not claimed met; what it handed "
                        "back so far is partial"
                        if w.get("ended") and w.get("paused") else
                        f"delegated work that {w['returned']}, not claimed "
                        "met; read what it handed back before relying on it"
                        if w.get("ended") else "not claimed met")
                     + (f"; reply {', '.join(w['replies'])}"
                        if w.get("replies") else "")
                     + (f"; returned artifacts {', '.join(left)} (read them "
                        "with read_artifact; hand them on with delegate's "
                        "`artifacts`)" if left else "")
                     + (f"; {kept} returned artifact(s) not available to this "
                        "work: restricted, deleted or held elsewhere"
                        if kept > 0 else ""))
    # NO REPORTING POLICY IS APPENDED HERE ANY MORE. A constant from
    # `mentis.worker` used to be added to this work text, prescribing the shape
    # of a routine status -- which made this the one place in the system that
    # put behavioural prose into a run's instructions from code, needing
    # nothing established, placed or named, and recorded as no governance
    # source. That is what the removed brief did, and an independent review
    # found this still doing it. What remains above is the FACTS a resumed
    # carrier is owed: which children ended, how, and what is still open.
    # If a reporting shape is wanted, it is behavioural material and reaches a
    # run the way behavioural material reaches a run.
    persona = next((a["detail"].get("persona") for a in sorted(
        cv.history(caused_by=parent), key=lambda a: a["at"], reverse=True)
        if a["act"] == "expectation-assigned" and a["detail"].get("persona")),
        None) or delegated_persona(cv, parent) \
        or started_persona(cv, parent, act["detail"]["carrier"])
    return dict(conversation=exp["conversation"], turn=exp["turn"],
                participant=act["detail"]["carrier"],
                work="\n".join(lines), persona=persona,
                expectation=parent,
                # A CONTINUATION OF THE SAME WORK: its run may continue the
                # earlier runtime session (`mentis.web.continuity`).
                resumed_from=resumed_act,
                # matched against the request's words, not these lines
                question=request_words(cv, parent) or None,
                because=f"resumed ({resumed_act}): "
                        + (told and "the owner gave a follow-up on this work"
                           or act["detail"].get("outstanding") and
                           "work delegated to be acted on alone returned; "
                           "other work it waits on is outstanding"
                           or act["detail"].get("open_questions") and
                           "nothing it was waiting on is outstanding but "
                           "questions it asked, still open"
                           or "nothing it was waiting on is outstanding"))


def _dispatch(st, *, conversation: str, turn: str, participant: str,
             work: str, runtime: str | None = None, model: str | None = None,
             effort: str | None = None, persona: str | None = None,
             new_instance: bool = False, difficulty: str = "ordinary",
             workspace: str | None = None, requires=(),
             expectation: str | None = None, because: str | None = None,
             deadline_s: int | None = ..., question: str | None = None,
             triggered_at: float | None = None,
             resumed_from: str | None = None) -> dict:
    """Summon or reuse, perform, and reply. Blocking; run it on a thread.

    Returns what it did, so a caller can record or report it. Raises nothing
    a caller has to catch: a failure comes back as a result that says so.

    `expectation` is the request this run carries. It becomes the cause of every
    act below and the scope of the grant, so the run is attached to the work
    rather than merely happening near it.

    `requires` is what the work needs. It reaches selection AND session reuse,
    because continuity that bypassed eligibility would be eligibility that only
    applied to first runs.

    `question` is what governing and propositional material is MATCHED
    against, when it is not `work`: a resume or a retry passes the request's
    own words (`request_words`), because its `work` is generated text the
    original request's conditions were never written against. It is only a
    matching input; the run is still told `work`.

    `triggered_at` is when the dispatch was asked for (`dispatch_soon`), and
    `resumed_from` the `work-resumed` act when this continues the same work
    (`resume_dispatch`): only then may the run continue its earlier runtime
    session (`mentis.web.continuity`).
    """
    svc, cv = st.agents, st.cv
    if svc is None:
        return {"ok": False, "why": "no agent service is attached to this server"}
    # WHERE THE TIME GOES (WS-P), epoch seconds, recorded on the start and on
    # the end of the run: what came before selection, selection, the start,
    # composition, and inside the execution boundary.
    clock = _Clock(triggered_at)
    # THE CAPACITY READ OVERLAPS THE RECORD READS BELOW: started now, in the
    # background, if the held answer is old; selection never waits for it.
    active = getattr(svc, "note_activity", None)
    if callable(active):
        active()
    prime = getattr(svc, "capacity_prime", None)
    if callable(prime):
        try:
            prime()
        except Exception:                                 # noqa: BLE001
            pass

    # A WITHDRAWN REQUEST IS NOT STARTED (owner decision, ent-750df9aa168c).
    # Asked before anything is written or summoned, and again in the transaction
    # that writes the start (below), which is the one a withdrawal cannot pass.
    gone = withdrawal_of(cv, expectation)
    if gone:
        return _refuse_withdrawn(
            cv, gone, participant=participant, conversation=conversation,
            turn=turn, expectation=expectation,
            requested={"runtime": runtime, "model": model, "effort": effort,
                       "requires": list(requires or ())})

    # A CLI-SESSION PARTICIPANT IS NOT AN AGENT MENTIS RUNS (WS-I, second
    # review): addressing @<Runtime>-CLI-<HOST>, or delegating to it, used to
    # start a runtime as it, and from then on every session on that runtime
    # and host was refused its own identity. Refused here, before anything is
    # summoned, as a failure before start that says what to do instead.
    from mentis.session_identity import is_cli_participant, not_dispatchable
    if is_cli_participant(cv, participant):
        refused = not_dispatchable(cv, participant)
        act = _failed_before_start(
            cv, participant=participant, conversation=conversation, turn=turn,
            expectation=expectation, stage="cli-session-participant",
            exc=refused, requested={"runtime": runtime, "model": model,
                                    "effort": effort,
                                    "requires": list(requires or ())})
        return {"ok": False, "why": str(refused), "failed_act": act,
                "before_execution_started": True,
                "refusal": refused.as_dict()}

    # THE SAME REQUEST RUNS AS IT WAS ASKED. Its own model and effort, read here
    # for every path that starts it -- first run, resume, retry, a start handed
    # on -- before anything judges a runtime against them, so no path has to
    # remember to pass them and a tier can never replace one on a later run. A
    # model that has since been retired fails honestly; it is never substituted.
    clock.step("withdrawal_checked")
    scope = execution_scope(cv, expectation)
    model = model or scope["constraints"].get("model") or None
    effort = effort or scope["constraints"].get("effort") or None
    # WHAT THIS REQUEST NAMES, READ ONCE. It decides the binding below and the
    # composition later, and those two must not be able to disagree about it:
    # a session chosen against one answer and told another is the continuity
    # bug this was repaired for.
    governed = _governed_for(cv, expectation)
    clock.step("scope_read")
    # A WORKFLOW CHANGE NEVER WIDENS WHAT WORK MAY DO (owner ruling
    # 2026-10-29), held here, where work is executed: a run of a request whose
    # Workflow changed is refused, before anything is selected, if it would be
    # allowed more than the work could do when the Workflow changed and the
    # owner has not acted on the work since (`workflow_change`).
    from mentis.conversation.workflow_change import authority_widened
    try:
        widened = authority_widened(cv, expectation) if expectation else None
    except Exception as exc:                              # noqa: BLE001
        widened = (f"what this work may do could not be compared with what it "
                   f"could do when its Workflow changed: {exc}")
    clock.step("workflow_checked")
    if widened:
        act = _failed_before_start(
            cv, participant=participant, conversation=conversation, turn=turn,
            expectation=expectation, stage="workflow-authority",
            exc=PermissionError(widened),
            requested={"runtime": runtime, "model": model, "effort": effort,
                       "requires": list(requires or ())})
        return {"ok": False, "why": widened, "failed_act": act,
                "before_execution_started": True}
    # WHAT THE GOVERNING MATERIAL REQUIRES, BEFORE ANY RUNTIME IS CHOSEN. A
    # Discipline that needs a capability -- named for this work, carried by
    # the Persona it is done as, or placed where it runs -- is part of what
    # this work needs, so it joins `requires` and reaches binding, selection
    # and reuse exactly as a requirement the caller stated does. Recorded with
    # where each came from (`requires_from`), so a refusal says which material
    # asked for what. It narrows; it never grants.
    # A REQUIREMENT THAT CANNOT BE READ IS NOT IGNORED: running the work on a
    # runtime chosen without it would be the silent gap this closes, so the
    # failure is recorded before anything starts, like every other one here.
    try:
        requires_from = requirements_of(
            cv, delivered_in_full(cv, conversation,
                                  governing_ids(cv, conversation, governed, persona),
                                  named=governed, persona=persona))
    except Exception as exc:
        act = _failed_before_start(
            cv, participant=participant, conversation=conversation, turn=turn,
            expectation=expectation, stage="requirements", exc=exc,
            requested={"runtime": runtime, "model": model, "effort": effort,
                       "requires": list(requires or ())})
        return {"ok": False, "why": str(exc), "failed_act": act,
                "before_execution_started": True}
    clock.step("requirements_read")
    requires = tuple(dict.fromkeys([*(requires or ()),
                                    *recorded_requires(cv, expectation),
                                    *requires_from]))
    requested = {"runtime": runtime, "model": model, "effort": effort,
                 "requires": list(requires or ()),
                 **({"requires_from": requires_from} if requires_from
                    else {})}
    # THE RUNTIME IS BOUND BEFORE ANYTHING IS SELECTED, from the request's own
    # record -- so a resumed or retried run cannot lose what the first one was
    # told, and a Participant's declared default becomes a recorded constraint
    # rather than a guess made again on every run. See `resolve_runtime`.
    try:
        # REVIEW SEPARATION IS ASKED OF THE BINDING BEFORE IT IS RECORDED: a
        # default that is the reviewed work's runtime yields, so no
        # `runtime-bound` act ever says this run was bound to it.
        review, author, review_said = review_signal(cv, expectation, persona)
        # WHAT THE WORK NEEDS, from its record, so a default that cannot do it
        # does not bind and selection fills only what nobody named.
        routed = routing_now(cv, expectation, persona=persona,
                             difficulty=difficulty)
        tier = (routed or {}).get("required_tier")
        binding = resolve_runtime(cv, participant=participant,
                                  expectation=expectation, named=runtime,
                                  judge=runtime_judge(svc, requires=requires,
                                                      model=model,
                                                      holds=lambda: quota_holds(cv),
                                                      tier=tier))
        binding = yield_to_review(binding, yields_to(cv, persona, author))
        # NOTHING STRUCTURED SAID ANYTHING, so the default tier, only now: a
        # Participant's default binds as before, and the request's own record
        # stays as it is, so a later change of default applies to later runs.
        if not tier:
            tier = _routing.DEFAULT_TIER
            routed = {**(routed or {}), "required_tier": tier,
                      "target_effort": _routing.TARGET_EFFORT[tier],
                      "tier_sources": ["default"]}
        if binding["runtime"] and expectation and not binding.get("act"):
            binding["act"] = cv.record_act(
                actor=participant, act=RUNTIME_BOUND,
                conversation=conversation, turn=turn, caused_by=expectation,
                about=[expectation],
                because=f"bound to runtime {binding['runtime']} "
                        f"({binding['source']})",
                detail={"runtime": binding["runtime"],
                        "source": binding["source"],
                        **({"declaration": binding["declaration"]}
                           if binding.get("declaration") else {})})
    except Exception as exc:
        act = _failed_before_start(
            cv, participant=participant, conversation=conversation, turn=turn,
            expectation=expectation, stage="runtime-binding", exc=exc,
            requested=requested)
        return {"ok": False, "why": str(exc), "failed_act": act,
                "before_execution_started": True}
    # ONLY THE RUNTIME COMES FROM THE BINDING. Model and effort are this
    # request's own (read above): work continuing it gets neither from it.
    runtime = binding["runtime"]
    clock.step("runtime_bound")
    requested = {**requested, "runtime": runtime, "model": model,
                 "effort": effort, "runtime_source": binding["source"],
                 **({"routing": routed} if routed else {})}
    # WHERE THE RUN WORKS: the repository directory this request declared,
    # if it declared one, else the server's workspace (below). Mentis cuts
    # no worktree and commits nothing: Git is the requester's and the
    # agent's. A session bound to one workspace is never reused for another.
    try:
        workspace = declared_workspace(cv, expectation) or workspace
        clock.step("workspace_read")
    except Exception as exc:
        act = _failed_before_start(
            cv, participant=participant, conversation=conversation, turn=turn,
            expectation=expectation, stage="repository", exc=exc,
            requested=requested)
        return {"ok": False, "why": str(exc), "failed_act": act,
                "before_execution_started": True}
    # EVERYTHING THAT CAN FAIL BEFORE A RUN EXISTS, INSIDE SOMETHING THAT
    # RECORDS IT. Each of these used to sit bare, so a failure in any of them
    # left the request owed and silent.
    try:
        address = address_for(cv, participant, runtime=runtime,
                              persona=persona, conversation=conversation,
                              governed=governed)
        # Unspecified dimensions stay unspecified. `execution_select` decides
        # only what the owner left open, and says what informed it -- and
        # what was weighed before it: a declined preference, and whether
        # this is review whose author's runtime should be avoided.
        considered = []
        if binding.get("declined"):
            considered.append(
                f"participant default {binding['preferred']} not used: "
                f"{binding['declined']}; selection fell through")
        disclosed = []
        if review:
            considered.append(review_said)
            if binding.get("yielded"):
                considered.append(binding["yielded"])
            if runtime and author:
                conflict = review_conflict(binding, author)
                if conflict:
                    disclosed.append(conflict)
                considered.append(
                    conflict or
                    f"runtime {runtime} is fixed ({binding['source']}), so "
                    f"independence by runtime was not applied over it")
        # CONTINUITY BEFORE ROTATION: a handle this Participant already holds
        # here names the runtime its work has been running on, and an unbound
        # request continues there when it can (`execution_select`'s `prefer`).
        clock.step("address_made")
        held = (svc.agents_resolve(address, participant=participant)
                if not (runtime or new_instance) else {})
        # KNOWN QUOTA FAILURES, read back from the record (`quota_holds`):
        # a runtime that just refused for quota is not chosen automatically
        # again until its reset or cooldown passes or it is seen to succeed.
        holds_now = quota_holds(cv)
        # WHAT THE WORK NEEDS OF A MODEL, from what its request recorded
        # (`need_of`), and the owner's standing suitability, both read from
        # the record HERE: selection itself never reads the record.
        work_req = ((routed or {}).get("requirements")
                    if isinstance((routed or {}).get("requirements"), dict)
                    else _req_from_routing(routed))
        need_now = need_of(routed, work_req)
        standing_now = standing_of(cv)
        clock.mark("selection_started")
        selection = svc.execution_select(difficulty=difficulty, runtime=runtime,
                                         model=model, effort=effort,
                                         requires=requires,
                                         avoid=None if runtime else author,
                                         considered=tuple(considered),
                                         prefer=held.get("would_reuse_runtime"),
                                         holds=holds_now, tier=tier,
                                         tier_sources=tuple(
                                             (routed or {}).get("tier_sources") or ()),
                                         **_selection_kwargs(
                                             svc, need=need_now,
                                             requirements=work_req,
                                             standing=standing_now))
        # WHAT A FIXED RUNTIME COSTS THE REVIEW, said beside what selection
        # itself discloses, as words a reader of the record finds in one place.
        if disclosed:
            said_before = selection.inputs.get("disclosed") or []
            selection.inputs["disclosed"] = [
                *said_before, *(d for d in disclosed if d not in said_before)]
        # THE REFERENCE TRAVELS BESIDE THE ADDRESS, NOT INSIDE IT. This boundary
        # already holds the durable Participant -- the composer sends an id and
        # this function is called with it -- and it used to be discarded here in
        # favour of the alias. Two deliberate Participants both called `@Ada`
        # then keyed identically, and the second would be handed the first's live
        # execution. The Address stays exactly what it is, a non-unique name.
        clock.mark("selection_done")
        before = svc.agents_resolve(address, participant=participant)
        instance = svc.agents_summon(address, selection,
                                     workspace=workspace or st.workspace,
                                     reuse=not new_instance,
                                     participant=participant,
                                     requires=requires,
                                     # WHAT THE RECORD SAYS IS STILL RUNNING,
                                     # by handle. The instance store keeps no
                                     # runs, so a session whose last row reads
                                     # `finished` about an EARLIER run would
                                     # otherwise be adopted while a later run
                                     # of it has no recorded end.
                                     open_runs={r["execution"]: r for r in
                                                cv.open_runs()
                                                if r.get("execution")})
    except Exception as exc:
        act = _failed_before_start(
            cv, participant=participant, conversation=conversation, turn=turn,
            expectation=expectation, stage="selection-or-summon", exc=exc,
            requested=requested)
        return {"ok": False, "why": str(exc), "failed_act": act,
                "before_execution_started": True}

    # RUN IT OR REFUSE, CHECKED ON WHAT WOULD ACTUALLY RUN. Selection already
    # refuses an absent runtime, and reuse is keyed on the bound runtime; this
    # is the last line, on the instance itself, so no path through reuse or
    # adoption can hand bound work to a different runtime.
    if runtime and instance.runtime != runtime:
        svc.agents_release(instance.instance_id)
        act = _failed_before_start(
            cv, participant=participant, conversation=conversation, turn=turn,
            expectation=expectation, stage="runtime-binding",
            exc=RuntimeConflict(
                f"bound to runtime {runtime!r} but the session that would "
                f"run it is {instance.runtime!r}; refusing rather than "
                f"running a different runtime"),
            requested=requested)
        return {"ok": False, "why": "runtime binding", "failed_act": act,
                "before_execution_started": True}

    # THE EXECUTION MODE, CHECKED ON WHAT WOULD ACTUALLY RUN (owner, 2026-11-11;
    # `execution.mode`): the mode the owner selected for this request, if the runtime's
    # contract supports it, else the runtime's default. A selected mode the runtime does not
    # support refuses the run before it starts -- never another mode, never another runtime.
    from mentis.execution import mode as _mode
    try:
        contract_of = getattr(svc, "runtime_contract", None)
        try:
            mode_contract = contract_of(instance.runtime) if callable(contract_of) else None
        except Exception:                                 # noqa: BLE001
            mode_contract = None
        execution_mode = _mode.resolve(cv, expectation, runtime=instance.runtime,
                                       contract=mode_contract)
    except _mode.Refused as exc:
        svc.agents_release(instance.instance_id)
        act = _failed_before_start(
            cv, participant=participant, conversation=conversation, turn=turn,
            expectation=expectation, stage="execution-mode", exc=exc,
            requested=requested)
        return {"ok": False, "why": str(exc), "failed_act": act,
                "before_execution_started": True}

    # WHAT THIS RUN IS CARRYING, RECORDED FOR EVERY RUN AND NOT ONLY THE
    # ORGANISING ONES.
    #
    # FOUND BY TWO INDEPENDENT REVIEWERS, SEPARATELY. This was conditional on a
    # caller having passed `authority`, and exactly one caller does -- intake. So
    # every ordinary dispatch and every delegated specialist got a grant naming
    # no Participant, no expectation and no Conversation, and `request_decision`
    # -- which every execution is shown and pre-approved for -- refused 100% of
    # the time with a message that reads like a malfunction. A specialist that
    # found the next step was the owner's had no way to record it and had to put
    # it in prose, which is the exact failure `request_decision` exists to end.
    #
    # `scope` still comes from the caller and defaults to `worker`, so this
    # widens nothing: what a run MAY DO is unchanged, and what it is carrying is
    # now always on the grant for the server to derive from.
    #
    # AND WHAT IT MAY ORGANISE COMES FROM THE WORK, NOT FROM THE CALLER. It used
    # to be a `scope` the one intake caller passed in, so it could only ever
    # attach to a first dispatch and was lost the moment the owner continued the
    # same work by name. It is now read from the record of the request being
    # carried -- so a delegated child, discovered work, and anything nobody
    # granted authority to are ordinary work because the record says so, and a
    # different runtime, model or session changes nothing.
    authority = authority_for(cv, expectation)
    grant_basis = dict(
        scope=authority["scope"], operations=authority["organising"],
        expectation=expectation, conversation=conversation,
        participant=participant, runtime=instance.runtime,
        # THE PERSONA THE RUN WEARS, so what it records says so
        # (`ladder_writes.record` puts it on the `material-recorded` act).
        persona=persona)
    svc.authority.authorise_for(instance.instance_id, grant_basis)

    # A CLAIM MUST BE USED OR GIVEN BACK. `agents_summon` hands back a
    # CLAIMED instance so nothing else can take it. If recording the act
    # fails, that claim would sit on the session for good and no later work
    # could continue it -- so the handle goes back before the error does.
    #
    # THE START ASKS AGAIN, INSIDE ITS OWN TRANSACTION, as `claim_resumption`
    # does: a withdrawal commits before this or after the start, never between.
    # One landing since the check above gives the claim back like any refusal.
    try:
        # WHAT WAS DECIDED AND WHY, for the start and for however the run ends.
        decided = (selection.inputs or {}).get("routing") or {}
        routed_record = ({**(routed or {}),
                          **{k: decided[k] for k in (
                              "selected_tier", "tier_unfulfilled",
                              "tier_unfulfilled_because",
                              "effort_floor_unverified") if decided.get(k)}}
                         if routed else None)
        provenance = field_provenance(cv, scope["constraints"], binding,
                                      model=model, effort=effort,
                                      selection=selection, routed=routed)
        clock.step("summoned")
        # SESSION CONTINUITY (WS-P), DECIDED BEFORE THE START IS RECORDED, so
        # the start says truthfully whether this run asks MARS to continue
        # an earlier runtime session; the end act says whether it did. A
        # continuation of the same work, by the same participant on the same
        # runtime and model, under unchanged governance, Workflow, authority
        # and consent, asks for the session its previous run left.
        from mentis.web import continuity as _continuity
        from mentis.conversation.workflow_change import authority_line
        try:
            wf_line = authority_line(cv, expectation) if expectation else None
            session_basis = _continuity.basis(
                participant=participant, backend=instance.runtime,
                model=instance.requested_model,
                context=getattr(address, "context", None), authority=authority,
                consent=_continuity.consent_before_start(
                    cv, expectation, instance.workspace),
                workflow_line=wf_line, workspace=instance.workspace)
            # WHAT THE RUNTIME DECLARES, not its name (round 2, O9): one
            # with no native resume is given the record-derived context.
            contract_of = getattr(svc, "runtime_contract", None)
            try:
                contract = (contract_of(instance.runtime, holds=holds_now)
                            if resumed_from and callable(contract_of) else None)
            except Exception:                             # noqa: BLE001
                contract = None
            resume, resume_why = _continuity.decide(
                cv, expectation=expectation, participant=participant,
                resumed_from=resumed_from, now=session_basis,
                contract=contract)
        except Exception as exc:                          # noqa: BLE001
            wf_line, session_basis = None, None
            resume, resume_why = None, f"continuity could not be decided ({exc})"
        clock.step("continuity_decided")
        with cv._c.atomic():
            gone = withdrawal_of(cv, expectation)
            if not gone:
                clock.mark("started_recorded")
                started = _started_act(
                    cv, participant, conversation, turn, instance, selection,
                    svc, before, new_instance, runtime, model, effort,
                    expectation=expectation, because=because,
                    authority=authority, binding=binding, requires=requires,
                    requires_from=requires_from, persona=persona,
                    routed=routed_record, provenance=provenance,
                    work_requirements=work_req,
                    timing=clock.record(),
                    session_note=_continuity.start_note(
                        resume, resume_why, resumed_from),
                    execution_mode=execution_mode)
        if gone:
            svc.agents_release(instance.instance_id)
            return _refuse_withdrawn(
                cv, gone, participant=participant, conversation=conversation,
                turn=turn, expectation=expectation, requested=requested)
    except Exception:
        svc.agents_release(instance.instance_id)
        raise
    # BOTH, because they answer different questions. `IN_FLIGHT` is main's
    # recovery bookkeeping -- which runs this process is between the start and
    # the end of, so a lost waiter can be told apart from a run still going.
    # `agents_open_run` is the OBSERVATION bookkeeping: what this process holds
    # of the run while it is going, read back by `mentis.operational.runs`.
    # Dropping the first would regress result-recovery; dropping the second
    # leaves a reader looking at an open run nobody appears to hold.
    clock.step("start_committed")
    IN_FLIGHT.add(started)
    _here.started = started
    svc.agents_open_run(instance.instance_id, started)


    # THE PERSONA MATERIAL, COMPOSED BY THE SEAM THAT ALREADY DOES IT.
    #
    # This path used to accept a `persona` and do nothing with it but put its
    # id in a binding key: the behaviour was never composed, never sent, and
    # so `reconstruct` could only report that no delivery evidence said which
    # Persona was in use. `compose` already reads the Persona entry, already
    # withholds a superseded one with the reason, and already knows what a
    # delivery record should carry. None of that is rebuilt here.
    #
    # It goes in the work payload rather than the runtime's start-of-session
    # delivery because a reused instance registers no new delivery, and
    # material that did not cross must not be recorded as though it had.
    execution = composition = None
    offered: list = []
    why_offered: list = []
    try:
        # THE WORK, AND NOTHING FROM THE FILESYSTEM. There is one behavioural
        # plane and it is Mentis: what a run is told comes from the governed
        # material composed below, and how to use the interface comes from the
        # interface's own tool descriptions. A file beside the checkout used to
        # be read in here as well, which made a second, untracked, unrecorded
        # plane that said what the other two already said and drifted from both.
        # The same UI syntax reaches every runtime, including reused sessions.
        # THE PROMPT'S SHAPE: "# Your task" first (the step's Done when is
        # added below once the composition has said which step this is), then
        # governance and orientation, then the reply format under its own
        # heading, then the closing block.
        payload = ""
        reply = f"{REPLY_HEADING}\n\n{RENDERER_BRIEF}"
        done_when = None
        # COMPOSED FOR EVERY DISPATCH, NOT ONLY WHEN A PERSONA WAS PICKED.
        # FOUND BY REVIEW: this whole block used to sit behind `if persona`,
        # so material an owner had established at a Conversation reached a
        # worker only when somebody happened to choose a Persona as well --
        # while the interface said governing material reaches every
        # execution. What governs here governs here.
        #
        # `instance.runtime`, not `selection.runtime`: a reused instance is
        # whatever it already was, and a selection that has since changed
        # would put a runtime in the record that did not run this.
        clock.step("composition_began")
        execution = cv.begin_execution(participant=participant,
                                       conversation=conversation,
                                       persona=persona,
                                       runtime=instance.runtime,
                                       # WHICH REQUEST THIS IS CARRYING. One
                                       # carrier may hold several at once in one
                                       # Conversation, and without this every
                                       # one of them reads as every other.
                                       for_expectation=expectation)
        # THE WORK TEXT IS THE QUESTION, which is what makes propositional
        # delivery a production path and not an API somebody could call. What
        # this run is being asked to do is the only statement of what it needs
        # to know, so it is what standing propositional material is matched
        # against; `compose` supplies nothing from this channel when it is empty.
        #
        # EXCEPT ON A RESUME OR A RETRY, whose work text is generated ("Resuming
        # the work you were carrying...", "The owner chose to retry..."): those
        # pass `question`, the request's own words, so a Workflow placed on a
        # condition the request met is delivered on its resumed runs as on its
        # first, not dropped to a pointer (owner's scope item 7, 2026-10-29).
        asked = question if question else work
        #
        # AND THE GOVERNED MATERIAL THIS REQUEST NAMES. `behavioural` has
        # always been part of this seam -- it standing-checks each id on its
        # own, withholds a superseded or unestablished one with the reason,
        # keeps every item a separate Component with its own identity, and
        # records `invocation:named` as why it was supplied. Brain scope and
        # the inspection door both passed it. THIS CALL DID NOT, and it is the
        # only production dispatch there is, so material an owner established
        # and named for a piece of work reached nobody unless it also happened
        # to be placed at the Conversation the work ran in. Nothing about
        # applicability is decided here: whoever assigned the work said what
        # applies, because they were already interpreting the intent and
        # defining the work, and this carries their references to the composer
        # unchanged.
        #
        # AND THE STEP IT WAS DELEGATED FOR. A request delegated for one
        # activity of a Workflow ("<workflow>#<key>" on its record) is given
        # that activity -- the Workflow's name, its `what` and `done_when` --
        # as a component sourced from the Workflow entry, so it is in the
        # delivery record like everything else composed, and is not prose
        # written here (see above). Read from the request on EVERY run of it,
        # so a resumed or continued run is told the same step. It is not added
        # to `governed`: the Workflow's text and `requires` stay the carrier's.
        composition = cv.compose(conversation=conversation,
                                 participant=participant, persona=persona,
                                 behavioural=governed,
                                 question=asked,
                                 activity=cv.activity_named(expectation),
                                 # THE POST THIS RUN CARRIES, so its
                                 # orientation says what that post replies
                                 # to with or without a Topic in focus.
                                 carrying=((cv._act(expectation) or {})
                                           .get("turn") if expectation
                                           else None))
        clock.step("composed")
        deliveries = ()
        if composition.components:
            # CONDENSED AS A HAND-STARTED SESSION'S BRIEF IS: the Persona and
            # what is named in full, placed material at the level the owner
            # placed it at, a condition the work meets in full. With no level
            # placed anywhere this is exactly `composition.payload()`. The
            # delivery record still records every component composed.
            from mentis.conversation.condense import condense, render
            deliveries = condense(cv._c, composition, question=asked)
            told = render(deliveries)
            # A CHANGED WORKFLOW IS SAID WITH WHAT IT DID NOT CHANGE: composed
            # from the record, beside the Workflow, never from its text.
            from mentis.conversation.workflow_change import authority_line
            changed = authority_line(cv, expectation) if expectation else None
            if changed:
                told = f"{told}\n\n{changed}"
            payload = told
            for comp in composition.components:
                if getattr(comp, "activity", None):
                    # ALL of it: a done_when may run over several lines, and
                    # it is the last field of the step component.
                    head, sep, rest = comp.text.partition("Done when:")
                    if sep:
                        done_when = rest.strip() or None
        # WHAT THIS RUN WAS TOLD, ON ITS GRANT. The delivery record is written
        # only once the run has ended (below), so while it runs the record
        # cannot yet say what it was delivered -- and two things need to know
        # during the run: which held artifacts the material it was told draws
        # on (`artifacts.available`, `drawn-on-by-governed`) and which
        # material it may propose a revision of (`propose_revision`). The ids
        # are the GOVERNING components of the composition -- material whose
        # Kind directs work, delivered as Persona, Persona-carried, named,
        # placed here or on the whole Brain (`Composition.governing`). Never
        # the orientation (whose source is the Conversation entry) and never
        # the knowledge channel: neither governs the run, so neither opens an
        # artifact or may be revised from it. Found by independent review.
        clock.step("condensed")
        # WHAT FOLLOWS IS THE RUN'S SITUATION, not its governance: told again,
        # as it stands now, to a resumed session (WS-P).
        situation_from = len(payload)
        delivered = composition.governing_ids()
        svc.authority.authorise_for(instance.instance_id,
                                    {**grant_basis, "delivered": delivered})
        # WHAT THIS RUN WAS GIVEN, OFFERED BY REFERENCE. The references cross
        # in the prompt; the BYTES cross only if the run asks (`read_artifact`),
        # which is its own act. Exactly what the grant admits, computed by the
        # function the door itself uses, so the list and the door cannot
        # disagree about what may be read.
        why_offered = _artifacts.available(st.corpus, cv,
                                           {"expectation": expectation,
                                            "delivered": delivered})
        offered = [w["ref"] for w in why_offered]
        # THE OBJECTS THE REQUEST REFERENCES, one each, as the author
        # selected them (owner decision, 2026-10-28): a held one is among
        # `offered` above, a Markdown one is told by its source here, and
        # one that does not resolve is said to. Nothing else of their posts.
        if expectation:
            from mentis.conversation import objectref
            payload += objectref.context_lines(
                objectref.for_request(st.corpus, cv, expectation), offered)
            # AND THE POSTS IT ANSWERS TO, when it was delegated: the
            # original request and what its delegations referenced.
            payload += posts_lines(referenced_posts(cv, expectation))
        if offered:
            payload += _offer(st.corpus, offered)
        # WHAT NOBODY HAS ESTABLISHED THIS RUNTIME CAN DO, told to the run
        # that is asked to do it (#1268): it was chosen without confirmation,
        # so it says plainly when it cannot, and the record learns from that.
        unsure = ((selection.inputs or {}).get("unconfirmed") or {}).get(
            selection.runtime)
        if unsure:
            payload += (
                f"\n\n---\nThis work needs {', '.join(unsure)}, and whether "
                f"this runtime ({selection.runtime}) can do that has not been "
                f"established. Try it. If you cannot, say so plainly and do not "
                f"report the work as done; a reviewer records the verdict as "
                f"incomplete with `lacks` naming what was missing.")
        # THE OWNER'S FOLLOW-UP PERMISSION, as a fact the run is told: read
        # from the original request this work serves, so every run of it --
        # first, resumed or another execution -- is told the same.
        if expectation:
            from mentis.operational import (ASK, discovery, follow_up_of)
            where = discovery(cv, expectation)
            allowed = follow_up_of(cv, where["origin"])
            if allowed != ASK:
                reach = ("without limit" if allowed == "unrestricted" else
                         f"up to generation {allowed['depth']}")
                payload += (
                    "\n\n---\nFollow-up permission (the owner's, on the "
                    f"original request): independently pursued discoveries "
                    f"are allowed {reach}; this work is generation "
                    f"{where['generation']}. A finding recorded with "
                    "record_discovered_work can be picked up with "
                    "delegate(expectation=...) within that allowance without "
                    "asking; findings not picked up are put to the owner when "
                    "the trunk they were found under is finished. Delegating "
                    "work this trunk needs does not count against it.")
        # THE OWNER'S RUN CONSENT, as a fact the run is told, so it knows
        # which of its operations proceed and that the rest are asked or
        # refused (docs/run-consent.md). Separate from the follow-up
        # permission above: one is about pursuing side work, this is about
        # which operations need a question.
        consent_said = ""
        c = None
        if expectation:
            from mentis.operational import consent as _consent
            c = _consent.of_run(cv, started, workspace=instance.workspace)
            # UNRESTRICTED HOST EXECUTION ON A RUNTIME THAT DOES NOT ASK (`execution.mode`,
            # from its contract, never its name): nothing is asked while it works, so the run
            # is never told that operations outside its consent "are still asked" or that
            # the owner may change it during the run.
            unasked = (execution_mode.get("effective") == _mode.UNRESTRICTED_HOST
                       and not _mode.asks(mode_contract, _mode.UNRESTRICTED_HOST))
            if c["source"] != "none" and unasked:
                consent_said += (
                    f"\n\n---\nRun consent (the owner's): {c['label'].lower()}. "
                    f"Approved workspaces: {', '.join(c['workspaces']) or 'none'}. "
                    f"Routine kinds of operation: {', '.join(c['categories'])}. "
                    "This run executes unrestricted on the host (Execution Mode "
                    "unrestricted-host) and your runtime does not ask before operations in "
                    "this mode: nothing enforces this consent while you work, so keep to it "
                    "yourself. "
                    + ("Anything outside it -- another directory, the network, a Git remote, "
                       "credentials, a Brain -- is not consented: do not do it. "
                       if c["mode"] in (_consent.TASK, _consent.DENY) else
                       "The owner approved every operation. " if c["mode"] == _consent.ALL
                       else "")
                    + "This is not authority over Mentis: its operations are still checked "
                    "against your grant. This is not permission to pursue side work.")
            elif c["source"] != "none":
                consent_said += (
                    f"\n\n---\nRun consent (the owner's): {c['label'].lower()}. "
                    f"Approved workspaces: {', '.join(c['workspaces']) or 'none'}. "
                    f"Routine kinds of operation: {', '.join(c['categories'])}. "
                    + ("Inside those, operations proceed without a question; "
                       "anything outside them -- another directory, the network, "
                       "a Git remote, credentials, a Brain -- is still asked. "
                       if c["mode"] == _consent.TASK else
                       "Inside those, operations proceed without a question; "
                       "anything outside them is refused at once, without "
                       "asking the owner, so do not wait for an answer. "
                       if c["mode"] == _consent.DENY else
                       "Every operation you ask permission for is approved without "
                       "asking the owner and recorded. This is not authority over "
                       "Mentis: its operations are still checked against your "
                       "grant. The owner chose this and may change it during the run. "
                       if c["mode"] == _consent.ALL else "")
                    + "This is not permission to pursue side work.")
            # PUBLIC WEB RESEARCH, when the owner's request asked for it:
            # told whatever the consent mode, because it holds in every mode.
            r = c.get("research") or {}
            if r.get("authorized"):
                consent_said += (
                    "\n\n---\nWeb research (the owner's request asks for it"
                    + (f": \"{r['because']}\"" if r.get("because") and r.get("source") == "request" else "")
                    + "): searching the web and reading public pages with your runtime's "
                    "own web search and fetch tools proceed without a question, as many "
                    "as the research needs. Shell network commands (curl, "
                    "Invoke-WebRequest), sending local files or Brain content anywhere, "
                    "logging in, posting to services and running anything downloaded are "
                    "not research: they are still asked, or refused.")
            payload += consent_said
        # OTHER LIVE WORK'S LEASES INSIDE THIS RUN'S WORKSPACE (WS-L): told,
        # never a reason to refuse the run.
        from mentis.operational import leases as _leases
        payload += _leases.prompt_lines(cv, workspace=getattr(instance, "workspace", None),
                                        execution=instance.instance_id,
                                        held=lambda e: svc.authority.session_held(e, st.path))
        # WHAT THIS PARTICIPANT'S LAST REPLY HERE WILL NOT RENDER, when this
        # boundary wrote it after that run had exited and nobody was told.
        # Read here because this run was starting anyway; see `owed`.
        owed = None
        if conversation:
            owed = _render_check.owed(cv, participant, conversation, started)
            if owed:
                payload += "\n\n---\n" + owed

        situation = payload[situation_from:]
        # The notes above each open with their own rule; the reply format
        # follows them under its own heading, and the closing block is last.
        notes = payload.strip("\n")
        if notes.startswith("---\n"):
            notes = notes[4:].lstrip("\n")
        # CONTEXT RESTORATION (round 2): a continuation of the same work sent in
        # a FRESH session -- no native resume, or one MARS could not load --
        # is given the request in full and its previous run's reply, from the
        # record. Only in the full payload: a resumed session holds both.
        restored = (_continuity.restoration_block(cv, expectation, exclude=started,
                                                  participant=participant)
                    if resumed_from else "")
        # THE POST THE REQUEST REPLIES TO, read from the record on every run of
        # it -- first, resumed, retried, restarted -- so an approval stays on
        # the exact post and work it answered (`threads`). Context, not a
        # decision. A record this cannot read leaves the task as it was.
        try:
            from mentis.conversation import threads as _threads
            replying = (_threads.reply_target_block(cv, expectation)
                        if expectation else "")
        except Exception:                                 # noqa: BLE001
            traceback.print_exc()
            replying = ""
        payload = SPLIT.join([_task_block(work, done_when, replying)]
                             + ([restored] if restored else [])
                             + ([notes] if notes else [])
                             + [reply, _closing_block(work, done_when)])
        clock.step("payload_built")

        # THE CONTINUATION (WS-P), for a run that asks to continue its earlier
        # runtime session (decided above): if MARS resumes it, the run is sent
        # this -- what is new, and always the current authority, consent and
        # closing block; otherwise the full payload above, as before.
        # Follow-ups reach it exactly as they always have: in the resume
        # text, and through `follow_ups_unseen` at its next delegation or claim.
        continuation = None
        if resume:
            told_now = situation.strip("\n")
            if told_now.startswith("---\n"):
                told_now = told_now[4:].lstrip("\n")
            continuation = _continuity.continuation_prompt(
                task=_task_block(work, done_when, replying),
                authority=authority, authority_line=wf_line,
                consent_text=told_now,
                closing=_closing_block(work, done_when), split=SPLIT)

        # A DEADLINE ONLY WHERE SOMEBODY ASKED FOR ONE. There used to be a
        # silent ten-minute kill here, and it stopped real work mid-task
        # and recorded it as failed. Omitted, the service's own policy
        # applies, which is no deadline unless the owner set one.
        outcome = svc.agents_perform(instance.instance_id, payload,
                                     deadline_s=deadline_s, run=started,
                                     **({"resume": resume,
                                         "continuation": continuation}
                                        if resume else {}),
                                     timing=clock.spans)
        clock.mark("ended")
    except Exception as exc:          # a runtime that would not run, or worse
        # NOTHING RECORDED AS DELIVERED. Composing may fail on a Persona the
        # record does not hold, and performing may fail before anything
        # crossed. In neither case is there evidence to write. Where something
        # DID cross and the failure came afterwards, this under-records rather
        # than over-records, which is the direction to be wrong in: a delivery
        # that may not have happened must never be asserted.
        if execution is not None:
            cv.end_execution(execution.reference)
        # A run that never reached the runtime, or whose perform raised, is no
        # longer held here either way.
        svc.agents_end_run(started)
        cv.record_act(actor=participant, act=FAILED, conversation=conversation,
                      turn=turn, execution=instance.instance_id,
                      runtime=instance.runtime, caused_by=started,
                      because=f"{type(exc).__name__}: {exc}",
                      detail={"traceback": traceback.format_exc()[-600:],
                              # the spans up to the failure (WS-P); what
                              # was not reached yet is absent
                              **_end_facts(clock, None,
                                           locals().get("session_basis"),
                                           locals().get("resume"),
                                           locals().get("resume_why"),
                                           None)})
        # A CLAIM THIS RUN MADE (`respond`) before its perform raised is
        # reconciled against this failure: pending, said why.
        _reconcile_at_end(cv, expectation, instance.instance_id)
        # THE HANDLE GOES BACK. A run that failed leaves a session nobody
        # should presume is clean, so it is not offered for continuation --
        # and an instance that can never be continued must not sit in the
        # live set forever either. Releasing is about OUR handle; the
        # runtime keeps whatever session it has.
        svc.agents_release(instance.instance_id)
        return {"ok": False, "why": str(exc), "instance": instance.instance_id}

    if execution is not None:
        try:
            # ONLY IF A PROCESS ACTUALLY RAN. An absent runtime comes back as
            # an ordinary failed outcome rather than an exception, and nothing
            # crossed then -- `started` is Foundation saying which it was.
            # `operation_ok` is a different question: the material crossed
            # even when the work went badly.
            if outcome.started and offered:
                # NOT A DELIVERY RECORD. What governs behaviour is delivered;
                # a list of files a run may read is not governing material, and
                # putting it in the delivery table would make "what reached
                # this execution" mean two things.
                cv.record_act(actor=participant, act=_artifacts.MADE_AVAILABLE,
                              conversation=conversation, turn=turn,
                              execution=instance.instance_id,
                              runtime=instance.runtime, caused_by=started,
                              about=list(offered),
                              because="listed by reference in the work sent "
                                      "to the run; whether it read any is "
                                      "recorded only if it asked",
                              # WHY EACH ONE: the request was made with it, it
                              # was in a Turn the request explicitly
                              # referenced (named), or the work returned it.
                              detail={"why": why_offered})
            if outcome.started and composition.components:
                # Evidence of what crossed, whatever it was: a Persona, the
                # material placed at this Conversation, or both. A run that
                # carried nothing records no delivery, because nothing did.
                # A RESUMED SESSION (WS-P) holds this material from its
                # earlier run, unchanged (`continuity.decide`), and was not
                # sent it again: said by the mechanism.
                cv.record_delivery(
                    execution, composition,
                    mechanism=("resumed-session" if ((outcome.evidence or {})
                               .get("resumed") or {}).get("resumed")
                               else "dispatch"),
                    operation_ok=outcome.terminal == "reported_done",
                    # HOW MUCH OF EACH CROSSED, as condensed above
                    deliveries=deliveries)
        finally:
            cv.end_execution(execution.reference)

    # WHAT THIS RUN HANDED BACK, joined by the record and not inferred: the
    # returns this execution recorded under this request. Named on whichever
    # act ends the run, so bytes a failed run returned are not lost from view.
    returned = [a["about"][0] for a in cv.history(
        execution=instance.instance_id)
        if a["act"] == _artifacts.RETURNED and a["about"]
        and a.get("caused_by") == expectation]
    said = (outcome.reported or "").strip()
    # THE RUN'S OUTCOME CLAIM, if its final text ends with an ```outcome
    # block (`operational.completion`): taken out of the text, which then
    # carries a one-line rendering of it instead. Any scope may claim this
    # way, delegated children included; the claim is recorded below, once
    # the run's end is, and reconciled there.
    from mentis.operational import completion as _completion
    inspected = _completion.inspect(said)
    claimed, said_clean = inspected["claim"], inspected["text"]
    # A BLOCK THAT IS NOT A VALID CLAIM (never closed, no or two results,
    # text after it, only quoted) claims nothing: the reply is kept exactly
    # as written, and why it is unclaimed goes on the act that ends the run.
    unclaimed = inspected["unclaimed"]
    if claimed is not None:
        said = _completion.with_rendering(said_clean, claimed,
                                          cv.alias(participant))
    # ONE EXECUTION, ONE ANSWER -- asked before anything is decided about how
    # this run ended, because the answer changes what silence at exit MEANS.
    answered = _already_answered(cv, execution=instance.instance_id,
                                 request_turn=turn, since=started)
    # A RUN THAT ANSWERED THROUGH `respond` with an outcome block that was
    # not a claim: that answer's own act says why (`worker` respond), and it
    # is the run's last word on its outcome when nothing at exit claims.
    # The answer `respond` gave IS the run's word on its outcome: what its exit text says
    # about an outcome block never overrides it (a valid claim made through `respond` is not
    # flagged "not valid" because the exit text quoted a block; round-3 final review).
    if claimed is None and answered is not None:
        unclaimed = _respond_unclaimed(cv, instance.instance_id, answered)
    # A RUN THAT ANSWERED AND THEN SAID NOTHING MORE HAS NOT FAILED. Reporting
    # nothing at exit used to be indistinguishable from returning nothing at
    # all, so a clean run whose whole answer went through `respond` was recorded
    # as `nothing reported` -- a failure, for doing exactly the right thing.
    # That mattered little while every run also printed its answer; it matters
    # entirely once `respond` owns the answer, because then an empty exit is the
    # normal shape of success and not a silence worth reporting.
    if outcome.terminal != "reported_done" or (not said and answered is None):
        # NO REPLY IS POSTED. A run that did not report is not an answer, and
        # inventing one here would be the interface lying about the record.
        # WHY IT FAILED, WHERE SOMEBODY WILL LOOK FOR IT.
        #
        # Traced from a real Antigravity failure recorded as exactly
        # `terminal 'failed', exit -1, nothing reported`. The run had lasted
        # 8.6 milliseconds, the adapter had caught an exception and put its
        # text in `RunResult.error`, Foundation had turned that into a note --
        # and this act kept neither, so the one specific thing anybody had
        # observed never reached the record and is now unrecoverable for that
        # execution.
        #
        # `nothing reported` describes the silence, not the failure, and it is
        # only the whole truth when nothing else was observed either.
        classified = option_failure(outcome.evidence,
                                    {f: r["source"] for f, r in provenance.items()})
        why = (f"terminal {outcome.terminal!r}, exit {outcome.exit_code!r}"
               + (f": {outcome.error}" if outcome.error
                  else ", nothing reported" if not said else ""))
        # WHO ENDED THE RUNTIME, when the record shows it (`execution.interference`):
        # a command that terminates processes BY NAME, this run's or another's, run
        # just before its runtime's process exited. Said, with the command, so that
        # whoever decides on a retry does not read it as a flaky runtime.
        terminated_by = _terminated_by(cv, instance, outcome)
        if terminated_by is not None:
            from mentis.execution import interference as _interference
            try:
                alias = cv.alias(terminated_by["actor"]) if terminated_by.get("actor") else None
            except Exception:                             # noqa: BLE001
                alias = None
            why += "; " + _interference.words(terminated_by, alias=alias)
        cv.record_act(actor=participant, act=FAILED, conversation=conversation,
                      turn=turn, execution=instance.instance_id,
                      runtime=instance.runtime, caused_by=started,
                      because=why,
                      detail={"terminal": outcome.terminal,
                              "exit_code": outcome.exit_code,
                              **({"terminated_by": terminated_by}
                                 if terminated_by is not None else {}),
                              # ASKED AND OBSERVED, side by side, because a
                              # thinking model that spends its whole budget
                              # reasoning fails exactly like this -- `nothing
                              # reported` -- and only these say why.
                              "requested_effort": effort,
                              "reasoning_items": outcome.reasoning_items,
                              # The runtime's own words, verbatim, and the
                              # notes Foundation gathered around them.
                              "error": outcome.error,
                              "notes": list(outcome.notes),
                              "returned_artifacts": returned,
                              # WHAT RAN AND WHY, AS EVIDENCE FOR WHOEVER IS
                              # COORDINATING: they may authorize a new execution
                              # on something stronger. Nothing here retries.
                              "selected": {"runtime": instance.runtime,
                                           "model": instance.requested_model,
                                           "effort": instance.requested_effort},
                              "field_sources": {f: r["source"]
                                                for f, r in provenance.items()},
                              **({"routing": routed_record} if routed_record else {}),
                              **({"failure_classification": classified}
                                 if classified else {}),
                              # RAW, AND KEPT APART FROM THE INTERPRETATION.
                              # `error` is what Mentis will say went wrong;
                              # this is what the runtime actually emitted, so
                              # a failure can be reconstructed later instead
                              # of re-guessed. Omitted when the runtime gave
                              # nothing, rather than filled in.
                              # WHAT COMPILED PERMISSION RULES LET IT DO
                              # (`web.permissions.audit_of`).
                              **({"audit": outcome.evidence["audit"]}
                                 if "audit" in (outcome.evidence or {}) else {}),
                              **({"runtime_evidence": _evidence_kept(outcome.evidence)}
                                 if outcome.evidence else {}),
                              **_end_facts(clock, outcome, session_basis,
                                           resume, resume_why, resumed_from)})
        # A CLAIM THIS RUN MADE EARLIER (`respond`) is reconciled against how
        # it ended: a failure after the claim keeps it pending, said why.
        _reconcile_at_end(cv, expectation, instance.instance_id)
        # THE HANDLE GOES BACK. A run that failed leaves a session nobody
        # should presume is clean, so it is not offered for continuation --
        # and an instance that can never be continued must not sit in the
        # live set forever either. Releasing is about OUR handle; the
        # runtime keeps whatever session it has.
        #
        # EXCEPT AT A DEADLINE. Nothing went wrong there: a boundary was
        # reached. Releasing would discard the provisioned home and with it
        # the session, so the one case where continuing the work is most
        # likely to be wanted is the one where it was being made impossible.
        if not outcome.timed_out:
            svc.agents_release(instance.instance_id)
        return {"ok": False, "why": outcome.terminal,
                "instance": instance.instance_id, "exit_code": outcome.exit_code}

    # ONE EXECUTION, ONE ANSWER. If this run already answered the request it
    # carried -- through `respond`, which is the deliberate path and owns the
    # answer -- this boundary writes NO second Turn. It still records everything
    # below: the terminal, the exit code, what model and effort were observed,
    # and the final text itself. Suppressing the Turn is not discarding the
    # text; the text becomes run-state evidence on the act, where operational
    # visibility belongs, instead of a second independently composed answer
    # standing beside the first as though the agent had replied twice.
    if answered is None:
        # `say` writes the Turn and links, not its operational act. Readers
        # finding answers through `turn-said` must see this fallback just as
        # they see `respond`. Keep both writes together, without claiming the
        # work met or putting a runtime badge on a conversational act.
        with cv._c.atomic():
            reply = cv.say(conversation, participant, [text_part(said)],
                           replies_to=turn,
                           # What actually typed it, which is not who it is
                           # attributed to. The session is part of that fact where
                           # one is known.
                           written_by=_wrote_it(instance))
            cv.record_act(
                actor=participant, act="turn-said", conversation=conversation,
                turn=reply, execution=instance.instance_id,
                caused_by=expectation,
                because="this execution's answer to the request it carries",
                detail={"answers_request": expectation, "answers_turn": turn})
        # WHAT IN IT WILL NOT RENDER, ON THE RECORD. The run has exited, so
        # there is nobody to hand a tool result to: the check of the Turn just
        # written goes on the act below that records how the run ended, about
        # this reply. The Turn stands as written whatever it says.
        rendering = _render_check.of_turn(cv.corpus, reply)
        # A CHOICE FOR THE OWNER WRITTEN INTO IT INSTEAD OF ASKED is asked:
        # a decision form on this reply, owed by the owner, when this run
        # raised none (`prose_decisions`). The reply stands as written.
        from mentis.web.prose_decisions import raise_from_reply
        asked = raise_from_reply(cv, instance.instance_id, reply, expectation,
                                 actor=participant, runtime=instance.runtime)
        # AND THE CHOICE IS SAID beside the rendering (P8): as asked, or,
        # where it was not the owner's, as written instead of asked.
        rendering = _render_check.with_choices(
            rendering, _render_check.texts_of_turn(cv.corpus, reply),
            cv.corpus, instance.instance_id,
            asked=asked["form"] if asked else None)
    else:
        # THE ANSWER THAT ALREADY EXISTS. The result evidence is named ONTO it
        # rather than onto nothing, so a reader asking "what did this run return
        # and how did it end" finds both on the one Turn that answered.
        reply = answered
    # A DECISION FORM THIS RUN ASKED WITH NO `on` GOES ON ITS ANSWER POST
    # (P7), now that it exists. `respond` already put any it had asked by
    # then; one asked after it, or by a run that never called it, goes here.
    try:
        cv.attach_pending_forms(instance.instance_id, reply, by=participant)
    except Exception:                                     # noqa: BLE001
        traceback.print_exc()
    # WHAT ACTUALLY RAN, READ BACK RATHER THAN ECHOED. The request said which
    # model was wanted, or said nothing; the instance says which one the
    # runtime reported using, and the two were measured to differ. A question
    # like "which model produced this result" can only be answered from the
    # observed value, so that is what is recorded beside the reply.
    observed: dict = {}
    try:
        from mentis.api.types import Provenance
        after = svc.agents_observe(instance.instance_id)
        observed = {
            "observed_model": getattr(after.actual_model, "value", None),
            "observed_model_how": (
                None if not getattr(after.actual_model, "value", None)
                else "reported by the provider"
                if getattr(after.actual_model, "provenance", None)
                == Provenance.PROVIDER_REPORTED
                else getattr(after.actual_model, "note", None)
                or "declared by MARS"),
            "observed_model_why_not": (
                None if getattr(after.actual_model, "value", None)
                else getattr(after.actual_model, "note", None)),
            "observed_effort": getattr(after.actual_effort, "value", None),
            "observed_effort_why_not": (
                None if getattr(after.actual_effort, "value", None)
                else getattr(after.actual_effort, "note", None)),
            "session_ref": after.session_ref,
            # THE PROVIDER OF WHAT ACTUALLY RAN, asked of the catalogue about
            # the OBSERVED model rather than the requested one. That is the
            # difference that matters: a run that asked for a local model and
            # was served a hosted one comes back with the hosted model here,
            # and therefore with no provider -- so "I asked Ollama for this and
            # something else answered" is readable from the two acts without
            # anybody having to know which slugs are local.
            "observed_provider": svc.provider_of(
                instance.runtime, getattr(after.actual_model, "value", None)),
            # AND WHETHER THAT IS EVEN ASKABLE. No runtime reports its provider;
            # this is the catalogue's answer about a model, which is a different
            # and weaker thing. Said plainly rather than presented as an
            # observation the runtime made.
            "observed_provider_how": (
                "looked up in the local catalogue by the observed model slug; "
                "no runtime reports the provider that served a run"),
        }
    except Exception as exc:
        observed = {"observed_model_why_not": f"{type(exc).__name__}: {exc}"}

    stopped_notes = [n for n in outcome.notes
                     if n.startswith("process stopped by Mentis")]
    # WHAT IT LEFT UNFINISHED: background work the session close stopped, or
    # uncommitted changes in a git tree it edited -- MARS's reading, recorded.
    incomplete = incomplete_of(getattr(outcome, "evidence", None))
    cv.record_act(actor=participant, act=RETURNED, conversation=conversation,
                  turn=reply, execution=instance.instance_id,
                  runtime=instance.runtime, caused_by=started,
                  because=("the run reported and this is what it said"
                           if answered is None else
                           "the run reported; it had already answered, so this "
                           "records how it ended and what it last said"),
                  detail={"terminal": outcome.terminal,
                          "exit_code": outcome.exit_code,
                          # WHICH PATH OWNED THE ANSWER, said plainly rather
                          # than left to be inferred from whether a Turn was
                          # created here. `respond` when the run used it, this
                          # boundary when it did not.
                          "response_owner": ("respond" if answered
                                             else "dispatch-completion"),
                          # WHY NOTHING WAS CLAIMED, when the reply tried:
                          # an outcome block that is not a valid claim
                          # (`completion.inspect`). The reply is as written.
                          **({"outcome_unclaimed": unclaimed}
                             if unclaimed and claimed is None else {}),
                          # WHETHER MENTIS STOPPED ITS PROCESS: a run that
                          # answered and lingered is ended by its waiter
                          # (`RunObservation.settle_due`), and says so.
                          **({"process_stopped": stopped_notes}
                             if stopped_notes else {}),
                          # RETURNED INCOMPLETE: not review-ready, and the
                          # parent is told so when it resumes. Absent on a
                          # clean return.
                          **({"incomplete": incomplete,
                              "returned_incomplete": True}
                             if incomplete else {}),
                          # AND THE FINAL TEXT, WHENEVER IT WAS NOT THE ANSWER.
                          # THIS IS THE WHOLE REASON SUPPRESSION IS SAFE. The
                          # two answers in the record were worded differently
                          # and each carried a detail the other did not, so a
                          # boundary that merely stopped writing the second
                          # would delete evidence -- silently, which is worse
                          # than duplicating it. Kept verbatim, beside the
                          # terminal, where run-state is read. Absent when this
                          # boundary wrote the answer itself, because then the
                          # text IS the Turn and repeating it would say the
                          # record held two things when it holds one.
                          **({"final_text": said,
                              "final_text_why": (
                                  "the run printed this at exit after it had "
                                  "already answered through `respond`; it is "
                                  "kept as evidence of how the run ended and "
                                  "is NOT a second answer")}
                             if answered and said else {}),
                          "requested_model": model,
                          # WHAT WAS ASKED, AND WHAT THE STREAM SHOWED. A
                          # provider can accept an effort and ignore it, so
                          # the request is never evidence it was honoured.
                          "requested_effort": effort,
                          "reasoning_items": outcome.reasoning_items,
                          # WHAT IT CALLED, IF THE RUNTIME SAYS. Recorded
                          # beside the model and tokens already kept here,
                          # because the same act is where somebody later asks
                          # `did this work actually use a tool`. It is an
                          # observation of THIS run: an empty list on work
                          # that needed no tool proves nothing, which is why
                          # the second field is recorded with it rather than
                          # letting absence speak.
                          # credentials masked (`mentis.redaction`)
                          "tool_calls": [_redact_call(c) for c in outcome.tool_calls],
                          "tool_calls_observable": outcome.tool_calls_observable,
                          # Beside the reply, not in it: the reply's text is
                          # what the run wrote, and these are what it handed
                          # back. Nothing is read out of prose.
                          "returned_artifacts": returned,
                          # Only for a reply this boundary wrote; `respond`
                          # handed its own check back to the run.
                          **({"rendering": rendering} if answered is None
                             else {}),
                          # HOW MARS SAID THE TURN ENDED: stop reason, its
                          # session, when it ran. An observation, never a
                          # verdict on whether the work is done.
                          # WHAT COMPILED PERMISSION RULES LET IT DO
                          # (`web.permissions.audit_of`).
                          **({"audit": outcome.evidence["audit"]}
                             if "audit" in (outcome.evidence or {}) else {}),
                          **({"runtime_evidence": _evidence_kept(outcome.evidence)}
                             if outcome.evidence else {}),
                          # WHERE THE TIME WENT, THE RUNTIME SESSION A LATER
                          # RUN MAY CONTINUE, AND WHETHER THIS ONE CONTINUED
                          # ONE (WS-P).
                          **_end_facts(clock, outcome, session_basis,
                                       resume, resume_why, resumed_from),
                          **observed,
                          **{k: v for k, v in (outcome.usage or {}).items()
                             if isinstance(v, (int, float, str))}})
    # THE CLAIM, AFTER THE END. The run's own words about its outcome are
    # recorded as its claim, about its own expectation, and reconciled now
    # that the run has ended: an execution ending never completes work by
    # itself, and neither does a claim -- `reconcile` decides what is
    # recorded. With no block, a claim this run made earlier through
    # `respond` is reconciled against the end instead.
    if claimed is not None and expectation:
        try:
            _completion.claim(
                cv, expectation, claimed, actor=participant,
                execution=instance.instance_id, runtime=instance.runtime,
                via="reply", reply_turn=reply, conversation=conversation,
                participant=participant)
        except Exception:                                 # noqa: BLE001
            traceback.print_exc()
    _reconcile_at_end(cv, expectation, instance.instance_id)
    return {"ok": True, "instance": instance.instance_id, "reply": reply,
            "runtime": instance.runtime, "terminal": outcome.terminal}


def _evidence_kept(evidence) -> dict:
    """MARS's evidence as recorded under `runtime_evidence`: without the
    timing, which `_end_facts` records under `timing`."""
    return {k: v for k, v in (evidence or {}).items() if k != "timing"}


def _end_facts(clock, outcome, session_basis, resume, resume_why,
               resumed_from) -> dict:
    """What a run's end act records for WS-P: `timing` (Mentis's spans and the
    boundary's, with MARS's own under `mars`), `runtime_session` (the token
    MARS gave and what the session was opened under, for `continuity`), and,
    on a continuation, `continuity` (asked, resumed, why)."""
    evidence = getattr(outcome, "evidence", None) or {}
    out: dict = {"timing": {**clock.record(), **(evidence.get("timing") or {})}}
    held = evidence.get("runtime_session")
    if isinstance(held, dict) and held.get("token"):
        out["runtime_session"] = {**(session_basis or {}), **held}
    if resumed_from:
        said = evidence.get("resumed") or {}
        out["continuity"] = {"asked": bool(resume),
                             "resumed": bool(said.get("resumed")),
                             "why": said.get("why") or resume_why,
                             "decided": resume_why}
    return out


def _reconcile_at_end(cv, expectation, execution) -> None:
    """Reconcile the newest claim about this run's expectation, when this
    execution made it. A failure here is printed and never fails the run's
    own record."""
    if not expectation:
        return
    try:
        from mentis.operational import completion
        c = completion.latest_claim(cv, expectation)
        if c is not None and c.get("execution") == execution:
            completion.reconcile(cv, expectation, c)
    except Exception:                                     # noqa: BLE001
        traceback.print_exc()


def _offer(corpus, refs) -> str:
    """The artifacts a run may read, as the lines the run is shown."""
    lines = []
    for ref in refs:
        d = _artifacts.describe(corpus, ref, verify=False)
        lines.append(f"- {ref}: {d.get('name') or '(no name given)'} "
                     f"(claimed {d.get('claimed_media_type')}, "
                     f"{d.get('size')} bytes, {d['state']})")
    return ("\n\n---\nARTIFACTS YOU MAY READ. Mentis holds their bytes; read "
            "one with your `read_artifact` tool and its reference, and return "
            "a file you make with `return_artifact`. Names are metadata.\n"
            + "\n".join(lines))


def dispatch_soon(st, **kw) -> None:
    """Run a dispatch without holding the request open.

    `Execution.perform` blocks until the agent's turn ends,
    and an HTTP POST cannot sit on that. The Turn is already durable before
    this is called, the START act lands immediately, and the reply arrives in
    the Conversation when the run actually finishes -- which the interface
    already notices, because it re-reads after a change.

    A thread, not a worker system. Nothing is queued, retried or scheduled.
    """
    # WHEN IT WAS ASKED FOR, the first of a run's timing spans (WS-P).
    kw.setdefault("triggered_at", time.time())

    def go():
        try:
            dispatch(st, **kw)
        except Exception as exc:
            # NEVER ONLY A TRACEBACK. `dispatch` records its own failures now,
            # so reaching here means something outside all of them broke -- and
            # a request whose only trace is a line on somebody's stderr is a
            # request that looks like it is still being worked on. The act is
            # recorded first; printing is what it always was, a last resort.
            try:
                _failed_before_start(
                    st.cv, participant=kw.get("participant"),
                    conversation=kw.get("conversation"), turn=kw.get("turn"),
                    expectation=kw.get("expectation"), stage="dispatch-thread",
                    exc=exc, requested={k: kw.get(k) for k in
                                        ("runtime", "model", "effort",
                                         "requires")})
            except Exception:
                pass                  # the print below is all that is left
            traceback.print_exc()

    threading.Thread(target=go, daemon=True,
                     name=f"dispatch-{kw.get('participant','?')[:8]}").start()


# -- a delegation committed and never started (round 4, C2) --------------------

#: The act a server's start writes when it starts a delegation that was
#: recorded and never started: caused by the child request, naming the
#: `work-delegated` act it recovers. It is the claim: written in the
#: transaction that checks nothing has started the child, so of two passes
#: one writes it.
DELEGATION_RECOVERED = "delegation-recovered"
#: The act a server's start writes when it will NOT start such a delegation,
#: with why (`detail.reason`): the delegation is then resolved, and no later
#: start asks about it again. Continuing that work is somebody's act.
DELEGATION_NOT_RECOVERED = "delegation-not-recovered"
#: THE BOUND (owner decision, round 4: "a committed delegation is durably
#: represented as pending execution until it is started or explicitly
#: resolved"; AGENTS.md "Background work"). What starts it: a server starting
#: to serve a Brain, once, before it answers any request (`web.serve`). It
#: reads only delegations recorded in the RECOVERY_WINDOW_S before that start;
#: older ones are not read and stay shown as delegated and not started. It
#: starts at most RECOVERY_LIMIT runs per pass (the rest are resolved as not
#: recovered, "limit"), and claims one delegation at most RECOVERY_ATTEMPTS
#: times over all starts (a pass cut before the run it claimed started is the
#: only way to a second). No timer, thread or poll: one pass, and the runs it
#: starts go through `dispatch_soon` like every other.
RECOVERY_WINDOW_S = 24 * 3600
RECOVERY_LIMIT = 20
RECOVERY_ATTEMPTS = 2

#: Why a pass did not start one, in the words the work state shows.
NOT_RECOVERED_WORDS = {
    "withdrawn": "the request was withdrawn",
    "met": "the request is already recorded met",
    "parent-closed": "the work it was delegated under is met or withdrawn",
    "owner-stopped": "the owner asked the run that delegated it to stop",
    "owner-said-since": "the owner handed that work a follow-up the run that "
                        "delegated it never read",
    "reassigned": "somebody else carries it now",
    "no-words": "the post that asked for it is deleted or empty",
    "attempts": f"recovery already started it {RECOVERY_ATTEMPTS} times and "
                f"no run was recorded starting",
    "limit": f"more than {RECOVERY_LIMIT} delegations were waiting at this "
             f"start",
}


def _turn_words(cv, turn) -> str:
    """A post's words as Mentis shows it now; "" when deleted or none."""
    from mentis.conversation.versions import flow_text, presented
    if not turn:
        return ""
    try:
        got = cv._c.read([turn])
        entry = presented(cv._c, got[0]) if got else None
    except Exception:                                     # noqa: BLE001
        return ""
    if not entry or entry.get("deleted"):
        return ""
    return flow_text((entry.get("body") or {}).get("parts"))


def delegation_start(cv, delegation) -> dict:
    """What the record says of one delegation's start, from the child's own
    acts since the delegation: `started` (a run recorded starting, or
    failing before it could), `resolved` (a pass recorded it not recovered)
    and `attempts` (passes that claimed it)."""
    child = (delegation.get("about") or [None])[0]
    acts = ([a for a in cv.history(caused_by=child)
             if a.get("at") is not None and a["at"] >= delegation["at"]]
            if child else [])
    return {"child": child,
            "started": [a for a in acts if a["act"] in (STARTED, FAILED)],
            "resolved": [a for a in acts
                         if a["act"] == DELEGATION_NOT_RECOVERED],
            "attempts": [a for a in acts if a["act"] == DELEGATION_RECOVERED]}


def pending_delegations(cv, *, now: float | None = None,
                        window_s: float = RECOVERY_WINDOW_S) -> list[dict]:
    """Delegations recorded in the window and never started -- no run of the
    child recorded starting or failing since, and not resolved by a pass --
    oldest first. Read only."""
    now = time.time() if now is None else now
    out = []
    for d in cv._c.operational(act="work-delegated", since=now - window_s):
        if not d.get("about"):
            continue
        s = delegation_start(cv, d)
        if s["started"] or s["resolved"]:
            continue
        out.append({"delegation": d, **s})
    out.sort(key=lambda p: p["delegation"]["at"])
    return out


def _why_not_recover(cv, d, child, attempts) -> str | None:
    """Why this delegation must not be started now, as a reason, or None.
    Each is a boundary the owner or the record already holds; none is new."""
    detail = d.get("detail") or {}
    parent = d.get("caused_by")
    if withdrawal_of(cv, child):
        return "withdrawn"
    try:
        state = cv.expectation_state(child)
    except ValueError:
        return "no-words"
    if state.get("satisfied_by"):
        return "met"
    parent_is_work = bool(parent) and (cv._act(parent) or {}).get("act") \
        == "expectation-recorded"
    if parent_is_work and (withdrawal_of(cv, parent)
                           or cv.expectation_state(parent).get("satisfied_by")):
        return "parent-closed"
    run = d.get("execution")
    if run:
        starts = [a["id"] for a in cv._c.operational(act=STARTED,
                                                     execution=run)]
        if starts and cv._c.operational(act="execution-stop-asked",
                                        caused_by=starts):
            return "owner-stopped"
        if parent_is_work and cv.follow_ups_unseen(parent, run):
            return "owner-said-since"
    try:
        carrier = cv.assigned_carrier(child)["carrier"]
    except ValueError:
        carrier = None
    if carrier != detail.get("participant"):
        return "reassigned"
    if not _turn_words(cv, d.get("turn")).strip():
        return "no-words"
    if len(attempts) >= RECOVERY_ATTEMPTS:
        return "attempts"
    return None


def _resolve(cv, d, child, reason, pass_id) -> str | None:
    """Record that this pass will not start it -- if, in this transaction,
    nothing has started or resolved it."""
    with cv._c.atomic():
        s = delegation_start(cv, d)
        if s["started"] or s["resolved"]:
            return None
        return cv.record_act(
            actor="mentis", act=DELEGATION_NOT_RECOVERED,
            conversation=d.get("conversation"), turn=d.get("turn"),
            caused_by=child, about=[child, d["id"]],
            because=("not started when the server started again: "
                     + NOT_RECOVERED_WORDS[reason]
                     + "; continuing it is somebody's act"),
            detail={"delegation": d["id"], "reason": reason,
                    "delegated_by": d.get("actor"),
                    "parent": d.get("caused_by"),
                    "delegating_execution": d.get("execution"),
                    "pass": pass_id})


def _claim(cv, d, child, pass_id) -> str | None:
    """The recovery's claim: written only if, in this transaction, nothing
    has started the child, no pass resolved it, and fewer than
    RECOVERY_ATTEMPTS passes claimed it."""
    with cv._c.atomic():
        s = delegation_start(cv, d)
        if s["started"] or s["resolved"] \
                or len(s["attempts"]) >= RECOVERY_ATTEMPTS:
            return None
        return cv.record_act(
            actor="mentis", act=DELEGATION_RECOVERED,
            conversation=d.get("conversation"), turn=d.get("turn"),
            caused_by=child, about=[child, d["id"]],
            because=("its delegation was recorded and no run of it started "
                     "before the server stopped; started now, as it was "
                     "delegated"),
            detail={"delegation": d["id"], "delegated_by": d.get("actor"),
                    "parent": d.get("caused_by"),
                    "delegating_execution": d.get("execution"),
                    "attempt": len(s["attempts"]) + 1, "pass": pass_id})


def _start_of(cv, d, child, claim) -> dict:
    """The dispatch the door would have made for this delegation, read from
    the record: the same request, Participant, Persona and constraints. What
    the run may do is read from the child's request when it starts
    (`authority_for`), as for every run."""
    detail = d.get("detail") or {}
    constraints = detail.get("constraints") or {}
    turn = ((cv._act(child) or {}).get("turn") if detail.get("picked_up")
            else d.get("turn"))
    return dict(conversation=d.get("conversation"), turn=turn,
                participant=detail.get("participant"),
                work=_turn_words(cv, d.get("turn")),
                persona=detail.get("persona"),
                runtime=constraints.get("runtime"),
                model=constraints.get("model"),
                effort=constraints.get("effort"),
                requires=list(detail.get("requires") or ()),
                expectation=child,
                because=(f"recovered by {claim}: delegated in {d['id']}, "
                         f"recorded before the server stopped and never "
                         f"started"))


def recover_delegations(st, *, start=None, now: float | None = None,
                        window_s: float = RECOVERY_WINDOW_S,
                        limit: int = RECOVERY_LIMIT) -> dict:
    """ONE PASS, AT A SERVER'S START: start once, as it was delegated, each
    delegation recorded in the window that no run has started; resolve, with
    why, each it must not start. Returns what it did.

    WHY IT EXISTS (round 4, C2). `delegate` commits the child request and its
    `work-delegated` act, and the door dispatches after the commit. A process
    that died between the two -- or before the dispatch recorded its start --
    left a delegation recorded and never started, and nothing started it.

    WHAT IT NEVER DOES. Create work: it starts only a recorded child request,
    for its recorded carrier, with the dispatch the door would have made
    (`_start_of`). Start a child that has a run: the claim (`_claim`) is
    written only where no `execution-started` or before-start failure exists
    since the delegation. Override the owner: a withdrawal, a met request or
    parent, a Stop asked on the delegating run, a follow-up it never read, a
    reassignment (`_why_not_recover`) each resolves it instead, recorded.

    WHO MAY CALL IT: only the server holding the Brain's serving lock, once,
    before it serves any request (`web.serve`), so no dispatch of this
    process is between a delegation and its start. `start` has
    `dispatch_soon`'s shape (st, **kw)."""
    cv = st.cv
    start = start or dispatch_soon
    now = time.time() if now is None else now
    pass_id = f"recovery-{int(now * 1000)}"
    done = {"recovered": [], "not_recovered": [], "pass": pass_id}
    started = 0
    for p in pending_delegations(cv, now=now, window_s=window_s):
        d, child = p["delegation"], p["child"]
        try:
            reason = _why_not_recover(cv, d, child, p["attempts"])
            if reason is None and started >= limit:
                reason = "limit"
            if reason:
                act = _resolve(cv, d, child, reason, pass_id)
                if act:
                    done["not_recovered"].append(
                        {"delegation": d["id"], "child": child,
                         "reason": reason, "act": act})
                continue
            claim = _claim(cv, d, child, pass_id)
            if not claim:
                continue
            started += 1
            done["recovered"].append({"delegation": d["id"], "child": child,
                                      "act": claim})
            start(st, **_start_of(cv, d, child, claim))
        except Exception:                                 # noqa: BLE001
            # ONE DELEGATION THAT CANNOT BE READ never keeps the server from
            # serving, nor the others from being asked.
            traceback.print_exc()
    return done


def _terminated_by(cv, instance, outcome) -> dict | None:
    """The recorded command that terminated this run's runtime by name, or None
    (`execution.interference`). Only for a runtime whose process exited
    (`backend_exited`); every observed call buffered so far is written first, so
    a killer's command seen a moment ago is in the record when it is read."""
    evidence = outcome.evidence or {}
    if evidence.get("error_kind") != "backend_exited":
        return None
    try:
        from mentis.execution import interference
        from mentis.web import permissions as _perm
        audit = _perm._audit_for(cv)
        with audit._cond:
            runs = list(getattr(audit, "_observed", {}) or {})
        for run in runs:
            audit.observed_flush(run)
        audit.flush(timeout=5.0)
        return interference.find(
            cv._c, execution=instance.instance_id, runtime=instance.runtime,
            ended_at=evidence.get("finished_at") or time.time(),
            own_calls=outcome.tool_calls or ())
    except Exception:                                     # noqa: BLE001
        return None
