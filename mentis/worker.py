"""What a dispatched worker is allowed to ask Mentis about Mentis.

WHY THIS EXISTS. An agent was asked whether a local worker had done a piece
of work on a Turn. It had been dispatched by Mark IV, into a Mark IV
worktree, to answer a question about Mark IV's own record -- and it answered
by running `findstr` over the repository, opening every SQLite file it could
find, failing to find the name, and concluding the record did not exist.

That was not the agent behaving badly. It was the only thing available to it.
A worker is started as a subprocess with a prompt on stdin and a working
directory, and nothing else: no corpus handle, no orientation, no way to ask
a question. Faced with a question about a record it could not address, it did
what anyone would do with a filesystem and no interface.

So this is the interface. It is deliberately small, deliberately read-only,
and deliberately scoped to ONE corpus -- the one the dispatching server is
already using -- so that "the current record" is a fact of how the worker was
started rather than something it has to locate, guess, or be told the path
to. The abstraction is: an agent asks Mentis about Mentis, and gets an answer
from observed durable and operational facts.

WHAT IT WILL NOT DO. It does not write. It does not reach outside its corpus.
It does not answer a question the record cannot answer: an unknown reference
comes back as unknown, with the reason, rather than as an empty result that
reads like an absence of fact. And it does not score, rank or summarise
anything -- it reports what was recorded and who recorded it.

It speaks MCP over stdio in the stdlib alone, because a query seam that
needed a dependency installed in every workspace would not be available in
the places it is most needed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any

import mentis.api as api
from mentis.conversation import (KNOWING_HOW, KNOWING_THAT, knowing_of,
                                 text as text_part)

PROTOCOL = "2024-11-05"

#: HOW A GRANT IS PRESENTED, in one place because two sides read it.
#: A header rather than a body field, so that every route can see one was
#: offered -- including the routes that exist to refuse it.
CAPABILITY_HEADER = "X-Mentis-Worker"

#: WHERE A HAND-STARTED SESSION ASKS FOR ITS GRANT, and `+ "/end"` gives it
#: back. Two sides read it: the server route and `serve`. See `SESSION_SCOPE`.
SESSION_ROUTE = "/api/worker/session"

#: How the spine writes a reference. Entries, operational acts and Admissions
#: -- which is what a held artifact is -- so a worker handed any can ask what
#: it is.
ENTRY_REF = re.compile(r"^(?:ent|opr|adm)-[0-9a-f]+$", re.I)

#: THE READS. Every execution gets these, a Scratch answer included, and they
#: are the whole of what a worker could do before this. Named as a set because
#: two places have to agree on which operations need no scope beyond holding a
#: grant at all.
#:
#: `kinds` JOINED THE ORIGINAL FOUR because an agent asked "how many of each
#: Kind, and how many proposed vs. established" had no way to answer but to
#: guess: the counts existed for the owner's UI (`/api/kinds`,
#: `/api/governed`) and reached no agent.
#:
#: THE SOURCE READS JOINED BY OWNER DECISION (conversation ent-cc71013e9872,
#: Turn 19, option 1 "Default agent capability"; Turn 29, C). Every dispatched
#: execution can discover acquired Bulk Source collections, their history and
#: links, and read bounded pages of their retained bytes -- see
#: `mentis.sources.reading`. They are reads of the record, admitted by holding
#: a grant like the others. No Governance check authorises each one, and no
#: collection ACL or per-agent grant exists; nothing here claims otherwise.
#:
#: THEIR OWN NAME, NOT PART OF `READS`, because the decision that granted them
#: was about dispatched agents and a Scratch answer had to be decided
#: separately: its runtime is launched with `--tools ""` -- measured, no shell,
#: no file access and no web -- so its Mentis grant is the WHOLE of its
#: capability, and for it these reads were a genuinely new power rather than a
#: formalisation of what its own tools could already do.
#:
#: THE OWNER HAS NOW DECIDED IT (opr-9fa00d2183a9, "Yes, give Quick Ask the
#: source and artifact reads"; the option chosen: "Quick Ask can quote acquired
#: files and held artifacts. Its reads stay unrecorded, as all Quick Ask reads
#: are."). A Quick Ask holds these and `read_artifact` -- see `permitted` --
#: and a Quick Ask's reads are UNRECORDED BY DESIGN: nothing durable is
#: written when it reads, which is what it was promised.
#:
#: WHAT A QUICK ASK SEES OF A COLLECTION BEFORE IT READS ANY BYTES, BY OWNER
#: RULING (#66, ent-c36debac8263: "I want Quick Ask to have access to most of
#: what Mentis has. That's its point."). Its `find` returns acquired hits --
#: object key, label, collection name and the observation's `adm-` -- and its
#: `resolve(adm-...)` returns that observation's provenance: collection,
#: object, version n of m and the sweep act. Both are reads of the record's
#: names, deliberate and not a leak. The later decision above added the bytes.
#:
#: `search_sources` JOINED WITH SOURCES A (`adm-fc4356b9eff0`, approved "Yes,
#: A after B"), with exactly `read_source`'s reach and, like it, unrecorded:
#: it scans the same acquired text `read_source` serves and returns where a
#: phrase occurs, with excerpts `read_source` reads back exactly. It is a
#: read of what the source reads already reach, so it widens nobody's reach.
SOURCE_READS = ("sources", "source_history", "source_links", "read_source",
                "search_sources")

#: THE STATES AN ACQUIRED OBJECT CAN BE IN, as the connector records them
#: (`mentis.sources.filesystem`). Named here so `sources` can refuse a
#: filter that is not one of them instead of answering with an empty
#: listing -- which would teach a worker that a populated collection holds
#: nothing. `None` means every state.
_SOURCE_STATES = ("present", "absent")
#: `check_rendering` runs the UI's Markdown readers over text the caller gives
#: it (`mentis.conversation.render_check`) and writes nothing, so every run
#: may ask it, Scratch included. The one thing it reads of the record, when
#: there is one, is whether a timer's about= ids name entries it holds.
#:
#: `governed`, `owner_decisions`, `capabilities` and `brief` JOINED as reads
#: of what already existed and reached no agent that was not handed it:
#: the register the owner's UI reads (`/api/governed`), the decisions a
#: dispatch brief names, the capability names a `requires` is checked
#: against, and the navigation brief a dispatched run is composed with --
#: now askable of any Conversation by whoever holds a grant.
READS = ("orient", "find", "resolve", "history", "kinds", "check_rendering",
         "governed", "owner_decisions", "capabilities", "brief", "recall",
         "work_overview")

#: THE OPERATIONS THAT WRITE A TURN OF THE CALLER'S OWN MARKDOWN, and the key
#: of their result naming it. That Turn is read back once written and checked
#: for rendering, and what will not render is put in the result
#: (`_operate`). The post is never refused for it (owner decision, Conversation
#: "Markdown Renderer Maturation"). `request_decision` writes no Turn since
#: forms build P9: its questions are a decision form on a post.
TURN_WRITERS = {"respond": "turn",
                "record_discovered_work": "turn", "delegate": "turn",
                "deep_dive": "opening_turn", "record_request": "turn",
                "record_outcome": "turn"}

#: ASKING THE OWNER FOR A DECISION. Every dispatched execution gets this, not
#: only an organising one: a specialist that discovers the next step is a
#: person's to take must be able to say so, and the alternative is prose in a
#: reply that nothing can find again. It writes an expectation OF THE REQUESTER
#: and nothing else, so it confers no ability to assign work to anybody.
#:
#: AND HANDING FILES ACROSS, in both directions, for the same reason: any
#: execution may make something worth keeping, and any execution may be asked
#: with a file. `return_artifact` puts bytes this run made into Mentis's
#: custody; `read_artifact` gets the bytes of an artifact this run was GRANTED
#: -- see `mentis.artifacts.granted` -- and refuses everything else. Neither
#: names a recipient, assigns anybody or reaches another Conversation.
#: `read_artifact` is the one ASK a Scratch answer also holds, unrecorded --
#: see `permitted`.
#:
#: AND SAYING WHAT ELSE THIS WORK WAITS FOR. `await_work` records that the
#: request this run carries cannot go on until other recorded work is claimed
#: met. It is about this work's own waiting and nothing else: it dispatches
#: nobody, asks nothing of the awaited work's carrier, and grants nothing.
#:
#: AND PROPOSING A REVISION OF WHAT THIS RUN WAS TOLD. `propose_revision`
#: writes a CANDIDATE of the same Kind as material this run was delivered, put
#: forward to replace it (`proposes-to-supersede`). The material it names goes
#: on standing; only the owner's `establish-replacement` replaces anything. It
#: is refused for material the run was not delivered, so a run can improve the
#: Discipline it worked under and cannot reach any other.
#:
#: AND THE EPISTEMIC LADDER'S FOUR ACTS, WHEREVER `propose_revision` IS (owner
#: decision 8). `record_material` writes what work taught a run, with its
#: basis, and asks nobody anything; `request_adoption` asks the owner to adopt
#: something; `challenge` disputes material with a reason and revokes nothing;
#: `withdraw_challenge` takes back the run's OWN challenge, with a reason. None
#: of them confers standing: only the owner adopts.
LADDER_ACTS = ("record_material", "request_adoption", "challenge",
               "withdraw_challenge")
#:
#: AND SAYING THE WORK WAITS FOR THE OWNER'S INPUT. `request_input` records
#: that the request this run carries cannot go on until the owner has filled
#: in a form, checklist, editable table or pad and marked it ready (Done). It
#: is `request_decision`'s counterpart for a block: owed by the owner, asking
#: nothing of anybody else, and granting nothing.
#:
#: AND ANSWERING A FORM UNDER ITS OWN NAME. `answer` records one field's
#: value in a response set as this run's Participant
#: (`mentis.conversation.responses`): attributed, versioned, never knowledge,
#: and never in place of the owner -- on a block in a post addressed to the
#: owner it records only a proposal quoting the owner's own words (P2b, F1).
#:
#: AND A TIMER, ONLY ON THE OWNER'S WORD. `timer` reads a timer block and
#: marks the owner's timer only when the call names the owner's direction
#: (`mentis.conversation.timers`): never by itself.
#:
#: AND SAYING HOW A REVIEW CAME OUT. `record_verdict` records the verdict of
#: the review this run carries -- pass, block or incomplete, with the
#: capabilities it lacked -- as a `review-verdict` act on its own request.
#: It judges nothing else and asks nobody anything.
#:
#: (Mark IV's `commit_work` is gone: Mentis commits nothing. Git belongs to
#: whoever asked for the work and to the agent.)
ASKS = ("request_decision", "request_input", "answer", "timer",
        "record_discovered_work",
        "return_artifact", "read_artifact", "await_work",
        "propose_revision", "record_verdict") + LADDER_ACTS

#: WHAT ORGANISING WORK REQUIRES, AND WHY IT IS A SEPARATE SET. These are
#: admissible only for an execution dispatched to carry an unaddressed request
#: -- the scope the grant carries. A specialist that such an execution delegates
#: to is dispatched with ordinary worker scope, so it holds none of these except
#: HANDS_OFF below. Authority comes from why the execution was dispatched, and a
#: delegated execution was not dispatched for this. A specialist that needs
#: organising done returns that need rather than doing it.
#:
#: *** THIS BOUNDS FAN-OUT ONLY FOR A RUN THAT KEEPS PRESENTING ITS GRANT, AND
#: THAT IS NOT A SECURITY PROPERTY. *** This used to claim the scope split "is
#: what bounds fan-out", full stop. Measured, and it is false: a headerless
#: request to the ordinary turns route with `action: ask-mentis` makes the
#: server mint a FRESH grant scoped `intake`, carrying every operation below --
#: `open_conversation`, `summon_participant` and the `coordinate` authority
#: included. So an
#: ordinary worker-scoped run upgrades itself by DROPPING its own credential,
#: in one HTTP call, and no depth counter would have seen it because the chain
#: is not walked, it is side-stepped.
#:
#: The split is still worth having: it is what Mentis HANDS OUT, it keeps the
#: honest path honest, and a run that follows the interface cannot fan out. It
#: is not a wall. The wall does not exist -- see the `_api` docstring in
#: `mentis/web/__init__.py` for why, and what it would cost to build one.
ORGANISES = ("open_topic", "open_conversation", "summon_participant",
             "propose_material", "respond")

#: HANDING WORK ON IS NOT ORGANISING. Every dispatched execution may hand
#: work outside its role to the Participant whose role it is. It does not
#: become them and gains none of their Persona: the child is dispatched as
#: itself, caused by this request, in this Conversation (`_where`), with no
#: wider reach than this work has. Whether a role SHOULD hand something on is
#: its Persona's to say; this is only that the tool is there when it does.
#: `delegate` IS A CAPABILITY, NEVER AUTHORITY. It is not in ORGANISES, and
#: nothing decides what a run may do from its holding `delegate` or from
#: `delegate` appearing in a grant. It hands on the work THIS RUN CARRIES,
#: with the configuration that delegation needs -- who (brought into the
#: Conversation if they are not in it), runtime, model, effort, requirements
#: and a repository directory -- each subject to the parent's own reach and the ordinary
#: checks. Taking on work this run does not carry is COORDINATE's (owner
#: rulings ent-fb17dc421a42, ent-94edb8bc6342 and the F-2 revision).
#: `delegate` enforces that line where it acts, in `_operate`.
#:
#: NO DEPTH LIMIT, DELIBERATELY. Before this, a delegated run that needed
#: another role had no way to involve it and could only return the need, which
#: nothing picked up. A depth number would bring that back at whatever depth it
#: named. Scope, Persona, causal lineage and `delegate`'s own checks are the
#: bounds, and every step is recorded.
HANDS_OFF = ("delegate",)

#: AUTHORITY TO COORDINATE THIS WORK, recorded on the request by the person who
#: made it -- the "may coordinate this work" gesture, an explicit `authority`
#: list naming it, or the continuation of work that had it -- and read from
#: that record, never from the run, its Participant or its Persona
#: (`may_coordinate`). It is authority to ORGANISE WORK BEYOND WHAT THIS RUN
#: CARRIES: picking up discovered work nobody carries. It means nothing about
#: repositories. Delegating the work this run carries, however it is
#: configured -- a repository directory included -- needs none of it.
#:
#: ITS OWN NAME, NOT AN OPERATION. Everything in ORGANISES is an operation a
#: run may be shown and call; `coordinate` is neither, so it is not in
#: ORGANISES or OPERATIONS and `permitted` never returns it. Grants written
#: before it existed recorded `delegate` for the same authority; that is read
#: as `coordinate` in exactly one place, `Conversations.authority_of`.
COORDINATE = "coordinate"

#: EVERY NAME A GRANT ON A REQUEST MAY RECORD: the organising operations and
#: the authority to coordinate. Never `delegate`.
AUTHORITY = ORGANISES + (COORDINATE,)

#: ANCHORED INTERACTION (`mentis.conversation.anchors`). Anchoring a place in
#: a Turn and reacting to it are attributed interactions that confer nothing,
#: assign nobody and govern nothing, so every dispatched execution holds them
#: -- not Scratch's transient read, which leaves no mark. They act only on
#: Turns in a Conversation this execution may act in (`_where`).
#:
#: A DEEP DIVE OPENS A CONVERSATION, so it is organising and is held exactly
#: when `open_conversation` is: it is the same authority, asked for one
#: reason, and is derived from it in `permitted` rather than listed in grants
#: recorded before it existed.
INTERACTS = ("anchor", "react")
DEEP_DIVE = "deep_dive"

#: RESUMING A REQUEST INTAKE COULD NOT ASSIGN is coordinating: it carries work
#: this run does not carry, so it is held exactly when the run's request was
#: granted COORDINATE -- derived in `permitted`, as DEEP_DIVE is, rather than
#: listed in grants (so a grant recorded before it existed holds it too), and
#: asked again in `_operate` by `may_coordinate`. The caller names only WHICH
#: request; the carrier, Persona, work and authority are read from the record
#: (`mentis.web.resume_intake`), so it can bring about nothing Ask Mentis
#: would not have when the request was asked.
RESUME_INTAKE = "resume_intake"

#: (Mark IV's `arm_deploy`, and `web_search` / `web_fetch` reached through the
#: Mentis server, are gone: there is no deploy supervisor, and MARS agents
#: have their own web tools.)

#: EVERY OPERATION, and the one place the list exists. A name absent here is
#: refused by not being present rather than by anybody remembering to exclude
#: it.
OPERATIONS = (READS + SOURCE_READS + ASKS + INTERACTS + HANDS_OFF
              + ORGANISES + (DEEP_DIVE, RESUME_INTAKE))

#: THE OPERATIONS THAT ONLY READ, so the door answers them as it answers a GET:
#: beside the writer, not queued behind its transaction (R1, `_Handler._api`).
#: Named one by one, never derived from READS: an operation joins this list
#: only once it is known to write nothing to the record. Each is answered by
#: `_result`, which appends nothing; what they keep is in memory (the context
#: cache, a reading scope, the deleted-reads banner) or derived beside the
#: record (`sources.extract.store`). `read_artifact` is NOT here: a dispatched
#: run's read records the supply. A name listed wrongly still answers the
#: same: the store refuses its write and the door answers it again outside.
READ_ONLY = ("orient", "find", "resolve", "history", "kinds",
             "check_rendering", "governed", "owner_decisions", "capabilities",
             "brief", "recall", "work_overview",
             "sources", "source_history", "source_links", "read_source",
             "search_sources")

#: WHAT A ROUTINE STATUS IS, now that the product shows a trunk's state.
#: Agents made up for an interface that showed nothing by retelling the whole
#: history in every report, and the owner lost the current state inside it.
#: The trunk's status surface carries state, carrier, children, what is owed
#: and when the record last changed, so a status that restates them only
#: competes with it. One sentence of guidance where a report is written, not a
#: register of rules: judgement, failures and findings are still prose.
#: REMOVED, AND WHY THE NAME IS NOT REUSED. A constant here used to prescribe
#: the SHAPE of a routine status -- five named lines, what not to restate, what
#: still belonged in prose -- and it was delivered twice: appended to
#: `respond`'s description, and appended directly to the work text of every
#: resumed run. That second one made this file a behavioural plane in its own
#: right: prose in Python reaching a run's instructions, needing nothing
#: established, nothing placed, nothing named, and recorded as no governance
#: source at all. `AGENT-BRIEF.local.md` was removed to stop exactly that, and
#: an independent review found this still doing it.
#:
#: WHAT IS GONE IS THE POLICY, NOT THE MACHINERY. Status states are still
#: computed, resumption still hands a carrier every child's ending, and
#: `respond` still says what it structurally is and does. What no longer
#: crosses is the instruction about how to write a status.
#:
#: NOTHING REPLACES IT YET, DELIBERATELY. Reporting shape is behavioural
#: material, so if it is wanted it belongs in Mentis as a Persona or a Rule
#: that was established, placed or named -- not as a constant any import can
#: deliver. No Rule has been established for it, and the owner's instruction
#: was to leave the hole visible rather than fill it to keep the architecture
#: tidy. This comment is the record of the hole.


#: The scope of a Scratch answer's grant. See `permitted`.
TRANSIENT_SCOPE = "transient-read"

#: A SESSION SOMEBODY STARTED BY HAND -- a `claude`, `codex` or `agy` the owner
#: opened themselves, reaching this server through the machine-wide MCP
#: registration rather than being dispatched (owner decision 2026-10-13:
#: standing access for manually started sessions, as Mark III had). Its grant is
#: minted by `Foundation.grant_session` from the same grant table a dispatched
#: run's is, and the same door (`/api/worker`) admits or refuses each call.
#:
#: WHAT IT MAY DO IS WHAT @Caretaker MAY DO (owner decision 2026-10-13): the
#: organising set and `coordinate` that a request addressed to nobody is
#: granted (`AUTHORITY`) -- summoning, delegating, opening Topics and
#: Conversations, proposing material -- except `SESSION_CARRIED`, which answer
#: or hang off a request a session does not carry. It acts in the
#: Conversations it opened (`_where`), and is the requester of the work it
#: hands on. Establishing stays the owner's: nothing here confers standing.
SESSION_SCOPE = "manual-session"

#: INTAKE AND RETURN FOR WORK SOMEBODY STARTED OUTSIDE MENTIS. These are
#: deliberately session operations, not caretaker operations and not a way
#: for a dispatched execution to answer some other request.
SESSION_ACTS = ("record_request", "record_outcome", "take_up")

#: WHAT ONLY A CARRIED REQUEST GIVES MEANING TO: answering it, asking the
#: owner to decide under it, waiting under it, finding work under it, committing or
#: returning into it, revising what it delivered, and reading what it reaches.
#: Each refuses without one ("this execution carries no expectation"), so a
#: session is not shown them -- a tool that always refuses is a worse surface
#: than a smaller one (`serve`).
SESSION_CARRIED = ("respond", "request_decision", "request_input", "answer",
                   "timer",
                   "await_work", "return_artifact",
                   "propose_revision", "read_artifact", "record_verdict")

#: WHO A HAND-STARTED SESSION IS RECORDED AS. One durable Participant, never a
#: runtime's name: which runtime ran a session is the act's own `runtime`, and
#: which session did it is the act's own `execution`, so neither is folded
#: into the Participant.
SESSION_PARTICIPANT = "@ManualSession"


def session_label_problem(label) -> str | None:
    """Why `label` cannot name a hand-started session's runtime, or None.

    FOR A RUNTIME MENTIS HAS NO ADAPTER FOR -- a local model, Kimi K3, anything
    MARS starts -- whose session would otherwise get no grant at all. The label
    follows the Participant-name rule (opr-938e0fa58007: English letters,
    digits, `-`, `_`, starting with a letter) and is only ever WRITTEN: on the
    session's acts as their `runtime` and in what it writes as `written_by`.
    Nothing reads a session grant's runtime as an adapter -- `end_session`,
    `session_held`, renewal and every recorded act take it as a string -- and
    the scope it gets is `SESSION_SCOPE`, exactly as a known runtime's.

    A label that reads as a runtime Mentis does run, or a model family
    (`participant_names.reserved_as`: `Claude`, `agy`, `codex-cli`), is
    refused, so a session's acts can never pass for that runtime's. The
    adapter's own name is not a label and never reaches here.
    """
    from mentis.conversation.participant_names import (alias_problem,
                                                       reserved_as)
    text = str(label or "")
    if not text:
        return "a session needs a `runtime`: an adapter's name, or a label"
    if text.startswith("@") or alias_problem(text):
        return (f"{text!r} is neither a runtime Mentis runs nor a label it "
                f"accepts: a label is English letters (A-Z, a-z), digits "
                f"(0-9), hyphen (-) and underscore (_), starting with a letter")
    taken = reserved_as(text)
    if taken:
        return (f"{text!r} reads as {taken!r}, which Mentis reserves for a "
                f"runtime or model family it names itself; a session's acts "
                f"must not pass for that runtime's. Use that runtime's own "
                f"name if it is that runtime, or another label")
    return None


def permitted(scope: str | None, operations=None) -> tuple[str, ...]:
    """What an execution dispatched with this scope may do.

    One function, because the MCP surface and the HTTP route must not be able
    to disagree about it. An unrecognised scope gets the ordinary worker set,
    which fails closed.

    `operations`, where the grant carries it, is the organising subset the WORK
    was granted -- read from the record at dispatch, so a request whose
    authority was narrowed gets exactly that and never the whole set. A name
    that is not an organising operation grants nothing by being listed.

    What a run may CALL, and nothing about what its work may do beyond that:
    every run may call `delegate`, so this is never asked whether the work
    may be coordinated. `may_coordinate` is.
    """
    # A SCRATCH ANSWER READS AND NOTHING ELSE (`mentis.scratch_store`): the
    # record reads, the source reads and `read_artifact`, BY OWNER DECISION
    # (opr-9fa00d2183a9: "Quick Ask can quote acquired files and held
    # artifacts. Its reads stay unrecorded, as all Quick Ask reads are.").
    # Not the rest of the ASKS: recording a decision, a piece of discovered
    # work, a wait or an artifact is a durable write, and a question asked in
    # Scratch can look but cannot leave a mark. For the same reason its
    # `read_artifact` records no supply (`_operate`) and reaches by its own
    # rule, having no request of its own (`mentis.artifacts.reachable`).
    if scope == TRANSIENT_SCOPE:
        return READS + SOURCE_READS + ("read_artifact",)
    # A HAND-STARTED SESSION: what @Caretaker may do, less what only a carried
    # request gives meaning to (`SESSION_SCOPE`, `SESSION_CARRIED`).
    if scope == SESSION_SCOPE:
        return tuple(o for o in permitted(
            "organising", AUTHORITY if operations is None else operations)
            if o not in SESSION_CARRIED) + SESSION_ACTS
    # EVERY DISPATCHED EXECUTION, whatever its scope, including a delegated
    # specialist and an unrecognised scope that fails closed to the ordinary
    # set. That is what "default agent capability" was decided to mean.
    base = READS + SOURCE_READS + ASKS + INTERACTS + HANDS_OFF
    if scope in ("intake", "organising"):
        if operations is None:
            return OPERATIONS
        organising = tuple(o for o in ORGANISES if o in operations)
        return (base + organising
                + ((DEEP_DIVE,) if "open_conversation" in organising else ())
                + ((RESUME_INTAKE,) if COORDINATE in operations else ()))
    return base


def _delegated_judge(surface, cv, args, *, model, conversation, governed,
                     persona):
    """What a Participant's default is judged by when work is delegated to
    them: `dispatch.runtime_judge` over EVERYTHING the child's run will
    require, by the same expression `_dispatch` uses -- what was stated (with
    what was inferred from the brief, already joined to `args["requires"]`),
    and what the governing material the child will carry requires (named for
    it, its activity's Disciplines, its Persona's, and what is placed where
    it runs, delivered in full). A default that lacks any of it does not bind.

    `holds` (recorded quota failures) is passed when `runtime_judge` accepts
    it, and left out when it does not; a judgement is never broken by it."""
    from mentis.web.dispatch import (delivered_in_full, governing_ids,
                                     requirements_of, runtime_judge)
    requires = list(args.get("requires") or ())
    named = list(governed or ())
    try:
        requires += list(requirements_of(cv, delivered_in_full(
            cv, conversation, governing_ids(cv, conversation, named, persona),
            named=named, persona=persona)))
    except Exception:                                     # noqa: BLE001
        # A requirement that cannot be read is the child's run's to refuse,
        # recorded there before anything starts; it binds nothing here.
        pass
    kw = {}
    try:
        import inspect
        if "holds" in inspect.signature(runtime_judge).parameters:
            from mentis.web.quota import quota_holds
            kw["holds"] = quota_holds(cv)
    except Exception:                                     # noqa: BLE001
        kw = {}
    return runtime_judge(getattr(surface, "agents", None),
                         requires=tuple(dict.fromkeys(requires)), model=model,
                         **kw)


def _activity_label(surface, grant, said) -> str | None:
    """`delegate`'s `activity`, checked, or None when none was said.

    "<reference>#<key>": the reference must be governing material this run
    was DELIVERED (its grant's `delivered`, which dispatch fills from what
    the composition actually governed with), and that material must carry an
    activity with the key. Nothing else is asked and nothing follows from it:
    it is a label the work status reads.
    """
    if said is None or said == "":
        return None
    if not isinstance(said, str) or said.count("#") != 1:
        raise NotPermitted('`activity` is "<workflow reference>#<activity key>"')
    ref, key = (x.strip() for x in said.split("#"))
    delivered = [str(d) for d in (grant or {}).get("delivered") or ()]
    if ref not in delivered:
        raise NotPermitted(
            f"{ref!r} is not governing material this run was delivered, so "
            f"its activities are not this run's to delegate. Delivered: "
            f"{[d for d in delivered if d.startswith('ent-')] or 'none'}")
    from mentis.conversation import activities_of
    got = surface.corpus.read([ref])
    keys = [row["key"] for row in activities_of(surface.corpus,
                                                got[0] if got else None)]
    if key not in keys:
        raise NotPermitted(
            f"{ref!r} has no activity keyed {key!r}. Its activities: "
            f"{keys or 'none'}")
    return f"{ref}#{key}"


def _activity_supplies(surface, activity) -> dict:
    """What a checked `activity` gives the child it is delegated to: its
    step's Persona and Disciplines, each at its CURRENT standing version.

    OWNER RULING 2026-10-29: delegated Builders and Reviewers receive their
    step's Persona and Disciplines. Before it, an activity was a label and the
    carrier had to name both by hand; a carrier that did not (#1026: ten
    delegations, Persona null) sent children with neither, and with no
    Reviewer Persona `review_signal` could not steer a review off the
    author's runtime.

    Resolved as the work status resolves an activity's Disciplines
    (`operational.work._discipline`): `current_of` follows the pinned id
    forward along its supersession line, so a revised Persona or Discipline
    reaches the child as its successor. What has no standing version is not
    passed on and is said, never substituted:

        persona       the Persona to wear, or None
        persona_why   why none, when the activity names one and it gives none
        disciplines   the Disciplines to add, current versions, in order
        withheld      [{"pinned", "why"}] for Disciplines that gave none
    """
    from mentis.conversation import activities_of, current_of
    ref, key = activity.split("#")
    got = surface.corpus.read([ref])
    row = next((r for r in activities_of(surface.corpus,
                                         got[0] if got else None)
                if r.get("key") == key), {})
    out = {"persona": None, "persona_why": None, "disciplines": [],
           "withheld": []}
    named = (row.get("who") or {}).get("persona")
    if named:
        cur = current_of(surface.corpus, named)
        if not cur["stands"]:
            out["persona_why"] = (f"the activity's Persona {named!r} has no "
                                  f"standing version ({cur['why']})")
        elif not surface.cv._is_kind(cur["entry"], "persona"):
            out["persona_why"] = (f"the activity's Persona {named!r} is not "
                                  f"a Persona")
        else:
            out["persona"] = cur["entry"]
    for d in row.get("disciplines") or ():
        cur = current_of(surface.corpus, d)
        if cur["stands"]:
            if cur["entry"] not in out["disciplines"]:
                out["disciplines"].append(cur["entry"])
        else:
            out["withheld"].append({"pinned": d, "why": cur["why"]})
    return out


def may_coordinate(grant: dict | None) -> bool:
    """Whether this run may organise work beyond what it carries. ONE PREDICATE.

    True only when the grant on the run's own request records COORDINATE --
    as `Conversations.authority_of` reads it, which is where a grant from
    before `coordinate` existed, listing `delegate`, is read as `coordinate`.
    `dispatch.authority_for` puts exactly that reading on the run's grant.

    NOT the scope, NOT `permitted`, and NOT who the run is: no Participant,
    alias or Persona -- Caretaker included -- implies it. Every run holds
    `delegate`, so what a run may call says nothing about this. An `intake` scope or an absent
    `operations` (the whole organising set, in `permitted`) is not authority
    either: no dispatched run is given either -- `dispatch.dispatch` gives
    every run `organising` or `worker` and the list read from the record --
    so they exist only on grants made by hand, and treating them as
    coordination would be authority nobody recorded.

    `delegate` in `_operate` asks this, and every call from the MCP surface
    reaches `_operate` through the one HTTP door, so they cannot disagree.
    """
    return COORDINATE in ((grant or {}).get("operations") or ())

#: HOW THIS SURFACE IS STARTED, in one place because more than one runtime
#: now starts it. An explicit path, an explicit corpus, and nothing taken from
#: the environment -- `-I` ignores even a PYTHONPATH we set, measured.
#: HOW THE MCP SERVER IS STARTED, and what it is allowed to reach. `via` and
#: `capability` are what make this the SAME bounded boundary the Codex
#: transport uses: with them the server asks the owner over `/api/worker`
#: under an invocation-scoped grant and opens nothing itself. Without them it
#: falls back to reading the record in-process, which is correct only for a
#: caller that legitimately holds it -- never for a dispatched worker.
#:
#: `permits` IS WHAT THIS RUN MAY DO, AND SO WHAT IT IS SHOWN. See `serve`.
BOOT = (
    "import sys; sys.path.insert(0, r'{root}'); "
    "from mentis.worker import serve; "
    "serve(r'{record}', via={via}, capability={capability}, permits={permits}, "
    "scratch={scratch}, project={project}, session={session})"
)


def boot_command(record: str, *, via: str | None = None,
                 capability: str | None = None, permits=None,
                 scratch: str | None = None, project: str | None = None,
                 session: str | None = None) -> str:
    """The one place a worker's MCP start command is built.

    Three adapters used to format `BOOT` themselves, each passing only the
    record -- which is how two runtimes ended up reading corpus.db directly
    while the third went through the grant. Built here so the bounded
    arguments cannot be forgotten by one caller and not another.

    `permits` NAMES WHAT THIS RUN MAY DO, so the surface can show exactly that.
    Foundation derives it from the grant's scope; no adapter composes it, and
    nothing a worker can reach sets it.

    `session` NAMES THE RUNTIME OF A HAND-STARTED SESSION, for the machine-wide
    registration only: with `via` and no `capability`, `serve` asks the server
    for a session grant itself (`SESSION_ROUTE`). No adapter passes it.
    """
    return BOOT.format(root=package_root(), record=record,
                       via=repr(via), capability=repr(capability),
                       permits=repr(tuple(permits) if permits else None),
                       scratch=repr(scratch), project=repr(project),
                       session=repr(session))


def package_root() -> str:
    """Where `mentis` is importable from, for a worker started with -I.

    Derived from this module's own location rather than the environment,
    because the environment is what -I exists to ignore.
    """
    import os
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Bounded because a worker asking an open question should get an answer it
#: can read, not the corpus. Every listing says what it did not return.
PAGE = 40

#: FILLABLE BLOCKS (forms build, P6). The block types that take answers, as
#: `isFillable` in ui/src/experimental/spec/fill.ts says; a table only when it
#: declares `editable=` or `select=one|many`, which is asked of that file's
#: own reader (`render_check.fill_of`), never of a second parser here. The
#: fence test is only a cheap "might this post hold one", so an ordinary Turn
#: is never extracted.
_FILL_TYPES = ("form", "checklist", "table", "pad")
_FILL_FENCE = re.compile(r"^[ \t]*(?:`{3,}|~{3,})[ \t]*(?:form|checklist|table|pad|panel)\b",
                         re.M)
#: The most fields `resolve` lists for one block; the rest are counted.
FIELDS_MAX = 100
#: The most changes one `history set= since=` page returns.
SINCE_MAX = 200


def _pending(not_searched: dict | None) -> dict:
    """What `find`'s content scan could not read YET: extractions being made
    in the background, by payload type. Empty when nothing is pending."""
    by_type = ((not_searched or {}).get("extraction") or {}).get(
        "extraction_pending") or {}
    n = sum(by_type.values())
    out = {"extractions": n, "by_type": dict(by_type)}
    if n:
        out["note"] = ("the text of these files is being extracted now and "
                       "was not searched; ask again shortly, or use "
                       "search_sources, which waits for it a bounded time")
    return out


def _when(at: float) -> str:
    """A moment as a reader can quote it back: UTC, to the second."""
    return datetime.fromtimestamp(at, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


class Surface:
    """The read-only view of one corpus, and the only thing the tools touch."""

    #: WHAT THIS RUN MAY DO, set by the owner when it answers for a worker.
    #: Machine-local and per-request, never durable: it is a fact about an
    #: execution, and the record holds no executions' authority.
    permits: tuple[str, ...] | None = None
    read_scope: str = "brain"

    def __init__(self, corpus_path: str, *, corpus=None,
                 read_scope: str = "brain") -> None:
        """One corpus, opened here or handed in.

        THE SAME SEAM ANSWERS BOTH CALLERS. A worker asking "what is this
        reference" and the composer's `#` picker asking "what could this
        reference be" are the same question, and answering them from two
        implementations would let them disagree about what exists. The web
        server passes the corpus it already has; a dispatched worker names a
        path and this opens it.
        """
        # OPENED HERE, IT MUST BE WRITABLE: a worker never half-runs on a
        # Brain the schema check opens read-only (`mentis.spine.migrations`).
        self.corpus = (corpus if corpus is not None
                       else api.open_corpus(corpus_path, access="write"))
        self.brain = api.brain(self.corpus)
        self.cv = self.brain.conversations
        self.path = corpus_path
        self.read_scope = read_scope

    # -- helpers ----------------------------------------------------------

    def _entry(self, ref: str) -> dict | None:
        """The entry AS IT NOW READS: an edited Turn or Topic with its current
        version's body, a deleted one blanked and marked `deleted`. See
        `mentis.conversation.versions`. Identity, author and time are the
        entry's own."""
        from mentis.conversation.versions import presented
        got = self.corpus.read([ref])
        return presented(self.corpus, got[0]) if got else None

    def _kind_of(self, e: dict) -> str | None:
        # The same place the web seam reads it from: an entry names its own
        # definition, and the definition's name IS the Kind.
        return (e.get("definition") or {}).get("name")

    def _conversation_name(self, cid: str) -> str | None:
        got = self._entry(cid)
        return got["body"].get("name") if got else None

    def _turn_line(self, e: dict) -> str:
        """The readable content of a contribution, references included.

        A structured reference is rendered as the characters the author wrote
        AND its identity, because a worker resolving this is usually trying to
        follow it. Nothing here re-reads prose to find references; they are
        parts, and they arrive as parts.
        """
        if e.get("deleted"):
            return "[deleted]"
        out = []
        for p in e.get("body", {}).get("parts", []) or []:
            if p.get("type") == "text":
                out.append(p.get("text", ""))
            elif p.get("type") == "object" and p.get("ref"):
                # ONE OBJECT IN A POST: its post and key (the live address)
                # and the version the author selected.
                out.append(f"{p.get('text') or ''}[object:{p['ref']}"
                           f"#{p.get('key')} {p.get('exact')}]")
            elif p.get("ref"):
                out.append(f"{p.get('text') or ''}[{p['type']}:{p['ref']}]")
        return "".join(out)

    # -- tools ------------------------------------------------------------

    def orient(self, conversation: str | None = None, *,
               scope: str | None = None) -> dict:
        """Where am I, and what is here."""
        if conversation:
            refused = self._conversation_or_refusal("orient", conversation)
            if refused:
                return refused
            cid = conversation.strip()
        else:
            cid = None

        effective_scope = scope or getattr(self, "read_scope", "brain")
        from mentis.core.context_cache import cache_for, revisions_for
        cache = cache_for(self.corpus)
        revs = revisions_for(self.corpus)

        if cid:
            # THE FOUNDATION CACHES ITSELF. Wrapping it in a second `get` under
            # its own key made the inner `get` wait on the outer one -- the same
            # computation, on the same thread -- for ever (found in the
            # concurrent verification: every cached orient timed out at 30 s).
            from mentis.core.orientation import foundation
            res, meta = foundation(self.brain, cid, scope=effective_scope,
                                   with_meta=True)
            return {**res, "cache": meta}

        deps = frozenset({"governance", "participants", "work", "conversations"})
        rev_token = revs.token(deps)
        key = ("orient", self.corpus.corpus_id, rev_token, None, None, None, effective_scope)

        def compute() -> dict:
            ident = {}
            try:
                ident = {"corpus_id": self.corpus.corpus_id}
            except Exception:
                ident = {"corpus_id": None}
            convs = []
            for c in self.cv.all_conversations():
                convs.append({
                    "conversation": c["id"],
                    "name": c["body"]["name"],
                    "about": c["body"].get("about", ""),
                    "turns": len(self.cv.contributions(c["id"])),
                })
            return {
                **ident,
                "corpus_path": self.path,
                "you_are_reading": (
                    "the Mark IV record this worker was dispatched from. It is the "
                    "only corpus this surface can see."
                ),
                "conversations": convs,
                "participants": len(self.cv.all_participants()),
                "kinds": self._kinds_in_brief(),
                "standing_governance": self._applicable_governance(),
                # WHAT YOU MAY DO, ANSWERED RATHER THAN INFERRED FROM YOUR TOOLBOX.
                # Real use found the gap: a Caretaker asked what was in force said
                # "the record says nothing about the grant scope -- I can see
                # organising tools, but that is what my surface shows, not what the
                # record says". It was right to distrust its toolbox, and right that
                # the record cannot answer this: authority belongs to the execution,
                # not to the corpus. So the OWNER answers it here, from the grant it
                # already checked, and the answer says which it is.
                "you_may": list(self.permits) if self.permits else None,
                "you_may_because": (
                    "the grant this execution was dispatched with, as the Mentis "
                    "that owns this record reads it. Not a durable fact and not "
                    "something the record holds -- ask again and it is computed "
                    "again." if self.permits else
                    "nothing answered for this call, so what you may do is whatever "
                    "the door admits; treat a refusal as the answer"),
            }

        res, meta = cache.get(key, compute, deps=deps, with_meta=True)
        return {**res, "cache": meta}

    def _applicable_governance(self, conversation=None) -> list[dict]:
        """Standing procedural material, names only, after supersession."""
        from mentis.conversation import content_of, first_line, rendering_of
        if conversation:
            rows = self.cv.governs(conversation)["governing"]
            return [{"id": r["entry"],
                     "title": first_line(r.get("text") or r.get("about")
                                         or r["entry"]),
                     "scope": list(r.get("placed") or ())}
                    for r in rows]
        out = []
        for e in self.cv.placed_brain_wide():
            if not self.corpus.stands(e["id"])["stands"]:
                continue
            kind = self._kind_of(e)
            title = self.cv._title_of(e) or first_line(
                content_of(e, *rendering_of(self.corpus, kind)))
            out.append({"id": e["id"], "title": title or e["id"],
                        "scope": ["whole-brain"]})
        return out

    def recall(self, work, conversation=None, *, participant=None, full=False,
               limit=None, persona=None, scope: str | None = None) -> dict:
        """The relevance and governance composition channel, compactly.

        `persona` composes as somebody wearing that Persona (`standing_material`
        resolves it), so what it carries is among what governs. `guidance`
        points to the standing Workflows and Disciplines whose "When it
        applies" meets the work (`guidance`), by reference only.

        SERVED THROUGH THE SHARED CONTEXT CACHE (`mentis.core.context_cache`),
        keyed by everything the answer depends on -- the work, the
        Conversation, the Persona worn, the caller's read scope and who is
        asking -- and dropped when a domain it read moves."""
        from mentis.conversation import first_line
        work = str(work or "").strip()
        if not work:
            return {"refused": True, "asked": "recall",
                    "why_not": "recall needs a description of the work"}
        wearing = None
        if persona not in (None, ""):
            wearing = standing_material(self, persona, PERSONA_KIND,
                                        by_name=True)
            if wearing.get("refused"):
                return {"refused": True, "asked": "recall", **wearing}
        pid = wearing["entry"] if wearing else None
        if conversation:
            refused = self._conversation_or_refusal("recall", conversation)
            if refused:
                return refused
            cid = conversation.strip()
        else:
            cid = None
        try:
            cap = 12 if limit in (None, "") else int(limit)
        except (TypeError, ValueError):
            return {"refused": True, "asked": "recall",
                    "why_not": f"`limit` is a whole number, not {limit!r}"}
        if cap < 1:
            return {"refused": True, "asked": "recall",
                    "why_not": "`limit` is at least 1"}
        cap = min(cap, 50)

        effective_scope = scope or getattr(self, "read_scope", "brain")
        from mentis.core.context_cache import cache_for, revisions_for
        cache = cache_for(self.corpus)
        revs = revisions_for(self.corpus)
        deps = frozenset(
            {"governance", "knowledge", "work", "participants"}
            | ({f"conversation:{cid}"} if cid else set()))
        task_digest = hashlib.sha256(work.encode("utf-8")).hexdigest()[:16]
        access_scope = ((effective_scope, participant) if participant
                        else (effective_scope,))
        key = ("recall", self.corpus.corpus_id, revs.token(deps), cid,
               task_digest, pid, (access_scope, bool(full), cap))

        def compute() -> dict:
            if cid:
                comp = self.cv.compose(conversation=cid, participant=participant,
                                       persona=pid, question=work)
            else:
                comp = self.brain.compose(participant=participant, persona=pid,
                                          question=work)
            tiers = {"governing": [], "adopted": [], "experience": []}
            omitted = {k: 0 for k in tiers}
            for c in comp.components:
                if c.tier not in tiers:
                    continue
                if len(tiers[c.tier]) >= cap:
                    omitted[c.tier] += 1
                    continue
                summary = first_line(c.text, 240)
                row = {"id": c.source_id, "kind": c.source_kind,
                       "title": c.title or summary, "summary": summary,
                       "why": c.why, "trailer": c.trailer or {}}
                if full:
                    row["text"] = c.text
                tiers[c.tier].append(row)
            return {"work": work, "conversation": cid,
                    **({"persona": wearing, "persona_note": PERSONA_NOTE}
                       if wearing else {}),
                    "full_text": bool(full), "limit_per_tier": cap,
                    "tiers": tiers, "omitted": omitted,
                    "guidance": guidance(self, work),
                    "withheld": list(comp.withheld)}

        res, meta = cache.get(key, compute, deps=deps, with_meta=True)
        return {**res, "cache": meta}

    def work_overview(self, conversation=None, limit=None, *,
                      scope: str | None = None) -> dict:
        """The existing work projection, bounded to outstanding items."""
        if conversation:
            refused = self._conversation_or_refusal("work_overview",
                                                    conversation)
            if refused:
                return refused
            cid = conversation.strip()
        else:
            cid = None
        try:
            cap = 20 if limit in (None, "") else int(limit)
        except (TypeError, ValueError):
            return {"refused": True, "asked": "work_overview",
                    "why_not": f"`limit` is a whole number, not {limit!r}"}
        if cap < 1:
            return {"refused": True, "asked": "work_overview",
                    "why_not": "`limit` is at least 1"}
        cap = min(cap, 100)

        effective_scope = scope or getattr(self, "read_scope", "brain")
        from mentis.core.context_cache import cache_for, revisions_for
        cache = cache_for(self.corpus)
        revs = revisions_for(self.corpus)
        deps = frozenset({"work"} | ({f"conversation:{cid}"} if cid else set()))
        key = ("work_overview", self.corpus.corpus_id, revs.token(deps), cid,
               None, None, (effective_scope, cap))

        def compute() -> dict:
            from mentis.operational import work_overview as wo
            got = wo.overview(
                self.cv, viewer=wo.owner_of(self.cv), conversation=cid,
                runtime={"runs": None,
                         "why_not": "the worker read has no live MARS feed"})
            outstanding = [i for i in got["items"]
                           if i.get("objective_met") is not True]
            keys = ("expectation", "title", "group", "state", "stage",
                    "status_words", "origin", "agents", "last_activity_at",
                    "objective_met", "follow_up", "generation")
            return {"conversation": cid, "counts": got["counts"],
                    "stage_counts": got["stage_counts"],
                    "outstanding_count": len(outstanding),
                    "items": [{k: i.get(k) for k in keys}
                              for i in outstanding[:cap]],
                    "omitted": max(0, len(outstanding) - cap), "limit": cap,
                    "needs_owner_unknown": got["needs_you_unknown"],
                    "needs_owner_why": got["needs_you_why"]}

        res, meta = cache.get(key, compute, deps=deps, with_meta=True)
        return {**res, "cache": meta}

    def kinds(self) -> dict:
        """How many entries of each Kind this Brain holds, and how they stand.

        EVERY KIND THE LIVE STORE DECLARES, with what `/api/kinds` gives the
        owner's UI -- name, fields, meaning, whether entries are true or false
        -- and beside it the count and the register's four-way split. Nothing
        here is derived a second time: the definitions are
        `register.kind_definitions`, the counts are `count_of_kind`, and the
        split is `register.standing_split`, which sorts by the same functions
        `/api/governed` does. So an agent, the UI and the register cannot
        disagree about the same store.

        AS READ, NOT AS KEPT. Nothing is stored or cached: the numbers are the
        record at `as_read_at`, and a later write changes them. Whatever could
        not be determined is None with the reason beside it, never 0.
        """
        from mentis.conversation.register import (kind_definitions,
                                                  standing_split)
        at = time.time()
        split = standing_split(self.corpus)
        rows = []
        for name, d in sorted(kind_definitions(self.corpus).items()):
            rows.append({**d, **split.get(name, {
                "entries": None,
                "entries_unknown_because": "its definition appeared between "
                                           "two reads; ask again"})})
        relations = {(e["body"] or {}).get("relation")
                     for e in self.corpus.definitions()} - {None}
        try:
            by_relation = {r: 0 for r in sorted(relations)}
            by_relation.update(self.corpus.count_of_links())
            links = {"total": sum(by_relation.values()),
                     "by_relation": by_relation}
        except Exception as exc:
            links = {"total": None,
                     "unknown_because": f"the store could not count them: "
                                        f"{type(exc).__name__}: {exc}"}
        return {
            "as_read_at": _when(at),
            "as_read": (
                "counted from the live store at as_read_at. Not kept anywhere "
                "and not a promise: a later write changes them, so ask again "
                "rather than reuse an old answer."),
            "kinds": rows,
            "definitions": {"kinds": len(rows), "relations": len(relations)},
            "links": links,
            "groups_mean": {
                "proposed": "written, neither established nor answered by a "
                            "successor. In the record; nobody was asked",
                "standing": "established, and nothing has superseded it",
                "history": "superseded -- after establishment (ended) or "
                           "before it (replaced, it never held)",
                "unknown": "standing not determined: the Kind does not "
                           "declare whether standing applies, or it could not "
                           "be computed. unknown_because says which",
            },
            "split_none_means": (
                "no split exists for that Kind or group, and split_because or "
                "unknown_because says why. None is never a count of zero"),
        }

    def _kinds_in_brief(self) -> dict:
        """One line per Kind for `orient`: the total and how it stands.

        SHORT ON PURPOSE. Every agent reads `orient` first, so this is the
        least that answers "how much of what is here, and how much of it is
        established" -- and it points at `kinds` for the rest. It is the SAME
        read `kinds` makes, cut down, so the two cannot disagree. A failure to
        count is said, never shown as an empty Brain.
        """
        try:
            got = self.kinds()
        except Exception as exc:
            return {"unknown": True,
                    "because": f"the counts could not be read: "
                               f"{type(exc).__name__}: {exc}"}
        lines = []
        for k in got["kinds"]:
            n, split = k.get("entries"), k.get("split")
            head = f"{k['kind']}: " + (
                str(n) if n is not None else "count unknown")
            if split is None:
                why = ("standing not meaningful"
                       if k.get("ground") == "standing_not_meaningful"
                       else "split unknown")
                lines.append(f"{head} ({why})")
            elif split["proposed"] is None:
                lines.append(f"{head} (standing undeclared: "
                             f"{split['unknown']} unknown)")
            else:
                parts = [f"{split[g]} {g}"
                         for g in ("recorded", "proposed", "standing", "history")]
                if split["unknown"]:
                    parts.append(f"{split['unknown']} unknown")
                lines.append(f"{head} ({', '.join(parts)})")
        links = got["links"]["total"]
        return {
            "as_read_at": got["as_read_at"],
            "lines": lines,
            "definitions": (
                f"{got['definitions']['kinds']} Kinds, "
                f"{got['definitions']['relations']} Relations, "
                + (f"{links} links" if links is not None
                   else "links uncounted")),
            "more": "as read at that moment. Ask `kinds` for each Kind's "
                    "fields and meaning, the full proposed / standing / "
                    "history / unknown split, and why any figure is unknown",
        }

    def resolve(self, ref: str) -> dict:
        """What is this identity, and what does the record say about it."""
        e = self._entry(ref)
        if e is None:
            # ABSENT, AND SAID SO. An empty result would read as "nothing
            # happened"; this says the record does not hold the reference at
            # all, which is a different fact and the one that matters.
            return {"ref": ref, "known": False,
                    "why_not": "this corpus holds no entry with that reference"}

        kind = self._kind_of(e)
        out: dict[str, Any] = {"ref": ref, "known": True, "kind": kind,
                               "recorded_at": e.get("recorded_at"),
                               "attributed_to": e.get("attributed_to"),
                               "written_by": e.get("written_by")}

        # DOES IT STAND, AND -- IF IT IS A LINK -- WHAT DOES IT JOIN.
        #
        # BOTH WERE MISSING, AND REAL USE FOUND IT. A Caretaker asked what was
        # in force for carrying unaddressed requests resolved the designation
        # and had to report three honest unknowns in a row: whether it was
        # established, which Participant and Persona it connects, and whether it
        # was the only one. The record answers all three. This read returned the
        # link's BODY and nothing else, so the one entry whose entire meaning is
        # the two things it joins came back saying only "carries requests
        # addressed to nobody" -- and a worker could not check the very fact it
        # was asked about. Standing is what `stands` already computes; the
        # endpoints are on the entry itself.
        # EDITED OR DELETED, said as the facts they are. What a deleted item
        # said is not handed on as usable: History holds it.
        if e.get("revision"):
            out["revision"] = e["revision"]
        if e.get("deleted"):
            out["deleted"] = e["deleted"]
        standing = self.corpus.stands(ref)
        out["stands"] = standing["stands"]
        out["established_by"] = standing["established_by"]
        out["superseded_by"] = standing["superseded_by"]
        body = e.get("body", {})
        if kind == "contribution":
            conv = self.cv.conversation_of(ref)
            out.update({
                "what": "a Turn",
                "conversation": conv,
                "number": self.cv.turn_number(ref),
                "said": self._turn_line(e),
                "author": e.get("attributed_to"),
                "author_alias": self.cv.alias(e.get("attributed_to")),
                "addressed_to": [
                    {"participant": p, "alias": self.cv.alias(p)}
                    for p in body.get("addressed_to", []) or []
                ],
                "references": [
                    {"type": p["type"], "ref": p["ref"], "text": p.get("text")}
                    for p in body.get("parts", []) or []
                    if p.get("ref")
                ],
            })
            from mentis.conversation import anchors
            if anchors.anchor_parts(body.get("parts")):
                out["anchored"] = anchors.route_back(self.cv, ref)
            fill = self._fillable(ref, e)
            if fill is not None:
                out["fillable"] = fill
            forms = self._decision_forms(ref)
            if forms:
                out["decision_forms"] = forms
        elif kind == "response-set":
            out.update(self._response_set(ref))
        elif kind == "conversation":
            from mentis.conversation.anchors import origin
            out.update({"what": "a Conversation", "name": body.get("name"),
                        "about": body.get("about"),
                        **({"origin": o} if (o := origin(self.cv, ref))
                           else {}),
                        "turns": len(self.cv.contributions(ref)),
                        "participants": [
                            {"participant": p, "alias": self.cv.alias(p)}
                            for p in self.cv.participants(ref)]})
        elif kind == "participant":
            out.update({"what": "a Participant", "alias": self.cv.alias(ref),
                        "about": body.get("about"),
                        "conversations": self.cv.conversations_of(ref)})
        elif kind == "topic":
            out.update({"what": "a Topic", "name": body.get("name"),
                        "about": body.get("about"),
                        "conversation": self.cv.conversation_of_topic(ref),
                        "turns": len(self.cv.topic_contributions(ref))})
        elif kind == "anchor":
            # A PLACE IN A TURN VERSION, resolved now: the exact selector, the
            # excerpt read from the immutable version (withheld once the Turn
            # is deleted), and what is attached to it.
            from mentis.conversation import anchors
            out.update({"what": "an Anchor", **anchors.view(self.cv, ref),
                        "interactions": anchors.interactions(self.cv, ref)})
        elif kind == "reaction":
            from mentis.conversation import anchors
            out.update({"what": "a Reaction", "token": body.get("token"),
                        "about": body.get("about"),
                        "note": "an attributed occurrence; it has no standing "
                                "and no effect on anything"})
        elif e.get("family") == "admission" and (
                (body.get("envelope") or {}).get("bulk_source")):
            # AN ACQUIRED OBSERVATION, said as one (B7): which object of which
            # collection, which version of how many, the sweep that produced
            # it and whether a newer one has been recorded since. It used to
            # come back as "a held artifact", which is true of its bytes and
            # says nothing about what it is an observation OF. The reference
            # is pinned: this names THIS observation, and a newer one is
            # shown, never followed (owner decision 3).
            from mentis.sources import Refused as _Refused, reading
            try:
                out.update(reading.provenance(self.corpus, ref))
            except _Refused as exc:
                out.update({"what": "an Admission", "why_not": str(exc)})
            else:
                from mentis import artifacts
                d = artifacts.public(artifacts.describe(self.corpus, ref,
                                                        verify=False))
                d.pop("url", None)
                # WHETHER IT IS A PICTURE, by the bytes' signature (Sources
                # B, B2): what lets a Turn draw it inline, never the name.
                got = artifacts.sniffed(self.corpus, d.get("digest"))
                if got is not None:
                    d["view"] = got["view"]
                    d["served_as"] = got["content_type"]
                out["artifact"] = d
                out["name"] = out.get("label")
        elif e.get("family") == "admission" and body.get("content") == "held":
            # WHAT STANDS BEHIND A HELD ARTIFACT, without its bytes: held,
            # missing, corrupt or purged are different answers. Reading the
            # bytes is `read_artifact`, and is granted separately.
            from mentis import artifacts
            d = artifacts.public(artifacts.describe(self.corpus, ref,
                                                    verify=False))
            d.pop("url", None)
            # WHETHER IT IS A PICTURE, by the bytes' signature and never the
            # name, as for an acquired observation above: an image an agent
            # returned is drawn inline by the same viewer.
            got = artifacts.sniffed(self.corpus, d.get("digest"))
            if got is not None:
                d["view"] = got["view"]
                d["served_as"] = got["content_type"]
            out.update({"what": "a held artifact", "artifact": d})
            # ITS NAME, TYPE AND SIZE ARE MATERIAL TOO. Attached to a Turn
            # that has since been deleted, this answer shows what came in on
            # it, so it says so (owner ruling on opr-b234b23b6ba5).
            marked = _deleted_marking(self, ref)
            if marked:
                out.update(marked)
        else:
            out.update({"what": f"an entry of kind {kind!r}", "body": body})

        # A LINK IS WHAT IT JOINS, and this goes LAST so the generic branch
        # above cannot overwrite it. A Link names a Relation rather than a Kind,
        # so it fell into that branch and came back described as "an entry of
        # kind 'carries-intake'" carrying only its body -- which for the
        # designation meant the words "carries requests addressed to nobody" and
        # not the Participant and Persona that are its entire meaning.
        link = e.get("link")
        if link:
            out["what"] = "a Link"
            out["relation"] = link.get("relation")
            out["links_from"] = link.get("from")
            out["links_to"] = link.get("to")
            # AN ALIAS ONLY WHERE THERE IS A PARTICIPANT. Most Links run from
            # something else -- an establishment from the Rule it establishes,
            # a reply from a Turn -- and those have no alias to give.
            out["links_from_alias"] = None
            for side in ("from", "to"):
                got = self._entry(link.get(side) or "")
                if got is None:
                    continue
                out[f"links_{side}_kind"] = self._kind_of(got)
                if side == "from" and out["links_from_kind"] == "participant":
                    out["links_from_alias"] = self.cv.alias(link["from"])
                name = (got.get("body") or {}).get("name")
                if name:
                    out[f"links_{side}_name"] = name

        # WHETHER IT STANDS TRAVELS WITH THE TEXT OF BEHAVIOURAL MATERIAL.
        # A worker resolving an instruction, a rule or a Persona got its
        # full text and nothing else, so a proposal nobody established read
        # exactly like material that governs. Keeping candidates readable is
        # the point -- they are meant to be argued with -- but handing one
        # over unqualified invites it to be obeyed.
        #
        # ASKED OF THE KIND'S DECLARATION, NEVER OF A LIST OF NAMES. The list
        # that used to be written here said "governing" of a `lesson`, which
        # declares `knowing: "that"` and governs nothing, and said nothing at
        # all about any Kind added since -- so a new procedural Kind resolved
        # by a worker arrived with no standing qualifier whatever.
        #
        # AND ANY KIND THAT DECLARES `knowing` AT ALL GETS ONE, because the
        # reason for the qualifier is the same on both ladders. Narrowing it to
        # `"how"` took the sentence away from every propositional Kind, so a
        # `lesson` nobody has established came back as its full text with
        # nothing saying so -- and a candidate conclusion handed over
        # unqualified is just as readily acted on as a candidate rule. The
        # WORDING is what differs, because the two ladders are different facts:
        # procedural material that stands GOVERNS the work, propositional
        # material that stands is something this Brain CARRIES FORWARD and
        # directs nobody. Absent is still absent: a Kind in neither ladder --
        # the record's own furniture -- gets no standing sentence, because
        # standing is not what decides whether a Conversation exists.
        knowing = knowing_of(self.corpus, kind)
        if knowing in (KNOWING_THAT, KNOWING_HOW):
            directs_work = knowing == KNOWING_HOW
            standing = self.corpus.stands(ref)
            out["stands"] = standing["stands"]
            out["standing"] = (
                ("governing: established, and not superseded" if directs_work
                 else "established: carried forward as something this Brain "
                      "knows, and governing nothing")
                if standing["stands"] else
                ("ended: superseded by later material" if directs_work
                 else "ended: superseded by later material, and no longer "
                      "carried forward")
                if standing["superseded_by"] else
                ("proposed: written down, established by nobody, and "
                 "governing nothing" if directs_work else
                 "proposed: written down, established by nobody, and asserted "
                 "by this Brain as nothing more than written down"))
            if standing["superseded_by"]:
                out["superseded_by"] = standing["superseded_by"]
        return out

    # -- fillable blocks and their response sets (forms build, P6) ---------

    def _fill_blocks(self, root, parts) -> dict:
        """The fillable blocks of a post as it now reads, each with whether
        what is filled in it can be saved and, when it can, its fields.
        `{"checked": False, "why_not"}` when the blocks could not be read."""
        from mentis.conversation import render_check
        from mentis.fluid import objects
        try:
            got = objects.post_objects(self.corpus, root)
        except Exception as exc:                         # noqa: BLE001
            return {"checked": False, "why_not": f"{type(exc).__name__}: {exc}"}
        if not got.get("extracted"):
            return {"checked": False, "why_not": got.get("why_not") or got.get("why")}
        rows = []
        for o in got["objects"]:
            if o.get("kind") != "block" or o.get("type") not in _FILL_TYPES:
                continue
            p = o.get("part")
            text = (parts[p].get("text") if isinstance(p, int) and 0 <= p < len(parts)
                    and isinstance(parts[p], dict) else None)
            unnamed = not o.get("name") or text is None
            # WHAT IT TAKES, read by the fill rules' own block reader
            # (`fillOf`): whether a table is edited or selected in, as the
            # table rules read editable= and select=, and the fields of a
            # block that has no usable name=.
            read = (render_check.fill_of(o.get("block") or {})
                    if o["type"] == "table" or unnamed else None)
            if o["type"] == "table" and read.get("checked") \
                    and not read["fillable"]:
                continue                 # a table nobody edits or selects in
            row = {"part": o.get("part"), "block": o.get("name"),
                   "type": o["type"], "title": o.get("title"),
                   "line": o.get("line"), "nested": o.get("parent") is not None}
            if unnamed:
                fields = [{k: f.get(k) for k in ("id", "label", "kind", "required")}
                          for f in (read.get("fields") or [])
                          if read.get("checked")]
                row.update(saveable=False, why=[
                    f"another block in this post also says name={o['duplicate']}"
                    if o.get("duplicate") else "it has no usable name="],
                    fields=fields[:FIELDS_MAX],
                    **({"fields_not_listed": len(fields) - FIELDS_MAX}
                       if len(fields) > FIELDS_MAX else {}),
                    **({} if read.get("checked")
                       else {"why_not": read.get("why_not")}))
                rows.append(row)
                continue
            check = render_check.answers(text, o["name"], {})
            if not check.get("checked"):
                row.update(saveable=None, why_not=check.get("why_not"))
            else:
                fields = [{k: f.get(k) for k in ("id", "label", "kind", "required")}
                          for f in check["fields"]]
                row.update(saveable=check["saveable"], why=check["why"],
                           fields=fields[:FIELDS_MAX],
                           **({"fields_not_listed": len(fields) - FIELDS_MAX}
                              if len(fields) > FIELDS_MAX else {}))
            rows.append(row)
        return {"checked": True, "blocks": rows}

    def _form_hits(self, tid, e, needle, conv) -> list[dict]:
        """`find`'s hits in one Turn's fillable blocks: a block whose title
        matches, and each field whose label does -- in a block that cannot be
        saved too (no usable or a repeated name=), marked `saveable: False`
        with why, so it is found though nothing can be answered in it."""
        parts = (e.get("body") or {}).get("parts") or []
        got = self._fill_blocks(tid, parts)
        out = []
        where = {"ref": tid, "conversation": conv["id"],
                 "conversation_name": conv["body"]["name"],
                 "number": self.cv.turn_number(tid)}
        for b in got.get("blocks") or ():
            base = {"what": "block", **where, "type": b["type"],
                    "block": b["block"], "part": b["part"], "title": b["title"],
                    **({"saveable": False, "why": b.get("why")}
                       if b.get("saveable") is False else {})}
            if needle in (b.get("title") or "").lower():
                out.append({**base, "matched": "title"})
            for f in b.get("fields") or ():
                if needle in (f.get("label") or "").lower():
                    out.append({**base, "matched": "field", "field": f["id"],
                                "label": f["label"]})
        return out

    def _fillable(self, ref, e) -> dict | None:
        """What `resolve` says of a post's fillable blocks and response sets:
        None for a post with neither, so an ordinary Turn reads as before."""
        from mentis.conversation import responses
        try:
            root = responses.post_root(self.corpus, ref)
            sets = responses.sets_on(self.cv, root)
        except Exception:                                # noqa: BLE001
            return None
        parts = (e.get("body") or {}).get("parts") or []
        texts = [p.get("text") or "" for p in parts
                 if isinstance(p, dict) and p.get("type") == "text"]
        fenced = any(_FILL_FENCE.search(t) for t in texts)
        if not sets and (e.get("deleted") or not fenced):
            return None

        def brief(s):
            b = s["body"]
            return {"set": s["id"], "part": b.get("part"), "block": b.get("block"),
                    "mode": b.get("mode"), "holder": b.get("holder"),
                    "answers": len(responses.answers_in(self.cv, s["id"]))}

        out: dict[str, Any] = {}
        if e.get("deleted"):
            out.update(source_deleted=True, blocks=[],
                       note="the post was deleted: its response sets are kept "
                            "as history and accept no new answers")
        else:
            got = self._fill_blocks(root, parts) if fenced else \
                {"checked": True, "blocks": []}
            out.update(got)
        placed = set()
        for row in out.get("blocks") or ():
            mine = [brief(s) for s in sets
                    if (s["body"].get("part"), s["body"].get("block"))
                    == (row["part"], row["block"]) and row["block"]]
            row["sets"] = mine
            placed.update(x["set"] for x in mine)
        rest = [brief(s) for s in sets if s["id"] not in placed]
        if rest:
            out["sets_without_block"] = rest
        out.setdefault("note", "resolve a response set (ent-...) for each "
                               "field's value, who set it and when; answer "
                               "a field with `answer`")
        return out

    def _response_set(self, sid) -> dict:
        """`resolve` on a response set: every field as it stands, computed.

        THE CURSOR AND THE VALUES ARE ONE READ. Taken as one computation
        between two equal `steady` readings (`Corpus.settled`), so the cursor
        is the last entry the values were read from; if a write lands while it
        runs it is read again. And the cursor is read FIRST, so even the
        fallback can only repeat in `history since=` an answer the values
        already show, never skip one they do not."""
        def at_once():
            return self._response_set_view(sid, self._set_members(sid))
        return self.corpus.settled(at_once, at_once)

    def _response_set_view(self, sid, members) -> dict:
        from mentis.conversation import render_check, responses
        st = responses.state(self.cv, sid)
        declared = []
        if not st.get("source_deleted") and st.get("checked"):
            ver = responses.current_version(self.corpus, st["post"])
            text = responses.part_text(ver, st.get("part") or 0)
            got = render_check.answers(text or "", st["block"], {})
            declared = got.get("fields") or [] if got.get("checked") else []
        missing = set(st.get("missing") or ())
        not_asked = set(st.get("not_asked") or ())
        problems: dict[str, list] = {}
        for p in st.get("problems") or ():
            problems.setdefault(p.get("field"), []).append(p.get("msg"))

        def head(r):
            return {"answer": r["answer"], "value": r["value"], "by": r["by"],
                    "by_alias": r["by_alias"], "at": r["at"],
                    "when": _when(r["at"]), "version": r["version"],
                    "earlier_version": r.get("earlier_version"),
                    "note": r.get("note")}

        def row(fid, info):
            h = st["fields"].get(fid)
            out = {"field": fid, **info, "answered": h is not None,
                   "conflict": bool(h and h["conflict"])}
            if h and not h["conflict"]:
                out.update(head(h["heads"][0]))
            elif h:
                out.update(value=None, answer=None,
                           heads=[head(r) for r in h["heads"]])
            else:
                out.update(value=None, answer=None)
            if fid in missing:
                out["missing"] = True
            if fid in not_asked:
                out["not_asked"] = True
            if problems.get(fid):
                out["problems"] = problems[fid]
            return out

        fields = [row(f["id"], {"label": f.get("label"), "kind": f.get("kind"),
                                "required": f.get("required")})
                  for f in declared]
        seen = {f["id"] for f in declared}
        fields += [row(fid, {"declared": False} if declared or st.get("checked")
                       else {})
                   for fid in st["fields"] if fid not in seen]
        keep ={k: st.get(k) for k in (
            "set", "post", "part", "block", "type", "mode", "holder", "version",
            "conflicts", "answers", "ready", "changed_since_ready",
            "marked_ready", "valid", "missing", "problems", "checked", "why_not",
            "source_deleted", "pending")}
        # F1: THE PEOPLE'S OWN WORDS, exactly as written, each version that
        # now reads; EVERY INTERPRETATION of them with its state; and, per
        # wording, which passages were interpreted and which not yet.
        words = [{**w, "when": _when(w["at"]),
                  "length": len(w["text"])} for w in st.get("own_words") or ()]
        proposals = [{**p, "when": _when(p["at"])}
                     for p in st.get("proposals") or ()]
        acc = responses.accounting(self.cv, sid)["words"]
        accounted = [{"words": a["words"], "by": a["by"],
                      "passages": [{"interpretation": v["interpretation"],
                                    "passage": v["passage"],
                                    "excerpt": v["excerpt"],
                                    "state": v["state"]}
                                   for v in a["passages"]],
                      "not_cited": a["not_cited"],
                      "on_earlier_wording": [
                          {"interpretation": v["interpretation"],
                           "words": v["words"], "state": v["state"]}
                          for v in a["on_earlier_wording"]]}
                     for a in acc]
        return {"what": "a response set", **keep,
                "conversation": self.cv.conversation_of(st["post"]),
                "own_words": words, "proposals": proposals,
                "accounting": accounted,
                "fields": fields,
                "cursor": members[-1]["id"] if members else sid,
                "note": "computed from the answers now; nothing here is a "
                        "stored status. `version` is the post's current "
                        "version; an answer with earlier_version true was "
                        "given against an earlier one. To answer, call "
                        "`answer` naming the answer you read in `replaces`. "
                        "`own_words` are people's own words, exactly as "
                        "written; `proposals` are interpretations of them "
                        "with their state (pending, confirmed, changed, "
                        "declined, out of date), and `accounting` says, per "
                        "wording, which passages were interpreted and which "
                        "(`not_cited`) not yet: account for every point. "
                        "Later, `history set=<this> since=<cursor>` says what "
                        "changed"}

    def _set_members(self, sid) -> list[dict]:
        """Everything written into a response set, oldest first: answers,
        marked-ready and whatever else joins it."""
        from mentis.conversation import responses
        ids = [x["link"]["from"]
               for x in self.corpus.links(relation=responses.IN_RESPONSE_SET, to=sid)]
        order = {eid: i for i, eid in enumerate(ids)}
        return sorted(self.corpus.read(ids),
                      key=lambda e: (e["recorded_at"], order.get(e["id"], 0)))

    def _decision_forms(self, ref) -> list[dict]:
        """The decision forms on a post (P7) -- asked `on` it or attached to
        it as a run's answer post -- each as the record holds it, with the
        cursor `history set=<form>` reads on from."""
        from mentis.conversation import responses
        try:
            root = responses.post_root(self.corpus, ref)
        except Exception:                                # noqa: BLE001
            return []
        out = []
        for form in self.cv.decision_forms_on(root):
            got = self.cv.decision_form(form)
            if got is None:
                continue
            changes = self._form_members(got)
            out.append({**got, "cursor": changes[-1]["entry"] if changes
                        else form,
                        "note": "a decision form: each question is answered "
                                "by the owner's reply naming it. `history "
                                "set=<form> since=<cursor>` says what was "
                                "answered or withdrawn since"})
        return out

    @staticmethod
    def _form_members(form) -> list[dict]:
        """What became of a decision form's questions, oldest first: each
        answer and each withdrawal, by the act that recorded it."""
        rows = []
        for q in form["questions"]:
            base = {"expectation": q["expectation"], "index": q["index"],
                    "question": q["question"]}
            if q.get("answer"):
                a = q["answer"]
                rows.append({"entry": a["act"], "kind": "decision-answered",
                             "at": a["at"], **base,
                             **{k: a.get(k) for k in ("reply", "option",
                                                      "label", "words")
                                if k in a}})
            if q.get("withdrawn"):
                w = q["withdrawn"]
                rows.append({"entry": w["act"], "kind": "decision-withdrawn",
                             "at": w["at"], "by": w.get("by"), **base,
                             "because": w.get("because"),
                             "reply": w.get("reply")})
        order = {r["entry"]: i for i, r in enumerate(rows)}
        return sorted(rows, key=lambda r: (r["at"] or "", order[r["entry"]]))

    def form_changes(self, form: dict, since: str | None = None,
                     limit: int = PAGE) -> dict:
        """`history set=<decision form> since=`: what its questions came
        to after `since`, oldest first, paged and marked as for a set."""
        fid = form["form"]
        members = self._form_members(form)
        ids = [m["entry"] for m in members]
        since = (since or "").strip() or None
        if since in (None, fid):
            start = 0
        elif since in ids:
            start = ids.index(since) + 1
        else:
            return {"refused": True, "set": fid, "since": since,
                    "why_not": f"{since!r} is not an answer or withdrawal of "
                               "this decision form: pass the `cursor` an "
                               "earlier read returned, or the form itself to "
                               "read from the start"}
        limit = max(1, min(int(limit or PAGE), SINCE_MAX))
        rest = members[start:]
        page = rest[:limit]
        rows = [{**m, "when": _when(m["at"])} for m in page]
        more = len(rest) > len(page)
        return {"set": fid, "decision_form": True, "since": since,
                "changes": rows,
                "cursor": page[-1]["entry"] if page else (since or fid),
                "more": more, "not_returned": len(rest) - len(page),
                "open": form["open"], "closed": form["closed"],
                "note": ("more changes follow: ask again with since=<cursor>"
                         if more else "nothing after cursor yet; keep it and "
                                      "ask again with since=<cursor>")}

    def set_changes(self, sid: str, since: str | None = None,
                    limit: int = PAGE) -> dict:
        """What was written into a response set after `since`, oldest first.
        A decision form (P7) is read the same way (`form_changes`).

        THE MARKER IS AN ENTRY OF THE SET, never a time: the `cursor` the
        last answer gave (or the set itself, to read from the start). Entries
        are immutable, so a marker means the same thing every time it is
        asked. One page at a time, oldest first, so a reader that fell behind
        catches up in order: `more` says there is more after `cursor`."""
        from mentis.conversation import responses
        from mentis.conversation.versions import Refused
        try:
            responses._set(self.corpus, sid)
        except Refused as exc:
            try:
                form = self.cv.decision_form(sid)
            except Exception:                            # noqa: BLE001
                form = None
            if form is not None:
                return self.form_changes(form, since, limit)
            return {"refused": True, "why_not": exc.refusal.get("error"),
                    "set": sid}
        members = self._set_members(sid)
        ids = [m["id"] for m in members]
        since = (since or "").strip() or None
        if since in (None, sid):
            start = 0
        elif since in ids:
            start = ids.index(since) + 1
        else:
            return {"refused": True, "set": sid, "since": since,
                    "why_not": f"{since!r} is not an entry of this response "
                               "set: pass the `cursor` an earlier read "
                               "returned, or the set itself to read from the "
                               "start"}
        limit = max(1, min(int(limit or PAGE), SINCE_MAX))
        rest = members[start:]
        page = rest[:limit]
        rows = []
        replies = None
        for m in page:
            b = dict(m.get("body") or {})
            b.pop("set", None)
            kind = self._kind_of(m)
            if kind == responses.INTERPRETATION:
                # the passage it quotes, read from the words, and what has
                # become of it NOW (a later reply is a later change too)
                if replies is None:
                    replies = responses.replies_in(self.cv, sid)
                v = responses.interpretation_view(self.cv, m, None, replies)
                b.update(excerpt=v["excerpt"], status_now=v["status"])
            rows.append({"entry": m["id"], "kind": kind,
                         "by": m.get("attributed_to"),
                         "by_alias": self.cv.alias(m.get("attributed_to")),
                         "at": m["recorded_at"], "when": _when(m["recorded_at"]),
                         **b})
        more = len(rest) > len(page)
        return {"set": sid, "since": since, "changes": rows,
                "cursor": page[-1]["id"] if page else (since or sid),
                "more": more, "not_returned": len(rest) - len(page),
                "note": ("more changes follow: ask again with since=<cursor>"
                         if more else "nothing after cursor yet; keep it and "
                                      "ask again with since=<cursor>")}

    def history(self, *, conversation: str | None = None, turn: str | None = None,
                participant: str | None = None, limit: int = PAGE) -> dict:
        """Operational acts, as recorded. Who did what, where, and with what.

        THE ONLY PLACE RUNTIME AND MODEL COME FROM. An act records the runtime
        it ran on and, where the run reported one, the model actually used --
        observed, not requested. A question like "which model produced this"
        is answered from here or not at all.
        """
        kw: dict[str, Any] = {"newest_first": True}
        if conversation:
            kw["conversation"] = conversation
        if turn:
            kw["turn"] = turn
        acts = self.cv.history(**kw)
        if participant:
            acts = [a for a in acts if a.get("actor") == participant]
        rows = []
        gone: dict[str, dict | None] = {}
        for a in acts[:limit]:
            rows.append({
                "id": a.get("id"),
                "act": a.get("act"),
                "at": a.get("at"),
                "actor": a.get("actor"),
                "actor_alias": self.cv.alias(a["actor"]) if a.get("actor") else None,
                "conversation": a.get("conversation"),
                "turn": a.get("turn"),
                "execution": a.get("execution"),
                "runtime": a.get("runtime"),
                "because": a.get("because"),
                # WHY THIS FOLLOWED FROM THAT, and the act's own id to follow it
                # BY. Both were dropped here, and the omission was found in real
                # use: a Caretaker asked to say what was in force reported that
                # it could not confirm its own start act was tied to the request,
                # because `history` showed no cause -- "the two are joined only
                # by sharing a Turn". The record held the link the whole time;
                # this read simply did not pass it on, which made a worker report
                # an honest unknown about something that is known.
                "caused_by": a.get("caused_by"),
                "about": a.get("about"),
                "detail": a.get("detail"),
            })
            # AN ACT ABOUT AN ARTIFACT A DELETED TURN CARRIED shows its name
            # and digest in `detail`, so the row is marked as the artifact's
            # own `resolve` is. Turn text is never in an act.
            for r in a.get("about") or ():
                if isinstance(r, str) and r.startswith("adm-"):
                    if r not in gone:
                        gone[r] = _deleted_marking(self, r)
                    if gone[r]:
                        rows[-1].update(gone[r], deleted_material=r)
                        break
        return {"acts": rows, "matched": len(acts),
                "not_returned": max(0, len(acts) - len(rows))}

    def find(self, q: str, limit: int = PAGE, *, here: str | None = None) -> dict:
        """Locate things by identity, by coordinate, or by name. Identities out.

        THREE GRAMMARS, AND THE ORDER MATTERS. `#120` was searching PROSE for
        the characters "120", which is not what anybody means by it: Turn #120
        of this Conversation existed, its text contained no "120", and so the
        only hit was a Participant who happened to be called `@EsmePike120`.
        The picker filtered that out, found nothing, and offered to create a
        Topic called "120". Text search was standing in for a lookup by
        coordinate, and it is not a substitute for one.

          IDENTITY    `ent-...` -- the reference itself. Exact by construction.
          COORDINATE  a bare number -- the Turn a person can SEE in the margin.
                      Not globally unique, which is why scope decides.
          TEXT        everything else, as before.

        SCOPE DECIDES A COORDINATE, AND NEVER GUESSES. Inside a Conversation,
        `#120` is that Conversation's 120th Turn. At Brain scope the number
        names one Turn in every Conversation long enough to have one, so all
        of them are returned and `ambiguous` says so. Picking the first would
        be inventing an answer to a question the person has not finished
        asking.

        EXACT HITS COME FIRST AND SAY THEY ARE EXACT, so a caller can tell a
        reference that IS the thing from one that merely mentions it -- and so
        that offering to create a Topic can never be the primary reading of an
        input that already names something.
        """
        raw = (q or "").strip()
        needle = raw.lower().lstrip("@#")
        if not needle:
            return {"found": [], "matched": 0, "why_not": "nothing to search for"}

        exact: list[dict] = []
        found: list[dict] = []

        # -- identity ------------------------------------------------------
        if ENTRY_REF.match(needle):
            got = self.resolve(needle)
            if got.get("known"):
                exact.append({"what": got.get("kind") or "entry", "ref": needle,
                              "exact": "identity",
                              "name": got.get("name") or got.get("alias"),
                              "number": got.get("number"),
                              "conversation": got.get("conversation"),
                              "said": got.get("said")})
                if got.get("what") == "a held artifact" and got.get("deleted"):
                    exact[-1].update(deleted=got["deleted"], note=got["note"])

        # -- coordinate ----------------------------------------------------
        if needle.isdigit():
            n = int(needle)
            # Inside a Conversation the local Turn is the answer. Elsewhere
            # every Conversation that has one is an answer, and the caller is
            # told the question was ambiguous rather than answered.
            scope = [here] if here else [c["id"] for c in self.cv.all_conversations()]
            for cid in scope:
                tid = self.cv.turn_at(cid, n)
                if not tid:
                    continue
                e = self._entry(tid)
                exact.append({
                    "what": "turn", "ref": tid, "exact": "coordinate",
                    "conversation": cid,
                    "conversation_name": self._conversation_name(cid),
                    "number": n,
                    "said": self._turn_line(e)[:160] if e else "",
                })

        # -- text ----------------------------------------------------------
        seen = {row["ref"] for row in exact}
        for p in self.cv.all_participants():
            if needle in p["body"]["alias"].lower():
                found.append({"what": "participant", "ref": p["id"],
                              "name": p["body"]["alias"]})
        for c in self.cv.all_conversations():
            if needle in c["body"]["name"].lower():
                found.append({"what": "conversation", "ref": c["id"],
                              "name": c["body"]["name"]})
            for t in self.cv.topics(c["id"]):
                if needle in t["body"]["name"].lower():
                    found.append({"what": "topic", "ref": t["id"],
                                  "name": t["body"]["name"],
                                  "conversation": c["id"]})
        # LINKS OF A NAMED RELATION, which is how you ask "how many of these
        # are there". Found in real use: a Caretaker asked what was in force
        # searched for `carries-intake`, got nothing back, and had to report
        # that it could not confirm the designation was the only one. Every
        # Link of that Relation was sitting in the record; searching only
        # Participants, Conversations, Topics and prose could never reach one,
        # because a Link has no name -- its relation IS its name.
        for e in self.corpus.links(relation=needle) if "-" in needle else ():
            st = self.corpus.stands(e["id"])
            found.append({"what": "link", "ref": e["id"],
                          "relation": e["link"]["relation"],
                          "links_from": e["link"]["from"],
                          "links_to": e["link"]["to"],
                          "stands": st["stands"],
                          "name": f"{e['link']['relation']}: "
                                  f"{self.cv.alias(e['link']['from'])}"})

        # Turns last: there are the most of them and they are the least
        # likely thing somebody means by a bare word. A Turn holding a
        # fillable block whose TITLE or a FIELD'S LABEL matches is also a
        # `block` hit, offered before every other text hit: it names the
        # block and field to `answer`, which the Turn hit cannot.
        forms: list[dict] = []
        for c in self.cv.all_conversations():
            for row in self.cv.contributions(c["id"]):
                if row["id"] in seen:
                    continue          # already returned as an exact hit
                e = self._entry(row["id"])
                if e is None:
                    continue
                said = self._turn_line(e)
                if needle in said.lower() and _FILL_FENCE.search(said):
                    forms.extend(self._form_hits(row["id"], e, needle, c))
                if needle in said.lower():
                    found.append({"what": "turn", "ref": row["id"],
                                  "conversation": c["id"],
                                  # WHICH ROOM IT IS IN. The coordinate grammar
                                  # has always said this; a text hit did not,
                                  # so a list of Turns from six Conversations
                                  # read as six Turns from nowhere.
                                  "conversation_name": c["body"]["name"],
                                  "number": self.cv.turn_number(row["id"]),
                                  "said": said[:160]})
                if len(found) >= limit * 3:
                    break

        # `here` does not filter. A reference to something in another
        # Conversation is a legitimate thing to want -- comparing this with
        # that is most of why references exist -- so it only decides what is
        # offered FIRST.
        found.sort(key=lambda row: 0 if here and row.get("conversation") == here else 1)

        # ACQUIRED MATERIAL, BY NAME AND LABEL ONLY (owner decision 4, B6).
        # The latest PRESENT observation of each object whose key or label
        # contains the needle; the hit's `ref` is that observation's `adm-`,
        # which is what a Turn then cites and pins. No bytes are read for
        # these and no index exists; content is searched separately, below,
        # since Sources A reversed decision 4 for scanning only.
        #
        # RANKED AFTER EVERY RECORD HIT, TURNS INCLUDED. Placed before the
        # Turns, a folder of 1,078 files whose names share an ordinary word
        # ("combat", "spell", "md") filled the whole page and hid the Turn
        # that said it: 15 `combat-NN.md` beside one Turn about combat, and
        # `find("combat", 12)` returned 12 files and no Turn. A file is the
        # most numerous and least likely thing a bare word means. Every
        # match is still counted, so `matched` and `not_returned` say how
        # many were left off the page.
        acquired = self._acquired_hits(needle)
        # ACQUIRED CONTENT, AFTER THE NAMES (Sources A, A2): where the phrase
        # occurs INSIDE acquired text, one hit per file, each `matched:
        # "content"`, appended after every name hit and so after every
        # record hit -- Turns always survive, by the ruling above. A file
        # already found by its name is not offered twice. Counted in
        # `matched` like every other hit.
        named = {row["ref"] for row in acquired}
        hits, not_searched = self._content_hits(raw.lstrip("@#"))
        content = [row for row in hits if row["ref"] not in named]
        forms.sort(key=lambda row: 0 if here and row.get("conversation") == here else 1)
        rows = exact + forms + found + acquired + content
        return {
            "found": rows[:limit],
            "matched": len(rows),
            "exact": len(exact),
            # True only where a coordinate named more than one Turn and
            # nothing narrowed it. The caller is expected to say so.
            "ambiguous": len(exact) > 1,
            "not_returned": max(0, len(rows) - limit),
            # WHAT THE CONTENT SCAN DID NOT READ, AND WHAT IS STILL BEING MADE
            # (Sources C, C-1; acceptance finding A1, adm-7a520bf68f2c). The
            # scan never waits for an extraction, so a PDF whose text is being
            # made in the background was simply absent from `found`, and
            # nothing said so: the picker and an agent read a silent answer
            # as everything there is. This is the scan's own `not_searched`,
            # exactly as `search_sources` gives it, over the same files the
            # content hits came from -- the whole held record, never the page
            # -- and `pending` is its extraction_pending, said on its own.
            # Asked again once it is made, the file is searched and pending
            # is empty: nothing is remembered between asks.
            "not_searched": not_searched,
            "pending": _pending(not_searched),
        }

    # -- acquired sources (Bulk Source) -----------------------------------

    def _acquired_hits(self, needle: str) -> list[dict]:
        from mentis.sources import declarations, latest, observation, source_id
        from mentis.sources import registry
        out = []
        for d in declarations(self.corpus):
            try:
                desc = registry.descriptor(d["connector"])
            except Exception:                            # noqa: BLE001
                continue
            src = source_id(d["connector"], d["collection"])
            for key, e in sorted(latest(self.corpus, src).items()):
                o = observation(e)
                if o.get("state") != "present":
                    continue
                label = registry.label(d["connector"], key, o)
                if needle in key.lower() or needle in label.lower():
                    out.append({"what": "acquired", "ref": e["id"],
                                "name": label, "key": key,
                                "collection": d["collection"],
                                "collection_name": d["name"],
                                "connector": d["connector"],
                                "connector_label": desc.label,
                                "admitted_at": e["body"].get("admitted_at"),
                                "matched": "name"})
        return out

    def _content_hits(self, q: str) -> tuple[list[dict], dict | None]:
        """One content hit per file, and the scan's `not_searched` (None
        where no scan ran)."""
        from mentis.sources import Refused, search
        try:
            got = search.first_in_each(self.corpus, q)
        except Refused:
            return [], None
        return [{"what": "acquired", "ref": h["ref"], "name": h["label"],
                 "key": h["key"], "collection": h["collection"],
                 "collection_name": h["collection_name"],
                 "matched": "content", "snippet": h["snippet"],
                 "line": h["line"], "offset": h["offset"], "end": h["end"],
                 "unit": h["unit"], "extraction": h["extraction"],
                 "display": h.get("display"),
                 "excerpt": h["excerpt"], "cite": h["cite"],
                 "matches_in_file": h["match"]["of"]}
                for h in got["hits"]], got["not_searched"]

    def sources(self, *, collection: str | None = None, q: str | None = None,
                state: str | None = "present", offset: int = 0,
                limit: int | None = None, prefix: str | None = None) -> dict:
        """Acquired collections, or the objects of one, as recorded."""
        from mentis.sources import reading
        if not collection:
            return reading.collections(self.corpus)
        return reading.objects(self.corpus, collection, q=q, state=state,
                               offset=offset, limit=limit or reading.LIST,
                               prefix=prefix)

    def source_history(self, collection: str, path: str) -> dict:
        from mentis.sources import reading
        return reading.history(self.corpus, collection, path)

    def source_links(self, collection: str, path: str, *, ref: str | None = None) -> dict:
        from mentis.sources import reading
        return reading.links(self.corpus, collection, path, ref=ref)

    def read_source(self, *, ref: str | None = None,
                    collection: str | None = None, path: str | None = None,
                    offset: int = 0, length: int | None = None,
                    extraction: str | None = None) -> dict:
        from mentis.sources import reading
        return reading.read(self.corpus, ref=ref, collection=collection,
                            path=path, offset=offset,
                            length=length or reading.PAGE_BYTES,
                            extraction=extraction)

    def search_sources(self, q: str, *, collection: str | None = None,
                       offset: int = 0, limit: int | None = None,
                       continuation: str | None = None) -> dict:
        from mentis.sources import search
        return search.search(self.corpus, q, collection=collection,
                             offset=offset, limit=limit or search.LIMIT,
                             continuation=continuation)

    # -- what governs, what was decided, what may be required -------------

    def governed(self, *, kind: str | None = None, q: str | None = None,
                 state: str | None = None, limit=None) -> dict:
        """The governed-material register, as `/api/governed` serves it to
        the owner's UI (`register.governed`): one read, two callers, so an
        agent and the UI cannot disagree. Each group is bounded by `limit`,
        PAGE when none is given, and `omitted` says what was left out."""
        from mentis.conversation.register import governed
        return governed(self.brain, kind=kind, q=q, state=state,
                        limit=PAGE if limit in (None, "") else limit)

    def _conversation_or_refusal(self, name: str, conversation) -> dict | None:
        if not isinstance(conversation, str) or not conversation.strip():
            return {"refused": True, "asked": name,
                    "why_not": f"{name} needs `conversation`, a Conversation's "
                               f"ent-... id (`orient` lists them)"}
        if not self.cv._is_kind(conversation.strip(), "conversation"):
            return {"refused": True, "asked": name,
                    "why_not": f"{conversation!r} is not a Conversation in "
                               f"this record"}
        return None

    def owner_decisions(self, conversation, most=None) -> dict:
        """The decision questions asked in a Conversation, answered and still
        open, newest first (`Conversations.owner_decisions`) -- what a
        dispatch brief names, so the owner is not asked twice. `most` bounds
        each list, at most PAGE; the counts are of all of them."""
        refused = self._conversation_or_refusal("owner_decisions",
                                                conversation)
        if refused:
            return refused
        if most in (None, ""):
            n = None
        else:
            try:
                n = int(most)
            except (TypeError, ValueError):
                return {"refused": True, "asked": "owner_decisions",
                        "why_not": f"`most` is a whole number, not {most!r}"}
            if n < 1:
                return {"refused": True, "asked": "owner_decisions",
                        "why_not": f"`most` is at least 1, not {n}"}
        return {"conversation": conversation.strip(),
                **self.cv.owner_decisions(
                    conversation.strip(),
                    most=None if n is None else min(n, PAGE))}

    def capabilities(self) -> dict:
        """The names a `requires` may use (`api.capability_names`), sorted.

        NAMES ONLY. `types.Capability` explains its members in source
        comments, which nothing can read at run time; a meaning restated
        here would be a second account free to drift from the first."""
        names = sorted(api.capability_names())
        return {"capabilities": names, "count": len(names),
                "note": ("what a runtime can declare and work can require "
                         "(`requires` on delegate). A requirement naming "
                         "anything else is refused.")}

    def brief(self, conversation, participant: str | None, *, persona=None,
              workflow=None, work=None, expectation=None, follow_up=None,
              scope: str | None = None, detail: bool = False) -> dict:
        """The navigation brief a dispatched run receives for a Conversation
        (`Conversations.orientation`, as `compose` asks it), composed for the
        CALLING Participant -- the one the door's grant names (`_result`),
        never a tool argument: a caller that could name it could read the
        brief composed for anybody. What it may also be asked to carry --
        the Persona worn, the Workflow named -- is `compose_brief`'s.

        AND THE PREPARED ORIENTATION BESIDE IT (docs/operating-model.md §5):
        the Conversation's shared foundation -- the same object for every
        caller with this read scope, computed once and kept while nothing it
        read has moved -- and this caller's own part, with `rendered` putting
        the stable shared text first. `expectation` names the request being
        worked; its recorded Persona and Workflow are used when none is named
        here, and its Task Gravity is the one in force."""
        from mentis.core.context_cache import cache_for, revisions_for
        from mentis.core.orientation import (blocks, for_agent, foundation,
                                             identifiers)
        if expectation and (persona in (None, "") or workflow in (None, "")):
            detail_of = (self.cv._act(str(expectation).strip()) or {}).get("detail") or {}
            persona = persona or detail_of.get("persona")
            workflow = workflow or detail_of.get("workflow")
        effective_scope = scope or getattr(self, "read_scope", "brain")
        cid = str(conversation or "").strip()
        work = str(work or "").strip() or None
        # WHO AND WHAT FIRST, refused before anything is composed: the same
        # Conversation, Participant, Persona and Workflow questions the
        # detailed brief asks.
        refused = self._conversation_or_refusal("brief", conversation)
        if refused:
            return refused
        if not participant:
            return {"refused": True, "asked": "brief",
                    "why_not": "this caller's grant names no Participant, so "
                               "there is nobody to compose the brief for "
                               "(what is owed to you depends on who you are)"}
        wearing = named = None
        if persona not in (None, ""):
            wearing = standing_material(self, persona, PERSONA_KIND, by_name=True)
            if wearing.get("refused"):
                return {"refused": True, "asked": "brief", **wearing}
        if workflow not in (None, ""):
            named = standing_material(self, workflow, WORKFLOW_KIND)
            if named.get("refused"):
                return {"refused": True, "asked": "brief", **named}
        shared, meta = foundation(self.brain, cid, scope=effective_scope,
                                  with_meta=True)
        mine = for_agent(self.brain, shared, participant=participant,
                         persona=(wearing or {}).get("entry"),
                         workflow=(named or {}).get("entry"),
                         work=work, follow_up=follow_up,
                         expectation=str(expectation).strip() if expectation else None)
        parts = blocks(shared, mine)
        rendered = "\n\n---\n\n".join(b["text"] for b in parts)
        if not detail:
            # THE COMPACT FORM, THE DEFAULT: the three blocks as a run reads
            # them, and the identifiers to act on. Everything in it is also in
            # the detailed form; nothing here is a summary of anything.
            return {"for": participant, "for_alias": self.cv.alias(participant),
                    "conversation": cid, "name": shared.get("name"),
                    **({"persona": wearing, "persona_note": PERSONA_NOTE}
                       if wearing else {}),
                    **({"workflow": named} if named else {}),
                    "task_gravity": mine.get("task_gravity"),
                    # THE TEXT ONCE: `rendered` is the three blocks in order,
                    # and each block says its tier, digest and length, which
                    # is what a client keeping a stable prefix compares.
                    "prepared": {"blocks": [{"tier": b["tier"],
                                             "digest": b["digest"],
                                             "chars": len(b["text"])}
                                            for b in parts],
                                 "rendered": rendered,
                                 "ids": identifiers(shared, mine)},
                    "detail": "compact; pass detail=true for the structured "
                              "brief and orientation",
                    "cache": meta}
        deps = frozenset({"governance", "knowledge", "work", "participants",
                          f"conversation:{cid}"})
        key = ("brief", self.corpus.corpus_id,
               revisions_for(self.corpus).token(deps), cid,
               hashlib.sha256((work or "").encode("utf-8")).hexdigest()[:16],
               persona, (effective_scope, participant, workflow))
        base, meta = cache_for(self.corpus).get(
            key, lambda: compose_brief(self, conversation, participant,
                                       persona=persona, workflow=workflow,
                                       work=work),
            deps=deps, with_meta=True)
        if base.get("refused"):
            return base
        return {**base, "prepared": {
                    "foundation": shared, "agent": mine, "blocks": parts,
                    "rendered": rendered, "ids": identifiers(shared, mine)},
                "cache": meta}


# --------------------------------------------------------------------------
# What a hand-started session is briefed with
# --------------------------------------------------------------------------

PERSONA_KIND, WORKFLOW_KIND = "persona", "workflow"

#: The Kinds `guidance` points to: material that says WHERE it applies in its
#: `about` ("When it applies") and is meant to be read in full only when it
#: does. Named, because the contract names them (docs/operating-model.md §5).
GUIDANCE_KINDS = ("workflow", "discipline")

#: SAID WHEREVER A PERSONA IS WORN THROUGH THE BRIDGE, because the words a
#: Persona carries read like a role and a role reads like a permission.
PERSONA_NOTE = (
    "This is the Persona this session acts AS: how to behave, and what it "
    "carries. It grants nothing -- no tool, permission, isolation or "
    "authority. What you may do is your grant's (`orient` says it), and a "
    "tool a Persona or Discipline names is not thereby installed or "
    "permitted.")


def standing_material(surface, ref, kind, *, by_name=False) -> dict:
    """The standing `kind` entry `ref` means, or a refusal with the reason.

    AN ID IS FOLLOWED FORWARD (`current_of`), as every pinned reference is:
    a Persona the owner has since replaced is named by its old id, and what
    governs is its standing successor -- said, never silently. A NAME is
    exact and matches standing entries only; two standing ones of that name
    are the owner's to tell apart, not this read's. Nothing that does not
    stand is delivered as if it did."""
    from mentis.conversation import current_of
    ref = str(ref or "").strip()
    if not ref:
        return {"refused": True, "why_not": f"name a {kind}"}
    got = surface.corpus.read([ref]) if ref.startswith("ent-") else []
    if got:
        if surface._kind_of(got[0]) != kind or got[0].get("link"):
            return {"refused": True,
                    "why_not": f"{ref} is {surface._kind_of(got[0])!r} "
                               f"material, not a {kind}"}
        cur = current_of(surface.corpus, ref)
        if not cur["stands"]:
            return {"refused": True,
                    "why_not": f"{ref} does not stand ({cur['why']}); "
                               f"nothing that does not stand governs work"}
        out = {"entry": cur["entry"]}
        if cur["entry"] != ref:
            out.update(named=ref, superseded_by=cur["entry"],
                       note=f"{ref} was superseded; its standing successor "
                            f"{cur['entry']} is delivered in its place")
    else:
        found = ([e["id"] for e in surface.corpus.entries_of_kind(kind)
                  if (e.get("body") or {}).get("name") == ref
                  and surface.corpus.stands(e["id"])["stands"]]
                 if by_name else [])
        if len(found) != 1:
            return {"refused": True,
                    "why_not": (f"{len(found)} standing {kind}s are named "
                                f"{ref!r} ({', '.join(found)}); name one by "
                                f"id" if found else
                                f"{ref!r} is no standing {kind} in this "
                                f"record" + (" (an id or its exact name)"
                                             if by_name else " (its id)"))}
        out = {"entry": found[0]}
    body = surface.corpus.read([out["entry"]])[0].get("body") or {}
    return {**out, "name": body.get("name") or ""}


def guidance(surface, work) -> list[dict]:
    """Standing Workflows and Disciplines whose "When it applies" meets the
    work, BY REFERENCE: id, name and about, and the words that met it. Never
    their text: one is read in full when it applies, a Workflow by naming it
    for the work (`brief(workflow=…)`), anything with `resolve`."""
    from mentis.conversation.knowledge import meets
    out = []
    for kind in GUIDANCE_KINDS:
        for e in surface.corpus.entries_of_kind(kind):
            body = e.get("body") or {}
            words = meets(work, body.get("about"))
            if words and surface.corpus.stands(e["id"])["stands"]:
                out.append({"id": e["id"], "kind": kind,
                            "name": body.get("name") or "",
                            "about": body.get("about") or "",
                            "met_by": words})
    return out


def compose_brief(surface, conversation, participant, *, persona=None,
                  workflow=None, work=None) -> dict:
    """The brief for a session in one Conversation, as the caller acts in it.

    THE SAME COMPOSITION A DISPATCHED RUN IS GIVEN (`Conversations.compose`),
    asked for the grant's Participant -- never one named here -- wearing
    `persona` (an established Persona's id or exact name) and with `workflow`
    (a Workflow's id) named for the work. What those deliver is delivered in
    full, under `governing`: the Persona's standing text, what it carries,
    and the Workflow. A Persona or Workflow that does not stand, or that the
    record does not hold, is refused with the reason rather than briefed
    around. `work`, when said, is the question the knowledge channel is asked
    and what `guidance` is matched against.

    A FUNCTION OF ITS ARGUMENTS AND THE RECORD, so a cache can hold it
    (docs/operating-model.md §4-5)."""
    from mentis.conversation import Composition, PERSONA_CARRIED_PREFIX
    refused = surface._conversation_or_refusal("brief", conversation)
    if refused:
        return refused
    if not participant:
        return {"refused": True, "asked": "brief",
                "why_not": "this caller's grant names no Participant, so "
                           "there is nobody to compose the brief for "
                           "(what is owed to you depends on who you are)"}
    wearing = named = None
    if persona not in (None, ""):
        wearing = standing_material(surface, persona, PERSONA_KIND,
                                    by_name=True)
        if wearing.get("refused"):
            return {"refused": True, "asked": "brief", **wearing}
    if workflow not in (None, ""):
        named = standing_material(surface, workflow, WORKFLOW_KIND)
        if named.get("refused"):
            return {"refused": True, "asked": "brief", **named}
    cid = conversation.strip()
    work = str(work or "").strip() or None
    out = {"for": participant, "for_alias": surface.cv.alias(participant),
           **surface.cv.orientation(cid, participant),
           "standing_governance": surface._applicable_governance(cid)}
    if work:
        out["work"] = work
        out["guidance"] = guidance(surface, work)
    if not (wearing or named):
        return out
    from mentis.core.orientation import composed
    comp = composed(surface.brain, cid, participant=participant,
                    persona=wearing["entry"] if wearing else None,
                    workflow=named["entry"] if named else None, work=work)
    delivered = [c for c in comp.components
                 if c.scope in ("invocation:persona", "invocation:named")
                 or c.scope.startswith(PERSONA_CARRIED_PREFIX)]
    out["governing"] = [{"id": c.source_id, "kind": c.source_kind,
                         "scope": c.scope, "title": c.title,
                         "why": c.why, "text": c.text}
                        for c in delivered]
    # Rendered as a run reads it, so a hand-started session is told what a
    # dispatched one is told, in the same words.
    out["delivered"] = Composition(tuple(delivered), (), ()).payload()
    out["withheld"] = [w for w in comp.withheld
                       if w.get("source_id") in (
                           (wearing or {}).get("entry"),
                           (wearing or {}).get("named"),
                           (named or {}).get("entry"),
                           (named or {}).get("named"))
                       or str(w.get("scope") or "").startswith(
                           PERSONA_CARRIED_PREFIX)]
    if wearing:
        out["persona"] = wearing
        out["persona_note"] = PERSONA_NOTE
    if named:
        out["workflow"] = named
    return out


# --------------------------------------------------------------------------
# The MCP wire. Small on purpose: initialize, list, call.
# --------------------------------------------------------------------------

TOOLS = [
    {
        "name": "orient",
        "description": (
            "Where you are: the Mark IV corpus this worker was dispatched "
            "from, its Conversations, and how much it holds. Call this first "
            "when asked anything about Mentis's own record."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "recall",
        "description": (
            "Recall what applies to a piece of work and what the Brain knows "
            "about it, through the same relevance-based composition used by "
            "GET /api/context?work=. Results are grouped as governing, adopted "
            "knowledge and relevant experience. Compact by default; set full "
            "to include full text. Superseded material is not active. "
            "`guidance` points to standing Workflows and Disciplines whose "
            "'When it applies' meets the work, by reference: read one in "
            "full when it applies. `persona` composes as somebody wearing "
            "that established Persona; it grants nothing."
        ),
        "inputSchema": {"type": "object", "properties": {
            "work": {"type": "string"},
            "conversation": {"type": "string"},
            "persona": {"type": "string",
                        "description": "an established Persona's id "
                                       "(ent-...) or exact name"},
            "limit": {"type": "integer"},
            "full": {"type": "boolean"}}, "required": ["work"]},
    },
    {
        "name": "work_overview",
        "description": (
            "Outstanding work from the same read-only projection as GET "
            "/api/work: open and in-flight work, work needing the owner, and "
            "returned or otherwise unfinished work. Optionally restrict it to "
            "one Conversation. Bounded and compact."
        ),
        "inputSchema": {"type": "object", "properties": {
            "conversation": {"type": "string"},
            "limit": {"type": "integer"}}},
    },
    {
        "name": "resolve",
        "description": (
            "What an identity IS. Give it a reference -- a Turn, Conversation, "
            "Participant or Topic id, including one carried by a structured "
            "reference inside a Turn -- and it answers what the record holds. "
            "A reference the corpus does not hold comes back known:false with "
            "a reason, which is an answer, not an error. On a post holding "
            "forms, checklists, editable tables or pads, `fillable` lists "
            "each block: its name=, whether answers to it can be saved (and "
            "why not), its fields, and its response sets. On a response set "
            "it gives every field: the current value, who set it and when, "
            "the form version it was given against, conflicts and missing "
            "required fields, and whether the set is valid, ready (Done) and "
            "changed since ready -- all computed from the answers now -- with "
            "people's own words exactly as written, every interpretation of "
            "them with its state, the passages not yet interpreted, and "
            "a `cursor` for `history set= since=`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string",
                                   "description": "an entry reference"}},
            "required": ["ref"],
        },
    },
    {
        "name": "history",
        "description": (
            "Operational acts as recorded: who did what, in which Conversation "
            "or Turn, on which runtime, under which execution. This is where "
            "the answer to 'which runtime or model actually did this work' "
            "comes from. Filter by conversation, turn or participant. With "
            "`set` (a response set, ent-...) it says instead what was written "
            "into that set after `since` -- answers, marked-ready, own words, "
            "interpretations and the replies to them -- oldest "
            "first, one page at a time: `since` is the `cursor` an earlier "
            "read returned (leave it out to read from the start), and `more` "
            "says to ask again with since=<cursor>. `set` may also be a "
            "decision form (opr-..., as `resolve` on the post that asks it "
            "lists it in `decision_forms`): then it says which of its "
            "questions were answered or withdrawn after `since`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation": {"type": "string"},
                "turn": {"type": "string"},
                "participant": {"type": "string"},
                "set": {"type": "string",
                        "description": "a response set (ent-...) or a "
                                       "decision form (opr-...)"},
                "since": {"type": "string",
                          "description": "with `set`: the cursor an earlier "
                                         "read returned"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "find",
        "description": (
            "Turn a name into a reference. Searches Participants, "
            "Conversations, Topics and what was said in Turns -- and the titles "
            "and field labels of fillable blocks (forms, checklists, editable "
            "tables, pads), as `block` hits naming the post, block and field, "
            "offered before other text hits -- then acquired "
            "source files by name, then by what they contain (one hit per "
            "file, matched: content, after every other hit). It never "
            "waits for a file's text to be extracted: `pending` counts "
            "those still being made, which were not searched, and "
            "`not_searched` everything else the content scan could not "
            "read; if any of it may matter, say so. Use this "
            "instead of searching files: the record is not on the filesystem "
            "in any form you can read, and this is the only sanctioned way in."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"q": {"type": "string"},
                           "limit": {"type": "integer"}},
            "required": ["q"],
        },
    },
    {
        "name": "kinds",
        "description": (
            "How many entries of each Kind this Brain holds, and how many are "
            "recorded, adoption requested, standing, history or unknown -- counted from the live "
            "store at the moment you ask. Each Kind comes with its fields, "
            "meaning and whether its entries can be true or false, as the "
            "store declares them; also how many Kind and Relation definitions "
            "and links there are. A figure that could not be determined is "
            "null with the reason, never 0. `orient` carries one line per "
            "Kind; ask this for the detail."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "check_rendering",
        "description": (
            "A dry run: check Markdown you are about to post with the UI's own "
            "block readers and get back every problem that would stop a "
            "marked block (checklist, chart, table, diagram, ref, panel, ...) "
            "being drawn -- block, line, severity, message and what to change. "
            "Writes nothing. A post is never refused for these; a block with "
            "an error is shown as readable source instead of being drawn. "
            "With `syntax` (a block name, or all) and no text it returns that "
            "block's full attribute rules and an example instead."
        ),
        "inputSchema": {"type": "object",
                        "properties": {"text": {"type": "string"},
                                       "syntax": {
                                           "type": "string",
                                           "description": "a block name "
                                           "(checklist, chart, ...) or all"}}},
    },
    {
        "name": "governed",
        "description": (
            "The rules, decisions, lessons, personas and workflows that "
            "govern work here, findable without knowing their ids. Use it "
            "before acting on something a rule may cover, or to find what "
            "was settled. Grouped by standing (proposed, recorded, standing, "
            "history, unknown); narrow with `kind`, `q` (words), `state` "
            "(one group) and `limit` (per group). `omitted` says what each "
            "group left out."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"kind": {"type": "string",
                                    "description": "one Kind, as `kinds` "
                                                   "names it"},
                           "q": {"type": "string"},
                           "state": {"type": "string",
                                     "description": "proposed, recorded, "
                                                    "standing, history or "
                                                    "unknown"},
                           "limit": {"type": "integer"}},
        },
    },
    {
        "name": "owner_decisions",
        "description": (
            "The decisions already put to the owner in a Conversation: the "
            "answered ones with the owner's choice, and the ones still open, "
            "newest first, with counts. Read it before asking the owner "
            "anything, so a settled question is not asked twice."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"conversation": {"type": "string",
                                            "description": "a Conversation "
                                                           "id (ent-...)"},
                           "most": {"type": "integer",
                                    "description": "how many of each to "
                                                   "list (default 5)"}},
            "required": ["conversation"],
        },
    },
    {
        "name": "capabilities",
        "description": (
            "The capability names a runtime can declare and work can "
            "require. Use it before naming `requires` when handing work on: "
            "a name not on this list is refused."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "brief",
        "description": (
            "Get your bearings in one Conversation: its name and purpose, "
            "the latest posts, what is still owed to you there, decisions "
            "the owner made or still owes, and work that stopped part-way -- "
            "the same brief a run dispatched into it is given, composed for "
            "you. Use it before joining or acting in a Conversation. Name "
            "the `persona` you act as and the `workflow` the work follows "
            "and both are delivered in full (a replaced Persona as its "
            "standing successor); `work` adds the Workflows and Disciplines "
            "that apply, by reference. A Persona grants nothing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"conversation": {"type": "string",
                                            "description": "a Conversation "
                                                           "id (ent-...)"},
                           "persona": {"type": "string",
                                       "description": "an established "
                                                      "Persona's id or "
                                                      "exact name"},
                           "workflow": {"type": "string",
                                        "description": "a standing "
                                                       "Workflow's id"},
                           "work": {"type": "string",
                                    "description": "the work, in words"},
                           "expectation": {"type": "string",
                                           "description": "the request being "
                                                          "worked; its Persona, "
                                                          "Workflow and Task "
                                                          "Gravity are used"},
                           "detail": {"type": "boolean",
                                      "description": "the structured brief and "
                                                     "orientation as well; "
                                                     "default is the compact "
                                                     "rendered blocks and ids"}},
            "required": ["conversation"],
        },
    },
    {
        "name": "sources",
        "description": (
            "Discover acquired Bulk Source material. With no collection: "
            "every declared collection, with how many objects are recorded "
            "present and absent. With a collection (its col-... id, or a name "
            "only one carries): the latest recorded observation of each "
            "object, filtered by `q` against its path, paged by offset. "
            "These are past observations held in Mentis, not the live "
            "folder; a file that was only linked to or left out by the "
            "collection's filters was never acquired and is not listed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"collection": {"type": "string"},
                           "q": {"type": "string"},
                           "state": {"type": "string",
                                     "description": "present (default), "
                                                    "absent, or empty for both"},
                           "offset": {"type": "integer"},
                           "limit": {"type": "integer"}},
        },
    },
    {
        "name": "source_history",
        "description": (
            "Every recorded observation of one acquired object, in the order "
            "recorded: when it was new, changed, reverted, recorded absent or "
            "reappeared, each with its Admission ref and digest."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"collection": {"type": "string"},
                           "path": {"type": "string"}},
            "required": ["collection", "path"],
        },
    },
    {
        "name": "source_links",
        "description": (
            "Links out of an acquired source object as authored, with how "
            "each resolved, and links into it from other acquired objects. "
            "Each target says whether it is acquired -- being linked to "
            "never makes it so. With `ref`, targets are projected at that "
            "observation's capture batch instead of the latest record."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"collection": {"type": "string"},
                           "path": {"type": "string"},
                           "ref": {"type": "string"}},
            "required": ["collection", "path"],
        },
    },
    {
        "name": "read_source",
        "description": (
            "One bounded page (at most 64 KiB) of an acquired object's exact "
            "retained bytes: by Admission ref (any observation, historical "
            "included) or by collection and path (the latest). Text comes "
            "back as text on character boundaries, anything else as base64. "
            "With `extraction` (an extractor id a search hit names), it "
            "reads that exact extraction of the file instead: offset and "
            "length in CODE POINTS of the extracted text, and `loc`/"
            "`display` say where in the source the window came from. Cite "
            "the `cite` it returns. Continue with `next_offset`. Works "
            "whether or not the folder it came from is still there."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string"},
                           "collection": {"type": "string"},
                           "path": {"type": "string"},
                           "offset": {"type": "integer"},
                           "length": {"type": "integer"},
                           "extraction": {"type": "string"}},
        },
    },
    {
        "name": "search_sources",
        "description": (
            "Search the CONTENTS of acquired files for a phrase: text "
            "files (Markdown, plain text, CSV, code) as their own bytes, "
            "and files with a configured extractor through their extracted "
            "text. Literal, case-insensitive, Unicode-normalised, no "
            "wildcards. Each hit gives the file's adm- ref, a snippet, an "
            "`excerpt` {offset, length, unit} and a `cite`; a hit in an "
            "extraction also names it (`extraction.extractor_id`) and where "
            "in the source it is (`display`, `loc`). To quote, read the "
            "excerpt with read_source(ref, offset=excerpt.offset, "
            "length=excerpt.length), adding extraction=<extractor_id> for "
            "an extraction hit, then put the quoted passage AND its cite in "
            "your answer, not just a pointer. `embeds_in_excerpt` lists images the passage embeds; "
            "open an acquired one's target_ref with read_artifact and write "
            "that adm- in your answer so it is shown. A match inside a "
            "character that folds to several (ß, ﬁ) cites that whole "
            "character. The first 3 matches of each file are hits; a "
            "file's further matches are counted in `more_in_file`, not "
            "returned -- read on from the cite with read_source. Continue "
            "through the hits with `next_offset`; `not_returned` counts "
            "what was not returned. ONE ANSWER IS ONE SLICE of at most "
            "256 MiB of text: `coverage` says how much of the scope has "
            "been examined and what remains, and `coverage.said` says it "
            "in words. Unless `coverage.complete` is true the answer is "
            "PARTIAL -- no match so far is not no match -- and "
            "`continuation` searches the next slice: pass it back with "
            "the same q and collection (`next` gives exactly the "
            "arguments for the next call). A continuation is refused if "
            "the record changed since the search began, or if it was "
            "issued by another server process or before a restart; "
            "search again from the start then. `not_searched` counts what "
            "was not "
            "searched, by type, and `not_searched.extraction` why (no "
            "extractor, extraction pending, empty, failed): if any of it "
            "may matter, say so. Reads the held record, never the "
            "folder."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"q": {"type": "string"},
                           "collection": {"type": "string"},
                           "offset": {"type": "integer"},
                           "limit": {"type": "integer"},
                           "continuation": {"type": "string"}},
            "required": ["q"],
        },
    },
]

#: The one Relation that says what work left behind -- see
#: `mentis.operational.products`, which reads production from it and nothing else.
from mentis.operational.products import PRODUCED  # noqa: E402

#: THE ALTERNATIVES A DECISION MAY CARRY, as the agent states them.
#:
#: OPTIONAL, AND ON THE SAME EXPECTATION -- not a second decision system. The
#: record already says a decision is owed by the requester; this lets the asker
#: say, as data, what the few alternatives are, so the owner can choose one
#: where they read the question instead of retyping it. They are never read out
#: of prose: an ask without them is an ask without them, and the owner can
#: always answer in their own words.
#:
#: THE WORDING IS MEASURED, NOT GUESSED. The bounded over-use trial the owner
#: asked for in Governance Production ran it against real agents: with the
#: first wording the one over-use was a menu of
#: "establish as written / with changes / reject" standing in for the owner's
#: own act on material; saying so, as below, removed it (round 2, 0/5, the same
#: as no field at all) without losing options where a real choice existed. A
#: change to this text is a change to that result and should be re-run.
DECISION_OPTIONS = {
    "type": "array",
    "description": (
        "Optional. Only for a decision whose answer is one of a few "
        "alternatives you can state; each is shown to the owner as a choice "
        "with its consequence, and the owner can always answer in their own "
        "words instead. Leave it out when the answer is a value, a "
        "description, or anything else only the owner can supply. Never use "
        "it to ask whether to establish, amend or reject material: "
        "establishing is the owner's own act on the material itself, not a "
        "decision you request."),
    "items": {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "consequence": {"type": "string",
                            "description": "what choosing this leads to"},
        },
        "required": ["label"],
    },
}


def decision_options(raw) -> list[dict] | None:
    """The alternatives exactly as the asker stated them, or None for none.

    ABSENT IS NOT EMPTY. No `options` means the ask carries none, and the
    expectation records no key at all -- so "no alternatives were offered" is
    never confused with "an empty list of alternatives was offered". An empty
    list is refused for the same reason: it would say the owner has choices and
    then give them nothing to choose.

    A command-line caller can only pass a string, so JSON text is read as the
    same list; nothing else is interpreted.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            raise NotPermitted(f"options must be a list, and this is not JSON: {exc}")
    if not isinstance(raw, list) or len(raw) < 2:
        raise NotPermitted(
            "options are the alternatives of a real choice, so there are at "
            "least two; leave them out when there is no such choice")
    out, seen = [], set()
    for o in raw:
        label = (o.get("label") if isinstance(o, dict) else None)
        if not isinstance(label, str) or not label.strip():
            raise NotPermitted("every option needs a label saying what it is")
        key = label.strip().casefold()
        if key in seen:
            raise NotPermitted(f"two options are both {label.strip()!r}")
        seen.add(key)
        item = {"label": label.strip()}
        consequence = o.get("consequence")
        if isinstance(consequence, str) and consequence.strip():
            item["consequence"] = consequence.strip()
        out.append(item)
    return out


#: The most questions one decision form carries. A bound, not a design: a
#: form the owner cannot take in at once is several forms.
DECISION_QUESTIONS_MAX = 20


def _propose_on_owner_form(cv, post, args, *, sid, block, part, owner, actor,
                           written_by, act_kw, proposes):
    """`answer` on a block in a post addressed to the owner, and `answer`
    proposing a new row or a new field anywhere: THE ONE SEAM for proposals
    (owner decision F3: on a form addressed to the owner an agent only
    proposes).

    F1: A PROPOSAL QUOTES SOMEBODY'S OWN WORDS. It is P2b's interpretation
    (`responses.interpret`): `proposes` is what it proposes -- a field's
    value, a new row or a new field -- and `words` and `passage` cite the
    passage of the own words in this set it was read from: the owner's, on a
    form addressed to them (`owner`), else anybody's but the proposer's
    (`owner` None). It is their answer only once they confirm it. Nothing is
    ever recorded as somebody's answer by anybody else, and a response set
    is never opened here: with no set there are no own words to quote.
    Refused, writing nothing, when there is nothing to quote or the call
    does not quote it."""
    from mentis.conversation import responses
    if not sid:
        mine = [s for s in responses.sets_on(cv, post)
                if (s["body"].get("part") or 0, s["body"].get("block"),
                    s["body"].get("mode"), s["body"].get("started_from"))
                == (part, block, "shared", None)]
        sid = mine[0]["id"] if mine else None
    heads = [w for w in responses.words_heads(cv, sid)
             if (w["attributed_to"] == owner if owner
                 else w["attributed_to"] != actor)] if sid else []
    whose = "the owner's" if owner else "somebody else's"
    lead = (f"the block is in a post addressed to the owner ({post}), so only "
            "the owner answers it; you may propose an answer for them to "
            "confirm, quoting the passage of their own words it comes from. "
            if owner else
            "a new row or a new field is proposed, never written into the "
            "post, and a proposal quotes the passage of somebody else's own "
            "words in the block it comes from. ")
    if not heads:
        raise NotPermitted(
            lead + ("They have written no own words" if owner else
                    "Nobody else has written own words") + " in this block "
            "yet, so there is nothing to quote and nothing was recorded. Say "
            "what you would propose in your reply instead")
    words = str(args.get("words") or "").strip()
    passage = args.get("passage")
    offered = "; ".join(f"{w['id']} ({len(w['body']['text'])} code points)"
                        for w in heads)
    if not words or not isinstance(passage, dict):
        raise NotPermitted(
            lead + "Name `words` (" + whose + " own words: " + offered + ") "
            "and `passage` {start, end, expected_excerpt}, as `resolve` on "
            "the response set shows them. Nothing was recorded")
    got = cv.corpus.read([words])
    if not got or (got[0]["attributed_to"] != owner if owner
                   else got[0]["attributed_to"] == actor):
        raise NotPermitted(
            lead + f"{words!r} is not {whose} own words in this block "
            "(" + offered + "). Nothing was recorded")
    got = responses.interpret(
        cv, sid, words=words, passage=passage, proposes=proposes,
        by=actor, written_by=written_by, op=args.get("op"), act_kw=act_kw)
    return {"ok": True, "proposed": True, **got,
            "revision": got["interpretation"],
            "note": "recorded as YOUR PROPOSAL, quoting " + whose + " words, "
                    "not as an answer: it is pending until the owner "
                    "confirms, changes or declines it, and it marks nothing "
                    "ready and wakes nobody. `resolve` the response set to "
                    "see its state"}


def _pending_form_of_run(cv, parent, execution) -> dict | None:
    """The decision form this run already asked with no `on` and that is on
    no post yet and not closed, or None: the form a later `request_decision`
    of the same run adds its questions to (`_decision_form`)."""
    from mentis.conversation import DECISION_FORM
    if not (parent and execution):
        return None
    try:
        asked = cv.corpus.operational(caused_by=parent, act=DECISION_FORM,
                                      execution=execution)
    except Exception:                                    # noqa: BLE001
        return None
    for a in reversed(asked):
        # A RUN'S PERMISSION QUESTION (`mentis/web/permissions.py`) is never
        # the form its own decisions are added to: those the work waits on.
        if a.get("turn") or (a.get("detail") or {}).get("permission"):
            continue
        got = cv.decision_form(a["id"])
        if got and got["pending"] and not got["closed"]:
            return got
    return None


def _decision_form(cv, args, *, actor, parent, here, wrote, act, where,
                   form_detail=None, execution=None):
    """`request_decision` with `questions` or `on`: ONE decision form.

    One `decision-form` act, caused by the carried request, on the post `on`
    names -- or on no post yet, when `on` is left out, until the run's
    answer post is written (`Conversations.attach_pending_forms`). Then one
    ordinary `kind="decision"` expectation of the owner per question, each
    naming the form, its index and its own words, so every question is owed,
    withdrawn and counted on its own (`DECISION_FORM`). No Turn is written:
    the questions are carried by the asking post, not posted beside it.
    All of it in one transaction, checked whole before anything is written.
    """
    from mentis.conversation import DECISION_FORM
    from mentis.conversation.versions import inert_refusal
    from mentis.conversation.owner import _owner
    if not parent:
        raise NotPermitted(
            "this execution carries no expectation, so a decision has "
            "nothing to be owed under")
    raw = args.get("questions")
    if raw is None:
        raw = [{k: args[k] for k in ("question", "because", "options")
                if args.get(k) is not None}]
    elif args.get("question") or args.get("options") is not None:
        raise NotPermitted(
            "ask either one `question` or several `questions`, not both: "
            "put every question, with its own options, in `questions`")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            raise NotPermitted(f"questions must be a list, and this is not "
                               f"JSON: {exc}")
    if not isinstance(raw, list) or not raw:
        raise NotPermitted("a decision request needs at least one question")
    if len(raw) > DECISION_QUESTIONS_MAX:
        raise NotPermitted(
            f"{len(raw)} questions is more than one form carries "
            f"({DECISION_QUESTIONS_MAX}); ask the rest separately")
    questions, seen = [], set()
    for i, q in enumerate(raw):
        words = (q.get("question") if isinstance(q, dict) else None)
        if not isinstance(words, str) or not words.strip():
            raise NotPermitted(f"question {i + 1} needs its question")
        key = words.strip().casefold()
        if key in seen:
            raise NotPermitted(f"two questions are both {words.strip()!r}")
        seen.add(key)
        try:
            options = decision_options(q.get("options"))
        except NotPermitted as exc:
            raise NotPermitted(f"question {i + 1}: {exc}")
        because = q.get("because") or args.get("because")
        questions.append({"question": words.strip(), "options": options,
                          "because": because if isinstance(because, str)
                          and because.strip() else None})
    on = str(args.get("on") or "").strip() or None
    conversation = here
    if on:
        got = cv.corpus.read([on])
        conversation = cv.conversation_of(on) if got else None
        if not got or not cv._is(got[0], "contribution") or not conversation:
            raise NotPermitted(f"{on!r} is not a post in a Conversation, so "
                               f"a decision form cannot be put on it")
        refusal = inert_refusal(cv.corpus, on)
        if refusal:
            raise NotPermitted(f"{on!r} cannot carry a decision form: "
                               f"{refusal['error']}")
        conversation = where(conversation)
    elif not here:
        raise NotPermitted(
            "this execution has no Conversation, so a decision form with no "
            "`on` has nowhere to go: name the post with `on`")
    asked_by = cv.expectation_state(parent)["requested_by"]
    owner = _owner(cv)
    of = owner or asked_by
    # ONE DECISION FORM PER RUN. A run that already asked the owner with no
    # `on`, on a form still waiting for its answer post, adds these questions
    # to THAT form rather than opening another: the owner meets one form per
    # run, however many times the run called. Nothing about who may ask or
    # who answers changes; it is the same form, expectations and act.
    folded = (None if on or form_detail
              else _pending_form_of_run(cv, parent, execution))
    if folded:
        had = {q["question"].strip().casefold() for q in folded["questions"]}
        questions = [q for q in questions
                     if q["question"].strip().casefold() not in had]
        if not questions:
            raise NotPermitted(
                f"every question here is already on this run's decision form "
                f"{folded['form']}: it is owed by the owner already")
        if len(folded["questions"]) + len(questions) > DECISION_QUESTIONS_MAX:
            raise NotPermitted(
                f"this run's decision form {folded['form']} would carry more "
                f"than {DECISION_QUESTIONS_MAX} questions; ask fewer")
        form = folded["form"]
        conversation = folded["conversation"]
        start = 1 + max((q["index"] for q in folded["questions"]), default=-1)
        with cv.corpus.atomic():
            exps = []
            for i, q in enumerate(questions, start=start):
                exps.append(cv.expect(
                    None, of=of, kind="decision", by=actor,
                    because=q["because"] or "a decision only the owner can "
                                            "make",
                    caused_by=parent, conversation=conversation,
                    detail={**({"options": q["options"]} if q["options"]
                               else {}),
                            "form": form, "index": i,
                            "question": q["question"],
                            "requester": asked_by}))
            act("decision-requested", conversation=conversation, turn=None,
                about=[*exps, form], detail={"form": form, "added": True})
        drawn = cv.decision_form(form)
        return {"ok": True, "form": form, "post": drawn["post"],
                "pending": drawn["pending"], "of": of, "requester": asked_by,
                "added_to_form": True,
                "questions": [{k: q[k] for k in ("expectation", "index",
                                                  "question", "options")}
                              for q in drawn["questions"]],
                "expectation": exps[0],
                "note": f"added to this run's decision form {form}, which "
                        "goes on your answer post when that is written: one "
                        "form per run. Each question is answered on its own"}
    with cv.corpus.atomic():
        form = act(DECISION_FORM, conversation=conversation, turn=on,
                   because=args.get("because") or "decisions only the owner "
                                                  "can make",
                   detail={"questions": len(questions), "on": on,
                           "requester": asked_by, **(form_detail or {})})
        exps = []
        for i, q in enumerate(questions):
            exps.append(cv.expect(
                on, of=of, kind="decision", by=actor,
                because=q["because"] or "a decision only the owner can make",
                caused_by=parent, conversation=conversation,
                detail={**({"options": q["options"]} if q["options"] else {}),
                        "form": form, "index": i,
                        "question": q["question"],
                        "requester": asked_by}))
        act("decision-requested", conversation=conversation, turn=on,
            about=[*exps, form], detail={"form": form})
    drawn = cv.decision_form(form)
    return {"ok": True, "form": form, "post": drawn["post"],
            "pending": drawn["pending"], "of": of, "requester": asked_by,
            "questions": [{k: q[k] for k in ("expectation", "index",
                                              "question", "options")}
                          for q in drawn["questions"]],
            # the first question's expectation, and its options, for a
            # caller that asked one
            "expectation": exps[0],
            **({"options": questions[0]["options"]}
               if len(questions) == 1 and questions[0]["options"] else {}),
            "note": ("recorded as owed BY the owner" if owner
                     else "recorded as owed BY the requester, because this "
                          "record names no owner")
            + "; one decision form"
            + (f" on post {on}" if on else
               ", on no post yet: it goes on your answer post when that is "
               "written, and until then is shown only in Needs You")
            + "; each question is answered on its own, in one of its "
              "options or the owner's own words; it is not an answer and "
              "obliges nobody to agree"}


#: THE OPERATIONS BEYOND READING. Offered to every execution, and ADMITTED
#: according to the grant -- the server refuses what this run may not do and says
#: what would have been needed. They are described here rather than filtered per
#: run because a tool list that changed shape per dispatch would make "why can I
#: not see it" unanswerable; a refusal that explains itself is better than an
#: absence. Each one takes CONTENT only: nothing here has an actor, an execution,
#: a cause or a `written_by`, because the server derives all four from the grant.
ACT_TOOLS = [
    {
        "name": "record_request",
        "description": (
            "Record the request for work begun in this hand-started session: "
            "one Turn and one open result expectation, so work_overview can "
            "carry it. Name a Conversation this session opened or an existing "
            "Conversation. This records work; it dispatches nobody."
        ),
        "inputSchema": {"type": "object", "properties": {
            "conversation": {"type": "string"},
            "text": {"type": "string"},
            "parent": {"type": "string"},
            "follow_up": {"oneOf": [
                {"type": "string", "enum": ["ask", "unrestricted"]},
                {"type": "object", "properties": {
                    "depth": {"type": "integer", "minimum": 1}},
                 "required": ["depth"], "additionalProperties": False}]},
            "persona": {"type": "string"},
            "workflow": {"type": "string"},
            "runtime": {"type": "string"},
            "requester_note": {"type": "string"},
            "repository": {"type": "string"},
            "branch": {"type": "string"}},
            "required": ["conversation", "text"]},
    },
    {
        "name": "take_up",
        "description": (
            "Take up, yourself, discovered work found under a request this "
            "hand-started session carries (`under`): the finding is assigned "
            "to this session, nothing is dispatched, and you close it later "
            "with record_outcome. Allowed only where the request's follow-up "
            "permission (Task Gravity) covers the finding's generation, or the "
            "owner chose to pursue it; otherwise it stays recorded and you "
            "return to the request you carry."
        ),
        "inputSchema": {"type": "object", "properties": {
            "expectation": {"type": "string",
                            "description": "the finding's expectation, as "
                                           "record_discovered_work returned it"},
            "under": {"type": "string",
                      "description": "the request this session carries"},
            "because": {"type": "string"}},
            "required": ["expectation", "under"]},
    },
    {
        "name": "record_outcome",
        "description": (
            "Record the outcome of a request this hand-started session "
            "recorded. Posts a reply, marks the expectation met only for a "
            "done result, and keeps each remaining item as a new open "
            "expectation. Include references and the runtimes that did the "
            "work. Record findings and lessons separately with "
            "record_material, using the returned outcome Turn as basis."
        ),
        "inputSchema": {"type": "object", "properties": {
            "expectation": {"type": "string"},
            "outcome": {"type": "string"},
            "result": {"type": "string",
                       "enum": ["done", "partial", "abandoned"]},
            "references": {"type": "array", "items": {}},
            "runtimes": {"type": "array", "items": {"type": "string"}},
            "remaining": {"type": "array", "items": {}}},
            "required": ["expectation", "outcome", "result"]},
    },
    {
        "name": "request_decision",
        # DESIGN 9D: AGENTS ASK THROUGH THE TOOL, NEVER IN PROSE. Said here,
        # where the operation is described, because a choice written as a
        # list in a reply is not owed by anybody and answers nothing.
        "description": (
            "Say that a decision belongs to the owner. Records it as something "
            "OWED BY THEM, so it appears as needing them rather than sitting "
            "in prose. You cannot choose who it goes to -- it goes to the "
            "owner, with who requested this work recorded beside it. "
            "FIRST CHECK WHETHER IT IS ALREADY SETTLED: the governing rules "
            "you were given, the owner decisions your orientation lists, and "
            "what the owner already required or decided, found with `find` "
            "and read with `resolve`. Where the answer is settled there, or "
            "the choice is reversible and within the work you were asked to "
            "do, it is yours: make it, act on it and say in your report what "
            "you chose and why. Ask only what is genuinely the owner's: "
            "something irreversible or outward-facing, spending, a change of "
            "scope, established requirements that conflict, or anything only "
            "the owner can authorise; and never a question already open for "
            "them. Ask every such choice through this tool: never write it "
            "in your reply as a list of options or a checklist to pick from. "
            "Put all of a run's decisions in ONE call with `questions`; a "
            "later call in the same run, with no `on`, adds its questions to "
            "that same form. They become "
            "one decision form on one post, and each question is answered "
            "on its own. `on` is the post (ent-...) the form belongs to; "
            "leave it out and the form goes on your answer post when that "
            "is written, and until then it is shown only in the owner's "
            "Needs You. Work that waits on the form resumes by itself, "
            "once, when its last question is answered or withdrawn."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": (
                        "Several decisions at once, each with its own "
                        "options; the owner can always answer any of them "
                        "in their own words."),
                    "items": {
                        "type": "object",
                        "properties": {"question": {"type": "string"},
                                       "because": {"type": "string"},
                                       "options": DECISION_OPTIONS},
                        "required": ["question"],
                    },
                },
                "on": {"type": "string",
                       "description": "the post (ent-...) the decision form "
                                      "belongs to; default: your answer post"},
                "question": {"type": "string",
                             "description": "one decision, the same as one "
                                            "entry in `questions`"},
                "because": {"type": "string"},
                "options": DECISION_OPTIONS},
        },
    },
    {
        "name": "request_input",
        "description": (
            "Say that the work you are carrying cannot go on until the owner "
            "has filled in a form, checklist, editable table or pad and "
            "marked it ready (Done). Name the block by the post it is in and "
            "its name=, or by its response set. It is owed BY THE OWNER, as a "
            "decision is. Mentis resumes this work by itself, once, when the "
            "owner marks it ready, and hands you the exact answers they "
            "marked; a reply in the Conversation does not count. Then end "
            "your run: say where things stand, without claiming the work met."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "post": {"type": "string",
                         "description": "the post (ent-...) the block is in"},
                "block": {"type": "string",
                          "description": "the block's name="},
                "part": {"type": "integer",
                         "description": "which text part of the post; "
                                        "default 0"},
                "set": {"type": "string",
                        "description": "or the response set (ent-...) "
                                       "instead of post and block"},
                "because": {"type": "string",
                            "description": "why this work needs it"}},
        },
    },
    {
        "name": "timer",
        "description": (
            "Read a ```timer``` block in a post, read the time spent on a "
            "Topic, Conversation or post, or start or stop a timer. Without "
            "`action` it reads the owner's timer (or `holder`'s): its runs, "
            "today and total in seconds, the box phase, and the 2-hour "
            "check-in. With `about` (an ent- id) and no post, it reads the "
            "time spent on that: one person's runs (the owner's, or "
            "`holder`'s) across every timer whose post names it in about=; "
            "read only. With `action` (start, stop, continue, box-end, "
            "break-end) it marks the OWNER's timer under your name -- and "
            "ONLY when the request this run carries is the owner's, still "
            "open, and names THIS timer exactly as ent-<post>#<name>. You do "
            "not name the request: it is this run's own, and the authority "
            "ends with this run. A bare word, or another post's timer of the "
            "same name, never counts. Never start or stop a timer on your own "
            "initiative. A stop may give `at` (ISO-8601 UTC), when the run "
            "really ended; to correct a stop, name it in `replaces`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "post": {"type": "string",
                         "description": "the post (ent-...) the timer is in"},
                "block": {"type": "string",
                          "description": "the timer's name="},
                "part": {"type": "integer",
                         "description": "which text part; default 0"},
                "action": {"type": "string",
                           "enum": ["start", "stop", "continue", "box-end",
                                    "break-end"],
                           "description": "leave out to read"},
                "about": {"type": "string",
                          "description": "reading only, without post: the "
                                         "Topic, Conversation or post "
                                         "(ent-...) to add up time spent on"},
                "at": {"type": "string",
                       "description": "a stop only: when the run ended"},
                "run": {"type": "string",
                        "description": "a stop only: the run's start mark, "
                                       "when it is not the run going now"},
                "replaces": {"type": "array", "items": {"type": "string"},
                             "description": "a stop only: the stop(s) it "
                                            "corrects"},
                "reason": {"type": "string"},
                "holder": {"type": "string",
                           "description": "reading only: whose ledger"},
                "tz": {"type": "string",
                       "description": "reading only: the IANA time zone "
                                      "for 'today', e.g. Europe/London"},
                "utc_offset": {"type": "integer",
                               "description": "reading only: minutes east "
                                              "of UTC for 'today', when no "
                                              "tz is given"},
                "op": {"type": "string",
                       "description": "a retry key: the same key is one "
                                      "occurrence"}},
            "required": [],
        },
    },
    {
        "name": "answer",
        "description": (
            "Fill in one field of a form, checklist, editable table or pad, "
            "under your own name. Name the block by its response set, or by "
            "the post it is in and its name= (its shared set is opened if "
            "none is). `field` is the field id `resolve` lists: a form "
            "field's id, a checklist item's text, `text` for a pad, a table "
            "cell's [row key, column]. `value` is true/false for a checkbox, "
            "a list of choices for a multi-choice, text for everything else. "
            "Put the answer you read as the field's current one in "
            "`replaces`; leave it out only for a field nobody has answered. "
            "Returns the field's new revision (`answer`). If somebody else "
            "changed the field after you read it, both answers are kept and "
            "you get `conflict` listing them: nothing is decided by the last "
            "save, so read the set again and answer naming both in "
            "`replaces`. A value the block's rules find wrong is kept with "
            "its `problems`. On a block in a post addressed to the owner you "
            "may not answer for them: there this records a PROPOSAL instead, "
            "pending until they confirm it, and it must quote the passage "
            "of their own words in the block it comes from -- `words` (their "
            "own-words entry) and `passage` {start, end, expected_excerpt}, "
            "as `resolve` on the response set lists them. With no own words "
            "of theirs there it is refused. Instead of a field's value you "
            "may propose a new table row (`row`, column -> text) or a new "
            "form field (`new_field` {id, kind, label?}): always a proposal, "
            "quoting the own words it comes from (the owner's on a form "
            "addressed to them, else somebody else's), never written into "
            "the post. A refusal writes nothing. Answering wakes nobody and "
            "marks nothing ready."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "set": {"type": "string",
                        "description": "the response set (ent-...)"},
                "post": {"type": "string",
                         "description": "or the post (ent-...) the block is "
                                        "in, with `block`"},
                "block": {"type": "string",
                          "description": "the block's name="},
                "part": {"type": "integer",
                         "description": "which text part of the post; "
                                        "default 0"},
                "field": {"type": "string"},
                "value": {"anyOf": [{"type": "boolean"}, {"type": "string"},
                                    {"type": "array",
                                     "items": {"type": "string"}}],
                          "description": "true/false, a list of choices, or "
                                         "text"},
                "replaces": {"type": "array", "items": {"type": "string"},
                             "description": "the answer(s) you read as the "
                                            "field's current value"},
                "note": {"type": "string",
                         "description": "optional, kept with the answer"},
                "words": {"type": "string",
                          "description": "on a form addressed to the owner: "
                                         "their own-words entry (ent-...) "
                                         "your proposal quotes"},
                "passage": {
                    "type": "object",
                    "description": "on a form addressed to the owner: the "
                                   "passage of `words` quoted, in code "
                                   "points, with the exact text you read",
                    "properties": {
                        "start": {"type": "integer"},
                        "end": {"type": "integer"},
                        "expected_excerpt": {"type": "string"},
                        "unit": {"type": "string",
                                 "enum": ["codepoint", "utf16"]}},
                    "required": ["start", "end", "expected_excerpt"]},
                "row": {"type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "propose a new table row instead: "
                                       "column name -> text"},
                "new_field": {
                    "type": "object",
                    "description": "propose a new form field instead",
                    "properties": {"id": {"type": "string"},
                                   "kind": {"type": "string"},
                                   "label": {"type": "string"}},
                    "required": ["id", "kind"]},
                "op": {"type": "string",
                       "description": "an operation key: a retry with the "
                                      "same key returns the first outcome"},
            },
        },
    },
    {
        "name": "await_work",
        "description": (
            "Say that the work you are carrying cannot go on until OTHER work "
            "already in Mentis is finished -- a request somebody else carries, "
            "that you did not delegate. Give its expectation reference. Mentis "
            "resumes this work by itself when that work's carrier claims it "
            "met (a run of it merely ending does not count), and not before. "
            "Then end your run: say where things stand with respond, without "
            "fulfils. Work Mentis does not hold cannot be waited on this way; "
            "for a decision, use request_decision; for work you hand out, "
            "delegate with return_to_me."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"expectation": {
                               "type": "string",
                               "description": "the awaited request's "
                                              "expectation reference (opr-...)"},
                           "because": {"type": "string",
                                       "description": "why this work needs "
                                                      "it finished first"}},
            "required": ["expectation"],
        },
    },
    {
        "name": "record_discovered_work",
        # WHAT THIS OPERATION IS, AND NO LONGER WHAT TO DO ABOUT SIDE WORK. The
        # description used to end "Use it instead of mentioning side work in
        # prose, and instead of doing it." That is a decision policy -- when to
        # pursue what you found and when to write it down -- and it was
        # duplicated: the governed Finding-scope Rule says the same thing, and
        # the Authorship Decision settles the phrase it turns on. It stayed
        # here deliberately while that Rule was unestablished, so there was
        # never a moment with neither. The Rule now stands and its real
        # delivery has been observed in a run's own `behavioural_sources`, so
        # the duplicate goes and the behaviour has one home.
        #
        # WHAT REMAINS IS THE CONTRACT: what invoking this creates, and the
        # three things it structurally does not do. Those are facts about the
        # operation and they belong in code.
        "description": (
            "Record a piece of work you found that is real but is not the work "
            "you are carrying, so it is kept without being pursued. It becomes "
            "a Turn here and something owed that NOBODY is assigned to: it "
            "dispatches nobody, asks nothing of the owner and grants nothing. "
            "Work under a request whose owner gave follow-up permission "
            "covering it can pick it up later with delegate(expectation=<its "
            "reference>) without asking again; the answer says whether that "
            "holds. Otherwise it waits, and the owner is asked about it once "
            "the work it was found under is finished."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"work": {"type": "string",
                                    "description": "what the work is"},
                           "under": {"type": "string",
                                     "description": "for a hand-started "
                                                    "session, the request "
                                                    "that carries this "
                                                    "finding"},
                           "because": {"type": "string",
                                       "description": "why it is real, and "
                                                      "why it is not yours now"}},
            "required": ["work"],
        },
    },
    {
        "name": "record_verdict",
        "description": (
            "Record the verdict of the review you are carrying: `pass`, "
            "`block` (it must not go in as it is), or `incomplete` (you could "
            "not finish judging it). When it is incomplete because this "
            "runtime cannot do something the review needs -- build the UI, "
            "drive a browser -- name those capabilities in `lacks` "
            "(build_ui, drive_browser, ...), so whoever carries the work on "
            "can send it where they are. `commit` is the commit you judged. Say what you found in "
            "your reply as well; this records the outcome, not the review."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string",
                            "enum": ["pass", "block", "incomplete"]},
                "commit": {"type": "string",
                           "description": "the commit reviewed"},
                "lacks": {"type": "array", "items": {"type": "string"},
                          "description": "declared capabilities this run "
                                         "lacked, for an incomplete verdict"},
                "summary": {"type": "string"}},
            "required": ["verdict", "summary"],
        },
    },
    {
        "name": "return_artifact",
        "description": (
            "Hand a file you made back to Mentis, so Mentis holds its bytes. "
            "A path in your reply is NOT a return: nobody else can open it, "
            "and it disappears with your workspace. Give the path of ONE "
            "regular file inside your working directory; it is read once, "
            "now, hashed, and sent. Mentis never reads that path again. "
            "`media_type` is your claim; Mentis decides what it serves it as. "
            "Returns an artifact reference -- refer to the file by that."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"},
                           "media_type": {"type": "string"},
                           "because": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "read_artifact",
        "description": (
            "Get the bytes of an artifact Mentis holds, by its reference "
            "(adm-...): one you were offered (what your request was made with "
            "or referenced, what earlier runs of this work returned, what "
            "work you delegated and waited on returned), or -- when a person "
            "asked for your work -- one held in that Conversation: posted in "
            "its Turns or returned there by other agents, unless that work was "
            "restricted. Work delegated to you reaches only what it was handed "
            "unless its delegation widened it. A Quick Ask, which carries no "
            "request, reaches any artifact Mentis holds unless restricted work "
            "returned it, and its reads are not recorded. An acquired IMAGE "
            "from a Bulk Source collection (an adm- that `sources` lists) is "
            "reachable wherever read_source is, and comes back with its "
            "collection and key to cite it by; write its adm- reference in "
            "what you post and the owner sees the image there. Any other "
            "acquired file is read with read_source. Images over 5 MB are "
            "refused, with their "
            "size. Anything else is refused, with "
            "the reason. Find references with resolve on the Turns. The bytes "
            "are written into your working directory under .mentis-artifacts/ "
            "and the path is returned; an image is also shown to you, and "
            "text is included in the answer. The name is metadata; the digest "
            "is the identity."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
    },
    {
        "name": "open_topic",
        "description": (
            "Open a Topic in the Conversation you are working in, for work "
            "substantial enough to deserve its own strand. A Topic organises; "
            "it does not move anything and is not a boundary."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"},
                           "about": {"type": "string"},
                           "conversation": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "open_conversation",
        "description": (
            "Open a new Conversation, for work that is genuinely separate from "
            "this one. It stays causally connected to the request that led to "
            "it. Prefer a Topic, or staying here, unless the work is separable."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"},
                           "about": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "summon_participant",
        "description": (
            "Find a durable Participant by alias, or deliberately create one "
            "for delegated work, and add them to a Conversation. The same alias "
            "always reaches the SAME Participant -- this never makes a second "
            "one -- so use it to reach somebody who already exists as well."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"alias": {"type": "string"},
                           "about": {"type": "string"},
                           "conversation": {"type": "string"}},
            "required": ["alias"],
        },
    },
    {
        "name": "delegate",
        "description": (
            "Hand part of this work to a Participant, optionally wearing an "
            "ESTABLISHED Persona, and dispatch them. They author their own "
            "result; you must not present it as yours. This does NOT satisfy "
            "the request you are carrying -- it creates work under it. Set "
            "return_to_me when you need their result before you can answer. "
            "Several delegations may be outstanding at once and each returns "
            "independently. Those you delegate to may hand on work outside "
            "their own role the same way. This hands on the work YOU "
            "CARRY, with what that needs: who (brought into this "
            "Conversation if they are not here), runtime, model, effort, "
            "requires and a repository directory. Taking on work you do not "
            "carry -- `expectation`, picking up discovered work -- is "
            "coordinating, and needs your request to have been granted "
            "`coordinate`; without it, leave that work recorded for "
            "whoever coordinates. `activity` says which activity of a "
            "Workflow you were delivered this is, and the child receives "
            "that step's Persona and Disciplines (owner ruling "
            "2026-10-29); a `persona` or `governed` you name still wins. "
            "It moves nothing and starts nothing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "participant": {"type": "string",
                                "description": "a Participant reference"},
                "work": {"type": "string"},
                "under": {"type": "string",
                           "description": "for a hand-started session, the "
                                          "request carrying a finding being "
                                          "picked up"},
                "persona": {"type": "string",
                            "description": "an established Persona reference"},
                # WHAT THE ARGUMENT IS, AND NOTHING ABOUT HOW TO BEHAVE. An
                # earlier wording of this said "Name what applies", which is a
                # directive about judgement rather than a description of the
                # field, and enumerated two Kinds -- in agent-visible text, in
                # a record whose Kinds declare their own ladder. Both are gone.
                # What remains is the contract: references, resolved later, and
                # what invoking it does not do.
                "governed": {"type": "array", "items": {"type": "string"},
                             "description": "references to governed material "
                                            "this work is to be composed with. "
                                            "They are carried as references, "
                                            "not copied: what stands when the "
                                            "work runs is what reaches it, and "
                                            "material nobody established "
                                            "reaches nobody. Naming material "
                                            "here establishes nothing"},
                "activity": {"type": "string",
                             "description": "which activity of a Workflow "
                                            "you were delivered this work is, "
                                            "as \"<workflow reference>#<key>\". "
                                            "Recorded on the delegation so "
                                            "progress can be read from the "
                                            "record. Delegated Builders and "
                                            "Reviewers receive their step's "
                                            "Persona and Disciplines (owner "
                                            "ruling 2026-10-29), at their "
                                            "current standing versions: "
                                            "without `persona`, the child "
                                            "wears the activity's Persona; "
                                            "without `governed`, it is given "
                                            "the activity's Disciplines; a "
                                            "`governed` list is joined by "
                                            "them; `governed: []` means none. "
                                            "It moves nothing and starts "
                                            "nothing"},
                "expects": {"type": "string"},
                "because": {"type": "string"},
                "conversation": {"type": "string"},
                "topics": {"type": "array", "items": {"type": "string"}},
                "requires": {"type": "array", "items": {"type": "string"},
                             "description": "declared capabilities this work "
                                            "genuinely needs"},
                "return_to_me": {"type": "boolean"},
                "repository": {"type": ["boolean", "string"],
                               "description": "the directory the child works "
                                              "in: an absolute path, or true "
                                              "for the one this work "
                                              "declared. Mentis makes no "
                                              "worktree and commits nothing; "
                                              "Git is yours and the "
                                              "child's"},
                "review_of": {"type": "string",
                              "description": "for a review: the request "
                                             "(this work, or work you "
                                             "delegated) it reviews. It "
                                             "works in the directory that "
                                             "request declared, if any"},
                "artifacts": {"type": "array", "items": {"type": "string"},
                              "description": "held artifact references "
                                             "(adm-...) to hand over with the "
                                             "work. Only ones you may read "
                                             "yourself"},
                "reach": {"type": "string", "enum": ["work", "conversation"],
                          "description": "what the child may read beyond what "
                                         "you hand it. `work` (the default): "
                                         "only that and its own lineage. "
                                         "`conversation`: also what is held "
                                         "in the Conversation, and only if "
                                         "your own work reaches it"},
                "restricted": {"type": "boolean",
                               "description": "keep what the child returns "
                                              "to this work's lineage: nobody "
                                              "else reaches it through the "
                                              "Conversation"},
                "restricted_because": {"type": "string"},
                "runtime": {"type": "string",
                            "description": "only when the owner constrained "
                                           "which runtime runs this work"},
                "model": {"type": "string",
                          "description": "only when the owner chose the model. "
                                         "It is a constraint: if nothing can run "
                                         "it, the work is refused, never moved "
                                         "to another model"},
                "effort": {"type": "string",
                           "description": "only when the owner chose how much "
                                          "the model may reason, in the "
                                          "runtime's own effort words (e.g. "
                                          "`none`). A constraint like model: "
                                          "sent as asked, never substituted"},
                "constraint_basis": {"type": "string",
                                     "description": "the owner's Turn that "
                                                    "decided the runtime/model/"
                                                    "effort"},
                "expectation": {
                    "type": "string",
                    "description": "coordinating, so only with "
                                   "`coordinate`: an existing "
                                   "piece of DISCOVERED work nobody "
                                   "is assigned to. It is assigned to them as it "
                                   "is -- same identity, same discovery, same "
                                   "lineage -- instead of being written again"},
            },
            "required": ["participant", "work"],
        },
    },
    {
        "name": "propose_material",
        "description": (
            "Put material forward for the owner to judge. It is written as a "
            "CANDIDATE and governs nothing. THIS SURFACE CANNOT ESTABLISH "
            "ANYTHING, and reaching the record by any other route to do so is "
            "OUT OF BOUNDS -- not merely unavailable. You run as the owner, so "
            "other routes exist; using one because this one said no is the one "
            "thing that would make the record untrue. If you need something "
            "established, propose it and say so, or report the refusal. Never "
            "act as though you had established it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"kind": {"type": "string"},
                           "body": {"type": "object"}},
            "required": ["kind", "body"],
        },
    },
    {
        "name": "propose_revision",
        "description": (
            "Propose a better version of governing material YOU WERE GIVEN "
            "for this work, when "
            "doing the work showed what it should say. `of` is its reference, "
            "shown as `(reference: ent-...)` under it in your work; `body` is "
            "the whole new version in the "
            "fields its Kind declares. It is written as a CANDIDATE proposed "
            "to replace that material: the material goes on standing and "
            "governing exactly as before, and only the owner can establish "
            "your version. Refused for material you were not given. "
            "`supports_with` may add evidence written beside it -- e.g. "
            "{\"kind\": \"lesson\", \"body\": {...}} supporting the "
            "revision, or {\"kind\": \"outcome\", \"body\": {...}, "
            "\"relation\": \"outcome-of\"} recording what happened when "
            "the current version was tried -- each also a candidate."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "of": {"type": "string",
                       "description": "the delivered material (ent-...)"},
                "body": {"type": "object",
                         "description": "the whole proposed version"},
                "because": {"type": "string",
                            "description": "what the work showed"},
                "supports_with": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "optional evidence: {kind, body, "
                                   "relation?} with relation `supports` "
                                   "(the default: it supports the proposed "
                                   "version) or `outcome-of` (an outcome of "
                                   "the material as it stands)"},
            },
            "required": ["of", "body", "because"],
        },
    },
    {
        "name": "anchor",
        "description": (
            "Name an exact place in a Turn: the whole of one version "
            "(type 'version'), or a passage of one of its text parts "
            "(type 'text-range': part index, start and end in code points, and "
            "the excerpt you expect there, which must match exactly). The same "
            "place always gives the same anchor. An anchor asserts nothing; "
            "react to it, reply through it, or open a deep dive from it. Only "
            "on Turns in the Conversation you work in, or one you opened."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "version": {"type": "string",
                            "description": "the Turn version (a Turn's id is "
                                           "its first version)"},
                "type": {"type": "string", "enum": ["version", "text-range"]},
                "part": {"type": "integer"},
                "start": {"type": "integer"},
                "end": {"type": "integer"},
                "unit": {"type": "string", "enum": ["codepoint", "utf16"]},
                "expected_excerpt": {"type": "string"},
                "op": {"type": "string",
                       "description": "an operation key: a retry with the same "
                                      "key returns the first outcome"},
            },
            "required": ["version", "type"],
        },
    },
    {
        "name": "react",
        "description": (
            "React to an anchor with a short token (an emoji or a word). It is "
            "recorded as yours and has no standing and no effect on anything. "
            "To change your reaction, react again naming the earlier one in "
            "`changes`; the earlier one stays in history. To say something, "
            "reply instead."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "anchor": {"type": "string"},
                "token": {"type": "string"},
                "changes": {"type": "string"},
                "because": {"type": "string"},
                "op": {"type": "string"},
            },
            "required": ["anchor", "token"],
        },
    },
    {
        "name": "deep_dive",
        "description": (
            "Open a fresh Conversation to explore an anchor, saying why. It "
            "starts with nothing of the Conversation the anchor is in -- only "
            "the anchor and your reason -- and keeps a durable link back to "
            "where it came from. You may continue work there, and dive again "
            "from inside it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "anchor": {"type": "string"},
                "why": {"type": "string"},
                "name": {"type": "string",
                         "description": "optional; never built from the "
                                        "anchored text"},
                "op": {"type": "string"},
            },
            "required": ["anchor", "why"],
        },
    },
    {
        "name": "resume_intake",
        "description": (
            "Coordinating, so only with `coordinate`: carry a request Ask "
            "Mentis recorded but could not assign when it was asked, because "
            "no intake designation resolved then. It is resumed as itself -- "
            "the same request, Turn, author and reason -- assigned to the "
            "carrier designated now and dispatched with the Turn's own words; "
            "you choose only which request. `all` resumes every such request "
            "nobody has since carried or answered. Anything already assigned, "
            "answered, met or running is refused and dispatches nothing, so "
            "asking twice is safe. Refused while the designation still does "
            "not resolve."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"expectation": {
                "type": "string",
                "description": "the unassigned request's expectation "
                               "reference (opr-...), or \"all\""}},
            "required": ["expectation"],
        },
    },
    {
        "name": "respond",
        "description": (
            "Answer the request you are carrying. `parts` may be prose, or "
            "references to work recorded elsewhere, or both -- an answer is not "
            "structurally text. To answer one passage of the request, include "
            "one {\"type\": \"anchor\", \"ref\": <anchor>} part naming an "
            "anchor in the request's own Turn. Set fulfils when you are claiming the request "
            "is answered; that is recorded as YOUR claim, not as verified work. "
            "Say what you did, what you delegated, and what is still open. "
            "THIS IS THE WHOLE ANSWER AND THE ONLY ONE. Put everything the "
            "person needs here, in one call: this is the response they read, "
            "and the request gets exactly one. Do not hold anything back to "
            "summarise when you finish, and do not restate the answer as your "
            "final words -- text printed at exit is kept as evidence of how the "
            "run ended, not delivered as a second reply, so anything that is "
            "only there is something they were never told."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "parts": {"type": "array", "items": {"type": "object"}},
                "fulfils": {"type": "boolean"},
                "results": {"type": "array", "items": {"type": "string"},
                            "description": "references this answer rests on"},
                "result_kind": {"type": "string",
                                "description": "what the result IS, as a label "
                                               "for whoever renders it later"},
                "because": {"type": "string"},
            },
        },
    },
]

#: Every tool the surface offers, in one list because the adapters build their
#: pre-approval from it and a tool missing there is a tool that cannot be called.
# The new tools share the proposal grant group; none offers standing.
_LADDER_SCHEMAS = {
    "record_material": ({"kind": {"type": "string"}, "body": {"type": "object",
        "description": "The material payload: text (the principal statement), limits (optional context where this holds), falsifier (for hypothesis: what would prove it wrong), about (for rules/decisions), result and attempted (for outcome)."},
        "basis": {"type": "array", "items": {"type": "string"}},
        "outcome_of": {"type": "string"}, "in_context": {"type": "string"}}, ["kind", "body"],
        "Record what work taught you, with its basis (Kinds that declare requires_basis are refused without one). Record outcomes against material you were given, "
        "with outcome_of and in_context. Recording asks nobody anything and confers no standing."),
    "request_adoption": ({"entry": {"type": "string"}, "of": {"type": "string"},
        "body": {"type": "object"}, "scope": {"type": "object"},
        "replaces": {"type": "array", "items": {"type": "string"}},
        "because": {"type": "string"}}, ["because"],
        "Request adoption only when material should change future behaviour. Name entry, or of plus "
        "the whole revision body. Only the owner adopts; recording and requesting are separate acts."),
    "challenge": ({"target": {"type": "string"}, "because": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}}}, ["target", "because"],
        "Challenge material: say why, and name evidence references where you have them. "
        "The challenge travels with the material and revokes nothing."),
    "withdraw_challenge": ({"dispute": {"type": "string"}, "because": {"type": "string"}},
        ["dispute", "because"],
        "Withdraw a challenge YOU made (dispute = its `disputes` link id), saying why. "
        "Only the participant who made a challenge may withdraw it; the challenge and "
        "the withdrawal both stay in the record.")}
for _name, (_properties, _required, _description) in _LADDER_SCHEMAS.items():
    ACT_TOOLS.append({"name": _name, "description": _description,
        "inputSchema": {"type": "object", "properties": _properties, "required": _required}})
for _tool in ACT_TOOLS:
    if _tool["name"] == "propose_material":
        _tool["description"] = ("Compatibility alias: record_material followed by request_adoption. "
            "Use record_material alone to record evidence without asking anyone. Only the owner adopts.")
        _tool["inputSchema"]["properties"].update(_LADDER_SCHEMAS["record_material"][0])
        _tool["inputSchema"]["properties"]["because"] = {"type": "string"}
    elif _tool["name"] == "propose_revision":
        _tool["description"] = "Compatibility alias for request_adoption(of, body). " + _tool["description"]

ALL_TOOLS = TOOLS + ACT_TOOLS


#: What a worker is told it can run. The names are the same reads the MCP
#: server offers, because they are the same operations.
USAGE = """Ask Mentis about this Mark IV record. Read-only.

  <cmd> orient
  <cmd> find <text>
  <cmd> resolve <reference>
  <cmd> history [--conversation <ref>] [--turn <ref>] [--participant <ref>]
  <cmd> kinds
  <cmd> sources [<col-id>] [--q <text>] [--offset <n>]
  <cmd> source_history --collection <col-id> --path <relative path>
  <cmd> source_links --collection <col-id> --path <relative path>
  <cmd> read_source <adm-ref> [--offset <n>] [--length <n>]
  <cmd> read_source --collection <col-id> --path <relative path>
  <cmd> search_sources <phrase> [--collection <col-id>] [--offset <n>]
                 [--continuation <token>]

Prints JSON. This is the sanctioned way in; the record is a SQLite spine
you cannot usefully read by hand."""


def _result(surface: Surface, name: str, args: dict, *,
            participant: str | None = None,
            grant: dict | None = None,
            scope: str | None = None) -> dict:
    """Answer one read. `participant` is who is asking, read by the door off
    the grant it admitted the call under; only `brief` uses it."""
    effective_scope = scope or (f"conversation:{grant['conversation']}"
                                if (grant and grant.get("conversation")) else None)
    if name == "orient":
        return surface.orient(conversation=args.get("conversation"),
                              scope=effective_scope)
    if name == "resolve":
        return surface.resolve(args["ref"])
    if name == "history":
        if args.get("set"):
            return surface.set_changes(str(args["set"]).strip(),
                                       args.get("since"),
                                       int(args.get("limit") or PAGE))
        if args.get("since"):
            return {"refused": True, "asked": name,
                    "why_not": "`since` reads what changed in a response set: "
                               "name the set with `set`"}
        return surface.history(conversation=args.get("conversation"),
                               turn=args.get("turn"),
                               participant=args.get("participant"),
                               limit=int(args.get("limit") or PAGE))
    if name == "find":
        return surface.find(args.get("q", ""), int(args.get("limit") or PAGE))
    if name == "kinds":
        return surface.kinds()
    if name == "governed":
        return surface.governed(kind=args.get("kind"), q=args.get("q"),
                                state=args.get("state"),
                                limit=args.get("limit"))
    if name == "owner_decisions":
        return surface.owner_decisions(args.get("conversation"),
                                       args.get("most"))
    if name == "capabilities":
        return surface.capabilities()
    if name == "brief":
        return surface.brief(args.get("conversation"), participant,
                             persona=args.get("persona"),
                             workflow=args.get("workflow"),
                             work=args.get("work"),
                             # A DISPATCHED RUN CARRIES ITS REQUEST: briefed
                             # without naming it, it is briefed for that request
                             # -- its Persona, Workflow and Task Gravity --
                             # rather than as nobody's work (found in the cutover
                             # rehearsal: a depth-2 run was told "ask").
                             expectation=(args.get("expectation")
                                          or (grant or {}).get("expectation")),
                             follow_up=args.get("follow_up"),
                             scope=effective_scope,
                             detail=bool(args.get("detail")))
    if name == "recall":
        return surface.recall(args.get("work"), args.get("conversation"),
                              participant=participant,
                              full=bool(args.get("full")),
                              limit=args.get("limit"),
                              persona=args.get("persona"),
                              scope=effective_scope)
    if name == "work_overview":
        return surface.work_overview(args.get("conversation"),
                                     args.get("limit"),
                                     scope=effective_scope)
    if name == "check_rendering":
        from mentis.conversation import render_check
        if not args.get("text") and not args.get("syntax"):
            return {"ok": False, "error": "give `text` to check, or `syntax` "
                                          "(a block name, or all)"}
        if args.get("syntax") and not args.get("text"):
            # THE BLOCKS' FULL RULES, BY REFERENCE: a dispatch carries only
            # the brief (`renderers.RENDERER_BRIEF`) and this returns the rest.
            from mentis.conversation.renderers import syntax
            try:
                return {"ok": True, "syntax": syntax(args.get("syntax"))}
            except KeyError as exc:
                return {"ok": False, "error": exc.args[0]}
        got = render_check.about_unresolved(
            render_check.check(args.get("text")),
            surface.corpus if surface is not None else None)
        words = render_check.said(got, posted=False)
        return {"ok": True, **got,
                "note": "a dry run: nothing was written. "
                + (words or "No problems: every marked block in it renders.")}
    if name in SOURCE_READS:
        from mentis.sources import Refused

        # EVERY ARGUMENT OF EVERY SOURCE READ, CHECKED THE SAME WAY. Found by
        # independent review, twice. First: `source_history` and
        # `source_links` read `args["collection"]` and `args["path"]`
        # directly, so an omitted argument raised `KeyError` and `path=None`
        # reached `str.replace` and raised `AttributeError` -- and over the CLI
        # the `KeyError` was printed as "no such tool", a false answer about a
        # tool that exists. Then: the repair covered only those two, while
        # `sources` and `read_source` still raised `AttributeError` on a
        # non-string `q`/`path` and `ValueError`/`TypeError` on an `offset`,
        # `limit` or `length` that was not a number -- 20 distinct unsanctioned
        # exceptions were enumerated. A bad argument is an answer like any
        # other, and an agent must be able to tell "fix your argument" from
        # "the surface is broken".
        def _text(key, *, required=False, allow=None):
            got = args.get(key)
            if got is None or (isinstance(got, str) and not got.strip()):
                if required:
                    raise Refused(f"{name} needs {key!r}: name the collection "
                                  f"and the path inside it, as `sources` "
                                  f"reports them")
                return None
            if not isinstance(got, str):
                raise Refused(f"{name}'s {key!r} is text, not "
                              f"{type(got).__name__}")
            got = got.strip()
            if allow is not None and got not in allow:
                raise Refused(f"{name}'s {key!r} is one of "
                              f"{sorted(allow)}, not {got!r}")
            return got

        def _count(key):
            got = args.get(key)
            if got is None or got == "":
                return 0
            if isinstance(got, bool) or not isinstance(got, (int, str)):
                raise Refused(f"{name}'s {key!r} is a whole number, not "
                              f"{type(got).__name__}")
            try:
                n = int(got)
            except (TypeError, ValueError):
                raise Refused(f"{name}'s {key!r} is a whole number, not "
                              f"{got!r}") from None
            if n < 0:
                raise Refused(f"{name}'s {key!r} cannot be negative ({n})")
            return n

        try:
            if name == "sources":
                # A STATE THAT IS NOT A STATE IS REFUSED, not answered with an
                # empty listing: an empty answer on a bad filter would teach a
                # worker that a populated collection holds nothing, which is
                # the mistake this surface exists to stop.
                return surface.sources(
                    collection=_text("collection"), q=_text("q"),
                    state=_text("state", allow=_SOURCE_STATES)
                    if "state" in args else "present",
                    offset=_count("offset"),
                    limit=_count("limit") or None)
            if name == "source_history":
                return surface.source_history(
                    _text("collection", required=True),
                    _text("path", required=True))
            if name == "source_links":
                return surface.source_links(
                    _text("collection", required=True),
                    _text("path", required=True), ref=_text("ref"))
            if name == "search_sources":
                got = args.get("q")
                if not isinstance(got, str) or not got.strip():
                    raise Refused("search_sources needs `q`, a phrase to "
                                  "search acquired text for; an empty or "
                                  "whitespace-only phrase is refused")
                return surface.search_sources(
                    got, collection=_text("collection"),
                    offset=_count("offset"), limit=_count("limit") or None,
                    continuation=_text("continuation"))
            return surface.read_source(
                ref=_text("ref"), collection=_text("collection"),
                path=_text("path"), offset=_count("offset"),
                length=_count("length") or None,
                extraction=_text("extraction"))
        except Refused as exc:
            # AN ANSWER, NOT A MALFUNCTION: what the record cannot serve,
            # and why, said the same way on every wire.
            return {"refused": True, "why_not": str(exc), "asked": name}
    raise KeyError(name)


class NotPermitted(PermissionError):
    """This operation is not admissible for the grant that was presented.

    A `PermissionError`, so that every transport already reports it as a
    refusal rather than as a malformed request: the HTTP seam maps that to 403
    in one place, and a refusal arriving as "400 bad request" would tell a
    worker to fix its arguments when the answer is that it may not ask.

    Its own exception because it is an ANSWER -- the record refusing, in words
    that say what would have been needed -- and not a malfunction. A worker that
    reads it should report what it could not do and why, never retry it on
    another wire.
    """


def _artifact_bytes(surface: Surface, ref: str,
                    why: dict | None = None) -> tuple[dict, dict]:
    """The answer `read_artifact` gives for a ref already found reachable, and
    what was described. Writes nothing: whether the supply is recorded is the
    caller's to decide, and every refusal here comes before it is."""
    import base64
    from mentis import artifacts
    d = artifacts.describe(surface.corpus, ref)
    if d["state"] != "held":
        raise NotPermitted(f"{ref!r} is {d['state']}; there are no bytes "
                           "to supply")
    data = d.pop("_bytes")
    t = d["treatment"]
    if t["view"] == "image" and len(data) > artifacts.READ_IMAGE_MAX:
        # A REFUSAL THAT NAMES THE SIZE, never a truncation (Sources B, B1).
        raise NotPermitted(
            f"{ref!r} is an image of {len(data)} bytes; read_artifact sends "
            f"images of at most {artifacts.READ_IMAGE_MAX} bytes, and sends "
            "nothing rather than part of one")
    size = d["size"] if d.get("size") is not None else len(data)
    out = {"ref": ref, "digest": d["digest"], "size": size,
           "view": t["view"], "served_as": t["content_type"],
           "ext": t["ext"], "door": d.get("door"),
           "name_metadata": d.get("name"),
           "note": "the name is metadata supplied by whoever sent it; the "
                   "digest is the identity",
           "bytes_b64": base64.b64encode(data).decode("ascii")}
    if why and why.get("because") == artifacts.ACQUIRED_SOURCE:
        # WHAT TO CITE IT BY: an acquired observation is named by its
        # collection and key, and the `adm-` pins this observation.
        out.update({"collection": why.get("collection"),
                    "collection_name": why.get("collection_name"),
                    "key": why.get("key"),
                    "name_metadata": why.get("key"),
                    "note": "an acquired observation, held exactly as "
                            "swept; cite it by its ref, which pins this "
                            "observation. The digest is the identity"})
    d.setdefault("size", size)
    return out, d


# -- deleted material a Quick Ask was served, marked by Mentis ----------------
#
# THE OWNER'S RULING (on opr-b234b23b6ba5): a Quick Ask may read material from
# deleted Turns and Conversations, for completeness, and whenever deleted
# material was included it must be very clearly marked, whether or not the
# answer used it. THE MARKING COMES FROM MENTIS, NOT FROM THE AGENT'S HONESTY:
#
#   * the tool answer that carries it says so -- a `deleted: {what, when, by}`
#     field and a one-line `note` (`_deleted_marking`);
#   * the door notes which run was served it, in memory, here; the Quick Ask
#     runner takes the list when the run ends (`Foundation.answer_once`) and
#     the answer carries a banner naming the refs. It is presentation, not a
#     record: nothing durable is written, as nothing is for a Quick Ask read.
#
# WHAT THE READS SHOW OF IT. `find`, `history` and `resolve` blank what a
# deleted Turn said (`presented`, "[deleted]"). They do not blank what an
# artifact attached to it IS -- its name, claimed type, size and digest -- and
# an earlier version of this paragraph said they carried no deleted material,
# which independent review disproved (adm-c0651b2a8b5e, F1). So `resolve` of
# such an artifact, an identity `find` of it, and every `history` row about it
# carry the same marking, and the door notes a Quick Ask's sight of them for
# the banner exactly as it does its bytes (`note_deleted_reads`). Nothing is
# withheld and no reach changes: the marking is said to whoever reads it.

_deleted_lock = threading.Lock()
_deleted_served: dict[str, list[dict]] = {}


def _deleted_marking(surface: Surface, ref: str) -> dict | None:
    from mentis import artifacts
    gone = artifacts.deleted_from(surface.corpus, surface.cv, ref)
    if gone is None:
        return None
    return {"deleted": {"what": gone["what"], "ref": gone["ref"],
                        "when": gone["when"], "by": gone["by"]},
            "note": (f"DELETED MATERIAL: this came in on a "
                     f"{gone['what']} that has been deleted "
                     f"({gone['ref']}). Mark any passage that uses "
                     f"it as deleted material.")}


def note_deleted_reads(grant: dict, name: str, value: dict) -> None:
    """Note for the banner the deleted material a Quick Ask's read showed.

    Only a Quick Ask's: a dispatched run has no banner, and nobody would
    take what was noted for it. Reads the marking the answer already
    carries, so what the banner lists is what the agent was told."""
    if grant.get("scope") != TRANSIENT_SCOPE or not isinstance(value, dict):
        return
    instance = grant.get("instance")
    if name == "resolve":
        rows = [value] if value.get("what") == "a held artifact" else []
    elif name == "find":
        rows = value.get("found") or []
    elif name == "history":
        rows = [dict(r, ref=r.get("deleted_material"))
                for r in value.get("acts") or () if r.get("deleted")]
    else:
        rows = []
    for r in rows:
        d = r.get("deleted")
        if d and str(r.get("ref") or "").startswith("adm-"):
            note_deleted_served(instance, r["ref"], d)


def note_deleted_served(instance: str | None, ref: str, deleted: dict) -> None:
    if not instance:
        return
    with _deleted_lock:
        rows = _deleted_served.setdefault(instance, [])
        if all(r["ref"] != ref for r in rows):
            rows.append({"ref": ref, "deleted": deleted})


def take_deleted_served(instance: str | None) -> list[dict]:
    """What deleted material this run was served, and forget it."""
    with _deleted_lock:
        return _deleted_served.pop(instance or "", [])


def _operate(surface: Surface, name: str, args: dict, grant: dict) -> dict:
    """`_operation`, and for one that wrote the caller's Markdown as a Turn,
    what in it will not render (`TURN_WRITERS`), in the result.

    ACCEPT, DON'T REFUSE. The Turn is already written when it is checked --
    read back from the record, so the check is of what will be drawn -- and
    nothing about the check can undo or stop it: a check that fails says so
    in `rendering` and the result is otherwise the operation's own.
    """
    out = _operation(surface, name, args, grant)
    key = TURN_WRITERS.get(name)
    turn = out.get(key) if key and isinstance(out, dict) else None
    if turn:
        from mentis.conversation import render_check
        out["rendering"] = render_check.of_turn(surface.corpus, turn)
        # A REPLY THAT WRITES A CHOICE INSTEAD OF ASKING IT (P8): warned when
        # this run has raised no decision. Said, never refused.
        if name == "respond":
            # AND ONE FOR THE OWNER IS ASKED, as a decision form on the
            # reply, when the run raised none (`prose_decisions`).
            from mentis.web.prose_decisions import raise_from_reply
            asked = raise_from_reply(
                surface.cv, grant.get("instance"), turn,
                grant.get("expectation"), actor=grant.get("participant"),
                runtime=grant.get("runtime"))
            out["rendering"] = render_check.with_choices(
                out["rendering"], render_check.texts_of_turn(
                    surface.corpus, turn), surface.corpus,
                grant.get("instance"), asked=asked["form"] if asked else None)
            if asked:
                out["asked_as_decision_form"] = asked["form"]
    return out


def _taken_up_by(cv, expectation, actor) -> bool:
    """Whether a hand-started session assigned this side work to itself
    (`take_up`), and nobody has carried it since."""
    exp = cv._act(expectation)
    if not exp or exp.get("act") != "expectation-recorded":
        return False
    carrier = cv.assigned_carrier(expectation)
    return carrier.get("carrier") == actor and any(
        (a.get("detail") or {}).get("taken_up")
        for a in cv.history(caused_by=expectation)
        if a["id"] == carrier.get("assignment"))


def _session_carries(cv, expectation, actor) -> bool:
    """What a hand-started session carries: a request it recorded, or side
    work it took up. Nothing anybody else recorded."""
    exp = cv._act(expectation)
    detail = (exp or {}).get("detail") or {}
    if (exp and exp.get("act") == "expectation-recorded"
            and exp.get("actor") == actor and detail.get("manual_session")):
        return True
    return _taken_up_by(cv, expectation, actor)


def _operation(surface: Surface, name: str, args: dict, grant: dict) -> dict:
    """The operations beyond reading, each bounded by the grant it arrived with.

    WHAT A WORKER MAY NOT SAY, IN ONE PLACE. Not who it is, not which execution
    this is, not what caused it, not which Conversation it is acting in, and not
    what wrote it. Every one of those comes off the grant below, because a worker
    that could supply them could attribute its work to anybody and hang it off
    anything. What a worker supplies is the CONTENT -- a name, a question, a
    piece of work -- and nothing structural.

    WHAT IS CREATED ESTABLISHED, SAID EXACTLY, BECAUSE AN EARLIER VERSION OF
    THIS PARAGRAPH WAS FALSE. It claimed "nothing here establishes" and that
    `create_and_establish` is never called; a reviewer found three paths that
    reach it. The true statement is narrower:

      * Topics, Conversations AND Participants are created established, because
        that is what those Kinds are -- an unestablished Conversation is not a
        candidate anything could judge. They are attributed to the CARETAKER
        EXECUTION, never to a person, which is the half that matters.
      * GOVERNED MATERIAL IS NEVER ESTABLISHED HERE. `propose_material` calls
        `write` and not `create_and_establish`, has no argument that could ask
        for standing, and returns `stands: False`. A person establishes it or it
        never governs anything.

    So the boundary is not "no establishment" -- it is that nothing which
    GOVERNS BEHAVIOUR can be established from here.

    READ "FROM HERE" STRICTLY. It is the whole of the claim, and two blind
    challenges confirmed it is the only version of the claim that is true. This
    surface grants no way to establish governed material. It does not follow
    that a dispatched execution cannot establish any -- it runs as the owner,
    with a shell, and its own boot line names both this package and the corpus,
    so it can open the record directly and write whatever it likes, including a
    `written_by` naming a person. That was reproduced, not argued.

    Which is why the useful sentence is about the INTERFACE and never about the
    agent: Mentis bounds what it hands out, and it does not defend the record
    against code running as the owner. A claim any competent delegate can
    disprove in three lines is worse than no claim, because somebody would rely
    on it when deciding whether to read proposed material before establishing
    it.
    """
    cv = surface.cv
    if name == "read_artifact" and grant.get("scope") == TRANSIENT_SCOPE:
        # A QUICK ASK READS AN ARTIFACT AND LEAVES NO MARK, by owner decision
        # (opr-9fa00d2183a9; see `permitted`). Served before the Participant
        # check because its grant names nobody, and nothing is recorded: no
        # SUPPLIED act, and no other write. The supply record is provenance
        # only -- reach, lineage and purge read none of it -- so withholding
        # it here takes nothing from anybody else.
        from mentis import artifacts
        ref = str(args.get("ref") or "").strip()
        why, why_not = artifacts.reachable(surface.corpus, cv, grant, ref)
        if why is None:
            raise NotPermitted(
                f"{ref!r} is not reachable by this Quick Ask: {why_not}")
        answer = _artifact_bytes(surface, ref, why)[0]
        marked = _deleted_marking(surface, ref)
        if marked:
            # Said in the answer, and noted for the banner. Not recorded.
            answer.update(marked)
            note_deleted_served(grant.get("instance"), ref, marked["deleted"])
        return answer
    actor = grant.get("participant")
    execution = grant.get("instance")
    runtime = grant.get("runtime")
    parent = grant.get("expectation")
    here = grant.get("conversation")
    wrote = f"{runtime}/{(execution or '')[:8]}" if runtime else None
    if not actor:
        raise NotPermitted(
            "this grant names no Participant, so nothing can be recorded as "
            "having been done by anybody; the execution was not dispatched to "
            "act in the record")
    session = grant.get("scope") == SESSION_SCOPE

    # A HAND-STARTED SESSION MAY NAME THE REQUEST IT RECORDED as the work it
    # carries for the two operations whose lineage needs one. The durable
    # request, not a session-local variable, supplies both parent and place.
    # Requests attributed to anybody else remain unreachable through this
    # seam; the ordinary gravity functions below still decide pursuit.
    carried = str(args.get("under") or "").strip()
    if carried:
        if not session or name not in ("record_discovered_work", "delegate",
                                       "take_up"):
            raise NotPermitted(
                "`under` names carried work only for a hand-started session")
        carrying = cv._act(carried)
        if not _session_carries(cv, carried, actor):
            raise NotPermitted(
                "`under` must name a request recorded by this session "
                "participant, or side work it took up")
        parent = carried
        here = carrying.get("conversation")

    def _act(act, **kw):
        kw.setdefault("caused_by", parent)
        return cv.record_act(actor=actor, act=act, execution=execution,
                             runtime=runtime, **kw)

    def _where(asked) -> str:
        """Which Conversation an operation may act in. Checked, never taken.

        FOUND BY TWO INDEPENDENT REVIEWERS. `delegate` and `summon_participant`
        took `args["conversation"]` and used it unchecked, so a carrier
        dispatched for one Conversation could write Turns into ANY Conversation
        in the Brain and launch runtimes there -- while this module's own
        docstring listed "which Conversation it is acting in" among the things a
        worker may not say. It also went unvalidated as a reference at all: a
        Turn id or a Participant id was accepted, producing a `participates-in`
        link from a Participant to a Turn.

        TWO ARE LEGITIMATE and no more. The Conversation this execution was
        dispatched into, and one THIS EXECUTION OPENED -- which is read from the
        record, not claimed, so opening a Conversation and then delegating into
        it works without the argument becoming a way to reach anywhere else.
        """
        if not asked or asked == here:
            return here
        if not cv._is_kind(asked, "conversation"):
            raise NotPermitted(
                f"{asked!r} is not a Conversation in this record")
        mine = {a["conversation"] for a in cv.history(caused_by=parent)
                if a["act"] == "conversation-opened"} if parent else set()
        if session:
            # A SESSION CARRIES NO REQUEST, so what it opened is read by its
            # own execution -- one per session, never reused.
            mine = {a["conversation"] for a in cv.history(execution=execution)
                    if a["act"] == "conversation-opened"}
        if asked not in mine:
            raise NotPermitted(
                f"this execution was dispatched into {here!r} and may act there, "
                f"or in a Conversation it opened itself under this request. "
                f"{asked!r} is neither. Open one, or return the need.")
        return asked

    def _somewhere(asked) -> str:
        """`_where` for a session, which has no Conversation of its own."""
        got = _where(asked)
        if not got:
            raise NotPermitted(
                "this session carries no request and so has no Conversation "
                "of its own: open one with `open_conversation` and name it")
        return got

    def _named_conversation(asked) -> str:
        """A Conversation explicitly named for manual-session intake."""
        if not session:
            raise NotPermitted("only a hand-started session records CLI work")
        asked = str(asked or "").strip()
        if not asked or not cv._is_kind(asked, "conversation"):
            raise NotPermitted(f"{asked!r} is not a Conversation in this record")
        return asked

    if name == "record_request":
        conversation = _named_conversation(args.get("conversation"))
        said = str(args.get("text") or "").strip()
        if not said:
            raise NotPermitted("a recorded request needs its text")
        note = str(args.get("requester_note") or "").strip()
        repository = str(args.get("repository") or "").strip()
        branch = str(args.get("branch") or "").strip()
        lines = [said]
        lines += [f"Requester note: {note}"] if note else []
        lines += [f"Repository: {repository}"] if repository else []
        lines += [f"Branch: {branch}"] if branch else []
        from mentis.operational import follow_up_of, follow_up_value
        try:
            follow_up = follow_up_value(args.get("follow_up"))
        except ValueError as exc:
            raise NotPermitted(str(exc))
        request_parent = str(args.get("parent") or "").strip() or None
        if request_parent:
            inherited_from = cv._act(request_parent)
            inherited_detail = (inherited_from or {}).get("detail") or {}
            if (not inherited_from
                    or inherited_from.get("act") != "expectation-recorded"
                    or inherited_from.get("actor") != actor
                    or not inherited_detail.get("manual_session")):
                raise NotPermitted(
                    "parent must name a request recorded by this session "
                    "participant")
            inherited = follow_up_of(cv, request_parent)

            def breadth(value):
                if value == "ask":
                    return 0
                if value == "unrestricted":
                    return float("inf")
                return value["depth"]

            if "follow_up" in args and breadth(follow_up) > breadth(inherited):
                raise NotPermitted(
                    "follow-up permission belongs to the original request; "
                    "a child cannot widen the permission it was asked with")
            follow_up = inherited
        persona = str(args.get("persona") or "").strip() or None
        if persona:
            if not cv._is_kind(persona, "persona"):
                raise NotPermitted(f"{persona!r} is not a Persona")
            if not surface.corpus.stands(persona)["stands"]:
                raise NotPermitted(
                    f"Persona {persona!r} does not stand, so it cannot govern "
                    f"a request")
        workflow = str(args.get("workflow") or "").strip() or None
        if workflow:
            if not cv._is_kind(workflow, "workflow"):
                raise NotPermitted(f"{workflow!r} is not a Workflow")
            if not surface.corpus.stands(workflow)["stands"]:
                raise NotPermitted(
                    f"Workflow {workflow!r} does not stand, so it cannot "
                    f"govern a request")
        request_runtime = str(args.get("runtime") or "").strip() or None
        detail = {"expects": "result", "manual_session": True,
                  "session_execution": execution,
                  **({"follow_up": follow_up} if follow_up != "ask" else {}),
                  **({"persona": persona} if persona else {}),
                  **({"workflow": workflow, "governed": [workflow]}
                     if workflow else {}),
                  **({"runtime": request_runtime} if request_runtime else {}),
                  **({"requester_note": note} if note else {}),
                  **({"repository": repository} if repository else {}),
                  **({"branch": branch} if branch else {})}
        with surface.corpus.atomic():
            turn = cv.say(conversation, actor,
                          [text_part("\n\n".join(lines))], written_by=wrote)
            expectation = cv.expect(
                turn, of=actor, kind="result", by=actor,
                because=note or said, caused_by=request_parent, detail=detail)
            recorded = _act("manual-session-request-recorded",
                            conversation=conversation, turn=turn,
                            caused_by=expectation, about=[expectation],
                            because="request entered from a hand-started session",
                            detail={"repository": repository or None,
                                    "branch": branch or None})
        return {"ok": True, "conversation": conversation, "turn": turn,
                "expectation": expectation, "recorded": recorded}

    if name == "take_up":
        """Pursue discovered work oneself, as a hand-started session.

        WHY NOT `delegate`. Delegating hands work to another Participant and
        is answered with a dispatch: Mentis would start a run. A CLI session
        pursuing side work it found does the work itself, so the finding is
        assigned to the session and nothing is run -- the session's own
        execution carries it, as the trunk's. Everything that decides whether
        it may is the pickup's own: the same `pursuit_permitted` on the
        original request (with its origin checked, as `delegate` checks it),
        the owner's selection, and `owner_decided` asked again inside the one
        claim. Nothing here is a new policy.
        """
        picked = str(args.get("expectation") or "").strip()
        if not parent:
            raise NotPermitted("take_up names the request this session carries "
                               "in `under`")
        from mentis.operational import (discovery, owner_decided,
                                        owner_selected, pursuit_permitted)
        try:
            state = cv.expectation_state(picked)
        except ValueError:
            raise NotPermitted(f"{picked!r} is not a request in this record")
        if not any(a["act"] == "work-discovered" and picked in (a["about"] or ())
                   for a in cv.history(turn=state["turn"])):
            raise NotPermitted(f"{picked!r} is not discovered work in this record")
        permitted = pursuit_permitted(cv, picked)
        if permitted and discovery(cv, parent)["origin"] != permitted["origin"]:
            permitted = None
        if not permitted and not owner_selected(cv, picked):
            got = discovery(cv, picked)
            raise NotPermitted(
                f"{picked!r} is generation {got['generation']} side work, and "
                f"the follow-up permission on the request it was found under "
                f"does not cover it, nor has the owner chosen to pursue it. It "
                f"stays recorded; return to the request you carry -- the owner "
                f"is asked about it once that work is finished")
        with surface.corpus.atomic():
            if cv.assigned_carrier(picked)["carrier"] is not None:
                raise NotPermitted(
                    f"{picked!r} is already carried; taking it up would take it "
                    f"from whoever has it")
            said = owner_decided(cv, picked)
            if permitted and said:
                raise NotPermitted(
                    f"{picked!r} is {said}; follow-up permission does not "
                    f"override the owner")
            assignment = cv.assign(
                picked, actor, by=actor,
                because=str(args.get("because") or "taken up by the session "
                                                     "that carries its trunk"),
                detail={"picked_up_under": parent, "execution": execution,
                        "manual_session": True, "taken_up": True})
        got = discovery(cv, picked)
        return {"ok": True, "expectation": picked, "assignment": assignment,
                "under": parent, "generation": got["generation"],
                "note": "assigned to this session; nothing was dispatched. Close "
                        "it with record_outcome; side work found while doing it "
                        "is recorded with record_discovered_work under it"}

    if name == "record_outcome":
        expectation = str(args.get("expectation") or "").strip()
        exp = cv._act(expectation)
        detail = (exp or {}).get("detail") or {}
        # WORK A SESSION TOOK UP IS CLOSED THE SAME WAY as work it recorded:
        # the finding keeps its own record, and the session's assignment of it
        # to itself (`take_up`) is what makes it this kind of work.
        if _taken_up_by(cv, expectation, actor):
            detail = {**detail, "manual_session": True}
            exp = {**exp, "actor": actor}
        # ANY HAND-STARTED SESSION MAY CLOSE IT, not only the one that opened
        # it: work recorded today is finished tomorrow by another session or
        # another runtime, and that continuation is the point of recording it.
        # Who closed it is the act's own `execution` and `runtime`.
        if (not exp or exp.get("act") != "expectation-recorded"
                or not detail.get("manual_session")
                or exp.get("actor") != actor):
            raise NotPermitted(
                "record_outcome names a request a hand-started session "
                "recorded (record_request, or remaining work from an outcome)")
        result = str(args.get("result") or "").strip()
        if result not in ("done", "partial", "abandoned"):
            raise NotPermitted("result is done, partial or abandoned")
        outcome = str(args.get("outcome") or "").strip()
        if not outcome:
            raise NotPermitted("an outcome needs saying what happened")
        references = list(args.get("references") or ())
        runtimes = [str(x).strip() for x in (args.get("runtimes") or ())
                    if str(x).strip()]
        remaining = list(args.get("remaining") or ())

        def label(value):
            if isinstance(value, dict):
                return str(value.get("work") or value.get("text")
                           or value.get("ref") or json.dumps(value,
                                                              sort_keys=True))
            return str(value)

        lines = [outcome, f"Result: {result}"]
        if references:
            lines.append("References: " + "; ".join(label(x)
                                                     for x in references))
        if runtimes:
            lines.append("Runtimes: " + ", ".join(runtimes))
        if remaining:
            lines.append("Remaining: " + "; ".join(label(x)
                                                    for x in remaining))
        conversation = exp.get("conversation")
        with surface.corpus.atomic():
            turn = cv.say(conversation, actor,
                          [text_part("\n\n".join(lines))],
                          replies_to=exp.get("turn"), written_by=wrote)
            outcome_act = _act(
                "manual-session-outcome-recorded", conversation=conversation,
                turn=turn, caused_by=expectation,
                about=[turn] + [str(x.get("ref")) for x in references
                                if isinstance(x, dict)
                                and ENTRY_REF.fullmatch(str(x.get("ref") or ""))],
                because=outcome,
                detail={"result": result, "references": references,
                        "runtimes": runtimes})
            met = None
            if result == "done":
                met = _act("expectation-met", conversation=conversation,
                           turn=turn, caused_by=expectation, about=[turn],
                           because=outcome,
                           detail={"result_kind": result,
                                   "claimed_by": execution})
            kept = []
            for item in remaining:
                work = label(item).strip()
                if not work:
                    raise NotPermitted("remaining work needs text")
                item_detail = item if isinstance(item, dict) else {}
                pending_turn = cv.say(conversation, actor, [text_part(work)],
                                      written_by=wrote)
                pending = cv.expect(
                    pending_turn, of=None, kind="result", by=actor,
                    because=str(item_detail.get("because") or work),
                    caused_by=outcome_act,
                    detail={"remaining_from": expectation,
                            "manual_session": True,
                            "session_execution": execution,
                            **{k: item_detail[k] for k in ("repository", "branch")
                               if item_detail.get(k)}})
                discovered = _act(
                    "work-discovered", conversation=conversation,
                    turn=pending_turn, caused_by=outcome_act, about=[pending],
                    because="remaining after the recorded outcome")
                kept.append({"turn": pending_turn, "expectation": pending,
                             "recorded": discovered})
        reconsidered = None
        if result == "done":
            from mentis.operational import reconsider_after
            reconsidered = reconsider_after(surface.brain, expectation)
        return {"ok": True, "conversation": conversation, "turn": turn,
                "expectation": expectation, "outcome_act": outcome_act,
                "result": result, "fulfilled_by": met,
                "remaining": kept, "reconsideration": reconsidered,
                "note": "record findings and lessons with record_material, "
                        "using this outcome Turn as basis"}

    if name == "request_decision":
        """Say that a decision is the owner's, as a fact rather than as prose.

        It writes an expectation OF THE BRAIN'S OWNER, identified as the wake
        check identifies them, and keeps who requested the carried work as
        `requester`. A worker cannot name the recipient, so this can never
        become a way to assign work to somebody else.

        REGRESSION (UI/UX #655 and #668). It used to be owed by the carried
        work's requester. Under a finding the owner chose to pursue, that is
        the agent who RECORDED the finding: both decisions sat owed by
        @Builder, who is never run to answer a decision, and the owner's
        Needs You, Work Overview and decision card -- each of which shows what
        the viewer owes -- showed neither. The requester is used only where
        the record names no owner.
        """
        # EVERY DECISION IS A DECISION FORM (P9): one question or several,
        # on the post `on` names or -- left out -- on the run's answer post
        # once it is written, never a top-level post of its own. Decisions
        # asked as their own post before this keep the rule they had.
        return _decision_form(cv, args, actor=actor, parent=parent,
                              here=here, wrote=wrote, act=_act, where=_where,
                              execution=execution)

    if name == "record_verdict":
        """The verdict of the review this run carries, as a fact.

        A `review-verdict` act on the carried request (the name is fixed:
        `dispatch.REVIEW_VERDICT`, read by recovery and the work view).
        `lacks` must name declared capabilities, as `requires` must; it is
        read only beside an `incomplete` verdict."""
        from mentis.api.types import Capability
        from mentis.web.dispatch import REVIEW_VERDICT
        if not parent:
            raise NotPermitted(
                "this execution carries no expectation, so there is no "
                "review to record a verdict on")
        verdict = str(args.get("verdict") or "").strip().lower()
        if verdict not in ("pass", "block", "incomplete"):
            raise NotPermitted("verdict is pass, block or incomplete")
        summary = str(args.get("summary") or "").strip()
        if not summary:
            raise NotPermitted("say in `summary` what the verdict rests on")
        lacks = list(dict.fromkeys(str(c).strip() for c in
                                   (args.get("lacks") or ()) if str(c).strip()))
        known = {c.value for c in Capability}
        unknown = [c for c in lacks if c not in known]
        if unknown:
            raise NotPermitted(
                f"{unknown} name no capability any runtime can declare. "
                f"Known: {sorted(known)}")
        if lacks and verdict != "incomplete":
            raise NotPermitted("`lacks` goes with an incomplete verdict only")
        commit = str(args.get("commit") or "").strip() or None
        act = _act(REVIEW_VERDICT, conversation=here, about=[parent],
                   because=summary[:400],
                   detail={"verdict": verdict, "commit": commit,
                           "lacks": lacks, "summary": summary,
                           "runtime": runtime})
        return {"ok": True, "act": act, "verdict": verdict, "lacks": lacks,
                "note": ("recorded. When this run ends the review is sent "
                         "once to a runtime that declares "
                         f"{', '.join(lacks)}, if there is one"
                         if lacks else "recorded")}

    if name == "request_input":
        """Say that the carried work waits for the owner's input on a block.

        AN EXPECTATION OF THE OWNER, `expects: "input"`, on the post the
        block is in and caused by the carried request -- owed as
        `request_decision` owes a decision, and never somebody else's. It
        names the response set, opening it if it is not open yet, and the
        marked-ready entries the set already holds, which answer nothing:
        only a Done written after this does (`Conversations.expectation_
        state`). Declaring the same open wait twice returns the first and
        records nothing.
        """
        from mentis.conversation import INPUT, responses
        from mentis.conversation.versions import Refused, inert_refusal
        from mentis.conversation.owner import _owner
        if not parent:
            raise NotPermitted(
                "this execution carries no expectation, so there is no work "
                "to wait")
        sid = str(args.get("set") or "").strip()
        part = args.get("part", 0)
        if part is None:
            part = 0
        try:
            if sid:
                got = cv.corpus.read([sid])
                if not got or (got[0].get("definition") or {}).get(
                        "name") != responses.RESPONSE_SET:
                    raise NotPermitted(f"{sid!r} is not a response set")
                s = got[0]
                root = s["body"]["post"]
            else:
                post = str(args.get("post") or "").strip()
                block = str(args.get("block") or "").strip()
                if not post or not block:
                    raise NotPermitted(
                        "name the block: its post and its name=, or its "
                        "response set")
                root = responses.post_root(cv.corpus, post) \
                    if cv.corpus.read([post]) else post
            # IN A CONVERSATION THIS RUN MAY ACT IN, as `answer`, `anchor`
            # and `react` check -- before anything is written, so a run
            # cannot open a set or owe the owner input anywhere else.
            where = cv.conversation_of(root)
            if not where:
                raise NotPermitted(f"{root!r} is not a post in a Conversation")
            _where(where)
            if not sid:
                sid = responses.open_set(cv, post, block=block, part=part,
                                         by=actor, written_by=wrote)["set"]
                s = cv.corpus.read([sid])[0]
        except Refused as refused:
            raise NotPermitted(refused.refusal.get("error")
                               or "that block cannot take input")
        sb = s["body"]
        root = sb["post"]
        gone = inert_refusal(cv.corpus, root)
        if gone:
            raise NotPermitted(
                "the post this block is in was deleted, so it accepts no new "
                "answers and there is nothing to wait for")
        asked_by = cv.expectation_state(parent)["requested_by"]
        owner = _owner(cv)
        of = owner or asked_by
        if sb.get("mode") == "each" and sb.get("holder") != of:
            raise NotPermitted(
                "that response set is somebody else's own, so the owner "
                "cannot mark it ready; name the owner's set or a shared one")
        with cv.corpus.atomic():
            for a in cv.history(caused_by=parent):
                if (a["act"] == "expectation-recorded"
                        and (a.get("detail") or {}).get("expects") == INPUT
                        and a["detail"].get("response_set") == sid
                        and not cv.expectation_state(a["id"])[
                            "response_present"]):
                    return {"ok": True, "expectation": a["id"], "set": sid,
                            "post": root, "of": of, "already": True,
                            "note": "this work already waits for that "
                                    "input; nothing new was recorded"}
            before = [m["id"] for m in responses._members(
                cv.corpus, sid, responses.MARKED_READY)]
            exp = cv.expect(root, of=of, kind=INPUT, by=actor,
                            because=args.get("because")
                            or "input only the owner can give",
                            caused_by=parent,
                            detail={"response_set": sid,
                                    "block": sb.get("block"),
                                    "part": sb.get("part"),
                                    "ready_before": before,
                                    "requester": asked_by})
            _act("input-requested", conversation=cv.conversation_of(root),
                 turn=root, about=[exp, sid])
        now = responses.state(cv, sid)
        return {"ok": True, "expectation": exp, "set": sid, "post": root,
                "block": sb.get("block"), "of": of, "requester": asked_by,
                **({"ready_now": now["marked_ready"]} if now.get("ready")
                   else {}),
                "note": ("recorded as owed BY the owner" if owner
                         else "recorded as owed BY the requester, because "
                              "this record names no owner")
                + "; this work resumes by itself, once, when they mark it "
                  "ready (Done) from now on, and is handed the answers they "
                  "marked. A reply does not count. End this run without "
                  "claiming the work met"
                + ("; it is ALREADY marked ready as it stands "
                   "(ready_now): read it, and wait only if you need them "
                   "to mark it again" if now.get("ready") else "")}

    if name == "answer":
        """One field's value, recorded as this run's Participant's answer.

        `responses.answer` does the work, exactly as the owner's own routes
        call it: the block's rules, the deleted-source refusal, the retry key
        and conflicts are all its. What is added here is who and where: the
        actor, execution and cause come off the grant, the post must be in a
        Conversation this run may act in (`_where`), and on a block in a post
        addressed to the owner the run never answers -- it goes to
        `_propose_on_owner_form`, which records P2b's interpretation. So
        does a proposed new row (`row`) or new field (`new_field`), on any
        block: neither is ever written into the post by anybody but its
        author. A refusal writes nothing, a response set included: opening
        the set and answering are one transaction."""
        from mentis.conversation import responses
        from mentis.conversation.versions import Refused
        from mentis.conversation.owner import _owner
        if not parent:
            raise NotPermitted(
                "this execution carries no expectation, so an answer would "
                "be given under no work")
        row, new_field = args.get("row"), args.get("new_field")
        if row is not None and new_field is not None:
            raise NotPermitted("propose one thing at a time: a `row` or a "
                               "`new_field`, not both")
        field = args.get("field")
        if row is not None:
            proposes = {"type": "add-row", "row": row}
        elif new_field is not None:
            proposes = {"type": "add-field", "field": new_field}
        else:
            if not isinstance(field, str) or not field:
                raise NotPermitted("name the `field` to answer, as `resolve` "
                                   "on the post or its response set lists "
                                   "it, or propose a `row` or a `new_field`")
            if "value" not in args:
                raise NotPermitted("an answer needs a `value`")
            proposes = {"type": "set-field", "field": field,
                        "value": args["value"]}
        replaces = args.get("replaces") or []
        if isinstance(replaces, str):
            replaces = [replaces]
        sid = str(args.get("set") or "").strip()
        part = args.get("part") or 0
        block = ""
        act_kw = {"execution": execution, "runtime": runtime,
                  "caused_by": parent}
        try:
            if sid:
                root = responses._set(cv.corpus, sid)["body"]["post"]
            else:
                post = str(args.get("post") or "").strip()
                block = str(args.get("block") or "").strip()
                if not post or not block:
                    raise NotPermitted(
                        "name the block: its response set, or its post and "
                        "its name=")
                root = responses.post_root(cv.corpus, post) \
                    if cv.corpus.read([post]) else post
            where = cv.conversation_of(root)
            if not where:
                raise NotPermitted(f"{root!r} is not a post in a Conversation")
            _where(where)
            owner = _owner(cv)
            got = cv.corpus.read([root])
            addressed = bool(owner and actor != owner and got and owner in (
                (got[0].get("body") or {}).get("addressed_to") or ()))
            if addressed or proposes["type"] != "set-field":
                return _propose_on_owner_form(
                    cv, root, args, sid=sid, block=block, part=part,
                    owner=owner if addressed else None, actor=actor,
                    written_by=wrote, act_kw=act_kw, proposes=proposes)
            # ONE TRANSACTION: a refused answer (an unknown field, a value
            # of the wrong shape) rolls back the set it would have opened.
            with cv.corpus.atomic():
                if not sid:
                    sid = responses.open_set(cv, root, block=block, part=part,
                                             by=actor, written_by=wrote,
                                             act_kw=act_kw)["set"]
                got = responses.answer(cv, sid, field=field,
                                       value=args["value"], replaces=replaces,
                                       note=args.get("note"), by=actor,
                                       owner=owner, written_by=wrote,
                                       op=args.get("op"), act_kw=act_kw)
        except Refused as refused:
            raise NotPermitted(refused.refusal.get("error") or "refused")
        out = {"ok": True, **got, "revision": got["answer"]}
        if got.get("conflict"):
            heads = responses.heads(responses.answers_in(cv, sid)).get(field, [])
            out["conflict"] = {
                "answers": got["conflict"],
                "heads": [{"answer": a["id"], "value": a["body"]["value"],
                           "by": a["attributed_to"],
                           "by_alias": cv.alias(a["attributed_to"]),
                           "when": _when(a["recorded_at"])} for a in heads]}
            out["note"] = ("CONFLICT: somebody else changed this field after "
                           "the answer you replaced. Both answers are kept "
                           "and the field reads as a conflict until an answer "
                           "names every one of them in `replaces`")
        else:
            out["note"] = ("recorded as your answer; it marks nothing ready "
                           "and wakes nobody")
        return out

    if name == "timer":
        """Read a timer block or the time spent on something, or mark a
        timer on the owner's explicit direction.

        `timers.timer_state`, `timers.time_spent` and `timers.mark` do the
        work, as the owner's own routes call them. Without `action` this
        reads (the owner's ledger unless `holder` names another). With one it
        marks the OWNER's timer under this run's Participant, on the request
        THIS RUN carries -- never one the agent names (R1a) -- and with this
        run's execution, so the authority ends with it (R1d). `timers.mark`
        checks the rest. Nothing here starts or stops a timer by itself."""
        from mentis.conversation import responses, timers
        from mentis.conversation.versions import Refused
        from mentis.conversation.owner import _owner
        owner = _owner(cv)
        zone = {"tz": args.get("tz"),
                "utc_offset": args.get("utc_offset") or 0}
        post = str(args.get("post") or "").strip()
        block = str(args.get("block") or "").strip()
        if args.get("about") and not post:
            if args.get("action"):
                raise NotPermitted("time spent is read only; to mark, name "
                                   "the timer's post and block")
            holder = str(args.get("holder") or "").strip() or owner
            if not holder:
                raise NotPermitted("this record names no owner: name whose "
                                   "time to add up in `holder`")
            try:
                return {"ok": True, **timers.time_spent(
                    cv, str(args["about"]), holder, **zone)}
            except Refused as refused:
                raise NotPermitted(refused.refusal.get("error") or "refused")
        if not post or not block:
            raise NotPermitted("name the timer: the post (ent-...) it is in "
                               "and its name=; or, to read time spent, "
                               "`about` alone")
        part = args.get("part") or 0
        root = responses.post_root(cv.corpus, post) \
            if cv.corpus.read([post]) else post
        where = cv.conversation_of(root)
        if not where:
            raise NotPermitted(f"{root!r} is not a post in a Conversation")
        _where(where)
        action = args.get("action")
        try:
            if not action:
                holder = str(args.get("holder") or "").strip() or owner
                if not holder:
                    raise NotPermitted("this record names no owner: name "
                                       "whose timer to read in `holder`")
                return {"ok": True, **timers.timer_state(
                    cv, root, block, holder=holder, part=part, **zone)}
            if not parent or not execution:
                raise NotPermitted(
                    "this execution carries no request, so there is no "
                    "owner's direction to mark a timer on; you start or stop "
                    "a timer only when the owner asked you to")
            replaces = args.get("replaces") or []
            if isinstance(replaces, str):
                replaces = [replaces]
            got = timers.mark(
                cv, root, block, action=action, by=actor, owner=owner,
                part=part, at=args.get("at"), run=args.get("run"),
                replaces=replaces, reason=args.get("reason"),
                direction=parent, execution=execution, written_by=wrote,
                op=args.get("op"),
                act_kw={"execution": execution, "runtime": runtime,
                        "caused_by": parent})
        except Refused as refused:
            raise NotPermitted(refused.refusal.get("error") or "refused")
        return {"ok": True, **got,
                "note": "marked on the owner's timer, under your name, with "
                        "the owner's direction (this run's request) on it"}

    if name == "await_work":
        """Say that the carried work waits on other recorded work.

        Only ever about THIS execution's request, which comes off the grant: a
        worker cannot make somebody else's work wait. What it names is the
        work awaited, and the record decides whether that wait could ever end
        -- see `Conversations.await_work` for what is refused and why.
        """
        awaited = (args.get("expectation") or "").strip()
        if not awaited:
            raise NotPermitted("say which request this work waits on")
        if not parent:
            raise NotPermitted(
                "this execution carries no expectation, so there is no work "
                "to wait")
        try:
            act = cv.await_work(parent, awaited, by=actor,
                                because=args.get("because") or None,
                                execution=execution, runtime=runtime)
        except ValueError as exc:
            raise NotPermitted(str(exc))
        w = cv.awaited_state(awaited)
        return {"ok": True, "awaiting": act, "expectation": parent,
                "awaited": awaited,
                "awaited_carrier": cv.alias(w["carrier"]) if w["carrier"]
                else None,
                # SAYS WHAT IT DELIVERS, NOT WHAT WAS INTENDED. Resumption is
                # relayed from ONE place: the end of a dispatched run of the
                # awaited work (`resume_if_ready`, called in `dispatch`'s
                # finally). A carrier who claims the work met OUTSIDE a run --
                # which is the only way a person can claim it, through the UI --
                # writes `expectation-met` via `_answered_asks`, and nothing
                # relays that to waiters. Nothing polls, so that wait is not
                # resumed by itself at all. Promising otherwise here would have
                # agents end their run relying on a wake-up that never comes.
                "note": "this work resumes by itself when a RUN of that work "
                        "ends having claimed it met -- or, if it is work "
                        "somebody delegated to be handed back, when its run "
                        "ends at all, even to pause; a run of it that was "
                        "recovered or interrupted resumes nothing, and "
                        "continuing is somebody's act. If its carrier claims it "
                        "met outside a run -- a person doing it in the "
                        "interface -- nothing relays that yet, and this work "
                        "waits until somebody continues it. End this run with "
                        "respond, without fulfils; nothing polls",
                "resumes_itself": "only when a run of the awaited work ends"}

    if name == "record_discovered_work":
        """Keep a real piece of side work without pursuing it.

        THE SAME TWO RECORDS EVERY REQUEST ALREADY IS: a Turn saying what the
        work is, and an expectation of it -- UNASSIGNED, which the model already
        treats as a real answer. Caused by the request this run carries, so it
        is findable from the work that found it. Nothing new is stored.

        WHY EVERY RUN MAY DO THIS. It addresses nobody, so it asks nothing of the
        owner; it assigns nobody, and nothing dispatches an unassigned
        expectation, so it launches nothing; it writes only into the
        Conversation this run was dispatched into, so it reaches nowhere new;
        and it is not governed material. Nor can it ever be an authority
        origin: its requester is this run's Participant, and organising
        authority is only granted, and only continued, by the person who made
        the request.
        """
        work = (args.get("work") or "").strip()
        if not work:
            raise NotPermitted("discovered work needs saying what it is")
        if not parent:
            raise NotPermitted(
                "this execution carries no request, so there is nothing for "
                "discovered work to have been discovered under")
        turn = cv.say(here, actor, [text_part(work)], written_by=wrote)
        # FILED WHERE THE WORK THAT FOUND IT IS FILED. The request's own Turn
        # is the package this was discovered under; its Topics are where that
        # package is read, so the finding is filed under them too -- ordinary,
        # append-only filing links. It is NOT made a reply: a reply by the
        # carrier would read as the request having been answered.
        package = cv._act(parent)
        for t in (cv.topics_of(package["turn"])
                  if package and package.get("turn") else ()):
            try:
                cv.assign_topic(turn, t, attributed_to=actor, written_by=wrote)
            except ValueError:
                pass        # a Topic of another Conversation is not this one's
        exp = cv.expect(turn, of=None, kind="result", by=actor,
                        because=args.get("because") or work,
                        caused_by=parent)
        _act("work-discovered", conversation=here, turn=turn, about=[exp],
             because=args.get("because") or work)
        from mentis.operational import pursuit_permitted
        allowed = pursuit_permitted(cv, exp)
        return {"ok": True, "turn": turn, "expectation": exp,
                "assigned": None, "may_pursue": bool(allowed),
                "note": ("kept and unassigned. The owner's follow-up "
                         "permission covers it: it can be picked up with "
                         "delegate(expectation=...) without asking; nothing "
                         "starts unless it is"
                         if allowed else
                         "kept, and pursued by nobody: the owner is asked "
                         "about it when the work it was found under is "
                         "finished, and only what they choose is pursued")}

    if name == "return_artifact":
        """Bytes this execution deliberately handed back.

        THE BYTES ARRIVE, A PATH NEVER DOES. The file was read on the worker's
        side, inside the worker's own directory (`_read_for_return`), and what
        crosses is its bytes and the digest computed there. Nothing on this
        side follows, lists or learns a worker path; `claimed_path` is kept as
        evidence of what the worker said and is never opened.
        """
        import base64
        from mentis import artifacts
        if "bytes_b64" not in args:
            raise NotPermitted(
                "return_artifact carries bytes read on the worker's side; a "
                "path alone is not a return and is never followed here")
        if not parent:
            raise NotPermitted(
                "this execution carries no request, so a returned file would "
                "belong to no work")
        try:
            data = base64.b64decode(args["bytes_b64"], validate=True)
        except ValueError as exc:
            raise NotPermitted(f"the bytes did not arrive intact: {exc}")
        if len(data) > artifacts.MAX_BYTES:
            raise NotPermitted(f"{len(data)} bytes; the cap is "
                               f"{artifacts.MAX_BYTES}")
        out = artifacts.hold(
            surface.corpus, cv, data, act=artifacts.RETURNED, actor=actor,
            source=f"execution:{execution}", door="worker-return",
            claimed_name=args.get("claimed_name"),
            claimed_media_type=args.get("media_type"),
            claimed_path=args.get("claimed_path"),
            claimed_digest=args.get("sha256"),
            execution=execution, runtime=runtime, conversation=here,
            turn=cv.expectation_state(parent)["turn"], caused_by=parent,
            because=args.get("because") or "returned deliberately by the "
                                            "execution",
            written_by=wrote)
        return {"ok": True, "ref": out["admission"], "digest": out["digest"],
                "size": out["size"], "act": out["act"],
                "note": "Mentis now holds these bytes. Refer to the artifact "
                        "by `ref`, not by its path; the path is gone with "
                        "your workspace."}

    if name == "read_artifact":
        """The bytes of an artifact THIS execution may reach.

        Reach is read off the grant and the record -- see
        `mentis.artifacts.reachable`: what the run was offered, and, for work a
        person asked for, what is held in its Conversation unless restricted.
        The act records that bytes were SENT to the execution's tool process
        and why they were reachable; whether the model looked at them is not
        observable here, and nothing claims it.
        """
        from mentis import artifacts
        ref = str(args.get("ref") or "").strip()
        why, why_not = artifacts.reachable(surface.corpus, cv, grant, ref)
        if why is None:
            offered = artifacts.granted(surface.corpus, cv, grant)
            raise NotPermitted(
                f"{ref!r} is not reachable by this execution: {why_not}. "
                f"Offered to it: {offered or 'none'}")
        answer, d = _artifact_bytes(surface, ref, why)
        _act(artifacts.SUPPLIED, conversation=here, about=[ref],
             because="bytes sent to the execution's tool process on request; "
                     "whether they were used is not observed",
             detail={"digest": d["digest"], "size": d["size"],
                     "reachable": why})
        return answer

    if name == "open_topic":
        name_ = (args.get("name") or "").strip()
        if not name_:
            raise NotPermitted("a Topic needs a name")
        # The Conversation is the grant's, so a Topic cannot be opened in one
        # this execution was not dispatched into.
        where_ = _somewhere(args.get("conversation")) if session else here
        tid = cv.open_topic(where_, name_, about=args.get("about") or "",
                            attributed_to=actor, written_by=wrote)
        _act("topic-opened", conversation=where_, about=[tid])
        return {"ok": True, "topic": tid, "conversation": where_}

    if name == "open_conversation":
        name_ = (args.get("name") or "").strip()
        if not name_:
            raise NotPermitted("a Conversation needs a name")
        cid = cv.open_conversation(name_, about=args.get("about") or "",
                                  attributed_to=actor, written_by=wrote)
        cv.join(actor, cid, attributed_to=actor, written_by=wrote)
        # CAUSALITY CROSSES THE BOUNDARY. The act is recorded in the NEW
        # Conversation and still caused by the expectation that led to it, so a
        # reader arriving in either one can get to the other. A new Conversation
        # is where work went, never where its lineage stopped.
        # A hand-started session is in no Conversation (`here` is None): its act
        # names nothing it was opened from, rather than recording [None].
        _act("conversation-opened", conversation=cid, about=[here] if here else [])
        return {"ok": True, "conversation": cid, "opened_from": here}

    if name == "summon_participant":
        alias = (args.get("alias") or "").strip()
        if not alias:
            raise NotPermitted("summoning somebody needs an alias")
        # THE SIGIL IS PART OF THE ALIAS IN THIS RECORD, and stripping it was a
        # real defect: aliases are stored as `@Ada`, so looking up `Ada` found
        # nothing and MINTED A SECOND PARTICIPANT beside the one that was
        # already there. Normalised once, here, so the same name always reaches
        # the same identity whichever form was typed.
        alias = "@" + alias.lstrip("@")
        # IDEMPOTENT ON PURPOSE: the same alias reaches the same durable
        # Participant rather than minting a second one. Creating a DELIBERATE
        # second @Ada is a thing a person does; it is not reachable from here.
        #
        # AND CASE IS NOT A DIFFERENT NAME. `find_participant` matches exactly,
        # so `@ada` minted a second Participant beside `@Ada` -- the same defect
        # the sigil had, one character along. Matched case-insensitively here
        # and the EXISTING spelling is kept, because the record's spelling of
        # somebody's name is not this operation's to change.
        existing = next((p["id"] for p in cv.all_participants()
                         if p["body"]["alias"].lower() == alias.lower()), None)
        # A FORMER ALIAS OR A RESERVED ONE IS REFUSED with what to do instead
        # (`participant_alias_refusal`), and so is an existing Participant
        # still named like a runtime (`refuse_reserved`): nobody is summoned.
        from mentis.conversation.versions import Refused
        try:
            if existing:
                cv.refuse_reserved(existing)
            pid = existing or cv.create_participant(
                alias, about=args.get("about") or "",
                attributed_to=actor, written_by=wrote)
        except Refused as refused:
            raise NotPermitted(refused.refusal["error"]) from None
        conversation = (_somewhere if session else _where)(
            args.get("conversation"))
        cv.join(pid, conversation, attributed_to=actor, written_by=wrote)
        _act("participant-summoned", conversation=conversation, about=[pid],
             detail={"found": bool(existing)})
        return {"ok": True, "participant": pid, "alias": cv.alias(pid),
                "conversation": conversation, "already_existed": bool(existing)}

    if name == RESUME_INTAKE:
        # COORDINATING: the request resumed is not the one this run carries.
        # Not bounded by `_where`, deliberately: it writes no Turn, names
        # nobody and chooses nothing, and the request it resumes is wherever
        # it was asked. Who resumed it is this run, recorded with its
        # execution and the request it was carrying.
        if not may_coordinate(grant):
            raise NotPermitted(
                "resuming a request intake could not assign is coordinating "
                "work this run does not carry, and this run's request was not "
                "granted `coordinate`. Leave it for whoever coordinates.")
        from mentis.web import resume_intake
        dispatches = []
        out = resume_intake(
            cv, str(args.get("expectation") or "").strip(), by=actor,
            execution=execution, runtime=runtime, under=parent,
            enqueue=lambda **kw: dispatches.append(kw))
        return {**out, "dispatches": dispatches}

    if name == "delegate":
        """Hand a piece of this work to somebody, keeping the lineage intact.

        THE CHILD EXPECTATION DOES NOT SATISFY THE PARENT. It is caused by it,
        which is a different relation: the parent stays owed until something
        answers it, and `expectation_state` reports the delegation as a
        delegation rather than as a response.

        THE SPECIALIST AUTHORS ITS OWN RESULT. Nothing here attributes the
        delegated work to the caller: the dispatch posts the reply as the
        specialist, with `written_by` naming the runtime that actually ran it.
        """
        who = (args.get("participant") or "").strip()
        work = (args.get("work") or "").strip()
        if not who or not work:
            raise NotPermitted("a delegation needs a Participant and the work")
        if not parent and not session:
            raise NotPermitted(
                "this execution carries no expectation, so a delegation would "
                "have no request to belong to")
        if not surface.cv._is_kind(who, "participant"):
            raise NotPermitted(f"{who!r} is not a Participant in this record")
        if session and not parent:
            # THE SAME GUARD AS BELOW, FOR A SESSION. It carries no request, so
            # nobody is recorded as having asked -- but a person is driving it,
            # and that is the owner (identified as the baseline identifies
            # them). Handing work to them would run a runtime as them.
            from mentis.bootstrap.baseline import OWNER_ABOUT
            owner = {p["id"] for p in cv.all_participants()
                     if (p.get("body") or {}).get("about") == OWNER_ABOUT}
            if who in owner or who == actor:
                raise NotPermitted(
                    "that is the person driving this session, or the session "
                    "itself. Delegating to them would dispatch a runtime as "
                    "them and record its work as theirs. Ask them directly.")
        # NOT BACK AT THE PERSON WHO ASKED. Found by two reviewers separately:
        # the record draws no human/agent distinction on a Participant -- the
        # body is an alias and a description -- so `delegate` would happily
        # target the requester's own Participant and DISPATCH A RUNTIME AS THEM,
        # recording a start act, a reply Turn and a result attributed to a
        # person. `written_by` naming the runtime was the only thing between
        # that and the record saying the owner did the work.
        #
        # Asking something of the person who asked you is a real need and it
        # already has its own operation, which records it as owed BY them and
        # runs nothing. So this refuses and says which to use.
        # A SESSION CARRIES NO REQUEST, so it is the requester of what it hands
        # on: the child is its own top-level request, owed back to it.
        asked_by = (cv.expectation_state(parent)["requested_by"] if parent
                    else actor)
        if who == asked_by:
            raise NotPermitted(
                "that is the Participant this work was requested by. Delegating "
                "to them would dispatch a runtime as them and record its work as "
                "theirs. A decision is asked with request_decision, and goes "
                "to the owner.")
        # DELEGATING THE WORK THIS RUN CARRIES NEEDS NO AUTHORITY BEYOND IT;
        # COORDINATING OTHER WORK DOES (owner rulings ent-fb17dc421a42,
        # ent-94edb8bc6342 and the revision of F-2 that followed). Every run
        # holds `delegate` (HANDS_OFF) and hands on part of ITS OWN request,
        # with the configuration that delegation needs: who (bringing them
        # into this Conversation if they are not in it), runtime, model,
        # effort and the Turn that decided them, requirements, Persona,
        # governed material, artifacts, reach and a worktree -- each bounded
        # by the ordinary checks below, never by who the run is. The child is
        # always caused by this run's own request.
        #
        # Taking on work that is NOT this run's -- picking up discovered work
        # nobody carries -- is coordination, and takes COORDINATE recorded on
        # the request (`may_coordinate`). An audit of every operation every run
        # holds found nothing else that assigns, re-parents or takes over other
        # work: `request_decision` points only at the owner,
        # `await_work` makes only this work wait, `record_discovered_work`
        # assigns nobody, and every other `delegate` argument describes the
        # child of this request. Checked here, before anything is written,
        # because this is where the delegation is recorded and what it returns
        # is what the door dispatches.
        picked = (args.get("expectation") or "").strip() or None
        coordinates = may_coordinate(grant)
        # PERMITTED PURSUIT. The owner's follow-up permission on the ORIGINAL
        # request lets work under it pursue its own lineage's findings without
        # asking again -- within the generations it allows. It is the owner's
        # grant for exactly this, so it stands in for `coordinate` here and
        # for the owner's selection below; it reaches no other request's
        # findings.
        permitted = None
        if picked and parent:
            from mentis.operational import discovery, pursuit_permitted
            permitted = pursuit_permitted(cv, picked)
            if permitted and (discovery(cv, parent)["origin"]
                              != permitted["origin"]):
                permitted = None
        if picked and not coordinates and not permitted:
            raise NotPermitted(
                "picking up discovered work widens what this run was asked "
                "to do: it takes on work this run does not carry, which is "
                "coordinating, and the request it carries was not granted "
                "`coordinate`. Hand on part of the work you carry "
                "instead -- with whatever runtime, model, effort or "
                "participant it needs -- or leave this recorded for whoever "
                "coordinates the work to pick up")
        # A REQUIREMENT MUST BE SOMETHING A RUNTIME CAN DECLARE. An unknown name
        # is UNKNOWN, unknown satisfies nothing, and so an invented one would
        # deterministically make every runtime ineligible -- a per-delegation
        # denial knob wearing the clothes of a capability. Refused here, in
        # words, rather than becoming a recorded pre-start failure nobody
        # expected.
        from mentis.api.types import Capability
        known = {c.value for c in Capability}
        unknown = [r for r in (args.get("requires") or ()) if r not in known]
        if unknown:
            raise NotPermitted(
                f"{unknown} name no capability any runtime can declare, so "
                f"nothing could ever satisfy them. Known: {sorted(known)}")
        # WHAT THE BRIEF ITSELF SAYS IT NEEDS, by one narrow rule
        # (`dispatch.inferred_requires`: a UI build or browser tests), added
        # to what was stated and recorded as inferred, so it is on the
        # request every run of it reads.
        from mentis.web.dispatch import inferred_requires
        inferred = [r for r in inferred_requires(work)
                    if r not in (args.get("requires") or ())]
        if inferred:
            args = {**args, "requires": [*(args.get("requires") or ()),
                                         *inferred]}
        # WHICH ACTIVITY OF A WORKFLOW THIS IS. Checked for exactly two
        # things: the Workflow is governing material this run was delivered
        # (its grant's `delivered`, the same list `propose_revision` reads),
        # and it has an activity with that key. It is recorded on the child
        # and on the delegation so the work status can READ which activity
        # each child is for. It moves nothing, starts nothing and is not a
        # position.
        #
        # IT DOES PASS ON ITS STEP'S PERSONA AND DISCIPLINES. Owner ruling
        # 2026-10-29: delegated Builders and Reviewers receive their step's
        # Persona and Disciplines. This used to say the label passed nothing
        # on and was nothing more than a label, and children delegated by
        # activity ran with no Persona and no Discipline unless the carrier
        # named them by hand. Now, what the caller leaves unsaid is filled
        # from the activity at the current standing versions
        # (`_activity_supplies`), and what the caller says wins: an explicit
        # `persona` replaces the activity's; a `governed` list is joined by
        # the activity's Disciplines; an explicit `[]` means none. Where each
        # came from is recorded on the delegation (`persona_from`,
        # `governed_from`). Who may delegate, grants and authority are
        # untouched: this changes what the child is given, not who may give.
        # Resolved BEFORE the checks below, so what the activity supplies is
        # checked exactly as what a caller names is.
        activity = _activity_label(surface, grant, args.get("activity"))
        supplied = _activity_supplies(surface, activity) if activity else None
        persona = args.get("persona") or None
        persona_from = "caller" if persona else None
        persona_unresolved = None
        if supplied and not persona:
            persona = supplied["persona"]
            persona_from = "activity" if persona else None
            persona_unresolved = supplied["persona_why"]
        if persona:
            # AN ESTABLISHED PERSONA OR NONE. Delegating with material nobody
            # established would be governing by delegation, which is exactly
            # the establishment power this scope does not carry.
            if not surface.cv._is_kind(persona, "persona"):
                raise NotPermitted(f"{persona!r} is not a Persona")
            if not surface.corpus.stands(persona)["stands"]:
                raise NotPermitted(
                    f"Persona {persona!r} does not stand, so it cannot be "
                    f"delegated with; propose material and let a person "
                    f"establish it")
        # THE GOVERNED MATERIAL THIS DELEGATION SAYS APPLIES, BY REFERENCE.
        # Checked only for being a durable reference the record holds, because
        # that is the one thing that cannot be checked later: whether it STANDS
        # is asked at delivery by the composer, which withholds a superseded or
        # unestablished item with the reason -- and asking here instead would
        # resolve standing at assignment time and deliver whatever the answer
        # was then. Nothing is filtered by Kind: what ladder an item comes up
        # is read from its Kind's own declaration when it is composed.
        #
        # PRESENCE, NOT TRUTHINESS, AND IT HAS TO SURVIVE THIS LINE. `None` is
        # the caller saying nothing about what governs the work; `[]` is the
        # caller saying NOTHING governs it any more. This normalisation used to
        # be `(args.get("governed") or ())`, which made both of them the empty
        # list before either write site below could tell them apart -- so the
        # presence-sensitive reader in `dispatch` could never observe an
        # explicit clear, whatever a caller sent. Found by independent review
        # at the production door, after a test proved the reader by writing the
        # assignment act directly and bypassing it.
        _named = args.get("governed")
        governed = (None if _named is None
                    else [str(g) for g in _named if g])
        # THE ACTIVITY'S DISCIPLINES, BY THE SAME PRESENCE RULE: absent ->
        # the activity's; a list -> that list and then the activity's, order
        # kept and nothing twice; `[]` -> none, as the caller said.
        governed_from = None
        if supplied:
            if _named is None:
                if supplied["disciplines"]:
                    governed = list(supplied["disciplines"])
                    governed_from = "activity"
            elif not governed:
                governed_from = "caller"
            else:
                added = [d for d in supplied["disciplines"]
                         if d not in governed]
                governed = [*governed, *added]
                governed_from = "caller and activity" if added else "caller"
        for ref in governed or ():
            if not surface.corpus.read([ref]):
                raise NotPermitted(
                    f"{ref!r} is not something this record holds, so it cannot "
                    f"be named as governing the work")
        # DELETED MATERIAL IS NOT NAMED AS GOVERNING NEW WORK. Naming it here
        # selects it for new forward use; that it would not stand when the run
        # composes is no reason to accept the naming now. See
        # `mentis.conversation.versions`, INERT GOING FORWARD.
        from mentis.conversation.versions import inert_refusal
        refusal = inert_refusal(surface.corpus, *(governed or ()))
        if refusal:
            raise NotPermitted(
                f"{refusal['entry']!r} cannot be named as governing the work: "
                f"{refusal['error']}")
        # A PROCEDURE IS NOT HANDED TO A CHILD. Material whose Kind declares an
        # `activities` input (a Workflow) is carried by the request it was
        # named for; a child is given its activity's Disciplines instead, as
        # the delivered procedure says. Asked of the declaration, not a name.
        from mentis.conversation import ROW_GROUP, fields_with_input
        for ref in governed or ():
            got = surface.corpus.read([ref])
            kind = (got[0].get("definition") or {}).get("name") if got else None
            if kind and fields_with_input(surface.corpus, kind, ROW_GROUP):
                raise NotPermitted(
                    f"{ref!r} is a procedure with activities; it is carried by "
                    f"the work it was named for, not handed on. Delegate one "
                    f"activity with `activity: \"{ref}#<key>\"`; that "
                    f"activity's Persona and Disciplines go with it")
        # WHERE THE PERSONA AND DISCIPLINES CAME FROM, recorded on the
        # delegation and said in the result -- only for a delegation by
        # activity, so one without an activity is recorded exactly as before.
        provenance = ({"persona_from": persona_from,
                       "governed_from": governed_from,
                       **({"persona_unresolved": persona_unresolved}
                          if persona_unresolved and not persona else {}),
                       **({"disciplines_withheld": supplied["withheld"]}
                          if supplied["withheld"] and _named != [] else {})}
                      if supplied else {})
        # EXECUTION CONSTRAINTS, CARRIED AS CONSTRAINTS. The owner may decide
        # which runtime or model a piece of work runs on, and a coordinator
        # that could not pass that on would record the decision and discard it.
        # They reach Foundation's ordinary selection exactly as the owner's own
        # dispatch does: a constraint narrows or refuses, and is never ranked,
        # tiered or quietly swapped for something that happens to be available.
        # WHO supplied them, and on what basis, is kept beside them, apart from
        # what Foundation later selects and what the run is observed to be.
        # FILES GO WITH THE WORK AS ORDINARY PARTS OF THE TURN THAT ASKS FOR
        # IT, so the child's grant -- what its request was made with -- covers
        # them without a second mechanism. Only artifacts this execution may
        # read itself: handing on is not a way to reach bytes one was not given.
        handed = list(dict.fromkeys(str(r).strip()
                                    for r in (args.get("artifacts") or ())
                                    if str(r).strip()))
        handed_parts = []
        if handed:
            from mentis import artifacts
            for ref in handed:
                ok, why_not = artifacts.reachable(surface.corpus, cv, grant,
                                                  ref)
                if ok is None:
                    raise NotPermitted(
                        f"{ref!r} is not reachable by this execution ({why_not}), "
                        f"so it cannot hand it on")
                st = artifacts.describe(surface.corpus, ref,
                                        verify=False)["state"]
                if st != "held":
                    raise NotPermitted(f"{ref!r} is {st}; there are no bytes "
                                       "to hand on")
            handed_parts = [artifacts.part(r, corpus=surface.corpus)
                            for r in handed]
        # A REPOSITORY DIRECTORY FOR THE CHILD, declared and never inferred:
        # where its run works (`dispatch.declared_workspace`). A path names
        # the directory; `true` is the one this work declared. Mentis cuts no
        # worktree and commits nothing: Git is the requester's and the
        # agent's. Part of configuring the delegation of the work this run
        # carries, so it takes no `coordinate`. The same declaration goes with
        # discovered work a coordinating run picks up: it is recorded on the
        # pick-up, which is where `dispatch.declared` reads it.
        from mentis.web.dispatch import declared as _declared
        repository = None
        if args.get("repository"):
            named = args["repository"]
            if isinstance(named, str):
                named = named.strip()
                if not os.path.isabs(named):
                    raise NotPermitted(
                        f"{named!r} is not an absolute directory for the "
                        "child to work in")
                repository = {"path": os.path.normpath(named)}
            else:
                mine = _declared(cv, parent) if parent else None
                path = (mine if isinstance(mine, str) else
                        mine.get("path") if isinstance(mine, dict) else None)
                if not path:
                    raise NotPermitted(
                        "this work declares no repository directory, so a "
                        "child cannot be given the same one. Name the "
                        "directory instead (repository: \"C:/path/to/repo\").")
                repository = {"path": path}
        # A REVIEW NAMES THE WORK IT REVIEWS: a request of this work's own
        # lineage -- this work, or work it delegated -- and works in the
        # directory that work declared, if it declared one. Which runtime
        # authored it is read from that request's runs (`review_signal`).
        reviewed = str(args.get("review_of") or "").strip() or None
        if reviewed:
            if repository:
                raise NotPermitted(
                    "name either `repository` or `review_of`, not both")
            mine = reviewed == parent or (
                (cv._act(reviewed) or {}).get("caused_by") == parent
                and parent is not None)
            if not mine:
                raise NotPermitted(
                    f"{reviewed!r} is neither this work nor work it "
                    "delegated, so it is not this run's to hand to a review")
            theirs = _declared(cv, reviewed)
            path = (theirs if isinstance(theirs, str) else
                    theirs.get("path") if isinstance(theirs, dict) else None)
            repository = {"review_of": reviewed, **({"path": path} if path else {})}
        # HOW FAR THE CHILD REACHES. Bounded by default: it receives what this
        # delegation hands it. Widening it to the Conversation is explicit,
        # and only work that reaches the Conversation itself can pass that on.
        reach = (str(args.get("reach") or "").strip() or None)
        if reach not in (None, "work", "conversation"):
            raise NotPermitted(f"reach is 'work' or 'conversation', not "
                               f"{reach!r}")
        if reach == "conversation":
            from mentis import artifacts
            if (not parent or artifacts.reach_of(cv, parent)["reach"]
                    != "conversation"):
                raise NotPermitted(
                    "this work does not reach its Conversation, so it cannot "
                    "give a child that reach")
        constraints = {k: (str(args.get(k) or "").strip() or None)
                       for k in ("runtime", "model", "effort")}

        def _child_conversation(picked):
            """The Conversation the child will run in, asked exactly as the
            write below asks it, or None when that would be refused -- the
            refusal itself is the write's to give, in its own words."""
            try:
                if picked:
                    return _where(cv.expectation_state(picked)["conversation"])
                return (_somewhere if session else _where)(
                    args.get("conversation"))
            except (NotPermitted, ValueError):
                return None
        basis = (str(args.get("constraint_basis") or "").strip() or None)
        if basis:
            said = surface.corpus.read([basis])
            if (not said or not surface.cv._is_kind(basis, "contribution")
                    or said[0]["attributed_to"] != asked_by):
                raise NotPermitted(
                    f"{basis!r} is not a Turn by the person who asked for this "
                    f"work, so it cannot be the basis of a constraint on it")
            refusal = inert_refusal(surface.corpus, basis)
            if refusal:
                raise NotPermitted(
                    f"{basis!r} cannot be the basis of a constraint on new "
                    f"work: {refusal['error']}")
        # A DECLARED DEFAULT IS A CONSTRAINT TOO, resolved here so it is on
        # the child's request from the start -- visible before anything runs,
        # and what every later run of it reads. Never derived from the name.
        from mentis.web.dispatch import (review_conflict, review_signal_of,
                                         resolve_runtime, yield_to_review)
        # WHOSE RUNTIME A REVIEW WOULD AVOID, read as its run will read it
        # (`review_signal`): the Persona it wears and the work it reviews.
        _, author, _ = review_signal_of(cv, persona, repository)
        warnings = []
        if not constraints["runtime"]:
            # A PREFERENCE, judged here as on every other path: a default
            # whose runtime could not take this work now is not recorded --
            # judged against EVERYTHING the child's run will require, not
            # only what this call stated (`_delegated_requires`).
            declared = resolve_runtime(
                cv, participant=who,
                judge=_delegated_judge(
                    surface, cv, args, model=constraints["model"],
                    conversation=_child_conversation(picked),
                    governed=governed, persona=persona))
            # AND IT GIVES WAY TO INDEPENDENT REVIEW: a default that is the
            # reviewed work's runtime is not recorded (`yield_to_review`).
            declared = yield_to_review(declared, author)
            if declared["runtime"]:
                constraints["runtime"] = declared["runtime"]
                source = declared
            else:
                source = None
        else:
            source = {"source": "named"}
            # A NAMED RUNTIME STAYS AS NAMED; if it is the reviewed work's
            # runtime, the carrier is told so here and the run's record says it.
            conflict = review_conflict(
                {"runtime": constraints["runtime"], "source": "named"}, author)
            if conflict:
                warnings.append(conflict)
            # AND IF IT IS KNOWN TO BE EXHAUSTED, the carrier is told before it
            # runs: a named runtime is never substituted, so this is the one
            # place the carrier can still choose otherwise (owner, 2026-10-29).
            judge = _delegated_judge(
                surface, cv, args, model=constraints["model"],
                conversation=_child_conversation(picked),
                governed=governed, persona=persona)
            why_not = judge(constraints["runtime"]) if judge else None
            if why_not:
                warnings.append(f"the named runtime {constraints['runtime']} "
                                f"cannot take this work now ({why_not}); it is "
                                f"kept because it was named")
        constrained = ({**constraints,
                        "requires": list(args.get("requires") or ()),
                        "supplied_by": actor, "basis": basis,
                        **({"source": source["source"]} if source else {}),
                        **({"declaration": source["declaration"]}
                           if source and source.get("declaration") else {})}
                       if any(constraints.values()) else None)

        # Picking up discovered work is coordinating: refused above without
        # `coordinate` (`may_coordinate`), as it was without `delegate` on
        # 4a5cbc8.
        if picked:
            # PICKING UP DISCOVERED WORK, AS ITSELF. Assigned where it stands, so
            # it keeps its identity, the Turn that described it, who found it
            # and under what -- rather than being written again as though it
            # had just been thought of. Only discovered work: an unassigned
            # request somebody made is not this run's to hand out.
            try:
                state = cv.expectation_state(picked)
            except ValueError:
                raise NotPermitted(f"{picked!r} is not a request in this record")
            found = [a for a in cv.history(turn=state["turn"])
                     if a["act"] == "work-discovered"
                     and picked in (a["about"] or ())]
            if not found:
                raise NotPermitted(
                    f"{picked!r} is not discovered work in this record")
            if not state["unassigned"]:
                raise NotPermitted(
                    f"{picked!r} is already carried; picking it up again would "
                    f"take it from whoever has it")
            # ONLY WHAT THE OWNER CHOSE TO PURSUE. Coordinating is authority to
            # organise work, not to decide that side work is worth doing: that
            # is the owner's, answered in the reconsideration they are asked
            # once the work it was found under is finished. Before then, or if
            # they kept it deferred or dismissed it, nobody picks it up.
            from mentis.operational import owner_selected
            if not permitted and not owner_selected(cv, picked):
                raise NotPermitted(
                    f"{picked!r} is a finding the owner has not chosen to "
                    f"pursue, and their follow-up permission does not cover "
                    f"it. It stays recorded; the owner is asked about it once "
                    f"the work it was found under is finished")
            conversation = _where(state["conversation"])
            # ONE CLAIM. Asked again and written in one transaction, so of two
            # pick-ups at once -- or a retry -- exactly one assigns it and is
            # handed a dispatch; the other is refused with nothing written.
            with surface.corpus.atomic():
                if cv.assigned_carrier(picked)["carrier"] is not None:
                    raise NotPermitted(
                        f"{picked!r} is already carried; picking it up again "
                        f"would take it from whoever has it")
                # AND THE OWNER HAS NOT SINCE SAID OTHERWISE: asked again
                # inside the claim, so an offer or answer written meanwhile
                # is never run over by permission (found by review).
                if permitted:
                    from mentis.operational import owner_decided
                    said = owner_decided(cv, picked)
                    if said:
                        raise NotPermitted(
                            f"{picked!r} is {said}; follow-up permission does "
                            f"not override the owner")
                cv.join(who, conversation, attributed_to=actor, written_by=wrote)
                turn = cv.say(conversation, actor,
                              [text_part(work)] + handed_parts,
                              addressed_to=[who], replies_to=state["turn"],
                              written_by=wrote)
                cv.assign(picked, who, by=actor,
                          because=args.get("because") or "picked up discovered work",
                          detail={"picked_up_under": parent, "execution": execution,
                                  **({"reach": reach} if reach else {}),
                                  # WHERE PICKED-UP WORK'S REPOSITORY IS DECLARED:
                                  # its own record is never rewritten, so the
                                  # pick-up says it, and `dispatch.declared`
                                  # reads the latest pick-up as for reach.
                                  **({"repository": repository}
                                     if repository else {}),
                                  # PRESENT MEANS ANSWERED, and `[]` is an answer:
                                  # picking work up is where a carrier says what it
                                  # is taking it on under, including nothing.
                                  **({"governed": governed}
                                     if governed is not None else {}),
                                  **({"activity": activity}
                                     if activity else {})})
                if args.get("restricted"):
                    from mentis import artifacts
                    artifacts.restrict(cv, picked, by=actor,
                                       because=str(args.get("restricted_because")
                                                   or "restricted by its "
                                                      "delegation"))
                act = _act("work-delegated", conversation=conversation, turn=turn,
                           about=[picked],
                           detail={"participant": who, "persona": persona,
                                   "picked_up": True,
                                   **({"activity": activity}
                                      if activity else {}),
                                   **provenance,
                                   "artifacts": handed, "reach": reach or "work",
                                   "restricted": bool(args.get("restricted")),
                                   "constraints": constrained,
                                   "requires": list(args.get("requires") or ()),
                                   "return_expected": bool(args.get("return_to_me"))})
                return {"ok": True, "turn": turn, "expectation": picked,
                        "delegation": act, "conversation": conversation,
                        "parent_expectation": parent, "picked_up": True,
                        **provenance,
                        **({"warnings": warnings} if warnings else {}),
                        "dispatch": {"participant": who, "persona": persona,
                                     "requires": list(args.get("requires") or ()),
                                     "work": work, **constraints,
                                     # the result answers the work as discovered
                                     "turn": state["turn"]},
                        "note": "the same expectation, now assigned; the parent is "
                                "NOT satisfied by this"}
        conversation = (_somewhere if session else _where)(
            args.get("conversation"))
        cv.join(who, conversation, attributed_to=actor, written_by=wrote)
        turn = cv.say(conversation, actor, [text_part(work)] + handed_parts,
                      addressed_to=[who], written_by=wrote)
        for t in args.get("topics") or ():
            try:
                cv.assign_topic(turn, t, attributed_to=actor, written_by=wrote)
            except ValueError:
                pass            # a Topic of another Conversation is not a silo
        child = cv.expect(turn, of=who, kind=args.get("expects") or "result",
                          by=actor, because=args.get("because") or None,
                          caused_by=parent,
                          requires=args.get("requires") or (),
                          detail={"returns_to": actor if args.get("return_to_me")
                                  else None,
                                  **({"reach": reach} if reach else {}),
                                  **({"repository": repository}
                                     if repository else {}),
                                  **({"constraints": constrained}
                                     if constrained else {}),
                                  # REFERENCES ON THE REQUEST, not prose. The
                                  # child's run reads them from here, so what
                                  # it is told is whatever stands when it runs.
                                  # PRESENT MEANS ANSWERED: `[]` says this
                                  # child is governed by nothing, which is not
                                  # the same as saying nothing about it.
                                  **({"governed": governed}
                                     if governed is not None else {}),
                                  # WHICH ACTIVITY IT IS FOR: a label the work
                                  # status reads, never a position.
                                  **({"activity": activity}
                                     if activity else {})})
        if args.get("restricted"):
            from mentis import artifacts
            artifacts.restrict(cv, child, by=actor,
                               because=str(args.get("restricted_because")
                                           or "restricted by its delegation"))
        act = _act("work-delegated", conversation=conversation, turn=turn,
                   about=[child],
                   detail={"participant": who, "persona": persona,
                           **({"activity": activity} if activity else {}),
                           **provenance,
                           "artifacts": handed, "reach": reach or "work",
                           "restricted": bool(args.get("restricted")),
                           "constraints": constrained,
                           **({"requires_inferred": inferred}
                              if inferred else {}),
                           "return_expected": bool(args.get("return_to_me"))})
        return {"ok": True, "turn": turn, "expectation": child,
                "delegation": act, "conversation": conversation,
                "parent_expectation": parent,
                **provenance,
                **({"warnings": warnings} if warnings else {}),
                "dispatch": {"participant": who, "persona": persona,
                             "requires": list(args.get("requires") or ()),
                             "work": work, **constraints},
                "note": "the parent expectation is NOT satisfied by this"}

    if name in LADDER_ACTS + ("propose_material", "propose_revision"):
        from mentis.conversation import ladder_writes as ladder
        on = cv.expectation_state(parent)["turn"] if parent else None
        context = {"conversation": here, "turn": on, "execution": execution,
                   "runtime": runtime, "caused_by": parent}
        try:
            with surface.corpus.atomic():
                if name in ("record_material", "propose_material"):
                    result = ladder.record(cv, kind=args.get("kind"), body=args.get("body"),
                        basis=args.get("basis") or [], outcome_of=args.get("outcome_of"),
                        in_context=args.get("in_context"), by=actor, writer=wrote, context=context,
                        persona=grant.get("persona"))
                    if name == "propose_material" and ladder.adoptable(
                            surface.corpus, surface.corpus.read([result["entry"]])[0]):
                        requested = ladder.request(cv, entry=result["entry"], by=actor,
                            because=args.get("because") or "proposed for owner adoption",
                            writer=wrote, context=context, persona=grant.get("persona"))
                        result.update(requested)
                    elif name == "propose_material":
                        result.update(request=None, request_why_not=(
                            "recorded as evidence; " + ladder.NOT_ADOPTABLE))
                    return result
                if name == "withdraw_challenge":
                    return ladder.withdraw(cv, dispute=args.get("dispute"),
                        because=args.get("because"), by=actor, writer=wrote,
                        context=context, persona=grant.get("persona"))
                if name == "challenge":
                    return ladder.challenge(cv, target=args.get("target"),
                        because=args.get("because"), evidence=args.get("evidence") or [],
                        by=actor, writer=wrote, context=context,
                        persona=grant.get("persona"))
                # ONE GATE FOR BOTH DOORS to a successor: a revision (`of`) and
                # recorded material put forward with `replaces`. A dispatched
                # run proposes successors to what it was delivered; a
                # hand-started session carries no delivery, and may propose a
                # successor to any material it can read -- proposing
                # displaces nothing, and adopting is the owner's.
                if grant.get("scope") != SESSION_SCOPE:
                    named = [args["of"]] if args.get("of") else []
                    named += [r for r in (args.get("replaces") or []) if isinstance(r, str)]
                    undelivered = [r for r in named if r not in (grant.get("delivered") or [])]
                    if undelivered:
                        raise ValueError(f"{undelivered[0]!r} was not delivered to this run; "
                                         "a dispatched run proposes successors to material "
                                         "it was delivered")
                result = ladder.request(cv, entry=args.get("entry"), of=args.get("of"),
                    body=args.get("body"), scope=args.get("scope"), replaces=args.get("replaces"),
                    because=args.get("because"), by=actor, writer=wrote, context=context,
                    persona=grant.get("persona"))
                if args.get("of"):
                    result.update(revision_of=args["of"], of_stands=surface.corpus.stands(args["of"])["stands"])
                evidence = []
                for one in args.get("supports_with") or []:
                    if not isinstance(one, dict) or one.get("relation", "supports") not in ("supports", "outcome-of"):
                        raise ValueError("revision evidence uses supports or outcome-of")
                    rel = one.get("relation", "supports")
                    target = args.get("of") if rel == "outcome-of" else result["entry"]
                    recorded = ladder.record(cv, kind=one.get("kind"), body=one.get("body"),
                        basis=[args["of"]], outcome_of=target if rel == "outcome-of" else None,
                        in_context=on or here, by=actor, writer=wrote, context=context,
                        persona=grant.get("persona"))
                    if rel == "supports":
                        ladder.edge(surface.corpus, recorded["entry"], target, rel,
                                    by=actor, writer=wrote, body={"reason": args.get("because")})
                    evidence.append({"entry": recorded["entry"], "kind": one.get("kind"),
                                     "relation": rel, "to": target})
                result["evidence"] = evidence
                return result
        except ValueError as exc:
            raise NotPermitted(str(exc))

    if name in INTERACTS or name == DEEP_DIVE:
        """Anchor, react, dive: `mentis.conversation.anchors`, as the owner's
        own routes call it. Who acts, and in which execution, come off the
        grant; where it may act is `_where`."""
        from mentis.conversation import anchors
        from mentis.conversation.versions import Refused
        act_kw = {"execution": execution, "runtime": runtime,
                  "caused_by": parent}
        try:
            if name == "anchor":
                return {"ok": True, **anchors.create_anchor(
                    cv, args, by=actor, written_by=wrote,
                    may_act_in=_where, act_kw=act_kw)}
            aid = str(args.get("anchor") or "")
            if name == "react":
                return {"ok": True, **anchors.react(
                    cv, aid, args, by=actor, written_by=wrote,
                    may_act_in=_where, act_kw=act_kw)}
            got = anchors.deep_dive(cv, aid, args, by=actor, written_by=wrote,
                                    may_act_in=_where, act_kw=act_kw)
            return {"ok": True, **got,
                    "note": "a fresh Conversation: nothing of the one the "
                            "anchor is in was carried into it. Its origin is "
                            "the anchor and your reason."}
        except Refused as refused:
            raise NotPermitted(refused.refusal.get("error") or "refused")

    if name == "respond":
        """Answer the request this execution is carrying.

        `parts` RATHER THAN A STRING, and that is not a convenience. A
        contribution is structurally a LIST of content parts, so an answer may
        be prose, or references to work done elsewhere, or both -- and a later
        reader composing a view of this result is reading the same parts. Text
        is the ordinary case and not the only possible one.

        Fulfilment is a SEPARATE act from the reply, and it cites what answers
        the request. A reply existing is not proof the work succeeded; saying so
        is a claim, and it is recorded as this execution's claim rather than as
        the record's own verdict.
        """
        parts = args.get("parts")
        if not parts:
            said = (args.get("text") or "").strip()
            if not said:
                raise NotPermitted("a response needs something to say")
            parts = [text_part(said)]
        if not parent:
            raise NotPermitted("this execution carries no expectation to answer")
        # WORK WAITING ON AN UNANSWERED DECISION IS NOT ANSWERED WORK, and the
        # record must not be able to say both at once. Asked BEFORE anything is
        # written, so a refusal records nothing -- not the reply, not the act.
        #
        # WHAT THIS IS FOR, in one sentence the caller can act on: marking the
        # work met is what makes it unanswerable later. `expectation-met` is
        # append-only and nothing withdraws it, and both continuation paths --
        # `continuation_candidates`, which the owner's "decide and continue"
        # uses, and `claim_resumption` -- exclude satisfied work by design. So a
        # carrier that asked the owner a question and then claimed its work was
        # done left the owner's own answer with nothing it could continue. That
        # happened: the request was closed 22 seconds after the question was
        # asked and 2m44s before the answer arrived, and the answer dispatched
        # a run with no organising authority at all.
        #
        # `waiting_on` IS THE ONE WAITING MODEL and this adds no second one: it
        # already computes which decisions raised under this work are
        # unanswered, for the resumption path, and this asks it the same
        # question. Only decisions block -- a child still running does not,
        # because a carrier may legitimately finish while work it handed out
        # continues.
        if args.get("fulfils"):
            unanswered = [d for d in cv.waiting_on(parent)["decisions"]
                          if not d["answered"]]
            if unanswered:
                asked = ", ".join(d["expectation"] for d in unanswered)
                raise NotPermitted(
                    f"this work is waiting on a decision you asked for and "
                    f"nobody has answered yet ({asked}), so it cannot be "
                    f"recorded as answered. Marking it met is what stops the "
                    f"answer continuing it: nothing withdraws that, and the "
                    f"paths that carry work on from an answer pass over work "
                    f"already claimed done. Respond WITHOUT `fulfils` to say "
                    f"where things stand and leave the request open.")
            # AND INPUT IT SAID IT WAITS FOR, by the same rule: claimed met,
            # the owner's Done would have nothing to resume.
            waiting = [i for i in cv.waiting_on(parent)["inputs"]
                       if not i["answered"]]
            if waiting:
                asked = ", ".join(i["expectation"] for i in waiting)
                raise NotPermitted(
                    f"this work is waiting for input you asked for and the "
                    f"owner has not marked it ready yet ({asked}), so it "
                    f"cannot be recorded as answered: marking it met is what "
                    f"stops their Done resuming it. Respond WITHOUT "
                    f"`fulfils` to say where things stand and leave the "
                    f"request open.")
        # A REPLY IS NOT A WAY TO REACH BYTES (found by review): an artifact
        # part names only what this execution may read itself, exactly as
        # handing one on through `delegate` does.
        from mentis import artifacts
        for p in parts:
            ref = p.get("ref") if isinstance(p, dict) else None
            if ref and str(ref).startswith("adm-"):
                ok, why_not = artifacts.reachable(surface.corpus, cv, grant,
                                                  ref)
                if ok is None:
                    raise NotPermitted(
                        f"{ref!r} is not reachable by this execution "
                        f"({why_not}), so a reply cannot carry it")
        # NOTHING NEW IS BUILT ON DELETED MATERIAL, from here any more than
        # from the owner's own Turn route: a `turn` part names what this answer
        # rests on, and `results` name what answers the request -- both chosen
        # by this caller, now, as support. Asked before anything is written.
        #
        # THE REQUEST'S OWN TURN IS NOT ASKED. The reply below is linked to it,
        # but nobody chose it: it is read from the record of work that already
        # existed, and answering that work records its completion. Deleting a
        # request does not withdraw the work it caused; whether it should is
        # undecided, and is not decided here.
        from mentis.conversation.versions import inert_refusal
        refusal = inert_refusal(
            surface.corpus,
            *[p.get("ref") for p in parts if isinstance(p, dict)
              and p.get("type") == "turn"],
            *[str(r) for r in (args.get("results") or ()) if r])
        if refusal:
            raise NotPermitted(
                f"{refusal['entry']!r} cannot be cited by a reply: "
                f"{refusal['error']}")
        # AN OBJECT REFERENCE, by the rule the owner's door asks
        # (`objectref.refusal`): a post that stands, the object at the
        # version named, by the same key. It names; it reaches nothing.
        from mentis.conversation import objectref
        refused_object = objectref.refusal(surface.corpus, parts)
        if refused_object:
            raise NotPermitted(
                f"this reply cannot carry that object reference (part "
                f"{refused_object['part']}): {refused_object['error']}")
        exp = cv.expectation_state(parent)
        # AN ANCHORED ANSWER answers a passage of the request's own Turn, by
        # the one rule every Turn write asks (`anchors.check_parts`). Choosing
        # a passage of a deleted request is new use and refused, though
        # answering the request is not.
        from mentis.conversation import anchors
        from mentis.conversation.versions import Refused
        try:
            anchors.check_parts(cv, here, parts, exp["turn"])
        except Refused as refused:
            raise NotPermitted(
                f"this reply cannot carry that anchor: "
                f"{refused.refusal.get('error')}")
        turn = cv.say(here, actor, list(parts), replies_to=exp["turn"],
                      written_by=wrote)
        # THE DURABLE FACT THE COMPLETION BOUNDARY READS, recorded for EVERY
        # response and not only a claimed one. Dispatch has to decide at exit
        # whether this execution already answered the request it carried, and
        # it must decide that from the record rather than by reading prose. An
        # answer given without `fulfils` used to leave no act naming its Turn at
        # all, so the only trace was the words themselves -- and dispatch, which
        # cannot read words, composed a second answer beside this one. That is
        # the 38 double responses in the record. `answers_request` names the
        # expectation, so a reply to a DIFFERENT request on the same execution
        # is not mistaken for this one.
        # NO RUNTIME ON IT, DELIBERATELY, AND NOT THROUGH `_act`. The
        # interface keys a provider/model badge off an act's `runtime` and says
        # in its own words that a `turn-said` carries none and must not pretend
        # to (`ui/src/surfaces/Provenance.tsx`). Recorded through `_act` this
        # would have carried `runtime` and no model, and every agent response
        # would have grown a manufactured `provider unknown` badge. What ran is
        # already recorded, on the acts whose business that is.
        said_act = cv.record_act(
            actor=actor, act="turn-said", execution=execution,
            caused_by=parent, conversation=here, turn=turn,
            because="this execution's answer to the request it carries",
            detail={"answers_request": parent, "answers_turn": exp["turn"]})
        out = {"ok": True, "turn": turn, "expectation": parent,
               "said_act": said_act}
        # THIS IS THE RUN'S ANSWER POST, so a decision form it asked with no
        # `on` goes on it now (P7), and stops being shown in Needs You only.
        attached = cv.attach_pending_forms(execution, turn, by=actor)
        if attached:
            out["decision_forms"] = attached
        if args.get("fulfils"):
            met = _act("expectation-met", conversation=here, turn=turn,
                       about=[turn] + list(args.get("results") or ()),
                       because=args.get("because")
                       or "answered by this execution",
                       detail={"claimed_by": execution,
                               # WHAT THE RESULT IS, so that something rendering
                               # it later need not guess from the prose. A label
                               # the responder supplies; it is not a Kind, it
                               # creates nothing, and nothing branches on it.
                               "result_kind": args.get("result_kind")})
            out["fulfilled_by"] = met
            out["note"] = ("recorded as this execution's claim that the request "
                           "is answered, not as verified work")
        else:
            out["note"] = ("a reply; the expectation is left open because "
                           "nothing claimed it was met")
        return out

    raise KeyError(name)


def _read_for_return(args: dict, workroot: str, also=()) -> dict:
    """Read ONE file for `return_artifact`, on the worker's side, or refuse.

    THE ONE PLACE A FILE IS READ, and it is read here -- in the worker's own
    process, from inside the directory it was started in -- so that what
    crosses to the owner is bytes and a digest, never a path to be followed.
    A path that resolves outside that directory (`..`, an absolute path, a
    link) is refused before anything is opened.

    `also` is the project this run was given, where it has one: a file made
    there may be returned too, because the project is intentionally shared.
    Nothing else is -- in particular not another execution's scratch.
    """
    import base64
    import hashlib
    import os
    from mentis.spine.held import MAX_BYTES
    asked = str(args.get("path") or "")
    if not asked:
        raise NotPermitted("return_artifact needs the path of a file")
    real = os.path.realpath(os.path.join(workroot, asked))

    def under(root):
        try:
            return os.path.commonpath([real, root]) == root
        except ValueError:                  # another drive, on Windows
            return False
    if not any(under(r) for r in (workroot, *also) if r):
        raise NotPermitted(f"{asked!r} is outside this worker's directory "
                           f"({workroot}"
                           + (f" and the project {also[0]}" if also else "")
                           + "); only files made there can be returned")
    if not os.path.isfile(real):
        raise NotPermitted(f"{asked!r} is not a regular file")
    size = os.path.getsize(real)
    if size > MAX_BYTES:
        raise NotPermitted(f"{asked!r} is {size} bytes; the cap is {MAX_BYTES}")
    with open(real, "rb") as fh:
        data = fh.read(MAX_BYTES + 1)
    return {"claimed_path": real, "claimed_name": os.path.basename(real),
            "media_type": args.get("media_type"), "because": args.get("because"),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes_b64": base64.b64encode(data).decode("ascii")}


def _materialise(got: dict, workroot: str) -> tuple[dict, bytes]:
    """Write supplied bytes into the worker's directory, named by digest and
    by the view Mentis chose -- never by the sender's filename, which is
    metadata and could be `../../anything`. Returns what to tell the worker,
    and the bytes. Nothing on the owner's side learns or touches this path.
    """
    import base64
    import hashlib
    import os
    data = base64.b64decode(got["bytes_b64"])
    if hashlib.sha256(data).hexdigest() != got["digest"]:
        raise ValueError("the bytes that arrived do not match their digest")
    where = os.path.join(workroot, ".mentis-artifacts")
    os.makedirs(where, exist_ok=True)
    path = os.path.join(where, got["digest"][:16] + got["ext"])
    with open(path, "wb") as fh:
        fh.write(data)
    meta = {k: got.get(k) for k in ("ref", "digest", "size", "view",
                                    "served_as", "name_metadata", "door",
                                    "note")}
    # What an acquired image is cited by, and deleted material's marking,
    # cross with it where the answer carries them.
    meta.update({k: got[k] for k in ("collection", "collection_name", "key",
                                     "deleted") if k in got})
    meta["path"] = path
    return meta, data


def _over_for(via, record, name, args, capability, workroot, also=()):
    """One operation over the wire, with the two that carry bytes handled on
    THIS side of it. Shared by both transports so they cannot differ.

    Returns (value, data): `data` is the bytes `read_artifact` wrote into the
    worker's directory, and None for everything else.
    """
    if name == "return_artifact":
        return _over(via, record, name,
                     _read_for_return(args, workroot, also), capability), None
    if name == "read_artifact":
        got = _over(via, record, name, args, capability)
        return _materialise(got, workroot)
    return _over(via, record, name, args, capability), None


def _parse(argv: list[str]) -> tuple[str, dict]:
    """The command line a worker types, as an operation and its arguments.

    Lifted out of `ask` unchanged so that both ways of reaching Mentis -- in
    this process, or across the boundary at a server that owns the corpus --
    understand exactly the same command. A second parser would be a second
    grammar, and the two would drift.
    """
    name, rest = argv[0], list(argv[1:])
    args: dict[str, Any] = {}
    loose: list[str] = []
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            key = rest[i][2:]
            args[key] = rest[i + 1] if i + 1 < len(rest) else ""
            i += 2
        else:
            loose.append(rest[i])
            i += 1
    # The obvious positional for each, so a worker can type the short form.
    if loose:
        if name == "find":
            args.setdefault("q", " ".join(loose))
        elif name == "resolve":
            args.setdefault("ref", loose[0])
        elif name == "history":
            args.setdefault("conversation", loose[0])
        elif name == "read_source":
            args.setdefault("ref", loose[0])
        elif name == "sources":
            args.setdefault("collection", loose[0])
        elif name == "search_sources":
            args.setdefault("q", " ".join(loose))
    return name, args


class NoOwner(Exception):
    """No Mentis process is serving the corpus this question is about.

    Its own exception because it is an answer, not a malfunction, and because
    the one thing that must never happen here is a quiet fall back to opening
    the corpus directly. A worker that cannot reach the owner has not been
    told the record is empty; it has been told it could not ask.
    """


class OwnerError(Exception):
    """The owner was reached and could not answer: it was asked something
    malformed, or failed answering. Not a refusal, and not "nobody is there"."""


#: How long a worker waits for the owner to answer one operation over
#: `/api/worker`.
ASK_TIMEOUT_S = 30


def _over(via: str, record: str, name: str, args: dict,
           capability: str | None = None) -> dict:
    """Ask the process that owns the corpus, and open nothing here.

    WHY THE QUESTION LEAVES THE WORKER AT ALL. A sandboxed worker cannot open
    this record even to read it: the spine is WAL, SQLite writes `-shm` beside
    a WAL database before it will read one, and the corpus is deliberately
    outside the only directory such a worker may write. The fix is not to
    widen what the worker may touch -- it is for the worker to stop touching
    the corpus. WORKER FILESYSTEM PERMISSIONS MUST NOT DETERMINE CORPUS
    PERMISSIONS, and after this they cannot: nothing on this side of the wire
    holds a corpus handle.

    What crosses is an operation, its arguments, which corpus is being
    asked about, and the opaque grant this execution was started with. No
    path is dereferenced here; the corpus is named so the owner can refuse
    a question about a record it does not hold rather than silently
    answering about a different one, and the grant is what makes the
    question admissible at all -- BEING ABLE TO REACH THE SERVER IS NOT
    PERMISSION TO ASK IT ANYTHING.

    The far side runs `_result` on the `Surface` it already has open. Same
    dispatch, same resolver, same semantics as the MCP server and the web
    seam; only the wire differs.
    """
    import urllib.error
    import urllib.request

    body = json.dumps({"corpus": record, "op": name, "args": args})
    req = urllib.request.Request(
        via.rstrip("/") + "/api/worker", method="POST",
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json",
                 CAPABILITY_HEADER: capability or ""})
    try:
        with urllib.request.urlopen(req, timeout=ASK_TIMEOUT_S) as fh:
            payload = json.loads(fh.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1200]
        try:
            said = json.loads(detail).get("error") or detail
        except (ValueError, AttributeError):
            said = detail
        if exc.code == 403:
            # A REFUSAL IS AN ANSWER FROM AN OWNER THAT IS THERE. It used to be
            # raised as NoOwner, so a worker refused a file it had not been
            # given was told Mentis was unreachable -- which reads as a
            # malfunction to retry, when the answer was "you may not".
            raise NotPermitted(said) from exc
        raise OwnerError(f"Mentis at {via} could not answer this: {said}") \
            from exc
    except OSError as exc:
        if isinstance(exc, urllib.error.URLError) and isinstance(
                exc.reason, TimeoutError):
            # TIMED OUT BEFORE THE REQUEST WAS SENT. urllib wraps an error in
            # URLError only while connecting and sending (`do_open` around
            # `h.request`); waiting for the answer raises TimeoutError bare.
            # Mentis never had the whole request, so it did nothing with it
            # (found by review: this said "may still have done it").
            raise OwnerError(
                f"Mentis at {via} did not take {name!r} within "
                f"{ASK_TIMEOUT_S:g} s: the connection or the sending of the "
                f"request timed out, so it never received it and NOTHING WAS "
                f"DONE. Call it again.") from exc
        if isinstance(exc, TimeoutError):
            # NOT "NOBODY IS THERE". Measured 2026-10-24: the server was up
            # (its root page answered in 2 ms) and still working on the call,
            # and finished it -- a commit landed -- after this side gave up.
            # Saying nobody answered made runs report work as not done.
            raise OwnerError(
                f"Mentis at {via} did not answer {name!r} within "
                f"{ASK_TIMEOUT_S:g} s. It may still have done it: do not "
                f"report it as not done. Check the record, or call it "
                f"again if it is safe to repeat.") from exc
        raise NoOwner(
            f"no Mentis is answering at {via} for corpus {record!r}: {exc}. "
            "The record can only be read by the process that owns it, so "
            "there is no answer to give and nothing else to try."
        ) from exc
    if isinstance(payload, dict) and "error" in payload and len(payload) == 1:
        raise NoOwner(payload["error"])
    return payload


def ask(record: str, argv: list[str], *, via: str | None = None,
        capability: str | None = None) -> int:
    """One question, one JSON answer, over the same four operations.

    WHY A SECOND TRANSPORT AND NOT A SECOND IMPLEMENTATION. A Codex server
    configured with a command that writes a marker file was never started,
    so the stdio server the other two runtimes get did not reach it. The
    second half of what used to be written here -- that codex's rollout
    recorded a tool set of `shell`, `apply_patch`, `update_plan` -- was a
    misreading: those were substrings of environment text (`"shell":
    "powershell"`), and the rollout records no tool definitions at all.

    What codex headless DOES have is a shell tool. So the capability arrives
    by being run rather than by being connected to, and it goes through
    `_result` -- the same dispatch the MCP server calls, onto the same
    `Surface`. There is one resolver in this process and one set of
    semantics; only the wire differs. A worker that shells out to this is not
    reading the corpus, it is asking Mentis.

    Deliberately read-only, deliberately the same four names, and it prints
    JSON so the answer is as machine-readable as the MCP one.
    """
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0 if argv else 2

    name, args = _parse(argv)

    try:
        # `via` names the process that owns the corpus. With one, this opens
        # nothing; without one, it is the same in-process call as before, for
        # the callers that legitimately hold the record.
        if via:
            import os
            value, data = _over_for(via, record, name, args, capability,
                                    os.path.realpath(os.getcwd()))
            if data is not None and value.get("view") in ("text", "markdown",
                                                         "html"):
                value["text"] = data.decode("utf-8")
        else:
            value = _result(Surface(record), name, args)
    except KeyError:
        print(json.dumps({"error": f"no such tool {name!r}",
                          "tools": [t["name"] for t in ALL_TOOLS]}))
        return 2
    except NotPermitted as exc:
        # REFUSED, by an owner that is there. Its own answer, so a worker does
        # not read "you may not" as "could not ask" and try again elsewhere.
        print(json.dumps({"error": "refused", "why_not": str(exc),
                          "asked": name}))
        return 4
    except NoOwner as exc:
        # Explicitly unanswerable, and deliberately NOT retried against the
        # corpus on disk. Three separate answers stay separate: this is
        # "could not ask", not "unknown" and not "empty".
        print(json.dumps({"error": "no Mentis owner for this record",
                          "why_not": str(exc), "asked": name}))
        return 3
    except Exception as exc:
        # Said out loud. A query that could not be answered must not look
        # like a record that holds nothing.
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 1
    print(json.dumps(value, indent=1, default=str))
    return 0


def serve(corpus_path: str, *, via: str | None = None,
          capability: str | None = None, permits=None,
          scratch: str | None = None, project: str | None = None,
          session: str | None = None) -> None:
    """The MCP transport for the same four reads.

    `permits` MAKES WHAT IS VISIBLE MATCH WHAT IS AUTHORISED, and it exists
    because the two came apart. This surface briefly advertised every operation
    to every bounded run, on the reasoning that the door refuses what a run may
    not do and an explicit refusal beats a missing tool. MEASURED CONSEQUENCE:
    an ordinary specialist, explicitly addressed for a small piece of work, was
    shown `delegate`, `respond` and `summon_participant`, correctly concluded it
    could not be looking at Mark IV's own surface, and declined to call anything
    at all. It reported the discrepancy; its restraint is not a boundary, and a
    worker that has to distrust its own tools has been handed a worse surface
    than a smaller one.

    So the offered set is now the run's own. Foundation derives it from the
    grant's scope and passes it here. THE DOOR STILL CHECKS INDEPENDENTLY: this
    decides what is SHOWN, `/api/worker` decides what is ALLOWED, and neither
    relies on the other being right. Absent, only the reads are offered, which
    fails closed.

    ONE BOUNDARY, TWO WIRES. With `via` this opens no corpus at all: every
    call goes to the process that owns the record over `/api/worker`, under
    the grant this execution was started with, and lands on `_result` against
    the `Surface` that process already holds. That is the identical path the
    Codex shell transport takes, so the two differ only in how the question
    travels -- not in what may be asked, of which corpus, or by whom.

    WHY THAT MATTERS AND WAS WRONG BEFORE. Without `via` this constructs a
    `Surface` here, which means the WORKER process opens corpus.db. Two
    runtimes were served that way while the third was bounded, so the same
    four operations had two different capability boundaries and a worker's
    filesystem permissions decided corpus permissions for two of them. The
    direct path remains only for a caller that legitimately holds the record
    -- the CLI, and tests -- and a dispatched worker is never given it.
    """
    surface: Surface | None = None
    out = sys.stdout
    # MCP stdio IS UTF-8, WHATEVER THE MACHINE'S CODE PAGE. Every runtime starts
    # this with `-I`, which ignores PYTHONUTF8 and PYTHONIOENCODING, so on
    # Windows sys.stdin was cp1252 with surrogateescape. Measured: an em dash
    # arrived as mojibake, and U+201D (whose third byte cp1252 does not map)
    # as a lone surrogate the store then refused to encode.
    if hasattr(out, "reconfigure"):
        out.reconfigure(encoding="utf-8")
    raw = getattr(sys.stdin, "buffer", None)
    lines = (b.decode("utf-8", "replace") for b in raw) if raw is not None \
        else sys.stdin
    # A WORKER THAT OPENS THE RECORD ITSELF REFUSES TO START on a Brain that is
    # missing or that the schema check does not open writable -- before it
    # answers anything, not at its first tool call. With `via` it opens none.
    if not via:
        from mentis.spine import brainlock, migrations
        try:
            st = migrations.status_of(corpus_path)
        except (migrations.BrainMissing, brainlock.BrainBusy) as exc:
            print(f"Mentis worker refused to start: {exc}", file=sys.stderr)
            raise SystemExit(3)
        if not st.writable:
            print(f"Mentis worker refused to start: {st.explain(corpus_path)}",
                  file=sys.stderr)
            raise SystemExit(3)
    # THIS EXECUTION'S PRIVATE SCRATCH bounds what it may return and is where
    # artifacts it reads are written -- NAMED by Foundation, not taken from
    # whatever directory a runtime happened to start this process in. Without
    # one (a caller that holds the record), the process's own directory.
    import os
    workroot = os.path.realpath(scratch or os.getcwd())
    also = (os.path.realpath(project),) if project else ()
    # FAIL CLOSED. An unbounded caller holds no grant, so no operation could be
    # admitted for it and none is shown; a bounded run shows what it was told it
    # may do, intersected with what actually exists so a stale or invented name
    # can never conjure a tool.
    # A HAND-STARTED SESSION (`session`, the machine-wide registration) holds
    # no grant until it asks for one, and asks again if the server forgot it
    # (a restart). What it is SHOWN is `permitted(SESSION_SCOPE)`, the same
    # function the door admits by, so nothing waits on the server to list tools.
    held = {"grant": capability, "execution": None}
    if via and session and not capability:
        permits = permitted(SESSION_SCOPE)
    allowed = set(permits or READS)
    offered = [t for t in ALL_TOOLS if t["name"] in allowed] if via else TOOLS

    def _granted(fresh: bool = False) -> str | None:
        if not (via and session) or capability:
            return held["grant"]
        if fresh or not held["grant"]:
            # A RENEWAL CONTINUES THE SAME EXECUTION, so what this session
            # opened before the server forgot its grant is still its own.
            got = _session_grant(via, corpus_path, session,
                                 continues=held["execution"])
            held["grant"], held["execution"] = got["grant"], got["execution"]
        return held["grant"]

    def _call(name, args):
        try:
            return _over_for(via, corpus_path, name, args, _granted(),
                             workroot, also)
        except NotPermitted as exc:
            if not (session and "needs a live worker grant" in str(exc)):
                raise
            return _over_for(via, corpus_path, name, args, _granted(True),
                             workroot, also)

    def send(msg: dict) -> None:
        out.write(json.dumps(msg) + "\n")
        out.flush()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        rid, method = req.get("id"), req.get("method")

        if method == "initialize":
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mentis-mark-iv", "version": "1"},
            }})
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            # EXACTLY WHAT THIS RUN MAY DO. Not every operation that exists, and
            # not a set that depends on which wire carried the question: the
            # run's own permitted names, decided by Foundation from the grant.
            # An ordinary worker therefore SEES the four reads and
            # `request_decision`, because that is what it has.
            send({"jsonrpc": "2.0", "id": rid, "result": {"tools": offered}})
        elif method == "tools/call":
            params = req.get("params") or {}
            try:
                name = params.get('name')
                args = params.get('arguments') or {}
                if via:
                    # Nothing on this side holds a corpus handle. Files cross
                    # as bytes, read and written in this worker's directory.
                    value, data = _call(name, args)
                    if data is not None:
                        content = [{"type": "text",
                                    "text": json.dumps(value, indent=1)}]
                        if value["view"] == "image":
                            import base64
                            content.append({
                                "type": "image", "mimeType": value["served_as"],
                                "data": base64.b64encode(data).decode("ascii")})
                        elif value["view"] in ("text", "markdown", "html"):
                            content.append({"type": "text",
                                            "text": data.decode("utf-8")})
                        send({"jsonrpc": "2.0", "id": rid,
                              "result": {"content": content}})
                        continue
                else:
                    if surface is None:
                        surface = Surface(corpus_path)
                    value = _result(surface, name, args)
                body = json.dumps(value, indent=1, default=str)
                send({"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": body}]}})
            except Exception as exc:
                # A failure is reported as a failure. A tool that returned an
                # empty answer on error would teach a worker that the record
                # is empty, which is the exact mistake this surface exists to
                # stop.
                send({"jsonrpc": "2.0", "id": rid, "result": {
                    "isError": True,
                    "content": [{"type": "text",
                                 "text": f"{type(exc).__name__}: {exc}"}]}})
        elif rid is not None:
            send({"jsonrpc": "2.0", "id": rid,
                  "error": {"code": -32601, "message": f"no method {method!r}"}})
    if via and session and not capability and held["grant"]:
        _session_end(via, corpus_path, held["grant"])


def _session_post(via: str, path: str, body: dict) -> dict:
    """One owner request to `SESSION_ROUTE` or its `/end`. JSON in, JSON out."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        via.rstrip("/") + path, method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as fh:
            return json.loads(fh.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1200]
        raise OwnerError(f"Mentis at {via} gave this session no grant: "
                         f"{detail}") from exc
    except OSError as exc:
        raise NoOwner(f"no Mentis is answering at {via}: {exc}") from exc


def _session_grant(via: str, record: str, runtime: str,
                   continues: str | None = None) -> dict:
    """Ask the server for a hand-started session's grant. See SESSION_ROUTE.

    `continues` names the execution this session already is, on renewal."""
    return _session_post(via, SESSION_ROUTE,
                         {"corpus": record, "runtime": runtime,
                          **({"continues": continues} if continues else {})})


def _session_end(via: str, record: str, grant: str) -> None:
    """Give a session's grant back. Best effort: a restart forgets it anyway."""
    try:
        _session_post(via, SESSION_ROUTE + "/end",
                      {"corpus": record, "grant": grant})
    except (OwnerError, NoOwner):
        pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m mentis.worker <corpus-path> [ask ...]")
    if len(sys.argv) > 2 and sys.argv[2] == "ask":
        raise SystemExit(ask(sys.argv[1], sys.argv[3:]))
    serve(sys.argv[1])
